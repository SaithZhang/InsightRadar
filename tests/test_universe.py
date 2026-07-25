from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from stock_assist.factor_lab import FactorLabConfig, build_factor_panel
from stock_assist.factor_pipeline import merge_observations
from stock_assist.universe import apply_universe, resolve_universe


class UniverseTests(unittest.TestCase):
    def _spec(self, rows: list[dict[str, str]]):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "membership.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            config = FactorLabConfig(
                universe_name="pit",
                universe_type="official_index_intervals",
                codes=(),
                universe_mode="point_in_time",
                universe_id="test_pit_v1",
                membership_path=str(path),
            )
            spec = resolve_universe(config)
            return spec

    def test_membership_uses_half_open_intervals(self) -> None:
        spec = self._spec(
            [
                {"universe_id": "test_pit_v1", "code": "A.SZ", "in_date": "2026-01-02", "out_date": "2026-01-06"},
                {"universe_id": "test_pit_v1", "code": "B.SZ", "in_date": "2026-01-05", "out_date": ""},
            ]
        )
        panel = pd.DataFrame(
            [(day, code) for day in pd.date_range("2026-01-02", "2026-01-06", freq="D") for code in ("A.SZ", "B.SZ")],
            columns=["date", "code"],
        )
        filtered = apply_universe(panel, spec)
        keys = set(zip(filtered["date"].dt.strftime("%Y-%m-%d"), filtered["code"]))
        self.assertIn(("2026-01-02", "A.SZ"), keys)
        self.assertNotIn(("2026-01-06", "A.SZ"), keys)
        self.assertNotIn(("2026-01-04", "B.SZ"), keys)
        self.assertIn(("2026-01-05", "B.SZ"), keys)

    def test_new_member_keeps_pre_entry_lookback_for_factors(self) -> None:
        dates = pd.bdate_range("2025-01-02", periods=100)
        rows = []
        for code, base in (("A.SZ", 10.0), ("B.SZ", 20.0), ("C.SZ", 30.0), ("D.SZ", 40.0)):
            close = base * np.cumprod(np.full(len(dates), 1.001))
            rows.extend(
                {"code": code, "date": day, "kline_time": day, "close": close[i], "volume": 1e6, "amount": close[i] * 1e6}
                for i, day in enumerate(dates)
            )
        rows.extend(
            {"code": "000852.SH", "date": day, "kline_time": day, "close": 1000 + i, "volume": 1e8, "amount": 1e11}
            for i, day in enumerate(dates)
        )
        entry = dates[70].strftime("%Y-%m-%d")
        spec = self._spec(
            [
                {"universe_id": "test_pit_v1", "code": code, "in_date": entry, "out_date": ""}
                for code in ("A.SZ", "B.SZ", "C.SZ", "D.SZ")
            ]
        )
        panel = build_factor_panel(pd.DataFrame(rows), "000852.SH", 5, spec)
        entry_rows = panel[panel["date"] == dates[70]]
        self.assertEqual(4, len(entry_rows))
        self.assertTrue(entry_rows["trend_60"].notna().all())

    def test_observation_keys_are_isolated_by_universe(self) -> None:
        columns = ["universe_id", "date", "code", "close", "momentum_20_5", "reversal_5", "trend_60", "low_vol_20", "downside_20", "liquidity_20", "amihud_20", "volume_surprise", "label", "label_train"]
        date = pd.Timestamp("2026-01-02")
        first = pd.DataFrame([["custom", date, "A.SZ", 10, *([0.1] * 8), 0.01, 0.01]], columns=columns)
        second = pd.DataFrame([["csi1000", date, "A.SZ", 10, *([0.1] * 8), 0.01, 0.01]], columns=columns)
        merged, counts = merge_observations(first, second)
        self.assertEqual(2, len(merged))
        self.assertEqual(1, counts["new_rows"])


if __name__ == "__main__":
    unittest.main()
