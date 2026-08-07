"""Deep, read-only module for intraday market evidence and trade review."""

from __future__ import annotations

import math
import time as monotonic_time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass, replace
from datetime import date, datetime, time, timedelta
from threading import Lock
from typing import Any, Literal, TypeVar, cast
from zoneinfo import ZoneInfo

from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.intraday.evidence_contracts import (
    CompareIntradayQuery,
    EvidenceEnvelope,
    EvidenceQuery,
    EvidenceStatus,
    GetIntradayQuery,
    InstrumentRef,
    IntradayCompareRow,
    IntradayCompareView,
    IntradayMinuteView,
    IntradayTape,
    IntradayView,
    MarketAmountQuery,
    MarketAmountView,
    ReviewTradesQuery,
    SourceConflict,
    SourceStamp,
    TapeMinute,
    TradeDecisionContext,
    TradeInput,
    TradeOutcome,
    TradeReviewItem,
    TradeReviewView,
)
from stock_assist.intraday.evidence_providers import (
    EastmoneyIntradayProvider,
    IntradayFetch,
    IntradayProvider,
    TencentIntradayProvider,
)
from stock_assist.intraday.instruments import resolve_benchmark, resolve_instrument

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "intraday-evidence/v1"
DEFAULT_TTL_SECONDS = 20
DEFAULT_STALE_AFTER_SECONDS = 180
PRICE_CONFLICT_TOLERANCE_PCT = 0.30
MAX_COMPARE_SYMBOLS = 20
MAX_REVIEW_TRADES = 100
EnvelopeT = TypeVar("EnvelopeT")


