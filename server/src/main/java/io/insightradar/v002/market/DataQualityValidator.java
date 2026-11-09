package io.insightradar.v002.market;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.technical.TechR1;
import io.insightradar.v002.technical.TechR1.Bar;
import java.math.*;
import java.time.*;
import java.util.*;
import static io.insightradar.v002.technical.TechR1.MC;

public final class DataQualityValidator {
 public record Snapshot(List<Bar> bars,List<LocalDate> sessions,LocalDate asOfTradeDate,LocalDate expectedDate,boolean reliable,boolean fresh,List<String> gaps,Map<String,Object> priceBasis,List<Map<String,Object>> derivedRatios){}
 private static BigDecimal num(JsonNode n,String key){return new BigDecimal(n.path(key).asText());}
 public static boolean validRow(JsonNode n){try {var o=num(n,"open");var c=num(n,"close");var h=num(n,"high");var l=num(n,"low");return o.signum()>0&&c.signum()>0&&l.signum()>0&&h.signum()>0&&l.compareTo(o.min(c))<=0&&h.compareTo(o.max(c))>=0&&num(n,"volume").signum()>=0&&num(n,"amount").signum()>=0;}catch(Exception e){return false;}}
 public static Map<LocalDate,JsonNode> index(JsonNode list){Map<LocalDate,JsonNode>map=new TreeMap<>();LocalDate previous=null;for(JsonNode row:list){var date=LocalDate.parse(row.path("date").asText());if(previous!=null&&!date.isAfter(previous))throw new IllegalArgumentException("NON_INCREASING_SOURCE_DATES");previous=date;if(map.put(date,row)!=null)throw new IllegalArgumentException("DUPLICATE_DATE");}return map;}
 public Snapshot validate(JsonNode src,MarketWindow window){
  LocalDate today=window.date();
  var gaps=new ArrayList<String>();var sessions=new ArrayList<LocalDate>();var bars=new ArrayList<Bar>();var ratios=new ArrayList<Map<String,Object>>();LocalDate asof=null,expected=null;boolean reliable=true,fresh=false;Map<String,Object>basis=new LinkedHashMap<>();basis.put("type","NORMALIZED_QFQ");basis.put("source","baostock");basis.put("factorSemantics","SPARSE_EVENTS_PLUS_DERIVED_OHLC_RATIOS");basis.put("finalityPolicy",MarketWindow.POLICY);
  try{
   LocalDate prev=null;for(var c:src.path("calendar")){var d=LocalDate.parse(c.path("calendar_date").asText());if(prev!=null&&!d.isAfter(prev))throw new IllegalArgumentException("CALENDAR_ORDER");prev=d;if(c.path("is_trading_day").asText().equals("1"))sessions.add(d);}
   if(sessions.isEmpty())throw new IllegalArgumentException("CALENDAR_UNAVAILABLE");
   if(src.path("calendar").isEmpty()||LocalDate.parse(src.path("calendar").get(src.path("calendar").size()-1).path("calendar_date").asText()).isBefore(today))throw new IllegalArgumentException("STALE_CALENDAR");
   expected=sessions.stream().filter(d->!d.isAfter(window.closedThrough())).max(LocalDate::compareTo).orElseThrow();
   if(!src.has("adjustmentEvents"))throw new IllegalArgumentException("ADJUSTMENT_METADATA_MISSING");
   var raw=index(src.path("raw"));var qfq=index(src.path("qfq"));if(raw.isEmpty())throw new IllegalArgumentException("NO_MARKET_BARS");if(!raw.keySet().equals(qfq.keySet()))throw new IllegalArgumentException("RAW_QFQ_DATE_CONFLICT");
   List<LocalDate>valid=new ArrayList<>();String providerCode=src.path("identity").path("providerCode").asText();
   for(var d:raw.keySet()){
    if(!allowsBar(src, d, window))throw new IllegalArgumentException("FUTURE_OR_UNFINALIZED_BAR");var r=raw.get(d);var q=qfq.get(d);
    if(!sessions.contains(d))throw new IllegalArgumentException("NON_SESSION_BAR");
    if(!r.path("code").asText().equals(providerCode)||!q.path("code").asText().equals(providerCode))throw new IllegalArgumentException("SECURITY_MISMATCH");
    if(!r.path("tradestatus").equals(q.path("tradestatus")))throw new IllegalArgumentException("SUSPENSION_CONFLICT");
    if(r.path("tradestatus").asText().equals("0"))continue;
    if(!r.path("tradestatus").asText().equals("1")||!validRow(r)||!validRow(q))throw new IllegalArgumentException("INVALID_OHLC_OR_VOLUME");
    if(num(r,"volume").compareTo(num(q,"volume"))!=0||num(r,"amount").compareTo(num(q,"amount"))!=0)throw new IllegalArgumentException("RAW_QFQ_VOLUME_AMOUNT_CONFLICT");
    if(!r.path("adjustflag").asText().equals("3")||!q.path("adjustflag").asText().equals("2"))throw new IllegalArgumentException("PRICE_BASIS_CONFLICT");
    var ratio=num(q,"close").divide(num(r,"close"),MC);BigDecimal maxError=BigDecimal.ZERO;
    for(String k:List.of("open","high","low","close")){var error=num(q,k).subtract(num(r,k).multiply(ratio,MC),MC).abs();maxError=maxError.max(error);if(error.compareTo(new BigDecimal("0.001"))>0)throw new IllegalArgumentException("OHLC_ADJUSTMENT_RATIO_CONFLICT");}
    ratios.add(Map.of("date",d,"qfqToRaw",ratio,"maxOhlcRoundingError",maxError));valid.add(d);
   }
   if(valid.isEmpty())throw new IllegalArgumentException("NO_VALID_TRADING_BARS");
   asof=valid.getLast();var scale=num(raw.get(asof),"close").divide(num(qfq.get(asof),"close"),MC);basis.put("anchor",asof);basis.put("providerQfqScale",scale);basis.put("anchorRawClose",num(raw.get(asof),"close"));
   var selected=valid.subList(Math.max(0,valid.size()-120),valid.size());
   for(var d:selected){var q=qfq.get(d);var r=raw.get(d);bars.add(new Bar(d,num(q,"open").multiply(scale,MC),num(q,"high").multiply(scale,MC),num(q,"low").multiply(scale,MC),d.equals(asof)?num(r,"close"):num(q,"close").multiply(scale,MC),num(r,"volume"),num(r,"amount")));}
   for(var d:sessions){if(!d.isBefore(selected.getFirst())&&!d.isAfter(expected)&&!d.equals(expected)&&!raw.containsKey(d))throw new IllegalArgumentException("MISSING_OPEN_SESSION:"+d);}
   fresh=asof.equals(expected)&&src.path("identity").path("listStatus").asText().equals("LISTED");
   if(!fresh) {
    String gap = window.awaitingRelease(expected) ? "TODAY_FINAL_BAR_AWAITING_PROVIDER" : "LATEST_SESSION_MISSING_SUSPENDED_OR_DELISTED";
    gaps.add(gap+":"+expected);
   }
   if(bars.size()<120)gaps.add("SHORT_HISTORY:"+bars.size()+"/120");
   if(!sessions.getLast().isAfter(asof))gaps.add("NEXT_SESSION_UNAVAILABLE");
  }catch(Exception e){reliable=false;gaps.add(e.getMessage()==null?"INVALID_PROVIDER_PAYLOAD":e.getMessage());bars.clear();}
  return new Snapshot(List.copyOf(bars),List.copyOf(sessions),asof,expected,reliable,fresh,List.copyOf(gaps),Collections.unmodifiableMap(basis),List.copyOf(ratios));
 }
 public static boolean allowsBar(JsonNode source, LocalDate date, MarketWindow window) {
  if (date.isAfter(window.requestThrough())) return false;
  if (!date.equals(window.date())) return true;
  if (!MarketWindow.POLICY.equals(source.path("finalityPolicy").asText()) ||
      !date.toString().equals(source.path("requestedEnd").asText())) return false;
  try {
   return !OffsetDateTime.parse(source.path("fetchedAt").asText()).isBefore(MarketWindow.releaseAt(date));
  } catch (DateTimeException e) {
   return false;
  }
 }
 public static Bar rawBar(JsonNode row){return new Bar(LocalDate.parse(row.path("date").asText()),num(row,"open"),num(row,"high"),num(row,"low"),num(row,"close"),num(row,"volume"),num(row,"amount"));}
 public static boolean comparable(JsonNode source,LocalDate anchor,LocalDate target,BigDecimal frozenRawClose){try{var r=index(source.path("raw"));var q=index(source.path("qfq"));if(num(r.get(anchor),"close").compareTo(frozenRawClose)!=0)return false;var a=num(q.get(anchor),"close").divide(num(r.get(anchor),"close"),MC);var t=num(q.get(target),"close").divide(num(r.get(target),"close"),MC);return a.subtract(t,MC).abs().compareTo(new BigDecimal("0.00001"))<=0;}catch(Exception e){return false;}}
}
