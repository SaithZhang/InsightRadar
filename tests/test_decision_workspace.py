from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from stock_assist.decision_workspace import (
    append_plan_response,
    build_decision_workspace,
    load_plan_versions,
    load_plan_responses,
    record_plan_versions,
    restage_workspace,
)
from stock_assist.after_close_workbench_html import render_after_close_workbench
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
        self.assertEqual(
            after_acknowledgement["active_plans"][-1]["user_response_status"],
            "blocked_acknowledged",
        )

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

    def test_blocked_plan_rejects_acceptance_and_renders_acknowledgement(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["blocked_actions"] = ["核心数据缺口阻断执行"]
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
        self.assertIn("不会进入有效计划或盘中监控", html)
        self.assertNotIn("采纳为今日计划", html)
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

        self.assertIn("计划内容未变，执行状态变为 blocked", unchanged_html)
        self.assertNotIn("上一版计划 · v-same", unchanged_html)
        self.assertIn("首次生成", first_html)
        self.assertNotIn("上一版计划", first_html)
        self.assertIn("上一版计划 · v-old", revised_html)
        self.assertIn("今日建议计划 · v-new", revised_html)

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
