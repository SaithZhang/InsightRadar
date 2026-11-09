package io.insightradar.v002.persistence;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.Json;
import io.insightradar.v002.api.AppException;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor;
import io.insightradar.v002.market.DataQualityValidator.Snapshot;
import io.insightradar.v002.market.MarketWindow;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.time.*;
import java.util.*;
@Repository
public class SnapshotRepository {
 public record StoredMarket(UUID id, JsonNode source, String inputHash) {}
 private final JdbcTemplate jdbc;
 private java.sql.Connection lease;
 public SnapshotRepository(JdbcTemplate jdbc){this.jdbc=jdbc;}
 public synchronized void acquireRuntimeLease(){try{lease=Objects.requireNonNull(jdbc.getDataSource()).getConnection();try(var statement=lease.createStatement();var result=statement.executeQuery("SELECT pg_try_advisory_lock(20261109002)")){result.next();if(!result.getBoolean(1)){lease.close();lease=null;throw new IllegalStateException("ANOTHER_LOCAL_INSTANCE_IS_RUNNING");}}}catch(java.sql.SQLException e){throw new IllegalStateException("RUNTIME_LOCK_UNAVAILABLE",e);}}
 public synchronized void releaseRuntimeLease(){if(lease!=null)try{try(var statement=lease.createStatement()){statement.execute("SELECT pg_advisory_unlock(20261109002)");}lease.close();lease=null;}catch(java.sql.SQLException e){throw new IllegalStateException("RUNTIME_LOCK_RELEASE_FAILED",e);}}
 public void recover(){jdbc.update("UPDATE analysis_runs SET status='FAILED',stage='RESTART',error_jsonb='{\"code\":\"INTERRUPTED_RESTART\",\"message\":\"运行中断，请重新分析\"}'::jsonb WHERE status IN ('QUEUED','RUNNING')");}
 public UUID create(String code){UUID id=UUID.randomUUID();jdbc.update("INSERT INTO analysis_runs(run_id,requested_code,status,stage,tech_rule_version) VALUES(?,?,'QUEUED','QUEUED','TECH-R1')",id,code);return id;}
 public void stage(UUID id,String stage){jdbc.update("UPDATE analysis_runs SET status='RUNNING',stage=? WHERE run_id=? AND status IN ('QUEUED','RUNNING')",stage,id);}
 public Optional<JsonNode> securityIdentity(String canonicalCode) {
  return jdbc.query("SELECT identity_jsonb::text FROM securities WHERE canonical_code = ?",
      (rs, n) -> Json.read(rs.getString(1)), canonicalCode).stream().findFirst();
 }
 public void security(JsonNode i){jdbc.update("INSERT INTO securities(canonical_code,code,name,exchange,type,list_status,provider,identity_jsonb) VALUES(?,?,?,?,?,?,?,?::jsonb) ON CONFLICT(canonical_code) DO UPDATE SET identity_jsonb=excluded.identity_jsonb,name=excluded.name,list_status=excluded.list_status,updated_at=now()",i.path("canonicalCode").asText(),i.path("sixDigitCode").asText(),i.path("name").asText(),i.path("exchange").asText(),"COMMON_A",i.path("listStatus").asText(),"baostock",Json.write(i));}
 public StoredMarket market(String requestedCode, JsonNode source, Snapshot normalized) {
  UUID id = UUID.randomUUID();
  String inputHash = Json.hash(Map.of("source", source, "normalized", normalized));
  jdbc.update("""
      INSERT INTO market_snapshots(id,requested_code,canonical_code,as_of_date,provider,fetched_at,
        raw_jsonb,qfq_source_jsonb,normalized_jsonb,calendar_jsonb,quality_jsonb,source_jsonb,input_sha256)
      VALUES(?,?,?,?,'baostock',?::timestamptz,?::jsonb,?::jsonb,?::jsonb,?::jsonb,?::jsonb,?::jsonb,?)
      """, id, requestedCode, source.path("identity").path("canonicalCode").asText(),
      normalized.asOfTradeDate(), source.path("fetchedAt").asText(), Json.write(source.path("raw")),
      Json.write(source.path("qfq")), Json.write(normalized.bars()), Json.write(source.path("calendar")),
      Json.write(normalized), Json.write(source), inputHash);
  return new StoredMarket(id, source, inputHash);
 }

