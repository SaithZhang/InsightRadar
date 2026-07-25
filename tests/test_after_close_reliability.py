from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.portfolio import Holding, Portfolio, load_manual_broker_portfolio, load_portfolio
from stock_assist.workflows.after_close import (
    _broker_snapshot_lines,
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


def _outcome_snapshot() -> dict[str, object]:
    return {
        "as_of_trade_date": "2026-07-17",
        "horizons": {"1d": {"matured": 2, "hit_rate": 0.5}},
        "latest": [],
    }


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
        self.assertIn('id="today"', html)
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
        self.assertEqual(reliability["optional_extension_gaps"], ["未采集大V观点流水"])
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


if __name__ == "__main__":
    unittest.main()
