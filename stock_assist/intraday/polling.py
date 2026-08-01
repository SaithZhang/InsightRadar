"""Bounded loopback-friendly intraday polling over the local archive seam."""

from __future__ import annotations

from datetime import datetime, time as clock_time
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Mapping

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.contracts import IntradayAlert, IntradaySnapshot, contract_dict
from stock_assist.intraday.execution import (
    DEFAULT_EXECUTION_LEDGER,
    DEFAULT_REENTRY_CONFIRMATION_LEDGER,
    load_executions,
    load_reentry_confirmations,
)
from stock_assist.intraday.providers import (
    fetch_amazingdata_latest_quotes,
    fetch_amazingdata_minute_bars,
    fetch_eastmoney_minute_bars,
)
from stock_assist.intraday.rules import IntradayDecisionEngine, ReentryPositionState
from stock_assist.intraday.snapshots import IntradaySnapshotBuilder
from stock_assist.intraday.universe import load_intraday_universe, universe_symbols
from stock_assist.paths import DATA_DIR
from stock_assist.portfolio import load_portfolio


RUNTIME_PATH = DATA_DIR / "intraday" / "runtime.json"
REENTRY_STATE_PATH = DATA_DIR / "intraday" / "reentry_state.json"
SCHEDULER_LOCK_PATH = DATA_DIR / "intraday" / "checkpoint-scheduler.lock"
ALERT_ARCHIVE_ROOT = DATA_DIR / "intraday" / "alerts"
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
    payload: dict[str, object] = {}
    for index in range(iterations):
        payload = poll_intraday_once(allow_fallback=allow_fallback)
        _append_alert_archive(payload)
        _atomic_json(RUNTIME_PATH, payload)
        if index + 1 < iterations:
            time.sleep(interval_seconds)
    return payload


