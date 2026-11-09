package io.insightradar.v002;
import io.insightradar.v002.technical.TechR1;
import io.insightradar.v002.technical.TechR1.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import java.math.*;
import java.time.*;
import java.util.*;
import java.nio.file.*;
import static org.assertj.core.api.Assertions.*;
class TechR1Test {
 static BigDecimal n(String s){return new BigDecimal(s);}
 static List<LocalDate> dates(int count){var ds=new ArrayList<LocalDate>();LocalDate d=LocalDate.of(2025,1,2);while(ds.size()<count){if(d.getDayOfWeek().getValue()<6)ds.add(d);d=d.plusDays(1);}return ds;}
 static List<Bar> bars(int count,boolean up){var ds=dates(count);var b=new ArrayList<Bar>();for(int i=0;i<count;i++){var c=BigDecimal.valueOf(up?100+i:300-i);b.add(new Bar(ds.get(i),c.subtract(n("0.2")),c.add(n("0.4")),c.subtract(n("0.4")),c,n("100"),n("10000")));}return b;}
 static Result calc(List<Bar>b){return TechR1.analyze(b,dates(140),b.getLast().date(),true,true);}
 static Plan plan(){return new Plan(UUID.randomUUID().toString(),UUID.randomUUID().toString(),"002463.SZ",LocalDate.of(2026,11,6),LocalDate.of(2026,11,9),new Zone(true,null,"MA20",n("11"),n("1"),n("10"),n("12")),"NORMALIZED_QFQ_AT_D",LocalDate.of(2026,11,6),"hash","TECH-R1","WAITING_NEXT_BAR");}
 static Bar target(String o,String l,String c){return new Bar(LocalDate.of(2026,11,9),n(o),n(c).max(n(o)).add(n("1")),n(l),n(c),n("1"),n("1"));}
 static Evaluation eval(Bar b){return TechR1.evaluate(plan(),b,LocalDate.of(2026,11,10),true,true);}
 @Test void T01_59_hasMa55ButUnknown(){var r=calc(bars(59,true));assertThat(r.trend()).isEqualTo("UNKNOWN");assertThat(r.indicators().ma55()).isNotNull();assertThat(r.indicators().ma55FiveBarsAgo()).isNull();}
 @ParameterizedTest @ValueSource(ints={60,61,120}) void T02_T03_completeWindows(int n){var r=calc(bars(n,true));assertThat(r.trend()).isEqualTo("UP");assertThat(r.indicators().ma20()).isEqualByComparingTo(BigDecimal.valueOf(100+n-1-9.5));assertThat(r.indicators().ma55()).isEqualByComparingTo(BigDecimal.valueOf(100+n-1-27));assertThat(r.indicators().ma55FiveBarsAgo()).isEqualByComparingTo(BigDecimal.valueOf(100+n-1-32));}
 @Test void T03_noFutureOrOversizedInput(){var b=bars(120,true);assertThatThrownBy(()->TechR1.analyze(b,dates(140),b.get(118).date(),true,true)).isInstanceOf(IllegalArgumentException.class);assertThatThrownBy(()->calc(bars(121,true))).isInstanceOf(IllegalArgumentException.class);}
 @Test void T04_equalAndFlatMeansMixed(){var b=dates(60).stream().map(d->new Bar(d,n("100"),n("101"),n("99"),n("100"),n("1"),n("1"))).toList();assertThat(calc(b).trend()).isEqualTo("MIXED");}
 @Test void T05_atrSeedExactly14TrueRanges(){assertThat(TechR1.atr(bars(14,true))).isNull();assertThat(TechR1.atr(bars(15,true))).isEqualByComparingTo("1.4");assertThat(TechR1.atr(bars(16,true))).isEqualByComparingTo("1.4");}
 @Test void T06_touchingZonesBothRejected(){var b=dates(60).stream().map(d->new Bar(d,n("100"),n("101"),n("99"),n("100"),n("1"),n("1"))).toList();var r=calc(b);assertThat(r.support().reason()).isEqualTo("ZONE_OVERLAP");assertThat(r.resistance().valid()).isFalse();assertThat(r.candidates().stream().filter(c->c.id().equals("MA20")).findFirst().orElseThrow().disposition()).isEqualTo("EQUAL_CLOSE_EXCLUDED");}
 @Test void T07_planDoesNotUseDBarAsSignal(){var b=bars(60,true);var p=TechR1.createPlan("run","002463.SZ",calc(b),b.getLast().date(),dates(100),dates(100).get(60),LocalTime.NOON,"h");assertThat(p).isNotNull();assertThat(p.status()).isEqualTo("WAITING_NEXT_BAR");assertThat(p.targetTradeDate()).isEqualTo(dates(100).get(60));assertThat(TechR1.createPlan("run","x",calc(b),b.getLast().date(),dates(100),dates(100).get(61),LocalTime.NOON,"h")).isNull();}
 @Test void T07_cannotCreateRetrospectivePlanAfterTargetSessionClose(){var b=bars(60,true);assertThat(TechR1.createPlan("run","002463.SZ",calc(b),b.getLast().date(),dates(100),dates(100).get(60),LocalTime.of(15,0),"h")).isNull();}
 @ParameterizedTest @ValueSource(strings={"10","12"})void T08_lowBoundaryInclusive(String low){assertThat(eval(target("12",low,"13")).status()).isEqualTo("TECHNICAL_CONDITION_MET");}
 @Test void T09_closeAtUpperAndDojiNotTrigger(){assertThat(eval(target("11","10","12")).status()).isEqualTo("EXPIRED_NO_SIGNAL");assertThat(eval(target("13","11","13")).status()).isEqualTo("EXPIRED_NO_SIGNAL");}
 @Test void T10_lowerBreakInvalidatesStrictly(){assertThat(eval(target("11","9","9.9")).status()).isEqualTo("INVALIDATED");assertThat(eval(target("11","9","10")).status()).isEqualTo("EXPIRED_NO_SIGNAL");}
 @Test void T11_nextDayCannotReviveExpired(){var b=target("12","10","13");var next=new Bar(b.date().plusDays(1),b.open(),b.high(),b.low(),b.close(),b.volume(),b.amount());assertThat(eval(next).status()).isEqualTo("NEEDS_RECHECK");assertThat(eval(target("12","9","13")).status()).isEqualTo("EXPIRED_NO_SIGNAL");}
 @Test void T12_suspensionLateArrivalAndUnfinalized(){var p=plan();assertThat(TechR1.evaluate(p,null,LocalDate.of(2026,11,10),true,false).status()).isEqualTo("NEEDS_RECHECK");assertThat(TechR1.evaluate(p,target("12","10","13"),LocalDate.of(2026,11,8),true,true).status()).isEqualTo("WAITING_NEXT_BAR");assertThat(TechR1.evaluate(p,target("12","10","13"),p.targetTradeDate(),true,true).status()).isEqualTo("TECHNICAL_CONDITION_MET");}
 @Test void T13_adjustmentConflict(){assertThat(TechR1.evaluate(plan(),target("12","10","13"),LocalDate.of(2026,11,10),false,true).status()).isEqualTo("ADJUSTMENT_CHANGED_RECHECK");}
 @Test void T14_afterTriggerIsDistinctRecord(){var p=plan();var b=target("11","8","9");assertThat(TechR1.afterTrigger(p,b,true,true)).isNull();var later=new Bar(b.date().plusDays(1),b.open(),b.high(),b.low(),b.close(),b.volume(),b.amount());assertThat(TechR1.afterTrigger(p,later,true,true).status()).isEqualTo("INVALIDATED_AFTER_TRIGGER");assertThat(p.status()).isEqualTo("WAITING_NEXT_BAR");}
 @Test void T15_sellMustNotSkipOpenSession(){var b=new ArrayList<>(bars(120,false));assertThat(calc(b).sellReview().state()).isEqualTo("PRICE_RISK_REVIEW");b.remove(118);assertThat(calc(b).sellReview().state()).isEqualTo("UNKNOWN");}
 @Test void qualityAndFreshnessGate(){var b=bars(120,true);assertThat(TechR1.analyze(b,dates(140),b.getLast().date(),false,true).trend()).isEqualTo("UNKNOWN");assertThat(TechR1.analyze(b,dates(140),b.getLast().date(),true,false).trend()).isEqualTo("UNKNOWN");}
 @Test void noDisplayRoundingInStrictComparisons(){var b=target("12.00000001","10","12.00000002");assertThat(eval(b).status()).isEqualTo("TECHNICAL_CONDITION_MET");}
 @Test void independentReferenceVector()throws Exception{var b=new ArrayList<Bar>();var ds=dates(120);for(int i=0;i<120;i++){var c=n("100").add(BigDecimal.valueOf(i).multiply(n("0.17"))).add(BigDecimal.valueOf((i*17)%13).multiply(n("0.031")));b.add(new Bar(ds.get(i),c.subtract(n("0.13")),c.add(n("0.57")),c.subtract(n("0.61")),c,n("123"),n("12300")));}Files.createDirectories(Path.of("target"));Files.writeString(Path.of("target/technical-vector.json"),Json.write(Map.of("bars",b,"result",calc(b))));}
}
