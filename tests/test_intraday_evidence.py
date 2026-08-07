from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.intraday.evidence import IntradayEvidenceService, evidence_to_dict
from stock_assist.intraday.evidence_contracts import (
    IntradayTape,
    TapeMinute,
    TradeInput,
)
from stock_assist.intraday.evidence_providers import IntradayFetch
from stock_assist.intraday.instruments import resolve_instrument

SHANGHAI = ZoneInfo("Asia/Shanghai")
DAY = date(2026, 8, 7)


class FakeProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.series: dict[tuple[str, date], ProviderResult[IntradayTape]] = {}
        self.recent: dict[str, ProviderResult[tuple[IntradayTape, ...]]] = {}
        self.fetch_count = 0

    def fetch(self, request: IntradayFetch) -> ProviderResult[IntradayTape]:
        self.fetch_count += 1
        key = (request.instrument.qualified_symbol, request.trade_date)
        return self.series.get(key) or _empty_result(
            self.provider_id, request.instrument.qualified_symbol, request.trade_date
        )

    def fetch_recent(
        self,
        instrument: object,
        *,
        through_date: date,
    ) -> ProviderResult[tuple[IntradayTape, ...]]:
        qualified = instrument.qualified_symbol
        return self.recent.get(qualified) or ProviderResult(
            provider=self.provider_id,
            schema_version="intraday-tapes/v1",
            source_time=None,
            fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
            trade_date=through_date,
            status="empty",
            gaps=("fixture_missing",),
            errors=(),
            price_basis="unadjusted",
            data=(),
        )


class IntradayEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = FakeProvider("eastmoney")
        self.fallback = FakeProvider("tencent")
        self.now = datetime(2026, 8, 7, 15, 5, tzinfo=SHANGHAI)
        self.service = IntradayEvidenceService(
            primary=self.primary,
            fallback=self.fallback,
            now_fn=lambda: self.now,
            ttl_seconds=20,
        )

    def test_get_intraday_calculates_vwap_returns_and_distance(self) -> None:
        tape = _trend_tape("588200", count=71, start=1.18, step=0.001)
        self.primary.series[("588200.SH", DAY)] = _ok_result("eastmoney", tape)

        result = self.service.get_intraday("588200", DAY, as_of=time(10, 30))

        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.data)
        assert result.data is not None
        self.assertEqual(result.data.minutes[-1].time, "10:30")
        self.assertIsNotNone(result.data.vwap)
        self.assertGreater(result.data.return_5m or 0, 0)
        self.assertGreater(result.data.return_15m or 0, 0)
        self.assertGreater(result.data.distance_to_vwap_pct or 0, 0)
        self.assertLessEqual(result.data.distance_to_high_pct or 0, 0)

    def test_eastmoney_failure_uses_whole_tencent_tape(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 10, tzinfo=SHANGHAI)
        self.primary.series[("002364.SZ", DAY)] = _invalid_result("eastmoney", "002364", DAY)
        fallback_tape = _trend_tape("002364", count=40, start=38.7, step=0.01)
        self.fallback.series[("002364.SZ", DAY)] = _ok_result("tencent", fallback_tape)

        result = self.service.get_intraday("002364", DAY)

        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.reason, "eastmoney_failed_tencent_fallback")
        self.assertEqual(result.data.source if result.data else None, "tencent")
        self.assertEqual([item.provider for item in result.provenance], ["eastmoney", "tencent"])

    def test_partial_primary_and_disagreeing_fallback_exposes_conflict(self) -> None:
        self.now = datetime(2026, 8, 7, 9, 50, tzinfo=SHANGHAI)
        primary_tape = _trend_tape("002364", count=20, start=38.7, step=0.01)
        fallback_tape = _trend_tape("002364", count=20, start=38.7, step=0.03)
        self.primary.series[("002364.SZ", DAY)] = _result("eastmoney", primary_tape, "partial")
        self.fallback.series[("002364.SZ", DAY)] = _ok_result("tencent", fallback_tape)

        result = self.service.get_intraday("002364", DAY)

        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.reason, "source_conflict")
        self.assertGreater(len(result.conflicts), 1)
        self.assertAlmostEqual(result.data.last if result.data else 0, primary_tape.minutes[-1].price)

    def test_conflict_before_matching_last_minute_is_not_hidden(self) -> None:
        self.now = datetime(2026, 8, 7, 9, 50, tzinfo=SHANGHAI)
        primary_tape = _trend_tape("002364", count=20, start=38.7, step=0.01)
        fallback_tape = replace(
            primary_tape,
            minutes=tuple(
                replace(item, price=item.price * 1.5) if index == 5 else item
                for index, item in enumerate(primary_tape.minutes)
            ),
        )
        self.primary.series[("002364.SZ", DAY)] = _result(
            "eastmoney", primary_tape, "partial"
        )
        self.fallback.series[("002364.SZ", DAY)] = _ok_result("tencent", fallback_tape)

        result = self.service.get_intraday("002364", DAY)

        self.assertEqual(result.reason, "source_conflict")
        self.assertTrue(any("09:35" in item.field for item in result.conflicts))

    def test_ttl_cache_avoids_duplicate_fetch(self) -> None:
        tape = _trend_tape("588200", count=10, start=1.18, step=0.001)
        self.primary.series[("588200.SH", DAY)] = _ok_result("eastmoney", tape)
        self.service.get_intraday("588200", DAY)
        self.service.get_intraday("588200", DAY)
        self.assertEqual(self.primary.fetch_count, 1)

    def test_compare_ranks_relative_strength_transparently(self) -> None:
        first = _trend_tape("588200", count=31, start=1.0, step=0.01)
        second = _trend_tape("002364", count=31, start=10.0, step=0.02)
        benchmark = _trend_tape("000688.SH", count=31, start=1000, step=1)
        for tape in (first, second, benchmark):
            self.primary.series[(tape.instrument.qualified_symbol, DAY)] = _ok_result("eastmoney", tape)

        result = self.service.get_intraday_compare(
            ["588200", "002364"], benchmark="000688", trade_date=DAY, as_of=time(10, 0)
        )

        self.assertEqual(result.status, "ok")
        assert result.data is not None
        rows = {item.symbol: item for item in result.data.rows}
        self.assertEqual(rows["588200"].rank, 1)
        self.assertEqual(rows["002364"].rank, 2)
        self.assertGreater(
            rows["588200"].relative_strength_vs_benchmark or 0,
            rows["002364"].relative_strength_vs_benchmark or 0,
        )

    def test_compare_aligns_every_series_to_one_common_minute(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 2, tzinfo=SHANGHAI)
        stock = _trend_tape("588200", count=31, start=1.0, step=0.01)
        benchmark = _trend_tape("000688.SH", count=32, start=1000, step=1)
        self.primary.series[(stock.instrument.qualified_symbol, DAY)] = _ok_result("eastmoney", stock)
        self.primary.series[(benchmark.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", benchmark
        )

        result = self.service.get_intraday_compare(
            ["588200"], benchmark="000688", trade_date=DAY
        )

        self.assertEqual(result.status, "degraded")
        self.assertIn("aligned_to_latest_common_minute", result.reason or "")
        assert result.data is not None
        self.assertEqual(result.data.rows[0].time, "10:00")

    def test_same_time_market_amount_sums_both_exchanges(self) -> None:
        previous = date(2026, 8, 6)
        sh_previous = _amount_tape("000001.SH", previous, (100.0, 200.0))
        sh_today = _amount_tape("000001.SH", DAY, (120.0, 240.0))
        sz_previous = _amount_tape("399001.SZ", previous, (80.0, 160.0))
        sz_today = _amount_tape("399001.SZ", DAY, (90.0, 180.0))
        self.primary.recent["000001.SH"] = _recent_result("eastmoney", (sh_previous, sh_today))
        self.primary.recent["399001.SZ"] = _recent_result("eastmoney", (sz_previous, sz_today))

        result = self.service.get_market_amount_compare(DAY, as_of=time(9, 31))

        self.assertEqual(result.status, "ok")
        assert result.data is not None
        self.assertEqual(result.data.today_amount, 630.0)
        self.assertEqual(result.data.previous_day_same_time_amount, 540.0)
        self.assertEqual(result.data.delta, 90.0)
        self.assertAlmostEqual(result.data.delta_pct or 0, 16.6666667, places=5)

    def test_partial_primary_amount_survives_failed_fallback(self) -> None:
        previous = date(2026, 8, 6)
        for symbol, previous_values, today_values in (
            ("000001.SH", (100.0, 200.0), (120.0, 240.0)),
            ("399001.SZ", (80.0, 160.0), (90.0, 180.0)),
        ):
            recent = _recent_result(
                "eastmoney",
                (
                    _amount_tape(symbol, previous, previous_values),
                    _amount_tape(symbol, DAY, today_values),
                ),
            )
            self.primary.recent[symbol] = replace(
                recent,
                status="partial",
                gaps=("synthetic_partial",),
            )

        result = self.service.get_market_amount_compare(DAY, as_of=time(9, 31))

        self.assertEqual(result.status, "degraded")
        self.assertIn("tencent_fallback_unavailable", result.reason or "")
        self.assertEqual(result.data.today_amount if result.data else None, 630.0)

    def test_current_market_amount_applies_freshness_gate(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 10, tzinfo=SHANGHAI)
        previous = date(2026, 8, 6)
        for symbol in ("000001.SH", "399001.SZ"):
            self.primary.recent[symbol] = _recent_result(
                "eastmoney",
                (
                    _amount_tape(symbol, previous, (100.0, 200.0)),
                    _amount_tape(symbol, DAY, (120.0, 240.0)),
                ),
            )

        result = self.service.get_market_amount_compare(DAY)

        self.assertEqual(result.status, "stale")
        self.assertGreater(result.stale_seconds or 0, 180)

    def test_missing_minute_amount_fails_closed(self) -> None:
        previous = date(2026, 8, 6)
        sh_today = _amount_tape("000001.SH", DAY, (120.0, 240.0))
        broken_minutes = (
            sh_today.minutes[0],
            replace(sh_today.minutes[1], amount=None),
        )
        sh_today = replace(sh_today, minutes=broken_minutes, amount_kind="incomplete")
        self.primary.recent["000001.SH"] = replace(
            _recent_result(
                "eastmoney",
                (_amount_tape("000001.SH", previous, (100.0, 200.0)), sh_today),
            ),
            status="partial",
        )
        self.primary.recent["399001.SZ"] = _recent_result(
            "eastmoney",
            (
                _amount_tape("399001.SZ", previous, (80.0, 160.0)),
                _amount_tape("399001.SZ", DAY, (90.0, 180.0)),
            ),
        )

        result = self.service.get_market_amount_compare(DAY, as_of=time(9, 31))

        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.data)

    def test_review_separates_no_lookahead_context_from_outcome(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 45, tzinfo=SHANGHAI)
        tape = _trend_tape("588200", count=75, start=1.10, step=0.002)
        benchmark = _trend_tape("000688.SH", count=75, start=1000, step=0.5)
        self.primary.series[("588200.SH", DAY)] = _ok_result("eastmoney", tape)
        self.primary.series[("000688.SH", DAY)] = _ok_result("eastmoney", benchmark)
        sell = TradeInput(DAY, time(10, 0, 30), "588200", "sell", 123, 1.161)
        buy = TradeInput(DAY, time(10, 0, 30), "588200", "buy", 123, 1.161)

        result = self.service.review_trades((sell, buy), benchmark="000688")

        self.assertEqual(result.status, "ok")
        assert result.data is not None
        sell_review, buy_review = result.data.trades
        assert sell_review.decision_context is not None and sell_review.outcome is not None
        self.assertTrue(sell_review.decision_context.evidence_time.endswith("09:59+08:00"))
        self.assertGreater(sell_review.outcome.max_continue_up_30m or 0, 0)
        self.assertEqual(sell_review.outcome.mae_30m, None)
        assert buy_review.outcome is not None
        self.assertGreater(buy_review.outcome.mfe_30m or 0, 0)
        self.assertLessEqual(buy_review.outcome.mae_30m or 0, 0.0)

    def test_review_degrades_when_benchmark_is_unavailable(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 45, tzinfo=SHANGHAI)
        tape = _trend_tape("588200", count=75, start=1.10, step=0.002)
        self.primary.series[(tape.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", tape
        )
        trade = TradeInput(DAY, time(10, 0, 30), "588200", "sell", 123, 1.161)

        result = self.service.review_trades((trade,), benchmark="000688")

        self.assertEqual(result.status, "degraded")
        assert result.data is not None
        item = result.data.trades[0]
        self.assertIn("benchmark_", item.reason or "")
        self.assertIsNone(
            item.decision_context.relative_strength_vs_benchmark
            if item.decision_context else None
        )

    def test_current_trade_review_applies_freshness_gate(self) -> None:
        tape = _trend_tape("588200", count=75, start=1.10, step=0.002)
        benchmark = _trend_tape("000688.SH", count=75, start=1000, step=0.5)
        self.primary.series[(tape.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", tape
        )
        self.primary.series[(benchmark.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", benchmark
        )
        trade = TradeInput(DAY, time(10, 0, 30), "588200", "sell", 123, 1.161)

        result = self.service.review_trades((trade,), benchmark="000688")

        self.assertEqual(result.status, "stale")
        self.assertGreater(result.stale_seconds or 0, 180)

    def test_point_only_tape_does_not_invent_outcome_extrema(self) -> None:
        self.now = datetime(2026, 8, 7, 10, 45, tzinfo=SHANGHAI)
        tape = _trend_tape("588200", count=75, start=1.10, step=0.002)
        point_only = replace(
            tape,
            minutes=tuple(replace(item, high=None, low=None) for item in tape.minutes),
        )
        benchmark = _trend_tape("000688.SH", count=75, start=1000, step=0.5)
        self.primary.series[(point_only.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", point_only
        )
        self.primary.series[(benchmark.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", benchmark
        )
        trade = TradeInput(DAY, time(10, 0, 30), "588200", "sell", 123, 1.161)

        result = self.service.review_trades((trade,), benchmark="000688")

        self.assertEqual(result.status, "degraded")
        assert result.data is not None and result.data.trades[0].outcome is not None
        item = result.data.trades[0]
        assert item.decision_context is not None
        self.assertIsNone(item.decision_context.day_high)
        self.assertIsNone(item.decision_context.day_low)
        self.assertIsNone(item.decision_context.distance_to_high_pct)
        self.assertIsNone(item.decision_context.distance_to_low_pct)
        self.assertIsNone(item.decision_context.range_position_pct)
        self.assertIsNone(item.decision_context.near_day_high)
        self.assertIn("minute_extrema_unavailable", item.gaps)
        self.assertIsNone(item.outcome.max_continue_up_30m)
        self.assertIsNone(item.outcome.max_down_30m)

        tape_result = self.service.get_intraday("588200", DAY)
        self.assertEqual(tape_result.status, "degraded")
        assert tape_result.data is not None
        self.assertIsNone(tape_result.data.high)
        self.assertIsNone(tape_result.data.low)
        self.assertIsNone(tape_result.data.distance_to_high_pct)
        self.assertIn("minute_extrema_unavailable", tape_result.gaps)

    def test_lunch_boundary_is_not_falsely_stale(self) -> None:
        self.now = datetime(2026, 8, 7, 13, 0, 30, tzinfo=SHANGHAI)
        tape = _trend_tape("588200", count=121, start=1.10, step=0.001)
        self.primary.series[(tape.instrument.qualified_symbol, DAY)] = _ok_result(
            "eastmoney", tape
        )

        result = self.service.get_intraday("588200", DAY)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.stale_seconds, 30.0)

        self.now = datetime(2026, 8, 7, 13, 2, tzinfo=SHANGHAI)
        resumed_result = self.service.get_intraday("588200", DAY)
        self.assertEqual(resumed_result.status, "ok")
        self.assertEqual(resumed_result.stale_seconds, 120.0)

    def test_lunch_and_future_date_trades_fail_closed(self) -> None:
        lunch = TradeInput(DAY, time(12, 0), "588200", "sell", 1, 1.0)
        future = TradeInput(date(2026, 8, 10), time(10, 0), "588200", "sell", 1, 1.0)

        lunch_result = self.service.review_trades((lunch,), benchmark="000688")
        future_result = self.service.review_trades((future,), benchmark="000688")

        assert lunch_result.data is not None and future_result.data is not None
        self.assertEqual(lunch_result.data.trades[0].reason, "outside_continuous_trading_session")
        self.assertEqual(future_result.data.trades[0].reason, "future_trade_date")

    def test_service_caps_compare_and_review_batches(self) -> None:
        symbols = tuple(f"{600000 + index:06d}" for index in range(21))
        trade = TradeInput(DAY, time(10, 0), "588200", "sell", 1, 1.0)

        compare = self.service.get_intraday_compare(
            symbols, benchmark="000688", trade_date=DAY
        )
        review = self.service.review_trades((trade,) * 101, benchmark="000688")

        self.assertEqual((compare.status, compare.reason), ("blocked", "symbols_exceed_limit_20"))
        self.assertEqual((review.status, review.reason), ("blocked", "trades_exceed_limit_100"))

    def test_future_trade_time_is_blocked(self) -> None:
        self.now = datetime(2026, 8, 7, 9, 45, tzinfo=SHANGHAI)
        trade = TradeInput(DAY, time(10, 0), "588200", "sell", 1, 1.0)
        result = self.service.review_trades((trade,), benchmark="000688")
        self.assertEqual(result.status, "blocked")
        assert result.data is not None
        self.assertEqual(result.data.trades[0].reason, "current_time_before_trade_time")

    def test_weekend_is_explicit_no_data(self) -> None:
        result = self.service.get_intraday("588200", date(2026, 8, 8))
        self.assertEqual((result.status, result.reason), ("no_data", "non_trading_day"))

    def test_serialization_preserves_unknown_as_null(self) -> None:
        result = self.service.get_intraday("588200", date(2026, 8, 8))
        payload = evidence_to_dict(result)
        self.assertIsInstance(payload, dict)
        self.assertIsNone(payload["data"])


def _trend_tape(symbol: str, *, count: int, start: float, step: float) -> IntradayTape:
    instrument = resolve_instrument(symbol)
    minutes: list[TapeMinute] = []
    cumulative_amount = 0.0
    cumulative_volume = 0.0
    begin = datetime(2026, 8, 7, 9, 30, tzinfo=SHANGHAI)
    for index in range(count):
        price = start + step * index
        volume = 1000.0 + index * 10.0
        amount = price * volume
        cumulative_volume += volume
        cumulative_amount += amount
        minutes.append(
            TapeMinute(
                timestamp=begin + timedelta(minutes=index),
                price=price,
                avg_price=cumulative_amount / cumulative_volume,
                high=price * 1.001,
                low=price * 0.999,
                volume=volume,
                amount=amount,
                cumulative_volume=cumulative_volume,
                cumulative_amount=cumulative_amount,
            )
        )
    return IntradayTape(
        instrument=instrument,
        name=instrument.display_name or f"Synthetic {instrument.code}",
        trade_date=DAY,
        pre_close=start * 0.99,
        minutes=tuple(minutes),
        volume_unit="share",
    )


def _amount_tape(symbol: str, day: date, amounts: tuple[float, ...]) -> IntradayTape:
    instrument = resolve_instrument(symbol)
    begin = datetime.combine(day, time(9, 30), tzinfo=SHANGHAI)
    return IntradayTape(
        instrument=instrument,
        name=instrument.display_name,
        trade_date=day,
        pre_close=None,
        minutes=tuple(
            TapeMinute(
                timestamp=begin + timedelta(minutes=index),
                price=100.0,
                avg_price=100.0,
                high=100.0,
                low=100.0,
                volume=1.0,
                amount=amount,
            )
            for index, amount in enumerate(amounts)
        ),
    )


def _result(provider: str, tape: IntradayTape, status: str) -> ProviderResult[IntradayTape]:
    return ProviderResult(
        provider=provider,
        schema_version="intraday-tape/v1",
        source_time=tape.minutes[-1].timestamp,
        fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        trade_date=tape.trade_date,
        status=status,  # type: ignore[arg-type]
        gaps=("synthetic_partial",) if status == "partial" else (),
        errors=(),
        price_basis="unadjusted",
        data=tape,
    )


def _ok_result(provider: str, tape: IntradayTape) -> ProviderResult[IntradayTape]:
    return _result(provider, tape, "ok")


def _empty_result(provider: str, symbol: str, day: date) -> ProviderResult[IntradayTape]:
    instrument = resolve_instrument(symbol)
    return ProviderResult(
        provider=provider,
        schema_version="intraday-tape/v1",
        source_time=None,
        fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        trade_date=day,
        status="empty",
        gaps=("fixture_missing",),
        errors=(),
        price_basis="unadjusted",
        data=IntradayTape(instrument, instrument.display_name, day, None, ()),
    )


def _invalid_result(provider: str, symbol: str, day: date) -> ProviderResult[IntradayTape]:
    result = _empty_result(provider, symbol, day)
    return ProviderResult(
        provider=result.provider,
        schema_version=result.schema_version,
        source_time=None,
        fetched_at=result.fetched_at,
        trade_date=day,
        status="invalid",
        gaps=("network_unavailable",),
        errors=("ConnectionError",),
        price_basis="unadjusted",
        data=result.data,
    )


def _recent_result(
    provider: str,
    tapes: tuple[IntradayTape, ...],
) -> ProviderResult[tuple[IntradayTape, ...]]:
    return ProviderResult(
        provider=provider,
        schema_version="intraday-tapes/v1",
        source_time=tapes[-1].minutes[-1].timestamp,
        fetched_at=datetime(2026, 8, 7, 15, 1, tzinfo=SHANGHAI),
        trade_date=tapes[-1].trade_date,
        status="ok",
        gaps=(),
        errors=(),
        price_basis="unadjusted",
        data=tapes,
    )


if __name__ == "__main__":
    unittest.main()
