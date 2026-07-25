from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from stock_assist.factor_lab import build_factor_panel
from stock_assist.factor_pipeline import decide_promotion, merge_observations, run_factor_pipeline


class FactorPipelineTests(unittest.TestCase):
    def _panel(self, days: int = 230, stocks: int = 18) -> pd.DataFrame:
        dates = pd.bdate_range("2025-01-02", periods=days)
        rows = []
        for code_index in range(stocks):
            code = f"{code_index:06d}.SZ"
            returns = 0.0004 + np.sin(np.arange(days) / 13 + code_index) * 0.002
            close = 10 * np.cumprod(1 + returns)
            for index, day in enumerate(dates):
                rows.append({"code": code, "kline_time": day, "date": day, "close": close[index], "volume": 1e6 + code_index, "amount": close[index] * 1e6})
        benchmark = 1000 * np.cumprod(1 + np.full(days, 0.0002))
        for index, day in enumerate(dates):
            rows.append({"code": "000852.SH", "kline_time": day, "date": day, "close": benchmark[index], "volume": 1e8, "amount": 1e11})
        return build_factor_panel(pd.DataFrame(rows), "000852.SH", 5)

    def test_merge_counts_new_rows_and_newly_matured_labels(self) -> None:
        date = pd.Timestamp("2026-01-02")
        columns = ["date", "code", "close", "momentum_20_5", "reversal_5", "trend_60", "low_vol_20", "downside_20", "liquidity_20", "amihud_20", "volume_surprise", "label", "label_train"]
        old = pd.DataFrame([[date, "000001.SZ", 10, *([0.1] * 8), np.nan, np.nan]], columns=columns)
        new = pd.DataFrame([[date, "000001.SZ", 10, *([0.1] * 8), 0.02, 0.02]], columns=columns)
        merged, counts = merge_observations(old, new)
        self.assertEqual(1, counts["matured_labels"])
        self.assertEqual(0.02, merged.iloc[0]["label_train"])

    def test_rejected_candidate_never_replaces_champion(self) -> None:
        result = decide_promotion({"validation_status": "failed"}, {"version": "old", "promotion_score": 1.0})
        self.assertFalse(result["promoted"])

    def test_daily_run_is_idempotent_for_same_data(self) -> None:
        panel = self._panel()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            factor_path = root / "factor.json"
            factor_path.write_text(json.dumps({
                "universe_name": "test", "universe_type": "test",
                "codes": [f"{i:06d}.SZ" for i in range(18)], "benchmark": "000852.SH",
                "min_train_days": 80, "train_window_days": 160, "top_n": 4,
            }), encoding="utf-8")
            pipeline_path = root / "pipeline.json"
            pipeline_path.write_text(json.dumps({
                "factor_config": str(factor_path), "data_dir": str(root / "runtime"), "validation_dates": 40,
            }), encoding="utf-8")
            first = run_factor_pipeline(pipeline_path, panel)
            second = run_factor_pipeline(pipeline_path, panel)
            self.assertGreater(first["ingest"]["new_rows"], 0)
            self.assertEqual(0, second["ingest"]["new_rows"])
            self.assertTrue(Path(first["candidate_path"]).exists())
            self.assertEqual(7, len(first["candidate"]["feature_names"]))
            registry = (root / "runtime" / "registry.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(registry))


if __name__ == "__main__":
    unittest.main()
