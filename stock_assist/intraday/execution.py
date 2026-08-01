"""Append-only, user-confirmed execution evidence for intraday re-entry rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from stock_assist.paths import DATA_DIR


DEFAULT_EXECUTION_LEDGER = DATA_DIR / "intraday" / "execution_ledger.jsonl"
DEFAULT_REENTRY_CONFIRMATION_LEDGER = (
    DATA_DIR / "intraday" / "reentry_confirmation_ledger.jsonl"
)


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    symbol: str
    target_id: str
    side: str
    quantity: float
    available_quantity: float
    sold_at: str
    sale_price: float
    source: str
    confirmed_at: str
    user_confirmed: bool = True
    reference_execution_id: str | None = None
    executed_at: str | None = None
    execution_price: float | None = None
    post_reentry_low_broken: bool = False


@dataclass(frozen=True)
class ReentryConfirmationRecord:
    confirmation_id: str
    symbol: str
    target_id: str
    sold_at: str
    failed_reentry_execution_id: str
    new_low_observed_at: str
    source: str
    confirmed_at: str
    user_confirmed: bool = True


def append_execution(
    payload: Mapping[str, object],
    *,
    path: Path = DEFAULT_EXECUTION_LEDGER,
    confirmed_at: datetime | None = None,
) -> ExecutionRecord:
    """Append one explicitly confirmed broker execution; never replace prior evidence."""

    if payload.get("user_confirmed") is not True:
        raise ValueError("execution evidence requires explicit user_confirmed=true")
    record = execution_from_mapping(payload, confirmed_at=confirmed_at or datetime.now())
    existing = {item.execution_id for item in load_executions(path)}
    if record.execution_id in existing:
        return record
    line = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n"
    _append_line(path, line)
    return record


def append_reentry_confirmation(
    payload: Mapping[str, object],
    *,
    execution_path: Path = DEFAULT_EXECUTION_LEDGER,
    path: Path = DEFAULT_REENTRY_CONFIRMATION_LEDGER,
    confirmed_at: datetime | None = None,
) -> ReentryConfirmationRecord:
    """Append a post-failure user confirmation without inventing another fill."""

    if payload.get("user_confirmed") is not True:
        raise ValueError("re-entry confirmation requires explicit user_confirmed=true")
    symbol = str(payload.get("symbol") or "").upper()
    target_id = str(payload.get("target_id") or "")
    sold_at = _required_datetime(payload.get("sold_at"), "sold_at")
    failed_id = str(payload.get("failed_reentry_execution_id") or "")
    source = str(payload.get("source") or "")
    if not all((symbol, target_id, failed_id, source)):
        raise ValueError(
            "re-entry confirmation requires symbol, target_id, "
            "failed_reentry_execution_id, and source"
        )
    failed = next(
        (
            item
            for item in load_executions(execution_path)
            if item.execution_id == failed_id
            and item.side == "buy"
            and item.symbol == symbol
            and item.target_id == target_id
            and item.sold_at == sold_at
        ),
        None,
    )
    if failed is None or failed.executed_at is None:
        raise ValueError("failed re-entry must reference a matching confirmed buy execution")
    new_low_at = _required_datetime(payload.get("new_low_observed_at"), "new_low_observed_at")
    if datetime.fromisoformat(new_low_at) <= datetime.fromisoformat(failed.executed_at):
        raise ValueError("new_low_observed_at must be after the failed re-entry execution")
    confirmation = (confirmed_at or datetime.now()).isoformat(timespec="seconds")
    if datetime.fromisoformat(confirmation) < datetime.fromisoformat(new_low_at):
        raise ValueError("confirmation cannot predate the new-low observation")
    canonical = {
        "symbol": symbol,
        "target_id": target_id,
        "sold_at": sold_at,
        "failed_reentry_execution_id": failed_id,
        "new_low_observed_at": new_low_at,
        "source": source,
    }
    identity = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record = ReentryConfirmationRecord(
        confirmation_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        confirmed_at=confirmation,
        user_confirmed=True,
        **canonical,
    )
    existing = {item.confirmation_id for item in load_reentry_confirmations(path)}
    if record.confirmation_id not in existing:
        _append_line(path, json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


def load_executions(path: Path = DEFAULT_EXECUTION_LEDGER) -> tuple[ExecutionRecord, ...]:
    if not path.exists():
        return ()
    result: list[ExecutionRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, Mapping) or item.get("user_confirmed") is not True:
            continue
        try:
            result.append(execution_from_mapping(item))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(result, key=lambda item: (item.sold_at, item.confirmed_at, item.execution_id)))


def load_reentry_confirmations(
    path: Path = DEFAULT_REENTRY_CONFIRMATION_LEDGER,
) -> tuple[ReentryConfirmationRecord, ...]:
    if not path.exists():
        return ()
    result: list[ReentryConfirmationRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, Mapping) or item.get("user_confirmed") is not True:
            continue
        required = (
            "confirmation_id", "symbol", "target_id", "sold_at",
            "failed_reentry_execution_id", "new_low_observed_at", "source", "confirmed_at",
        )
        if any(not str(item.get(field) or "") for field in required):
            continue
        try:
            result.append(
                ReentryConfirmationRecord(
                    confirmation_id=str(item["confirmation_id"]),
                    symbol=str(item["symbol"]).upper(),
                    target_id=str(item["target_id"]),
                    sold_at=_required_datetime(item["sold_at"], "sold_at"),
                    failed_reentry_execution_id=str(item["failed_reentry_execution_id"]),
                    new_low_observed_at=_required_datetime(
                        item["new_low_observed_at"], "new_low_observed_at"
                    ),
                    source=str(item["source"]),
                    confirmed_at=_required_datetime(item["confirmed_at"], "confirmed_at"),
                    user_confirmed=True,
                )
            )
        except (TypeError, ValueError):
            continue
    return tuple(sorted(result, key=lambda item: (item.confirmed_at, item.confirmation_id)))


def execution_from_mapping(
    item: Mapping[str, object],
    *,
    confirmed_at: datetime | None = None,
) -> ExecutionRecord:
    required_text = ("symbol", "target_id", "side", "sold_at", "source")
    missing = [key for key in required_text if not str(item.get(key) or "").strip()]
    if missing:
        raise ValueError("execution evidence missing: " + ", ".join(missing))
    side = str(item["side"]).lower()
    if side not in {"sell", "buy"}:
        raise ValueError("execution side must be sell or buy")
    quantity = _required_positive(item.get("quantity"), "quantity")
    available = _required_non_negative(item.get("available_quantity"), "available_quantity")
    sale_price = _required_positive(item.get("sale_price"), "sale_price")
    sold_at = datetime.fromisoformat(str(item["sold_at"])).isoformat(timespec="seconds")
    executed_at = _optional_text(item.get("executed_at"))
    execution_price = _optional_positive(item.get("execution_price"))
    if side == "buy":
        if executed_at is None or execution_price is None:
            raise ValueError("buy execution requires executed_at and execution_price")
        executed_at = datetime.fromisoformat(executed_at).isoformat(timespec="seconds")
    elif available <= 0 or quantity > available:
        raise ValueError("sell quantity cannot exceed positive available_quantity")
    confirmation = str(
        item.get("confirmed_at")
        or (confirmed_at.isoformat(timespec="seconds") if confirmed_at else sold_at)
    )
    canonical = {
        "symbol": str(item["symbol"]).upper(),
        "target_id": str(item["target_id"]),
        "side": side,
        "quantity": quantity,
        "available_quantity": available,
        "sold_at": sold_at,
        "sale_price": sale_price,
        "source": str(item["source"]),
        "confirmed_at": confirmation,
        "reference_execution_id": _optional_text(item.get("reference_execution_id")),
        "executed_at": executed_at,
        "execution_price": execution_price,
        "post_reentry_low_broken": item.get("post_reentry_low_broken") is True,
    }
    identity_fields = dict(canonical)
    identity_fields.pop("confirmed_at", None)
    identity = json.dumps(
        identity_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    execution_id = str(item.get("execution_id") or hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24])
    return ExecutionRecord(
        execution_id=execution_id,
        user_confirmed=True,
        **canonical,
    )


def _required_positive(value: object, field: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _required_non_negative(value: object, field: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _optional_positive(value: object) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _required_datetime(value: object, field: str) -> str:
    try:
        return datetime.fromisoformat(str(value)).isoformat(timespec="seconds")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
