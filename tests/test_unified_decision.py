from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.unified_decision import (
    build_unified_decision,
    inject_unified_decision,
    render_unified_decision_markdown,
)
from stock_assist.reports import (
    _battle_timeline,
    _operator_strip,
    _parse_broker_holdings,
    _parse_unified_brief,
    _regime_gauges,
    _signal_panel,
    markdown_report_to_html,
)


ACTIONS = [
    {
        "name": "中际旭创（300308.SZ）",
        "code": "300308.SZ",
        "action": "持有但不加仓",
        "position_action": "不加仓；等重新站回20日线后再提高信心。",
        "upside_trigger": "若放量站回20日线1187.29上方，继续持有观察。",
        "downside_trigger": "若跌破950.08或板块明显转弱，先降1/4仓位。",
        "flat_trigger": "若在20日线下方震荡，保持仓位不动。",
        "priority": "中",
    }
]

RELIABILITY = {
    "decision_ready_coverage": 0.0,
    "holding_count": 1,
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class UnifiedDecisionTests(unittest.TestCase):
    def test_red_risk_merges_state_team_and_industry_into_tomorrow_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            _write_json(
                report_dir / "20260719-153506-risk-watch.json",
                {
                    "workflow": "risk-watch",
                    "generated_at": "2026-07-19T15:35:06",
                    "as_of": "2026-07-17",
                    "profile": {"total_exposure_pct": 20.0, "high_beta_exposure_pct": 20.0},
                    "latest": {
                        "date": "2026-07-17",
                        "level": "red",
                        "level_label": "红灯",
                        "score": 76,
                        "active_families": 5,
                        "risk_budget": {"total_exposure_cap_pct": 30, "high_beta_cap_pct": 15},
                        "metrics": {
                            "all_a": {
                                "day_return": -0.0456,
                                "return_20d": -0.1176,
                                "drawdown_20d": -0.1233,
                                "ma20_gap": -0.0796,
                                "vol20_ratio": 1.3819,
                            },
                            "chinext": {"ma20_gap": -0.1460},
                            "star50": {"ma20_gap": -0.1457},
                            "csi1000": {"ma20_gap": -0.1417},
                        },
                    },
                    "crowding_snapshot": {
                        "top20_amount_share": 0.1473,
                        "top1_turnover_free_float": 0.0699,
                        "top1_amount_share": 0.0211,
                    },
                    "anchor_structure": {
                        "as_of": "2026-07-17",
                        "anchor_date": "2024-09-24",
                        "status": "verified",
                        "eligible_count": 5299,
                        "valid_count": 5299,
                        "coverage_ratio": 1.0,
                        "below_anchor_count": 925,
                        "below_anchor_ratio": 0.1746,
                        "claim_3900_status": "not_supported",
                        "equal_weight_return": 0.7675,
                        "median_return": 0.3431,
                        "benchmark_return": 0.3147,
                        "benchmark_current_close": 3764.15,
                        "equal_weight_equivalent_point": 5060.68,
                        "median_equivalent_point": 3845.54,
                        "benchmark_equal_weight_gap": -0.4528,
                        "technology_definition": ["电子", "通信", "计算机"],
                        "health_score": 78,
                        "health_label": "多数显著高于锚点",
                    },
                    "actions": ["暂停新增高β和追涨。"],
                },
            )
            _write_json(
                report_dir / "20260719-153523-market-pulse.json",
                {
                    "workflow": "market-pulse",
                    "generated_at": "2026-07-19T15:35:23",
                    "analysis": {"verdict": "方向不清", "action_bias": "等待确认。"},
                    "state_team_etf_proxy": {
                        "as_of": "2026-07-17",
                        "change_signal": "短期回补、近20次仍净收缩",
                        "minimum_exit_ratio": 0.7764,
                        "recent_changes": {
                            "five_observations": {"change_pct": 17.88},
                            "twenty_observations": {"change_pct": -33.38},
                        },
                    },
                },
            )
            _write_json(
                report_dir / "20260719-153530-market-levels.json",
                {
                    "workflow": "market-levels",
                    "generated_at": "2026-07-19T15:35:30",
                    "analysis": {
                        "verdict": "弱势中的支撑试探",
                        "weak_timeframes": 6,
                        "confluence_zone": {"lower": 3742, "upper": 3770},
                        "confirmation_zone": {"lower": 3790, "upper": 3826},
                        "conditions": ["守住支撑只按弱反弹处理。", "有效跌破3742且不能收回。", "站稳3790-3826。"],
                    },
                    "timeframes": [
                        {"timeframe": "day", "as_of": "2026-07-17", "latest": 3764.15, "resistance_zones": [{"lower": 3944, "upper": 3980}]},
                        {"timeframe": "week", "resistance_zones": [{"lower": 3863, "upper": 3913}]},
                    ],
                },
            )
            _write_json(
                report_dir / "20260719-153524-ai-capex-watch.json",
                {
                    "workflow": "ai-capex-watch",
                    "generated_at": "2026-07-19T15:35:24",
                    "as_of": "2026-07-19",
                    "conclusion": "产业逻辑获支持，不构成追涨依据。",
                    "metrics": [{"key": "supplier_realization", "state": "pending"}],
                },
            )

            decision = build_unified_decision(
                ACTIONS,
                RELIABILITY,
                report_dir=report_dir,
                now=datetime(2026, 7, 19, 16, 0),
            )

        self.assertEqual(decision["plan_date"], "2026-07-20")
        self.assertEqual(decision["stance"], "防守观察")
        self.assertEqual(decision["confidence"], "中低")
        self.assertEqual(decision["risk_budget"]["high_beta_over_cap_pct"], 5.0)
        self.assertEqual(decision["market_regime"]["bear_bull_score"], 2.0)
        self.assertEqual(decision["market_regime"]["regime_label"], "熊市风险开启")
        self.assertEqual(decision["market_structure"]["below_anchor_count"], 925)
        self.assertEqual(decision["market_structure"]["claim_3900_status"], "not_supported")
        self.assertIsInstance(decision["market_regime"]["fear_greed_score"], int)
        self.assertIsInstance(decision["market_regime"]["crowding_score"], int)
        self.assertEqual(decision["market_levels"]["support_zone"], {"lower": 3742.0, "upper": 3770.0})
        self.assertEqual(len(decision["tomorrow_watchlist"]), 4)
        self.assertIn("不新增高β仓位", decision["first_action"])
        self.assertIn("降低约25%", decision["first_action"])
        self.assertIn("跌破950.08", decision["first_action"])
        self.assertEqual(len(decision["scenario_plan"]), 4)
        self.assertTrue(any("国家队ETF短期回补" in item for item in decision["blocked_actions"]))
        self.assertTrue(any("供应商业绩兑现" in item for item in decision["blocked_actions"]))
        self.assertTrue(any(item["status"] == "current" for item in decision["source_reports"]))
        self.assertEqual(len(decision["source_reports"]), 5)

    def test_missing_monitor_reports_fail_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            decision = build_unified_decision(
                ACTIONS,
                RELIABILITY,
                report_dir=Path(tmp),
                now=datetime(2026, 7, 19, 16, 0),
            )

        self.assertEqual(decision["stance"], "等待确认")
        self.assertEqual(decision["confidence"], "低")
        self.assertIn("风险预算未确认前不新增仓位", decision["first_action"])
        self.assertTrue(any("风险预算缺失" in item for item in decision["blocked_actions"]))
        self.assertEqual({item["status"] for item in decision["source_reports"]}, {"missing"})

    def test_markdown_is_injected_before_optional_extensions(self) -> None:
        decision = {
            "plan_date": "2026-07-20",
            "stance": "防守观察",
            "confidence": "中低",
            "first_action": "不加仓；未触发下行条件时保持不动。",
            "risk_budget": {
                "risk_label": "红灯",
                "total_exposure_pct": 20,
                "total_exposure_cap_pct": 30,
                "high_beta_exposure_pct": 20,
                "high_beta_cap_pct": 15,
            },
            "scenario_plan": [
                {"scenario": "低开或走弱", "trigger": "跌破950.08", "action": "先降1/4仓位。"}
            ],
            "blocked_actions": ["新增高β。"],
            "unlock_conditions": ["站回MA20。"],
            "evidence_effects": [],
            "data_gaps": [],
        }
        base = "# 盘后持仓操作指引\n\n## 数据缺口\n- 暂无\n\n## 可选扩展缺口\n- 暂无"

        section = render_unified_decision_markdown(decision)
        merged = inject_unified_decision(base, decision)

        self.assertIn("## 明日统一指引", section)
        self.assertIn("跌破950.08", section)
        self.assertLess(merged.index("## 明日统一指引"), merged.index("## 可选扩展缺口"))

    def test_dashboard_preserves_holding_with_unknown_broker_fields_and_red_budget(self) -> None:
        markdown = """# 盘后持仓操作指引

## 明日统一指引
- 总体姿态：防守观察（置信度：中低）
- 第一动作：不新增高β仓位。
- 风险预算：红灯；总仓位 20.0% / 上限 30.0%；高β 20.0% / 上限 15.0%。

## 券商持仓快照
- 中际旭创：仓位 20.00％，成本 未提供，市价 未提供，总盈亏 未提供，当日 未提供，市值 100000。
"""

        holdings = _parse_broker_holdings(markdown)
        unified = _parse_unified_brief(markdown)
        signal_html = _signal_panel(1, 0, 0, 0, 0, unified.get("risk_label", ""))

        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["weight_pct"], 20.0)
        self.assertIsNone(holdings[0]["pnl_pct"])
        self.assertEqual(holdings[0]["market_value"], 100000.0)
        self.assertEqual(unified["risk_label"], "红灯")
        self.assertIn("红灯", signal_html)
        self.assertIn("统一风险预算", signal_html)

    def test_regime_gauges_level_ladder_and_local_import_are_rendered(self) -> None:
        markdown = """# 盘后持仓操作指引

## 明日统一指引
- 总体姿态：防守观察（置信度：中低）
- 第一动作：不新增高β仓位。
- 评分截至：2026-07-17；口径：诊断性合成，未回测校准。
- 熊牛评分：2.0/10（熊市风险开启；未回测校准）
- 恐慌贪婪：18/100（极度恐慌）
- 拥挤度：49/100（中性；绝对阈值诊断）

### 市场宽度与指数失真
- 锚点累计宽度：78/100（多数显著高于锚点；verified；不代表当前短线趋势）。
- 低于锚点：925/5299（17.5%；覆盖率 100.0%）。
- 等权等效上证：5060.68；中位数股票等效：3845.54；官方上证：3764.15。
- 指数偏离：官方区间 31.5%，固定股票池等权 76.8%，差 -45.3%。
- 3900只审计：同口径不支持3900只；科技定义 电子,通信,计算机。

### 大盘点位与状态切换
- 当前点位：3764.15；结构：弱势中的支撑试探。
- 生死支撑：3742-3770；跌破且不能收回继续防守。
- 第一确认：3790-3826；站稳后才上调反弹级别。
- 较强压力：3863-3913。
- 日线修复：3944-3980；配合宽度改善。

## 持仓动作
### 中际旭创（300308.SZ）
- 建议动作：持有但不加仓

## 券商持仓快照
- 中际旭创：仓位 20.00％，成本 未提供，市价 未提供，总盈亏 未提供，当日 未提供，市值 100000。
"""
        unified = _parse_unified_brief(markdown)
        gauges = _regime_gauges(unified)
        html = markdown_report_to_html(markdown)

        self.assertEqual(unified["support_zone"], "3742-3770")
        self.assertIn("熊市风险开启", gauges)
        self.assertIn("上证状态切换阶梯", gauges)
        self.assertIn("市场宽度与指数失真", gauges)
        self.assertIn("925/5299", unified["below_anchor"])
        self.assertIn("同口径不支持3900只", gauges)
        self.assertIn("portfolio-import-open", html)
        self.assertNotIn("showSaveFilePicker", html)
        self.assertIn("InsightRadar.cmd", html)
        self.assertIn("打开 InsightRadar 导入页", html)
        self.assertIn("127.0.0.1:8765", html)
        self.assertIn("数据只在本机浏览器中解析", html)

    def test_operator_strip_and_four_exact_timeline_windows_are_first_screen_components(self) -> None:
        markdown = """# 盘后持仓操作指引

## 核心可靠性
- 结构化动作覆盖 1/1；严格决策就绪 0/1。

## 明日统一指引
- 总体姿态：防守观察（置信度：中低）
- 第一动作：不新增高β。
- 评分截至：2026-07-17；口径：确定性状态机。
- 熊牛评分：2.0/10（正式分；熊市风险开启）
- 评分变化：上一正式分 2.0；当前正式分 2.0；盘中候选分 2.0；正式变化 0；候选变化 0。

### 大盘点位与状态切换
- 当前点位：3764.15；market_level_state：support_testing；结构：支撑试探。
- 生死支撑：3742-3770；现价3764.15，区间内；动作：只按止跌。
- 第一确认：3790-3826；现价3764.15，位于区间下方；动作：不追涨。
- 较强压力：3863-3913；现价3764.15，位于区间下方；动作：等待收盘。
- 失效预案：15分钟跌破3742且下一根不能收回。

### 四时点作战时间轴
- 开盘前｜观察：隔夜风险｜当前：等待观察｜动作：弱=不新增；强=沿用；混合=等待
- 9:30–10:00｜观察：支撑｜当前：support_testing｜动作：弱=候选-1；强=止跌；混合=等待
- 11:20–11:30｜观察：确认区与宽度｜当前：等待观察｜动作：弱=保持；强=候选+1；混合=冲突0
- 14:45–15:00｜观察：收盘确认｜当前：finalized｜动作：弱=正式-1；强=正式+1；混合=维持
"""
        unified = _parse_unified_brief(markdown)
        strip = _operator_strip(markdown, unified, 1)
        timeline = _battle_timeline(markdown)
        html = markdown_report_to_html(markdown)

        self.assertIn("当前熊牛分", strip)
        self.assertIn("2.0/10", strip)
        self.assertIn("严格决策就绪", markdown)
        for window in ("开盘前", "9:30–10:00", "11:20–11:30", "14:45–15:00"):
            self.assertIn(window, timeline)
        self.assertIn("operator-strip", html)
        self.assertIn("battle-timeline", html)


if __name__ == "__main__":
    unittest.main()
