package io.insightradar.v002.analysis;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.Json;
import io.insightradar.v002.api.AppException;
import io.insightradar.v002.market.*;
import io.insightradar.v002.technical.TechR1;
import io.insightradar.v002.disclosure.DisclosureProvider;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor.Mode;
import io.insightradar.v002.persistence.SnapshotRepository;
import io.insightradar.v002.persistence.PositionRepository;
import jakarta.annotation.*;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
@Service
public class AnalysisOrchestrator {
 private final MarketDataProvider market;private final DisclosureProvider disclosure;private final LlmEvidenceExtractor llm;private final SnapshotRepository repo;
 private final PositionRepository positions;
 private final TencentClosingQuote quotes;
 private final ThreadPoolExecutor pool=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(8),new ThreadPoolExecutor.AbortPolicy());
 public AnalysisOrchestrator(MarketDataProvider market,DisclosureProvider disclosure,LlmEvidenceExtractor llm,SnapshotRepository repo,PositionRepository positions,TencentClosingQuote quotes){this.market=market;this.disclosure=disclosure;this.llm=llm;this.repo=repo;this.positions=positions;this.quotes=quotes;}
 @PostConstruct public void recover(){repo.acquireRuntimeLease();repo.recover();}
 @PreDestroy public void stop(){pool.shutdownNow();repo.releaseRuntimeLease();}
 public UUID submit(String code, Mode mode){code=normalize(code);UUID id=repo.create(code);String input=code;Instant cutoff=Instant.now();
  var position = PositionDecision.Capture.read(positions, input, cutoff);
  try{pool.execute(()->run(id,input,cutoff,mode,position));}catch(RejectedExecutionException e){repo.fail(id,Map.of("code","QUEUE_FULL","message","本地队列已满，请稍后重试"));throw new AppException("QUEUE_FULL","本地分析队列已满","QUEUE",true,429);}return id;}
 public static String normalize(String code){if(code==null||!code.trim().toUpperCase(Locale.ROOT).matches("[0-9]{6}(\\.(SH|SZ|BJ))?"))throw new AppException("INVALID_SECURITY","请输入六位普通 A 股代码，可带交易所后缀","IDENTITY",false,422);return code.trim().toUpperCase(Locale.ROOT);}
 private Map<String,Object> error(AppException e){return Map.of("code",e.code,"message",e.getMessage(),"stage",e.stage,"retryable",e.retryable,"details",Map.of());}
 private record MarketLoad(SnapshotRepository.StoredMarket stored, DataQualityValidator.Snapshot snapshot, boolean cacheHit) {}

 // Keep lookup, fetch and persistence together so concurrent misses share one verified input.
 private synchronized MarketLoad loadMarket(String code, MarketWindow window) {
  var validator = new DataQualityValidator();
  var cached = repo.dailyMarket(code, window);
  if (cached.isPresent()) {
   var stored = cached.get();
   var snapshot = validator.validate(stored.source(), window);
   var eligible = snapshot.sessions().stream().filter(d -> !d.isAfter(window.requestThrough())).reduce((a, b) -> b);
   boolean usableWhileWaiting = window.awaitingRelease(snapshot.expectedDate()) &&
       eligible.filter(d -> d.equals(snapshot.asOfTradeDate())).isPresent();
   if (snapshot.reliable() && (snapshot.fresh() || usableWhileWaiting)) return new MarketLoad(stored, snapshot, true);
  }
  var source = market.snapshot(code, null, window.requestThrough());
  repo.security(source.path("identity"));
  var snapshot = validator.validate(source, window);
  return new MarketLoad(repo.market(code, source, snapshot), snapshot, false);
 }

 private void run(UUID id,String code,Instant cutoff,Mode mode,PositionDecision.Capture position){
  try{
   var window = new MarketWindow(cutoff);var report=new LinkedHashMap<String,Object>();var gaps=new ArrayList<String>();var errors=new ArrayList<Map<String,Object>>();JsonNode source=null,identity=null;UUID marketId=null;
   DataQualityValidator.Snapshot snap=null;TechR1.Result tech=TechR1.analyze(List.of(),List.of(),null,false,false);TechR1.Plan plan=null;
   String inputHash = null;
   boolean marketCacheHit = false;
   report.put("runId",id);report.put("requestedCode",code);report.put("createdAt",Instant.now());report.put("knowledgeCutoff",cutoff);report.put("trade_authority","none");report.put("techRuleVersion",TechR1.VERSION);
   repo.stage(id,"MARKET");
   try{
    var loaded = loadMarket(code, window);
    source = loaded.stored().source();
    identity = source.path("identity");
    snap = loaded.snapshot();
    marketId = loaded.stored().id();
    inputHash = loaded.stored().inputHash();
    marketCacheHit = loaded.cacheHit();
    gaps.addAll(snap.gaps());
    tech = TechR1.analyze(snap.bars(), snap.sessions(), snap.asOfTradeDate(), snap.reliable(), snap.fresh());
    plan = TechR1.createPlan(id.toString(), identity.path("canonicalCode").asText(), tech,
        snap.asOfTradeDate(), snap.sessions(), window.date(), window.time(), source.path("sourceHash").asText());
   }catch(AppException e){if(e.code.equals("INVALID_SECURITY")){repo.fail(id,error(e));return;}gaps.add(e.code);gaps.add("SECURITY_IDENTITY_UNCONFIRMED");errors.add(error(e));}
   String canonical=identity==null?null:identity.path("canonicalCode").asText();report.put("identity",identity);report.put("canonicalCode",canonical);report.put("asOfTradeDate",snap==null?null:snap.asOfTradeDate());report.put("source","baostock");report.put("priceBasis",snap==null?null:snap.priceBasis());report.put("technicalStatus",tech.trend().equals("UNKNOWN")?"UNKNOWN":"READY");report.put("candles",snap==null?List.of():snap.bars());report.put("indicators",tech.indicators());report.put("indicatorSeries",tech.series());report.put("trend",Map.of("state",tech.trend(),"reasons",tech.reasons()));report.put("candidates",tech.candidates());report.put("support",tech.support());report.put("resistance",tech.resistance());report.put("sellReview",tech.sellReview());report.put("buyPlan",plan);report.put("buyPlanNotCreatedReason",plan==null?(tech.trend().equals("UP")?"NO_VALID_ZONE_OR_NEXT_SESSION_OR_LATE_BASE":"TREND_NOT_UP"):null);
   var quality=new LinkedHashMap<String,Object>();quality.put("provider","baostock");quality.put("barsValid",snap==null?0:snap.bars().size());quality.put("targetBars",120);quality.put("reliable",snap!=null&&snap.reliable());quality.put("fresh",snap!=null&&snap.fresh());quality.put("lastFinalizedDate",snap==null?null:snap.asOfTradeDate());quality.put("expectedSession",snap==null?null:snap.expectedDate());quality.put("gaps",List.copyOf(gaps));report.put("dataQuality",quality);
   String phase = window.phase(snap == null || snap.expectedDate() == null ? List.of() : snap.sessions());
   var timing = new LinkedHashMap<String, Object>();
   timing.put("phase", phase);
   timing.put("requestedThrough", window.requestThrough());
   timing.put("awaitingPublication", snap != null && window.awaitingRelease(snap.expectedDate()));
   timing.put("providerReleaseAt", snap != null && snap.sessions().contains(window.date()) ? MarketWindow.releaseAt(window.date()) : null);
   report.put("marketTiming", timing);
   if (snap == null || (phase.equals("POST_CLOSE") && !snap.fresh())) {
    quotes.find(canonical == null ? code : canonical, window).ifPresent(quote -> report.put("closingQuote", quote));
   }
   report.put("positionSnapshot", PositionDecision.evaluate(position, canonical, snap, tech.sellReview()));
   repo.stage(id,"DISCLOSURE");var bundle=disclosure.collect(code,canonical,cutoff);gaps.addAll(bundle.gaps());report.put("officialIssuer",bundle.issuer());report.put("documents",bundle.documents());
   repo.stage(id,"SEMANTIC");
   var context = new LinkedHashMap<String, Object>();
   context.put("security", canonical == null ? code : canonical);
   context.put("ruleVersion", TechR1.VERSION);
   context.put("asOfTradeDate", report.get("asOfTradeDate"));
   context.put("trend", tech.trend());
   context.put("priceReviewState", tech.sellReview().state());
   context.put("indicators", tech.indicators());
   context.put("support", tech.support());
   context.put("resistance", tech.resistance());
   var semantic=llm.extract(bundle,cutoff,mode,context);report.put("semantic",semantic);report.put("facts",semantic.get("facts"));report.put("followUps",semantic.get("followUps"));
   var coverage=new LinkedHashMap<>(bundle.coverage());String eventState=bundle.coverage().get("state").equals("UNAVAILABLE")?"UNAVAILABLE":bundle.coverage().get("state").equals("COMPLETE")&&semantic.get("state").equals("COMPLETE")?"COMPLETE":"PARTIAL";coverage.put("directoryAndPdfState",bundle.coverage().get("state"));coverage.put("semanticState",semantic.get("state"));coverage.put("state",eventState);report.put("coverage",coverage);report.put("eventStatus",eventState);gaps.add("SEMANTIC:"+semantic.get("reason"));
   JsonNode facts=Json.read(Json.write(semantic.get("facts")));boolean negative=false;for(var f:facts)if(Set.of("NEGATIVE","MIXED").contains(f.path("impact").asText()))negative=true;report.put("eventReview",Map.of("state",negative?"EVENT_RISK_REVIEW":"UNKNOWN","reason","不由摘要缺失或未发现负面推断无风险"));
   report.put("dataGaps",gaps);report.put("errors",errors);report.put("status",tech.trend().equals("UNKNOWN")||!eventState.equals("COMPLETE")?"PARTIAL":"COMPLETED");var provenance=new LinkedHashMap<String,Object>();provenance.put("techRuleVersion",TechR1.VERSION);provenance.put("schemaVersion","report-v1");provenance.put("promptVersion",LlmEvidenceExtractor.PROMPT_VERSION);provenance.put("codeVersion","0.2.0");provenance.put("providerVersion",source==null?null:source.path("providerVersion"));provenance.put("sourceHash",source==null?null:source.path("sourceHash"));provenance.put("providerFetchAt",source==null?null:source.path("fetchedAt"));provenance.put("inputHash",inputHash);provenance.put("marketCacheHit",marketCacheHit);report.put("provenance",provenance);repo.finish(id,report,marketId);
  }catch(Exception e){repo.fail(id,Map.of("code","ANALYSIS_FAILED","message",e.getClass().getSimpleName(),"stage","ANALYSIS","retryable",true));}
 }
 public synchronized JsonNode evaluate(UUID planId){
  var report=repo.planReport(planId);final TechR1.Plan plan;try{plan=Json.MAPPER.treeToValue(report.path("buyPlan"),TechR1.Plan.class);}catch(Exception e){throw new AppException("PLAN_CORRUPT","计划无法解析","PLAN",false,500);}
  var window = new MarketWindow(Instant.now());
  var eligibleThrough = window.requestThrough();
  JsonNode source=null;TechR1.Evaluation result;var record=new LinkedHashMap<String,Object>();
  if(plan.targetTradeDate().isAfter(eligibleThrough))result=TechR1.evaluate(plan,null,eligibleThrough,false,false);
  else try{
   source=market.snapshot(plan.canonicalCode(),plan.baseTradeDate().minusDays(5),eligibleThrough);var raw=DataQualityValidator.index(source.path("raw"));JsonNode row=raw.get(plan.targetTradeDate());var qfq=DataQualityValidator.index(source.path("qfq"));
   var knownSessions=new ArrayList<LocalDate>();for(var session:source.path("calendar"))if(session.path("is_trading_day").asText().equals("1"))knownSessions.add(LocalDate.parse(session.path("calendar_date").asText()));
   var nextSession=knownSessions.stream().filter(d->d.isAfter(plan.baseTradeDate())).findFirst().orElse(null);
   var targetQfq=qfq.get(plan.targetTradeDate());
   boolean valid=plan.canonicalCode().equals(source.path("identity").path("canonicalCode").asText())&&plan.targetTradeDate().equals(nextSession)&&row!=null&&targetQfq!=null&&DataQualityValidator.allowsBar(source,plan.targetTradeDate(),window)&&row.path("tradestatus").asText().equals("1")&&targetQfq.path("tradestatus").asText().equals("1")&&DataQualityValidator.validRow(row)&&DataQualityValidator.validRow(targetQfq);
   var frozenRaw=new BigDecimal(report.path("priceBasis").path("anchorRawClose").asText());boolean comparable=DataQualityValidator.comparable(source,plan.anchor(),plan.targetTradeDate(),frozenRaw);
   var target=valid?DataQualityValidator.rawBar(row):null;
   result=TechR1.evaluate(plan,target,eligibleThrough,comparable,valid);
   boolean triggered=repo.evaluations(UUID.fromString(plan.baseRunId())).stream().anyMatch(x->x.path("status").asText().equals("TECHNICAL_CONDITION_MET"));
   // A trigger is persisted on its own evaluation before subsequent invalidation can be appended.
   if(triggered){for(var entry:raw.entrySet())if(entry.getKey().isAfter(plan.targetTradeDate())&&DataQualityValidator.allowsBar(source,entry.getKey(),window)){var r=entry.getValue();boolean ok=r.path("tradestatus").asText().equals("1")&&DataQualityValidator.validRow(r);boolean same=DataQualityValidator.comparable(source,plan.anchor(),entry.getKey(),frozenRaw);var later=TechR1.afterTrigger(plan,ok?DataQualityValidator.rawBar(r):null,same,ok);if(later!=null){result=later;break;}}}
  }catch(AppException e){result=new TechR1.Evaluation("NEEDS_RECHECK",plan.targetTradeDate(),null,e.code,Map.of());record.put("error",error(e));}
  catch(Exception e){result=new TechR1.Evaluation("NEEDS_RECHECK",plan.targetTradeDate(),null,"INVALID_TARGET_INPUT",Map.of());}
  record.put("status",result.status());record.put("planId",plan.id());record.put("baseRunId",plan.baseRunId());record.put("targetTradeDate",plan.targetTradeDate());record.put("observedTradeDate",result.observedTradeDate());record.put("reason",result.reason());record.put("conditions",result.conditions());record.put("ruleVersion",plan.ruleVersion());record.put("trade_authority","none");
  // Exclude fetch timestamps from idempotence key; freeze full observed inputs in each new evidence record.
  Object stable=Map.of("reason",result.reason());
  if(source!=null){var relevantDates=new HashSet<String>(List.of(plan.baseTradeDate().toString(),plan.targetTradeDate().toString()));if(result.observedTradeDate()!=null)relevantDates.add(result.observedTradeDate().toString());var relevant=new LinkedHashMap<String,Object>();for(String kind:List.of("raw","qfq")){var rows=new ArrayList<JsonNode>();for(var row:source.path(kind))if(relevantDates.contains(row.path("date").asText()))rows.add(row);relevant.put(kind,rows);}relevant.put("identity",source.path("identity"));stable=relevant;}String hash=Json.hash(Map.of("evaluation",result,"inputs",stable));record.put("inputHash",hash);record.put("marketEvidence",source);
  return repo.appendEvaluation(planId,UUID.fromString(plan.baseRunId()),plan.targetTradeDate(),result.status(),hash,record);
 }
}
