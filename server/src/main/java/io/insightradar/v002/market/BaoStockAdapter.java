package io.insightradar.v002.market;
import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.Json;
import io.insightradar.v002.api.AppException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.*;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.*;
@Component
public class BaoStockAdapter implements MarketDataProvider {
 private final String python,bridge;
 public BaoStockAdapter(@Value("${app.python}")String python,@Value("${app.bridge}")String bridge){this.python=python;this.bridge=bridge;}
 public JsonNode resolve(String code){return call("resolve",code,null,null).path("identity");}
 public JsonNode snapshot(String code,LocalDate start,LocalDate end){return call("snapshot",code,start,end);}
 private synchronized JsonNode call(String command,String code,LocalDate start,LocalDate end){
  if(code==null || !code.trim().toUpperCase(Locale.ROOT).matches("[0-9]{6}(\\.(SH|SZ|BJ))?"))throw new AppException("INVALID_SECURITY","请输入六位股票代码，可带交易所后缀","IDENTITY",false,422);
  List<String> args=new ArrayList<>(List.of(python,bridge,command,"--code",code.trim().toUpperCase(Locale.ROOT)));
  if(start!=null){args.add("--start");args.add(start.toString());}
  if(end!=null){args.add("--end");args.add(end.toString());}
  Process p=null;
  try(var pool=Executors.newVirtualThreadPerTaskExecutor()){
   p=new ProcessBuilder(args).redirectError(ProcessBuilder.Redirect.DISCARD).start(); final Process process=p;
   Future<byte[]> bytes=pool.submit(()->{byte[] b=process.getInputStream().readNBytes(16*1024*1024+1);if(b.length>16*1024*1024){process.destroyForcibly();throw new IOException("OUTPUT_LIMIT");}return b;});
   if(!p.waitFor(180,TimeUnit.SECONDS)){p.destroyForcibly();throw new AppException("PROVIDER_TIMEOUT","BaoStock 在 180 秒内未完成行情请求，请稍后重新分析","MARKET",true,503);}
   JsonNode result=Json.read(new String(bytes.get(2,TimeUnit.SECONDS),java.nio.charset.StandardCharsets.UTF_8));
   if(result.has("error")){var e=result.path("error");throw new AppException(e.path("code").asText(),e.path("message").asText(),"MARKET",e.path("retryable").asBoolean(),e.path("code").asText().equals("INVALID_SECURITY")?422:503);}
   if(p.exitValue()!=0)throw new IOException("BRIDGE_EXIT");return result;
  }catch(AppException e){throw e;}catch(Exception e){throw new AppException("PROVIDER_UNAVAILABLE","BaoStock 本地桥接不可用："+e.getClass().getSimpleName(),"MARKET",true,503);}finally{if(p!=null&&p.isAlive())p.destroyForcibly();}
 }
}