class IntradayEvidenceService:
    """One typed interface shared by CLI and MCP transports."""

    def __init__(
        self,
        *,
        primary: IntradayProvider | None = None,
        fallback: IntradayProvider | None = None,
        now_fn: Callable[[], datetime] | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
        max_workers: int = 6,
    ) -> None:
        self.primary = primary or EastmoneyIntradayProvider()
        self.fallback = fallback or TencentIntradayProvider()
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI))
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.stale_after_seconds = max(30, int(stale_after_seconds))
        self.max_workers = max(1, min(12, int(max_workers)))
        self._cache: dict[tuple[str, str, date], tuple[float, ProviderResult[IntradayTape]]] = {}
        self._cache_lock = Lock()

    def run(self, query: EvidenceQuery) -> EvidenceEnvelope[object]:
        if isinstance(query, GetIntradayQuery):
            return cast(EvidenceEnvelope[object], self.get_intraday(query.symbol, query.trade_date, as_of=query.as_of))
        if isinstance(query, CompareIntradayQuery):
            return cast(
                EvidenceEnvelope[object],
                self.get_intraday_compare(
                    query.symbols,
                    benchmark=query.benchmark,
                    trade_date=query.trade_date,
                    as_of=query.as_of,
                ),
            )
        if isinstance(query, MarketAmountQuery):
            return cast(
                EvidenceEnvelope[object],
                self.get_market_amount_compare(query.trade_date, as_of=query.as_of),
            )
        if isinstance(query, ReviewTradesQuery):
            return cast(
                EvidenceEnvelope[object],
                self.review_trades(
                    query.trades,
                    benchmark=query.benchmark,
                    horizons=query.horizons_minutes,
                ),
            )
        raise TypeError(f"unsupported intraday evidence query: {type(query).__name__}")

    def get_intraday(
        self,
        symbol: str,
        trade_date: date,
        *,
        as_of: time | None = None,
    ) -> EvidenceEnvelope[IntradayView]:
        now = _aware(self._now_fn())
        if trade_date.weekday() >= 5:
            return cast(
                EvidenceEnvelope[IntradayView],
                _empty_envelope(now, "no_data", "non_trading_day"),
            )
        try:
            instrument = resolve_instrument(symbol)
        except ValueError as exc:
            return cast(EvidenceEnvelope[IntradayView], _empty_envelope(now, "blocked", str(exc)))
        resolved = self._resolve_tape(instrument.qualified_symbol, trade_date)
        if resolved.data is None:
            return cast(EvidenceEnvelope[IntradayView], resolved)
        tape = resolved.data
        if as_of is not None:
            tape = replace(
                tape,
                minutes=tuple(item for item in tape.minutes if item.timestamp.time() <= as_of),
            )
        if not tape.minutes:
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="no_data",
                reason="no_minutes_at_or_before_requested_time",
                source_time=resolved.source_time,
                fetched_at=resolved.fetched_at,
                stale_seconds=None,
                data=None,
                provenance=resolved.provenance,
                gaps=resolved.gaps,
                conflicts=resolved.conflicts,
            )
        selected_stamp = (
            resolved.provenance[-1]
            if resolved.reason == "eastmoney_failed_tencent_fallback"
            else resolved.provenance[0]
        )
        view = _intraday_view(tape, source=selected_stamp.provider)
        status = resolved.status
        reason = resolved.reason
        extrema_unknown = not _has_complete_extrema(tape.minutes)
        if extrema_unknown:
            if status == "ok":
                status = "degraded"
            reason = _join_reasons(reason, "minute_extrema_unavailable")
        stale_seconds = _stale_seconds(
            tape.minutes[-1].timestamp,
            now=now,
            requested_date=trade_date,
            as_of=as_of,
        )
        if (
            status in {"ok", "degraded"}
            and stale_seconds is not None
            and stale_seconds > self.stale_after_seconds
        ):
            status = "stale"
            reason = _join_reasons(reason, "latest_minute_exceeds_freshness_gate")
        gaps = resolved.gaps + (
            ("minute_extrema_unavailable",) if extrema_unknown else ()
        ) + (
            ("latest_minute_exceeds_freshness_gate",) if status == "stale" else ()
        )
        return EvidenceEnvelope(
            schema_version=resolved.schema_version,
            status=status,
            reason=reason,
            source_time=tape.minutes[-1].timestamp,
            fetched_at=resolved.fetched_at,
            stale_seconds=stale_seconds,
            data=view,
            provenance=resolved.provenance,
            gaps=tuple(dict.fromkeys(gaps)),
            conflicts=resolved.conflicts,
            analysis_authority=resolved.analysis_authority,
            trade_authority=resolved.trade_authority,
        )

    def get_intraday_compare(
        self,
        symbols: Sequence[str],
        *,
        benchmark: str,
        trade_date: date,
        as_of: time | None = None,
    ) -> EvidenceEnvelope[IntradayCompareView]:
        now = _aware(self._now_fn())
        try:
            benchmark_ref = resolve_benchmark(benchmark)
        except ValueError as exc:
            return cast(
                EvidenceEnvelope[IntradayCompareView],
                _empty_envelope(now, "blocked", str(exc)),
            )
        unique_symbols = tuple(dict.fromkeys(str(item).strip() for item in symbols if str(item).strip()))
        if not unique_symbols:
            return cast(
                EvidenceEnvelope[IntradayCompareView],
                _empty_envelope(now, "blocked", "symbols_required"),
            )
        if len(unique_symbols) > MAX_COMPARE_SYMBOLS:
            return cast(
                EvidenceEnvelope[IntradayCompareView],
                _empty_envelope(now, "blocked", f"symbols_exceed_limit_{MAX_COMPARE_SYMBOLS}"),
            )
        requests = unique_symbols + (benchmark_ref.qualified_symbol,)
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(requests))) as executor:
            results = list(
                executor.map(
                    lambda item: self.get_intraday(item, trade_date, as_of=as_of),
                    requests,
                )
            )
        usable_views = [item.data for item in results if item.data is not None]
        common_minutes: set[str] | None = None
        for available_view in usable_views:
            observed = {item.time for item in available_view.minutes}
            common_minutes = observed if common_minutes is None else common_minutes & observed
        alignment_reason: str | None = None
        comparison_time: time | None = None
        if len(usable_views) >= 2 and common_minutes:
            comparison_time = time.fromisoformat(max(common_minutes))
            latest_times = {view.minutes[-1].time for view in usable_views if view.minutes}
            if latest_times != {comparison_time.isoformat(timespec="minutes")}:
                alignment_reason = "aligned_to_latest_common_minute"
                with ThreadPoolExecutor(max_workers=min(self.max_workers, len(requests))) as executor:
                    results = list(
                        executor.map(
                            lambda item: self.get_intraday(item, trade_date, as_of=comparison_time),
                            requests,
                        )
                    )
        elif usable_views:
            alignment_reason = "no_common_comparison_minute"
        benchmark_result = results[-1]
        benchmark_return = (
            _return_from_open(benchmark_result.data)
            if alignment_reason != "no_common_comparison_minute"
            else None
        )
        rows: list[IntradayCompareRow] = []
        ranked: list[tuple[int, float]] = []
        for index, (requested, result) in enumerate(zip(unique_symbols, results[:-1])):
            view = result.data
            own_return = _return_from_open(view)
            relative = (
                own_return - benchmark_return
                if own_return is not None and benchmark_return is not None
                else None
            )
            if relative is not None:
                ranked.append((index, relative))
            rows.append(
                IntradayCompareRow(
                    symbol=view.symbol if view else requested,
                    qualified_symbol=view.qualified_symbol if view else requested,
                    name=view.name if view else None,
                    time=view.minutes[-1].time if view and view.minutes else None,
                    return_from_open=own_return,
                    return_5m=view.return_5m if view else None,
                    return_15m=view.return_15m if view else None,
                    distance_to_vwap_pct=view.distance_to_vwap_pct if view else None,
                    distance_to_high_pct=view.distance_to_high_pct if view else None,
                    volume_acceleration=view.volume_acceleration if view else None,
                    relative_strength_vs_benchmark=relative,
                    rank=None,
                    status=result.status,
                    reason=result.reason,
                )
            )
        ranks = {
            row_index: rank
            for rank, (row_index, _) in enumerate(
                sorted(ranked, key=lambda item: item[1], reverse=True), start=1
            )
        }
        rows = [replace(item, rank=ranks.get(index)) for index, item in enumerate(rows)]
        all_results = results
        status = _combined_status(all_results)
        reason = _combined_reason(all_results, status)
        if alignment_reason is not None:
            if status == "ok":
                status = "degraded"
            reason = _join_reasons(reason, alignment_reason)
        provenance = _unique_provenance(all_results)
        source_times = [item.source_time for item in all_results if item.source_time is not None]
        conflicts = tuple(conflict for item in all_results for conflict in item.conflicts)
        gaps = tuple(
            dict.fromkeys(
                [gap for item in all_results for gap in item.gaps]
                + ([alignment_reason] if alignment_reason else [])
            )
        )
        return EvidenceEnvelope(
            schema_version=SCHEMA_VERSION,
            status=status,
            reason=reason,
            source_time=min(source_times) if source_times else None,
            fetched_at=max((item.fetched_at for item in all_results), default=now),
            stale_seconds=max(
                (item.stale_seconds for item in all_results if item.stale_seconds is not None),
                default=None,
            ),
            data=IntradayCompareView(
                trade_date=trade_date.isoformat(),
                requested_time=as_of.isoformat(timespec="minutes") if as_of else None,
                benchmark=benchmark_ref.qualified_symbol,
                rows=tuple(rows),
            ),
            provenance=provenance,
            gaps=gaps,
            conflicts=conflicts,
        )

    def get_market_amount_compare(
        self,
        trade_date: date,
        *,
        as_of: time | None = None,
    ) -> EvidenceEnvelope[MarketAmountView]:
        now = _aware(self._now_fn())
        if trade_date.weekday() >= 5:
            return cast(
                EvidenceEnvelope[MarketAmountView],
                _empty_envelope(now, "no_data", "non_trading_day"),
            )
        sh = resolve_benchmark("000001")
        sz = resolve_benchmark("399001")
        primary = self._amount_from_provider(self.primary, sh, sz, trade_date, as_of)
        if primary.data is not None and primary.status == "ok":
            return _apply_freshness(
                primary,
                now=now,
                requested_date=trade_date,
                as_of=as_of,
                stale_after_seconds=self.stale_after_seconds,
            )
        fallback = self._amount_from_provider(self.fallback, sh, sz, trade_date, as_of)
        provenance = _unique_provenance((primary, fallback))
        if fallback.data is not None:
            return _apply_freshness(
                replace(
                    fallback,
                    status="degraded",
                    reason="eastmoney_failed_tencent_fallback",
                    provenance=provenance,
                    gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
                ),
                now=now,
                requested_date=trade_date,
                as_of=as_of,
                stale_after_seconds=self.stale_after_seconds,
            )
        if primary.data is not None:
            return _apply_freshness(
                replace(
                    primary,
                    status="degraded",
                    reason=_join_reasons(primary.reason, "tencent_fallback_unavailable"),
                    provenance=provenance,
                    gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
                ),
                now=now,
                requested_date=trade_date,
                as_of=as_of,
                stale_after_seconds=self.stale_after_seconds,
            )
        status: EvidenceStatus = (
            "blocked" if primary.status == "blocked" or fallback.status == "blocked" else "no_data"
        )
        return EvidenceEnvelope(
            schema_version=SCHEMA_VERSION,
            status=status,
            reason="market_amount_sources_unavailable",
            source_time=None,
            fetched_at=max(primary.fetched_at, fallback.fetched_at),
            stale_seconds=None,
            data=None,
            provenance=provenance,
            gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
        )

    def review_trades(
        self,
        trades: Sequence[TradeInput],
        *,
        benchmark: str,
        horizons: Sequence[int] = (5, 15, 30),
    ) -> EvidenceEnvelope[TradeReviewView]:
        now = _aware(self._now_fn())
        try:
            benchmark_ref = resolve_benchmark(benchmark)
        except ValueError as exc:
            return cast(
                EvidenceEnvelope[TradeReviewView],
                _empty_envelope(now, "blocked", str(exc)),
            )
        normalized_horizons = tuple(sorted({int(item) for item in horizons if int(item) > 0}))
        if normalized_horizons != (5, 15, 30):
            return cast(
                EvidenceEnvelope[TradeReviewView],
                _empty_envelope(now, "blocked", "horizons_must_be_5_15_30"),
            )
        if not trades:
            return cast(
                EvidenceEnvelope[TradeReviewView],
                _empty_envelope(now, "blocked", "trades_required"),
            )
        if len(trades) > MAX_REVIEW_TRADES:
            return cast(
                EvidenceEnvelope[TradeReviewView],
                _empty_envelope(now, "blocked", f"trades_exceed_limit_{MAX_REVIEW_TRADES}"),
            )
        cache: dict[tuple[str, date], EvidenceEnvelope[IntradayTape]] = {}

        def resolved(symbol: str, day: date, *, is_benchmark: bool = False) -> EvidenceEnvelope[IntradayTape]:
            ref = resolve_benchmark(symbol) if is_benchmark else resolve_instrument(symbol)
            key = (ref.qualified_symbol, day)
            if key not in cache:
                cache[key] = _apply_freshness(
                    self._resolve_tape(ref.qualified_symbol, day),
                    now=now,
                    requested_date=day,
                    as_of=None,
                    stale_after_seconds=self.stale_after_seconds,
                )
            return cache[key]

        items: list[TradeReviewItem] = []
        for trade in trades:
            if (
                not math.isfinite(trade.quantity)
                or not math.isfinite(trade.price)
                or trade.quantity <= 0
                or trade.price <= 0
            ):
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="blocked",
                        reason="trade_quantity_and_price_must_be_positive",
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            if trade.trade_date.weekday() >= 5:
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="no_data",
                        reason="non_trading_day",
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            if trade.trade_date > now.date():
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="blocked",
                        reason="future_trade_date",
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            if not _is_continuous_trading_time(trade.time):
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="blocked",
                        reason="outside_continuous_trading_session",
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            trade_at = datetime.combine(trade.trade_date, trade.time, tzinfo=SHANGHAI)
            if trade.trade_date == now.date() and trade_at > now:
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="blocked",
                        reason="current_time_before_trade_time",
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            try:
                series = resolved(trade.symbol, trade.trade_date)
                benchmark_series = resolved(benchmark_ref.qualified_symbol, trade.trade_date, is_benchmark=True)
            except ValueError as exc:
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status="blocked",
                        reason=str(exc),
                        decision_context=None,
                        outcome=None,
                    )
                )
                continue
            if series.data is None:
                items.append(
                    TradeReviewItem(
                        trade=trade,
                        benchmark=benchmark_ref.qualified_symbol,
                        status=series.status,
                        reason=series.reason,
                        decision_context=None,
                        outcome=None,
                        provenance=series.provenance,
                        gaps=series.gaps,
                    )
                )
                continue
            item = _review_one_trade(
                trade,
                tape=series.data,
                benchmark=benchmark_series.data,
                benchmark_symbol=benchmark_ref.qualified_symbol,
                horizons=normalized_horizons,
                base_status=_review_status(series, benchmark_series),
                base_reason=_review_reason(series, benchmark_series),
                provenance=_unique_provenance((series, benchmark_series)),
                gaps=tuple(
                    dict.fromkeys(
                        series.gaps
                        + benchmark_series.gaps
                        + (("benchmark_unavailable",) if benchmark_series.data is None else ())
                    )
                ),
            )
            items.append(item)
        item_statuses = [item.status for item in items]
        status = _combined_status_values(item_statuses)
        source_times = [stamp.source_time for item in items for stamp in item.provenance if stamp.source_time]
        fetched = [stamp.fetched_at for item in items for stamp in item.provenance]
        stale_values = [
            result.stale_seconds
            for result in cache.values()
            if result.stale_seconds is not None
        ]
        return EvidenceEnvelope(
            schema_version=SCHEMA_VERSION,
            status=status,
            reason=None if status == "ok" else "one_or_more_trade_reviews_incomplete",
            source_time=max(source_times) if source_times else None,
            fetched_at=max(fetched, default=now),
            stale_seconds=max(stale_values, default=None),
            data=TradeReviewView(
                trades=tuple(items),
                summary={
                    "trade_count": len(items),
                    "ok_count": sum(item.status == "ok" for item in items),
                    "degraded_count": sum(item.status == "degraded" for item in items),
                    "pending_outcome_count": sum(
                        bool(item.outcome and item.outcome.pending_horizons) for item in items
                    ),
                    "decision_quality_label": "not_assigned_by_tool",
                    "outcome_quality_label": "facts_only",
                },
            ),
            provenance=_unique_stamps(stamp for item in items for stamp in item.provenance),
            gaps=tuple(dict.fromkeys(gap for item in items for gap in item.gaps)),
        )

    def _resolve_tape(
        self,
        qualified_symbol: str,
        trade_date: date,
    ) -> EvidenceEnvelope[IntradayTape]:
        now = _aware(self._now_fn())
        try:
            instrument = resolve_instrument(qualified_symbol)
        except ValueError:
            try:
                instrument = resolve_benchmark(qualified_symbol)
            except ValueError as exc:
                return cast(
                    EvidenceEnvelope[IntradayTape],
                    _empty_envelope(now, "blocked", str(exc)),
                )
        primary = self._fetch_cached(self.primary, IntradayFetch(instrument, trade_date))
        primary_stamp = _stamp(primary, "Eastmoney trends2/get")
        if _provider_usable(primary) and primary.status == "ok":
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="ok",
                reason=None,
                source_time=primary.source_time,
                fetched_at=primary.fetched_at,
                stale_seconds=None,
                data=primary.data,
                provenance=(primary_stamp,),
                gaps=primary.gaps,
            )
        fallback = self._fetch_cached(self.fallback, IntradayFetch(instrument, trade_date))
        fallback_stamp = _stamp(fallback, "Tencent minute/query")
        provenance = (primary_stamp, fallback_stamp)
        if _provider_usable(primary):
            conflicts = _detect_conflicts(primary.data, fallback.data if _provider_usable(fallback) else None)
            reason = "source_conflict" if conflicts else "eastmoney_partial"
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="degraded",
                reason=reason,
                source_time=primary.source_time,
                fetched_at=max(primary.fetched_at, fallback.fetched_at),
                stale_seconds=None,
                data=primary.data,
                provenance=provenance,
                gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
                conflicts=conflicts,
            )
        if _provider_usable(fallback):
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="degraded",
                reason="eastmoney_failed_tencent_fallback",
                source_time=fallback.source_time,
                fetched_at=max(primary.fetched_at, fallback.fetched_at),
                stale_seconds=None,
                data=fallback.data,
                provenance=provenance,
                gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
            )
        if primary.price_basis != "unadjusted" or fallback.price_basis != "unadjusted":
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="blocked",
                reason="unsupported_price_basis",
                source_time=None,
                fetched_at=max(primary.fetched_at, fallback.fetched_at),
                stale_seconds=None,
                data=None,
                provenance=provenance,
                gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps + ("unadjusted_prices_required",))),
            )
        statuses = {primary.status, fallback.status}
        status: EvidenceStatus = "blocked" if statuses & {"invalid", "quarantined"} else "no_data"
        reason = "all_providers_failed" if status == "blocked" else "requested_trade_date_unavailable"
        return EvidenceEnvelope(
            schema_version=SCHEMA_VERSION,
            status=status,
            reason=reason,
            source_time=None,
            fetched_at=max(primary.fetched_at, fallback.fetched_at),
            stale_seconds=None,
            data=None,
            provenance=provenance,
            gaps=tuple(dict.fromkeys(primary.gaps + fallback.gaps)),
        )

    def _fetch_cached(
        self,
        provider: IntradayProvider,
        request: IntradayFetch,
    ) -> ProviderResult[IntradayTape]:
        key = (provider.provider_id, request.instrument.qualified_symbol, request.trade_date)
        current = monotonic_time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None and current - cached[0] <= self.ttl_seconds:
                return cached[1]
        result = provider.fetch(request)
        with self._cache_lock:
            self._cache[key] = (current, result)
        return result

    def _amount_from_provider(
        self,
        provider: IntradayProvider,
        sh: InstrumentRef,
        sz: InstrumentRef,
        trade_date: date,
        as_of: time | None,
    ) -> EvidenceEnvelope[MarketAmountView]:
        now = _aware(self._now_fn())
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(provider.fetch_recent, instrument, through_date=trade_date)
                for instrument in (sh, sz)
            ]
            results = [future.result() for future in futures]
        stamps = tuple(
            _stamp(result, f"{provider.provider_id} recent minute amount") for result in results
        )
        if not all(result.status in {"ok", "partial"} and result.data for result in results):
            unavailable_status: EvidenceStatus = (
                "blocked"
                if any(result.status in {"invalid", "quarantined"} for result in results)
                else "no_data"
            )
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status=unavailable_status,
                reason="market_amount_provider_unavailable",
                source_time=None,
                fetched_at=max((result.fetched_at for result in results), default=now),
                stale_seconds=None,
                data=None,
                provenance=stamps,
                gaps=tuple(dict.fromkeys(gap for result in results for gap in result.gaps)),
            )
        by_market = [
            {item.trade_date: item for item in cast(tuple[IntradayTape, ...], result.data)}
            for result in results
        ]
        common_dates = sorted(set(by_market[0]) & set(by_market[1]))
        eligible = [item for item in common_dates if item <= trade_date]
        if len(eligible) < 2 or trade_date not in eligible:
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="no_data",
                reason="fewer_than_two_common_trading_dates",
                source_time=None,
                fetched_at=max(result.fetched_at for result in results),
                stale_seconds=None,
                data=None,
                provenance=stamps,
                gaps=("same_time_amount_requires_current_and_previous_session",),
            )
        previous_date = eligible[eligible.index(trade_date) - 1]
        selected = (
            by_market[0][trade_date],
            by_market[1][trade_date],
            by_market[0][previous_date],
            by_market[1][previous_date],
        )
        common_times = set(_minute_times(selected[0]))
        for tape in selected[1:]:
            common_times &= set(_minute_times(tape))
        if as_of is not None:
            common_times = {item for item in common_times if item <= as_of}
        if not common_times:
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="no_data",
                reason="no_common_same_time_minute",
                source_time=None,
                fetched_at=max(result.fetched_at for result in results),
                stale_seconds=None,
                data=None,
                provenance=stamps,
            )
        aligned_time = max(common_times)
        amounts = [_cumulative_amount(tape, aligned_time) for tape in selected]
        if any(item is None for item in amounts):
            return EvidenceEnvelope(
                schema_version=SCHEMA_VERSION,
                status="blocked",
                reason="minute_amount_semantics_unavailable",
                source_time=None,
                fetched_at=max(result.fetched_at for result in results),
                stale_seconds=None,
                data=None,
                provenance=stamps,
                gaps=("amount_must_be_incremental_cny",),
            )
        numeric_amounts = cast(list[float], amounts)
        today_amount = numeric_amounts[0] + numeric_amounts[1]
        previous_amount = numeric_amounts[2] + numeric_amounts[3]
        delta = today_amount - previous_amount
        data = MarketAmountView(
            market="CN_A",
            trade_date=trade_date.isoformat(),
            previous_trade_date=previous_date.isoformat(),
            time=aligned_time.isoformat(timespec="minutes"),
            today_amount=today_amount,
            previous_day_same_time_amount=previous_amount,
            delta=delta,
            delta_pct=_pct(delta, previous_amount),
        )
        source_times = [result.source_time for result in results if result.source_time]
        status: EvidenceStatus = "degraded" if any(result.status == "partial" for result in results) else "ok"
        return EvidenceEnvelope(
            schema_version=SCHEMA_VERSION,
            status=status,
            reason="provider_partial" if status == "degraded" else None,
            source_time=min(source_times) if source_times else None,
            fetched_at=max(result.fetched_at for result in results),
            stale_seconds=None,
            data=data,
            provenance=stamps,
            gaps=tuple(dict.fromkeys(gap for result in results for gap in result.gaps)),
        )


