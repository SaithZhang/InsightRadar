package io.insightradar.v002;
import io.insightradar.v002.analysis.AnalysisOrchestrator;
import io.insightradar.v002.market.MarketDataProvider;
import io.insightradar.v002.persistence.SnapshotRepository;
import io.insightradar.v002.technical.TechR1;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class PlanReviewTest {
 @Test void targetFingerprintIgnoresLaterUnrelatedBarsAndFetchTime(){var repo=mock(SnapshotRepository.class);var market=mock(MarketDataProvider.class);var p=new TechR1.Plan(UUID.randomUUID().toString(),UUID.randomUUID().toString(),"002463.SZ",LocalDate.of(2025,1,2),LocalDate.of(2025,1,3),TechR1Test.plan().zone(),"NORMALIZED_QFQ_AT_D",LocalDate.of(2025,1,2),"h","TECH-R1","WAITING_NEXT_BAR");var report=Json.MAPPER.valueToTree(Map.of("buyPlan",p,"priceBasis",Map.of("anchorRawClose","11")));when(repo.planReport(any())).thenReturn(report);when(repo.evaluations(any())).thenReturn(List.of());
  ObjectNode source=Json.MAPPER.createObjectNode();source.set("identity",Json.MAPPER.valueToTree(Map.of("canonicalCode","002463.SZ")));source.putArray("adjustmentEvents");var raw=source.putArray("raw");for(var d:List.of("2025-01-02","2025-01-03")){raw.addObject().put("date",d).put("tradestatus","1").put("open","11").put("high","14").put("low","10").put("close",d.endsWith("02")?"11":"13").put("volume","100").put("amount","1000");}source.set("qfq",raw.deepCopy());var cal=source.putArray("calendar");for(var d:List.of("2025-01-02","2025-01-03","2025-01-06"))cal.addObject().put("calendar_date",d).put("is_trading_day","1");when(market.snapshot(anyString(),any(),any())).thenReturn(source);
  var hashes=new ArrayList<String>();when(repo.appendEvaluation(any(),any(),any(),anyString(),anyString(),anyMap())).thenAnswer(inv->{hashes.add(inv.getArgument(4));return Json.MAPPER.valueToTree(inv.getArgument(5));});var service=new AnalysisOrchestrator(market,null,null,repo,null,null);try{assertThat(service.evaluate(UUID.fromString(p.id())).path("status").asText()).isEqualTo("TECHNICAL_CONDITION_MET");var later=raw.get(1).deepCopy();((ObjectNode)later).put("date","2025-01-06");raw.add(later);((ArrayNode)source.path("qfq")).add(later.deepCopy());source.put("fetchedAt",Instant.now().toString());service.evaluate(UUID.fromString(p.id()));assertThat(hashes.get(0)).isEqualTo(hashes.get(1));}finally{service.stop();}
 }
}
