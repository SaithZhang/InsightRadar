package io.insightradar.v002.api;
public class AppException extends RuntimeException {
 public final String code,stage; public final boolean retryable; public final int httpStatus;
 public AppException(String code,String message,String stage,boolean retryable,int httpStatus){super(message);this.code=code;this.stage=stage;this.retryable=retryable;this.httpStatus=httpStatus;}
}
