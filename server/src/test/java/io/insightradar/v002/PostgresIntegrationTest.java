package io.insightradar.v002;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.analysis.AnalysisOrchestrator;
import io.insightradar.v002.api.AppException;
import io.insightradar.v002.api.SecurityLookup;
import org.flywaydb.core.Flyway;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import io.insightradar.v002.disclosure.DisclosureProvider;
import io.insightradar.v002.market.MarketDataProvider;
import io.insightradar.v002.market.MarketWindow;
import io.insightradar.v002.persistence.PositionRepository;
import io.insightradar.v002.persistence.SnapshotRepository;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import static org.mockito.Mockito.*;
import io.insightradar.v002.market.DataQualityValidator;
import io.insightradar.v002.disclosure.DisclosureProvider.Bundle;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor.Mode;
import io.insightradar.v002.intelligence.LlmRequestRepository;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;



import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.core.env.Environment;

import java.net.*;
import java.net.http.*;
import java.time.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class PostgresIntegrationTest {
 static LocalPostgres db;
 static ConfigurableApplicationContext context;
 static SnapshotRepository repo; static JdbcTemplate jdbc; static Environment env;
 @BeforeAll static void start() throws Exception {db=new LocalPostgres();try{db.start();context=new SpringApplication(Application.class).run("--server.port=0","--spring.datasource.url="+db.jdbcUrl(),"--spring.datasource.username=test_user","--spring.datasource.password=");repo=context.getBean(SnapshotRepository.class);jdbc=context.getBean(JdbcTemplate.class);env=context.getEnvironment();}catch(Exception e){db.close();throw e;}}
 @AfterAll static void stop() throws Exception {try{if(context!=null)context.close();}finally{if(db!=null)db.close();}}
 @Test void T18_terminalReportCannotBeUpdatedOrDeleted(){var id=repo.create("002463");repo.stage(id,"MARKET");var report=new LinkedHashMap<String,Object>();report.put("status","PARTIAL");report.put("canonicalCode","002463.SZ");report.put("facts",List.of());repo.finish(id,report,null);var original=Json.write(repo.get(id));assertThatThrownBy(()->jdbc.update("UPDATE analysis_runs SET report_jsonb='{}'::jsonb WHERE run_id=?",id)).isInstanceOf(Exception.class);assertThatThrownBy(()->jdbc.update("DELETE FROM analysis_runs WHERE run_id=?",id)).isInstanceOf(Exception.class);repo.recover();assertThat(Json.write(repo.get(id))).isEqualTo(original);var next=repo.create("002463.SZ");assertThat(next).isNotEqualTo(id);assertThat(repo.history("002463.SZ",null,null,0,100)).anyMatch(x->x.get("runId").equals(id.toString()));}
 @Test void T14_appendOnlyEvaluationAndIdempotence(){var run=repo.create("600519.SH");var plan=UUID.randomUUID();var date=LocalDate.of(2026,11,9);var a=repo.appendEvaluation(plan,run,date,"NEEDS_RECHECK","h1",new LinkedHashMap<>(Map.of("status","NEEDS_RECHECK")));var b=repo.appendEvaluation(plan,run,date,"NEEDS_RECHECK","h1",new LinkedHashMap<>(Map.of("status","NEEDS_RECHECK")));assertThat(a).isEqualTo(b);repo.appendEvaluation(plan,run,date,"TECHNICAL_CONDITION_MET","h2",new LinkedHashMap<>(Map.of("status","TECHNICAL_CONDITION_MET")));repo.appendEvaluation(plan,run,date,"INVALIDATED_AFTER_TRIGGER","h3",new LinkedHashMap<>(Map.of("status","INVALIDATED_AFTER_TRIGGER")));assertThat(repo.evaluations(run)).hasSize(3);assertThatThrownBy(()->jdbc.update("UPDATE plan_evaluations SET status='X' WHERE plan_id=?",plan)).isInstanceOf(Exception.class);}
 @Test void sourceAndDocumentRowsAreImmutable(){var src=new DataQualityTest().input();((com.fasterxml.jackson.databind.node.ObjectNode)src.path("identity")).put("canonicalCode","002463.SZ");src.put("fetchedAt",Instant.now().toString());var normalized=new DataQualityValidator().validate(src,DataQualityTest.window(new DataQualityTest().today(),9,0));var id=repo.market("002463.SZ",src,normalized).id();assertThatThrownBy(()->jdbc.update("UPDATE market_snapshots SET input_sha256='changed' WHERE id=?",id)).isInstanceOf(Exception.class);assertThatThrownBy(()->jdbc.update("DELETE FROM market_snapshots WHERE id=?",id)).isInstanceOf(Exception.class);var meta=new LinkedHashMap<String,Object>();meta.put("documentId","123-0000000000000000");meta.put("canonicalCode","002463.SZ");meta.put("title","SYNTHETIC TEST");meta.put("publishedAt",Instant.now().toString());meta.put("officialUrl","https://www.cninfo.com.cn/");meta.put("pdfSha256","test");meta.put("textExtractionStatus","EXTRACTED");repo.disclosure(meta,List.of(),null);assertThatThrownBy(()->jdbc.update("UPDATE disclosures SET title='changed' WHERE doc_id=?",meta.get("documentId"))).isInstanceOf(Exception.class);assertThatThrownBy(()->jdbc.update("DELETE FROM disclosures WHERE doc_id=?",meta.get("documentId"))).isInstanceOf(Exception.class);}

 @Test void dailyMarketReusesOnlyQualifiedInputForTheShanghaiDay() {
  var fixture = new DataQualityTest();
  var date = fixture.today();
  var start = date.atStartOfDay(ZoneId.of("Asia/Shanghai"));
  var source = fixture.input();
  source.withObject("identity").put("canonicalCode", "002463.SZ");
  source.put("fetchedAt", start.toInstant().toString());
  source.put("requestedEnd", date.minusDays(1).toString());
  source.put("finalityPolicy", MarketWindow.POLICY);
  var validator = new DataQualityValidator();
  var saved = repo.market("002463", source, validator.validate(source, DataQualityTest.window(date,9,0)));

  var stale = source.deepCopy();
  stale.put("fetchedAt", start.plusHours(1).toInstant().toString());
  for (String series : List.of("raw", "qfq")) {
   ((com.fasterxml.jackson.databind.node.ObjectNode) stale.path(series).get(59)).put("tradestatus", "0");
  }
  repo.market("002463", stale, validator.validate(stale, DataQualityTest.window(date,9,0)));

  var invalid = source.deepCopy();
  invalid.put("fetchedAt", start.plusHours(2).toInstant().toString());
  invalid.putArray("qfq");
  repo.market("002463", invalid, validator.validate(invalid, DataQualityTest.window(date,9,0)));

  for (String code : List.of("002463", "002463.SZ")) {
   var hit = repo.dailyMarket(code, DataQualityTest.window(date,9,0)).orElseThrow();
   assertThat(hit.id()).isEqualTo(saved.id());
   assertThat(hit.inputHash()).isEqualTo(saved.inputHash());
   assertThat(hit.source()).isEqualTo(source);
  }
  assertThat(repo.dailyMarket("002463.SH", DataQualityTest.window(date,9,0))).isEmpty();
  assertThat(repo.dailyMarket("600519.SH", DataQualityTest.window(date,9,0))).isEmpty();
  assertThat(repo.dailyMarket("002463", DataQualityTest.window(date.minusDays(1),9,0))).isEmpty();
  assertThat(repo.dailyMarket("002463", DataQualityTest.window(date.plusDays(1),9,0))).isEmpty();
  assertThat(repo.dailyMarket("002463", DataQualityTest.window(date,17,59))).isPresent();
  assertThat(repo.dailyMarket("002463", DataQualityTest.window(date,18,0))).isEmpty();

  var after = source.deepCopy();
  for (String kind : List.of("raw","qfq")) {
   var bars = (com.fasterxml.jackson.databind.node.ArrayNode) after.path(kind);
   var last = (com.fasterxml.jackson.databind.node.ObjectNode) bars.get(59).deepCopy();
   bars.add(last.put("date",date.toString()));
  }
  after.put("requestedEnd",date.toString()).put("fetchedAt",MarketWindow.releaseAt(date).toString());
  var afterClose = DataQualityTest.window(date,18,0);
  var finalSnap = validator.validate(after, afterClose);
  assertThat(finalSnap.fresh()).isTrue();
  var finalId = repo.market("002463",after,finalSnap).id();
  assertThat(repo.dailyMarket("002463",afterClose).orElseThrow().id()).isEqualTo(finalId);
  assertThat(repo.dailyMarket("002463",DataQualityTest.window(date,16,0)).orElseThrow().id()).isEqualTo(saved.id());
 }
 @Test void duplicateRuntimeMustNotRecoverActiveWork(){var run=repo.create("300750.SZ");var second=new SnapshotRepository(jdbc);assertThatThrownBy(second::acquireRuntimeLease).isInstanceOf(IllegalStateException.class).hasMessageContaining("ANOTHER_LOCAL_INSTANCE");assertThat(repo.get(run).get("status")).isEqualTo("QUEUED");}

 @Test void productionReusesValidatedResultDebugRefreshesAndBudgetStopsNewCalls(@org.junit.jupiter.api.io.TempDir java.nio.file.Path data) throws Exception {
  var calls = new java.util.concurrent.atomic.AtomicInteger();
  var stub = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
  String quote = "公司披露本期收入同比增长";
  stub.createContext("/chat/completions", exchange -> {
   calls.incrementAndGet();
   exchange.getRequestBody().readAllBytes();
   var fact = Map.of("statement", quote, "classification", "DISCLOSED_FACT", "impact", "POSITIVE",
       "whyItMatters", "关注收入增长是否持续", "asOf", "2026-11-09",
       "evidence", List.of(Map.of("documentId", "test-doc", "page", 1, "quote", quote)));
   String content = Json.write(Map.of("facts", List.of(fact), "followUps", List.of()));
   byte[] body = Json.write(Map.of("choices", List.of(Map.of("finish_reason", "stop",
       "message", Map.of("content", content))))).getBytes(java.nio.charset.StandardCharsets.UTF_8);
   exchange.sendResponseHeaders(200, body.length);
   try (var output = exchange.getResponseBody()) { output.write(body); }
  });
  stub.start();
  try {
   String endpoint = "http://127.0.0.1:" + stub.getAddress().getPort();
   var store = new LlmRequestRepository(jdbc);
   var budget = new java.math.BigDecimal("0.60");
   var first = new LlmEvidenceExtractor(endpoint, "test-key", "gpt-6.1-sol", data.toString(), "", budget, store);
   var bundle = new Bundle(List.of(Map.of("documentId", "test-doc")),
       Map.of("test-doc", List.of(Map.of("page", 1, "text", quote, "normalizedText", quote))), Map.of(), List.of(), Map.of());
   var cutoff = Instant.parse("2026-11-09T13:00:00Z");
   var context = Map.<String, Object>of("trend", "UP");
   var cold = first.extract(bundle, cutoff, Mode.PRODUCTION, context);
   assertThat(cold).containsEntry("state", "COMPLETE").containsEntry("cacheHit", false);

   var next = new LlmEvidenceExtractor(endpoint, "test-key", "gpt-6.1-sol", data.toString(), "", budget, store);
   var hit = next.extract(bundle, cutoff.plusSeconds(60), Mode.PRODUCTION, context);
   assertThat(hit).containsEntry("cacheHit", true).containsEntry("apiDispatched", false)
       .containsEntry("requestId", cold.get("requestId"));
   assertThat(calls.get()).isEqualTo(1);

   var debug = next.extract(bundle, cutoff, Mode.DEBUG, context);
   assertThat(debug).containsEntry("cacheHit", false).containsEntry("apiDispatched", true);
   assertThat(debug.get("requestId")).isNotEqualTo(cold.get("requestId"));
   assertThat(next.extract(bundle, cutoff, Mode.PRODUCTION, context)).containsEntry("requestId", debug.get("requestId"));
   assertThat(next.extract(bundle, cutoff, Mode.PRODUCTION, Map.of("trend", "DOWN"))).containsEntry("cacheHit", false);
   assertThat(next.extract(bundle, cutoff, Mode.DEBUG, context)).containsEntry("reason", "LLM_MONTHLY_BUDGET_REACHED");
   assertThat(next.extract(bundle, cutoff, Mode.PRODUCTION, context)).containsEntry("cacheHit", true);
   assertThat(calls.get()).isEqualTo(3);
  } finally {
   stub.stop(0);
  }
 }
 @Test void restartFailsPendingOnly(){var run=repo.create("000001");repo.recover();assertThat(repo.get(run).get("status")).isEqualTo("FAILED");assertThat(Json.write(repo.get(run))).contains("INTERRUPTED_RESTART");}
 @Test void actualSpringHttpAndOriginBoundary()throws Exception{String base="http://127.0.0.1:"+env.getProperty("local.server.port")+"/api/v1";var client=HttpClient.newHttpClient();var health=client.send(HttpRequest.newBuilder(URI.create(base+"/health")).build(),HttpResponse.BodyHandlers.ofString());assertThat(health.statusCode()).isEqualTo(200);assertThat(health.body()).contains("none");var invalid=client.send(HttpRequest.newBuilder(URI.create(base+"/analyses")).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{\"code\":\"fake\"}")).build(),HttpResponse.BodyHandlers.ofString());assertThat(invalid.statusCode()).isEqualTo(422);var evil=client.send(HttpRequest.newBuilder(URI.create(base+"/analyses")).header("Origin","https://evil.test").header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{\"code\":\"002463\"}")).build(),HttpResponse.BodyHandlers.ofString());assertThat(evil.statusCode()).isEqualTo(403);}

 @Test void v3HistoryAndNewPositionsSurviveMigrationAndNativeRestart() throws Exception {
  try (var isolated = new LocalPostgres()) {
   isolated.start();
   var source = new DriverManagerDataSource(isolated.jdbcUrl(), "test_user", "");
   Flyway.configure().dataSource(source).target("3").load().migrate();
   var sql = new JdbcTemplate(source);
   var snapshots = new SnapshotRepository(sql);
   var id = snapshots.create("601793.SH");
   snapshots.finish(id, Map.of("status", "PARTIAL", "canonicalCode", "601793.SH"), null);
   var oldReport = snapshots.get(id);

   Flyway.configure().dataSource(source).load().migrate();
   assertThat(snapshots.get(id)).isEqualTo(oldReport);
   snapshots.security(Json.read("""
       {"canonicalCode":"601793.SH","sixDigitCode":"601793","exchange":"SH","listStatus":"LISTED","name":"SYNTHETIC"}
       """));
   var positions = new PositionRepository(sql);
   var written = positions.save("601793.SH", 200, new BigDecimal("1.234567"), "REVIEW_EXIT", 0).orElseThrow();
   isolated.restart();
   assertThat(positions.candidates("601793.SH")).containsExactly(written);
   assertThat(snapshots.get(id)).isEqualTo(oldReport);
  }
 }

 @Test void positionWritesRequireExactVersionsAndUseOnlyLocalQuotes() throws Exception {
  var fixture = new DataQualityTest();
  var source = fixture.input();
  var identity = source.withObject("identity");
  identity.put("canonicalCode", "601790.SH").put("sixDigitCode", "601790")
      .put("exchange", "SH").put("name", "SYNTHETIC POSITION TEST");
  repo.security(identity);
  var market = mock(MarketDataProvider.class);
  when(market.resolve("601790.SZ")).thenReturn(identity);
  assertThatThrownBy(() -> new SecurityLookup(market, repo).resolve("601790.SZ"))
      .isInstanceOf(AppException.class).hasMessageContaining("交易所");
  String base = "http://127.0.0.1:" + env.getProperty("local.server.port") + "/api/v1/positions";
  var client = HttpClient.newHttpClient();
  var created = client.send(put(base + "/601790.SH", 100, "140.123456", "REVIEW_EXIT", 0),
      HttpResponse.BodyHandlers.ofString());
  assertThat(created.statusCode()).as(created.body()).isEqualTo(200);
  assertThat(Json.read(created.body()).path("unitCost").asText()).isEqualTo("140.123456");
  assertThat(client.send(put(base + "/601790", 100, null, null, 0),
      HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(422);
  assertThat(client.send(put(base + "/601790.SH", -1, null, null, 1),
      HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(422);
  assertThat(client.send(put(base + "/601790.SH", 1, "0.0000001", null, 1),
      HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(422);
  assertThat(client.send(put(base + "/601790.SH", 1, null, "UNSUPPORTED", 1),
      HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(422);

  var positions = context.getBean(PositionRepository.class);
  var noQuote = positions.list("holding").stream().filter(item -> item.position().canonicalCode().equals("601790.SH")).findFirst().orElseThrow();
  assertThat(noQuote.marketValue()).isNull();

  source.put("fetchedAt", Instant.now().toString());
  repo.market("601790.SH", source, new DataQualityValidator().validate(source, DataQualityTest.window(fixture.today(),9,0)));
  var quote = positions.list("holding").stream().filter(item -> item.position().canonicalCode().equals("601790.SH")).findFirst().orElseThrow();
  assertThat(quote.referenceClose()).isEqualByComparingTo("159");
  assertThat(quote.marketValue()).isEqualByComparingTo("15900");
  assertThat(quote.unrealizedPnl()).isEqualByComparingTo("1887.654400");
  assertThat(quote.confirmedToday()).isTrue();

  var a = client.sendAsync(put(base + "/601790.SH", 120, null, "REVIEW_REDUCTION", 1), HttpResponse.BodyHandlers.ofString());
  var b = client.sendAsync(put(base + "/601790.SH", 130, null, "REVIEW_REDUCTION", 1), HttpResponse.BodyHandlers.ofString());
  assertThat(List.of(a.get().statusCode(), b.get().statusCode())).containsExactlyInAnyOrder(200, 409);
  var newRecord = positions.candidates("601790").getFirst();
  assertThat(newRecord.version()).isEqualTo(2);
  assertThat(newRecord.unitCost()).isNull();

  var cleared = client.send(put(base + "/601790.SH", 0, null, null, 2), HttpResponse.BodyHandlers.ofString());
  assertThat(cleared.statusCode()).isEqualTo(200);
  var listed = client.send(HttpRequest.newBuilder(URI.create(base + "?status=cleared")).build(), HttpResponse.BodyHandlers.ofString());
  assertThat(listed.statusCode()).isEqualTo(200);
  assertThat(Json.read(listed.body()).path("items").get(0).path("marketValue").asText()).isEqualTo("0");
  assertThat(positions.list("holding")).noneMatch(item -> item.position().canonicalCode().equals("601790.SH"));
 }

 @Test void analysisFreezesPositionBeforeQueueAndOnlyPublicInputsReachModel(@org.junit.jupiter.api.io.TempDir java.nio.file.Path data) throws Exception {
  String code = "601791.SH";
  var source = new DegradationTest().freshInput();
  source.withObject("identity").put("canonicalCode", code).put("sixDigitCode", "601791")
      .put("exchange", "SH").put("providerCode", "sh.601791");
  for (String series : List.of("raw", "qfq")) {
   for (var bar : source.path(series)) ((com.fasterxml.jackson.databind.node.ObjectNode) bar).put("code", "sh.601791");
  }
  LocalDate day = LocalDate.now(PositionRepository.ZONE);
  repo.security(source.path("identity"));
  var positions = context.getBean(PositionRepository.class);
  positions.save(code, 321987654, new BigDecimal("987654.123456"), "REVIEW_EXIT", 0).orElseThrow();

  var entered = new CountDownLatch(1);
  var proceed = new CountDownLatch(1);
  var market = mock(MarketDataProvider.class);
  when(market.snapshot(anyString(), isNull(), any())).thenAnswer(call -> {
   entered.countDown();
   if (!proceed.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("test timed out");
   return source;
  });
  var disclosure = mock(DisclosureProvider.class);
  String quote = "测试公司披露本期收入同比增长";
  String document = "position-test-doc";
  var bundle = new Bundle(List.of(Map.of("documentId", document)),
      Map.of(document, List.of(Map.of("page", 1, "text", quote, "normalizedText", quote))), Map.of("state", "COMPLETE"), List.of(), Map.of());
  when(disclosure.collect(anyString(), anyString(), any())).thenReturn(bundle);

  var bodies = new CopyOnWriteArrayList<String>();
  var stub = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
  stub.createContext("/chat/completions", exchange -> {
   bodies.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
   var fact = Map.of("statement", quote, "classification", "DISCLOSED_FACT", "impact", "POSITIVE",
       "whyItMatters", "关注收入增长是否持续", "asOf", day.toString(),
       "evidence", List.of(Map.of("documentId", document, "page", 1, "quote", quote)));
   String content = Json.write(Map.of("facts", List.of(fact), "followUps", List.of()));
   byte[] body = Json.write(Map.of("choices", List.of(Map.of("finish_reason", "stop",
       "message", Map.of("content", content))))).getBytes(StandardCharsets.UTF_8);
   exchange.sendResponseHeaders(200, body.length);
   try (var output = exchange.getResponseBody()) { output.write(body); }
  });
  stub.start();
  var extractor = new LlmEvidenceExtractor("http://127.0.0.1:" + stub.getAddress().getPort(),
      "test-key", "gpt-6.1-sol", data.toString(), "", new BigDecimal("100.00"), new LlmRequestRepository(jdbc));
  var service = new AnalysisOrchestrator(market, disclosure, extractor, new SnapshotRepository(jdbc), positions, mock(io.insightradar.v002.market.TencentClosingQuote.class));
  try {
   var firstId = service.submit(code, Mode.PRODUCTION);
   assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();
   positions.save(code, 0, null, null, 1).orElseThrow();
   proceed.countDown();

   var first = waitForReport(firstId);
   assertThat(first.path("report").path("positionSnapshot").path("position").path("quantity").asInt()).isEqualTo(321987654);
   assertThat(first.path("report").path("semantic").path("state").asText()).isEqualTo("COMPLETE");
   var next = waitForReport(service.submit(code, Mode.PRODUCTION));
   var snapshot = next.path("report").path("positionSnapshot");
   assertThat(snapshot.path("positionStatus").asText()).isEqualTo("CLEARED");
   assertThat(snapshot.path("action").asText()).isEqualTo("OBSERVE");
   assertThat(next.path("report").path("semantic").path("cacheHit").asBoolean()).isTrue();
   assertThat(next.path("report").path("provenance").path("marketCacheHit").asBoolean()).isTrue();
   assertThat(bodies).hasSize(1);
   assertThat(first).isEqualTo(Json.MAPPER.valueToTree(repo.get(firstId)));

   var debug = waitForReport(service.submit(code, Mode.DEBUG));
   assertThat(debug.path("report").path("semantic").path("cacheHit").asBoolean()).isFalse();
   assertThat(bodies).hasSize(2).allSatisfy(body -> assertThat(body)
       .doesNotContain("321987654", "987654.123456", "REVIEW_EXIT", "positionSnapshot", "onMa55Trigger", "confirmedAt"));
   assertThat(bodies.get(1)).isEqualTo(bodies.getFirst());
  } finally {
   proceed.countDown();
   service.stop();
   stub.stop(0);
  }
 }

 @Test void analysisHistoryFiltersByShanghaiDateAndQualifiedIdentity() throws Exception {
  UUID endPrevious = insertHistoryAt("601792.SH", "2026-11-08T15:59:59Z");
  UUID start = insertHistoryAt("601792.SH", "2026-11-08T16:00:00Z");
  UUID end = insertHistoryAt("601792.SH", "2026-11-09T16:00:00Z");
  UUID wrongExchange = insertHistoryAt("601792.SZ", "2026-11-08T16:00:00Z");
  String base = "http://127.0.0.1:" + env.getProperty("local.server.port") + "/api/v1/analyses";
  String query = base + "?code=601792.SH&from=2026-11-09&to=2026-11-09";
  var response = HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(query)).build(),
      HttpResponse.BodyHandlers.ofString());
  assertThat(response.statusCode()).isEqualTo(200);
  assertThat(response.body()).contains(start.toString()).doesNotContain(endPrevious.toString(), end.toString(), wrongExchange.toString());
 }

 private UUID insertHistoryAt(String code, String time) {
  UUID id = repo.create(code);
  jdbc.update("UPDATE analysis_runs SET created_at = ? WHERE run_id = ?", OffsetDateTime.parse(time), id);
  repo.finish(id, Map.of("status", "PARTIAL", "canonicalCode", code), null);
  return id;
 }

 private static HttpRequest put(String url, int quantity, String cost, String action, long version) {
  var payload = new LinkedHashMap<String, Object>();
  payload.put("quantity", quantity);
  payload.put("unitCost", cost);
  payload.put("onMa55Trigger", action);
  payload.put("expectedVersion", version);
  return HttpRequest.newBuilder(URI.create(url)).header("Content-Type", "application/json")
      .PUT(HttpRequest.BodyPublishers.ofString(Json.write(payload))).build();
 }

 private static JsonNode waitForReport(UUID id) throws InterruptedException {
  for (int attempt = 0; attempt < 100; attempt++) {
   var run = repo.get(id);
   assertThat(run.get("status")).as("run %s %s", id, run.get("error")).isNotEqualTo("FAILED");
   if (run.get("report") != null) return Json.MAPPER.valueToTree(run);
   Thread.sleep(50);
  }
  throw new AssertionError("Report did not complete: " + id);
 }
}
