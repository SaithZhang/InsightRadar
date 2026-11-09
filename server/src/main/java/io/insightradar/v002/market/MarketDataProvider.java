package io.insightradar.v002.market;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDate;
public interface MarketDataProvider {
 JsonNode resolve(String code);
 JsonNode snapshot(String code, LocalDate start, LocalDate end);
}
