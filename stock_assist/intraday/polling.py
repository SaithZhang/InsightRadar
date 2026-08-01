"""Bounded loopback-friendly intraday polling over the local archive seam."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time as clock_time
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock
import time
from typing import Callable, Iterable, Mapping

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.contracts import IntradayAlert, IntradaySnapshot, contract_dict
from stock_assist.intraday.execution import (
    DEFAULT_EXECUTION_LEDGER,
    DEFAULT_REENTRY_FAILURE_LEDGER,
    DEFAULT_REENTRY_CONFIRMATION_LEDGER,
    detect_reentry_failures,
    load_executions,
    load_reentry_failures,
    load_reentry_confirmations,
)
from stock_assist.intraday.providers import (
    EndpointCircuitBreaker,
    fetch_amazingdata_latest_quotes,
    fetch_amazingdata_minute_bars,
    fetch_eastmoney_minute_bars,
)
from stock_assist.intraday.network import (
    declared_provider_routes,
    provider_policy,
    sanitize_diagnostic_text,
    sanitized_error_type,
)
from stock_assist.intraday.session import TradingSessionResolution, resolve_trading_session
from stock_assist.intraday.rules import (
    RULE_VERSION,
    IntradayDecisionEngine,
    ReentryPositionState,
)
from stock_assist.intraday.snapshots import IntradaySnapshotBuilder
from stock_assist.intraday.universe import load_intraday_universe, universe_symbols
from stock_assist.paths import DATA_DIR
from stock_assist.portfolio import load_portfolio


RUNTIME_PATH = DATA_DIR / "intraday" / "runtime.json"
REENTRY_STATE_PATH = DATA_DIR / "intraday" / "reentry_state.json"
SCHEDULER_LOCK_PATH = DATA_DIR / "intraday" / "checkpoint-scheduler.lock"
ALERT_ARCHIVE_ROOT = DATA_DIR / "intraday" / "alerts"
PROVIDER_DIAGNOSTIC_PATH = DATA_DIR / "intraday" / "provider-diagnostics.jsonl"
REFRESH_LOCK_PATH = DATA_DIR / "intraday" / "refresh.lock"
REFRESH_HARD_TIMEOUT_SECONDS = 57.0
_ACTIVE_REFRESH_PROCESS: subprocess.Popen[bytes] | None = None
_ACTIVE_REFRESH_PROCESS_LOCK = Lock()
CHECKPOINTS = (clock_time(9, 25), clock_time(9, 35), clock_time(10, 0))
TECHNOLOGY_THEME_IDS = (
    "ai_hardware_semiconductor",
    "communication_cpo",
    "pcb",
    "ai_software_apps",
    "robot",
    "data_compute",
)


def poll_intraday(
    *,
    iterations: int = 1,
    interval_seconds: int = 60,
    allow_fallback: bool = True,
) -> dict[str, object]:
    """Poll a bounded number of times; every iteration persists one runtime atomically."""

    if not 1 <= iterations <= 240:
        raise ValueError("iterations must be between 1 and 240")
    if not 5 <= interval_seconds <= 60:
        raise ValueError("interval_seconds must be between 5 and 60")
    lock = _acquire_refresh_lock(datetime.now())
    if lock is None:
        existing = load_intraday_runtime() or {}
        return {
            **existing,
            "refresh_single_flight": "already_running",
        }
    try:
        payload: dict[str, object] = {}
        for index in range(iterations):
            payload = poll_intraday_once(
                allow_fallback=allow_fallback,
                persist_progress=True,
            )
            _append_alert_archive(payload)
            _atomic_json(RUNTIME_PATH, payload)
            if index + 1 < iterations:
                time.sleep(interval_seconds)
        return payload
    finally:
        os.close(lock)
        try:
            REFRESH_LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def poll_intraday_once(
    *,
    as_of: datetime | None = None,
    allow_fallback: bool = True,
    persist_progress: bool = False,
    refresh_timeout_seconds: float = 60.0,
) -> dict[str, object]:
    now = as_of or datetime.now()
    previous = load_intraday_runtime()
    universe = load_intraday_universe()
    themes = [dict(item) for item in universe["themes"]]
    symbols = universe_symbols(universe)
    portfolio = load_portfolio()
    symbols = tuple(dict.fromkeys([*symbols, *(item.code.upper() for item in portfolio.holdings)]))
    archive = MinuteArchive()
    started = time.monotonic()
    deadline = started + refresh_timeout_seconds
    failures: dict[str, str] = {}
    bars: list[object] = []
    quotes: list[object] = []
    diagnostics: list[dict[str, object]] = []
    client: AmazingDataClient | None = None

    def progress(
        phase: str,
        *,
        provider: str | None = None,
        batch: int = 0,
        total_batches: int = 0,
        processed: int = 0,
        succeeded: int = 0,
        failed: int = 0,
        missing: int = 0,
        circuit_state: str = "closed",
        next_action: str = "",
        session: TradingSessionResolution | None = None,
    ) -> None:
        if not persist_progress:
            return
        _write_refresh_progress(
            now,
            previous,
            phase=phase,
            provider=provider,
            batch=batch,
            total_batches=total_batches,
            processed=processed,
            total_symbols=len(symbols),
            succeeded=succeeded,
            failed=failed,
            missing=missing,
            circuit_state=circuit_state,
            elapsed_seconds=max(0.0, time.monotonic() - started),
            next_action=next_action,
            session=session,
        )

    progress("resolving_trade_date", next_action="解析A股真实交易日")
    try:
        try:
            client = AmazingDataClient()
        except Exception as exc:
            failures["galaxy_amazingdata:configuration"] = sanitized_error_type(exc)
            _append_provider_diagnostic("galaxy_amazingdata", exc, 0, "failed", 1, "closed")
        session = resolve_trading_session(now, client=client, archive=archive)
        progress(
            "trade_date_resolved",
            provider="galaxy_amazingdata",
            next_action="读取本地不可变行情档案",
            session=session,
        )
        runtime_day = session.runtime_trade_date
        if runtime_day is None:
            return _runtime_envelope(
                now,
                status="blocked",
                data_status="missing",
                freshness_status="missing",
                source_time=None,
                previous=None,
                session=session,
                extra={
                    "latest_snapshot": None,
                    "timeline": [],
                    "active_alerts": [],
                    "opportunity_states": {},
                    "data_gaps": list(session.data_gaps),
                    "provider_status": {"diagnostics": diagnostics},
                },
            )
        if not isinstance(previous, Mapping) or previous.get("trade_date") != runtime_day.isoformat():
            previous = None

        through = now if runtime_day == now.date() else None
        archived = archive.read_bars(
            runtime_day,
            symbols=symbols,
            through=through,
            observed_through=now,
        )
        archived_symbols = set(archived)
        missing_primary = [symbol for symbol in symbols if symbol not in archived_symbols]
        batches = list(_batches(missing_primary, 24))
        succeeded_symbols: set[str] = set(archived_symbols)
        for batch_index, batch in enumerate(batches, start=1):
            if time.monotonic() >= deadline:
                failures.update({symbol: "refresh_total_timeout" for symbol in batch})
                break
            progress(
                "fetching_primary",
                provider="galaxy_amazingdata",
                batch=batch_index,
                total_batches=len(batches),
                processed=len(succeeded_symbols) + len(failures),
                succeeded=len(succeeded_symbols),
                failed=len(failures),
                missing=max(0, len(symbols) - len(succeeded_symbols)),
                next_action="继续读取银河分钟行情",
                session=session,
            )
            try:
                if client is None:
                    raise RuntimeError("AmazingData client unavailable")
                remaining = max(0.1, deadline - time.monotonic())
                fetched_bars = fetch_amazingdata_minute_bars(
                    client,
                    batch,
                    start=runtime_day,
                    end=runtime_day,
                    fetched_at=now,
                    timeout_seconds=min(
                        provider_policy("galaxy_amazingdata").timeout_seconds,
                        remaining,
                    ),
                )
                bars.extend(fetched_bars)
                succeeded_symbols.update(item.symbol for item in fetched_bars)
                if runtime_day == now.date() and session.session_mode in {
                    "preopen", "live", "after_close"
                }:
                    quotes.extend(
                        fetch_amazingdata_latest_quotes(
                            client,
                            batch,
                            as_of=now,
                            fetched_at=now,
                            timeout_seconds=min(
                                provider_policy("galaxy_amazingdata").timeout_seconds,
                                max(0.1, deadline - time.monotonic()),
                            ),
                        )
                    )
                diagnostics.append(
                    _provider_diagnostic(
                        "galaxy_amazingdata",
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        status="success",
                        error_type=None,
                        attempt_count=batch_index,
                        circuit_state="closed",
                    )
                )
            except Exception as exc:
                error_type = sanitized_error_type(exc)
                failures.update({symbol: error_type for symbol in batch})
                _append_provider_diagnostic(
                    "galaxy_amazingdata", exc,
                    int((time.monotonic() - started) * 1000),
                    "failed", batch_index, "closed",
                )
                diagnostics.append(
                    _provider_diagnostic(
                        "galaxy_amazingdata",
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        status="failed",
                        error_type=error_type,
                        attempt_count=batch_index,
                        circuit_state="closed",
                    )
                )
    finally:
        if client is not None:
            client.logout()
    if bars:
        archive.write_bars(bars)
    if quotes:
        archive.write_quotes(quotes)
    archived_today = archive.read_bars(
        runtime_day, symbols=symbols,
        through=now if runtime_day == now.date() else None,
        observed_through=now,
    )
    missing = sorted(set(symbols) - set(archived_today))
    fallback_failures: dict[str, str] = {}
    if allow_fallback and missing and time.monotonic() < deadline:
        progress(
            "fetching_fallback",
            provider="eastmoney_push2his",
            processed=len(symbols) - len(missing),
            succeeded=len(archived_today),
            failed=len(failures),
            missing=len(missing),
            next_action="备用源有界请求并在重复错误后熔断",
            session=session,
        )
        remaining_seconds = max(0.1, min(20.0, deadline - time.monotonic()))
        fallback_result = fetch_eastmoney_minute_bars(
            missing,
            start=runtime_day,
            end=runtime_day,
            fetched_at=now,
            circuit_breaker=EndpointCircuitBreaker(failure_threshold=3),
            include_diagnostics=True,
            total_timeout_seconds=remaining_seconds,
        )
        fallback, fallback_failures, fallback_diagnostic = fallback_result
        diagnostics.append(dict(fallback_diagnostic))
        if fallback:
            archive.write_bars(fallback)
            archived_today = archive.read_bars(
                runtime_day, symbols=symbols,
                through=now if runtime_day == now.date() else None,
                observed_through=now,
            )
            for recovered in {item.symbol for item in fallback}:
                failures.pop(recovered, None)
        progress(
            "fallback_finished",
            provider="eastmoney_push2his",
            processed=len(symbols),
            succeeded=len(archived_today),
            failed=len(fallback_failures),
            missing=max(0, len(symbols) - len(archived_today)),
            circuit_state=str(fallback_diagnostic.get("circuit_state") or "closed"),
            next_action="构建点时快照",
            session=session,
        )
    elif missing and time.monotonic() >= deadline:
        fallback_failures.update({symbol: "refresh_total_timeout" for symbol in missing})
    failures.update(fallback_failures)
    if archived_today:
        detect_reentry_failures(archived_today, rule_version=RULE_VERSION)
    if not archived_today and not quotes:
        return _runtime_envelope(
            now,
            status="blocked",
            data_status="missing" if not failures else "failed",
            freshness_status="missing",
            source_time=None,
            previous=previous,
            session=session,
            extra={
            "latest_snapshot": None,
            "timeline": list(previous.get("timeline", [])) if isinstance(previous, Mapping) else [],
            "active_alerts": list(previous.get("active_alerts", [])) if isinstance(previous, Mapping) else [],
            "opportunity_states": {},
            "data_gaps": [
                "当前交易日没有可见分钟线或快照；页面保留盘后能力，但盘中状态不可用。",
                *_failure_summaries(failures),
                *session.data_gaps,
            ],
            "provider_status": {
                "failed_count": len(failures),
                "diagnostics": diagnostics,
            },
            "refresh_progress": _final_progress(
                started, len(symbols), 0, len(failures), len(symbols), "failed"
            ),
            },
        )
    case = _live_case(portfolio, themes, quotes, previous=previous)
    prior_dates = [day for day in archive.available_dates() if day <= runtime_day][-6:]
    bars_by_date = {
        day: archive.read_bars(
            day,
            symbols=symbols,
            through=now if day == runtime_day and runtime_day == now.date() else None,
            observed_through=now,
        )
        for day in prior_dates
    }
    visible_quotes = archive.read_quotes(
        runtime_day,
        through=now if runtime_day == now.date() else None,
        observed_through=now,
    )
    builder = IntradaySnapshotBuilder(
        case=case,
        themes=themes,
        bars_by_date=bars_by_date,
        quotes=visible_quotes,
        benchmark=str(universe.get("benchmark") or "000300.SH"),
    )
    engine = IntradayDecisionEngine(
        technology_theme_ids=TECHNOLOGY_THEME_IDS,
        catalyst_theme_ids=TECHNOLOGY_THEME_IDS,
        decision_authority="shadow_only",
    )
    reentry_states = load_reentry_states()
    timepoints = sorted(
        {
            *(bar.timestamp for rows in archived_today.values() for bar in rows),
            *(quote.timestamp for quote in visible_quotes),
        }
    )
    snapshots = []
    timeline = list(previous.get("timeline", [])) if isinstance(previous, Mapping) else []
    latest_states: Mapping[str, object] = {}
    active_alerts = {
        _alert_key(item): dict(item)
        for item in previous.get("active_alerts", [])
        if isinstance(item, Mapping)
    } if isinstance(previous, Mapping) else {}
    previous_source_time = _datetime(previous.get("last_source_time")) if isinstance(previous, Mapping) else None
    latest_timepoint = timepoints[-1]
    for timestamp in timepoints:
        snapshot = builder.build(timestamp, previous=snapshots)
        evaluation = engine.evaluate(
            snapshot,
            history=snapshots,
            reentry_states=reentry_states,
        )
        latest_states = evaluation.opportunity_states
        if timestamp == latest_timepoint and (
            previous_source_time is None or timestamp > previous_source_time
        ):
            transitions, active_alerts = _alert_transitions(
                snapshot,
                evaluation.alerts,
                active_alerts,
            )
            timeline.extend(transitions)
        snapshots.append(snapshot)
    latest = snapshots[-1]
    stale = [item.symbol for item in latest.quote_freshness if item.status != "fresh"]
    source_time = max(latest.source_times, default=latest.timestamp)
    latest_snapshot_payload = contract_dict(latest)
    non_advancing_gap: str | None = None
    if previous_source_time is not None and source_time <= previous_source_time:
        source_time = previous_source_time
        if isinstance(previous, Mapping) and isinstance(previous.get("latest_snapshot"), Mapping):
            latest_snapshot_payload = dict(previous["latest_snapshot"])
            prior_states = previous.get("opportunity_states")
            if isinstance(prior_states, Mapping):
                latest_states = dict(prior_states)
        non_advancing_gap = (
            "本轮 source_time 未单调推进；新供应商 observation 已追加保存，但未改写既有点时快照或警报。"
        )
    if runtime_day == now.date() and (now - source_time).total_seconds() > 120 and "runtime_source_time" not in stale:
        stale.append("runtime_source_time")
    freshness_status = "historical" if session.view_mode == "historical_review" else (
        "missing"
        if not latest.quote_freshness
        else "stale"
        if stale
        else "fresh"
    )
    peak_observations = _merge_peak_observations(previous, snapshots, previous_source_time)
    return _runtime_envelope(
        now,
        status=(
            "historical_review"
            if session.view_mode == "historical_review"
            else "partial" if failures or stale or freshness_status != "fresh" else "shadow"
        ),
        data_status=(
            "historical_partial"
            if session.view_mode == "historical_review" and failures
            else "historical_available"
            if session.view_mode == "historical_review"
            else "partial" if failures else "available"
        ),
        freshness_status=freshness_status,
        source_time=source_time,
        previous=previous,
        session=session,
        extra={
        "latest_snapshot": latest_snapshot_payload,
        "timeline": timeline,
        "active_alerts": list(active_alerts.values()),
        "account_peak_observations": peak_observations,
        "opportunity_states": dict(latest_states),
        "data_gaps": [
            *(f"行情不新鲜或缺失：{', '.join(stale)}" for _ in [0] if stale),
            *_failure_summaries(failures),
            *session.data_gaps,
            *([non_advancing_gap] if non_advancing_gap else []),
            "外部映射强度尚未接入实时点时源，catalyst_failure 只在该字段可用时授权。",
            *(
                ["尚无用户确认的减仓/接回状态账本；实时 reentry_guard 保持不可判定。"]
                if not reentry_states
                else []
            ),
        ],
        "provider_status": {
            "primary_bar_count": len(bars),
            "quote_count": len(quotes),
            "failed_count": len(failures),
            "local_archive_available": bool(archived_today),
            "diagnostics": diagnostics,
        },
        "refresh_progress": _final_progress(
            started,
            len(symbols),
            len(archived_today),
            len(failures),
            max(0, len(symbols) - len(archived_today)),
            "partial" if failures else "succeeded",
        ),
        },
    )


def poll_intraday_checkpoints(
    *,
    allow_fallback: bool = True,
    now_fn=datetime.now,
    sleep_fn=time.sleep,
    refresh_fn: Callable[[], dict[str, object]] | None = None,
    stop_event: Event | None = None,
    scheduler_lock: int | None = None,
) -> dict[str, object]:
    """Reliably run the remaining 09:25/09:35/10:00 checkpoints once per day."""

    lock = (
        scheduler_lock
        if scheduler_lock is not None
        else _acquire_scheduler_lock(now_fn())
    )
    if lock is None:
        return load_intraday_runtime() or {
            "status": "scheduler_already_running",
            "decision_authority": "shadow_only",
        }
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                return load_intraday_runtime() or {
                    "status": "scheduler_stopped",
                    "decision_authority": "shadow_only",
                    "trade_authority": "none",
                }
            now = now_fn()
            runtime = load_intraday_runtime()
            if isinstance(runtime, Mapping) and runtime.get("session_mode") == "non_trading_day":
                result = dict(runtime)
                result["checkpoint_status"] = "disabled_non_trading_day"
                result["next_check_time"] = None
                _atomic_json(RUNTIME_PATH, result)
                return result
            completed = _completed_checkpoints(runtime, now.date().isoformat())
            exhausted = _exhausted_checkpoints(runtime, now.date().isoformat())
            target = _next_scheduler_target(now, completed | exhausted)
            if target is None:
                return runtime or _runtime_envelope(
                    now,
                    status="blocked",
                    data_status="missing",
                    freshness_status="missing",
                    source_time=None,
                    previous=None,
                    extra={"latest_snapshot": None, "timeline": [], "active_alerts": []},
                )
            wait_seconds = (target - now).total_seconds()
            if wait_seconds > 0:
                wait_slice = min(wait_seconds, 30.0)
                if stop_event is not None:
                    stop_event.wait(wait_slice)
                else:
                    sleep_fn(wait_slice)
                continue
            payload = (
                refresh_fn()
                if refresh_fn is not None
                else poll_intraday_once(as_of=now, allow_fallback=allow_fallback)
            )
            _append_alert_archive(payload)
            _atomic_json(RUNTIME_PATH, payload)
    finally:
        _release_scheduler_lock(lock)


def _runtime_envelope(
    now: datetime,
    *,
    status: str,
    data_status: str,
    freshness_status: str,
    source_time: datetime | None,
    previous: Mapping[str, object] | None,
    session: TradingSessionResolution | None = None,
    extra: Mapping[str, object],
) -> dict[str, object]:
    runtime_day = session.runtime_trade_date if session is not None else now.date()
    trade_date = runtime_day.isoformat() if runtime_day is not None else ""
    runs = [
        dict(item)
        for item in previous.get("checkpoint_runs", [])
        if isinstance(item, Mapping) and item.get("trade_date") == trade_date
    ] if isinstance(previous, Mapping) else []
    completed = {
        str(item.get("checkpoint"))
        for item in runs
        if item.get("status") in {"succeeded", "partial"}
    }
    pre_exhausted = _exhausted_checkpoints(
        {"trade_date": trade_date, "checkpoint_runs": runs},
        trade_date,
    )
    checkpoints_enabled = session is None or session.session_mode != "non_trading_day"
    checkpoint = (
        _checkpoint_for_poll(now, completed | pre_exhausted)
        if checkpoints_enabled
        else None
    )
    if checkpoint is not None:
        run_status = _checkpoint_run_status(status)
        runs.append(
            {
                "trade_date": trade_date,
                "checkpoint": checkpoint.strftime("%H:%M"),
                "source_time": source_time.isoformat(timespec="seconds") if source_time else None,
                "fetch_time": now.isoformat(timespec="seconds"),
                "status": run_status,
                "attempt_count": 1 + sum(
                    1 for item in runs if item.get("checkpoint") == checkpoint.strftime("%H:%M")
                ),
            }
        )
        if run_status in {"succeeded", "partial"}:
            completed.add(checkpoint.strftime("%H:%M"))
    exhausted = _exhausted_checkpoints(
        {"trade_date": trade_date, "checkpoint_runs": runs},
        trade_date,
    )
    resolved_checkpoints = completed | exhausted
    next_check = (
        next_checkpoint_time(now, resolved_checkpoints)
        if checkpoints_enabled
        else None
    )
    missed = [
        checkpoint.strftime("%H:%M")
        for checkpoint in CHECKPOINTS
        if checkpoints_enabled
        and checkpoint.strftime("%H:%M") not in resolved_checkpoints
        and (now - datetime.combine(now.date(), checkpoint)).total_seconds() > 180
    ]
    payload: dict[str, object] = {
        "schema_version": "intraday-runtime/v2",
        "trade_date": trade_date,
        "generated_at": now.isoformat(timespec="seconds"),
        "source_time": source_time.isoformat(timespec="seconds") if source_time else None,
        "last_source_time": source_time.isoformat(timespec="seconds") if source_time else None,
        "fetch_time": now.isoformat(timespec="seconds"),
        "next_check_time": next_check.isoformat(timespec="seconds") if next_check else None,
        "status": status,
        "data_status": data_status,
        "freshness_status": freshness_status,
        "analysis_authority": (
            session.analysis_authority if session is not None else "live_shadow"
        ),
        "decision_authority": (
            session.decision_authority if session is not None else "shadow_only"
        ),
        "trade_authority": "none",
        "network_routes": declared_provider_routes(),
        "checkpoint_runs": runs,
        "missed_checkpoints": missed,
        "checkpoint_status": (
            "disabled_non_trading_day"
            if not checkpoints_enabled
            else _checkpoint_run_status(status) if checkpoint is not None
            else "scheduled" if next_check is not None
            else "succeeded"
        ),
    }
    if session is not None:
        payload.update(session.as_dict())
        payload["trade_date"] = trade_date
    payload.update(extra)
    payload["timeline"] = [
        _shadow_event_mapping(item)
        for item in payload.get("timeline", [])
        if isinstance(item, Mapping)
    ]
    payload["active_alerts"] = [
        _shadow_event_mapping(item)
        for item in payload.get("active_alerts", [])
        if isinstance(item, Mapping)
    ]
    return payload


def run_intraday_service(
    *,
    allow_fallback: bool = True,
    stop_event: Event | None = None,
) -> dict[str, object]:
    """Own one initial refresh and the remaining bounded checkpoints in-process."""

    now = datetime.now()
    scheduler_lock = _acquire_scheduler_lock(now)
    if scheduler_lock is None:
        return load_intraday_runtime() or {
            "status": "scheduler_already_running",
            "decision_authority": "shadow_only",
            "trade_authority": "none",
        }
    try:
        _write_refresh_progress(
            now,
            load_intraday_runtime(),
            phase="workspace_started",
            provider=None,
            batch=0,
            total_batches=0,
            processed=0,
            total_symbols=0,
            succeeded=0,
            failed=0,
            missing=0,
            circuit_state="closed",
            elapsed_seconds=0.0,
            next_action="后台解析A股真实交易日",
            session=None,
        )
        payload = _run_bounded_refresh(allow_fallback=allow_fallback)
        progress = payload.get("refresh_progress")
        if isinstance(progress, Mapping):
            print(
                "盘中刷新："
                f"{progress.get('status')}，已处理 {progress.get('processed_symbols')}/"
                f"{progress.get('total_symbols')}，失败 {progress.get('failed_count')}。"
            )
        if payload.get("session_mode") == "non_trading_day":
            return payload
        checkpoint_lock = scheduler_lock
        scheduler_lock = None
        return poll_intraday_checkpoints(
            allow_fallback=allow_fallback,
            refresh_fn=lambda: _run_bounded_refresh(allow_fallback=allow_fallback),
            stop_event=stop_event,
            scheduler_lock=checkpoint_lock,
        )
    finally:
        if scheduler_lock is not None:
            _release_scheduler_lock(scheduler_lock)


def _write_refresh_progress(
    now: datetime,
    previous: Mapping[str, object] | None,
    *,
    phase: str,
    provider: str | None,
    batch: int,
    total_batches: int,
    processed: int,
    total_symbols: int,
    succeeded: int,
    failed: int,
    missing: int,
    circuit_state: str,
    elapsed_seconds: float,
    next_action: str,
    session: TradingSessionResolution | None,
) -> None:
    payload = dict(previous) if isinstance(previous, Mapping) else {}
    payload.update(
        {
            "schema_version": "intraday-runtime/v2",
            "generated_at": now.isoformat(timespec="seconds"),
            "fetch_time": now.isoformat(timespec="seconds"),
            "status": "running",
            "trade_authority": "none",
            "network_routes": declared_provider_routes(),
            "scheduler_status": "registered",
            "refresh_progress": {
                "phase": phase,
                "provider": provider,
                "route_policy": (
                    provider_policy(provider).proxy_policy if provider else "automatic"
                ),
                "route_display": (
                    provider_policy(provider).display_route if provider else "自动/未知"
                ),
                "batch": batch,
                "total_batches": total_batches,
                "processed_symbols": processed,
                "total_symbols": total_symbols,
                "succeeded_count": succeeded,
                "failed_count": failed,
                "missing_count": missing,
                "circuit_state": circuit_state,
                "elapsed_seconds": round(elapsed_seconds, 1),
                "last_success_time": payload.get("last_success_time"),
                "next_action": next_action,
                "status": "running",
            },
        }
    )
    if session is not None:
        payload.update(session.as_dict())
        payload["trade_date"] = (
            session.runtime_trade_date.isoformat()
            if session.runtime_trade_date is not None else ""
        )
    _atomic_json(RUNTIME_PATH, payload)
    route = provider_policy(provider).display_route if provider else "自动/未知"
    print(
        f"盘中刷新 · {phase} · {provider or 'session'} / {route} · "
        f"{processed}/{total_symbols} · {elapsed_seconds:.1f}s"
    )


def _final_progress(
    started: float,
    total: int,
    succeeded: int,
    failed: int,
    missing: int,
    status: str,
) -> dict[str, object]:
    return {
        "phase": "refresh_finished",
        "provider": None,
        "route_policy": "automatic",
        "route_display": "自动/未知",
        "batch": 0,
        "total_batches": 0,
        "processed_symbols": total,
        "total_symbols": total,
        "succeeded_count": succeeded,
        "failed_count": failed,
        "missing_count": missing,
        "circuit_state": "closed",
        "elapsed_seconds": round(max(0.0, time.monotonic() - started), 1),
        "last_success_time": (
            datetime.now().isoformat(timespec="seconds") if succeeded else None
        ),
        "next_action": "页面可继续使用",
        "status": status,
    }


def _run_bounded_refresh(
    *,
    allow_fallback: bool,
    timeout_seconds: float = REFRESH_HARD_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Run one real refresh out-of-process so a stuck SDK call is terminable."""

    global _ACTIVE_REFRESH_PROCESS
    command = [
        sys.executable,
        "-m",
        "stock_assist.cli",
        "intraday-poll",
        "--iterations",
        "1",
    ]
    if not allow_fallback:
        command.append("--no-fallback")
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with _ACTIVE_REFRESH_PROCESS_LOCK:
        _ACTIVE_REFRESH_PROCESS = process
    timed_out = False
    try:
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
            return_code = process.returncode
    finally:
        _remove_refresh_lock_owned_by(process.pid)
        with _ACTIVE_REFRESH_PROCESS_LOCK:
            if _ACTIVE_REFRESH_PROCESS is process:
                _ACTIVE_REFRESH_PROCESS = None
    payload = load_intraday_runtime() or {}
    if timed_out:
        return _mark_refresh_process_failure(
            payload,
            reason="refresh_total_timeout",
            elapsed_seconds=time.monotonic() - started,
        )
    if return_code != 0:
        return _mark_refresh_process_failure(
            payload,
            reason="refresh_worker_failed",
            elapsed_seconds=time.monotonic() - started,
        )
    return payload


