package io.insightradar.v002;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
public final class Json {
 public static final ObjectMapper MAPPER=new ObjectMapper().registerModule(new JavaTimeModule())
  .registerModule(new SimpleModule().addSerializer(BigDecimal.class,ToStringSerializer.instance))
  .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
 public static String write(Object o){try{return MAPPER.writeValueAsString(o);}catch(Exception e){throw new IllegalArgumentException("JSON_SERIALIZATION",e);}}
 public static JsonNode read(String s){try{return MAPPER.readTree(s);}catch(Exception e){throw new IllegalArgumentException("INVALID_JSON",e);}}
 public static String hash(Object o){return hashBytes(write(o).getBytes(StandardCharsets.UTF_8));}
 public static String hashBytes(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(Exception e){throw new IllegalStateException(e);}}
 private Json(){}
}
