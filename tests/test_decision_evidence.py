from __future__ import annotations

import unittest

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.decision_evidence import (
    build_decision_evidence,
    link_evidence_to_plans,
)


class DecisionEvidenceTests(unittest.TestCase):
    def test_source_health_is_joined_by_source_name_not_list_position(self) -> None:
        decision = {
            "stance": "防守观察",
            "confidence": "中低",
            "style_rotation": {
                "relative_strength": {
                    "technology_growth": {"5d": -0.08, "20d": -0.16},
                    "high_dividend": {"5d": 0.05, "20d": 0.14},
                }
            },
            "evidence_effects": [
                {
                    "source": "style-rotation",
                    "as_of": "2026-07-30",
                    "state": "高股息领先，科技成长走弱",
                    "effect": "风格只提供相对强弱，不授权切换持仓。",
                },
                {
                    "source": "ai-capex-watch",
                    "as_of": "2026-07-28",
                    "state": "产业逻辑获支持，供应商兑现未闭环",
                    "effect": "不能授权追涨。",
                },
            ],
        }
        health = [
            {
                "source_name": "ai_capex_watch",
                "status": "stale",
                "source_time": "2026-07-28",
                "gap_reason": "超过1日新鲜度窗口",
            },
            {
                "source_name": "style_rotation",
                "status": "ready",
                "source_time": "2026-07-30",
                "gap_reason": None,
            },
        ]
        plans = [{"plan_id": "holding:900001.SH", "symbol": "900001.SH"}]

        evidence = build_decision_evidence(decision, health, plans)
        items = {
            item["source_ref"]: item
            for item in evidence["items"]
        }

        self.assertEqual(items["style-rotation"]["freshness"], "ready")
        self.assertEqual(items["ai-capex-watch"]["freshness"], "stale")
        self.assertEqual(
            items["ai-capex-watch"]["gaps"],
            [
                "超过1日新鲜度窗口",
                "产业证据尚未提供到具体持仓的官方映射。",
            ],
        )
        self.assertEqual(items["ai-capex-watch"]["linked_plan_ids"], [])
        self.assertEqual(items["ai-capex-watch"]["authority"], "diagnostic_only")
        conclusion = evidence["conclusion"]
        self.assertEqual(conclusion["technology_stance"], "科技偏弱，等待修复")
        self.assertEqual(conclusion["dividend_stance"], "红利相对占优")

    def test_holding_evidence_links_to_its_plan_by_stable_id(self) -> None:
        plans = [
            {
                "plan_id": "holding:900001.SH",
                "symbol": "900001.SH",
                "current_action": "降低仓位复核",
                "then_action": "修复后观察",
                "technical_snapshot": {
                    "state": "weak",
                    "as_of": "2026-07-30",
                    "close": 96.0,
                    "ma20": 102.3,
                    "support_20d": 95.0,
                    "resistance_20d": 112.0,
                    "ma20_slope_5d": -0.03,
                    "change_5d": -0.08,
                },
                "evidence_refs": ["wrong:list-position"],
            }
        ]

        evidence = build_decision_evidence({}, [], plans)
        link_evidence_to_plans(plans, evidence)

        self.assertIn(
            "holding:900001.SH:technical",
            plans[0]["evidence_refs"],
        )
        self.assertNotIn("wrong:list-position", plans[0]["evidence_refs"])
        item = next(
            row
            for row in evidence["items"]
            if row["evidence_id"] == "holding:900001.SH:technical"
        )
        self.assertEqual(
            item["linked_plan_ids"],
            ["holding:900001.SH"],
        )
        self.assertIn("MA20", item["claim"])
        self.assertEqual(item["plan_impact"], "降低仓位复核")

    def test_workbench_separates_decision_evidence_from_source_health(self) -> None:
        workspace = {
            "schema_version": "decision-workspace/v1",
            "generated_at": "2026-07-30T20:00:00",
            "source_generated_at": "2026-07-30T20:00:00",
            "run_stage": "after_close",
            "runtime_status": "reviewed",
            "market_gate": {"permission": "防守观察"},
            "portfolio_summary": {"holding_count": 0},
            "portfolio_positions": [],
            "plan_changes": [],
            "today_plans": [],
            "active_plans": [],
            "data_health": [
                {
                    "label": "产业研究",
                    "source_name": "ai_capex_watch",
                    "status": "stale",
                    "source_time": "2026-07-28",
                    "fetched_at": "2026-07-30T20:00:00",
                    "freshness_rule": "1日",
                    "gap_reason": "超过新鲜度窗口",
                }
            ],
            "decision_evidence": {
                "conclusion": {
                    "overall_stance": "防守观察",
                    "confidence": "中低",
                    "technology_stance": "科技偏弱，等待修复",
                    "dividend_stance": "红利相对占优",
                    "headline": "今日科技看修复，红利看震荡偏强。",
                    "top_reasons": [
                        {
                            "claim": "产业逻辑获支持，供应商兑现未闭环",
                            "plan_impact": "不能授权追涨",
                        }
                    ],
                    "counter_evidence": ["订单和现金流尚未闭环"],
                    "invalidation": ["科技重新取得相对强势后复核"],
                },
                "items": [
                    {
                        "evidence_id": "industry:ai",
                        "scope": "industry",
                        "fact_class": "fact_with_rule_inference",
                        "claim": "产业逻辑获支持，供应商兑现未闭环",
                        "change": "资本开支继续增长",
                        "plan_impact": "不能授权追涨",
                        "source_ref": "ai-capex-watch",
                        "source_time": "2026-07-28",
                        "freshness": "stale",
                        "supports": ["overall:defensive"],
                        "opposes": ["overall:increase_risk"],
                        "counter_evidence": ["公司订单未知"],
                        "gaps": ["超过新鲜度窗口"],
                        "authority": "rule_input",
                        "linked_plan_ids": [],
                    }
                ],
            },
            "research_tasks": [],
            "user_responses": [],
            "plan_version_history": [],
            "outcome_summary": {},
        }

        html = render_after_close_workbench(
            {"decision_workspace": workspace},
            "",
        )

        self.assertIn('id="evidence-backdrop"', html)
        self.assertIn('id="data-backdrop"', html)
        self.assertIn("今日科技看修复，红利看震荡偏强。", html)
        self.assertIn("如何影响计划", html)
        self.assertIn("来源可用性请在“数据状态”查看", html)
        self.assertIn("Source Health / Repair", html)


if __name__ == "__main__":
    unittest.main()
