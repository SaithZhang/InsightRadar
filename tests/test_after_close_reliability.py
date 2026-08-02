from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.portfolio import (
    Holding,
    Portfolio,
    load_manual_broker_portfolio,
    load_portfolio,
)
from stock_assist.workflows.after_close import (
    _broker_snapshot_lines,
    _current_decision_context_complete,
    _historical_context_complete,
    _signal_for_holding,
    _signal_from_broker_snapshot,
    build_after_close_bundle,
    build_after_close_payload,
)

ACTION_MARKDOWN = """# 盘后持仓操作指引

## 数据缺口
- 暂无

## 可选扩展缺口
- 未采集大V观点流水

## 持仓动作
### 中际旭创（300308.SZ）
- 建议动作：持有但不加仓
- 核心理由：趋势确认不足。
- 仓位动作：不加仓。
- 上行条件：站回20日线。
- 下行条件：破位后减仓复核。
- 震荡处理：保持仓位等待确认。
- 明日优先级：中
"""

SYNTHETIC_ACTION_MARKDOWN = """# 盘后持仓操作指引

## 数据缺口
- 暂无

## 持仓动作
### 合成标的甲（600001.SH）
- 建议动作：持有但不加仓
- 核心理由：趋势确认不足。
- 仓位动作：不加仓。
- 上行条件：站回20日线。
- 下行条件：破位后减仓复核。
- 震荡处理：保持仓位等待确认。
- 明日优先级：中
"""


def _outcome_snapshot() -> dict[str, object]:
    return {
        "as_of_trade_date": "2026-07-17",
        "horizons": {"1d": {"matured": 2, "hit_rate": 0.5}},
        "latest": [],
    }


def _daily_result(frame: pd.DataFrame) -> ProviderResult[pd.DataFrame]:
    return ProviderResult(
        provider="synthetic",
        schema_version="daily-ohlcv/v1",
        source_time=None,
        fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
        trade_date=None,
        status="ok",
        gaps=(),
        errors=(),
        price_basis="unadjusted",
        data=frame,
    )


