package io.insightradar.v002;
import com.fasterxml.jackson.databind.node.*;
import io.insightradar.v002.market.DataQualityValidator;
import io.insightradar.v002.market.MarketWindow;
import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class DataQualityTest {
 ObjectNode input(){ObjectNode root=Json.MAPPER.createObjectNode();root.set("identity",Json.MAPPER.valueToTree(Map.of("providerCode","sz.002463","listStatus","LISTED")));var ds=TechR1Test.dates(65);ArrayNode cal=root.putArray("calendar"),raw=root.putArray("raw"),qfq=root.putArray("qfq");for(var d:ds)cal.addObject().put("calendar_date",d.toString()).put("is_trading_day","1");for(int i=0;i<60;i++){var b=TechR1Test.bars(60,true).get(i);var row=raw.addObject();row.put("date",b.date().toString()).put("code","sz.002463").put("open",b.open().toPlainString()).put("high",b.high().toPlainString()).put("low",b.low().toPlainString()).put("close",b.close().toPlainString()).put("volume","100").put("amount","1000").put("tradestatus","1").put("adjustflag","3");ObjectNode q=row.deepCopy();q.put("adjustflag","2");for(String k:List.of("open","high","low","close"))q.put(k,new java.math.BigDecimal(row.path(k).asText()).multiply(TechR1Test.n("0.5")).toPlainString());qfq.add(q);}root.putArray("adjustmentEvents");return root;}
 LocalDate today(){return TechR1Test.dates(65).get(60);}
 @Test void normalizationAnchorsToRawClose(){var s=new DataQualityValidator().validate(input(),window(today(),9,0));assertThat(s.reliable()).isTrue();assertThat(s.fresh()).isTrue();assertThat(s.bars().getLast().close()).isEqualByComparingTo("159");assertThat(s.bars().getFirst().close()).isEqualByComparingTo("100");}
 @Test void invalidAndDuplicateAndMissingDatesFailClosed(){for(String type:List.of("negative","duplicate","missing","volume","factor")){var i=input();switch(type){case "negative"->((ObjectNode)i.path("raw").get(2)).put("close","-1");case "duplicate"->((ArrayNode)i.path("raw")).add(i.path("raw").get(0));case "missing"->((ArrayNode)i.path("qfq")).remove(5);case "volume"->((ObjectNode)i.path("qfq").get(5)).put("volume","101");case "factor"->((ObjectNode)i.path("qfq").get(5)).put("open","1");}assertThat(new DataQualityValidator().validate(i,window(today(),9,0)).reliable()).as(type).isFalse();}}
 @Test void suspensionNotCountedAndFreshnessBlocksPlan(){var i=input();((ObjectNode)i.path("raw").get(59)).put("tradestatus","0");((ObjectNode)i.path("qfq").get(59)).put("tradestatus","0");var s=new DataQualityValidator().validate(i,window(today(),9,0));assertThat(s.bars()).hasSize(59);assertThat(s.fresh()).isFalse();}
 @Test void duringSessionRejectsSameDayBar(){assertThat(new DataQualityValidator().validate(input(),window(TechR1Test.dates(65).get(59),14,59)).reliable()).isFalse();}
 @Test void missingIntermediateOpenSessionRejected(){var i=input();((ArrayNode)i.path("raw")).remove(30);((ArrayNode)i.path("qfq")).remove(30);assertThat(new DataQualityValidator().validate(i,window(today(),9,0)).gaps()).anyMatch(s->s.startsWith("MISSING_OPEN_SESSION"));}

 static MarketWindow window(LocalDate date,int hour,int minute) {
  return new MarketWindow(date.atTime(hour,minute).atZone(MarketWindow.ZONE).toInstant());
 }
 @Test void shanghaiPhaseAndFinalityAreIndependent() {
  var source = input();
  var validator = new DataQualityValidator();
  var day = TechR1Test.dates(65).get(59);
  var prior = day.minusDays(1);
  var withoutToday = source.deepCopy();
  for (String kind : List.of("raw", "qfq")) ((ArrayNode) withoutToday.path(kind)).remove(59);
  for (var cutoff : List.of(window(day,9,14),window(day,9,15),window(day,14,59))) {
   var previous = validator.validate(withoutToday,cutoff);
   assertThat(previous.fresh()).isTrue();
   assertThat(previous.asOfTradeDate()).isEqualTo(prior);
   assertThat(cutoff.phase(previous.sessions())).isEqualTo(cutoff.time().isBefore(MarketWindow.OPEN) ? "PRE_OPEN" : "IN_SESSION");
  }
  var pending = validator.validate(withoutToday,window(day,15,0));
  assertThat(pending.expectedDate()).isEqualTo(day);
  assertThat(pending.asOfTradeDate()).isEqualTo(prior);
  assertThat(pending.reliable()).isTrue();
  assertThat(pending.fresh()).isFalse();
  assertThat(pending.gaps()).contains("TODAY_FINAL_BAR_AWAITING_PROVIDER:"+day);
  assertThat(validator.validate(source,window(day,17,59)).reliable()).isFalse();
  assertThat(validator.validate(source,window(day,18,0)).reliable()).isFalse();

  source.put("requestedEnd",day.toString()).put("finalityPolicy",MarketWindow.POLICY)
      .put("fetchedAt",MarketWindow.releaseAt(day).minusSeconds(1).toString());
  assertThat(validator.validate(source,window(day,18,0)).reliable()).isFalse();
  source.put("fetchedAt",MarketWindow.releaseAt(day).toString());
  var finalBar = validator.validate(source,window(day,18,0));
  assertThat(finalBar.asOfTradeDate()).isEqualTo(day);
  assertThat(finalBar.fresh()).isTrue();
  assertThat(finalBar.priceBasis()).containsEntry("anchorRawClose", new java.math.BigDecimal("159"));
  var delayed = validator.validate(withoutToday,window(day,18,0));
  assertThat(delayed.reliable()).isTrue();
  assertThat(delayed.fresh()).isFalse();
  assertThat(delayed.gaps()).contains("LATEST_SESSION_MISSING_SUSPENDED_OR_DELISTED:"+day);
 }

 @Test void nonTradingDayKeepsPreviousExchangeSession() {
  var source = input();
  ((ObjectNode) source.path("calendar").get(60)).put("is_trading_day","0");
  var window = window(today(),18,0);
  var snap = new DataQualityValidator().validate(source,window);
  assertThat(window.phase(snap.sessions())).isEqualTo("NON_TRADING_DAY");
  assertThat(snap.fresh()).isTrue();
  assertThat(snap.asOfTradeDate()).isEqualTo(today().minusDays(1));
 }
}
