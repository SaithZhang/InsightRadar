from __future__ import annotations

from dataclasses import replace
import unittest

import pandas as pd

from stock_assist.holding_decision import build_holding_decision
from stock_assist.portfolio import Holding, _merge_holding_context


class HoldingDecisionTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        closes = [
            112.0,
            111.5,
            111.0,
            110.5,
            110.0,
            109.5,
            109.0,
            108.5,
            108.0,
            107.5,
            107.0,
            106.5,
            106.0,
            105.5,
            105.0,
            104.5,
            104.0,
            103.5,
            103.0,
            102.5,
            102.0,
            101.5,
            101.0,
            100.5,
            100.0,
            99.5,
            99.0,
            98.5,
            98.0,
            96.0,
        ]
        return pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-06-19", periods=len(closes)),
                "close": closes,
                "high": [value + 1.2 for value in closes],
                "low": [value - 1.0 for value in closes],
                "volume": [1000 + index * 10 for index in range(len(closes))],
            }
        )

    def test_cost_changes_do_not_change_technical_state_or_levels(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            cost=130.0,
            market_price=96.0,
            pnl_pct=-20.0,
            weight_pct=25.0,
        )
        low_cost = replace(holding, cost=80.0)

        original = build_holding_decision(holding, self._frame())
        changed_cost = build_holding_decision(low_cost, self._frame())

        self.assertEqual(original.technical, changed_cost.technical)
        self.assertEqual(original.action, changed_cost.action)
        self.assertEqual(
            [item.threshold for item in original.branches],
            [item.threshold for item in changed_cost.branches],
        )
        self.assertEqual(
            original.cost_reference["authority"],
            "reference_only",
        )
        self.assertNotEqual(
            original.cost_reference["cost"],
            changed_cost.cost_reference["cost"],
        )

    def test_plan_uses_three_complete_branches_and_no_price_multiplier(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            cost=130.0,
            market_price=96.0,
            pnl_pct=-20.0,
            weight_pct=25.0,
        )

        decision = build_holding_decision(holding, self._frame())

        self.assertEqual(
            [item.branch_id for item in decision.branches],
            ["repair_observe", "risk_reduce_review", "continue_waiting"],
        )
        for branch in decision.branches:
            self.assertTrue(branch.trigger)
            self.assertTrue(branch.persistence)
            self.assertTrue(branch.action)
            self.assertTrue(branch.invalidation)
            self.assertTrue(branch.review_time)
        rendered = str(decision.to_contract())
        self.assertNotIn("站回成本", rendered)
        self.assertNotIn(f"{96.0 * 0.97:.2f}", rendered)
        self.assertIn("moving_average", decision.technical.evidence_families)
        self.assertIn("price_structure", decision.technical.evidence_families)
        self.assertEqual(
            decision.branch("repair_observe").threshold,
            decision.technical.support_20d,
        )
        self.assertIn(
            "风险分支已进入确认期",
            decision.branch("risk_reduce_review").trigger,
        )

    def test_unreachable_threshold_is_explicitly_multi_session(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            cost=150.0,
            market_price=96.0,
        )
        frame = self._frame()
        frame.loc[frame.index[-20:-1], "close"] = 120.0
        frame.loc[frame.index[-1], "close"] = 96.0
        frame.loc[frame.index[-20:-1], "high"] = 121.0
        frame.loc[frame.index[-20:-1], "low"] = 119.0

        decision = build_holding_decision(holding, frame)

        repair = decision.branch("repair_observe")
        self.assertTrue(repair.reachability.startswith("multi_session_min_"))
        self.assertNotEqual(repair.threshold, holding.cost)

    def test_amazingdata_kline_time_is_preserved_as_technical_as_of(self) -> None:
        frame = self._frame().rename(columns={"trade_date": "kline_time"})

        decision = build_holding_decision(
            Holding(code="900001.SH", name="合成标的甲", market_price=96.0),
            frame,
        )

        self.assertEqual(decision.technical.as_of, "2026-07-18")

    def test_large_unadjusted_price_discontinuity_quarantines_technical_levels(self) -> None:
        frame = self._frame()
        frame.loc[frame.index[:21], "close"] = 4.0
        frame.loc[frame.index[21:], "close"] = 1.2
        frame.loc[frame.index[-1], "close"] = 1.1

        decision = build_holding_decision(
            Holding(
                code="900002.SH",
                name="合成标的乙",
                market_price=1.1,
            ),
            frame,
        )

        self.assertEqual(decision.technical.state, "quarantined")
        self.assertEqual(decision.action, "等待数据，不做主动交易")
        self.assertIn("单日价格断点", decision.reason)
        self.assertIsNone(decision.branch("repair_observe").threshold)

    def test_missing_prices_block_model_levels_instead_of_using_zero(self) -> None:
        decision = build_holding_decision(
            Holding(code="900001.SH", cost=130.0, market_price=96.0),
            pd.DataFrame({"volume": [1, 2, 3]}),
        )

        self.assertEqual(decision.technical.state, "unknown")
        self.assertIsNone(decision.technical.close)
        self.assertIsNone(decision.branch("repair_observe").threshold)
        self.assertEqual(decision.action, "等待数据，不做主动交易")

    def test_new_loss_snapshot_invalidates_old_profit_protection_context(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            cost=130.0,
            market_price=96.0,
            pnl_pct=-20.0,
        )
        context = {
            "buy_thesis": "AI服务器PCB订单兑现需要继续验证。",
            "initial_risk_line": "临时关注浮盈保护。",
            "current_risk_line": "浮盈较大，优先保护利润。",
            "review_status": "profit_protect",
            "observation_window": "2026-07-09 至 2026-07-19",
            "next_review_date": "2026-07-12",
        }

        merged = _merge_holding_context(holding, context)

        self.assertEqual(merged.review_status, "stale_context")
        self.assertIn("最新券商盈亏状态冲突", merged.risk_line)
        self.assertEqual(merged.observation_window, "")
        self.assertEqual(merged.next_review_date, "")


if __name__ == "__main__":
    unittest.main()
