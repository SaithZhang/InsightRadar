package io.insightradar.v002.api;
import io.insightradar.v002.Json;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import java.util.Map;
@RestControllerAdvice
public class ApiErrors {
 @ExceptionHandler(AppException.class)public ResponseEntity<String> app(AppException e){return ResponseEntity.status(e.httpStatus).contentType(MediaType.APPLICATION_JSON).body(Json.write(Map.of("code",e.code,"message",e.getMessage(),"stage",e.stage,"retryable",e.retryable,"details",Map.of())));}
 @ExceptionHandler({MethodArgumentTypeMismatchException.class,HttpMessageNotReadableException.class})public ResponseEntity<String> bad(Exception e){return app(new AppException("INVALID_REQUEST","请求格式无效","API",false,422));}
 @ExceptionHandler(Exception.class)public ResponseEntity<String> other(Exception e){return app(new AppException("INTERNAL_ERROR","服务无法处理请求，请查看本地运行状态","API",true,500));}
}
