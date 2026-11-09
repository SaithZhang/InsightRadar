package io.insightradar.v002.market;

import com.fasterxml.jackson.databind.node.ObjectNode;
import io.insightradar.v002.Json;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class TencentClosingQuoteTest {
 private static final MarketWindow AFTER_CLOSE = new MarketWindow(Instant.parse("2026-11-09T07:15:00Z"));

 @Test void agreesWithTencentClosedMarketSnapshotAndUnadjustedDayBar() {
  var quote = TencentClosingQuote.parse(response(), "sz002463", AFTER_CLOSE).orElseThrow();
  assertThat(quote.tradeDate()).isEqualTo(LocalDate.of(2026, 11, 9));
  assertThat(quote.canonicalCode()).isEqualTo("002463.SZ");
  assertThat(quote.close()).isEqualByComparingTo("77.10");
  assertThat(quote.quotedAt().toString()).isEqualTo("2026-11-09T15:00:30+08:00");
  assertThat(TencentClosingQuote.ticker("002463")).isEqualTo("sz002463");
  assertThat(TencentClosingQuote.ticker("002463.SH")).isNull();
 }

 @Test void rejectsIntradayStaleSuspendedConflictingAndMismatchedQuotes() {
  var intraday = new MarketWindow(Instant.parse("2026-11-09T06:59:59Z"));
  assertThat(TencentClosingQuote.parse(response(), "sz002463", intraday)).isEmpty();
  var nextDay = new MarketWindow(Instant.parse("2026-11-10T08:00:00Z"));
  assertThat(TencentClosingQuote.parse(response(), "sz002463", nextDay)).isEmpty();
  for (String problem : new String[] {"open", "stale", "suspended", "mismatch", "conflict", "no-trades"}) {
   var candidate = response();
   var stock = candidate.withObject("/data/sz002463");
   var qt = stock.withObject("qt");
   var quote = qt.withArray("sz002463");
   switch (problem) {
    case "open" -> qt.withArray("market").set(0, "2026-11-09 15:15:00|SZ_open_交易中");
    case "stale" -> quote.set(30, "20261106150000");
    case "suspended" -> quote.set(40, "S");
    case "mismatch" -> quote.set(2, "002464");
    case "conflict" -> ((com.fasterxml.jackson.databind.node.ArrayNode) stock.path("day").path(0)).set(2, "77.11");
    case "no-trades" -> quote.set(6, "0");
   }
   assertThat(TencentClosingQuote.parse(candidate, "sz002463", AFTER_CLOSE)).as(problem).isEmpty();
  }
 }

 private static ObjectNode response() {
  var root = Json.MAPPER.createObjectNode().put("code", 0);
  var stock = root.putObject("data").putObject("sz002463");
  stock.putArray("day").addArray().add("2026-11-09").add("74.49").add("77.100").add("79.80").add("72.10").add("841738");
  var qt = stock.putObject("qt");
  qt.putArray("market").add("2026-11-09 15:15:00|SH_close_已收盘|SZ_close_已收盘");
  var quote = qt.putArray("sz002463");
  var fields = Map.of(0,"51",1,"沪电股份",2,"002463",3,"77.10",6,"841738",30,"20261109150030");
  for (int i = 0; i <= 40; i++) quote.add(fields.getOrDefault(i, ""));
  return root;
 }
}
