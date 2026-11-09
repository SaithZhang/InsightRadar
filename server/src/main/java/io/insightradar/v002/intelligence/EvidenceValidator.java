package io.insightradar.v002.intelligence;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.disclosure.PdfPageExtractor;
import java.time.LocalDate;
import java.util.*;
import java.util.regex.*;
/** Strict evidence-v1 shape plus exact page/quote and conservative numerical-claim gate. */
public class EvidenceValidator {
 public record Validated(List<JsonNode> facts,List<JsonNode>followUps,List<Map<String,Object>> rejectedItems){}
 private static void fields(JsonNode n,String...names){if(!n.isObject())throw new IllegalArgumentException("OBJECT_REQUIRED");var required=Set.of(names);var actual=new HashSet<String>();n.fieldNames().forEachRemaining(actual::add);if(!actual.equals(required))throw new IllegalArgumentException("SCHEMA_FIELDS");}
 private static void text(JsonNode n,String field,int min,int max){var v=n.path(field);if(!v.isTextual()||v.asText().length()<min||v.asText().length()>max)throw new IllegalArgumentException("SCHEMA_TEXT:"+field);}
 private static void enumeration(JsonNode n,String field,String...values){if(!n.path(field).isTextual()||!Set.of(values).contains(n.path(field).asText()))throw new IllegalArgumentException("SCHEMA_ENUM:"+field);}
 public Validated validate(JsonNode output,Map<String,List<Map<String,Object>>>pages,LocalDate cutoff){
  fields(output,"facts","followUps");if(!output.path("facts").isArray()||output.path("facts").size()>5||!output.path("followUps").isArray()||output.path("followUps").size()>3)throw new IllegalArgumentException("SCHEMA_ARRAY_LIMIT");
  var accepted=new ArrayList<JsonNode>();var rejected=new ArrayList<Map<String,Object>>();int index=0;
  for(var fact:output.path("facts")){try{
   fields(fact,"statement","classification","impact","whyItMatters","asOf","evidence");text(fact,"statement",1,1000);text(fact,"whyItMatters",1,1000);enumeration(fact,"classification","DISCLOSED_FACT","COMPANY_EXPLANATION","MODEL_INFERENCE");enumeration(fact,"impact","POSITIVE","NEGATIVE","MIXED","UNCERTAIN");text(fact,"asOf",10,10);if(LocalDate.parse(fact.path("asOf").asText()).isAfter(cutoff))throw new IllegalArgumentException("FUTURE_FACT_DATE");
   var evidence=fact.path("evidence");if(!evidence.isArray()||evidence.isEmpty()||evidence.size()>5)throw new IllegalArgumentException("EVIDENCE_REQUIRED");StringBuilder quoted=new StringBuilder();
   for(var e:evidence){fields(e,"documentId","page","quote");text(e,"documentId",1,200);text(e,"quote",8,1000);if(!e.path("page").isIntegralNumber()||!e.path("page").canConvertToInt())throw new IllegalArgumentException("INVALID_PAGE");var doc=pages.get(e.path("documentId").asText());int page=e.path("page").asInt();if(doc==null||page<1||page>doc.size())throw new IllegalArgumentException("DOCUMENT_OR_PAGE_NOT_FOUND");String original=doc.get(page-1).get("normalizedText").toString(),quote=PdfPageExtractor.normalize(e.path("quote").asText());if(!original.contains(quote))throw new IllegalArgumentException("QUOTE_NOT_ON_PAGE");quoted.append(quote);}
   // Unverified arithmetic/percentages are rejected, never promoted to disclosed facts.
   Matcher numbers=Pattern.compile("[0-9]+(?:[.,][0-9]+)*%?").matcher(fact.path("statement").asText()+fact.path("whyItMatters").asText());while(numbers.find())if(!quoted.toString().contains(numbers.group()))throw new IllegalArgumentException("NUMERIC_CLAIM_NOT_IN_QUOTE");
   if((fact.path("statement").asText()+fact.path("whyItMatters").asText()).matches(".*(目标价|预期收益率|建议买入|建议卖出|立即买入|立即卖出|MA20|MA55|ATR14).*"))throw new IllegalArgumentException("OUT_OF_SCOPE_TECHNICAL_OR_TRADE_CLAIM");
   accepted.add(fact);
  }catch(Exception e){rejected.add(Map.of("index",index,"reason",e.getMessage()==null?"INVALID_EVIDENCE":e.getMessage()));}index++;}
  var followUps=new ArrayList<JsonNode>();for(var f:output.path("followUps")){fields(f,"question","evidenceSource","criterion","expectedVerificationTime","manualConfirmationRequired");for(String k:List.of("question","evidenceSource","criterion"))text(f,k,1,1000);text(f,"expectedVerificationTime",1,100);if(!f.path("manualConfirmationRequired").isBoolean()||!f.path("manualConfirmationRequired").asBoolean())throw new IllegalArgumentException("MANUAL_CONFIRMATION_REQUIRED");followUps.add(f);}
  return new Validated(List.copyOf(accepted),List.copyOf(followUps),List.copyOf(rejected));
 }
}