def stop_intraday_refresh_process() -> None:
    """Stop only the child refresh process owned by this workspace process."""

    with _ACTIVE_REFRESH_PROCESS_LOCK:
        process = _ACTIVE_REFRESH_PROCESS
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.0)
    _remove_refresh_lock_owned_by(process.pid)


def stop_intraday_scheduler() -> None:
    """Release only a scheduler lock owned by the current workspace process."""

    _remove_lock_owned_by(SCHEDULER_LOCK_PATH, os.getpid())


def _remove_refresh_lock_owned_by(process_id: int) -> None:
    """Remove only the single-flight lock written by the terminated child."""

    _remove_lock_owned_by(REFRESH_LOCK_PATH, process_id)


def _remove_lock_owned_by(path: Path, process_id: int) -> None:
    try:
        owner = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    if not owner.startswith(f"pid={process_id} "):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _mark_refresh_process_failure(
    payload: Mapping[str, object],
    *,
    reason: str,
    elapsed_seconds: float,
) -> dict[str, object]:
    result = dict(payload)
    raw_gaps = result.get("data_gaps")
    gaps = [str(item) for item in raw_gaps] if isinstance(raw_gaps, list) else []
    message = (
        "总刷新达到硬时限；后台工作进程已终止，页面和既有真实档案继续可用。"
        if reason == "refresh_total_timeout"
        else "后台刷新工作进程异常结束；页面和既有真实档案继续可用。"
    )
    if message not in gaps:
        gaps.append(message)
    raw_progress = result.get("refresh_progress")
    progress = dict(raw_progress) if isinstance(raw_progress, Mapping) else {}
    progress.update(
        {
            "phase": reason,
            "status": "failed",
            "elapsed_seconds": round(elapsed_seconds, 1),
            "next_action": "保留当前页面；等待下一次有界刷新",
        }
    )
    result.update(
        {
            "schema_version": "intraday-runtime/v2",
            "status": "partial" if result.get("latest_snapshot") else "blocked",
            "trade_authority": "none",
            "data_gaps": gaps,
            "refresh_progress": progress,
            "refresh_process_status": reason,
            "network_routes": declared_provider_routes(),
        }
    )
    _atomic_json(RUNTIME_PATH, result)
    return result


