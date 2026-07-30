from __future__ import annotations

import unittest

from stock_assist.signal_outcomes import build_outcome_snapshot


class SignalOutcomeQuarantineTests(unittest.TestCase):
    def test_price_basis_mismatch_is_excluded_from_all_aggregates(self) -> None:
        records = [
            {
                "signal_id": "2026-07-28:900002.SH",
                "signal_date": "2026-07-28",
                "code": "900002.SH",
                "action_class": "risk_reduce",
                "reason": "收盘价 1.18 低于20日线 3.40，且20日线弱于中期均线 3.61。",
                "reference_price": 1.18,
                "return_1d": -0.02,
                "effect_1d": 0.02,
                "hit_1d": True,
                "status": "partial",
                "last_price_date": "2026-07-29",
            },
            {
                "signal_id": "2026-07-28:900003.SH",
                "signal_date": "2026-07-28",
                "code": "900003.SH",
                "action_class": "hold",
                "reason": "收盘价仍在20日线 7.03 附近。",
                "reference_price": 7.16,
                "return_1d": -0.01,
                "effect_1d": -0.01,
                "hit_1d": False,
                "status": "partial",
                "last_price_date": "2026-07-29",
            },
        ]

        snapshot = build_outcome_snapshot(records)

        self.assertEqual(snapshot["tracked_signals"], 1)
        self.assertEqual(snapshot["tracked_symbols"], 1)
        self.assertEqual(snapshot["quarantined_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["hits"], 0)
        self.assertEqual(snapshot["horizons"]["1d"]["hit_rate"], 0.0)
        self.assertEqual(snapshot["horizons"]["1d"]["average_effect"], -0.01)
        self.assertEqual(
            [item["signal_id"] for item in snapshot["latest"]],
            ["2026-07-28:900003.SH"],
        )
        self.assertEqual(
            [item["signal_id"] for item in snapshot["quarantined_latest"]],
            ["2026-07-28:900002.SH"],
        )
        self.assertEqual(
            snapshot["quarantined_latest"][0]["evaluation_status"],
            "quarantined",
        )

    def test_explicit_quarantine_without_reason_remains_fail_closed(self) -> None:
        snapshot = build_outcome_snapshot(
            [
                {
                    "signal_id": "2026-07-28:900002.SH",
                    "signal_date": "2026-07-28",
                    "code": "900002.SH",
                    "action_class": "hold",
                    "evaluation_status": "quarantined",
                    "return_1d": 0.01,
                    "effect_1d": 0.01,
                    "hit_1d": True,
                    "status": "partial",
                }
            ]
        )

        self.assertEqual(snapshot["tracked_signals"], 0)
        self.assertEqual(snapshot["quarantined_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)
        self.assertEqual(snapshot["latest"], [])
        self.assertTrue(
            snapshot["quarantined_latest"][0]["quarantine_reason"]
        )


if __name__ == "__main__":
    unittest.main()
