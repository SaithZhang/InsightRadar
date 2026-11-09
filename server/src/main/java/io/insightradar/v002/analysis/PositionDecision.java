package io.insightradar.v002.analysis;

import io.insightradar.v002.market.DataQualityValidator.Snapshot;
import io.insightradar.v002.market.MarketWindow;
import io.insightradar.v002.persistence.PositionRepository;
import io.insightradar.v002.persistence.PositionRepository.Position;
import io.insightradar.v002.technical.TechR1;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.dao.DataAccessException;

final class PositionDecision {
 record Capture(Instant at, List<Position> candidates, boolean failed) {
  static Capture read(PositionRepository positions, String code, Instant at) {
   try {
    return new Capture(at, List.copyOf(positions.candidates(code)), false);
   } catch (DataAccessException e) {
    return new Capture(at, List.of(), true);
   }
  }
 }

 record NextCheck(LocalDate tradeDate, LocalDate earliestAnalysisDate, OffsetDateTime earliestAnalysisAt, String message) {}

 record Decision(String schemaVersion, Instant capturedAt, String canonicalCode, Position position,
                 String positionStatus, String confirmationStatus, String priceState, String action, String reason,
                 String ruleId, String ruleVersion, TechR1.Sell evidence, NextCheck nextCheck) {}

 static Decision evaluate(Capture capture, String canonical, Snapshot market, TechR1.Sell evidence) {
  var day = capture.at().atZone(PositionRepository.ZONE).toLocalDate();
  Position position = canonical == null ? null : capture.candidates().stream()
      .filter(item -> item.canonicalCode().equals(canonical)).findFirst().orElse(null);
  String state = capture.failed() ? "READ_FAILED" : canonical == null ? "IDENTITY_UNCONFIRMED" :
      position == null ? "UNREGISTERED" : position.quantity() == 0 ? "CLEARED" : "HOLDING";
  boolean current = position != null && position.confirmedAt().atZone(PositionRepository.ZONE).toLocalDate().equals(day);
  String confirmation = position == null ? "UNAVAILABLE" : current ? "CONFIRMED" : "STALE";
  String priceState = switch (evidence.state()) {
   case "PRICE_RISK_REVIEW" -> "TRIGGERED";
   case "NOT_TRIGGERED" -> "NOT_TRIGGERED";
   default -> "DATA_INSUFFICIENT";
  };
  String action;
  String reason;
  if (!current) {
   action = "CONFIRM_POSITION";
   reason = switch (state) {
    case "READ_FAILED" -> "本机持仓读取失败，修复后重新生成分析。";
    case "IDENTITY_UNCONFIRMED" -> "证券身份尚未确认，请核对代码和行情来源后重新生成分析。";
    case "UNREGISTERED" -> "该证券没有持仓记录。请登记股数，空仓可明确登记为零。";
    default -> "这份持仓在之前的日期确认。请在持仓页核对股数，或选择「确认未变」。";
   };
  } else if (state.equals("CLEARED")) {
   action = "OBSERVE";
   reason = "你已确认该标的为零股。可查看价格信号和符合条件的 D+1 观察计划。";
  } else if (priceState.equals("DATA_INSUFFICIENT")) {
   action = "WAIT_FOR_DATA";
   reason = priceGap(market);
  } else if (priceState.equals("NOT_TRIGGERED")) {
   action = "EXIT_CONDITION_NOT_MET";
   reason = "最近两个有效开放日中，至少一天的收盘达到或高于当日 MA55。";
  } else if (position.onMa55Trigger() == null) {
   action = "SET_EXIT_RULE";
   reason = "两日收盘均低于各自 MA55。可在持仓页为这个条件设置退出纪律。";
  } else {
   action = position.onMa55Trigger();
   reason = "两日收盘均低于各自 MA55，已达到你设定的评估条件。";
  }
  return new Decision("position-v1", capture.at(), canonical, position, state, confirmation, priceState, action,
      reason, "TWO_CLOSES_BELOW_MA55", TechR1.VERSION, evidence, nextCheck(market, evidence));
 }

 private static String priceGap(Snapshot market) {
  if (market == null) return "尚未取得行情终值和交易日历。";
  if (!market.reliable()) return "行情质量或价格口径校验未通过，请查看来源与缺口。";
  if (market.gaps().stream().anyMatch(gap -> gap.startsWith("TODAY_FINAL_BAR_AWAITING_PROVIDER:")))
   return "今日已收盘，等待行情源发布当日终值及复权数据。";
  if (!market.fresh()) return "缺少 " + market.expectedDate() + " 的有效终值，可能停牌或来源尚未提供。";
  int index = market.sessions().indexOf(market.asOfTradeDate());
  if (index > 0) {
   var previous = market.sessions().get(index - 1);
   if (market.bars().stream().noneMatch(bar -> bar.date().equals(previous)))
    return "缺少前一个开放日 " + previous + " 的有效终值，无法连续比较。";
  }
  return "缺少连续两个开放日及各自计算 MA55 所需的有效历史。";
 }

 private static NextCheck nextCheck(Snapshot market, TechR1.Sell evidence) {
  if (evidence.state().equals("UNKNOWN")) {
   LocalDate expected = market == null ? null : market.expectedDate();
   boolean waiting = market != null && market.gaps().stream()
       .anyMatch(gap -> gap.startsWith("TODAY_FINAL_BAR_AWAITING_PROVIDER:"));
   return new NextCheck(expected, waiting ? expected : null, waiting ? MarketWindow.releaseAt(expected) : null, priceGap(market));
  }
  var next = market.sessions().stream().filter(session -> session.isAfter(evidence.date())).findFirst();
  if (next.isEmpty()) return new NextCheck(null, null, null, "待取得下一开放日的交易日历。");
  var session = next.get();
  return new NextCheck(session, session, MarketWindow.releaseAt(session), "待该交易日终值与复权数据发布后检查。");
 }

 private PositionDecision() {}
}
