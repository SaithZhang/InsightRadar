package io.insightradar.v002.api;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import io.insightradar.v002.Json;
import io.insightradar.v002.analysis.AnalysisOrchestrator;
import io.insightradar.v002.persistence.PositionRepository;
import java.math.BigDecimal;
import java.util.Map;
import java.util.Set;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(value = "/api/v1/positions", produces = "application/json")
public class PositionController {
 private static final com.fasterxml.jackson.databind.ObjectReader INPUT_READER = Json.MAPPER.reader()
     .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
     .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
 private static final Set<String> FIELDS = Set.of("quantity", "unitCost", "onMa55Trigger", "expectedVersion");
 private static final Set<String> ACTIONS = Set.of("REVIEW_REDUCTION", "REVIEW_EXIT");
 private final PositionRepository positions;
 private final SecurityLookup securities;

 public PositionController(PositionRepository positions, SecurityLookup securities) {
  this.positions = positions;
  this.securities = securities;
 }

 @GetMapping
 public String list(@RequestParam(defaultValue = "holding") String status) {
  if (!Set.of("holding", "cleared", "all").contains(status)) throw invalid("持仓筛选状态无效");
  return Json.write(Map.of("items", positions.list(status)));
 }

 @PutMapping("/{canonicalCode}")
 public String save(@PathVariable String canonicalCode, @RequestBody String body) {
  String code = AnalysisOrchestrator.normalize(canonicalCode);
  if (code.length() != 9) throw invalid("请使用已确认的证券代码和交易所后缀");
  final JsonNode input;
  try {
   input = INPUT_READER.readTree(body);
  } catch (IOException e) {
   throw invalid("持仓请求格式无效");
  }
  if (input == null || !input.isObject() || input.properties().stream().anyMatch(field -> !FIELDS.contains(field.getKey()))) throw invalid("持仓字段无效");
  JsonNode quantityField = input.path("quantity");
  JsonNode versionField = input.path("expectedVersion");
  if (!quantityField.isIntegralNumber() || !quantityField.canConvertToInt() ||
      quantityField.asInt() < 0 || quantityField.asInt() > 999999999) throw invalid("股数须为 0 至 999,999,999 的整数");
  if (!versionField.isIntegralNumber() || !versionField.canConvertToLong() || versionField.asLong() < 0)
   throw invalid("持仓版本无效");

  int quantity = quantityField.asInt();
  BigDecimal cost = parseCost(input.path("unitCost"));
  JsonNode actionField = input.path("onMa55Trigger");
  String action = actionField.asText(null);
  if (!actionField.isNull() && !actionField.isMissingNode() &&
      (!actionField.isTextual() || !ACTIONS.contains(action))) throw invalid("MA55 触发动作无效");
  if (quantity == 0 && (cost != null || action != null)) throw invalid("标记清仓时请清空成本与预设动作");

  long version = versionField.asLong();
  if (version == 0) securities.resolve(code);
  var saved = positions.save(code, quantity, cost, action, version).orElseThrow(() ->
      new AppException("POSITION_VERSION_CONFLICT", "持仓已更新，请核对最新记录后重新保存", "POSITION", false, 409));
  return Json.write(saved);
 }

 private static BigDecimal parseCost(JsonNode value) {
  if (value.isMissingNode() || value.isNull()) return null;
  if (value.isNumber()) {
   var number = value.decimalValue();
   if (number.scale() > 6 || (long) number.precision() - number.scale() > 12)
    throw invalid("每股成本最多 12 位整数及 6 位小数");
   return number;
  }
  if (!value.isTextual() || !value.asText().matches("-?[0-9]{1,12}(\\.[0-9]{1,6})?"))
   throw invalid("每股成本最多 12 位整数及 6 位小数");
  return new BigDecimal(value.asText());
 }

 private static AppException invalid(String message) {
  return new AppException("INVALID_POSITION", message, "POSITION", false, 422);
 }
}
