package io.insightradar.v002.persistence;

import io.insightradar.v002.market.MarketWindow;
import java.math.BigDecimal;
import java.math.MathContext;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class PositionRepository {
 public static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");

 public record Position(String canonicalCode, int quantity, BigDecimal unitCost, String onMa55Trigger,
                        String source, Instant confirmedAt, Instant updatedAt, long version) {}

 public record Item(Position position, String name, boolean confirmedToday, LocalDate quoteDate,
                    BigDecimal referenceClose, BigDecimal marketValue, BigDecimal unrealizedPnl,
                    BigDecimal unrealizedPnlPercent) {}

 private final JdbcTemplate jdbc;

 public PositionRepository(JdbcTemplate jdbc) {
  this.jdbc = jdbc;
 }

 private static Position row(ResultSet rs, int rowNumber) throws SQLException {
  return new Position(rs.getString("canonical_code"), rs.getInt("quantity"), rs.getBigDecimal("unit_cost"),
      rs.getString("on_ma55_trigger"), rs.getString("source"), rs.getTimestamp("confirmed_at").toInstant(),
      rs.getTimestamp("updated_at").toInstant(), rs.getLong("version"));
 }

 public List<Position> candidates(String code) {
  if (code.length() == 6) {
   return jdbc.query("SELECT p.* FROM positions p JOIN securities s USING (canonical_code) WHERE s.code = ?",
       PositionRepository::row, code);
  }
  return jdbc.query("SELECT * FROM positions WHERE canonical_code = ?", PositionRepository::row, code);
 }

 public Optional<Position> save(String code, int quantity, BigDecimal cost, String action, long expectedVersion) {
  if (expectedVersion == 0) {
   return jdbc.query("""
       INSERT INTO positions(canonical_code, quantity, unit_cost, on_ma55_trigger, confirmed_at, updated_at, version)
       VALUES (?, ?, ?, ?, now(), now(), 1)
       ON CONFLICT (canonical_code) DO NOTHING RETURNING *
       """, PositionRepository::row, code, quantity, cost, action).stream().findFirst();
  }
  return jdbc.query("""
      UPDATE positions
      SET quantity = ?, unit_cost = ?, on_ma55_trigger = ?, confirmed_at = now(), updated_at = now(), version = version + 1
      WHERE canonical_code = ? AND version = ? RETURNING *
      """, PositionRepository::row, quantity, cost, action, code, expectedVersion).stream().findFirst();
 }

 public List<Item> list(String status) {
  var window = new MarketWindow(Instant.now());
  LocalDate today = window.date();
  return jdbc.query("""
      SELECT p.*, s.name, q.as_of_date, q.reference_close
      FROM positions p JOIN securities s USING (canonical_code)
      LEFT JOIN LATERAL (
        SELECT m.as_of_date, r.bar->>'close' AS reference_close
        FROM market_snapshots m
        CROSS JOIN LATERAL jsonb_array_elements(m.raw_jsonb) AS r(bar)
        WHERE m.canonical_code = p.canonical_code
          AND m.quality_jsonb->>'reliable' = 'true' AND m.as_of_date <= ?
          AND r.bar->>'date' = m.as_of_date::text AND r.bar->>'adjustflag' = '3'
          AND r.bar->>'tradestatus' = '1' AND r.bar->>'code' = m.source_jsonb->'identity'->>'providerCode'
        ORDER BY m.as_of_date DESC, m.fetched_at DESC, m.id DESC LIMIT 1
      ) q ON p.quantity > 0
      WHERE CASE ? WHEN 'holding' THEN p.quantity > 0 WHEN 'cleared' THEN p.quantity = 0 ELSE true END
      ORDER BY p.canonical_code
      """, (rs, n) -> {
   var position = row(rs, n);
   var close = rs.getBigDecimal("reference_close");
   var shares = BigDecimal.valueOf(position.quantity());
   var cost = position.unitCost();
   var value = position.quantity() == 0 ? BigDecimal.ZERO : close == null ? null : shares.multiply(close);
   var pnl = close == null || cost == null ? null : close.subtract(cost).multiply(shares);
   var percent = pnl == null || cost.signum() <= 0 ? null :
       close.subtract(cost).movePointRight(2).divide(cost, MathContext.DECIMAL128);
   return new Item(position, rs.getString("name"), position.confirmedAt().atZone(ZONE).toLocalDate().equals(today),
       rs.getObject("as_of_date", LocalDate.class), close, value, pnl, percent);
  }, window.requestThrough(), status);
 }
}
