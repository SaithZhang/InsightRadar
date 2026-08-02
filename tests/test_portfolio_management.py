from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.decision_workspace import build_decision_workspace
from stock_assist.portfolio import Holding, Portfolio
from stock_assist.portfolio_import_server import apply_portfolio_management_response
from stock_assist.refresh_jobs import select_refresh_workflows


def _contract(state: str = "neutral") -> dict[str, object]:
    price_ready = state not in {"unknown", "quarantined"}
    return {
        "action": "持有观察" if price_ready else "等待数据，不做主动交易",
        "technical": {
            "state": state,
            "as_of": "2026-08-01",
            "adjustment_basis": "unadjusted",
            "close": 10.5 if price_ready else None,
            "ma20": 10.0 if price_ready else None,
            "support_20d": 9.6 if price_ready else None,
        },
        "cost_reference": {"authority": "reference_only"},
        "branches": [
            {
                "branch_id": "repair_observe",
                "trigger": "收盘站稳 10.00" if price_ready else "可靠行情恢复",
                "persistence": "连续两个有效收盘" if price_ready else "完成同口径校验",
                "action": "继续持有观察",
                "invalidation": "重新跌回结构下方" if price_ready else "校验再次失败",
            },
            {
                "branch_id": "risk_reduce_review",
                "trigger": "收盘跌破 9.60" if price_ready else "组合风险预算超限",
                "persistence": "连续一个有效收盘" if price_ready else "持续到下一次 after-close",
                "action": "降低仓位复核",
                "invalidation": "重新站回结构上方" if price_ready else "风险预算恢复",
            },
            {
                "branch_id": "continue_waiting",
                "trigger": "修复与风险条件均未成立",
                "persistence": "等待下一次有效收盘",
                "action": "维持当前仓位",
                "invalidation": "任一分支成立",
            },
        ],
    }