class AfterCloseReliabilityTests(unittest.TestCase):
    @patch("stock_assist.workflows.after_close.build_after_close_report")
    @patch("stock_assist.workflows.after_close.build_after_close_payload")
    def test_bundle_uses_payload_driven_workbench_renderer(
        self,
        build_payload: object,
        build_report: object,
    ) -> None:
        build_report.return_value = ACTION_MARKDOWN
        payload = {
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 0,
                "decision_ready_holdings": 0,
            },
            "unified_decision": {
                "holding_plans": [],
                "holding_execution_plans": [],
                "risk_budget": {},
                "blocked_actions": [],
                "data_gaps": [],
                "source_reports": [],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "groups": [],
                "portfolio_translation": "不改变当前计划",
            },
            "sections": [],
            "signal_outcomes": {},
            "data_gaps": [],
        }
        build_payload.side_effect = [payload, payload]

        result, markdown, html = build_after_close_bundle(
            portfolio=Portfolio(
                cash=None,
                holdings=[],
                source=Path("data/portfolio.json"),
            ),
        )

        self.assertIs(result, payload)
        self.assertIn('id="route-today" data-route-panel="today"', html)
        self.assertIn('data-view="lookup"', html)
        self.assertIn("Rule-first decision intelligence", html)
        self.assertIn("不改变当前计划", html)
        self.assertNotIn('class="dashboard"', html)

    def test_portfolio_json_retains_explicit_snapshot_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "portfolio.json"
            path.write_text(
                json.dumps(
                    {
                        "as_of": "2026-07-18",
                        "source_note": "user-confirmed snapshot",
                        "holdings": [{"code": "300308.SZ", "name": "中际旭创", "weight_pct": 20}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            portfolio = load_portfolio(path)

        self.assertEqual(portfolio.as_of, "2026-07-18")
        self.assertEqual(portfolio.source_note, "user-confirmed snapshot")

    def test_stale_context_blocks_current_decision_context(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            thesis="合成订单兑现待验证",
            initial_risk_line="跌破结构位后复核",
            risk_line="价格与基本面共同复核",
            review_status="stale_context",
        )

        self.assertFalse(_current_decision_context_complete(holding))

    def test_unknown_entry_history_does_not_block_current_decision_context(self) -> None:
        holding = Holding(
            code="900001.SH",
            name="合成标的甲",
            thesis="合成订单兑现待验证",
            initial_risk_line="用户未提供原始买入时的失效条件；不得事后伪造。",
            risk_line="价格破位并出现基本面反证时复核",
            review_status="risk_review",
        )

        self.assertTrue(_current_decision_context_complete(holding))
        self.assertFalse(_historical_context_complete(holding))

    @patch("stock_assist.workflows.after_close.load_outcome_snapshot", side_effect=_outcome_snapshot)
    def test_missing_user_context_does_not_block_base_after_close_analysis(self, _mock) -> None:
        portfolio = Portfolio(
            cash=400000,
            holdings=[
                Holding(
                    code="600001.SH",
                    name="合成标的甲",
                    shares=100,
                    cost=900,
                    market_price=950,
                    pnl_pct=5.5,
                    market_value=95000,
                    weight_pct=19,
                    review_status="needs_context",
                )
            ],
            source=Path("fixture-portfolio.json"),
            as_of="2026-07-31",
            risk_reconciliation_status="reconciled",
        )

        payload = build_after_close_payload(SYNTHETIC_ACTION_MARKDOWN, portfolio=portfolio)

        self.assertEqual(payload["data_gaps"], [])
        self.assertEqual(payload["reliability"]["decision_ready_holdings"], 1)
        management = payload["decision_workspace"]["portfolio_management_plans"][0]
        self.assertEqual(management["context_status"], "system_proposed")
        self.assertTrue(management["base_analysis_available"])

    @patch("stock_assist.workflows.after_close.load_outcome_snapshot", side_effect=_outcome_snapshot)
    def test_unknown_entry_history_is_a_review_gap_not_a_decision_blocker(self, _mock) -> None:
        portfolio = Portfolio(
            cash=400000,
            holdings=[
                Holding(
                    code="300308.SZ",
                    name="合成标的甲",
                    shares=100,
                    cost=900,
                    market_price=950,
                    pnl_pct=5.5,
                    market_value=95000,
                    weight_pct=19,
                    thesis="合成需求假设待持续验证",
                    initial_risk_line="用户未提供原始买入时的失效条件；不得事后伪造。",
                    risk_line="价格破位并出现基本面反证时复核",
                    review_status="risk_review",
                )
            ],
            source=Path("fixture-portfolio.json"),
            as_of="2026-07-31",
            risk_reconciliation_status="reconciled",
        )

        payload = build_after_close_payload(ACTION_MARKDOWN, portfolio=portfolio)

        reliability = payload["reliability"]
        holding = reliability["holdings"][0]
        self.assertEqual(reliability["decision_ready_holdings"], 1)
        self.assertTrue(holding["current_context_complete"])
        self.assertTrue(holding["context_complete"])
        self.assertFalse(holding["historical_context_complete"])
        self.assertEqual(
            holding["missing_historical_context_fields"],
            ["原始买入失效条件"],
        )
        self.assertNotIn("持仓上下文未补全", "；".join(payload["data_gaps"]))
        self.assertTrue(
            any("仅影响复盘" in item for item in reliability["optional_extension_gaps"])
        )

    @patch("stock_assist.workflows.after_close.load_outcome_snapshot", side_effect=_outcome_snapshot)
    def test_placeholder_gap_is_not_counted_and_missing_snapshot_blocks_strict_readiness(self, _mock) -> None:
        portfolio = Portfolio(
            cash=None,
            holdings=[
                Holding(
                    code="300308.SZ",
                    name="中际旭创",
                    market_value=100000,
                    weight_pct=20,
                    thesis="AI光互连需求",
                    initial_risk_line="用户未提供原始条件",
                    risk_line="破位并有反证时复核",
                    review_status="risk_review",
                )
            ],
            source=Path("data/portfolio.json"),
            as_of="2026-07-18",
        )

        payload = build_after_close_payload(ACTION_MARKDOWN, portfolio=portfolio)

        self.assertEqual(payload["data_gaps"], [])
        reliability = payload["reliability"]
        self.assertIn("未采集大V观点流水", reliability["optional_extension_gaps"])
        self.assertTrue(
            any(
                "历史买入上下文未知" in item
                for item in reliability["optional_extension_gaps"]
            )
        )
        self.assertEqual(reliability["structural_action_holdings"], 1)
        self.assertEqual(reliability["decision_ready_holdings"], 0)
        self.assertIn("成本", reliability["holdings"][0]["missing_snapshot_fields"])
        matrix = payload["market_matrix"]
        self.assertEqual(matrix["authority"], "diagnostic_only")
        self.assertEqual(
            [group["id"] for group in matrix["groups"]],
            ["risk_assets", "macro_pressure"],
        )
        self.assertEqual(
            payload["reliability"]["holding_count"],
            len(payload["unified_decision"]["holding_plans"]),
        )

    @patch("stock_assist.workflows.after_close.load_outcome_snapshot", side_effect=_outcome_snapshot)
    def test_complete_snapshot_context_and_action_reach_strict_readiness(self, _mock) -> None:
        portfolio = Portfolio(
            cash=400000,
            holdings=[
                Holding(
                    code="300308.SZ",
                    name="中际旭创",
                    shares=100,
                    cost=900,
                    market_price=979.46,
                    pnl_pct=8.8,
                    market_value=97946,
                    weight_pct=20,
                    thesis="AI光互连需求",
                    initial_risk_line="跌破900且基本面转弱",
                    risk_line="破位并有反证时复核",
                    review_status="risk_review",
                )
            ],
            source=Path("data/portfolio.json"),
            as_of="2026-07-18",
        )

        payload = build_after_close_payload(ACTION_MARKDOWN, portfolio=portfolio)

        reliability = payload["reliability"]
        self.assertEqual(reliability["structural_action_coverage"], 1.0)
        self.assertEqual(reliability["decision_ready_coverage"], 1.0)
        self.assertEqual(payload["actions"][0]["downside_trigger"], "破位后减仓复核。")

    def test_broker_snapshot_does_not_render_missing_values_as_zero(self) -> None:
        portfolio = Portfolio(
            cash=None,
            holdings=[Holding(code="300308.SZ", name="中际旭创", market_value=100000, weight_pct=20)],
            source=Path("data/portfolio.json"),
        )

        lines = _broker_snapshot_lines(portfolio)

        self.assertEqual(len(lines), 1)
        self.assertIn("仓位 20.00％", lines[0])
        self.assertIn("成本 未提供", lines[0])
        self.assertIn("市价 未提供", lines[0])
        self.assertIn("总盈亏 未提供", lines[0])
        self.assertNotIn("成本 0.000", lines[0])

    def test_user_broker_tsv_format_preserves_position_numbers(self) -> None:
        header = "操作\t证券代码\t证券名称\t自有股份可用\t股票余额\t成本价\t市价\t盈亏\t盈亏比例(%)\t当日盈亏\t当日盈亏比(%)\t市值\t仓位占比(%)\t交易市场\t当前持仓\t股份可用\t融资买入证券可用\t信用资金占用\t客户余券\t是否担保品\t买入冻结\t卖出冻结\t当日买入\t当日卖出\t划转数量"
        row = "\t300308\t中际旭创\t100\t100\t1336.141\t979.460\t-35668.080\t-26.695\t-13354.00\t-12.00\t97946.000\t19.17\t深Ａ\t100\t100\t0\t0.00\t0.000\t担保品\t0.000\t0.000\t0\t0\t0"
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "broker.tsv"
            path.write_text(f"{header}\n{row}\n", encoding="utf-8")
            portfolio = load_manual_broker_portfolio(path)

        self.assertEqual(len(portfolio.holdings), 1)
        holding = portfolio.holdings[0]
        self.assertEqual(holding.code, "300308.SZ")
        self.assertEqual(holding.shares, 100)
        self.assertEqual(holding.cost, 1336.141)
        self.assertEqual(holding.market_price, 979.46)
        self.assertEqual(holding.pnl, -35668.08)
        self.assertEqual(holding.pnl_pct, -26.695)
        self.assertEqual(holding.day_pnl, -13354.0)
        self.assertEqual(holding.weight_pct, 19.17)

    def test_adjustment_basis_mismatch_quarantines_price_thresholds(self) -> None:
        holding = Holding(
            code="900002.SH",
            name="合成标的乙",
            shares=1000,
            cost=1.2,
            market_price=1.18,
            pnl_pct=-1.7,
        )
        frame = pd.DataFrame({"close": [3.2 + index * 0.01 for index in range(20)]})

        signal = _signal_for_holding(holding, _daily_result(frame))

        self.assertEqual(signal.action, "等待数据，不做主动交易")
        self.assertIn("复权或标的映射口径不一致", signal.reason)
        self.assertIn("不使用当前均线或价格阈值", signal.position_action)
        self.assertEqual(signal.priority, "高")

    def test_broker_only_fallback_does_not_invent_cost_or_price_triggers(self) -> None:
        signal = _signal_from_broker_snapshot(
            Holding(
                code="900001.SH",
                name="合成标的甲",
                cost=130.0,
                market_price=96.0,
                pnl_pct=-20.0,
            )
        )

        self.assertEqual(signal.action, "等待数据，不做主动交易")
        self.assertNotIn("130.00", signal.upside_trigger)
        self.assertNotIn("96.00", signal.downside_trigger)
        self.assertEqual(
            signal.decision_contract["cost_reference"]["authority"],
            "reference_only",
        )


if __name__ == "__main__":
    unittest.main()
