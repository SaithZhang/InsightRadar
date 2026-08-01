"""Bounded loopback-friendly intraday polling over the local archive seam."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Mapping

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.contracts import contract_dict
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
    archived_today = archive.read_bars(now.date(), symbols=symbols, through=now)
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
            archived_today = archive.read_bars(now.date(), symbols=symbols, through=now)
            for recovered in {item.symbol for item in fallback}:
                failures.pop(recovered, None)
    failures.update(fallback_failures)
    if not archived_today and not quotes:
        return {
            "schema_version": "intraday-runtime/v1",
            "generated_at": now.isoformat(timespec="seconds"),
            "status": "blocked",
            "latest_snapshot": None,
            "timeline": [],
            "opportunity_states": {},
            "data_gaps": [
                "当前交易日没有可见分钟线或快照；页面保留盘后能力，但盘中状态不可用。",
                *sorted(set(failures.values())),
            ],
            "provider_status": {"failed_symbols": failures},
        }
    case = _live_case(portfolio, themes, quotes, previous=load_intraday_runtime())
    prior_dates = [day for day in archive.available_dates() if day <= now.date()][-6:]
    bars_by_date = {
        day: archive.read_bars(day, symbols=symbols, through=now if day == now.date() else None)
        for day in prior_dates
    }
    visible_quotes = archive.read_quotes(now.date(), through=now)
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
    )
    reentry_states = load_reentry_states()
    timepoints = sorted(
        {
            *(bar.timestamp for rows in archived_today.values() for bar in rows),
            *(quote.timestamp for quote in visible_quotes),
        }
    )
    snapshots = []
    timeline = []
    latest_states: Mapping[str, object] = {}
    seen = set()
    for timestamp in timepoints:
        snapshot = builder.build(timestamp, previous=snapshots)
        evaluation = engine.evaluate(
            snapshot,
            history=snapshots,
            reentry_states=reentry_states,
        )
        latest_states = evaluation.opportunity_states
        for alert in evaluation.alerts:
            key = (alert.type, alert.target_id, alert.severity, alert.title, alert.action_state)
            if key not in seen:
                seen.add(key)
                timeline.append(contract_dict(alert))
        snapshots.append(snapshot)
    latest = snapshots[-1]
    stale = [item.symbol for item in latest.quote_freshness if item.status != "fresh"]
    return {
        "schema_version": "intraday-runtime/v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "status": "partial" if failures or stale else "ready",
        "latest_snapshot": contract_dict(latest),
        "timeline": timeline,
        "opportunity_states": dict(latest_states),
        "data_gaps": [
            *(f"行情不新鲜或缺失：{', '.join(stale)}" for _ in [0] if stale),
            *(f"{symbol}: {reason}" for symbol, reason in sorted(failures.items())),
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
    }


def load_intraday_runtime(path: Path = RUNTIME_PATH) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_reentry_states(path: Path = REENTRY_STATE_PATH) -> tuple[ReentryPositionState, ...]:
    """Load optional user-confirmed state; absence never implies that no sale occurred."""

    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    rows = payload.get("states") if isinstance(payload, Mapping) else None
    result: list[ReentryPositionState] = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, Mapping) or not item.get("target_id") or not item.get("sold_at"):
            continue
        try:
            result.append(
                ReentryPositionState(
                    target_id=str(item["target_id"]),
                    sold_at=str(item["sold_at"]),
                    sold_fraction=float(item.get("sold_fraction") or 0),
                    sale_price=float(item.get("sale_price") or 0),
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
                )
            )
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _live_case(portfolio, themes, quotes, *, previous: Mapping[str, object] | None) -> dict[str, object]:
    quote_by_symbol = {item.symbol: item for item in quotes}
    previous_snapshot = previous.get("latest_snapshot") if isinstance(previous, Mapping) else None
    previous_peak = previous_snapshot.get("account_peak_daily_pnl") if isinstance(previous_snapshot, Mapping) else None
    return {
        "cash": portfolio.cash,
        "initial_account_peak_daily_pnl": previous_peak,
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
