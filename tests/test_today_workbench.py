from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_assist.today_workbench import build_today_workbench


class TodayWorkbenchContractTests(unittest.TestCase):
    def _plan(
        self,
        *,
        symbol: str,
        name: str,
        status: str = "new",
        response: str = "pending",
        evidence_refs: list[str] | None = None,
        blocking_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "plan_id": f"holding:{symbol}",
            "symbol": symbol,
            "name": name,
            "plan_version": f"v-{symbol}",
            "status": status,
            "priority": "高",
            "current_action": "继续观察结构修复",
            "current_next_event": "下一次已完成收盘",
            "invalid_condition": "跌破风险线",
            "change_reasons": ["计划状态由规则更新"],
            "blocking_reasons": blocking_reasons or [],
            "evidence_refs": evidence_refs or [],
            "user_response_status": response,
        }

    def test_weekend_snapshot_computes_pnl_peak_and_giveback(self) -> None:
        workspace = {
            "effective_market_date": "2026-07-31",
            "latest_completed_session": {
                "session_mode": "non_trading_day",
                "view_mode": "historical_review",
                "trade_date": "2026-07-31",
                "latest_snapshot": {
                    "timestamp": "2026-07-31T15:00:00",
                    "account_daily_pnl": 16361.0,
                    "account_peak_daily_pnl": 35433.0,
                    "pnl_giveback_ratio": 19072 / 35433,
                    "holding_snapshots": [
                        {"symbol": "A.SZ", "name": "盈利来源", "day_pnl": 5760.0},
                        {"symbol": "B.SZ", "name": "亏损来源", "day_pnl": -8700.0},
                    ],
                },
            },
            "active_plans": [],
        }

        result = build_today_workbench(
            workspace,
            now=datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        account = result["account_snapshot"]

        self.assertEqual(result["phase"], "weekend")
        self.assertEqual(result["review_trade_date"], "2026-07-31")
        self.assertEqual(account["daily_pnl"], 16361.0)
        self.assertEqual(account["peak_daily_pnl"], 35433.0)
        self.assertEqual(account["giveback_amount"], 19072.0)
        self.assertAlmostEqual(account["giveback_ratio"], 19072 / 35433)
        self.assertEqual(account["attribution"][0]["name"], "亏损来源")
        self.assertEqual(account["data_quality"], "ready")

    def test_after_close_missing_peak_stays_unknown(self) -> None:
        result = build_today_workbench(
            {
                "effective_market_date": "2026-07-31",
                "run_stage": "after_close",
                "portfolio_positions": [
                    {"symbol": "A.SZ", "name": "示例", "day_pnl": 120.0},
                    {"symbol": "B.SZ", "name": "缺口", "day_pnl": None},
                ],
                "active_plans": [],
            },
            now=datetime(2026, 7, 31, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        account = result["account_snapshot"]

        self.assertEqual(result["phase"], "after_close")
        self.assertIsNone(account["daily_pnl"])
        self.assertIsNone(account["peak_daily_pnl"])
        self.assertIsNone(account["giveback_amount"])
        self.assertEqual(account["data_quality"], "blocked")
        self.assertTrue(any("unknown" in item for item in account["gaps"]))

    def test_attention_unifies_positions_and_honest_empty_opportunity(self) -> None:
        evidence_id = "holding:A.SZ:technical"
        blocked = self._plan(
            symbol="A.SZ",
            name="阻断持仓",
            status="blocked",
            evidence_refs=[evidence_id],
            blocking_reasons=["行情口径待核对"],
        )
        ready = self._plan(
            symbol="B.SZ",
            name="待确认持仓",
            evidence_refs=["holding:B.SZ:technical"],
        )
        result = build_today_workbench(
            {
                "active_plans": [ready, blocked],
                "decision_evidence": {
                    "items": [
                        {
                            "evidence_id": evidence_id,
                            "claim": "技术数据口径不一致。",
                            "source_ref": "holding:A.SZ:completed_daily_bars",
                            "freshness": "blocked",
                            "counter_evidence": ["完成复权口径核对"],
                        },
                        {
                            "evidence_id": "holding:B.SZ:technical",
                            "claim": "收盘结构等待确认。",
                            "source_ref": "holding:B.SZ:completed_daily_bars",
                            "freshness": "ready",
                            "counter_evidence": ["跌破风险线"],
                        },
                    ]
                },
            }
        )
        items = result["attention_items"]

        self.assertEqual(items[0]["title"], "阻断持仓")
        self.assertEqual(items[0]["type"], "position")
        self.assertEqual(items[-1]["type"], "opportunity")
        self.assertEqual(items[-1]["title"], "暂无经证据验证的机会")
        self.assertIsNone(items[-1]["symbol"])

    def test_rule_state_machine_never_admits_unconfirmed_blocked_or_disabled(
        self,
    ) -> None:
        evidence = {
            "items": [
                {
                    "evidence_id": "holding:B.SZ:technical",
                    "claim": "完成日线证据就绪。",
                    "source_ref": "holding:B.SZ:completed_daily_bars",
                    "freshness": "ready",
                }
            ]
        }
        pending = self._plan(
            symbol="A.SZ",
            name="待确认",
            evidence_refs=["holding:B.SZ:technical"],
        )
        confirmed = self._plan(
            symbol="B.SZ",
            name="已确认",
            response="accepted",
            evidence_refs=["holding:B.SZ:technical"],
        )
        blocked = self._plan(
            symbol="C.SZ",
            name="被阻断",
            status="blocked",
            response="blocked_acknowledged",
            blocking_reasons=["数据异常"],
        )
        disabled = self._plan(
            symbol="D.SZ",
            name="暂不启用",
            response="disabled",
        )
        result = build_today_workbench(
            {
                "active_plans": [pending, confirmed, blocked, disabled],
                "decision_evidence": evidence,
            }
        )
        rules = {item["title"]: item for item in result["rules"]}

        self.assertFalse(rules["待确认"]["monitor_eligible"])
        self.assertTrue(rules["已确认"]["monitor_eligible"])
        self.assertFalse(rules["被阻断"]["monitor_eligible"])
        self.assertFalse(rules["暂不启用"]["monitor_eligible"])
        self.assertEqual(rules["被阻断"]["status"], "blocked")
        self.assertEqual(rules["暂不启用"]["status"], "disabled")

    def test_modification_request_cannot_reconfirm_stale_rule_version(self) -> None:
        result = build_today_workbench(
            {
                "active_plans": [
                    self._plan(
                        symbol="A.SZ",
                        name="修改中",
                        response="disputed",
                    )
                ]
            }
        )

        rule = result["rules"][0]
        requirement = result["decision_requirements"][0]
        self.assertEqual(rule["status"], "modification_requested")
        self.assertFalse(rule["monitor_eligible"])
        self.assertEqual(requirement["allowed_responses"], ["disabled"])
        self.assertIn("等待新规则版本", requirement["prompt"])


if __name__ == "__main__":
    unittest.main()
