"""Persistent after-close signal outcome tracking for InsightRadar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any, Iterable

import pandas as pd

from stock_assist.paths import DATA_DIR, REPORT_DIR


LEDGER_PATH = DATA_DIR / "signal_outcomes.jsonl"
HORIZONS = (1, 5, 20)
CODE_PATTERN = re.compile(r"(?P<code>\d{6}\.(?:SZ|SH))")


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
        row = _normalise_signal(signal, default_date=today.isoformat(), source_report="current-run")
        if row:
            records[str(row["signal_id"])] = _merge_signal(records.get(str(row["signal_id"])), row)

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

    eligible = [row for row in records if row.get("action_class") in {"hold", "risk_reduce"}]
    horizons: dict[str, dict[str, object]] = {}
    for horizon in HORIZONS:
        return_key = f"return_{horizon}d"
        hit_key = f"hit_{horizon}d"
        matured = [row for row in eligible if isinstance(row.get(return_key), (int, float))]
        hits = sum(1 for row in matured if row.get(hit_key) is True)
        effects = [float(row[f"effect_{horizon}d"]) for row in matured if isinstance(row.get(f"effect_{horizon}d"), (int, float))]
        horizons[f"{horizon}d"] = {
            "matured": len(matured),
            "hits": hits,
            "hit_rate": round(hits / len(matured), 4) if matured else None,
            "average_effect": round(sum(effects) / len(effects), 6) if effects else None,
        }

    latest = sorted(
        records,
        key=lambda row: (str(row.get("signal_date", "")), str(row.get("code", ""))),
        reverse=True,
    )[:8]
    evaluated_dates = [str(row.get("last_price_date")) for row in records if row.get("last_price_date")]
    return {
        "tracked_signals": len(records),
        "tracked_symbols": len({str(row.get("code")) for row in records if row.get("code")}),
        "pending_signals": sum(1 for row in records if row.get("status") == "pending"),
        "as_of_trade_date": max(evaluated_dates) if evaluated_dates else None,
        "horizons": horizons,
        "latest": latest,
        "ledger": str(LEDGER_PATH),
        "method": "盘后信号以信号日最近有效收盘价为基准；持有类后续上涨为命中，降风险类后续下跌为命中。",
    }


def outcome_markdown_lines(snapshot: dict[str, object]) -> list[str]:
    tracked = int(snapshot.get("tracked_signals", 0) or 0)
    symbols = int(snapshot.get("tracked_symbols", 0) or 0)
    pending = int(snapshot.get("pending_signals", 0) or 0)
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
    raw = client.query_daily_kline(codes, begin, end)  # type: ignore[attr-defined]
    frames = {}
    for code in codes:
        frame = _normalise_price_frame(_frame_for_code(raw, code))
        if not frame.empty:
            frame = frame[frame["trade_date"] <= pd.Timestamp(today)].reset_index(drop=True)
        frames[code] = frame
    evaluated_at = datetime.now().isoformat(timespec="seconds")
    for row in records:
        frame = frames.get(str(row.get("code")), pd.DataFrame())
        _evaluate_record(row, frame, evaluated_at)


def _evaluate_record(row: dict[str, object], frame: pd.DataFrame, evaluated_at: str) -> None:
    if frame.empty:
        row["status"] = "pending"
        row["evaluation_gap"] = "未取得有效日线"
        return
    signal_date = _parse_iso_date(str(row.get("signal_date", "")))
    if signal_date is None:
        return
    base_candidates = frame[frame["trade_date"] <= pd.Timestamp(signal_date)]
    if base_candidates.empty:
        row["status"] = "pending"
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


def _normalise_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    date_col = _pick_column(frame, ["kline_time", "trade_date", "date", "交易日期", "S_DQ_DATE"])
    close_col = _pick_column(frame, ["close", "收盘价", "S_DQ_CLOSE"])
    if date_col is None or close_col is None:
        return pd.DataFrame()
    high_col = _pick_column(frame, ["high", "最高价", "S_DQ_HIGH"])
    low_col = _pick_column(frame, ["low", "最低价", "S_DQ_LOW"])
    result = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame[date_col], errors="coerce"),
            "close": pd.to_numeric(frame[close_col], errors="coerce"),
        }
    )
    result["high"] = pd.to_numeric(frame[high_col], errors="coerce") if high_col else result["close"]
    result["low"] = pd.to_numeric(frame[low_col], errors="coerce") if low_col else result["close"]
    result = result.dropna(subset=["trade_date", "close"])
    result = result[result["close"] > 0].sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return result.reset_index(drop=True)


def _frame_for_code(raw: object, code: str) -> pd.DataFrame:
    if isinstance(raw, dict):
        value = raw.get(code)
        if value is None:
            value = raw.get(code.replace(".", "_"))
        return value if isinstance(value, pd.DataFrame) else pd.DataFrame()
    if isinstance(raw, pd.DataFrame):
        if "code" in raw.columns:
            return raw[raw["code"].astype(str) == code]
        return raw
    return pd.DataFrame()


def _pick_column(frame: pd.DataFrame, names: list[str]) -> str | None:
    lowered = {str(column).lower(): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


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