class PortfolioManagementTests(unittest.TestCase):
    def _workspace(
        self,
        holding: Holding,
        *,
        technical_state: str = "neutral",
    ) -> dict[str, object]:
        data_status = (
            "data_blocked"
            if technical_state in {"unknown", "quarantined"}
            else "ready"
        )
        portfolio = Portfolio(
            cash=20_000,
            holdings=[holding],
            source=Path("data/portfolio.json"),
            as_of="2026-08-01",
            risk_reconciliation_status="ready",
        )
        payload = {
            "generated_at": "2026-08-01T21:30:00",
            "data_gaps": [],
            "market_matrix": {},
            "reliability": {
                "holding_count": 1,
                "decision_ready_holdings": 1,
                "current_context_ready_holdings": int(bool(holding.risk_line)),
                "historical_context_ready_holdings": 0,
                "risk_reconciliation_status": "ready",
                "holdings": [
                    {
                        "code": holding.code,
                        "name": holding.name,
                        "current_context_complete": bool(holding.risk_line)
                        and holding.review_status != "stale_context",
                        "historical_context_complete": False,
                        "missing_current_context_fields": (
                            [] if holding.risk_line else ["当前风险规则"]
                        ),
                        "missing_historical_context_fields": ["原始买入逻辑"],
                        "missing_snapshot_fields": [],
                        "decision_ready": True,
                        "base_analysis_ready": True,
                        "risk_reconciliation_status": "ready",
                        "technical_state": technical_state,
                        "data_status": data_status,
                        "blocked_capabilities": (
                            ["均线判断", "支撑/压力判断", "价格阈值判断"]
                            if data_status == "data_blocked"
                            else []
                        ),
                        "available_capabilities": [
                            "持仓数量",
                            "成本参考",
                            "仓位占比",
                            "组合暴露",
                        ],
                    }
                ],
            },
            "unified_decision": {
                "plan_date": "2026-08-03",
                "stance": "谨慎持有",
                "first_action": "维持组合风险预算",
                "risk_budget": {
                    "risk_level": "green",
                    "upgrade_eligible": True,
                },
                "blocked_actions": [],
                "source_reports": [],
                "holding_plans": [
                    {
                        "code": holding.code,
                        "name": holding.name,
                        "action": "持有观察",
                        "position_action": "维持仓位",
                        "priority": "中",
                        "decision_contract": _contract(technical_state),
                    }
                ],
            },
        }
        return build_decision_workspace(
            payload,
            portfolio,
            generated_at=datetime(2026, 8, 1, 21, 30),
            response_ledger=Path("missing-responses.jsonl"),
            plan_ledger=Path("missing-plans.jsonl"),
        )

    @staticmethod
    def _holding(**overrides: object) -> Holding:
        defaults: dict[str, object] = {
            "code": "600001.SH",
            "name": "合成持仓",
            "shares": 1000,
            "cost": 10.0,
            "market_price": 10.5,
            "market_value": 10_500,
            "weight_pct": 20.0,
            "pnl_pct": 5.0,
            "review_status": "needs_context",
        }
        defaults.update(overrides)
        return Holding(**defaults)

    def test_missing_context_generates_system_proposal_without_blocking_base_analysis(self) -> None:
        workspace = self._workspace(self._holding())

        management = workspace["portfolio_management_plans"][0]
        plan = workspace["active_plans"][0]
        self.assertEqual(management["context_status"], "system_proposed")
        self.assertTrue(management["base_analysis_available"])
        self.assertNotIn("当前风险上下文", plan["blocking_reasons"])

    def test_stale_context_generates_replacement_and_explains_why(self) -> None:
        workspace = self._workspace(
            self._holding(
                risk_line="旧浮盈保护线",
                review_status="stale_context",
                context_status="stale",
            )
        )

        management = workspace["portfolio_management_plans"][0]
        self.assertEqual(management["context_status"], "stale")
        self.assertTrue(management["requires_confirmation"])
        self.assertIn("盈亏状态", management["stale_reason"])
        self.assertNotEqual(management["current_risk_line"], "旧浮盈保护线")

    def test_adopt_and_modify_are_saved_to_compatible_private_context(self) -> None:
        holding = self._holding()
        workspace = self._workspace(holding)
        proposal = workspace["portfolio_management_plans"][0]
        with TemporaryDirectory() as temporary:
            context_path = Path(temporary) / "portfolio_context.json"
            adopted = apply_portfolio_management_response(
                workspace,
                Portfolio(20_000, [holding], Path("portfolio.json"), as_of="2026-08-01"),
                {
                    "symbol": holding.code,
                    "management_plan_version": proposal["management_plan_version"],
                    "response": "adopt",
                },
                context_path=context_path,
                now=datetime(2026, 8, 1, 21, 31),
            )
            modified = apply_portfolio_management_response(
                workspace,
                Portfolio(20_000, [holding], Path("portfolio.json"), as_of="2026-08-01"),
                {
                    "symbol": holding.code,
                    "management_plan_version": proposal["management_plan_version"],
                    "response": "modify",
                    "management_choice": "risk_review",
                    "trigger_condition": "组合风险预算转为橙色",
                    "note": "等待下一次复核",
                },
                context_path=context_path,
                now=datetime(2026, 8, 1, 21, 32),
            )
            persisted = json.loads(context_path.read_text(encoding="utf-8"))

        self.assertEqual(adopted["context_status"], "user_confirmed")
        self.assertEqual(modified["context_status"], "user_modified")
        self.assertEqual(persisted["positions"][0]["review_status"], "risk_review")
        self.assertIn("组合风险预算转为橙色", persisted["positions"][0]["current_risk_line"])
        self.assertEqual(select_refresh_workflows("after_close", []), ("after-close",))

    def test_uncertain_keeps_base_analysis_and_does_not_claim_confirmation(self) -> None:
        holding = self._holding()
        workspace = self._workspace(holding)
        proposal = workspace["portfolio_management_plans"][0]
        with TemporaryDirectory() as temporary:
            saved = apply_portfolio_management_response(
                workspace,
                Portfolio(20_000, [holding], Path("portfolio.json"), as_of="2026-08-01"),
                {
                    "symbol": holding.code,
                    "management_plan_version": proposal["management_plan_version"],
                    "response": "uncertain",
                },
                context_path=Path(temporary) / "portfolio_context.json",
            )

        self.assertEqual(saved["context_status"], "system_proposed")
        self.assertEqual(saved["review_status"], "uncertain")
        self.assertTrue(proposal["base_analysis_available"])
        self.assertIsNone(saved["confirmed_at"])

    def test_user_confirmation_cannot_bypass_quarantined_price_data(self) -> None:
        holding = self._holding(code="900002.SH", name="合成芯片ETF")
        workspace = self._workspace(holding, technical_state="quarantined")
        proposal = workspace["portfolio_management_plans"][0]
        with TemporaryDirectory() as temporary:
            saved = apply_portfolio_management_response(
                workspace,
                Portfolio(20_000, [holding], Path("portfolio.json"), as_of="2026-08-01"),
                {
                    "symbol": holding.code,
                    "management_plan_version": proposal["management_plan_version"],
                    "response": "adopt",
                },
                context_path=Path(temporary) / "portfolio_context.json",
            )
        confirmed = replace(
            holding,
            context_status="user_confirmed",
            review_status=saved["review_status"],
            risk_line=saved["current_risk_line"],
        )
        rebuilt = self._workspace(confirmed, technical_state="quarantined")
        rebuilt_plan = rebuilt["portfolio_management_plans"][0]

        self.assertEqual(rebuilt_plan["context_status"], "user_confirmed")
        self.assertEqual(rebuilt_plan["data_status"], "data_blocked")
        self.assertIn("价格阈值判断", rebuilt_plan["blocked_capabilities"])
        self.assertIn("用户确认不能解除", rebuilt["active_plans"][0]["blocking_reasons"][0])

    def test_quarantined_data_never_generates_price_thresholds(self) -> None:
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
        )
        proposal = workspace["portfolio_management_plans"][0]
        rule_text = " ".join(
            str(proposal[field])
            for field in (
                "trigger_condition",
                "confirmation_window",
                "triggered_action",
                "invalidation_condition",
            )
        )
        self.assertNotIn("10.00", rule_text)
        self.assertNotIn("9.60", rule_text)
        self.assertNotIn("均线", rule_text)
        self.assertNotIn("支撑", rule_text)

    def test_ui_uses_user_language_and_separates_management_from_data_faults(self) -> None:
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
        )
        html = render_after_close_workbench(
            {"decision_workspace": workspace},
            "# synthetic",
        )

        self.assertIn("持仓管理方案待确认", html)
        self.assertIn("行情数据异常", html)
        self.assertIn("用户无需填写", html)
        self.assertIn("采用系统建议", html)
        self.assertIn("我不确定，仅按系统规则监控", html)
        self.assertNotIn("current_risk_line", html)
        self.assertNotIn("review_status", html)
        self.assertNotIn("stale_context", html)


if __name__ == "__main__":
    unittest.main()