def _provider_diagnostic(
    provider: str,
    *,
    elapsed_ms: int,
    status: str,
    error_type: str | None,
    attempt_count: int,
    circuit_state: str,
) -> dict[str, object]:
    policy = provider_policy(provider)
    return {
        "provider": provider,
        "route_policy": policy.proxy_policy,
        "route_display": policy.display_route,
        "elapsed_ms": max(0, elapsed_ms),
        "status": status,
        "sanitized_error_type": error_type,
        "attempt_count": attempt_count,
        "circuit_state": circuit_state,
        "route_scope": policy.route_scope,
        "os_tun_bypass_guaranteed": policy.os_tun_bypass_guaranteed,
    }


def _append_provider_diagnostic(
    provider: str,
    exc: BaseException,
    elapsed_ms: int,
    status: str,
    attempt_count: int,
    circuit_state: str,
) -> None:
    record = _provider_diagnostic(
        provider,
        elapsed_ms=elapsed_ms,
        status=status,
        error_type=sanitized_error_type(exc),
        attempt_count=attempt_count,
        circuit_state=circuit_state,
    )
    record["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    record["local_error"] = sanitize_diagnostic_text(repr(exc))
    PROVIDER_DIAGNOSTIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        PROVIDER_DIAGNOSTIC_PATH,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(
            descriptor,
            (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _failure_summaries(failures: Mapping[str, str]) -> list[str]:
    counts: dict[str, int] = {}
    for reason in failures.values():
        counts[str(reason)] = counts.get(str(reason), 0) + 1
    result: list[str] = []
    for reason, count in sorted(counts.items()):
        if reason == "provider_unavailable_due_to_circuit_breaker":
            result.append(f"东方财富备用源已熔断；剩余 {count} 个标的不再请求。")
        elif reason == "refresh_total_timeout":
            result.append(f"总刷新达到时限；{count} 个标的保留缺失状态。")
        else:
            result.append(f"{reason}：{count} 个标的。")
    return result


def _checkpoint_run_status(status: str) -> str:
    if status in {"shadow", "historical_review", "succeeded"}:
        return "succeeded"
    if status == "partial":
        return "partial"
    if status in {"blocked", "failed"}:
        return "failed"
    return "running" if status == "running" else "scheduled"


def next_checkpoint_time(
    now: datetime,
    completed: Iterable[str] = (),
) -> datetime | None:
    done = {str(item) for item in completed}
    for checkpoint in CHECKPOINTS:
        label = checkpoint.strftime("%H:%M")
        target = datetime.combine(now.date(), checkpoint)
        if label in done:
            continue
        if target >= now or 0 <= (now - target).total_seconds() <= 180:
            return target
    return None


def _checkpoint_for_poll(now: datetime, completed: set[str]) -> clock_time | None:
    eligible = [
        checkpoint
        for checkpoint in CHECKPOINTS
        if checkpoint.strftime("%H:%M") not in completed
        and 0 <= (now - datetime.combine(now.date(), checkpoint)).total_seconds() <= 180
    ]
    return eligible[-1] if eligible else None


def _completed_checkpoints(runtime: Mapping[str, object] | None, trade_date: str) -> set[str]:
    if not isinstance(runtime, Mapping) or runtime.get("trade_date") != trade_date:
        return set()
    return {
        str(item.get("checkpoint"))
        for item in runtime.get("checkpoint_runs", [])
        if isinstance(item, Mapping)
        and item.get("trade_date") == trade_date
        and item.get("status") in {"succeeded", "partial"}
    }


def _exhausted_checkpoints(
    runtime: Mapping[str, object] | None,
    trade_date: str,
    max_attempts: int = 2,
) -> set[str]:
    if not isinstance(runtime, Mapping) or runtime.get("trade_date") != trade_date:
        return set()
    attempts: dict[str, int] = {}
    for item in runtime.get("checkpoint_runs", []):
        if not isinstance(item, Mapping) or item.get("trade_date") != trade_date:
            continue
        if item.get("status") != "failed":
            continue
        label = str(item.get("checkpoint") or "")
        attempts[label] = attempts.get(label, 0) + 1
    return {label for label, count in attempts.items() if label and count >= max_attempts}


def _next_scheduler_target(now: datetime, completed: set[str]) -> datetime | None:
    for checkpoint in CHECKPOINTS:
        label = checkpoint.strftime("%H:%M")
        if label in completed:
            continue
        target = datetime.combine(now.date(), checkpoint)
        if target >= now or (now - target).total_seconds() <= 180:
            return target
    return None


def _acquire_scheduler_lock(now: datetime) -> int | None:
    SCHEDULER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _remove_dead_owner_lock(SCHEDULER_LOCK_PATH)
    try:
        descriptor = os.open(
            SCHEDULER_LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        return None
    os.write(descriptor, f"pid={os.getpid()} started_at={now.isoformat(timespec='seconds')}\n".encode("utf-8"))
    os.fsync(descriptor)
    return descriptor


def _release_scheduler_lock(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass
    _remove_lock_owned_by(SCHEDULER_LOCK_PATH, os.getpid())


def _acquire_refresh_lock(now: datetime) -> int | None:
    REFRESH_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _remove_dead_owner_lock(REFRESH_LOCK_PATH)
    try:
        descriptor = os.open(
            REFRESH_LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        return None
    os.write(
        descriptor,
        f"pid={os.getpid()} started_at={now.isoformat(timespec='seconds')}\n".encode("utf-8"),
    )
    os.fsync(descriptor)
    return descriptor


def _remove_dead_owner_lock(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
        owner = int(text.split(" ", 1)[0].removeprefix("pid="))
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return
    if _process_is_alive(owner):
        return
    _remove_lock_owned_by(path, owner)


def _process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            process_id,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _alert_transitions(
    snapshot: IntradaySnapshot,
    alerts: Iterable[IntradayAlert],
    prior_active: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    current = {
        _alert_key(contract_dict(alert)): dict(contract_dict(alert))
        for alert in alerts
    }
    emitted: list[dict[str, object]] = []
    severity_rank = {"info": 0, "yellow": 1, "orange": 2, "red": 3}
    for key, item in current.items():
        prior = prior_active.get(key)
        if prior is None:
            emitted.append(item)
            continue
        if _alert_signature(prior) == _alert_signature(item):
            continue
        if item.get("event_state") != "invalidation":
            item["event_state"] = (
                "escalated"
                if severity_rank.get(str(item.get("severity")), 0)
                > severity_rank.get(str(prior.get("severity")), 0)
                else "updated"
            )
        emitted.append(item)
    for key, prior in prior_active.items():
        if key in current:
            continue
        identity = f"resolved|{key}|{snapshot.timestamp.isoformat()}"
        emitted.append(
            {
                **dict(prior),
                "alert_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
                "timestamp": snapshot.timestamp.isoformat(timespec="seconds"),
                "severity": "info",
                "title": "条件解除：" + str(prior.get("title") or prior.get("type") or key),
                "conclusion": "先前点时条件不再满足，状态已明确结束；IR-002 仍无交易建议权限。",
                "action_state": "observation_only",
                "suggested_risk_change": {
                    "target": prior.get("target_id"),
                    "new_risk_authorized": False,
                    "automatic_execution": False,
                },
                "source_times": contract_dict(snapshot.source_times),
                "fetched_at": contract_dict(snapshot.fetched_at),
                "event_state": "resolved",
            }
        )
    return emitted, current


def _alert_key(item: Mapping[str, object]) -> str:
    return f"{item.get('type')}|{item.get('target_type')}|{item.get('target_id')}"


def _alert_signature(item: Mapping[str, object]) -> tuple[object, ...]:
    return (
        item.get("severity"),
        item.get("title"),
        item.get("action_state"),
        item.get("event_state"),
    )


def _shadow_event_mapping(item: Mapping[str, object]) -> dict[str, object]:
    result = dict(item)
    target = result.get("target_id")
    event_state = str(result.get("event_state") or "activated")
    result["title"] = f"影子规则观察：{result.get('type') or 'unknown'}"
    if event_state == "resolved":
        result["conclusion"] = "影子观察：先前规则条件已结束；只记录 resolved 状态，不形成仓位动作。"
    elif event_state == "invalidation":
        result["conclusion"] = "影子观察：先前点时证据或结构已失效；只记录 invalidation 状态，不形成仓位动作。"
    else:
        result["conclusion"] = "影子观察：规则条件已触发，但当前没有交易建议权限；仅记录点时结果并等待实盘校准。"
    evidence = result.get("evidence")
    result["evidence"] = _shadow_observation_texts(evidence if isinstance(evidence, list) else [])
    result["action_state"] = "observation_only"
    result["suggested_risk_change"] = {
        "target": target,
        "new_risk_authorized": False,
        "automatic_execution": False,
    }
    result["confirmation_conditions"] = [
        "仅校准该规则在此 source_time 是否准确触发，不形成仓位动作。"
    ]
    result["invalidation_conditions"] = [
        "条件不再满足或点时证据失效时，只记录 resolved / invalidation 事件。"
    ]
    result["reentry_conditions"] = []
    return result


def _shadow_observation_texts(values: Iterable[object]) -> list[str]:
    action_terms = ("减仓", "兑现", "加仓", "买入", "卖出", "接回", "仓位动作")
    result = [str(value) for value in values if not any(term in str(value) for term in action_terms)]
    return result or ["原始动作型说明已隐藏；保留规则类型、目标、时点与状态用于校准。"]


def _merge_peak_observations(
    previous: Mapping[str, object] | None,
    snapshots: Iterable[IntradaySnapshot],
    previous_source_time: datetime | None,
) -> list[dict[str, object]]:
    rows = [
        dict(item)
        for item in previous.get("account_peak_observations", [])
        if isinstance(item, Mapping) and item.get("source_time") and item.get("value") is not None
    ] if isinstance(previous, Mapping) else []
    last_value = max((float(item["value"]) for item in rows), default=None)
    for snapshot in snapshots:
        if previous_source_time is not None and snapshot.timestamp <= previous_source_time:
            continue
        value = snapshot.account_peak_daily_pnl
        if value is None or (last_value is not None and value <= last_value):
            continue
        rows.append(
            {
                "source_time": snapshot.timestamp.isoformat(timespec="seconds"),
                "value": value,
            }
        )
        last_value = value
    return rows


def _append_alert_archive(payload: Mapping[str, object]) -> None:
    trade_date = str(payload.get("trade_date") or "")
    if not trade_date:
        return
    path = ALERT_ARCHIVE_ROOT / f"{trade_date}.jsonl"
    existing = {
        str(item.get("observation_id"))
        for item in _jsonl_mappings(path)
        if item.get("observation_id")
    }
    fetch_time = payload.get("fetch_time")
    rows: list[str] = []
    for item in payload.get("timeline", []):
        if not isinstance(item, Mapping):
            continue
        record = dict(item)
        record["trade_date"] = trade_date
        record["source_time"] = record.get("timestamp")
        record["source_fetched_at"] = record.get("fetched_at")
        record["fetched_at"] = fetch_time
        record["provider"] = "InsightRadar deterministic intraday rules"
        record.pop("observation_id", None)
        raw = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        observation_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        if observation_id in existing:
            continue
        record["observation_id"] = observation_id
        rows.append(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        existing.add(observation_id)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, "".join(rows).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _jsonl_mappings(path: Path) -> Iterable[dict[str, object]]:
    if not path.exists():
        return ()
    result: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return tuple(result)


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def load_intraday_runtime(path: Path = RUNTIME_PATH) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def persist_execution_guard(
    *,
    runtime_path: Path = RUNTIME_PATH,
    execution_path: Path = DEFAULT_EXECUTION_LEDGER,
    confirmation_path: Path = DEFAULT_REENTRY_CONFIRMATION_LEDGER,
    failure_path: Path = DEFAULT_REENTRY_FAILURE_LEDGER,
) -> dict[str, object]:
    """Refresh the durable guard immediately after confirmed ledger writes."""

    runtime = load_intraday_runtime(runtime_path) or {
        "schema_version": "intraday-runtime/v2",
        "status": "blocked",
        "data_status": "missing",
        "freshness_status": "missing",
        "analysis_authority": "none",
        "decision_authority": "blocked",
        "trade_authority": "none",
    }
    states = load_reentry_states(
        execution_path,
        confirmation_path=confirmation_path,
        failure_path=failure_path,
    )
    guard_rows = [asdict(item) for item in states]
    runtime["reentry_guard_states"] = guard_rows
    runtime["execution_guard"] = {
        "status": "active" if guard_rows else "unknown",
        "confirmed_sell_count": sum(
            1 for item in load_executions(execution_path) if item.side == "sell"
        ),
        "structure_data_status": (
            "available" if isinstance(runtime.get("latest_snapshot"), Mapping) else "missing"
        ),
        "default_reentry_policy": "structure_confirmation_required",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _atomic_json(runtime_path, runtime)
    return dict(runtime["execution_guard"])


def load_reentry_states(
    path: Path = DEFAULT_EXECUTION_LEDGER,
    *,
    confirmation_path: Path | None = None,
    failure_path: Path | None = None,
) -> tuple[ReentryPositionState, ...]:
    """Load optional user-confirmed state; absence never implies that no sale occurred."""

    executions = load_executions(path)
    if executions:
        resolved_confirmation_path = (
            confirmation_path
            if confirmation_path is not None
            else DEFAULT_REENTRY_CONFIRMATION_LEDGER
            if path == DEFAULT_EXECUTION_LEDGER
            else path.with_name("reentry_confirmation_ledger.jsonl")
        )
        confirmations = load_reentry_confirmations(resolved_confirmation_path)
        resolved_failure_path = (
            failure_path
            if failure_path is not None
            else DEFAULT_REENTRY_FAILURE_LEDGER
            if path == DEFAULT_EXECUTION_LEDGER
            else path.with_name("reentry_failure_ledger.jsonl")
        )
        failures = load_reentry_failures(resolved_failure_path)
        result: list[ReentryPositionState] = []
        sales = [item for item in executions if item.side == "sell"]
        for sale in sales:
            reentries = [
                item
                for item in executions
                if item.side == "buy"
                and item.reference_execution_id == sale.execution_id
            ]
            reentry_ids = {item.execution_id for item in reentries}
            failure_ids = {
                item.failure_id
                for item in failures
                if item.referenced_buy_execution_id in reentry_ids
                and item.referenced_sell_execution_id == sale.execution_id
            }
            second_reentry_confirmed = any(
                item.symbol == sale.symbol
                and item.target_id == sale.target_id
                and item.sold_at == sale.sold_at
                and item.failed_reentry_execution_id in reentry_ids
                and item.failure_observation_id in failure_ids
                for item in confirmations
            )
            result.append(
                ReentryPositionState(
                    target_id=sale.target_id,
                    sold_at=sale.sold_at,
                    sold_fraction=(
                        sale.quantity / sale.available_quantity
                        if sale.available_quantity > 0
                        else None
                    ),
                    sale_price=sale.sale_price,
                    reentry_count=len(reentries),
                    first_reentry_price=(
                        reentries[0].execution_price if reentries else None
                    ),
                    post_reentry_low_broken=bool(failure_ids),
                    symbol=sale.symbol,
                    quantity=sale.quantity,
                    available_quantity=sale.available_quantity,
                    second_reentry_confirmed=second_reentry_confirmed,
                    sale_execution_id=sale.execution_id,
                )
            )
        return tuple(result)

    legacy_path = REENTRY_STATE_PATH if path == DEFAULT_EXECUTION_LEDGER else path
    path = legacy_path
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    rows = payload.get("states") if isinstance(payload, Mapping) else None
    result: list[ReentryPositionState] = []
    for item in rows if isinstance(rows, list) else []:
        if (
            not isinstance(item, Mapping)
            or not item.get("target_id")
            or not item.get("sold_at")
            or item.get("sale_price") is None
        ):
            continue
        try:
            result.append(
                ReentryPositionState(
                    target_id=str(item["target_id"]),
                    sold_at=str(item["sold_at"]),
                    sold_fraction=(
                        float(item["sold_fraction"])
                        if item.get("sold_fraction") is not None
                        else None
                    ),
                    sale_price=float(item["sale_price"]),
                    reentry_count=int(item.get("reentry_count") or 0),
                    first_reentry_price=(
                        float(item["first_reentry_price"])
                        if item.get("first_reentry_price") is not None
                        else None
                    ),
                    post_reentry_low_broken=item.get("post_reentry_low_broken") is True,
                    account_profit_floor=(
                        float(item["account_profit_floor"])
                        if item.get("account_profit_floor") is not None
                        else None
                    ),
                    second_reentry_confirmed=item.get("second_reentry_confirmed") is True,
                )
            )
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _live_case(portfolio, themes, quotes, *, previous: Mapping[str, object] | None) -> dict[str, object]:
    quote_by_symbol = {item.symbol: item for item in quotes}
    previous_peaks = previous.get("account_peak_observations") if isinstance(previous, Mapping) else None
    timed_peaks = [
        dict(item)
        for item in previous_peaks
        if isinstance(item, Mapping) and item.get("source_time") and item.get("value") is not None
    ] if isinstance(previous_peaks, list) else []
    return {
        "cash": portfolio.cash,
        "account_peak_observations": timed_peaks,
        "holdings": [
            {
                "symbol": item.code.upper(),
                "name": item.name,
                "shares": item.shares,
                "available": item.available,
                "primary_theme_id": _assign_theme(item.code.upper(), themes),
                "pre_close": quote_by_symbol.get(item.code.upper()).pre_close if quote_by_symbol.get(item.code.upper()) else None,
            }
            for item in portfolio.holdings
        ],
        "external_mapping_returns": {},
    }


def _assign_theme(symbol: str, themes: Iterable[Mapping[str, object]]) -> str:
    code = symbol.upper()
    for item in themes:
        if str(item.get("representative_etf") or "").upper() == code:
            return str(item.get("theme_id") or "unknown")
    for item in themes:
        raw = item.get("representative_symbols")
        if isinstance(raw, list) and code in {str(value).upper() for value in raw}:
            return str(item.get("theme_id") or "unknown")
    return "unknown"


def _batches(values: Iterable[str], size: int) -> Iterable[tuple[str, ...]]:
    rows = tuple(values)
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()
