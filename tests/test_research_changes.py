from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import unittest

from stock_assist.research_changes import evaluate_change


NOW = datetime.fromisoformat("2026-11-07T02:00:00+08:00")


def sample() -> dict:
    return {
        "schema": 1, "symbol": "900001", "as_of": NOW.isoformat(), "mode": "live_review",
        "scope": "合成样例，仅比较两项同期财务指标",
        "thesis": {"text": "合成研究理由：盈利增长伴随回款", "as_of": "2026-10-01", "url": "https://example.com/thesis"},
        "holding": {"as_of": "2026-11-06", "url": "https://example.com/holding"},
        "coverage": {"status": "complete", "checked_at": NOW.isoformat(), "note": "合成财报中的两项指标均已读取"},
        "sources": [{"id": "report", "title": "合成三季报", "url": "https://example.com/report.pdf",
                     "published_at": "2026-10-30", "page": 2,
                     "text": "归母净利润 本期 1,200.25 上年同期 1,000.25。经营现金流 本期 80.50 上年同期 100.50。公司认为回款具有季节性。"}],
        "metrics": {
            "net_profit": {"current": "1200.25", "previous": "1000.25", "unit": "元", "period": "2026-01-01/2026-09-30",
                           "comparison_period": "2025-01-01/2025-09-30", "source_id": "report", "quote": "归母净利润 本期 1,200.25 上年同期 1,000.25"},
            "operating_cash_flow": {"current": "80.50", "previous": "100.50", "unit": "元", "period": "2026-01-01/2026-09-30",
                                    "comparison_period": "2025-01-01/2025-09-30", "source_id": "report", "quote": "经营现金流 本期 80.50 上年同期 100.50"},
        },
        "explanation": {"text": "公司解释具有季节性，需核对历史季度", "source_id": "report", "quote": "公司认为回款具有季节性"},
    }


def set_cashflow(payload: dict, current: str, previous: str) -> None:
    metric = payload["metrics"]["operating_cash_flow"]
    old = metric["quote"]
    metric.update(current=current, previous=previous, quote=f"经营现金流 本期 {current} 上年同期 {previous}")
    payload["sources"][0]["text"] = payload["sources"][0]["text"].replace(old, metric["quote"])