 public Optional<StoredMarket> dailyMarket(String code, MarketWindow window) {
  var start = window.date().atStartOfDay(MarketWindow.ZONE).toOffsetDateTime();
  var cutoff = window.cutoff().atOffset(ZoneOffset.UTC);
  // A bare code can reuse an input previously resolved from that exact bare code.
  // A qualified code can match the canonical identity regardless of how it was requested.
  return jdbc.query("""
      SELECT id, source_jsonb::text, input_sha256 FROM market_snapshots
      WHERE provider = 'baostock' AND fetched_at >= ? AND fetched_at <= ?
        AND (requested_code = ? OR canonical_code = ?)
        AND quality_jsonb->>'reliable' = 'true'
        AND source_jsonb->>'finalityPolicy' = ?
        AND source_jsonb->>'requestedEnd' = ?
      ORDER BY as_of_date DESC NULLS LAST, fetched_at DESC, id DESC LIMIT 1
      """, (rs, row) -> new StoredMarket(rs.getObject(1, UUID.class), Json.read(rs.getString(2)), rs.getString(3)),
      start, cutoff, code, code, MarketWindow.POLICY, window.requestThrough().toString()).stream().findFirst();
 }
 public void finish(UUID id,Map<String,Object> report,UUID marketId){String json=Json.write(report);jdbc.update("UPDATE analysis_runs SET status=?,stage='FINISHED',canonical_code=?,market_snapshot_id=?,report_jsonb=?::jsonb,report_hash=?,prompt_version=? WHERE run_id=?",report.get("status"),report.get("canonicalCode"),marketId,json,Json.hashBytes(json.getBytes(java.nio.charset.StandardCharsets.UTF_8)),LlmEvidenceExtractor.PROMPT_VERSION,id);}
 public void fail(UUID id,Object error){jdbc.update("UPDATE analysis_runs SET status='FAILED',stage='FAILED',error_jsonb=?::jsonb WHERE run_id=? AND status IN ('QUEUED','RUNNING')",Json.write(error),id);}
 public Map<String,Object> get(UUID id){var list=jdbc.query("SELECT run_id,status,stage,created_at,report_jsonb::text,error_jsonb::text,report_hash FROM analysis_runs WHERE run_id=?",(rs,n)->{Map<String,Object> m=new LinkedHashMap<>();m.put("runId",rs.getString(1));m.put("status",rs.getString(2));m.put("stage",rs.getString(3));m.put("createdAt",rs.getTimestamp(4).toInstant());m.put("report",rs.getString(5)==null?null:Json.read(rs.getString(5)));m.put("error",rs.getString(6)==null?null:Json.read(rs.getString(6)));m.put("reportHash",rs.getString(7));return m;},id);if(list.isEmpty())throw new AppException("NOT_FOUND","报告不存在","STORAGE",false,404);return list.getFirst();}
 public List<Map<String,Object>> history(String code, Instant from, Instant until, int page, int size) {
  var sql = new StringBuilder("""
      SELECT run_id, status, created_at, requested_code, canonical_code,
             report_jsonb->>'asOfTradeDate' AS asof, report_jsonb->'trend'->>'state' AS trend,
             report_jsonb->>'eventStatus' AS event_status
      FROM analysis_runs WHERE true
      """);
  var args = new ArrayList<>();
  if (code != null) {
   if (code.length() == 6) {
    sql.append(" AND split_part(COALESCE(canonical_code, requested_code), '.', 1) = ?");
    args.add(code);
   } else {
    sql.append(" AND (canonical_code = ? OR (canonical_code IS NULL AND requested_code = ?))");
    args.add(code);
    args.add(code);
   }
  }
  if (from != null) {
   sql.append(" AND created_at >= ?");
   args.add(from.atOffset(ZoneOffset.UTC));
  }
  if (until != null) {
   sql.append(" AND created_at < ?");
   args.add(until.atOffset(ZoneOffset.UTC));
  }
  sql.append(" ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?");
  args.add(size);
  args.add(page * size);
  return jdbc.query(sql.toString(), (rs, n) -> {
   Map<String, Object> item = new LinkedHashMap<>();
   item.put("runId", rs.getString("run_id"));
   item.put("status", rs.getString("status"));
   item.put("createdAt", rs.getTimestamp("created_at").toInstant());
   item.put("requestedCode", rs.getString("requested_code"));
   item.put("canonicalCode", rs.getString("canonical_code"));
   item.put("asOfTradeDate", rs.getString("asof"));
   item.put("trend", rs.getString("trend"));
   item.put("eventStatus", rs.getString("event_status"));
   return item;
  }, args.toArray());
 }
 public JsonNode planReport(UUID plan){var list=jdbc.query("SELECT report_jsonb::text FROM analysis_runs WHERE report_jsonb->'buyPlan'->>'id'=?",(rs,n)->Json.read(rs.getString(1)),plan.toString());if(list.isEmpty())throw new AppException("PLAN_NOT_FOUND","观察计划不存在","PLAN",false,404);return list.getFirst();}
 public JsonNode source(UUID run){return jdbc.queryForObject("SELECT m.source_jsonb::text FROM market_snapshots m JOIN analysis_runs a ON a.market_snapshot_id=m.id WHERE a.run_id=?",(rs,n)->Json.read(rs.getString(1)),run);}
 public List<JsonNode> evaluations(UUID run){return jdbc.query("SELECT record_jsonb::text FROM plan_evaluations WHERE base_run_id=? ORDER BY evaluated_at,id",(rs,n)->Json.read(rs.getString(1)),run);}
 public JsonNode appendEvaluation(UUID plan,UUID run,LocalDate target,String status,String hash,Map<String,Object>record){UUID id=UUID.randomUUID();record.put("id",id);record.put("evaluatedAt",OffsetDateTime.now(ZoneOffset.UTC));jdbc.update("INSERT INTO plan_evaluations(id,plan_id,base_run_id,target_date,evaluated_at,status,input_sha256,record_jsonb) VALUES(?,?,?,?,?::timestamptz,?,?,?::jsonb) ON CONFLICT(plan_id,target_date,input_sha256) DO NOTHING",id,plan,run,target,record.get("evaluatedAt").toString(),status,hash,Json.write(record));return jdbc.queryForObject("SELECT record_jsonb::text FROM plan_evaluations WHERE plan_id=? AND target_date=? AND input_sha256=?",(rs,n)->Json.read(rs.getString(1)),plan,target,hash);}
 public void disclosure(Map<String,Object>meta,List<Map<String,Object>>pages,String path){jdbc.update("INSERT INTO disclosures(doc_id,canonical_code,title,published_at,official_url,pdf_path,pdf_sha256,pages_jsonb,fetch_status,metadata_jsonb) VALUES(?,?,?,?::timestamptz,?,?,?,?::jsonb,?,?::jsonb) ON CONFLICT(doc_id) DO NOTHING",meta.get("documentId"),meta.get("canonicalCode"),meta.get("title"),meta.get("publishedAt"),meta.get("officialUrl"),path,meta.get("pdfSha256"),Json.write(pages),meta.get("textExtractionStatus"),Json.write(meta));}
 public Map<String,Object> document(String id){var list=jdbc.query("SELECT metadata_jsonb::text,pages_jsonb::text FROM disclosures WHERE doc_id=?",(rs,n)->Map.<String,Object>of("metadata",Json.read(rs.getString(1)),"pages",Json.read(rs.getString(2))),id);if(list.isEmpty())throw new AppException("DOCUMENT_NOT_FOUND","文档不存在","DISCLOSURE",false,404);return list.getFirst();}
}
