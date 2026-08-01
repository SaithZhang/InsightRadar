from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.decision_workspace import (
    append_plan_response,
    build_decision_workspace,
    load_plan_responses,
    load_plan_versions,
    record_plan_versions,
    restage_workspace,
)
from stock_assist.portfolio import Holding, Portfolio


class DecisionWorkspaceTests(unittest.TestCase):
    def _portfolio(self) -> Portfolio:
        return Portfolio(
            cash=None,
            holdings=[
                Holding(
                    code="000001.SZ",
                    name="示例持仓",
                    shares=100,
                    cost=None,
                    market_price=10.5,
                    pnl_pct=None,
                    market_value=1050,
                    weight_pct=12.5,
                    beta_classification="unknown",
                )
            ],
            source=Path("fixture-portfolio.json"),
            as_of="2026-07-24",
            risk_reconciliation_status="unverified",
        )

    def _payload(self) -> dict[str, object]:
        return {
            "generated_at": "2026-07-24T18:30:00",
            "data_gaps": ["示例持仓缺少成本与盈亏字段"],
            "unified_decision": {
                "plan_date": "2026-07-25",
                "stance": "谨慎持有",
                "first_action": "等待条件，不抢跑",
                "risk_budget": {"risk_level": "yellow", "risk_score": 62},
                "blocked_actions": [],
                "source_reports": [
                    {
                        "workflow": "risk_watch",
                        "status": "current",
                        "as_of": "2026-07-24",
                        "path": "reports/risk-watch.json",
                    },
                    {
                        "workflow": "market_levels",
                        "status": "missing",
                        "as_of": None,
                    },
                ],
                "holding_plans": [
                    {
                        "code": "000001.SZ",
                        "name": "示例持仓",
                        "position_action": "不追涨，等待确认",
                        "upside_trigger": "三个 15 分钟 K 线站稳关键位",
                        "flat_trigger": "下一交易日收盘前复核",
                        "downside_trigger": "跌破风险线则计划失效",
                    }
                ],
            },
            "market_matrix": {"groups": []},
            "reliability": {
                "decision_ready_holdings": 0,
                "holding_count": 1,
                "risk_reconciliation_status": "ready",
                "holdings": [
                    {
                        "code": "000001.SZ",
                        "context_complete": True,
                        "missing_snapshot_fields": [],
                        "decision_ready": True,
                        "risk_reconciliation_status": "ready",
                    }
                ],
            },
            "sections": [],
            "signal_outcomes": {},
        }

    def test_schema_keeps_unknown_values_and_explicit_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                generated_at=datetime(2026, 7, 24, 18, 30),
                response_ledger=Path(temporary) / "responses.jsonl",
                plan_ledger=Path(temporary) / "plans.jsonl",
            )

        self.assertEqual(workspace["schema_version"], "decision-workspace/v1")
        self.assertTrue(str(workspace["portfolio_version"]).startswith("portfolio-"))
        self.assertEqual(workspace["run_stage"], "after_close")
        statuses = {item["status"] for item in workspace["data_health"]}
        self.assertTrue({"ready", "missing", "blocked"}.issubset(statuses))
        position = workspace["portfolio_positions"][0]
        self.assertIsNone(position["cost"])
        self.assertIsNone(position["pnl_pct"])
        self.assertEqual(position["beta_classification"], "unknown")
        self.assertEqual(
            len(workspace["plan_changes"]),
            sum(
                plan["user_response_status"] == "pending"
                and plan["status"] in {"new", "revised", "voided", "blocked"}
                for plan in workspace["active_plans"]
            ),
        )
        self.assertEqual(
            workspace["source_generated_at"],
            workspace["generated_at"],
        )

    def test_structured_branches_keep_if_then_semantics_aligned(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["holding_plans"][0]["decision_contract"] = {
            "action": "降低仓位复核",
            "technical": {
                "state": "weak",
                "close": 9.5,
                "ma20": 10.0,
                "support_20d": 9.2,
            },
            "cost_reference": {
                "authority": "reference_only",
                "cost": 15.0,
            },
            "branches": [
                {
                    "branch_id": "repair_observe",
                    "trigger": "收盘站上20日线10.00",
                    "persistence": "连续2个交易日",
                    "action": "降为持有观察，不自动加仓",
                },
                {
                    "branch_id": "risk_reduce_review",
                    "trigger": "当前收盘9.50已低于技术结构位10.00",
                    "persistence": "下一交易日未收回",
                    "action": "复核降低仓位",
                },
                {
                    "branch_id": "continue_waiting",
                    "trigger": "两侧条件均未满足",
                    "persistence": "保持到下一有效收盘",
                    "action": "保持仓位",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=root / "responses.jsonl",
                plan_ledger=root / "plans.jsonl",
            )

        plan = workspace["active_plans"][0]
        self.assertIn("收盘站上20日线10.00", plan["if_condition"])
        self.assertEqual(plan["then_action"], "降为持有观察，不自动加仓")
        self.assertEqual(plan["current_branch"], "risk_reduce_review")
        self.assertEqual(plan["current_action"], "降低仓位复核")
        self.assertEqual(plan["current_next_event"], "下一交易日未收回")
        self.assertIn("当前收盘9.50已低于技术结构位10.00", plan["invalid_condition"])
        self.assertNotIn("成本", plan["if_condition"])
        self.assertEqual(plan["cost_reference"]["authority"], "reference_only")
        self.assertEqual(len(plan["branches"]), 3)

    def test_reduction_current_action_is_not_blocked_as_added_exposure(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["risk_budget"] = {
            "risk_level": "red",
            "upgrade_blocked": True,
            "upgrade_eligible": False,
        }
        payload["unified_decision"]["holding_plans"][0]["decision_contract"] = {
            "action": "降低仓位复核",
            "technical": {"state": "weak"},
            "branches": [
                {
                    "branch_id": "repair_observe",
                    "trigger": "站回结构位",
                    "action": "从降低仓位复核降为观察；不自动加仓",
                },
                {
                    "branch_id": "risk_reduce_review",
                    "trigger": "当前收盘已低于结构位",
                    "persistence": "下一收盘仍未收回",
                    "action": "复核降低仓位",
                },
                {
                    "branch_id": "continue_waiting",
                    "trigger": "两侧未确认",
                    "action": "保持仓位",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=root / "responses.jsonl",
                plan_ledger=root / "plans.jsonl",
            )

        plan = workspace["active_plans"][0]
        self.assertEqual(plan["current_action"], "降低仓位复核")
        self.assertNotIn(
            "当前风险预算禁止新增或提高风险仓位。",
            plan["blocking_reasons"],
        )

    def test_plan_versions_form_a_quiet_change_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "plans.jsonl"
            responses = Path(temporary) / "responses.jsonl"
            first = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                generated_at=datetime(2026, 7, 24, 18, 30),
                response_ledger=responses,
                plan_ledger=ledger,
            )
            first_rows = record_plan_versions(first, ledger)
            unchanged = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                generated_at=datetime(2026, 7, 24, 19, 0),
                response_ledger=responses,
                plan_ledger=ledger,
            )
            unchanged_rows = record_plan_versions(unchanged, ledger)
            revised_payload = self._payload()
            revised_payload["unified_decision"]["holding_plans"][0][
                "position_action"
            ] = "仅在市场门成立后减仓"
            revised = build_decision_workspace(
                revised_payload,
                self._portfolio(),
                generated_at=datetime(2026, 7, 24, 19, 30),
                response_ledger=responses,
                plan_ledger=ledger,
            )
            revised_rows = record_plan_versions(revised, ledger)

            persisted = load_plan_versions(ledger)

        self.assertEqual(len(first_rows), 1)
        self.assertEqual(len(unchanged_rows), 1)
        self.assertEqual(len(revised_rows), 2)
        self.assertEqual(persisted[-1]["previous_version"], persisted[0]["plan_version"])
        self.assertNotEqual(persisted[-1]["plan_version"], persisted[0]["plan_version"])
        self.assertEqual(
            unchanged["active_plans"][0]["previous_version"],
            persisted[0]["plan_version"],
        )
        self.assertEqual(unchanged["active_plans"][0]["status"], "unchanged")
        self.assertEqual(revised["active_plans"][0]["status"], "revised")

    def test_today_queue_exactly_matches_pending_actionable_plans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty_payload = self._payload()
            empty_payload["unified_decision"]["holding_plans"] = []
            empty = build_decision_workspace(
                empty_payload,
                self._portfolio(),
                response_ledger=root / "empty-responses.jsonl",
                plan_ledger=root / "empty-plans.jsonl",
            )
            single = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                response_ledger=root / "single-responses.jsonl",
                plan_ledger=root / "single-plans.jsonl",
            )
            crowded_payload = self._payload()
            base_plan = crowded_payload["unified_decision"]["holding_plans"][0]
            crowded_payload["unified_decision"]["holding_plans"] = [
                {**base_plan, "code": f"00000{index}.SZ", "name": f"示例{index}"}
                for index in range(1, 5)
            ]
            crowded_payload["reliability"]["risk_reconciliation_status"] = "blocked"
            crowded = build_decision_workspace(
                crowded_payload,
                self._portfolio(),
                response_ledger=root / "crowded-responses.jsonl",
                plan_ledger=root / "crowded-plans.jsonl",
            )
            acknowledged = crowded["active_plans"][-1]
            append_plan_response(
                plan_id=acknowledged["plan_id"],
                plan_version=acknowledged["plan_version"],
                response="blocked_acknowledged",
                plan_status="blocked",
                ledger_path=root / "crowded-responses.jsonl",
            )
            after_acknowledgement = build_decision_workspace(
                crowded_payload,
                self._portfolio(),
                response_ledger=root / "crowded-responses.jsonl",
                plan_ledger=root / "crowded-plans.jsonl",
            )

        self.assertEqual(empty["plan_changes"], [])
        self.assertEqual(len(single["plan_changes"]), 1)
        self.assertEqual(len(crowded["active_plans"]), 4)
        self.assertEqual(len(crowded["plan_changes"]), 4)
        self.assertTrue(
            all(
                plan["user_response_status"] == "pending"
                for plan in crowded["plan_changes"]
            )
        )
        self.assertEqual(len(after_acknowledgement["plan_changes"]), 3)
        self.assertEqual(len(after_acknowledgement["today_plans"]), 4)
        self.assertEqual(
            after_acknowledgement["active_plans"][-1]["user_response_status"],
            "blocked_acknowledged",
        )

    def test_acknowledged_blocked_plan_stays_visible_until_repaired(self) -> None:
        payload = self._payload()
        payload["reliability"]["risk_reconciliation_status"] = "blocked"
        payload["reliability"]["holdings"][0][
            "risk_reconciliation_status"
        ] = "blocked"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            responses = root / "responses.jsonl"
            plans = root / "plans.jsonl"
            original = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=responses,
                plan_ledger=plans,
            )
            plan = original["active_plans"][0]
            append_plan_response(
                plan_id=plan["plan_id"],
                plan_version=plan["plan_version"],
                response="blocked_acknowledged",
                plan_status="blocked",
                ledger_path=responses,
            )
            restored = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=responses,
                plan_ledger=plans,
            )
            payload["reliability"]["risk_reconciliation_status"] = "ready"
            payload["reliability"]["holdings"][0][
                "risk_reconciliation_status"
            ] = "ready"
            recovered = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=responses,
                plan_ledger=plans,
            )
            html = render_after_close_workbench(
                {"decision_workspace": restored},
                "",
            )

        self.assertEqual(restored["plan_changes"], [])
        self.assertEqual(len(restored["today_plans"]), 1)
        self.assertEqual(restored["runtime_status"], "blocked_waiting")
        self.assertIn("判断阻断", html)
        self.assertIn("不能把本规则变成已确认或提醒候选", html)
        self.assertIn("blocked_acknowledged", html)
        self.assertNotEqual(recovered["active_plans"][0]["status"], "blocked")
        self.assertEqual(
            recovered["active_plans"][0]["user_response_status"],
            "pending",
        )
        self.assertEqual(recovered["runtime_status"], "awaiting_confirmation")

    def test_local_holding_gap_does_not_block_an_unrelated_plan(self) -> None:
        payload = self._payload()
        base_plan = payload["unified_decision"]["holding_plans"][0]
        payload["unified_decision"]["holding_plans"] = [
            {**base_plan, "code": "000001.SZ", "name": "缺口持仓", "priority": "中"},
            {**base_plan, "code": "000002.SZ", "name": "就绪持仓", "priority": "高"},
        ]
        payload["reliability"]["holdings"] = [
            {
                "code": "000001.SZ",
                "context_complete": False,
                "missing_snapshot_fields": [],
                "decision_ready": False,
                "risk_reconciliation_status": "ready",
            },
            {
                "code": "000002.SZ",
                "context_complete": True,
                "missing_snapshot_fields": [],
                "decision_ready": True,
                "risk_reconciliation_status": "ready",
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=Path(temporary) / "responses.jsonl",
                plan_ledger=Path(temporary) / "plans.jsonl",
            )

        plans = {item["symbol"]: item for item in workspace["active_plans"]}
        self.assertEqual(plans["000001.SZ"]["status"], "blocked")
        self.assertEqual(plans["000002.SZ"]["status"], "new")
        self.assertEqual(workspace["today_plans"][0]["symbol"], "000002.SZ")

    def test_source_time_field_prevents_false_missing_status(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["source_reports"][1] = {
            "workflow": "market_levels",
            "status": "current",
            "source_time": "2026-07-24 15:00",
        }
        with tempfile.TemporaryDirectory() as temporary:
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                generated_at=datetime(2026, 7, 24, 18, 30),
                response_ledger=Path(temporary) / "responses.jsonl",
                plan_ledger=Path(temporary) / "plans.jsonl",
            )

        market_levels = next(
            item
            for item in workspace["data_health"]
            if item["id"] == "market_levels"
        )
        self.assertEqual(market_levels["status"], "ready")
        self.assertEqual(market_levels["source_time"], "2026-07-24 15:00")

    def test_historical_ma_basis_mismatch_is_quarantined_from_review(self) -> None:
        portfolio = Portfolio(
            cash=None,
            holdings=[
                Holding(
                    code="900002.SH",
                    name="合成标的乙",
                    shares=1000,
                    cost=12.0,
                    market_price=10.0,
                    pnl_pct=-16.7,
                )
            ],
            source=Path("fixture-portfolio.json"),
            as_of="2026-07-30",
            risk_reconciliation_status="blocked",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "plans.jsonl"
            ledger.write_text(
                json.dumps(
                    {
                        "plan_id": "holding:900002.SH",
                        "symbol": "900002.SH",
                        "plan_version": "v-old",
                        "if_condition": "若放量站回20日线 30.00 上方",
                        "then_action": "继续观察",
                        "until_condition": "下一次复核",
                        "invalid_condition": "跌破20日线 30.00",
                        "created_at": "2026-07-28T15:55:57",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            workspace = build_decision_workspace(
                self._payload(),
                portfolio,
                response_ledger=root / "responses.jsonl",
                plan_ledger=ledger,
            )
            html = render_after_close_workbench(
                {"decision_workspace": workspace},
                "",
            )

        history = workspace["plan_version_history"]
        self.assertEqual(workspace["quarantined_plan_version_count"], 1)
        self.assertEqual(history[0]["evaluation_status"], "quarantined")
        self.assertIn("口径异常，已隔离", html)

    def test_voided_plan_requires_an_explicit_pending_response(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["holding_plans"][0]["position_action"] = "作废该计划"
        with tempfile.TemporaryDirectory() as temporary:
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=Path(temporary) / "responses.jsonl",
                plan_ledger=Path(temporary) / "plans.jsonl",
            )

        plan = workspace["plan_changes"][0]
        self.assertEqual(plan["status"], "voided")
        self.assertEqual(plan["user_response_status"], "pending")
        self.assertTrue(plan["effective_after_user_confirmation"])

    def test_plan_response_is_atomic_and_version_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "responses.jsonl"
            record = append_plan_response(
                plan_id="holding:000001.SZ",
                plan_version="v-123",
                response="disputed",
                note="大盘条件尚未满足",
                ledger_path=ledger,
                created_at=datetime(2026, 7, 25, 8, 31),
            )
            rows = load_plan_responses(ledger)

        self.assertEqual(record["response"], "disputed")
        self.assertEqual(rows, [record])
        self.assertEqual(rows[0]["plan_version"], "v-123")
        self.assertFalse(ledger.with_suffix(".tmp").exists())

    def test_invalid_response_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                append_plan_response(
                    plan_id="holding:000001.SZ",
                    plan_version="v-123",
                    response="execute_now",
                    ledger_path=Path(temporary) / "responses.jsonl",
                )

    def test_disabled_response_is_persisted_and_not_monitor_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "responses.jsonl"
            record = append_plan_response(
                plan_id="holding:000001.SZ",
                plan_version="v-123",
                response="disabled",
                ledger_path=ledger,
            )
            rows = load_plan_responses(ledger)

        self.assertEqual(record["response"], "disabled")
        self.assertEqual(rows[-1]["response"], "disabled")

    def test_blocked_plan_rejects_acceptance_and_renders_acknowledgement(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["blocked_actions"] = ["核心数据缺口阻断执行"]
        payload["reliability"]["risk_reconciliation_status"] = "blocked"
        payload["reliability"]["holdings"][0][
            "risk_reconciliation_status"
        ] = "blocked"
        with tempfile.TemporaryDirectory() as temporary:
            workspace = build_decision_workspace(
                payload,
                self._portfolio(),
                response_ledger=Path(temporary) / "responses.jsonl",
                plan_ledger=Path(temporary) / "plans.jsonl",
            )
            blocked_plan = workspace["plan_changes"][0]
            with self.assertRaisesRegex(ValueError, "blocked"):
                append_plan_response(
                    plan_id=blocked_plan["plan_id"],
                    plan_version=blocked_plan["plan_version"],
                    response="accepted",
                    plan_status="blocked",
                    ledger_path=Path(temporary) / "responses.jsonl",
                )
            html = render_after_close_workbench(
                {"decision_workspace": workspace},
                "",
            )

        self.assertIn("确认已知悉阻断", html)
        self.assertIn("任何按钮都不能把本规则变成已确认或提醒候选", html)
        self.assertIn("暂不启用", html)
        self.assertNotIn('data-plan-response="accepted"', html)

    def test_version_display_separates_first_content_and_execution_changes(self) -> None:
        base_plan = {
            "plan_id": "holding:000001.SZ",
            "symbol": "000001.SZ",
            "name": "示例持仓",
            "plan_version": "v-same",
            "previous_version": "v-same",
            "status": "blocked",
            "if_condition": "站回20日线",
            "then_action": "继续观察",
            "until_condition": "下一次复核",
            "invalid_condition": "跌破风险线",
            "change_reasons": ["核心数据缺口阻断执行"],
            "risk_constraints": ["数据缺口"],
            "created_at": "2026-07-25T08:30:00",
            "user_response_status": "pending",
            "user_response_note": "",
        }
        unchanged_workspace = {
            "plan_changes": [base_plan],
            "active_plans": [base_plan],
            "plan_version_history": [
                {
                    **base_plan,
                    "previous_version": None,
                }
            ],
        }
        unchanged_html = render_after_close_workbench(
            {"decision_workspace": unchanged_workspace},
            "",
        )
        first_plan = {
            **base_plan,
            "plan_version": "v-first",
            "previous_version": None,
        }
        first_html = render_after_close_workbench(
            {
                "decision_workspace": {
                    "plan_changes": [first_plan],
                    "active_plans": [first_plan],
                    "plan_version_history": [],
                }
            },
            "",
        )
        previous = {
            **base_plan,
            "plan_version": "v-old",
            "previous_version": None,
            "then_action": "沿用旧计划",
        }
        revised = {
            **base_plan,
            "plan_version": "v-new",
            "previous_version": "v-old",
            "status": "revised",
            "then_action": "执行新计划",
        }
        revised_html = render_after_close_workbench(
            {
                "decision_workspace": {
                    "plan_changes": [revised],
                    "active_plans": [revised],
                    "plan_version_history": [previous],
                }
            },
            "",
        )

        self.assertIn('data-plan-version="v-same"', unchanged_html)
        self.assertIn("核心数据缺口阻断执行", unchanged_html)
        self.assertIn('data-plan-version="v-first"', first_html)
        self.assertIn('data-plan-version="v-new"', revised_html)
        self.assertIn("执行新计划", revised_html)

    def test_dispute_is_restored_only_for_the_matching_plan_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            responses = root / "responses.jsonl"
            plans = root / "plans.jsonl"
            original = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                response_ledger=responses,
                plan_ledger=plans,
            )
            plan = original["active_plans"][0]
            append_plan_response(
                plan_id=plan["plan_id"],
                plan_version=plan["plan_version"],
                response="disputed",
                note="市场门尚未成立",
                ledger_path=responses,
            )
            restored = build_decision_workspace(
                self._payload(),
                self._portfolio(),
                response_ledger=responses,
                plan_ledger=plans,
            )

        restored_plan = restored["active_plans"][0]
        self.assertEqual(restored_plan["user_response_status"], "disputed")
        self.assertEqual(restored_plan["user_response_note"], "市场门尚未成立")

    def test_morning_recheck_marks_old_ready_source_stale(self) -> None:
        workspace = {
            "run_stage": "after_close",
            "data_health": [
                {
                    "status": "ready",
                    "source_time": "2026-07-20",
                }
            ],
        }
        result = restage_workspace(
            workspace,
            run_stage="morning_recheck",
            now=datetime(2026, 7, 24, 8, 30),
        )

        self.assertEqual(result["run_stage"], "morning_recheck")
        self.assertEqual(result["data_health"][0]["status"], "stale")
        self.assertIn("未接入实时行情刷新", result["stage_note"])


if __name__ == "__main__":
    unittest.main()
