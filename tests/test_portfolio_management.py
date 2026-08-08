from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.decision_workspace import build_decision_workspace
from stock_assist.portfolio import Holding, Portfolio, _with_position_context
from stock_assist.portfolio_import_server import (
    apply_portfolio_management_response,
    start_repair_recheck,
)
from stock_assist.refresh_jobs import select_refresh_workflows


def _contract(
    state: str = "neutral",
    *,
    provider_status: str | None = None,
    gaps: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
) -> dict[str, object]:
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
        "data_evidence": {
            "provider": "amazingdata",
            "schema_version": "daily-ohlcv/v1",
            "status": provider_status
            or ("quarantined" if state == "quarantined" else "ok"),
            "source_time": None,
            "fetched_at": "2026-08-01T15:05:00+08:00",
            "trade_date": "2026-08-01",
            "price_basis": "unadjusted",
            "gaps": list(gaps),
            "errors": list(errors),
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
        decision_contract: dict[str, object] | None = None,
        missing_snapshot_fields: list[str] | None = None,
        source_reports: list[dict[str, object]] | None = None,
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
                        "missing_snapshot_fields": missing_snapshot_fields or [],
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
                "source_reports": source_reports or [],
                "holding_plans": [
                    {
                        "code": holding.code,
                        "name": holding.name,
                        "action": "持有观察",
                        "position_action": "维持仓位",
                        "priority": "中",
                        "decision_contract": decision_contract
                        or _contract(technical_state),
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
        self.assertEqual(workspace["repair_issues"], [])
        self.assertEqual(plan["data_status"], "ready")
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

    def test_saved_manual_context_survives_reload_and_after_close_rebuild(self) -> None:
        holding = self._holding()
        workspace = self._workspace(holding)
        proposal = workspace["portfolio_management_plans"][0]
        with TemporaryDirectory() as temporary:
            context_path = Path(temporary) / "portfolio_context.json"
            apply_portfolio_management_response(
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
            reloaded = _with_position_context(
                Portfolio(
                    20_000,
                    [holding],
                    Path("portfolio.json"),
                    as_of="2026-08-01",
                ),
                context_path,
            )

        rebuilt = self._workspace(reloaded.holdings[0])
        rebuilt_management = rebuilt["portfolio_management_plans"][0]
        self.assertEqual(rebuilt_management["context_status"], "user_confirmed")
        self.assertFalse(rebuilt_management["requires_confirmation"])
        self.assertTrue(rebuilt_management["current_risk_line"])

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

    def test_quarantined_issue_has_structured_repair_contract_and_provider_lineage(self) -> None:
        contract = _contract(
            "quarantined",
            gaps=("900002.SH:price_discontinuity:0.618819",),
        )
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
            decision_contract=contract,
        )

        issue = workspace["repair_issues"][0]
        self.assertEqual(issue["entity"]["symbol"], "900002.SH")
        self.assertEqual(issue["field"], "daily_kline.price_basis")
        self.assertEqual(issue["status"], "quarantined")
        self.assertEqual(issue["reason_code"], "PRICE_BASIS_QUARANTINED")
        self.assertEqual(issue["source"], "amazingdata")
        self.assertIsNone(issue["source_time"])
        self.assertEqual(issue["fetched_at"], "2026-08-01T15:05:00+08:00")
        self.assertEqual(issue["price_basis"], "unadjusted")
        self.assertFalse(issue["manual_repair_allowed"])
        self.assertEqual(issue["repair_method"], "retry_after_close")
        self.assertIn("不能使用 0", issue["criticality_reason"])
        self.assertIn("重新生成", issue["next_action"])

    def test_provider_mapping_fault_is_auto_retried_not_manually_overridden(self) -> None:
        contract = _contract(
            "unknown",
            provider_status="invalid",
            errors=("900003.SH:code_mismatch",),
        )
        workspace = self._workspace(
            self._holding(code="900003.SH", name="合成映射异常"),
            technical_state="unknown",
            decision_contract=contract,
        )

        issue = workspace["repair_issues"][0]
        self.assertEqual(issue["field"], "security.mapping")
        self.assertEqual(issue["reason_code"], "SECURITY_MAPPING_INVALID")
        self.assertFalse(issue["manual_repair_allowed"])
        self.assertEqual(issue["repair_method"], "retry_after_close")
        self.assertIn("腾讯前复权全序列", issue["repair_label"])

        coordinator = Mock()
        coordinator.start.return_value = {"run_id": "mapping-run", "status": "pending"}
        with TemporaryDirectory() as temporary:
            repair_state_path = Path(temporary) / "daily-repair.json"
            start_repair_recheck(
                workspace,
                {
                    "issue_id": issue["issue_id"],
                    "workspace_generated_at": workspace["generated_at"],
                },
                coordinator,
                repair_state_path=repair_state_path,
            )
            repair_state = json.loads(repair_state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            repair_state["repairs"]["900003.SH"]["reason_code"],
            "SECURITY_MAPPING_INVALID",
        )

        repaired = self._workspace(
            self._holding(code="900003.SH", name="合成映射异常"),
            technical_state="neutral",
            decision_contract=_contract("neutral"),
        )
        self.assertEqual(repaired["repair_issues"], [])
        self.assertEqual(repaired["active_plans"][0]["data_status"], "ready")

    def test_stale_source_issue_is_structured_and_links_blocked_plan(self) -> None:
        workspace = self._workspace(
            self._holding(),
            source_reports=[
                {
                    "workflow": "market_pulse",
                    "status": "stale",
                    "source_time": "2026-07-30",
                    "path": "reports/market-pulse.json",
                }
            ],
        )

        issue = next(
            item
            for item in workspace["repair_issues"]
            if item["field"] == "source.market_pulse"
        )
        plan = workspace["active_plans"][0]
        self.assertEqual(issue["status"], "stale")
        self.assertEqual(issue["reason_code"], "SOURCE_STALE")
        self.assertFalse(issue["manual_repair_allowed"])
        self.assertEqual(issue["repair_method"], "refresh_sources")
        self.assertIn(issue["issue_id"], plan["repair_issue_ids"])
        self.assertEqual(workspace["market_gate"]["status"], "blocked")

    def test_missing_core_snapshot_field_routes_to_approved_import_without_zero_fill(self) -> None:
        workspace = self._workspace(
            self._holding(market_price=None),
            missing_snapshot_fields=["券商市价"],
        )

        issue = next(
            item
            for item in workspace["repair_issues"]
            if item["field"] == "portfolio.market_price"
        )
        self.assertIsNone(issue["current_value"])
        self.assertEqual(issue["status"], "missing")
        self.assertTrue(issue["manual_repair_allowed"])
        self.assertEqual(issue["repair_method"], "portfolio_import")
        self.assertIn("券商持仓", issue["input_format"])

    def test_ui_exposes_issue_detail_direct_action_and_explicit_recheck(self) -> None:
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
            decision_contract=_contract(
                "quarantined",
                gaps=("900002.SH:price_discontinuity:0.618819",),
            ),
        )
        html = render_after_close_workbench(
            {"decision_workspace": workspace},
            "# synthetic",
        )

        self.assertIn("核心数据缺口", html)
        self.assertIn("daily_kline.price_basis", html)
        self.assertIn("为什么阻断", html)
        self.assertIn("当前系统知道什么", html)
        self.assertIn("data-repair-action", html)
        self.assertIn("重新检查并生成", html)
        self.assertIn('post("/api/repair-recheck"', html)
        self.assertIn("问题仍保持 blocked", html)
        self.assertIn("pollRefresh(job.run_id, container)", html)
        self.assertIn("重新检查未完成", html)

    def test_recheck_validates_current_issue_and_starts_only_after_close(self) -> None:
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
            decision_contract=_contract(
                "quarantined",
                gaps=("900002.SH:price_discontinuity:0.618819",),
            ),
        )
        issue = workspace["repair_issues"][0]
        coordinator = Mock()
        coordinator.start.return_value = {"run_id": "repair-run", "status": "pending"}
        with TemporaryDirectory() as temporary:
            repair_state_path = Path(temporary) / "daily-repair.json"
            job = start_repair_recheck(
                workspace,
                {
                    "issue_id": issue["issue_id"],
                    "workspace_generated_at": workspace["generated_at"],
                    "request_id": "repair-request",
                },
                coordinator,
                repair_state_path=repair_state_path,
            )
            repair_state = json.loads(repair_state_path.read_text(encoding="utf-8"))

        self.assertEqual(job["run_id"], "repair-run")
        self.assertEqual(
            repair_state["repairs"]["900002.SH"]["strategy"],
            "tencent_forward_adjusted_whole_series",
        )
        coordinator.start.assert_called_once_with(
            mode="after_close",
            data_health=(),
            idempotency_key="repair-request",
        )
        with self.assertRaisesRegex(ValueError, "版本已过期"):
            start_repair_recheck(
                workspace,
                {
                    "issue_id": issue["issue_id"],
                    "workspace_generated_at": "stale-version",
                },
                coordinator,
            )

    def test_source_recheck_targets_only_selected_stale_source(self) -> None:
        workspace = self._workspace(
            self._holding(),
            source_reports=[
                {
                    "workflow": "market_pulse",
                    "status": "stale",
                    "source_time": "2026-07-30",
                },
                {
                    "workflow": "market_levels",
                    "status": "missing",
                    "source_time": None,
                },
            ],
        )
        issue = next(
            item
            for item in workspace["repair_issues"]
            if item["field"] == "source.market_pulse"
        )
        matching_health = next(
            item
            for item in workspace["data_health"]
            if item["source_name"] == "market_pulse"
        )
        coordinator = Mock()
        coordinator.start.return_value = {"run_id": "source-run", "status": "pending"}

        start_repair_recheck(
            workspace,
            {
                "issue_id": issue["issue_id"],
                "workspace_generated_at": workspace["generated_at"],
            },
            coordinator,
        )

        coordinator.start.assert_called_once_with(
            mode="stale",
            data_health=(matching_health,),
            idempotency_key=(
                f"repair-recheck:{issue['issue_id']}:{workspace['generated_at']}"
            ),
        )

    def test_recheck_failure_is_not_swallowed_and_issue_remains_blocked(self) -> None:
        workspace = self._workspace(
            self._holding(code="900002.SH", name="合成芯片ETF"),
            technical_state="quarantined",
        )
        issue = workspace["repair_issues"][0]
        coordinator = Mock()
        coordinator.start.side_effect = RuntimeError("after-close failed")

        with self.assertRaisesRegex(RuntimeError, "after-close failed"):
            start_repair_recheck(
                workspace,
                {
                    "issue_id": issue["issue_id"],
                    "workspace_generated_at": workspace["generated_at"],
                },
                coordinator,
            )

        self.assertEqual(workspace["repair_issues"][0]["status"], "quarantined")


if __name__ == "__main__":
    unittest.main()
