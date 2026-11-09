package io.insightradar.v002.api;
import io.insightradar.v002.Json;
import io.insightradar.v002.market.MarketWindow;
import io.insightradar.v002.market.TencentClosingQuote;
import java.time.Instant;
import io.insightradar.v002.analysis.AnalysisOrchestrator;
import io.insightradar.v002.intelligence.LlmEvidenceExtractor.Mode;
import io.insightradar.v002.persistence.PositionRepository;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import io.insightradar.v002.persistence.SnapshotRepository;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import java.util.*;
@RestController
@RequestMapping(value="/api/v1",produces=MediaType.APPLICATION_JSON_VALUE)
public class ApiController {
 private final AnalysisOrchestrator analysis;private final SnapshotRepository repo;private final SecurityLookup securities;private final TencentClosingQuote quotes;
 public ApiController(AnalysisOrchestrator analysis,SnapshotRepository repo,SecurityLookup securities,TencentClosingQuote quotes){this.analysis=analysis;this.repo=repo;this.securities=securities;this.quotes=quotes;}
 @GetMapping("/health")public String health(){return Json.write(Map.of("status","UP","trade_authority","none","version","0.2.0"));}
 @GetMapping("/securities/resolve")public String resolve(@RequestParam String code){return Json.write(securities.resolve(AnalysisOrchestrator.normalize(code)));}
 @GetMapping("/securities/close")
 public String close(@RequestParam String code) {
  var quote = quotes.find(AnalysisOrchestrator.normalize(code), new MarketWindow(Instant.now()));
  return Json.write(quote.orElse(null));
 }
 @PostMapping("/analyses")
 public ResponseEntity<String> create(@RequestBody Map<String, Object> input) {
  if (!(input.get("code") instanceof String code) || !Set.of("code", "mode").containsAll(input.keySet())) {
   throw new AppException("INVALID_REQUEST", "仅接受字符串 code 与可选 mode", "API", false, 422);
  }
  var mode = switch (input.getOrDefault("mode", "production")) {
   case String value when value.equals("production") -> Mode.PRODUCTION;
   case String value when value.equals("debug") -> Mode.DEBUG;
   case null, default -> throw new AppException("INVALID_MODE", "mode 必须为 production 或 debug", "API", false, 422);
  };
  UUID id = analysis.submit(code, mode);
  return ResponseEntity.status(202).body(Json.write(Map.of("runId", id, "status", "QUEUED")));
 }
 @GetMapping("/analyses/{id}")public String get(@PathVariable UUID id){return Json.write(repo.get(id));}
 @GetMapping("/analyses")
 public String history(@RequestParam(required = false) String code,
                       @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
                       @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
                       @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
  if (page < 0 || page > 10000 || size < 1 || size > 100)
   throw new AppException("INVALID_PAGINATION", "分页参数无效", "API", false, 422);
  if ((from != null && to != null && from.isAfter(to)) || LocalDate.MAX.equals(to))
   throw new AppException("INVALID_DATE_RANGE", "分析日期范围无效", "API", false, 422);
  String normalized = code == null || code.isBlank() ? null : AnalysisOrchestrator.normalize(code);
  var start = from == null ? null : from.atStartOfDay(PositionRepository.ZONE).toInstant();
  var end = to == null ? null : to.plusDays(1).atStartOfDay(PositionRepository.ZONE).toInstant();
  return Json.write(Map.of("items", repo.history(normalized, start, end, page, size), "page", page, "size", size));
 }
 @GetMapping("/analyses/{id}/plan-evaluations")public String evaluations(@PathVariable UUID id){repo.get(id);return Json.write(Map.of("items",repo.evaluations(id)));}
 @PostMapping("/plans/{id}/evaluations")public String evaluate(@PathVariable UUID id){return Json.write(analysis.evaluate(id));}
 @GetMapping("/disclosures/{id}")public String document(@PathVariable String id){if(!id.matches("[0-9]+-[a-f0-9]{16}"))throw new AppException("DOCUMENT_NOT_FOUND","文档不存在","DISCLOSURE",false,404);return Json.write(repo.document(id));}
}
