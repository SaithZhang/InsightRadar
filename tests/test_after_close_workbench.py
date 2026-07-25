from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.after_close_workbench import (
    build_market_matrix_contract,
    build_workbench_view,
    plain_gap,
)
from stock_assist.after_close_workbench_html import (
    render_after_close_workbench,
)


class AfterCloseWorkbenchContractTests(unittest.TestCase):
    def test_matrix_has_two_semantic_groups_and_no_temperature_score(self) -> None:
        with TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            risk_path = report_dir / "20260723-risk-watch.json"
            risk_path.write_text(
                json.dumps(
                    {
                        "as_of": "2026-07-23",
                        "latest": {
                            "metrics": {
                                "star50": {
                                    "as_of": "2026-07-23",
                                    "day_return": -0.01,
                                    "return_5d": -0.03,
                                    "ma20_gap": -0.04,
                                }
                            }
                        },
                        "replay": {
                            "rows": [
                                {
                                    "date": f"2026-07-{day:02d}",
                                    "metrics": {
                                        "star50": {
                                            "close": 1000.0 + day,
                                            "ma20_gap": -0.04,
                                        }
                                    },
                                }
                                for day in range(1, 24)
                            ]
                        },
                        "macro_transmission": {
                            "authority": "diagnostic_only",
                            "energy_supply_shock": {"status": "observe"},
                            "duration_pressure": {"status": "unavailable"},
                            "series_30d": {
                                "brent": {
                                    "source": "https://example.test/brent",
                                    "as_of": "2026-07-22",
                                    "points": [
                                        {"date": "2026-07-21", "close": 80.0},
                                        {"date": "2026-07-22", "close": 82.0},
                                    ],
                                }
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            decision = {
                "source_reports": [
                    {
                        "workflow": "risk_watch",
                        "path": str(risk_path),
                        "as_of": "2026-07-23",
                    }
                ],
                "risk_budget": {"risk_level": "yellow"},
            }

            matrix = build_market_matrix_contract(
                decision,
                report_dir=report_dir,
                generated_at=datetime(2026, 7, 23, 16, 20),
            )

        self.assertEqual(
            [group["id"] for group in matrix["groups"]],
            ["risk_assets", "macro_pressure"],
        )
        cards = [
            card
            for group in matrix["groups"]
            for card in group["cards"]
        ]
        self.assertEqual(
            [card["id"] for card in cards],
            [
                "a_share_technology",
                "us_technology",
                "us_semiconductors",
                "korea",
                "japan",
                "crude_oil",
                "us_duration",
            ],
        )
        self.assertNotIn("score", cards[0])
        self.assertEqual(cards[0]["state_label"], "低于20日均线")
        self.assertEqual(cards[1]["freshness"], "unavailable")
        self.assertEqual(cards[5]["authority"], "diagnostic_only")

    def test_raw_provider_exception_becomes_plain_chinese(self) -> None:
        raw = (
            "HTTPSConnectionPool(host='query1.finance.yahoo.com', port=443): "
            "Read timed out. (read timeout=10.0)"
        )
        self.assertEqual(plain_gap(raw), "上游市场数据源超时")
        self.assertNotIn("HTTPSConnectionPool", plain_gap(raw))


class AfterCloseWorkbenchViewTests(unittest.TestCase):
    def test_view_uses_payload_holdings_not_markdown_broker_parser(self) -> None:
        payload = {
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 3,
                "decision_ready_holdings": 0,
            },
            "actions": [],
            "unified_decision": {
                "plan_date": "2026-07-24",
                "stance": "谨慎持有",
                "first_action": "未触发条件前不操作",
                "risk_budget": {
                    "risk_level": "yellow",
                    "risk_score": 49,
                },
                "holding_plans": [
                    {
                        "name": "沪电股份",
                        "code": "002463.SZ",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复126.12且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破112.27才考虑减仓",
                        "priority": "高",
                    },
                    {
                        "name": "中际旭创",
                        "code": "300308.SZ",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复1336.14且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破1040.34才考虑减仓",
                        "priority": "高",
                    },
                    {
                        "name": "中国人寿",
                        "code": "601628.SH",
                        "position_action": "继续持有",
                        "upside_trigger": "不追涨",
                        "flat_trigger": "继续持有",
                        "downside_trigger": "放量跌破38.45再减仓",
                        "priority": "中",
                    },
                ],
                "blocked_actions": ["持仓字段不完整"],
                "data_gaps": ["关键价位数据已过期"],
                "source_reports": [
                    {
                        "workflow": "market_levels",
                        "as_of": "2026-07-21",
                        "status": "current",
                    }
                ],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "groups": [],
                "portfolio_translation": "高Beta暂不加仓",
            },
            "sections": [],
            "signal_outcomes": {"horizons": {}},
            "data_gaps": [],
        }

        view = build_workbench_view(payload, "# 盘后持仓操作指引")

        self.assertEqual(view.holding_count, 3)
        self.assertEqual(view.decision_ready_text, "0/3")
        self.assertEqual(len(view.holdings), 3)
        self.assertEqual(view.holdings[0].name, "沪电股份")
        self.assertEqual(view.holdings[0].downside, "跌破112.27才考虑减仓")
        self.assertEqual(view.default_route, "today")
        market_levels = next(
            item for item in view.freshness if item.id == "market_levels"
        )
        self.assertEqual(market_levels.state, "stale")

    def test_view_translates_internal_status_and_raw_errors(self) -> None:
        payload = {
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 0,
                "decision_ready_holdings": 0,
            },
            "unified_decision": {
                "stance": "谨慎持有",
                "risk_budget": {"risk_level": "yellow", "risk_score": 49},
                "holding_plans": [],
                "blocked_actions": [],
                "data_gaps": [
                    "HTTPSConnectionPool(host='query1.finance.yahoo.com'): "
                    "Read timed out."
                ],
                "source_reports": [],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "groups": [],
                "portfolio_translation": "市场矩阵不改变当前计划",
            },
            "sections": [],
            "signal_outcomes": {},
            "data_gaps": [],
        }

        view = build_workbench_view(payload, "# 盘后持仓操作指引")

        self.assertEqual(view.risk_label, "黄灯")
        self.assertIn("上游市场数据源超时", view.gaps)
        self.assertFalse(
            any("HTTPSConnectionPool" in item for item in view.gaps)
        )


class AfterCloseWorkbenchHTMLTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "title": "盘后持仓操作指引",
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 1,
                "decision_ready_holdings": 0,
            },
            "unified_decision": {
                "plan_date": "2026-07-24",
                "stance": "谨慎持有",
                "first_action": "未触发条件前不操作",
                "risk_budget": {
                    "risk_level": "yellow",
                    "risk_score": 49,
                },
                "holding_plans": [
                    {
                        "name": "沪电股份",
                        "code": "002463.SZ",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复126.12且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破112.27才考虑减仓",
                        "priority": "高",
                    }
                ],
                "blocked_actions": ["持仓字段不完整"],
                "data_gaps": [],
                "source_reports": [],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "portfolio_translation": "高Beta暂不加仓",
                "groups": [
                    {
                        "id": "risk_assets",
                        "label": "全球科技与风险资产",
                        "cards": [
                            {
                                "group": "risk_assets",
                                "id": "a_share_technology",
                                "label": "A股科技",
                                "state": "below_ma20",
                                "state_label": "低于20日均线",
                                "day_change": -0.01,
                                "as_of": "2026-07-23",
                                "freshness": "fresh",
                                "source": "risk-watch",
                                "points": [
                                    {"date": "2026-07-22", "close": 1000.0},
                                    {"date": "2026-07-23", "close": 990.0},
                                ],
                                "authority": "diagnostic_only",
                                "gap": None,
                            }
                        ],
                    },
                    {
                        "id": "macro_pressure",
                        "label": "宏观压力",
                        "cards": [],
                    },
                ],
            },
            "sections": [],
            "signal_outcomes": {},
            "data_gaps": [],
        }

    def test_html_is_market_permission_first_and_has_file_safe_routes(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertIn('data-route="today"', html)
        self.assertIn('id="today"', html)
        self.assertIn('id="portfolio"', html)
        self.assertLess(html.index("市场约束"), html.index("优先处理"))
        self.assertIn("A股科技", html)
        self.assertIn("location.hash", html)
        self.assertNotIn("0 / 100", html)

    def test_html_has_no_external_asset_or_simulated_chart(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=", html)
        self.assertNotIn("<svg", html)

    def test_html_has_four_task_interfaces_and_rule_playbook_first(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        for route in ("today", "portfolio", "lookup", "review"):
            self.assertIn(f'id="{route}"', html)
            self.assertIn(f'data-view="{route}"', html)
            self.assertIn(f'data-route="{route}"', html)
        self.assertNotIn('id="route-holdings"', html)
        self.assertNotIn('id="route-market"', html)
        self.assertIn("IF", html)
        self.assertIn("THEN", html)
        self.assertIn("UNTIL", html)
        self.assertIn("INVALID", html)
        self.assertIn("确认已知悉阻断", html)
        self.assertNotIn("采纳为今日计划", html)
        self.assertIn("提出异议", html)
        self.assertIn("后验统计成熟度", html)

    def test_html_matches_v3_shell_without_copying_prototype_market_values(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertIn("grid-template-columns:228px minmax(0,1fr)", html)
        self.assertIn("max-width:1340px", html)
        self.assertIn('class="panel runtime-strip"', html)
        self.assertIn('class="panel market-gate"', html)
        self.assertIn('class="today-layout"', html)
        self.assertIn('class="side-stack"', html)
        self.assertIn("Rule-first decision intelligence", html)
        self.assertIn('class="chart-empty"', html)
        self.assertIn("技术图表尚未接入此 P0 页面", html)
        self.assertNotIn("示意技术结构图", html)
        self.assertNotIn("33 / 100", html)

    def test_normal_ui_does_not_show_raw_provider_exception(self) -> None:
        payload = self._payload()
        payload["unified_decision"]["data_gaps"] = [
            "HTTPSConnectionPool(host='query1.finance.yahoo.com'): Read timed out."
        ]

        html = render_after_close_workbench(
            payload,
            "# 盘后持仓操作指引",
        )

        self.assertNotIn("HTTPSConnectionPool", html)
        self.assertIn("旧版 payload", html)

    def test_portfolio_import_controls_remain_local_and_explicit(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertIn('href="/portfolio-import"', html)
        self.assertIn("__LOCAL_SESSION_TOKEN__", html)
        self.assertNotIn("showSaveFilePicker", html)


if __name__ == "__main__":
    unittest.main()
