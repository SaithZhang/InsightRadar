package io.insightradar.v002.intelligence;

import com.fasterxml.jackson.core.type.TypeReference;
import io.insightradar.v002.Json;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LlmRequestRepository {
    private final JdbcTemplate jdbc;

    public LlmRequestRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Map<String, Object>> cached(String cacheKey) {
        return jdbc.query("""
                SELECT result_jsonb::text FROM llm_requests
                WHERE cache_key = ? AND result_jsonb IS NOT NULL
                ORDER BY requested_at DESC, id DESC LIMIT 1
                """, (rs, row) -> Json.MAPPER.convertValue(Json.read(rs.getString(1)),
                new TypeReference<Map<String, Object>>() {}), cacheKey).stream().findFirst();
    }

    public boolean reserve(UUID id, String cacheKey, BigDecimal amount, BigDecimal monthlyBudget) {
        var zone = ZoneId.of("Asia/Shanghai");
        var now = ZonedDateTime.now(zone);
        var month = YearMonth.from(now);
        return jdbc.update("""
                INSERT INTO llm_requests (id, cache_key, reserved_usd, requested_at)
                SELECT ?, ?, ?, ? WHERE ? >= ? + (
                    SELECT COALESCE(SUM(reserved_usd), 0) FROM llm_requests
                    WHERE requested_at >= ? AND requested_at < ?
                )
                """, id, cacheKey, amount, now.toOffsetDateTime(), monthlyBudget, amount,
                month.atDay(1).atStartOfDay(zone).toOffsetDateTime(),
                month.plusMonths(1).atDay(1).atStartOfDay(zone).toOffsetDateTime()) == 1;
    }

    public void saveResult(UUID id, Map<String, Object> result) {
        jdbc.update("UPDATE llm_requests SET result_jsonb = ?::jsonb WHERE id = ? AND result_jsonb IS NULL",
                Json.write(result), id);
    }
}
