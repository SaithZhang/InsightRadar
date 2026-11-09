package io.insightradar.v002.disclosure;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.text.PDFTextStripper;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.*;
public class PdfPageExtractor {
 public static String normalize(String text){return Normalizer.normalize(text,Normalizer.Form.NFKC).replaceAll("[\\s\\p{Z}]+","");}
 public List<Map<String,Object>> extract(byte[] bytes)throws Exception{
  if(bytes.length<5||!new String(bytes,0,5,StandardCharsets.US_ASCII).equals("%PDF-"))throw new IllegalArgumentException("NOT_PDF");
  try(var pdf=Loader.loadPDF(bytes)){
   if(pdf.isEncrypted()&&!pdf.getCurrentAccessPermission().canExtractContent())throw new IllegalArgumentException("EXTRACTION_NOT_PERMITTED");
   if(pdf.getNumberOfPages()>800)throw new IllegalArgumentException("PDF_PAGE_LIMIT");
   var pages=new ArrayList<Map<String,Object>>();var stripper=new PDFTextStripper();stripper.setSortByPosition(true);int chars=0;
   for(int page=1;page<=pdf.getNumberOfPages();page++){stripper.setStartPage(page);stripper.setEndPage(page);String text=stripper.getText(pdf);chars+=text.length();if(chars>3000000)throw new IllegalArgumentException("PDF_TEXT_LIMIT");pages.add(Map.of("page",page,"text",text,"normalizedText",normalize(text)));}
   return pages;
  }
 }
}
