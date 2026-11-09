package io.insightradar.v002.disclosure;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.io.*;
import java.util.*;
import org.springframework.stereotype.Component;
/** Fixed official hosts, verified TLS, bounded bodies and validated redirects. */
@Component
public class OfficialHttp {
 private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).followRedirects(HttpClient.Redirect.NEVER).build();
 private static final Set<String> HOSTS=Set.of("www.cninfo.com.cn","static.cninfo.com.cn");
 public static URI allowed(String url){URI u=URI.create(url);if(!"https".equals(u.getScheme())||!HOSTS.contains(u.getHost())||u.getUserInfo()!=null||(u.getPort()!=-1&&u.getPort()!=443))throw new IllegalArgumentException("UNTRUSTED_OFFICIAL_URL");return u;}
 public byte[] get(String url,int limit)throws Exception{return request(allowed(url),null,limit,0);}
 public byte[] post(String url,Map<String,String>form,int limit)throws Exception{StringJoiner j=new StringJoiner("&");form.forEach((k,v)->j.add(URLEncoder.encode(k,java.nio.charset.StandardCharsets.UTF_8)+"="+URLEncoder.encode(v,java.nio.charset.StandardCharsets.UTF_8)));return request(allowed(url),j.toString(),limit,0);}
 private byte[] request(URI uri,String body,int limit,int redirects)throws Exception{
  if(redirects>3)throw new IOException("REDIRECT_LIMIT");
  var builder=HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(25)).header("User-Agent","Mozilla/5.0 InsightRadarLocal/0.2").header("Referer","https://www.cninfo.com.cn/");
  if(body!=null)builder.header("Content-Type","application/x-www-form-urlencoded").POST(HttpRequest.BodyPublishers.ofString(body));
  var response=client.send(builder.build(),HttpResponse.BodyHandlers.ofInputStream());
  try(var in=response.body()){
   if(response.statusCode()/100==3){URI next=allowed(uri.resolve(response.headers().firstValue("location").orElseThrow()).toString());return request(next,null,limit,redirects+1);}
   if(response.statusCode()!=200)throw new IOException("OFFICIAL_HTTP_"+response.statusCode());
   if(response.headers().firstValueAsLong("content-length").orElse(0)>limit)throw new IOException("OFFICIAL_SIZE_LIMIT");
   byte[] bytes=in.readNBytes(limit+1);if(bytes.length>limit)throw new IOException("OFFICIAL_SIZE_LIMIT");return bytes;
  }
 }
}