class ChangeTests(unittest.TestCase):
    def evaluate(self, payload=None):
        return evaluate_change(sample() if payload is None else payload, current_time=NOW)

    def test_declining_cashflow_keeps_positive_profit_and_counter_explanation(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "needs_review")
        self.assertGreater(result["metrics"]["net_profit"]["yoy_pct"], 0)
        self.assertLess(result["metrics"]["operating_cash_flow"]["yoy_pct"], 0)
        self.assertIn("季节性", result["explanation"]["quote"])
        self.assertEqual(result["metrics"]["operating_cash_flow"]["delta"], "-20.00")
        self.assertEqual(result["trade_authority"], "none")
        self.assertEqual(result["rule_origin"], "engineering_review_rule")

    def test_unchanged_financials_are_scoped_to_supplied_reports(self):
        payload = sample()
        set_cashflow(payload, "100.50", "100.50")
        result = self.evaluate(payload)
        self.assertEqual(result["status"], "no_material_change")
        self.assertEqual(result["status_label"], "无实质变化（本次核验范围）")
        self.assertIn("完整投资理由仍需人工判断", result["rule_text"])

    def test_missing_evidence_returns_coverage_state_without_financial_facts(self):
        payload = sample()
        payload.update(sources=[], metrics={}, mode="missing_source_validation")
        payload.pop("explanation")
        payload["coverage"]["status"] = "unavailable"
        result = self.evaluate(payload)
        self.assertEqual(result["status"], "insufficient_coverage")
        self.assertEqual(result["metrics"], {})
        self.assertEqual(result["basis"], [])
        self.assertEqual(result["mode_label"], "缺源场景验证")

    def test_partial_stale_or_missing_metric_prevents_no_change(self):
        for defect in ("partial", "stale", "missing_metric"):
            with self.subTest(defect=defect):
                payload = sample()
                set_cashflow(payload, "100.50", "100.50")
                if defect == "partial":
                    payload["coverage"]["status"] = "partial"
                elif defect == "stale":
                    payload["coverage"]["checked_at"] = "2026-11-05T01:00:00+08:00"
                else:
                    payload["metrics"].pop("net_profit")
                self.assertEqual(self.evaluate(payload)["status"], "insufficient_coverage")

    def test_negative_or_zero_baseline_has_no_misleading_growth_rate(self):
        for current, previous, status in (("-20", "-100", "needs_review"), ("20", "0", "no_material_change")):
            with self.subTest(previous=previous):
                payload = sample()
                set_cashflow(payload, current, previous)
                result = self.evaluate(payload)
                self.assertIsNone(result["metrics"]["operating_cash_flow"]["yoy_pct"])
                self.assertEqual(result["status"], status)

    def test_profit_decline_alone_requires_review(self):
        payload = sample()
        set_cashflow(payload, "150", "100")
        payload["metrics"]["net_profit"]["current"] = "1000.25"
        payload["metrics"]["net_profit"]["previous"] = "1200.25"
        self.assertEqual(self.evaluate(payload)["status"], "needs_review")

    def test_stable_fingerprint_and_input_immutability(self):
        payload = sample()
        original = deepcopy(payload)
        result = self.evaluate(payload)
        self.assertEqual(payload, original)
        self.assertEqual(result["fingerprint"], self.evaluate(payload)["fingerprint"])
        payload["thesis"]["text"] += "（修订）"
        self.assertNotEqual(result["fingerprint"], self.evaluate(payload)["fingerprint"])

    def test_historical_mode_is_prominent_and_missing_source_mode_needs_gap(self):
        payload = sample()
        payload["mode"] = "historical_validation"
        self.assertEqual(self.evaluate(payload)["mode_label"], "历史材料验证")
        payload["mode"] = "missing_source_validation"
        with self.assertRaisesRegex(ValueError, "实际覆盖缺口"):
            self.evaluate(payload)

    def test_invalid_numbers_are_rejected(self):
        for value in (True, float("nan"), float("inf"), "NaN", "Infinity", [], "1e100", "1e-999999999", "1e999999999"):
            with self.subTest(value=value):
                payload = sample()
                payload["metrics"]["net_profit"]["current"] = value
                with self.assertRaises(ValueError):
                    self.evaluate(payload)

    def test_unquoted_amount_and_substring_amount_are_rejected(self):
        for value in ("999.00", "100", "200.25"):
            with self.subTest(value=value):
                payload = sample()
                payload["metrics"]["net_profit"]["current"] = value
                with self.assertRaisesRegex(ValueError, "完整出现在引用摘句"):
                    self.evaluate(payload)

    def test_exact_citations_and_safe_source_urls(self):
        for defect in ("missing_id", "invented_quote", "duplicate_id", "bad_url", "credentials"):
            with self.subTest(defect=defect):
                payload = sample()
                if defect == "missing_id":
                    payload["metrics"]["net_profit"]["source_id"] = "missing"
                elif defect == "invented_quote":
                    payload["explanation"]["quote"] = "原文没有这句话"
                elif defect == "duplicate_id":
                    payload["sources"].append(deepcopy(payload["sources"][0]))
                else:
                    payload["sources"][0]["url"] = "javascript:alert(1)" if defect == "bad_url" else "https://secret:token@example.com"
                with self.assertRaises(ValueError):
                    self.evaluate(payload)

    def test_whitespace_and_grouping_commas_do_not_break_citation(self):
        payload = sample()
        payload["metrics"]["net_profit"]["quote"] = "归母净利润\n本期1200.25上年同期1000.25"
        self.assertEqual(self.evaluate(payload)["status"], "needs_review")

    def test_financial_table_keeps_neighboring_amounts_separate(self):
        payload = sample()
        quote = "归母净利润 1,200.25 1,000.25 1,000.25 20.00%"
        old = payload["metrics"]["net_profit"]["quote"]
        payload["sources"][0]["text"] = payload["sources"][0]["text"].replace(old, quote)
        payload["metrics"]["net_profit"]["quote"] = quote
        result = self.evaluate(payload)
        self.assertEqual(result["metrics"]["net_profit"]["current"], "1200.25")
        self.assertEqual(result["metrics"]["net_profit"]["previous"], "1000.25")
        payload["metrics"]["net_profit"]["current"] = "200.25"
        with self.assertRaisesRegex(ValueError, "完整出现在引用摘句"):
            self.evaluate(payload)

    def test_future_naive_and_invalid_dates_are_rejected(self):
        mutations = [
            ("as_of", "2026-11-07T03:00:00+08:00"),
            ("as_of", "2026-11-07T02:00:00"),
            ("checked_at", "2026-11-07T03:00:00+08:00"),
            ("published_at", "2026-11-08"),
            ("thesis", "2026-11-08"),
            ("holding", "2026-11-08"),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                payload = sample()
                if field == "as_of":
                    payload[field] = value
                elif field == "checked_at":
                    payload["coverage"][field] = value
                elif field == "published_at":
                    payload["sources"][0][field] = value
                else:
                    payload[field]["as_of"] = value
                with self.assertRaises(ValueError):
                    self.evaluate(payload)

    def test_period_mismatch_and_preperiod_publication_are_rejected(self):
        mutations = [
            ("period", "2026-07-01/2026-09-30"),
            ("comparison_period", "2024-01-01/2024-09-30"),
            ("unit", "万元"),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                payload = sample()
                payload["metrics"]["net_profit"][field] = value
                with self.assertRaises(ValueError):
                    self.evaluate(payload)
        payload = sample()
        payload["sources"][0]["published_at"] = "2026-08-01"
        with self.assertRaisesRegex(ValueError, "早于财务期间"):
            self.evaluate(payload)

    def test_invalid_structure_and_state_are_rejected(self):
        for field, value in (("schema", True), ("symbol", "SH900001"), ("mode", "buy"), ("mode", {}), ("sources", {}), ("metrics", [])):
            with self.subTest(field=field):
                payload = sample()
                payload[field] = value
                with self.assertRaises(ValueError):
                    self.evaluate(payload)
        payload = sample()
        payload["coverage"]["status"] = []
        with self.assertRaises(ValueError):
            self.evaluate(payload)


if __name__ == "__main__":
    unittest.main()
