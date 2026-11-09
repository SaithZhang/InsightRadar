package io.insightradar.v002;
import io.insightradar.v002.analysis.AnalysisOrchestrator;
import io.insightradar.v002.api.AppException;
import io.insightradar.v002.market.MarketDataProvider;
import io.insightradar.v002.market.MarketWindow;
import io.insightradar.v002.disclosure.DisclosureProvider;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor;
import io.insightradar.v002.persistence.SnapshotRepository;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class DegradationTest {
 ObjectNode freshInput(){var root=new DataQualityTest().input();var window=new MarketWindow(Instant.now());root.put("fetchedAt",window.cutoff().toString()).put("finalityPolicy",MarketWindow.POLICY).put("requestedEnd",window.requestThrough().toString());root.put("sourceHash","synthetic-unit-only");var i=(ObjectNode)root.path("identity");i.put("canonicalCode","002463.SZ").put("sixDigitCode","002463").put("name","SYNTHETIC TEST").put("exchange","SZ");var dates=new ArrayList<LocalDate>();LocalDate d=window.requestThrough();while(dates.size()<60){if(d.getDayOfWeek().getValue()<6)dates.addFirst(d);d=d.minusDays(1);}for(int n=0;n<60;n++){((ObjectNode)root.path("raw").get(n)).put("date",dates.get(n).toString());((ObjectNode)root.path("qfq").get(n)).put("date",dates.get(n).toString());}ArrayNode cal=root.putArray("calendar");LocalDate first=dates.getFirst(),end=LocalDate.now(ZoneId.of("Asia/Shanghai")).plusDays(10);for(d=first;!d.isAfter(end);d=d.plusDays(1))cal.addObject().put("calendar_date",d.toString()).put("is_trading_day",d.getDayOfWeek().getValue()<6?"1":"0");return root;}
 Map<String,Object> run(boolean missingMarket)throws Exception{
  var market=mock(MarketDataProvider.class);if(missingMarket)when(market.snapshot(anyString(),isNull(),any())).thenThrow(new AppException("MARKET_COVERAGE_UNAVAILABLE","No BSE coverage","MARKET",false,503));else when(market.snapshot(anyString(),isNull(),any())).thenReturn(freshInput());
  var disclosure=mock(DisclosureProvider.class);when(disclosure.collect(anyString(),nullable(String.class),any())).thenReturn(new DisclosureProvider.Bundle(List.of(),Map.of(),Map.of("state","UNAVAILABLE"),List.of("OFFICIAL_SOURCE_UNAVAILABLE"),Map.of()));
  var repo=mock(SnapshotRepository.class);var id=UUID.randomUUID();when(repo.create(anyString())).thenReturn(id);when(repo.market(anyString(),any(),any())).thenAnswer(call->new SnapshotRepository.StoredMarket(UUID.randomUUID(),call.getArgument(1),"synthetic-test"));var latch=new CountDownLatch(1);var captured=new AtomicReference<Map<String,Object>>();doAnswer(invocation->{captured.set(invocation.getArgument(1));latch.countDown();return null;}).when(repo).finish(eq(id),anyMap(),nullable(UUID.class));
  var service=new AnalysisOrchestrator(market,disclosure,new LlmEvidenceExtractor("","","","target/test-data","",java.math.BigDecimal.ZERO,null),repo,mock(io.insightradar.v002.persistence.PositionRepository.class),mock(io.insightradar.v002.market.TencentClosingQuote.class));try{service.submit(missingMarket?"920029.BJ":"002463",LlmEvidenceExtractor.Mode.PRODUCTION);assertThat(latch.await(10,TimeUnit.SECONDS)).isTrue();return captured.get();}finally{service.stop();}
 }
 @Test void T19_semanticFailurePreservesTechnicalResult()throws Exception{var r=run(false);assertThat(r.get("technicalStatus")).isEqualTo(((Map<?,?>)r.get("marketTiming")).get("awaitingPublication").equals(true)?"UNKNOWN":"READY");assertThat(r.get("eventStatus")).isEqualTo("UNAVAILABLE");assertThat(r.get("status")).isEqualTo("PARTIAL");assertThat(r.get("trade_authority")).isEqualTo("none");}
 @Test void T20_coverageUnavailableNeverCreatesPrices()throws Exception{var r=run(true);assertThat(r.get("technicalStatus")).isEqualTo("UNKNOWN");assertThat((List<?>)r.get("candles")).isEmpty();assertThat(r.get("buyPlan")).isNull();assertThat(r.get("canonicalCode")).isNull();assertThat(Json.write(r)).contains("MARKET_COVERAGE_UNAVAILABLE");}
}
