from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from stock_assist.factor_lab import FACTOR_COLUMNS, FactorLabConfig, build_factor_panel, fit_ridge, run_walk_forward


class FactorLabTests(unittest.TestCase):
    def _prices(self, days: int = 220, stocks: int = 18) -> pd.DataFrame:
        dates = pd.bdate_range("2025-01-02", periods=days)
        rows = []
        for code_index in range(stocks):
            code = f"{code_index:06d}.SZ"
            returns = 0.0003 + (code_index - stocks / 2) * 0.00002 + np.sin(np.arange(days) / 11 + code_index) * 0.002
            close = 10 * np.cumprod(1 + returns)
            for index, day in enumerate(dates):
                rows.append({"code": code, "kline_time": day, "date": day, "close": close[index], "volume": 1e6 + code_index * 1000, "amount": close[index] * 1e6})
        benchmark_close = 1000 * np.cumprod(1 + np.full(days, 0.0002))
        for index, day in enumerate(dates):
            rows.append({"code": "000852.SH", "kline_time": day, "date": day, "close": benchmark_close[index], "volume": 1e8, "amount": 1e11})
        return pd.DataFrame(rows)

    def test_future_label_is_not_available_on_latest_rows(self) -> None:
        panel = build_factor_panel(self._prices(), "000852.SH", 5)
        latest = panel[panel["date"] == panel["date"].max()]
        self.assertTrue(latest["label"].isna().all())

    def test_ridge_recovers_positive_first_factor(self) -> None:
        rng = np.random.default_rng(7)
        frame = pd.DataFrame(rng.normal(size=(300, len(FACTOR_COLUMNS))), columns=FACTOR_COLUMNS)
        frame["label_train"] = frame[FACTOR_COLUMNS[0]] * 0.03 + rng.normal(scale=0.002, size=len(frame))
        weights, _, condition, vif = fit_ridge(frame, 1.0)
        self.assertGreater(weights[0], 0.02)
        self.assertLess(condition, 3)
        self.assertEqual(8, len(vif))

    def test_walk_forward_uses_embargo_and_emits_ranking(self) -> None:
        panel = build_factor_panel(self._prices(), "000852.SH", 5)
        config = FactorLabConfig("synthetic", "test", tuple(f"{i:06d}.SZ" for i in range(18)), min_train_days=80, train_window_days=140, top_n=4)
        result = run_walk_forward(panel, config)
        self.assertGreater(result["period_count"], 10)
        self.assertTrue(result["latest_ranking"])
        self.assertEqual(8, len(result["factor_weights"]))
        self.assertEqual(5, len(result["quintile_average_returns"]))
        self.assertIn(result["validation_status"], {"passed_pilot", "failed_validation"})


if __name__ == "__main__":
    unittest.main()
