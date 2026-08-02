from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from stock_assist.data_sources import xysz
from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.portfolio import Holding
from stock_assist.workflows.after_close import _build_signals

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "amazingdata_daily_unadjusted_split.json"
)


def _load_fixture() -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw = {
        code: pd.DataFrame(rows)
        for code, rows in payload["response"].items()
    }
    return raw, payload


def _healthy_raw(code: str = "900001.SH") -> dict[str, pd.DataFrame]:
    trade_dates = pd.bdate_range(end="2026-07-31", periods=25)
    closes = [10.0 + index * 0.05 for index in range(len(trade_dates))]
    return {
        code: pd.DataFrame(
            {
                "code": [code] * len(trade_dates),
                "kline_time": trade_dates,
                "open": [value - 0.02 for value in closes],
                "high": [value + 0.08 for value in closes],
                "low": [value - 0.08 for value in closes],
                "close": closes,
                "volume": [1000 + index * 10 for index in range(len(closes))],
                "amount": [10000 + index * 100 for index in range(len(closes))],
                "provider_debug": ["not-for-downstream"] * len(closes),
            }
        )
    }


class _FixtureClient:
    def __init__(self, raw: dict[str, pd.DataFrame]) -> None:
        self.calendar = [20260703, 20260731]
        self.raw = raw

    def query_daily_kline(
        self,
        codes: list[str],
        begin_date: int,
        end_date: int,
    ) -> dict[str, pd.DataFrame]:
        return self.raw

    def query_daily_kline_result(
        self,
        codes: list[str],
        begin_date: int,
        end_date: int,
    ) -> ProviderResult[dict[str, pd.DataFrame]]:
        return xysz.normalise_daily_kline_result(
            self.query_daily_kline(codes, begin_date, end_date),
            requested_codes=codes,
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )


class DailyKlineContractTests(unittest.TestCase):
    def test_fixture_reaches_holding_rule_with_declared_price_basis(self) -> None:
        raw, _ = _load_fixture()
        client = _FixtureClient(raw)

        signals = _build_signals(
            client,  # type: ignore[arg-type]
            [Holding(code="900002.SH", name="合成标的乙", market_price=1.15)],
            lookback_days=60,
        )

        technical = signals[0].decision_contract["technical"]
        self.assertEqual(technical["state"], "quarantined")
        self.assertEqual(technical["adjustment_basis"], "unadjusted")
        self.assertIn("价格断点", signals[0].reason)

    def test_adapter_contract_exposes_fault_context_offline(self) -> None:
        raw, fixture = _load_fixture()
        normalise = xysz.normalise_daily_kline_result

        result = normalise(
            raw,
            requested_codes=[str(fixture["requested_code"])],
            fetched_at=datetime.fromisoformat(str(fixture["fetched_at"])),
            expected_trade_date=date.fromisoformat(
                str(fixture["expected_trade_date"])
            ),
        )

        self.assertEqual(result.provider, "amazingdata")
        self.assertEqual(result.schema_version, "daily-ohlcv/v1")
        self.assertEqual(result.trade_date, date(2026, 7, 31))
        self.assertEqual(result.status, "quarantined")
        self.assertEqual(result.price_basis, "unadjusted")
        self.assertEqual(result.errors, ())
        self.assertTrue(any("price_discontinuity" in gap for gap in result.gaps))
        self.assertEqual(
            list(result.data["900002.SH"].columns),
            ["code", "trade_date", "open", "high", "low", "close", "volume", "amount"],
        )
        self.assertIsNone(result.source_time)
        self.assertEqual(result.fetched_at.isoformat(), "2026-07-31T15:05:00+08:00")

    def test_invalid_ohlc_fails_closed_before_holding_rules(self) -> None:
        raw, _ = _load_fixture()
        raw["900002.SH"].loc[0, "close"] = 0
        client = _FixtureClient(raw)

        result = client.query_daily_kline_result(
            ["900002.SH"],
            20260703,
            20260731,
        )
        signal = _build_signals(
            client,  # type: ignore[arg-type]
            [Holding(code="900002.SH", name="合成标的乙", market_price=1.15)],
            lookback_days=60,
        )[0]

        self.assertEqual(result.status, "invalid")
        self.assertTrue(any("invalid_ohlc_rows" in error for error in result.errors))
        self.assertEqual(signal.decision_contract["technical"]["state"], "unknown")
        self.assertIn("ProviderResult 数据不变量", signal.reason)

    def test_out_of_order_timestamps_are_sorted_and_reported(self) -> None:
        raw, _ = _load_fixture()
        raw["900002.SH"] = (
            raw["900002.SH"].tail(3).iloc[::-1].reset_index(drop=True)
        )

        result = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900002.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )

        self.assertEqual(result.status, "partial")
        self.assertTrue(any("timestamps_reordered" in gap for gap in result.gaps))
        self.assertTrue(result.data["900002.SH"]["trade_date"].is_monotonic_increasing)

    def test_multi_code_dataframe_without_code_is_invalid(self) -> None:
        raw = _healthy_raw()["900001.SH"].drop(columns="code")

        result = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900001.SH", "900002.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )

        self.assertEqual(result.status, "invalid")
        self.assertIn("request:ambiguous_frame_without_code", result.errors)
        self.assertTrue(all(frame.empty for frame in result.data.values()))

    def test_single_code_dataframe_without_code_uses_unique_request_code(self) -> None:
        raw = _healthy_raw()["900001.SH"].drop(columns="code")

        result = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900001.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(set(result.data["900001.SH"]["code"]), {"900001.SH"})

    def test_dict_key_and_inner_code_mismatch_is_invalid(self) -> None:
        raw = _healthy_raw("900002.SH")

        result = xysz.normalise_daily_kline_result(
            {"900001.SH": raw["900002.SH"]},
            requested_codes=["900001.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )

        self.assertEqual(result.status, "invalid")
        self.assertIn("900001.SH:code_mismatch", result.errors)
        self.assertTrue(result.data["900001.SH"].empty)

    def test_point_underscore_alias_remains_compatible(self) -> None:
        raw = _healthy_raw("900001_SH")

        result = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900001.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(set(result.data["900001.SH"]["code"]), {"900001.SH"})

    def test_explicit_source_time_after_fetch_is_invalid(self) -> None:
        result = xysz.normalise_daily_kline_result(
            _healthy_raw(),
            requested_codes=["900001.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
            source_time=datetime.fromisoformat("2026-07-31T15:06:00+08:00"),
        )

        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.source_time)
        self.assertIn("request:source_time_after_fetched_at", result.errors)

    def test_healthy_daily_series_reaches_usable_holding_technical_state(self) -> None:
        client = _FixtureClient(_healthy_raw())

        result = client.query_daily_kline_result(
            ["900001.SH"],
            20260626,
            20260731,
        )
        signal = _build_signals(
            client,  # type: ignore[arg-type]
            [Holding(code="900001.SH", name="合成标的甲", market_price=11.2)],
            lookback_days=60,
        )[0]

        technical = signal.decision_contract["technical"]
        narrowed = xysz.daily_kline_result_for_code(result, "900001.SH")
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.source_time)
        self.assertIsNone(narrowed.source_time)
        self.assertNotIn(technical["state"], {"unknown", "quarantined"})
        self.assertEqual(technical["adjustment_basis"], "unadjusted")
        self.assertNotIn("provider_debug", result.data["900001.SH"].columns)


if __name__ == "__main__":
    unittest.main()
