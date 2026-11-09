package io.insightradar.v002;
import io.insightradar.v002.intelligence.EvidenceValidator;
import io.insightradar.v002.disclosure.*;
import org.junit.jupiter.api.*;
import org.apache.pdfbox.pdmodel.*;
import org.apache.pdfbox.pdmodel.font.*;
import java.io.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class EvidenceTest {
 String json(String doc,int page,String quote){return Json.write(Map.of("facts",List.of(Map.of("statement","已披露报告内容","classification","DISCLOSED_FACT","impact","UNCERTAIN","whyItMatters","需结合其他证据核验","asOf","2026-11-06","evidence",List.of(Map.of("documentId",doc,"page",page,"quote",quote)))),"followUps",List.of()));}
 Map<String,List<Map<String,Object>>> pages(){return Map.of("doc",List.of(Map.of("page",1,"normalizedText","公司报告显示营业收入较上期下降，需关注风险。")));}
 @Test void T16_exactQuoteAndPageGate(){var v=new EvidenceValidator();assertThat(v.validate(Json.read(json("doc",1,"营业收入较上期下降")),pages(),LocalDate.of(2026,11,9)).facts()).hasSize(1);for(String text:List.of(json("doc",2,"营业收入较上期下降"),json("fake",1,"营业收入较上期下降"),json("doc",1,"这是模型捏造的八个字"))){var r=v.validate(Json.read(text),pages(),LocalDate.of(2026,11,9));assertThat(r.facts()).isEmpty();assertThat(r.rejectedItems()).hasSize(1);}}
 @Test void strictSchemaRejectsExtras(){assertThatThrownBy(()->new EvidenceValidator().validate(Json.read("{\"facts\":[],\"followUps\":[],\"buy\":true}"),pages(),LocalDate.now())).isInstanceOf(IllegalArgumentException.class);}
 @Test void unverifiedNumericalDerivationRejected(){var n=Json.read(json("doc",1,"营业收入较上期下降"));((com.fasterxml.jackson.databind.node.ObjectNode)n.path("facts").get(0)).put("statement","同比下降88%");assertThat(new EvidenceValidator().validate(n,pages(),LocalDate.now()).facts()).isEmpty();}
 @Test void officialUrlsFailClosed(){for(String u:List.of("http://static.cninfo.com.cn/a.pdf","https://evil.test/a.pdf","https://static.cninfo.com.cn.evil.test/a.pdf","https://me@static.cninfo.com.cn/a.pdf","file:///etc/passwd"))assertThatThrownBy(()->OfficialHttp.allowed(u)).isInstanceOf(IllegalArgumentException.class);}
 @Test void pdfPageNumbersArePhysicalAndStable()throws Exception{byte[]b;try(var pdf=new PDDocument();var out=new ByteArrayOutputStream()){for(String text:List.of("First official test page","Second official test page")){var page=new PDPage();pdf.addPage(page);try(var c=new PDPageContentStream(pdf,page)){c.beginText();c.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA),12);c.newLineAtOffset(40,700);c.showText(text);c.endText();}}pdf.save(out);b=out.toByteArray();}var pages=new PdfPageExtractor().extract(b);assertThat(pages).hasSize(2);assertThat(pages.get(1).get("page")).isEqualTo(2);assertThat(pages.get(1).get("text").toString()).contains("Second official test page");}
 @Test void realOfficialPdfWhenSupplied()throws Exception{String path=System.getenv("OFFICIAL_PDF_TEST");Assumptions.assumeTrue(path!=null,"Set OFFICIAL_PDF_TEST for explicit real-PDF acceptance");byte[]b=Files.readAllBytes(Path.of(path));var extracted=new PdfPageExtractor().extract(b);assertThat(extracted).isNotEmpty();String first=extracted.getFirst().get("normalizedText").toString();assertThat(first.length()).isGreaterThan(40);var p=Map.of("doc",extracted);var validated=new EvidenceValidator().validate(Json.read(json("doc",1,first.substring(0,30))),p,LocalDate.of(2026,11,9));assertThat(validated.facts()).hasSize(1);Files.writeString(Path.of("target/official-pdf-check.json"),Json.write(Map.of("sha256",Json.hashBytes(b),"pages",extracted.size(),"verifiedQuotePage",1,"quoteCharacters",30,"status","PASS")));}
}
