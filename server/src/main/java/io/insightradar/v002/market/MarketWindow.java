package io.insightradar.v002.market;

import java.time.*;
import java.util.List;

public record MarketWindow(Instant cutoff) {
 public static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
 public static final LocalTime OPEN = LocalTime.of(9, 15);
 public static final LocalTime CLOSE = LocalTime.of(15, 0);
 public static final LocalTime BAOSTOCK_RELEASE = LocalTime.of(18, 0);
 public static final String POLICY = "SESSION_AWARE_BAOSTOCK_R1";

 public LocalDate date() { return cutoff.atZone(ZONE).toLocalDate(); }
 public LocalTime time() { return cutoff.atZone(ZONE).toLocalTime(); }
 public LocalDate closedThrough() { return time().isBefore(CLOSE) ? date().minusDays(1) : date(); }
 public LocalDate requestThrough() { return time().isBefore(BAOSTOCK_RELEASE) ? date().minusDays(1) : date(); }

 public String phase(List<LocalDate> sessions) {
  if (sessions.isEmpty()) return "UNKNOWN";
  if (!sessions.contains(date())) return "NON_TRADING_DAY";
  if (time().isBefore(OPEN)) return "PRE_OPEN";
  return time().isBefore(CLOSE) ? "IN_SESSION" : "POST_CLOSE";
 }

 public boolean awaitingRelease(LocalDate expectedDate) {
  return date().equals(expectedDate) && time().isBefore(BAOSTOCK_RELEASE);
 }

 public static OffsetDateTime releaseAt(LocalDate date) {
  return date.atTime(BAOSTOCK_RELEASE).atZone(ZONE).toOffsetDateTime();
 }
}
