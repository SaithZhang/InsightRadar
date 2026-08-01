"""Append-only, user-confirmed execution evidence for intraday re-entry rules."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

from stock_assist.intraday.contracts import MinuteBar

from stock_assist.paths import DATA_DIR


DEFAULT_EXECUTION_LEDGER = DATA_DIR / "intraday" / "execution_ledger.jsonl"
DEFAULT_REENTRY_CONFIRMATION_LEDGER = (
    DATA_DIR / "intraday" / "reentry_confirmation_ledger.jsonl"
)
DEFAULT_REENTRY_FAILURE_LEDGER = DATA_DIR / "intraday" / "reentry_failure_ledger.jsonl"


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
    failure_observation_id: str
    new_low_observed_at: str
    source: str
    confirmed_at: str
    user_confirmed: bool = True


@dataclass(frozen=True)
class ReentryFailureRecord:
    failure_id: str
    symbol: str
    target_id: str
    referenced_buy_execution_id: str
    referenced_sell_execution_id: str
    source_time: str
    fetched_at: str
    price: float
    first_reentry_price: float
    market_observation_id: str
    rule_version: str


def append_execution(
    payload: Mapping[str, object],
    *,
    path: Path = DEFAULT_EXECUTION_LEDGER,
    confirmed_at: datetime | None = None,
) -> ExecutionRecord:
    """Append one explicitly confirmed broker execution; never replace prior evidence."""

    if payload.get("user_confirmed") is not True:
        raise ValueError("execution evidence requires explicit user_confirmed=true")
    with _ledger_single_flight(path):
        record = execution_from_mapping(
            payload,
            confirmed_at=confirmed_at or datetime.now(),
        )
        existing_records = load_executions(path)
        existing = {item.execution_id for item in existing_records}
        if record.execution_id in existing:
            return record
        if record.side == "buy":
            _validate_buy_reference(record, existing_records)
        line = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n"
        _append_line(path, line)
        return record


def append_reentry_confirmation(
    payload: Mapping[str, object],
    *,
    execution_path: Path = DEFAULT_EXECUTION_LEDGER,
    failure_path: Path = DEFAULT_REENTRY_FAILURE_LEDGER,
    path: Path = DEFAULT_REENTRY_CONFIRMATION_LEDGER,
    confirmed_at: datetime | None = None,
) -> ReentryConfirmationRecord:
    """Append a post-failure user confirmation without inventing another fill."""

    with _ledger_single_flight(execution_path):
        return _append_reentry_confirmation_unlocked(
            payload,
            execution_path=execution_path,
            failure_path=failure_path,
            path=path,
            confirmed_at=confirmed_at,
        )


def _append_reentry_confirmation_unlocked(
    payload: Mapping[str, object],
    *,
    execution_path: Path,
    failure_path: Path,
    path: Path,
    confirmed_at: datetime | None,
) -> ReentryConfirmationRecord:

    if payload.get("user_confirmed") is not True:
        raise ValueError("re-entry confirmation requires explicit user_confirmed=true")
    symbol = str(payload.get("symbol") or "").upper()
    target_id = str(payload.get("target_id") or "")
    sold_at = _required_datetime(payload.get("sold_at"), "sold_at")
    failure_observation_id = str(payload.get("failure_observation_id") or "")
    source = str(payload.get("source") or "")
    if not all((symbol, target_id, failure_observation_id, source)):
        raise ValueError(
            "re-entry confirmation requires symbol, target_id, "
            "failure_observation_id, and source"
        )
    failure = next(
        (
            item for item in load_reentry_failures(failure_path)
            if item.failure_id == failure_observation_id
            and item.symbol == symbol
            and item.target_id == target_id
        ),
        None,
    )
    if failure is None:
        raise ValueError("override must reference a real re-entry failure observation")
    executions = {item.execution_id: item for item in load_executions(execution_path)}
    failed = executions.get(failure.referenced_buy_execution_id)
    sale = executions.get(failure.referenced_sell_execution_id)
    if (
        failed is None or sale is None or failed.side != "buy" or sale.side != "sell"
        or failed.reference_execution_id != sale.execution_id
        or sale.sold_at != sold_at
    ):
        raise ValueError("failure observation execution lineage is unavailable")
    failed_id = failed.execution_id
    new_low_at = failure.source_time
    confirmation = (confirmed_at or datetime.now()).isoformat(timespec="seconds")
    if datetime.fromisoformat(confirmation) < datetime.fromisoformat(new_low_at):
        raise ValueError("confirmation cannot predate the new-low observation")
    canonical = {
        "symbol": symbol,
        "target_id": target_id,
        "sold_at": sold_at,
        "failed_reentry_execution_id": failed_id,
        "failure_observation_id": failure_observation_id,
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


def append_reentry_failure(
    payload: Mapping[str, object],
    *,
    execution_path: Path = DEFAULT_EXECUTION_LEDGER,
    path: Path = DEFAULT_REENTRY_FAILURE_LEDGER,
) -> ReentryFailureRecord:
    """Append one market-observed failed first re-entry; later prices cannot erase it."""

    with _ledger_single_flight(execution_path):
        return _append_reentry_failure_unlocked(
            payload,
            execution_path=execution_path,
            path=path,
        )


def _append_reentry_failure_unlocked(
    payload: Mapping[str, object],
    *,
    execution_path: Path,
    path: Path,
) -> ReentryFailureRecord:

    buy_id = str(payload.get("referenced_buy_execution_id") or "")
    sell_id = str(payload.get("referenced_sell_execution_id") or "")
    observation_id = str(payload.get("market_observation_id") or "")
    rule_version = str(payload.get("rule_version") or "")
    if not all((buy_id, sell_id, observation_id, rule_version)):
        raise ValueError(
            "re-entry failure requires referenced buy/sell executions, "
            "market_observation_id, and rule_version"
        )
    executions = {item.execution_id: item for item in load_executions(execution_path)}
    buy = executions.get(buy_id)
    sale = executions.get(sell_id)
    if (
        buy is None or sale is None or buy.side != "buy" or sale.side != "sell"
        or buy.reference_execution_id != sale.execution_id
    ):
        raise ValueError("re-entry failure execution lineage is invalid")
    source_time = _required_datetime(payload.get("source_time"), "source_time")
    fetched_at = _required_datetime(payload.get("fetched_at"), "fetched_at")
    if buy.executed_at is None or datetime.fromisoformat(source_time) <= datetime.fromisoformat(buy.executed_at):
        raise ValueError("failure observation must be after the referenced buy")
    if datetime.fromisoformat(fetched_at) < datetime.fromisoformat(source_time):
        raise ValueError("failure fetched_at cannot predate source_time")
    price = _required_positive(payload.get("price"), "price")
    first_reentry_price = _required_positive(
        payload.get("first_reentry_price"), "first_reentry_price"
    )
    if buy.execution_price != first_reentry_price:
        raise ValueError("first_reentry_price must match the referenced buy")
    if price >= first_reentry_price:
        raise ValueError("failure observation price must be below first re-entry price")
    canonical = {
        "symbol": buy.symbol,
        "target_id": buy.target_id,
        "referenced_buy_execution_id": buy.execution_id,
        "referenced_sell_execution_id": sale.execution_id,
        "source_time": source_time,
        "fetched_at": fetched_at,
        "price": price,
        "first_reentry_price": first_reentry_price,
        "market_observation_id": observation_id,
        "rule_version": rule_version,
    }
    identity = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record = ReentryFailureRecord(
        failure_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        **canonical,
    )
    existing = {item.failure_id for item in load_reentry_failures(path)}
    if record.failure_id not in existing:
        _append_line(path, json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


def detect_reentry_failures(
    bars: Mapping[str, Iterable[MinuteBar]],
    *,
    execution_path: Path = DEFAULT_EXECUTION_LEDGER,
    path: Path = DEFAULT_REENTRY_FAILURE_LEDGER,
    rule_version: str,
) -> tuple[ReentryFailureRecord, ...]:
    """Persist the first real post-buy lower observation for every referenced sale."""

    executions = load_executions(execution_path)
    existing_buy_ids = {
        item.referenced_buy_execution_id for item in load_reentry_failures(path)
    }
    created: list[ReentryFailureRecord] = []
    sales = {item.execution_id: item for item in executions if item.side == "sell"}
    for buy in executions:
        if (
            buy.side != "buy"
            or not buy.reference_execution_id
            or buy.execution_id in existing_buy_ids
            or buy.executed_at is None
            or buy.execution_price is None
        ):
            continue
        sale = sales.get(buy.reference_execution_id)
        if sale is None:
            continue
        executed_at = datetime.fromisoformat(buy.executed_at)
        candidates = sorted(
            (
                bar for bar in bars.get(buy.symbol, ())
                if bar.source_time > executed_at
                and bar.close < buy.execution_price
                and bool(bar.observation_id)
            ),
            key=lambda item: (item.source_time, item.fetched_at, item.observation_id),
        )
        if not candidates:
            continue
        observation = candidates[0]
        created.append(
            append_reentry_failure(
                {
                    "referenced_buy_execution_id": buy.execution_id,
                    "referenced_sell_execution_id": sale.execution_id,
                    "source_time": observation.source_time.isoformat(timespec="seconds"),
                    "fetched_at": observation.fetched_at.isoformat(timespec="seconds"),
                    "price": observation.close,
                    "first_reentry_price": buy.execution_price,
                    "market_observation_id": observation.observation_id,
                    "rule_version": rule_version,
                },
                execution_path=execution_path,
                path=path,
            )
        )
    return tuple(created)


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
            "failed_reentry_execution_id", "failure_observation_id",
            "new_low_observed_at", "source", "confirmed_at",
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
                    failure_observation_id=str(item["failure_observation_id"]),
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


def load_reentry_failures(
    path: Path = DEFAULT_REENTRY_FAILURE_LEDGER,
) -> tuple[ReentryFailureRecord, ...]:
    if not path.exists():
        return ()
    result: list[ReentryFailureRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            item = json.loads(line)
            result.append(
                ReentryFailureRecord(
                    failure_id=str(item["failure_id"]),
                    symbol=str(item["symbol"]).upper(),
                    target_id=str(item["target_id"]),
                    referenced_buy_execution_id=str(item["referenced_buy_execution_id"]),
                    referenced_sell_execution_id=str(item["referenced_sell_execution_id"]),
                    source_time=_required_datetime(item["source_time"], "source_time"),
                    fetched_at=_required_datetime(item["fetched_at"], "fetched_at"),
                    price=_required_positive(item["price"], "price"),
                    first_reentry_price=_required_positive(
                        item["first_reentry_price"], "first_reentry_price"
                    ),
                    market_observation_id=str(item["market_observation_id"]),
                    rule_version=str(item["rule_version"]),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return tuple(sorted(result, key=lambda item: (item.source_time, item.failure_id)))


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


def _validate_buy_reference(
    record: ExecutionRecord,
    existing: tuple[ExecutionRecord, ...],
) -> None:
    reference = record.reference_execution_id
    if not reference:
        raise ValueError("buy execution requires reference_execution_id")
    sale = next(
        (item for item in existing if item.execution_id == reference and item.side == "sell"),
        None,
    )
    if sale is None:
        raise ValueError("buy execution must reference an existing sell execution")
    if (
        record.symbol != sale.symbol
        or record.target_id != sale.target_id
        or record.sold_at != sale.sold_at
    ):
        raise ValueError("buy execution must match sell symbol, target_id, and sold_at")
    if record.executed_at is None or datetime.fromisoformat(record.executed_at) <= datetime.fromisoformat(sale.sold_at):
        raise ValueError("buy execution time must be after the referenced sell")
    already_bought = sum(
        item.quantity
        for item in existing
        if item.side == "buy" and item.reference_execution_id == sale.execution_id
    )
    if already_bought + record.quantity > sale.quantity:
        raise ValueError("cumulative re-entry quantity cannot exceed remaining sell quantity")


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


@contextmanager
def _ledger_single_flight(path: Path):
    """Serialize ledger validation and append across server threads/processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / ".intraday-ledger.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
