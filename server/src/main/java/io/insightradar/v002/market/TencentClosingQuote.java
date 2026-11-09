package io.insightradar.v002.market;

import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.Json;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Arrays;
import java.util.Locale;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class TencentClosingQuote {
 public record Quote(String canonicalCode, String name, LocalDate tradeDate, BigDecimal close,
                     OffsetDateTime quotedAt, String source) {}

 private record Cached(Quote quote, Instant checkedAt) {}

 private static final String ENDPOINT = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=";
 private static final Duration TTL = Duration.ofMinutes(5);
 private static final DateTimeFormatter QUOTE_TIME = DateTimeFormatter.ofPattern("uuuuMMddHHmmss")
     .withResolverStyle(ResolverStyle.STRICT);
 private static final DateTimeFormatter MARKET_TIME = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss")
     .withResolverStyle(ResolverStyle.STRICT);

 private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
 private final ConcurrentHashMap<String, Cached> cache = new ConcurrentHashMap<>();

 public Optional<Quote> find(String code, MarketWindow window) {
  if (window.time().isBefore(MarketWindow.CLOSE)) return Optional.empty();
  String ticker = ticker(code);
  if (ticker == null) return Optional.empty();
  Instant now = Instant.now();
  cache.entrySet().removeIf(entry -> entry.getValue().checkedAt().plus(TTL).isBefore(now));
  var cached = cache.compute(ticker, (key, existing) -> {
   if (existing != null && existing.quote().tradeDate().equals(window.date())) return existing;
   return fetch(ticker, window).map(quote -> new Cached(quote, Instant.now())).orElse(null);
  });
  return Optional.ofNullable(cached).map(Cached::quote)
      .filter(quote -> !quote.quotedAt().toInstant().isAfter(window.cutoff()));
 }

 private Optional<Quote> fetch(String ticker, MarketWindow window) {
  var date = window.date();
  var request = HttpRequest.newBuilder(URI.create(ENDPOINT + ticker + ",day," + date + "," + date + ",3,"))
      .timeout(Duration.ofSeconds(5)).header("User-Agent", "Mozilla/5.0 InsightRadar").GET().build();
  try {
   var response = http.send(request, HttpResponse.BodyHandlers.ofString());
   if (response.statusCode() != 200 || response.body().length() > 100_000) return Optional.empty();
   return parse(Json.read(response.body()), ticker, window);
  } catch (InterruptedException e) {
   Thread.currentThread().interrupt();
   return Optional.empty();
  } catch (java.io.IOException | IllegalArgumentException e) {
   return Optional.empty();
  }
 }

 static String ticker(String code) {
  String six = code.split("\\.", 2)[0];
  String exchange;
  if (six.matches("(60|68)[0-9]{4}")) exchange = "SH";
  else if (six.matches("(00|30)[0-9]{4}")) exchange = "SZ";
  else return null;
  return code.equals(six) || code.equals(six + "." + exchange) ? exchange.toLowerCase(Locale.ROOT) + six : null;
 }

 static Optional<Quote> parse(JsonNode response, String ticker, MarketWindow window) {
  if (window.time().isBefore(MarketWindow.CLOSE) || response.path("code").asInt(-1) != 0) return Optional.empty();
  String exchange = ticker.substring(0, 2).toUpperCase(Locale.ROOT);
  String code = ticker.substring(2);
  var stock = response.path("data").path(ticker);
  var qt = stock.path("qt");
  var quote = qt.path(ticker);
  if (!code.equals(quote.path(2).asText()) || quote.path(1).asText().isBlank() ||
      !("SH".equals(exchange) ? "1" : "51").equals(quote.path(0).asText()) ||
      !quote.path(40).asText().isEmpty()) return Optional.empty();

  try {
   var date = window.date();
   var state = qt.path("market").path(0).asText().split("\\|");
   var marketAt = LocalDateTime.parse(state[0], MARKET_TIME);
   var quotedAt = LocalDateTime.parse(quote.path(30).asText(), QUOTE_TIME);
   if (!marketAt.toLocalDate().equals(date) || marketAt.toLocalTime().isBefore(MarketWindow.CLOSE) ||
       !quotedAt.toLocalDate().equals(date) || quotedAt.toLocalTime().isBefore(MarketWindow.CLOSE) ||
       quotedAt.isAfter(marketAt) || Arrays.stream(state).noneMatch((exchange + "_close_已收盘")::equals)) return Optional.empty();
   var close = new BigDecimal(quote.path(3).asText());
   if (close.signum() <= 0 || new BigDecimal(quote.path(6).asText()).signum() <= 0) return Optional.empty();

   for (var bar : stock.path("day")) {
    if (bar.path(0).asText().equals(date.toString()) &&
        new BigDecimal(bar.path(2).asText()).compareTo(close) == 0 &&
        new BigDecimal(bar.path(5).asText()).signum() > 0) {
     return Optional.of(new Quote(code + "." + exchange, quote.path(1).asText(), date, close,
         quotedAt.atZone(MarketWindow.ZONE).toOffsetDateTime(), "tencent"));
    }
   }
  } catch (DateTimeException | NumberFormatException e) {
   return Optional.empty();
  }
  return Optional.empty();
 }
}
