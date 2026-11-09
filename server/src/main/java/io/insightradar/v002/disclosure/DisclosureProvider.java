package io.insightradar.v002.disclosure;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.Json;
import io.insightradar.v002.persistence.SnapshotRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.regex.*;
@Component
public class DisclosureProvider {
 public record Bundle(List<Map<String,Object>>documents,Map<String,List<Map<String,Object>>>pages,Map<String,Object>coverage,List<String>gaps,Map<String,Object>issuer){}
 private record Listing(List<JsonNode>rows,boolean complete,int total){}
 private final OfficialHttp http;private final SnapshotRepository repo;private final Path root;private final int maxPdfs;
 public DisclosureProvider(OfficialHttp http,SnapshotRepository repo,@Value("${app.data}")String root,@Value("${app.disclosure.max-pdfs}")int maxPdfs){this.http=http;this.repo=repo;this.root=Path.of(root).toAbsolutePath().normalize();this.maxPdfs=Math.min(30,Math.max(1,maxPdfs));}
 private JsonNode parse(byte[] b){return Json.read(new String(b,java.nio.charset.StandardCharsets.UTF_8));}
 private Listing list(String code,String org,String from,String through,String category,int maxPages)throws Exception{
  var unique=new LinkedHashMap<String,JsonNode>();int expected=-1;boolean complete=false;
  for(int p=1;p<=maxPages;p++){
   var form=new LinkedHashMap<String,String>();form.put("stock",code+","+org);form.put("tabName","fulltext");form.put("pageSize","30");form.put("pageNum",Integer.toString(p));form.put("column","");form.put("category",category);form.put("plate","");form.put("seDate",from+"~"+through);form.put("searchkey","");form.put("isHLtitle","false");form.put("sortName","time");form.put("sortType","desc");
   var j=parse(http.post("https://www.cninfo.com.cn/new/hisAnnouncement/query",form,5_000_000));
   if(!j.has("totalAnnouncement")||!j.path("announcements").isArray()&&j.path("totalAnnouncement").asInt()!=0)throw new IllegalArgumentException("DIRECTORY_SHAPE");
   int total=j.path("totalAnnouncement").asInt();if(expected>=0&&expected!=total)throw new IllegalArgumentException("DIRECTORY_CHANGED_DURING_PAGING");expected=total;
   int before=unique.size();for(var row:j.path("announcements")){
    if(!row.path("secCode").asText(code).equals(code))throw new IllegalArgumentException("DISCLOSURE_ISSUER_MISMATCH");
    String id=row.path("announcementId").asText();if(!id.matches("[0-9]+"))throw new IllegalArgumentException("INVALID_DOCUMENT_ID");unique.put(id,row);
   }
   if(unique.size()==expected&&!j.path("hasMore").asBoolean()){complete=true;break;}
   if(unique.size()==before||unique.size()>expected)break;
   Thread.sleep(250);
  }
  return new Listing(List.copyOf(unique.values()),complete,expected);
 }
 private static boolean periodic(String title){return title.matches(".*(年度报告|半年度报告|季度报告|季报).*" )&&!title.matches(".*(摘要|英文|取消|提示性|审议|说明会|关于|公告).*" );}
 static String period(String title){Matcher m=Pattern.compile("(20[0-9]{2})年?.*?(第一季度|一季度|第三季度|三季度|半年度|年度|年报)").matcher(title);if(!m.find())return "UNKNOWN";String kind=m.group(2);return m.group(1)+"-"+(kind.contains("一")?"Q1":kind.contains("三")?"Q3":kind.contains("半")?"Q2":"Q4");}
 public Bundle collect(String requestedCode,String canonicalCode,Instant cutoff){
  var docs=new ArrayList<Map<String,Object>>();var pages=new LinkedHashMap<String,List<Map<String,Object>>>();var gaps=new ArrayList<String>();var coverage=new LinkedHashMap<String,Object>();var issuer=new LinkedHashMap<String,Object>();
  LocalDate through=cutoff.atZone(ZoneId.of("Asia/Shanghai")).toLocalDate(),from=through.minusDays(89);coverage.put("from",from);coverage.put("through",through);coverage.put("knowledgeCutoff",cutoff);coverage.put("scope","90_CALENDAR_DAYS_PLUS_LATEST_DISCLOSED_PERIODIC_REPORT");coverage.put("source","CNINFO");coverage.put("paginationComplete",false);coverage.put("latestPeriodicSearchComplete",false);int extracted=0,failed=0;
  try{
   String code=requestedCode.split("\\.")[0];var master=parse(http.get("https://www.cninfo.com.cn/new/data/szse_stock.json",5_000_000));var matches=new ArrayList<JsonNode>();for(var s:master.path("stockList"))if(s.path("code").asText().equals(code)&&s.path("category").asText().equals("A股"))matches.add(s);
   if(matches.size()!=1)throw new IllegalArgumentException("OFFICIAL_ISSUER_NOT_UNIQUE");var identity=matches.getFirst();String org=identity.path("orgId").asText();issuer.put("code",code);issuer.put("name",identity.path("zwjc").asText());issuer.put("orgId",org);issuer.put("source","CNINFO_OFFICIAL_MASTER");
   var recent=list(code,org,from.toString(),through.toString(),"",20);coverage.put("paginationComplete",recent.complete);coverage.put("directoryTotal",recent.total);if(!recent.complete)gaps.add("DIRECTORY_PAGINATION_INCOMPLETE");
   // Search all disclosed report history, sorted newest first. Bound and declare scope on truncation.
   var periodic=list(code,org,"1990-01-01",through.toString(),"category_ndbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;category_yjdbg_szsh",20);
   coverage.put("latestPeriodicSearchComplete",periodic.complete);if(!periodic.complete)gaps.add("PERIODIC_SEARCH_INCOMPLETE");
   JsonNode latest=periodic.rows.stream().filter(r->periodic(r.path("announcementTitle").asText())).filter(r->r.path("announcementTime").asLong()<=cutoff.toEpochMilli()).filter(r->!period(r.path("announcementTitle").asText()).equals("UNKNOWN")).max(Comparator.<JsonNode,String>comparing(r->period(r.path("announcementTitle").asText())).thenComparingLong(r->r.path("announcementTime").asLong())).orElse(null);
   if(latest==null)gaps.add("LATEST_PERIODIC_REPORT_NOT_CONFIRMED");
   var all=new LinkedHashMap<String,JsonNode>();if(latest!=null){all.put(latest.path("announcementId").asText(),latest);coverage.put("reportPeriod",period(latest.path("announcementTitle").asText()));}
   for(var r:recent.rows)if(r.path("announcementTime").asLong()<=cutoff.toEpochMilli())all.put(r.path("announcementId").asText(),r);
   coverage.put("documentsFound",all.size());int processed=0;
   for(var r:all.values()){
    String ref=r.path("announcementId").asText(),title=r.path("announcementTitle").asText().replaceAll("<[^>]+>",""),pdf="https://static.cninfo.com.cn/"+r.path("adjunctUrl").asText();
    var meta=new LinkedHashMap<String,Object>();meta.put("sourceDocumentId",ref);meta.put("canonicalCode",canonicalCode);meta.put("issuerCode",code);meta.put("title",title);meta.put("publishedAt",Instant.ofEpochMilli(r.path("announcementTime").asLong()).toString());meta.put("publicationTimePrecision","SOURCE_DATE_OR_TIMESTAMP");meta.put("officialUrl","https://www.cninfo.com.cn/new/disclosure/detail?annoId="+ref);meta.put("pdfUrl",pdf);meta.put("source","CNINFO");meta.put("fetchedAt",Instant.now());meta.put("reportPeriod",period(title));meta.put("correctionOrSupplement",title.matches(".*(更正|修订|补充).*"));meta.put("latestPeriodicReport",latest!=null&&ref.equals(latest.path("announcementId").asText()));
    String status="NOT_PROCESSED_LIMIT",path=null,hash=null;List<Map<String,Object>>docPages=List.of();
    if(processed++<maxPdfs){try{byte[]bytes=http.get(pdf,25_000_000);hash=Json.hashBytes(bytes);Path dir=root.resolve("disclosures").resolve(ref);Files.createDirectories(dir);Path target=dir.resolve(hash+".pdf");Files.write(target,bytes);path=target.toString();docPages=new PdfPageExtractor().extract(bytes);boolean nonempty=docPages.stream().anyMatch(p->!p.get("normalizedText").toString().isBlank());status=nonempty?"EXTRACTED":"EXTRACTION_UNAVAILABLE";if(nonempty){extracted++;if(docPages.stream().anyMatch(p->p.get("normalizedText").toString().isBlank()))gaps.add("PDF_EMPTY_OR_IMAGE_PAGE:"+ref);}else failed++;}catch(Exception e){status="EXTRACTION_UNAVAILABLE";failed++;meta.put("error",e.getClass().getSimpleName());}}
    String version=hash==null?Json.hash(Map.of("meta",meta,"status",status)).substring(0,16):hash.substring(0,16);String id=ref+"-"+version;meta.put("documentId",id);meta.put("pdfSha256",hash);meta.put("textExtractionStatus",status);meta.put("pageCount",docPages.size());repo.disclosure(meta,docPages,path);docs.add(meta);if(status.equals("EXTRACTED"))pages.put(id,docPages);
   }
   if(all.size()>maxPdfs)gaps.add("PDF_PROCESSING_LIMIT:"+maxPdfs);if(failed>0)gaps.add("PDF_EXTRACTION_FAILURES:"+failed);
  }catch(Exception e){gaps.add("OFFICIAL_SOURCE_UNAVAILABLE:"+e.getClass().getSimpleName());}
  coverage.put("processedDocuments",extracted);coverage.put("pdfExtractionFailures",failed);coverage.put("state",docs.isEmpty()?"UNAVAILABLE":gaps.isEmpty()?"COMPLETE":"PARTIAL");coverage.put("warning","覆盖完整仅指声明范围；不能推断没有重大风险");return new Bundle(List.copyOf(docs),pages,coverage,gaps,issuer);
 }
}
