package io.insightradar.v002.api;

import com.fasterxml.jackson.databind.JsonNode;
import io.insightradar.v002.market.MarketDataProvider;
import io.insightradar.v002.persistence.SnapshotRepository;
import org.springframework.stereotype.Component;

@Component
public class SecurityLookup {
 private final MarketDataProvider market;
 private final SnapshotRepository snapshots;

 public SecurityLookup(MarketDataProvider market, SnapshotRepository snapshots) {
  this.market = market;
  this.snapshots = snapshots;
 }

 public JsonNode resolve(String code) {
  if (code.length() == 9) {
   var known = snapshots.securityIdentity(code);
   if (known.isPresent()) return known.get();
  }
  JsonNode identity = market.resolve(code);
  String canonical = identity.path("canonicalCode").asText();
  if (!canonical.matches("[0-9]{6}\\.(SH|SZ|BJ)") || !canonical.startsWith(code) ||
      !identity.path("sixDigitCode").asText().equals(canonical.substring(0, 6))) {
   throw new AppException("INVALID_SECURITY", "未能核实证券和交易所", "IDENTITY", false, 422);
  }
  snapshots.security(identity);
  return identity;
 }
}
