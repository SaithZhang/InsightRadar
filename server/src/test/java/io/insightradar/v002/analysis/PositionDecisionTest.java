package io.insightradar.v002.analysis;

import io.insightradar.v002.market.DataQualityValidator.Snapshot;
import io.insightradar.v002.persistence.PositionRepository;
import io.insightradar.v002.persistence.PositionRepository.Position;
import io.insightradar.v002.technical.TechR1;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class PositionDecisionTest {
 private static final Instant AT = Instant.parse("2026-11-09T01:00:00Z");
 private static final LocalDate DAY = LocalDate.of(2026, 11, 9);
 private static final String CODE = "002463.SZ";

 @Test void sameSignalHasDifferentActionsForHoldingClearedAndUnconfirmedPositions() {
  var market = market(false, false, true);
  var evidence = rule(market);
  assertThat(evidence.state()).isEqualTo("PRICE_RISK_REVIEW");
  assertThat(decision(market, evidence, position(100, "REVIEW_EXIT", AT)).action()).isEqualTo("REVIEW_EXIT");
  assertThat(decision(market, evidence, position(100, "REVIEW_REDUCTION", AT)).action()).isEqualTo("REVIEW_REDUCTION");
  assertThat(decision(market, evidence, position(100, null, AT)).action()).isEqualTo("SET_EXIT_RULE");
  assertThat(decision(market, evidence, position(0, null, AT)).action()).isEqualTo("OBSERVE");
  var stale = decision(market, evidence, position(100, "REVIEW_EXIT", AT.minusSeconds(10 * 3600)));
  assertThat(stale.confirmationStatus()).isEqualTo("STALE");
  assertThat(stale.action()).isEqualTo("CONFIRM_POSITION");
  assertThat(stale.priceState()).isEqualTo("TRIGGERED");

  var candidate = new Position("002463.SH", 200, null, "REVIEW_EXIT", "MANUAL", AT, AT, 1);
  var capture = new PositionDecision.Capture(AT, List.of(candidate), false);
  assertThat(PositionDecision.evaluate(capture, CODE, market, evidence).positionStatus()).isEqualTo("UNREGISTERED");
  assertThat(PositionDecision.evaluate(capture, null, market, evidence).positionStatus()).isEqualTo("IDENTITY_UNCONFIRMED");

  var repo = mock(PositionRepository.class);
  when(repo.candidates("002463")).thenThrow(new DataAccessResourceFailureException("test"));
  var failed = PositionDecision.evaluate(PositionDecision.Capture.read(repo, "002463", AT), CODE, market, evidence);
  assertThat(failed.positionStatus()).isEqualTo("READ_FAILED");
  assertThat(failed.priceState()).isEqualTo("TRIGGERED");
 }

 @Test void equalitySuspensionAndStaleTerminalBarsAreSeparated() {
  var holding = position(100, "REVIEW_EXIT", AT);
  var equal = market(true, false, true);
  var notTriggered = decision(equal, rule(equal), holding);
  assertThat(notTriggered.priceState()).isEqualTo("NOT_TRIGGERED");
  assertThat(notTriggered.action()).isEqualTo("EXIT_CONDITION_NOT_MET");
  assertThat(notTriggered.nextCheck().tradeDate()).isEqualTo(DAY);
  assertThat(notTriggered.nextCheck().earliestAnalysisDate()).isEqualTo(DAY);
  var skipped = market(false, true, true);
  var insufficient = decision(skipped, rule(skipped), holding);
  assertThat(insufficient.priceState()).isEqualTo("DATA_INSUFFICIENT");
  assertThat(insufficient.action()).isEqualTo("WAIT_FOR_DATA");
  assertThat(insufficient.reason()).contains(DAY.minusDays(2).toString());
  var stale = market(false, false, false);
  assertThat(decision(stale, rule(stale), holding).priceState()).isEqualTo("DATA_INSUFFICIENT");
 }

 private static PositionDecision.Decision decision(Snapshot market, TechR1.Sell evidence, Position position) {
  return PositionDecision.evaluate(new PositionDecision.Capture(AT, List.of(position), false), CODE, market, evidence);
 }

 private static Position position(int quantity, String action, Instant at) {
  return new Position(CODE, quantity, null, action, "MANUAL", at, at, 1);
 }

 private static Snapshot market(boolean equal, boolean gap, boolean fresh) {
  var sessions = IntStream.rangeClosed(0, 60).mapToObj(i -> DAY.minusDays(60 - i)).toList();
  var bars = IntStream.range(0, 60).filter(i -> !gap || i != 58).mapToObj(i -> {
   var close = BigDecimal.valueOf(equal ? 10 : 100 - i);
   return new TechR1.Bar(sessions.get(i), close, close, close, close, BigDecimal.ONE, BigDecimal.ONE);
  }).toList();
  return new Snapshot(bars, sessions, DAY.minusDays(1), DAY.minusDays(1), true, fresh, List.of(), Map.of(), List.of());
 }

 private static TechR1.Sell rule(Snapshot market) {
  return TechR1.analyze(market.bars(), market.sessions(), market.asOfTradeDate(), market.reliable(), market.fresh()).sellReview();
 }
}
