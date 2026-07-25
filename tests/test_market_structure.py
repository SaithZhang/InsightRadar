from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from stock_assist.data_sources.iwencai_market import fetch_a_share_anchor_records
from stock_assist.market_structure import build_anchor_structure


class MarketStructureTests(unittest.TestCase):
    def test_builds_fixed_universe_breadth_and_equivalent_points(self) -> None:
        rows = [
            {"code": "000001.SZ", "name": "甲", "listing_date": "19910101", "return_rate": -0.50, "anchor_close": 10, "current_close": 5, "industry": "银行", "current_free_float_cap": 100},
            {"code": "000002.SZ", "name": "乙", "listing_date": "19920101", "return_rate": -0.20, "anchor_close": 10, "current_close": 8, "industry": "电子", "current_free_float_cap": 400},
            {"code": "000003.SZ", "name": "丙", "listing_date": "19930101", "return_rate": 0.10, "anchor_close": 10, "current_close": 11, "industry": "通信", "current_free_float_cap": 300},
            {"code": "000004.SZ", "name": "丁", "listing_date": "19940101", "return_rate": 0.20, "anchor_close": 10, "current_close": 12, "industry": "食品饮料", "current_free_float_cap": 200},
            {"code": "000005.SZ", "name": "新股", "listing_date": "20250101", "return_rate": 1.00, "anchor_close": 1, "current_close": 2, "industry": "电子", "current_free_float_cap": 500},
        ]
        result = build_anchor_structure(
            rows,
            anchor_date=date(2024, 9, 24),
            as_of=date(2026, 7, 17),
            benchmark_anchor_close=100,
            benchmark_current_close=160,
            min_rows=4,
            min_coverage=0.90,
            source="test",
            query="test query",
        )

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["eligible_count"], 4)
        self.assertEqual(result["returned_unique_count"], 5)
        self.assertEqual(result["post_anchor_listing_count"], 1)
        self.assertEqual(result["valid_count"], 4)
        self.assertEqual(result["below_anchor_count"], 2)
        self.assertEqual(result["below_anchor_ratio"], 0.5)
        self.assertEqual(result["equal_weight_return"], -0.1)
        self.assertEqual(result["equal_weight_equivalent_point"], 90.0)
        self.assertEqual(result["median_equivalent_point"], 95.0)
        self.assertEqual(result["benchmark_equal_weight_gap"], 0.7)
        self.assertEqual(result["claim_3900_status"], "not_supported")
        self.assertEqual(result["technology_definition"], ["电子", "计算机", "通信"])

    def test_missing_endpoint_data_keeps_claim_unverified(self) -> None:
        result = build_anchor_structure(
            [
                {"code": "000001.SZ", "listing_date": "19910101", "return_rate": -0.2, "anchor_close": 10, "current_close": 8},
                {"code": "000002.SZ", "listing_date": "19920101", "return_rate": None, "anchor_close": 10, "current_close": None},
            ],
            anchor_date=date(2024, 9, 24),
            as_of=date(2026, 7, 17),
            benchmark_anchor_close=2863.13,
            benchmark_current_close=3764.15,
            min_rows=2,
            min_coverage=0.90,
            source="test",
            query="test query",
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage_ratio"], 0.5)
        self.assertEqual(result["claim_3900_status"], "unverified")

    def test_iwencai_pagination_normalizes_forward_adjusted_interval_return(self) -> None:
        def response_for_page(query: str, *, limit: int, timeout: int, page: int = 1, call_type: str = "normal") -> dict[str, object]:
            self.assertIn("前复权区间涨跌幅", query)
            start = 0 if page == 1 else 50
            end = 50 if page == 1 else 51
            return {
                "code_count": 51,
                "datas": [
                    {
                        "股票代码": f"{index:06d}.SZ",
                        "股票简称": f"样本{index}",
                        "上市日期": "20000101",
                        "涨跌幅[20240924-20260717]": -25.0 if index == 50 else 10.0,
                        "收盘价[20240924]": 10,
                        "收盘价[20260717]": 7.5 if index == 50 else 11,
                        "所属申万一级行业": "电子",
                        "自由流通市值[20260717]": 1000 + index,
                    }
                    for index in range(start, end)
                ],
            }

        with patch("stock_assist.data_sources.iwencai_market._query_iwencai", side_effect=response_for_page) as mocked:
            rows, source, query = fetch_a_share_anchor_records(
                date(2024, 9, 24),
                date(2026, 7, 17),
                page_size=50,
                max_pages=3,
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(rows), 51)
        self.assertEqual(rows[-1]["return_rate"], -0.25)
        self.assertIn("同花顺问财", source)
        self.assertIn("2024年9月24日", query)


if __name__ == "__main__":
    unittest.main()
