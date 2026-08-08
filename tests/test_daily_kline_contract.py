from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from stock_assist.data_sources import xysz
from stock_assist.data_sources.a_share_klines import fetch_tencent_daily_result
from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.data_sources.eastmoney_klines import Candle
from stock_assist.portfolio import Holding
from stock_assist.workflows.after_close import (
    _build_signals,
    _daily_kline_result_with_requested_repair,
    _signal_for_holding,
)

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
    @patch("stock_assist.data_sources.a_share_klines.fetch_tencent_klines")
    def test_tencent_repair_adapter_is_forward_adjusted_and_drops_future_rows(
        self,
        fetch: object,
    ) -> None:
        rows = [
            Candle(
                time=datetime(2026, 7, 1) + timedelta(days=index),
                open=10.0 + index * 0.02,
                high=10.1 + index * 0.02,
                low=9.9 + index * 0.02,
                close=10.0 + index * 0.02,
                volume=1000.0,
                amount=10_000.0,
            )
            for index in range(32)
        ]
        fetch.return_value = rows  # type: ignore[attr-defined]

        result = fetch_tencent_daily_result(
            "900001.SH",
            expected_trade_date=date(2026, 7, 31),
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
        )

        self.assertEqual(result.provider, "tencent")
        self.assertEqual(result.price_basis, "forward_adjusted")
        self.assertEqual(result.trade_date, date(2026, 7, 31))
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("future_rows_dropped" in gap for gap in result.gaps))

    def test_requested_repair_uses_whole_fallback_and_keeps_primary_quarantine_gap(self) -> None:
        raw, _ = _load_fixture()
        primary_batch = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900002.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )
        primary = xysz.daily_kline_result_for_code(primary_batch, "900002.SH")
        healthy_batch = xysz.normalise_daily_kline_result(
            _healthy_raw("900002.SH"),
            requested_codes=["900002.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:06:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )
        fallback = replace(
            xysz.daily_kline_result_for_code(healthy_batch, "900002.SH"),
            provider="tencent",
            price_basis="forward_adjusted",
        )
        with patch(
            "stock_assist.workflows.after_close.fetch_tencent_daily_result",
            return_value=fallback,
        ):
            resolved = _daily_kline_result_with_requested_repair(
                primary,
                code="900002.SH",
                expected_trade_date=date(2026, 7, 31),
                repair={"strategy": "tencent_forward_adjusted_whole_series"},
            )

        signal = _signal_for_holding(
            Holding(code="900002.SH", name="合成标的乙", market_price=11.2),
            resolved,
        )
        self.assertEqual(primary.status, "quarantined")
        self.assertEqual(resolved.provider, "tencent")
        self.assertEqual(resolved.status, "partial")
        self.assertEqual(resolved.price_basis, "forward_adjusted")
        self.assertTrue(any("fallback_from:amazingdata" in gap for gap in resolved.gaps))
        self.assertNotEqual(signal.decision_contract["technical"]["state"], "quarantined")

    def test_failed_requested_repair_retains_primary_quarantine_and_new_reason(self) -> None:
        raw, _ = _load_fixture()
        primary_batch = xysz.normalise_daily_kline_result(
            raw,
            requested_codes=["900002.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )
        primary = xysz.daily_kline_result_for_code(primary_batch, "900002.SH")
        failed = ProviderResult(
            provider="tencent",
            schema_version="daily-ohlcv/v1",
            source_time=None,
            fetched_at=datetime.fromisoformat("2026-07-31T15:06:00+08:00"),
            trade_date=None,
            status="invalid",
            gaps=(),
            errors=("900002.SH:tencent_daily:TimeoutError",),
            price_basis="forward_adjusted",
            data=pd.DataFrame(),
        )
        with patch(
            "stock_assist.workflows.after_close.fetch_tencent_daily_result",
            return_value=failed,
        ):
            resolved = _daily_kline_result_with_requested_repair(
                primary,
                code="900002.SH",
                expected_trade_date=date(2026, 7, 31),
                repair={"strategy": "tencent_forward_adjusted_whole_series"},
            )

        self.assertEqual(resolved.status, "quarantined")
        self.assertEqual(resolved.provider, "amazingdata")
        self.assertIn("900002.SH:tencent_daily:TimeoutError", resolved.errors)
        self.assertTrue(any("repair_fallback_failed" in gap for gap in resolved.gaps))

    def test_security_mapping_repair_uses_requested_symbol_with_safe_fallback(self) -> None:
        primary = ProviderResult(
            provider="amazingdata",
            schema_version="daily-ohlcv/v1",
            source_time=None,
            fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
            trade_date=None,
            status="invalid",
            gaps=(),
            errors=("900003.SH:code_mismatch",),
            price_basis="unadjusted",
            data=pd.DataFrame(),
        )
        healthy_batch = xysz.normalise_daily_kline_result(
            _healthy_raw("900003.SH"),
            requested_codes=["900003.SH"],
            fetched_at=datetime.fromisoformat("2026-07-31T15:06:00+08:00"),
            expected_trade_date=date(2026, 7, 31),
        )
        fallback = replace(
            xysz.daily_kline_result_for_code(healthy_batch, "900003.SH"),
            provider="tencent",
            price_basis="forward_adjusted",
        )
        with patch(
            "stock_assist.workflows.after_close.fetch_tencent_daily_result",
            return_value=fallback,
        ):
            resolved = _daily_kline_result_with_requested_repair(
                primary,
                code="900003.SH",
                expected_trade_date=date(2026, 7, 31),
                repair={
                    "strategy": "tencent_forward_adjusted_whole_series",
                    "reason_code": "SECURITY_MAPPING_INVALID",
                },
            )

        self.assertEqual(resolved.provider, "tencent")
        self.assertEqual(resolved.status, "partial")
        self.assertTrue(any("security_mapping_invalid" in gap for gap in resolved.gaps))

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
