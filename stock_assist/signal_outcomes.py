"""Persistent after-close signal outcome tracking for InsightRadar."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.data_sources.xysz import (
    DAILY_KLINE_SCHEMA_VERSION,
    daily_kline_result_for_code,
)
from stock_assist.paths import DATA_DIR, REPORT_DIR

LEDGER_PATH = DATA_DIR / "signal_outcomes.jsonl"
HORIZONS = (1, 5, 20)
CODE_PATTERN = re.compile(r"(?P<code>\d{6}\.(?:SZ|SH))")
MA20_VALUE_PATTERN = re.compile(r"20日线\s*([0-9]+(?:\.[0-9]+)?)")
PRICE_BASIS_MISMATCH_LIMIT = 0.35
RECORD_SCHEMA_VERSION = "signal-outcome/v2"
EVALUATION_SOURCE = "provider-contract"
EVALUATABLE_PRICE_BASES = {
    "unadjusted",
    "forward_adjusted",
    "backward_adjusted",
}


def refresh_signal_outcomes(
    client: object | None,
    current_signals: Iterable[dict[str, object]] = (),
    *,
    report_dir: Path = REPORT_DIR,
    ledger_path: Path = LEDGER_PATH,
    as_of: date | None = None,
) -> dict[str, object]:
    """Upsert report/current signals, refresh their price outcomes, and persist them."""

    today = as_of or date.today()
    records = {str(row["signal_id"]): row for row in _read_ledger(ledger_path) if row.get("signal_id")}
    for row in _import_report_signals(report_dir):
        records[str(row["signal_id"])] = _merge_signal(records.get(str(row["signal_id"])), row)
    for signal in current_signals:
        normalised = _normalise_signal(signal, default_date=today.isoformat(), source_report="current-run")
        if normalised:
            records[str(normalised["signal_id"])] = _merge_signal(records.get(str(normalised["signal_id"])), normalised)

    ordered = sorted(records.values(), key=lambda row: (str(row.get("signal_date", "")), str(row.get("code", ""))))
    if client is not None and ordered:
        _evaluate_records(client, ordered, today)
    _write_ledger(ledger_path, ordered)
    snapshot = build_outcome_snapshot(ordered)
    snapshot["ledger"] = str(ledger_path)
    return snapshot


def load_outcome_snapshot(ledger_path: Path = LEDGER_PATH) -> dict[str, object]:
    snapshot = build_outcome_snapshot(_read_ledger(ledger_path))
    snapshot["ledger"] = str(ledger_path)
    return snapshot


def build_outcome_snapshot(records: list[dict[str, object]]) -> dict[str, object]:
    """Build a compact, client-readable scorecard from ledger rows."""

    included: list[dict[str, object]] = []
    quarantined: list[dict[str, object]] = []
    for row in records:
        item = dict(row)
        is_contract_record = item.get("evaluation_source") == EVALUATION_SOURCE and item.get("record_schema_version") == RECORD_SCHEMA_VERSION
        is_current_record = item.get("record_schema_version") == RECORD_SCHEMA_VERSION
        has_evaluation_source = bool(item.get("evaluation_source"))
        has_record_version = bool(item.get("record_schema_version"))
        if is_contract_record:
            evaluation_status = str(item.get("evaluation_status") or "")
            if evaluation_status not in {"eligible", "pending"}:
                item["evaluation_status"] = "quarantined"
                item["quarantine_reason"] = str(
                    item.get("quarantine_reason")
                    or "provider_contract:evaluation_status_unusable"
                )
                quarantined.append(item)
                continue
            item["quarantine_reason"] = None
        elif is_current_record and not has_evaluation_source:
            item["evaluation_status"] = "pending"
            item["quarantine_reason"] = None
        elif has_evaluation_source or has_record_version:
            item["evaluation_status"] = "quarantined"
            item["quarantine_reason"] = "provider_contract:unknown_record_marker"
            quarantined.append(item)
            continue
        else:
            quarantine_reason = str(item.get("quarantine_reason") or "")
            if item.get("evaluation_status") == "quarantined":
                quarantine_reason = (
                    quarantine_reason
                    or "上游已标记口径异常，缺少可安全纳入统计的证据。"
                )
            else:
                quarantine_reason = price_basis_quarantine_reason(
                    str(item.get("reason") or ""),
                    item.get("reference_price"),
                ) or ""
            if quarantine_reason:
                item["evaluation_status"] = "quarantined"
                item["quarantine_reason"] = quarantine_reason
                quarantined.append(item)
                continue
            item["evaluation_status"] = "eligible"
            item["quarantine_reason"] = None
        included.append(item)

    eligible = [
        row
        for row in included
        if row.get("evaluation_status") == "eligible"
        and row.get("action_class") in {"hold", "risk_reduce"}
    ]
    horizons: dict[str, dict[str, object]] = {}
    for horizon in HORIZONS:
        return_key = f"return_{horizon}d"
        hit_key = f"hit_{horizon}d"
        matured = [row for row in eligible if isinstance(row.get(return_key), (int, float))]
        hits = sum(1 for row in matured if row.get(hit_key) is True)
        effects = [value for row in matured if isinstance((value := row.get(f"effect_{horizon}d")), (int, float))]
        horizons[f"{horizon}d"] = {
            "matured": len(matured),
            "hits": hits,
            "hit_rate": round(hits / len(matured), 4) if matured else None,
            "average_effect": round(sum(effects) / len(effects), 6) if effects else None,
        }

    latest = sorted(
        included,
        key=lambda row: (str(row.get("signal_date", "")), str(row.get("code", ""))),
        reverse=True,
    )[:8]
    quarantined_latest = sorted(
        quarantined,
        key=lambda row: (str(row.get("signal_date", "")), str(row.get("code", ""))),
        reverse=True,
    )[:8]
    evaluated_dates = [
        str(row.get("last_price_date"))
        for row in included
        if row.get("evaluation_status") == "eligible" and row.get("last_price_date")
    ]
    return {
        "tracked_signals": len(included),
        "tracked_symbols": len(
            {str(row.get("code")) for row in included if row.get("code")}
        ),
        "pending_signals": sum(
            1 for row in included if row.get("status") == "pending"
        ),
        "quarantined_signals": len(quarantined),
        "as_of_trade_date": max(evaluated_dates) if evaluated_dates else None,
        "horizons": horizons,
        "latest": latest,
        "quarantined_latest": quarantined_latest,
        "ledger": str(LEDGER_PATH),
        "method": "盘后信号以信号日最近有效收盘价为基准；持有类后续上涨为命中，降风险类后续下跌为命中。",
    }


def price_basis_quarantine_reason(
    rule_text: str,
    reference_price: object,
) -> str | None:
    """Legacy-only heuristic for unversioned ledgers and historical plan rows."""

    if not isinstance(reference_price, (int, float)) or reference_price <= 0:
        return None
    ma_values = [
        float(value)
        for value in MA20_VALUE_PATTERN.findall(rule_text)
    ]
    if any(
        abs(value / float(reference_price) - 1.0) > PRICE_BASIS_MISMATCH_LIMIT
        for value in ma_values
    ):
        return "历史20日线与当前价格偏差超过35%，复权或标的映射口径待核对。"
    return None


def outcome_markdown_lines(snapshot: dict[str, object]) -> list[str]:
    tracked = int(str(snapshot.get("tracked_signals", 0) or 0))
    symbols = int(str(snapshot.get("tracked_symbols", 0) or 0))
    pending = int(str(snapshot.get("pending_signals", 0) or 0))
    as_of = snapshot.get("as_of_trade_date") or "暂无有效收盘日"
    lines = [f"已跟踪 {tracked} 条信号 / {symbols} 只股票；待到期 {pending} 条；行情截至 {as_of}。"]
    horizons = snapshot.get("horizons", {})
    if isinstance(horizons, dict):
        for label in ("1d", "5d", "20d"):
            item = horizons.get(label, {})
            if not isinstance(item, dict) or not item.get("matured"):
                lines.append(f"{label}：暂无到期样本，不提前宣称命中率。")
                continue
            rate = float(item.get("hit_rate", 0.0))
            effect = float(item.get("average_effect", 0.0))
            lines.append(
                f"{label}：样本 {item['matured']}，命中率 {rate:.1%}，方向调整后平均效果 {effect:+.2%}。"
            )
    lines.append(str(snapshot.get("method", "")))
    return [line for line in lines if line]


def _import_report_signals(report_dir: Path) -> list[dict[str, object]]:
    if not report_dir.exists():
        return []
    latest_by_date: dict[str, tuple[Path, dict[str, object]]] = {}
    for path in sorted(report_dir.glob("*-after-close.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        signal_date = str(payload.get("generated_at", ""))[:10]
        if not _parse_iso_date(signal_date):
            continue
        latest_by_date[signal_date] = (path, payload)

    rows: list[dict[str, object]] = []
    for signal_date, (path, payload) in latest_by_date.items():
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            raw = dict(action)
            raw["signal_date"] = signal_date
            row = _normalise_signal(raw, default_date=signal_date, source_report=path.name)
            if row:
                rows.append(row)
    return rows


def _normalise_signal(
    signal: dict[str, object],
    *,
    default_date: str,
    source_report: str,
) -> dict[str, object] | None:
    name = str(signal.get("name", "")).strip()
    code = str(signal.get("code", "")).strip().upper()
    if not code:
        match = CODE_PATTERN.search(name)
        code = match.group("code") if match else ""
    if not CODE_PATTERN.fullmatch(code):
        return None
    signal_date = str(signal.get("signal_date", default_date))[:10]
    if not _parse_iso_date(signal_date):
        return None
    action = str(signal.get("action", "")).strip()
    row: dict[str, object] = {
        "signal_id": f"{signal_date}:{code}",
        "signal_date": signal_date,
        "code": code,
        "name": name or code,
        "action": action,
        "action_class": _action_class(action),
        "priority": str(signal.get("priority", "")).strip(),
        "reason": str(signal.get("reason", "")).strip(),
        "source_report": source_report,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "status": "pending",
    }
    return row


def _merge_signal(existing: dict[str, object] | None, new: dict[str, object]) -> dict[str, object]:
    if existing is None:
        return new
    merged = dict(existing)
    for key, value in new.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _evaluate_records(client: object, records: list[dict[str, object]], today: date) -> None:
    dates = [_parse_iso_date(str(row.get("signal_date", ""))) for row in records]
    valid_dates = [value for value in dates if value is not None]
    codes = sorted({str(row.get("code")) for row in records if row.get("code")})
    if not valid_dates or not codes:
        return
    begin = int((min(valid_dates) - timedelta(days=10)).strftime("%Y%m%d"))
    end = int(today.strftime("%Y%m%d"))
    batch_result: ProviderResult[dict[str, pd.DataFrame]] = (
        client.query_daily_kline_result(codes, begin, end)  # type: ignore[attr-defined]
    )
    evaluated_at = datetime.now().isoformat(timespec="seconds")
    for row in records:
        code = str(row.get("code") or "")
        result = daily_kline_result_for_code(batch_result, code)
        previous_basis = (
            str(row.get("price_basis") or "")
            if row.get("evaluation_source") == EVALUATION_SOURCE
            else ""
        )
        _store_provider_context(row, result)
        if result.status == "empty" and result.provider == "amazingdata" and result.schema_version == DAILY_KLINE_SCHEMA_VERSION:
            row["evaluation_status"] = "pending"
            row["status"] = "pending"
            row["evaluation_gap"] = _provider_context_reason(result)
            row.pop("quarantine_reason", None)
            continue
        quarantine_reason = _provider_quarantine_reason(
            result,
            code=code,
            previous_basis=previous_basis,
        )
        if quarantine_reason:
            row["evaluation_status"] = "quarantined"
            row["quarantine_reason"] = quarantine_reason
            continue
        row["evaluation_status"] = "eligible"
        row["price_basis"] = result.price_basis
        row.pop("quarantine_reason", None)
        _clear_calculated_outcomes(row)
        _evaluate_record(row, result.data, evaluated_at)


def _store_provider_context(
    row: dict[str, object],
    result: ProviderResult[pd.DataFrame],
) -> None:
    row.update(
        {
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "evaluation_source": EVALUATION_SOURCE,
            "provider": result.provider,
            "provider_schema_version": result.schema_version,
            "provider_status": result.status,
            "provider_gaps": list(result.gaps),
            "provider_errors": list(result.errors),
            "provider_source_time": result.source_time.isoformat() if result.source_time else None,
            "provider_fetched_at": result.fetched_at.isoformat(),
            "provider_trade_date": result.trade_date.isoformat() if result.trade_date else None,
            "provider_price_basis": result.price_basis,
        }
    )


def _provider_quarantine_reason(
    result: ProviderResult[pd.DataFrame],
    *,
    code: str,
    previous_basis: str,
) -> str | None:
    if result.provider != "amazingdata":
        return f"provider_contract:provider={result.provider}"
    if result.schema_version != DAILY_KLINE_SCHEMA_VERSION:
        return f"provider_contract:schema_version={result.schema_version}"
    if result.status in {"invalid", "quarantined"}:
        return _provider_context_reason(result)
    if result.status == "partial" and (
        not result.gaps
        or not all(_is_safe_partial_gap(gap, code) for gap in result.gaps)
    ):
        return _provider_context_reason(result)
    if result.status not in {"ok", "partial"}:
        return _provider_context_reason(result)
    if result.price_basis not in EVALUATABLE_PRICE_BASES:
        return f"provider_contract:price_basis={result.price_basis}"
    if previous_basis in EVALUATABLE_PRICE_BASES and previous_basis != result.price_basis:
        return f"provider_contract:price_basis_changed:{previous_basis}->{result.price_basis}"
    return None


def _is_safe_partial_gap(gap: str, code: str) -> bool:
    prefix = f"{code}:"
    if not gap.startswith(prefix):
        return False
    detail = gap[len(prefix) :]
    return detail == "timestamps_reordered" or detail.startswith(
        "duplicate_trade_dates:"
    )


def _provider_context_reason(result: ProviderResult[pd.DataFrame]) -> str:
    details = [*result.errors, *result.gaps]
    suffix = f";details={','.join(details)}" if details else ""
    return f"provider_contract:status={result.status}{suffix}"


def _clear_calculated_outcomes(row: dict[str, object]) -> None:
    for horizon in HORIZONS:
        for prefix in ("return", "effect", "hit", "price", "date"):
            row.pop(f"{prefix}_{horizon}d", None)
    for key in ("base_trade_date", "reference_price", "last_price_date", "available_sessions", "mfe_20d", "mae_20d"):
        row.pop(key, None)


def _evaluate_record(row: dict[str, object], frame: pd.DataFrame, evaluated_at: str) -> None:
    if frame.empty:
        row["status"] = "pending"
        row["evaluation_status"] = "pending"
        row["evaluation_gap"] = "未取得有效日线"
        return
    signal_date = _parse_iso_date(str(row.get("signal_date", "")))
    if signal_date is None:
        row["status"] = "pending"
        row["evaluation_status"] = "pending"
        row["evaluation_gap"] = "signal_date_invalid"
        return
    base_candidates = frame[frame["trade_date"] <= pd.Timestamp(signal_date)]
    if base_candidates.empty:
        row["status"] = "pending"
        row["evaluation_status"] = "pending"
        row["evaluation_gap"] = "信号日前无有效收盘价"
        return
    base_index = int(base_candidates.index[-1])
    base = frame.loc[base_index]
    reference = float(base["close"])
    available = max(0, len(frame) - base_index - 1)
    row.update(
        {
            "base_trade_date": base["trade_date"].date().isoformat(),
            "reference_price": round(reference, 6),
            "last_price_date": frame.iloc[-1]["trade_date"].date().isoformat(),
            "available_sessions": available,
            "last_evaluated_at": evaluated_at,
        }
    )
    action_class = str(row.get("action_class", "wait"))
    for horizon in HORIZONS:
        if available < horizon:
            continue
        end_row = frame.loc[base_index + horizon]
        raw_return = float(end_row["close"]) / reference - 1.0
        effect = -raw_return if action_class == "risk_reduce" else raw_return
        row[f"return_{horizon}d"] = round(raw_return, 6)
        row[f"effect_{horizon}d"] = round(effect, 6)
        row[f"hit_{horizon}d"] = effect >= 0
        row[f"price_{horizon}d"] = round(float(end_row["close"]), 6)
        row[f"date_{horizon}d"] = end_row["trade_date"].date().isoformat()
    future = frame.iloc[base_index + 1 : base_index + min(available, 20) + 1]
    if not future.empty:
        row["mfe_20d"] = round(float(future["high"].max()) / reference - 1.0, 6)
        row["mae_20d"] = round(float(future["low"].min()) / reference - 1.0, 6)
    row.pop("evaluation_gap", None)
    row["status"] = "complete" if available >= 20 else ("partial" if available >= 1 else "pending")


def _action_class(action: str) -> str:
    if any(word in action for word in ("减仓", "退出", "降低", "降集中度", "锁定利润")):
        return "risk_reduce"
    if any(word in action for word in ("持有", "观察", "保护浮盈")):
        return "hold"
    return "wait"


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _read_ledger(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_ledger(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in records)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")