def default_service() -> IntradayEvidenceService:
    return IntradayEvidenceService()


def evidence_to_dict(value: object) -> object:
    """Serialize evidence while preserving unknown as JSON null, never zero."""

    if is_dataclass(value):
        return evidence_to_dict(asdict(cast(Any, value)))
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Mapping):
        return {str(key): evidence_to_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [evidence_to_dict(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _intraday_view(tape: IntradayTape, *, source: str) -> IntradayView:
    minutes = tape.minutes
    first = minutes[0]
    last = minutes[-1]
    high, low = _session_extrema(minutes)
    vwap = _vwap(minutes)
    return IntradayView(
        symbol=tape.instrument.code,
        qualified_symbol=tape.instrument.qualified_symbol,
        name=tape.name,
        market=tape.instrument.market,
        trade_date=tape.trade_date.isoformat(),
        source=source,
        pre_close=tape.pre_close,
        open=first.price,
        last=last.price,
        high=high,
        low=low,
        day_pct=_return_pct(last.price, tape.pre_close),
        vwap=vwap,
        return_5m=_trailing_return(minutes, 5),
        return_15m=_trailing_return(minutes, 15),
        return_30m=_trailing_return(minutes, 30),
        distance_to_vwap_pct=_return_pct(last.price, vwap),
        distance_to_high_pct=_return_pct(last.price, high),
        volume_acceleration=_volume_acceleration(minutes),
        minutes=tuple(
            IntradayMinuteView(
                time=item.timestamp.strftime("%H:%M"),
                price=item.price,
                avg_price=item.avg_price,
                volume=item.volume,
                amount=item.amount,
            )
            for item in minutes
        ),
        amount_unit=tape.amount_unit,
        volume_unit=tape.volume_unit,
    )


def _review_one_trade(
    trade: TradeInput,
    *,
    tape: IntradayTape,
    benchmark: IntradayTape | None,
    benchmark_symbol: str,
    horizons: tuple[int, ...],
    base_status: EvidenceStatus,
    base_reason: str | None,
    provenance: tuple[SourceStamp, ...],
    gaps: tuple[str, ...],
) -> TradeReviewItem:
    trade_at = datetime.combine(trade.trade_date, trade.time, tzinfo=SHANGHAI)
    completed_cutoff = trade_at.replace(second=0, microsecond=0) - timedelta(minutes=1)
    before = tuple(item for item in tape.minutes if item.timestamp <= completed_cutoff)
    if not before:
        return TradeReviewItem(
            trade=trade,
            benchmark=benchmark_symbol,
            status="blocked" if tape.minutes and tape.minutes[0].timestamp > trade_at else "no_data",
            reason="trade_time_not_observed",
            decision_context=None,
            outcome=None,
            provenance=provenance,
            gaps=gaps + ("no_completed_minute_before_trade",),
        )
    latest = before[-1]
    vwap = _vwap(before)
    day_high, day_low = _session_extrema(before)
    context_extrema_unknown = day_high is None or day_low is None
    benchmark_before = (
        tuple(item for item in benchmark.minutes if item.timestamp <= completed_cutoff)
        if benchmark is not None else ()
    )
    own_from_open = _return_pct(latest.price, before[0].price)
    benchmark_from_open = (
        _return_pct(benchmark_before[-1].price, benchmark_before[0].price)
        if benchmark_before else None
    )
    relative_strength = (
        own_from_open - benchmark_from_open
        if own_from_open is not None and benchmark_from_open is not None else None
    )
    volume_acceleration = _volume_acceleration(before)
    previous_volumes = [item.volume for item in before[-6:-1] if item.volume is not None]
    avg_previous_volume = (
        sum(previous_volumes) / len(previous_volumes) if previous_volumes else None
    )
    before_5 = _trailing_return(before, 5)
    before_15 = _trailing_return(before, 15)
    trend = _trend_label(before_5, before_15, relative_strength)
    context = TradeDecisionContext(
        evidence_time=latest.timestamp.isoformat(timespec="minutes"),
        trade_price=trade.price,
        vwap=vwap,
        distance_to_vwap_pct=_return_pct(trade.price, vwap),
        day_high=day_high,
        day_low=day_low,
        distance_to_high_pct=_return_pct(trade.price, day_high),
        distance_to_low_pct=_return_pct(trade.price, day_low),
        range_position_pct=(
            (trade.price - day_low) / (day_high - day_low) * 100.0
            if day_high is not None and day_low is not None and day_high > day_low else None
        ),
        return_before_5m=before_5,
        return_before_15m=before_15,
        relative_strength_vs_benchmark=relative_strength,
        current_minute_volume=latest.volume,
        average_volume_previous_5m=avg_previous_volume,
        volume_acceleration=volume_acceleration,
        above_vwap=trade.price >= vwap if vwap is not None else None,
        near_day_high=(trade.price >= day_high * 0.99) if day_high is not None and day_high > 0 else None,
        volume_confirmation=(volume_acceleration >= 1.2) if volume_acceleration is not None else None,
        trend=trend,
    )
    outcome, pending, outcome_extrema_unknown = _trade_outcome(
        trade, tape.minutes, trade_at, horizons
    )
    extrema_unknown = context_extrema_unknown or outcome_extrema_unknown
    status = base_status
    reason = base_reason
    if pending and status == "ok":
        status = "degraded"
        reason = "outcome_horizon_pending"
    if extrema_unknown:
        if status == "ok":
            status = "degraded"
        reason = _join_reasons(reason, "minute_extrema_unavailable")
    return TradeReviewItem(
        trade=trade,
        benchmark=benchmark_symbol,
        status=status,
        reason=reason,
        decision_context=context,
        outcome=outcome,
        provenance=provenance,
        gaps=tuple(
            dict.fromkeys(
                gaps
                + (("outcome_horizon_pending",) if pending else ())
                + (("minute_extrema_unavailable",) if extrema_unknown else ())
            )
        ),
    )


def _trade_outcome(
    trade: TradeInput,
    minutes: tuple[TapeMinute, ...],
    trade_at: datetime,
    horizons: tuple[int, ...],
) -> tuple[TradeOutcome, tuple[int, ...], bool]:
    returns: dict[int, float | None] = {}
    maes: dict[int, float | None] = {}
    mfes: dict[int, float | None] = {}
    up: dict[int, float | None] = {}
    down: dict[int, float | None] = {}
    pending: list[int] = []
    extrema_unknown = False
    after = tuple(item for item in minutes if item.timestamp > trade_at)
    for horizon in horizons:
        horizon_start = trade_at.replace(second=0, microsecond=0)
        target = _shift_market_minutes(horizon_start, horizon)
        through = tuple(item for item in after if item.timestamp <= target)
        endpoint = through[-1] if through else None
        if not minutes or minutes[-1].timestamp < target or endpoint is None:
            pending.append(horizon)
            returns[horizon] = None
        else:
            returns[horizon] = _return_pct(endpoint.price, trade.price)
        if not through:
            maes[horizon] = mfes[horizon] = up[horizon] = down[horizon] = None
            continue
        if any(item.high is None or item.low is None for item in through):
            extrema_unknown = True
            maes[horizon] = mfes[horizon] = up[horizon] = down[horizon] = None
            continue
        upward = [_return_pct(item.high, trade.price) for item in through]
        downward = [_return_pct(item.low, trade.price) for item in through]
        upward_numeric = [item for item in upward if item is not None]
        downward_numeric = [item for item in downward if item is not None]
        max_up = max(0.0, max(upward_numeric)) if upward_numeric else None
        max_down = min(0.0, min(downward_numeric)) if downward_numeric else None
        up[horizon] = max_up
        down[horizon] = max_down
        if trade.side == "buy":
            mfes[horizon] = max_up
            maes[horizon] = max_down
        else:
            mfes[horizon] = None
            maes[horizon] = None
    return (
        TradeOutcome(
            return_after_5m=returns.get(5),
            return_after_15m=returns.get(15),
            return_after_30m=returns.get(30),
            mae_5m=maes.get(5),
            mae_15m=maes.get(15),
            mae_30m=maes.get(30),
            mfe_5m=mfes.get(5),
            mfe_15m=mfes.get(15),
            mfe_30m=mfes.get(30),
            max_continue_up_5m=up.get(5) if trade.side == "sell" else None,
            max_continue_up_15m=up.get(15) if trade.side == "sell" else None,
            max_continue_up_30m=up.get(30) if trade.side == "sell" else None,
            max_down_5m=down.get(5) if trade.side == "sell" else None,
            max_down_15m=down.get(15) if trade.side == "sell" else None,
            max_down_30m=down.get(30) if trade.side == "sell" else None,
            pending_horizons=tuple(pending),
        ),
        tuple(pending),
        extrema_unknown,
    )


def _provider_usable(result: ProviderResult[IntradayTape]) -> bool:
    return (
        result.status in {"ok", "partial"}
        and result.price_basis == "unadjusted"
        and bool(result.data.minutes)
    )


def _stamp(result: ProviderResult[object], source: str) -> SourceStamp:
    data = result.data
    if isinstance(data, IntradayTape):
        symbol = data.instrument.qualified_symbol
    elif isinstance(data, tuple) and data and isinstance(data[0], IntradayTape):
        symbol = data[0].instrument.qualified_symbol
    else:
        symbol = None
    return SourceStamp(
        provider=result.provider,
        source=source,
        symbol=symbol,
        provider_status=result.status,
        source_time=result.source_time,
        fetched_at=result.fetched_at,
        trade_date=result.trade_date,
        gaps=result.gaps,
        errors=result.errors,
    )


def _detect_conflicts(
    primary: IntradayTape,
    fallback: IntradayTape | None,
) -> tuple[SourceConflict, ...]:
    if fallback is None or fallback.trade_date != primary.trade_date:
        return ()
    primary_by_time = {item.timestamp: item for item in primary.minutes}
    fallback_by_time = {item.timestamp: item for item in fallback.minutes}
    common = sorted(set(primary_by_time) & set(fallback_by_time))
    if not common:
        return ()
    conflicts = []
    for stamp in common:
        left = primary_by_time[stamp].price
        right = fallback_by_time[stamp].price
        difference = abs(_return_pct(left, right) or 0.0)
        if difference > PRICE_CONFLICT_TOLERANCE_PCT:
            conflicts.append(
                SourceConflict(
                    primary_provider="eastmoney",
                    fallback_provider="tencent",
                    field=f"price@{stamp.isoformat(timespec='minutes')}",
                    primary_value=left,
                    fallback_value=right,
                    tolerance=PRICE_CONFLICT_TOLERANCE_PCT,
                )
            )
    return tuple(conflicts)


def _vwap(minutes: Sequence[TapeMinute]) -> float | None:
    for item in reversed(minutes):
        if item.avg_price is not None and item.avg_price > 0:
            return item.avg_price
    amount = sum(item.amount for item in minutes if item.amount is not None and item.amount >= 0)
    volume = sum(item.volume for item in minutes if item.volume is not None and item.volume >= 0)
    if amount <= 0 or volume <= 0:
        return None
    candidate = amount / volume
    last = minutes[-1].price
    return candidate if 0.5 * last <= candidate <= 1.5 * last else None


def _trailing_return(minutes: Sequence[TapeMinute], window_minutes: int) -> float | None:
    if len(minutes) < 2:
        return None
    target = _shift_market_minutes(minutes[-1].timestamp, -window_minutes)
    reference = next((item for item in reversed(minutes[:-1]) if item.timestamp <= target), None)
    return _return_pct(minutes[-1].price, reference.price) if reference else None


def _volume_acceleration(minutes: Sequence[TapeMinute]) -> float | None:
    if len(minutes) < 2 or minutes[-1].volume is None:
        return None
    previous = [item.volume for item in minutes[-6:-1] if item.volume is not None]
    if not previous:
        return None
    average = sum(previous) / len(previous)
    return minutes[-1].volume / average if average > 0 else None


def _return_pct(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0:
        return None
    return (value / reference - 1.0) * 100.0


def _pct(value: float, reference: float) -> float | None:
    return value / reference * 100.0 if reference > 0 else None


def _return_from_open(view: IntradayView | None) -> float | None:
    return _return_pct(view.last, view.open) if view is not None else None


def _minute_times(tape: IntradayTape) -> tuple[time, ...]:
    return tuple(item.timestamp.time().replace(tzinfo=None) for item in tape.minutes)


def _cumulative_amount(tape: IntradayTape, through: time) -> float | None:
    if tape.amount_kind != "incremental" or tape.amount_unit != "CNY":
        return None
    eligible = [
        item
        for item in tape.minutes
        if item.timestamp.time().replace(tzinfo=None) <= through
    ]
    if not eligible or any(item.amount is None for item in eligible):
        return None
    return sum(cast(float, item.amount) for item in eligible)


def _has_complete_extrema(minutes: Sequence[TapeMinute]) -> bool:
    return bool(minutes) and all(
        item.high is not None and item.low is not None for item in minutes
    )


def _session_extrema(
    minutes: Sequence[TapeMinute],
) -> tuple[float | None, float | None]:
    if not _has_complete_extrema(minutes):
        return None, None
    highs = [cast(float, item.high) for item in minutes]
    lows = [cast(float, item.low) for item in minutes]
    return max(highs), min(lows)


def _stale_seconds(
    source_time: datetime,
    *,
    now: datetime,
    requested_date: date,
    as_of: time | None,
) -> float | None:
    if requested_date != now.date() or as_of is not None:
        return None
    current_time = now.time().replace(tzinfo=None)
    if current_time < time(9, 30):
        return None
    return _continuous_trading_seconds(source_time, now)


def _continuous_trading_seconds(start: datetime, end: datetime) -> float:
    if end <= start:
        return 0.0
    trading_date = end.astimezone(SHANGHAI).date()
    total = 0.0
    for session_start, session_end in (
        (time(9, 30), time(11, 30)),
        (time(13, 0), time(15, 0)),
    ):
        lower = datetime.combine(trading_date, session_start, tzinfo=SHANGHAI)
        upper = datetime.combine(trading_date, session_end, tzinfo=SHANGHAI)
        overlap_start = max(start, lower)
        overlap_end = min(end, upper)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds()
    return total


def _trend_label(
    return_5m: float | None,
    return_15m: float | None,
    relative_strength: float | None,
) -> Literal["strong", "weak", "mixed", "unknown"]:
    values = [item for item in (return_5m, return_15m, relative_strength) if item is not None]
    if not values:
        return "unknown"
    if all(item > 0 for item in values):
        return "strong"
    if all(item < 0 for item in values):
        return "weak"
    return "mixed"


def _is_continuous_trading_time(value: time) -> bool:
    return time(9, 30) <= value <= time(11, 30) or time(13, 0) <= value <= time(15, 0)


def _review_status(
    series: EvidenceEnvelope[IntradayTape],
    benchmark: EvidenceEnvelope[IntradayTape],
) -> EvidenceStatus:
    if series.status in {"blocked", "no_data", "stale"}:
        return series.status
    if benchmark.status == "stale":
        return "stale"
    if series.status == "degraded" or benchmark.status != "ok" or benchmark.data is None:
        return "degraded"
    return "ok"


def _review_reason(
    series: EvidenceEnvelope[IntradayTape],
    benchmark: EvidenceEnvelope[IntradayTape],
) -> str | None:
    reason = series.reason
    if benchmark.status != "ok" or benchmark.data is None:
        reason = _join_reasons(reason, f"benchmark_{benchmark.reason or benchmark.status}")
    return reason


def _apply_freshness(
    result: EvidenceEnvelope[EnvelopeT],
    *,
    now: datetime,
    requested_date: date,
    as_of: time | None,
    stale_after_seconds: int,
) -> EvidenceEnvelope[EnvelopeT]:
    if result.data is None or result.source_time is None:
        return result
    stale_seconds = _stale_seconds(
        result.source_time,
        now=now,
        requested_date=requested_date,
        as_of=as_of,
    )
    status = result.status
    reason = result.reason
    gaps = result.gaps
    if (
        status in {"ok", "degraded"}
        and stale_seconds is not None
        and stale_seconds > stale_after_seconds
    ):
        status = "stale"
        reason = _join_reasons(reason, "latest_minute_exceeds_freshness_gate")
        gaps = tuple(dict.fromkeys(gaps + ("latest_minute_exceeds_freshness_gate",)))
    return replace(
        result,
        status=status,
        reason=reason,
        stale_seconds=stale_seconds,
        gaps=gaps,
    )


def _join_reasons(*values: str | None) -> str | None:
    reasons = tuple(dict.fromkeys(item for item in values if item))
    return ";".join(reasons) if reasons else None


def _combined_status(results: Sequence[EvidenceEnvelope[EnvelopeT]]) -> EvidenceStatus:
    return _combined_status_values([item.status for item in results])


def _combined_status_values(statuses: Sequence[EvidenceStatus]) -> EvidenceStatus:
    if statuses and all(item == "ok" for item in statuses):
        return "ok"
    if any(item == "blocked" for item in statuses):
        return "blocked"
    if any(item == "stale" for item in statuses):
        return "stale"
    if any(item == "degraded" for item in statuses):
        return "degraded"
    return "no_data"


def _combined_reason(
    results: Sequence[EvidenceEnvelope[EnvelopeT]],
    status: EvidenceStatus,
) -> str | None:
    if status == "ok":
        return None
    reasons = tuple(dict.fromkeys(item.reason for item in results if item.reason))
    return ";".join(reasons) if reasons else "one_or_more_series_incomplete"


def _unique_provenance(
    results: Sequence[EvidenceEnvelope[EnvelopeT]],
) -> tuple[SourceStamp, ...]:
    return _unique_stamps(stamp for result in results for stamp in result.provenance)


def _unique_stamps(stamps: Iterable[SourceStamp]) -> tuple[SourceStamp, ...]:
    result: list[SourceStamp] = []
    seen: set[tuple[str, str, str | None, date | None]] = set()
    for stamp in stamps:
        key = (stamp.provider, stamp.source, stamp.symbol, stamp.trade_date)
        if key not in seen:
            seen.add(key)
            result.append(stamp)
    return tuple(result)


def _empty_envelope(
    now: datetime,
    status: EvidenceStatus,
    reason: str,
) -> EvidenceEnvelope[object]:
    return EvidenceEnvelope(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        source_time=None,
        fetched_at=now,
        stale_seconds=None,
        data=None,
        provenance=(),
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)


def _shift_market_minutes(value: datetime, minutes: int) -> datetime:
    """Move over the A-share lunch break without inventing tradable minutes."""

    shifted = value + timedelta(minutes=minutes)
    lunch_start = datetime.combine(value.date(), time(11, 30), tzinfo=SHANGHAI)
    lunch_end = datetime.combine(value.date(), time(13, 0), tzinfo=SHANGHAI)
    if minutes > 0 and value <= lunch_start < shifted:
        shifted += lunch_end - lunch_start
    elif minutes < 0 and shifted < lunch_end <= value:
        shifted -= lunch_end - lunch_start
    return shifted
