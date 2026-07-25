from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import unittest

from stock_assist.data_sources.eastmoney_klines import Candle
from stock_assist.style_rotation import build_style_rotation_matrix


CONFIG = json.loads((Path(__file__).parents[1] / "configs" / "style_rotation.json").read_text(encoding="utf-8"))


def candles(daily_return: float, *, last_jump: float = 0.0, amount_last: float = 100.0) -> list[Candle]:
    start = date(2026, 1, 1)
    close = 100.0
    rows: list[Candle] = []
    for index in range(100):
        close *= 1 + daily_return
        if last_jump and index >= 95:
            close *= 1 + last_jump
        amount = amount_last if index == 99 else 100.0
        rows.append(Candle(datetime.combine(start + timedelta(days=index), datetime.min.time()), close, close, close, close, 1000, amount))
    return rows


def complete_series(*, conflict: bool = False) -> dict[str, list[Candle]]:
    result = {"510300.SH": candles(0.0008)}
    for style in CONFIG["styles"]:
        for member in style["members"]:
            if style["key"] == "large_financials":
                result[member["code"]] = candles(0.0020, amount_last=400.0)
            elif style["key"] == "high_dividend":
                result[member["code"]] = candles(0.0012)
            else:
                result[member["code"]] = candles(0.0001, last_jump=0.002 if conflict else 0.0)
    return result


class StyleRotationTests(unittest.TestCase):
    def test_fixed_three_style_definitions_and_multi_horizon_metrics(self) -> None:
        matrix = build_style_rotation_matrix(CONFIG, complete_series(), as_of=date(2026, 4, 10))
        self.assertEqual([row["style_key"] for row in matrix["styles"]], ["technology_growth", "large_financials", "high_dividend"])
        self.assertEqual([member["industry"] for member in CONFIG["styles"][0]["members"]], ["电子", "通信", "计算机"])
        for row in matrix["styles"]:
            self.assertEqual(set(row["relative_strength"]), {"5d", "20d", "60d"})
            self.assertIn("above_ma20_ratio", row["breadth"])
            self.assertIn("above_ma60_ratio", row["breadth"])

    def test_persistent_confirmation_requires_strength_breadth_turnover_and_days(self) -> None:
        matrix = build_style_rotation_matrix(CONFIG, complete_series(), as_of=date(2026, 4, 10))
        self.assertEqual(matrix["style_rotation_status"], "持续确认")
        self.assertEqual(matrix["leader_style"], "大金融")
        self.assertGreaterEqual(matrix["confirmation_days"], 5)
        families = {item["family"] for item in matrix["positive_evidence"]}
        self.assertTrue({"relative_strength", "breadth", "turnover"}.issubset(families))
        self.assertTrue(matrix["questions"]["enough_to_change_risk_budget"])

    def test_conflicting_horizon_leaders_cannot_confirm_rotation(self) -> None:
        matrix = build_style_rotation_matrix(CONFIG, complete_series(conflict=True), as_of=date(2026, 4, 10))
        self.assertGreater(len(set(matrix["horizon_leaders"].values())), 1)
        self.assertEqual(matrix["style_rotation_status"], "信号冲突")
        self.assertFalse(matrix["questions"]["enough_to_change_risk_budget"])

    def test_missing_style_data_degrades_without_zero_fill(self) -> None:
        series = complete_series()
        for member in CONFIG["styles"][2]["members"]:
            series.pop(member["code"])
        matrix = build_style_rotation_matrix(CONFIG, series, as_of=date(2026, 4, 10), source_gaps=["红利代理缺失"])
        self.assertEqual(matrix["style_rotation_status"], "数据不足")
        dividend = next(row for row in matrix["styles"] if row["style_key"] == "high_dividend")
        self.assertEqual(dividend["coverage_ratio"], 0.0)
        self.assertIsNone(dividend["relative_strength"]["20d"])
        self.assertIn("红利代理缺失", matrix["source_coverage"]["gaps"])

    def test_fund_and_earnings_proxies_keep_limitations_explicit(self) -> None:
        matrix = build_style_rotation_matrix(CONFIG, complete_series(), as_of=date(2026, 4, 10))
        financial = next(row for row in matrix["styles"] if row["style_key"] == "large_financials")
        self.assertIn("不是ETF份额", financial["fund_proxy"]["limitation"])
        self.assertEqual(financial["earnings_confirmation"]["state"], "unavailable")
        self.assertEqual(matrix["calibration"], "diagnostic_unbacktested")
        self.assertTrue(any("不得单独授权" in item for item in matrix["blocked_conclusions"]))


if __name__ == "__main__":
    unittest.main()
