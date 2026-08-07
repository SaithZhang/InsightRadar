from __future__ import annotations

import json
import unittest
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from stock_assist.intraday.evidence import _cumulative_amount
from stock_assist.intraday.evidence_contracts import IntradayView
from stock_assist.intraday.evidence_providers import (
    parse_eastmoney_trends,
    parse_tencent_minute,
)
from stock_assist.intraday.instruments import resolve_benchmark, resolve_instrument

SHANGHAI = ZoneInfo("Asia/Shanghai")
FIXTURES = Path(__file__).parent / "fixtures" / "intraday_evidence"


class InstrumentResolutionTests(unittest.TestCase):
    def test_stock_etf_and_benchmark_ids_are_explicit(self) -> None:
        etf = resolve_instrument("588200")
        stock = resolve_instrument("002364")
        benchmark = resolve_benchmark("000688")

        self.assertEqual((etf.market, etf.eastmoney_secid, etf.tencent_symbol), ("SH", "1.588200", "sh588200"))
        self.assertEqual((stock.market, stock.eastmoney_secid), ("SZ", "0.002364"))
        self.assertEqual((benchmark.qualified_symbol, benchmark.kind), ("000688.SH", "index"))

    def test_ambiguous_bare_000001_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous_symbol"):
            resolve_instrument("000001")
        self.assertEqual(resolve_instrument("000001.SZ").qualified_symbol, "000001.SZ")
        self.assertEqual(resolve_benchmark("上证指数").qualified_symbol, "000001.SH")


    def test_all_bare_benchmark_codes_fail_closed_on_security_path(self) -> None:
        for symbol in ("000688", "000001", "000300", "399006", "399001"):
            with self.subTest(symbol=symbol), self.assertRaisesRegex(ValueError, "ambiguous_symbol"):
                resolve_instrument(symbol)