def poll_intraday_once(
    *,
    as_of: datetime | None = None,
    allow_fallback: bool = True,
) -> dict[str, object]:
    now = as_of or datetime.now()
    previous = load_intraday_runtime()
    if not isinstance(previous, Mapping) or previous.get("trade_date") != now.date().isoformat():
        previous = None
    universe = load_intraday_universe()
    themes = [dict(item) for item in universe["themes"]]
    symbols = universe_symbols(universe)
    portfolio = load_portfolio()
    symbols = tuple(dict.fromkeys([*symbols, *(item.code.upper() for item in portfolio.holdings)]))
    archive = MinuteArchive()
    failures: dict[str, str] = {}
    bars = []
    quotes = []
    client = AmazingDataClient()
    try:
        for batch in _batches(symbols, 24):
            try:
                bars.extend(
                    fetch_amazingdata_minute_bars(
                        client,
                        batch,
                        start=now.date(),
                        end=now.date(),
                        fetched_at=now,
                    )
                )
                quotes.extend(fetch_amazingdata_latest_quotes(client, batch, as_of=now, fetched_at=now))
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                failures.update({symbol: message for symbol in batch})
    finally:
        client.logout()
    if bars:
        archive.write_bars(bars)
    if quotes:
        archive.write_quotes(quotes)
    archived_today = archive.read_bars(
        now.date(), symbols=symbols, through=now, observed_through=now
    )
    missing = sorted(set(symbols) - set(archived_today))
    fallback_failures: dict[str, str] = {}
    if allow_fallback and missing:
        fallback, fallback_failures = fetch_eastmoney_minute_bars(
            missing,
            start=now.date(),
            end=now.date(),
            fetched_at=now,
        )
        if fallback:
            archive.write_bars(fallback)
            archived_today = archive.read_bars(
                now.date(), symbols=symbols, through=now, observed_through=now
            )
            for recovered in {item.symbol for item in fallback}:
                failures.pop(recovered, None)
    failures.update(fallback_failures)
    if not archived_today and not quotes:
        return _runtime_envelope(
            now,
            status="blocked",
            data_status="missing" if not failures else "failed",
            freshness_status="missing",
            source_time=None,
            previous=previous,
            extra={
            "latest_snapshot": None,
            "timeline": list(previous.get("timeline", [])) if isinstance(previous, Mapping) else [],
            "active_alerts": list(previous.get("active_alerts", [])) if isinstance(previous, Mapping) else [],
            "opportunity_states": {},
            "data_gaps": [
                "当前交易日没有可见分钟线或快照；页面保留盘后能力，但盘中状态不可用。",
                *sorted(set(failures.values())),
            ],
            "provider_status": {"failed_symbols": failures},
            },
        )
    case = _live_case(portfolio, themes, quotes, previous=previous)
    prior_dates = [day for day in archive.available_dates() if day <= now.date()][-6:]
    bars_by_date = {
        day: archive.read_bars(
            day,
            symbols=symbols,
            through=now if day == now.date() else None,
            observed_through=now,
        )
        for day in prior_dates
    }
    visible_quotes = archive.read_quotes(
        now.date(), through=now, observed_through=now
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
    if (now - source_time).total_seconds() > 120 and "runtime_source_time" not in stale:
        stale.append("runtime_source_time")
    freshness_status = (
        "missing"
        if not latest.quote_freshness
        else "stale"
        if stale
        else "fresh"
    )
    peak_observations = _merge_peak_observations(previous, snapshots, previous_source_time)
    return _runtime_envelope(
        now,
        status="partial" if failures or stale or freshness_status != "fresh" else "shadow",
        data_status="partial" if failures else "available",
        freshness_status=freshness_status,
        source_time=source_time,
        previous=previous,
        extra={
        "latest_snapshot": latest_snapshot_payload,
        "timeline": timeline,
        "active_alerts": list(active_alerts.values()),
        "account_peak_observations": peak_observations,
        "opportunity_states": dict(latest_states),
        "data_gaps": [
            *(f"行情不新鲜或缺失：{', '.join(stale)}" for _ in [0] if stale),
            *(f"{symbol}: {reason}" for symbol, reason in sorted(failures.items())),
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
            "failed_symbols": failures,
            "local_archive": str(archive.root),
        },
        },
    )


def poll_intraday_checkpoints(
    *,
    allow_fallback: bool = True,
    now_fn=datetime.now,
    sleep_fn=time.sleep,
) -> dict[str, object]:
    """Reliably run the remaining 09:25/09:35/10:00 checkpoints once per day."""

    lock = _acquire_scheduler_lock(now_fn())
    if lock is None:
        return load_intraday_runtime() or {
            "status": "scheduler_already_running",
            "decision_authority": "shadow_only",
        }
    try:
        while True:
            now = now_fn()
            runtime = load_intraday_runtime()
            completed = _completed_checkpoints(runtime, now.date().isoformat())
            target = _next_scheduler_target(now, completed)
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
                sleep_fn(min(wait_seconds, 30.0))
                continue
            payload = poll_intraday_once(as_of=now, allow_fallback=allow_fallback)
            _append_alert_archive(payload)
            _atomic_json(RUNTIME_PATH, payload)
    finally:
        os.close(lock)
        try:
            SCHEDULER_LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def _runtime_envelope(
    now: datetime,
    *,
    status: str,
    data_status: str,
    freshness_status: str,
    source_time: datetime | None,
    previous: Mapping[str, object] | None,
    extra: Mapping[str, object],
) -> dict[str, object]:
    trade_date = now.date().isoformat()
    runs = [
        dict(item)
        for item in previous.get("checkpoint_runs", [])
        if isinstance(item, Mapping) and item.get("trade_date") == trade_date
    ] if isinstance(previous, Mapping) else []
    completed = {str(item.get("checkpoint")) for item in runs}
    checkpoint = _checkpoint_for_poll(now, completed)
    if checkpoint is not None:
        runs.append(
            {
                "trade_date": trade_date,
                "checkpoint": checkpoint.strftime("%H:%M"),
                "source_time": source_time.isoformat(timespec="seconds") if source_time else None,
                "fetch_time": now.isoformat(timespec="seconds"),
                "status": status,
            }
        )
        completed.add(checkpoint.strftime("%H:%M"))
    next_check = next_checkpoint_time(now, completed)
    missed = [
        checkpoint.strftime("%H:%M")
        for checkpoint in CHECKPOINTS
        if checkpoint.strftime("%H:%M") not in completed
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
        "decision_authority": "shadow_only",
        "checkpoint_runs": runs,
        "missed_checkpoints": missed,
    }
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
        if isinstance(item, Mapping) and item.get("trade_date") == trade_date
    }


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
    if SCHEDULER_LOCK_PATH.exists():
        age = now.timestamp() - SCHEDULER_LOCK_PATH.stat().st_mtime
        if age > 12 * 60 * 60:
            SCHEDULER_LOCK_PATH.unlink()
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


def load_reentry_states(
    path: Path = DEFAULT_EXECUTION_LEDGER,
    *,
    confirmation_path: Path | None = None,
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
        result: list[ReentryPositionState] = []
        latest_sales = {
            (item.target_id, item.symbol): item
            for item in executions
            if item.side == "sell"
        }
        for sale in latest_sales.values():
            reentries = [
                item
                for item in executions
                if item.side == "buy"
                and item.symbol == sale.symbol
                and item.sold_at == sale.sold_at
            ]
            reentry_ids = {item.execution_id for item in reentries}
            second_reentry_confirmed = any(
                item.symbol == sale.symbol
                and item.target_id == sale.target_id
                and item.sold_at == sale.sold_at
                and item.failed_reentry_execution_id in reentry_ids
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
                    post_reentry_low_broken=any(item.post_reentry_low_broken for item in reentries),
                    symbol=sale.symbol,
                    quantity=sale.quantity,
                    available_quantity=sale.available_quantity,
                    second_reentry_confirmed=second_reentry_confirmed,
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
