package io.insightradar.v002.technical;

import java.math.*;
import java.time.*;
import java.util.*;
import java.util.stream.*;

/** TECH-R1: pure decimal functions, no Spring/IO. Display rounding never enters comparisons. */
public final class TechR1 {
 public static final String VERSION="TECH-R1";
 public static final MathContext MC=MathContext.DECIMAL128;
 public record Bar(LocalDate date,BigDecimal open,BigDecimal high,BigDecimal low,BigDecimal close,BigDecimal volume,BigDecimal amount){}
 public record Point(LocalDate date,BigDecimal ma20,BigDecimal ma55){}
 public record Candidate(String id,BigDecimal center,int window,String disposition){}
 public record Zone(boolean valid,String reason,String source,BigDecimal center,BigDecimal halfWidth,BigDecimal lower,BigDecimal upper){}
 public record Indicators(BigDecimal ma20,BigDecimal ma55,BigDecimal ma20FiveBarsAgo,BigDecimal ma55FiveBarsAgo,BigDecimal atr14){}
 public record Sell(String state,String reason,LocalDate previousDate,LocalDate date,BigDecimal previousClose,BigDecimal previousMa55,BigDecimal close,BigDecimal ma55){}
 public record Result(String trend,List<String> reasons,Indicators indicators,List<Point> series,List<Candidate> candidates,Zone support,Zone resistance,Sell sellReview){}
 public record Plan(String id,String baseRunId,String canonicalCode,LocalDate baseTradeDate,LocalDate targetTradeDate,Zone zone,String normalizedPriceBasis,LocalDate anchor,String sourceHash,String ruleVersion,String status){}
 public record Evaluation(String status,LocalDate targetTradeDate,LocalDate observedTradeDate,String reason,Map<String,Boolean> conditions){}
 public static BigDecimal ma(List<Bar>b,int n,int end){if(end<n-1)return null;BigDecimal s=BigDecimal.ZERO;for(int i=end-n+1;i<=end;i++)s=s.add(b.get(i).close,MC);return s.divide(BigDecimal.valueOf(n),MC);}
 public static BigDecimal atr(List<Bar>b){if(b.size()<15)return null;BigDecimal seed=BigDecimal.ZERO,a=null;for(int i=1;i<b.size();i++){var v=b.get(i);var p=b.get(i-1).close;var tr=v.high.subtract(v.low,MC).max(v.high.subtract(p,MC).abs()).max(v.low.subtract(p,MC).abs());if(i<=14)seed=seed.add(tr,MC);if(i==14)a=seed.divide(BigDecimal.valueOf(14),MC);else if(i>14)a=a.multiply(BigDecimal.valueOf(13),MC).add(tr,MC).divide(BigDecimal.valueOf(14),MC);}return a;}
 public static boolean gt(BigDecimal a,BigDecimal b){return a.compareTo(b)>0;}
 public static boolean lt(BigDecimal a,BigDecimal b){return a.compareTo(b)<0;}
 public static Zone absent(String reason){return new Zone(false,reason,null,null,null,null,null);}
 private static BigDecimal extreme(List<Bar>b,int n,boolean high){if(b.size()<n)return null;return b.subList(b.size()-n,b.size()).stream().map(v->high?v.high:v.low).reduce(high?BigDecimal::max:BigDecimal::min).orElseThrow();}
 private static Zone zone(Candidate c,BigDecimal half){return c==null?absent("NO_VALID_CANDIDATE"):new Zone(true,null,c.id,c.center,half,c.center.subtract(half,MC),c.center.add(half,MC));}
 public static Result analyze(List<Bar>b,List<LocalDate>sessions,LocalDate asOf,boolean reliable,boolean fresh){
  if(b.size()>120 || b.stream().anyMatch(v->asOf==null||v.date.isAfter(asOf)))throw new IllegalArgumentException("INPUT_WINDOW_OR_FUTURE_BAR");
  for(int i=1;i<b.size();i++)if(!b.get(i).date.isAfter(b.get(i-1).date))throw new IllegalArgumentException("BAR_ORDER");
  int t=b.size()-1; var m20=ma(b,20,t);var m55=ma(b,55,t);var m20p=ma(b,20,t-5);var m55p=ma(b,55,t-5);var atr=atr(b);
  var ind=new Indicators(m20,m55,m20p,m55p,atr);
  List<Point>series=IntStream.range(0,b.size()).mapToObj(i->new Point(b.get(i).date,ma(b,20,i),ma(b,55,i))).toList();
  var reasons=new ArrayList<String>();String trend="UNKNOWN";
  if(!reliable)reasons.add("DATA_QUALITY_FAILED");if(!fresh)reasons.add("LATEST_FINAL_SESSION_UNAVAILABLE");if(b.size()<60)reasons.add("INSUFFICIENT_BARS_60_REQUIRED");
  if(reasons.isEmpty()){var c=b.get(t).close;trend=gt(c,m20)&&gt(m20,m55)&&gt(m20,m20p)&&gt(m55,m55p)?"UP":lt(c,m20)&&lt(m20,m55)&&lt(m20,m20p)&&lt(m55,m55p)?"DOWN":"MIXED";reasons.add("STRICT_CLOSE_MA20_MA55_AND_FIVE_BAR_SLOPES");}
  var candidates=new ArrayList<Candidate>();Zone support=absent("DATA_QUALITY_FAILED"),resistance=support;
  if(reliable&&!b.isEmpty()&&atr!=null&&atr.signum()>0){
   BigDecimal close=b.get(t).close;String[]ids={"MA20","MA55","LOW20","HIGH20","LOW60","HIGH60"};int[]windows={20,55,20,20,60,60};BigDecimal[]values={m20,m55,extreme(b,20,false),extreme(b,20,true),extreme(b,60,false),extreme(b,60,true)};
   for(int i=0;i<6;i++)candidates.add(new Candidate(ids[i],values[i],windows[i],values[i]==null?"INSUFFICIENT_WINDOW":values[i].compareTo(close)==0?"EQUAL_CLOSE_EXCLUDED":"ELIGIBLE"));
   Candidate lo=candidates.stream().filter(c->c.center!=null&&lt(c.center,close)).max(Comparator.comparing(Candidate::center)).orElse(null),hi=candidates.stream().filter(c->c.center!=null&&gt(c.center,close)).min(Comparator.comparing(Candidate::center)).orElse(null);
   var half=atr.multiply(new BigDecimal("0.5"),MC);support=zone(lo,half);resistance=zone(hi,half);
   if(support.valid&&resistance.valid&&support.upper.compareTo(resistance.lower)>=0){support=absent("ZONE_OVERLAP");resistance=absent("ZONE_OVERLAP");}
   var selected=List.of(lo==null?"":lo.id,hi==null?"":hi.id);candidates.replaceAll(c->new Candidate(c.id,c.center,c.window,c.disposition.equals("ELIGIBLE")?(selected.contains(c.id)?"SELECTED":"FARTHER_FROM_CLOSE"):c.disposition));
  }else if(reliable){support=absent("ATR_UNAVAILABLE_OR_NONPOSITIVE");resistance=support;}
  Sell sell=new Sell("UNKNOWN","TWO_ADJACENT_VALID_SESSIONS_REQUIRED",null,asOf,null,null,t<0?null:b.get(t).close,m55);
  if(reliable&&fresh&&b.size()>=56){var prev=b.get(t-1);var last=b.get(t);int ix=sessions.indexOf(last.date);if(ix>0&&sessions.get(ix-1).equals(prev.date)){var pm=ma(b,55,t-1);sell=new Sell(lt(prev.close,pm)&&lt(last.close,m55)?"PRICE_RISK_REVIEW":"NOT_TRIGGERED","TWO_SESSIONS_CLOSE_STRICTLY_BELOW_OWN_MA55",prev.date,last.date,prev.close,pm,last.close,m55);}}
  return new Result(trend,List.copyOf(reasons),ind,series,List.copyOf(candidates),support,resistance,sell);
 }
 public static Plan createPlan(String run,String code,Result result,LocalDate base,List<LocalDate>sessions,LocalDate today,LocalTime creationTime,String hash){
  if(!result.trend.equals("UP")||!result.support.valid||base==null)return null;
  var target=sessions.stream().filter(d->d.isAfter(base)).findFirst().orElse(null);
  // An expired target may be evaluated, but cannot be created retrospectively.
  if(target==null||target.isBefore(today)||(target.equals(today)&&!creationTime.isBefore(LocalTime.of(15,0))))return null;
  return new Plan(UUID.randomUUID().toString(),run,code,base,target,result.support,"NORMALIZED_QFQ_AT_D",base,hash,VERSION,"WAITING_NEXT_BAR");
 }
 public static Evaluation evaluate(Plan plan,Bar target,LocalDate eligibleThrough,boolean comparable,boolean valid){
  if(!plan.ruleVersion.equals(VERSION))return ev(plan,"NEEDS_RECHECK",null,"RULE_VERSION_UNAVAILABLE",Map.of());
  if(plan.targetTradeDate.isAfter(eligibleThrough))return ev(plan,"WAITING_NEXT_BAR",null,"TARGET_FINALITY_NOT_CONFIRMED",Map.of());
  if(target==null||!target.date.equals(plan.targetTradeDate)||!valid)return ev(plan,"NEEDS_RECHECK",null,"FIXED_TARGET_MISSING_SUSPENDED_OR_INVALID",Map.of());
  if(!comparable)return ev(plan,"ADJUSTMENT_CHANGED_RECHECK",target.date,"PRICE_BASIS_NOT_COMPARABLE",Map.of());
  var z=plan.zone;var c=Map.of("lowInZone",target.low.compareTo(z.lower)>=0&&target.low.compareTo(z.upper)<=0,"closeAboveUpper",gt(target.close,z.upper),"bullishClose",gt(target.close,target.open));
  String status=lt(target.close,z.lower)?"INVALIDATED":c.values().stream().allMatch(Boolean::booleanValue)?"TECHNICAL_CONDITION_MET":"EXPIRED_NO_SIGNAL";
  return ev(plan,status,target.date,"FIXED_D_PLUS_ONE_ONLY",c);
 }
 public static Evaluation afterTrigger(Plan plan,Bar bar,boolean comparable,boolean valid){if(bar==null||!bar.date.isAfter(plan.targetTradeDate)||!comparable||!valid||!lt(bar.close,plan.zone.lower))return null;return ev(plan,"INVALIDATED_AFTER_TRIGGER",bar.date,"LATER_FINAL_CLOSE_BELOW_FROZEN_LOWER",Map.of());}
 private static Evaluation ev(Plan p,String status,LocalDate observed,String reason,Map<String,Boolean>conditions){return new Evaluation(status,p.targetTradeDate,observed,reason,conditions);}
 private TechR1(){}
}