class ProviderParserTests(unittest.TestCase):
    def test_eastmoney_raw_fields_stop_at_adapter(self) -> None:
        payload = json.loads((FIXTURES / "eastmoney_trends.json").read_text(encoding="utf-8"))
        fetched_at = datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI)

        result = parse_eastmoney_trends(
            payload,
            instrument=resolve_instrument("588200"),
            fetched_at=fetched_at,
            through_date=date(2026, 8, 7),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.price_basis, "unadjusted")
        self.assertEqual(len(result.data), 1)
        tape = result.data[0]
        self.assertEqual(tape.name, "合成芯片ETF")
        self.assertEqual(tape.pre_close, 1.18)
        self.assertEqual(tape.minutes[-1].price, 1.188)
        self.assertEqual(tape.minutes[-1].volume, 1400)
        self.assertEqual(tape.minutes[-1].amount, 166320)
        self.assertEqual(tape.minutes[-1].avg_price, 1.187)

    def test_tencent_cumulative_values_become_minute_increments(self) -> None:
        payload = json.loads((FIXTURES / "tencent_minute.json").read_text(encoding="utf-8"))
        result = parse_tencent_minute(
            payload,
            instrument=resolve_instrument("002364"),
            requested_date=date(2026, 8, 7),
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.minutes[1].volume, 13000)
        self.assertEqual(result.data.minutes[1].amount, 506000)
        self.assertAlmostEqual(result.data.minutes[1].avg_price or 0, 38.869565, places=5)
        self.assertIn("volume_unit_inferred_from_price_consistency", result.gaps)

    def test_tencent_counter_reversal_is_quarantined(self) -> None:
        payload = json.loads((FIXTURES / "tencent_minute.json").read_text(encoding="utf-8"))
        payload["data"]["sz002364"]["data"]["data"][2] = "0932 39.00 200 700000"
        result = parse_tencent_minute(
            payload,
            instrument=resolve_instrument("002364"),
            requested_date=date(2026, 8, 7),
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        )
        self.assertEqual(result.status, "quarantined")
        self.assertFalse(result.data.minutes)

    def test_eastmoney_missing_minute_amount_marks_tape_incomplete(self) -> None:
        payload = json.loads((FIXTURES / "eastmoney_trends.json").read_text(encoding="utf-8"))
        parts = payload["data"]["trends"][1].split(",")
        parts[6] = ""
        payload["data"]["trends"][1] = ",".join(parts)

        result = parse_eastmoney_trends(
            payload,
            instrument=resolve_instrument("588200"),
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
            through_date=date(2026, 8, 7),
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data[0].amount_kind, "incomplete")
        self.assertIn("missing_minute_amount:2026-08-07:1", result.gaps)
        self.assertIsNone(_cumulative_amount(result.data[0], time(15, 0)))

    def test_tencent_missing_minute_amount_marks_tape_incomplete(self) -> None:
        payload = json.loads((FIXTURES / "tencent_minute.json").read_text(encoding="utf-8"))
        payload["data"]["sz002364"]["data"]["data"][1] = "0931 38.90 230"

        result = parse_tencent_minute(
            payload,
            instrument=resolve_instrument("002364"),
            requested_date=date(2026, 8, 7),
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.amount_kind, "incomplete")
        self.assertIn("missing_minute_amount:1", result.gaps)
        self.assertIsNone(_cumulative_amount(result.data, time(15, 0)))

    def test_tencent_minutes_must_be_strictly_monotonic_and_unique(self) -> None:
        fixture = json.loads((FIXTURES / "tencent_minute.json").read_text(encoding="utf-8"))
        cases = {
            "out_of_order": [
                "0930 38.80 100 388000",
                "0932 39.00 230 894000",
                "0931 38.90 390 1518000",
            ],
            "duplicate": [
                "0930 38.80 100 388000",
                "0931 38.90 230 894000",
                "0931 38.91 390 1518000",
            ],
        }
        for reason, rows in cases.items():
            with self.subTest(reason=reason):
                payload = json.loads(json.dumps(fixture))
                payload["data"]["sz002364"]["data"]["data"] = rows
                result = parse_tencent_minute(
                    payload,
                    instrument=resolve_instrument("002364"),
                    requested_date=date(2026, 8, 7),
                    fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
                )
                self.assertEqual(result.status, "quarantined")
                self.assertIn(f"{reason}_minute_timestamp", result.gaps)
                self.assertFalse(result.data.minutes)

    def test_eastmoney_pre_close_is_not_reassigned_to_historical_cutoff(self) -> None:
        payload = json.loads((FIXTURES / "eastmoney_trends.json").read_text(encoding="utf-8"))
        payload["data"]["trends"] = [
            "2026-08-06 09:30,1.170,1.171,1.172,1.169,1200,140520,1.171",
            *payload["data"]["trends"],
        ]

        result = parse_eastmoney_trends(
            payload,
            instrument=resolve_instrument("588200"),
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
            through_date=date(2026, 8, 6),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.data), 1)
        self.assertIsNone(result.data[0].pre_close)

    def test_intraday_view_exposes_amount_and_volume_units(self) -> None:
        view = IntradayView(
            symbol="588200",
            qualified_symbol="588200.SH",
            name="合成芯片ETF",
            market="SH",
            trade_date="2026-08-07",
            source="eastmoney",
            pre_close=1.18,
            open=1.18,
            last=1.19,
            high=1.20,
            low=1.17,
            day_pct=0.85,
            vwap=1.185,
            return_5m=0.1,
            return_15m=0.2,
            return_30m=0.3,
            distance_to_vwap_pct=0.4,
            distance_to_high_pct=-0.8,
            volume_acceleration=1.2,
            minutes=(),
            amount_unit="CNY",
            volume_unit="lot",
        )
        self.assertEqual((view.amount_unit, view.volume_unit), ("CNY", "lot"))


if __name__ == "__main__":
    unittest.main()
