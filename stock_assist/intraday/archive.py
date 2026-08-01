"""Local JSONL archive for minute bars and point-in-time quotes."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from stock_assist.intraday.contracts import MinuteBar, PointQuote, contract_dict
from stock_assist.paths import DATA_DIR


DEFAULT_INTRADAY_ROOT = DATA_DIR / "intraday"


class MinuteArchive:
    """Persist provider observations by trade date and symbol.

    The interface is intentionally small: write immutable provider rows, then
    read one day with an optional point-in-time cutoff.  Rules never call a
    market provider directly.
    """

    def __init__(self, root: Path = DEFAULT_INTRADAY_ROOT) -> None:
        self.root = root

    def write_bars(self, bars: Iterable[MinuteBar]) -> list[Path]:
        groups: dict[tuple[date, str, str, datetime], list[MinuteBar]] = defaultdict(list)
        for bar in bars:
            groups[(bar.timestamp.date(), _slug(bar.source), bar.symbol, bar.fetched_at)].append(bar)
        paths: list[Path] = []
        for (trade_date, provider_slug, symbol, _fetched_at), rows in sorted(groups.items()):
            records = [
                _observation_record(item, trade_date=trade_date, provider=item.source)
                for item in sorted(rows, key=lambda item: (item.source_time, item.timestamp))
            ]
            content = "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                for item in records
            )
            batch_id = hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]
            path = (
                self.root / "minute" / trade_date.isoformat() / provider_slug /
                symbol.upper() / f"{batch_id}.jsonl"
            )
            _atomic_write_once(path, content)
            paths.append(path)
        return paths

    def write_quotes(self, quotes: Iterable[PointQuote]) -> list[Path]:
        groups: dict[tuple[date, str, datetime], list[PointQuote]] = defaultdict(list)
        for quote in quotes:
            groups[(quote.timestamp.date(), _slug(quote.source), quote.fetched_at)].append(quote)
        paths: list[Path] = []
        for (trade_date, provider_slug, _fetched_at), rows in sorted(groups.items()):
            records = [
                _observation_record(item, trade_date=trade_date, provider=item.source)
                for item in sorted(rows, key=lambda item: (item.source_time, item.symbol))
            ]
            content = "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                for item in records
            )
            batch_id = hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]
            path = self.root / "quotes" / trade_date.isoformat() / provider_slug / f"{batch_id}.jsonl"
            _atomic_write_once(path, content)
            paths.append(path)
        return paths

    def read_bars(
        self,
        trade_date: date,
        *,
        symbols: Iterable[str] | None = None,
        through: datetime | None = None,
        observed_through: datetime | None = None,
    ) -> dict[str, list[MinuteBar]]:
        observations = self.read_bar_observations(
            trade_date,
            symbols=symbols,
            through=through,
            observed_through=observed_through,
        )
        selected: dict[tuple[str, datetime, str], MinuteBar] = {}
        for symbol, rows in observations.items():
            for bar in rows:
                key = (symbol, bar.timestamp, bar.source)
                prior = selected.get(key)
                if prior is None or (bar.fetched_at, bar.observation_id) > (
                    prior.fetched_at,
                    prior.observation_id,
                ):
                    selected[key] = bar
        result: dict[str, list[MinuteBar]] = defaultdict(list)
        for (symbol, _timestamp, _source), bar in selected.items():
            result[symbol].append(bar)
        return {
            symbol: sorted(rows, key=lambda item: (item.timestamp, item.fetched_at))
            for symbol, rows in result.items()
        }

    def read_bar_observations(
        self,
        trade_date: date,
        *,
        symbols: Iterable[str] | None = None,
        through: datetime | None = None,
        observed_through: datetime | None = None,
    ) -> dict[str, list[MinuteBar]]:
        """Return every immutable supplier observation, including later corrections."""

        wanted = {str(item).upper() for item in symbols} if symbols is not None else None
        result: dict[str, list[MinuteBar]] = defaultdict(list)
        day_root = self.root / "minute" / trade_date.isoformat()
        if not day_root.exists():
            return {}
        for path in sorted(day_root.rglob("*.jsonl")):
            for item in _jsonl_rows(path):
                bar = _bar_from_dict(item)
                symbol = bar.symbol.upper()
                if wanted is not None and symbol not in wanted:
                    continue
                if (through is None or bar.timestamp <= through) and (
                    observed_through is None or bar.fetched_at <= observed_through
                ):
                    result[symbol].append(bar)
        return {
            symbol: sorted(rows, key=lambda item: (item.fetched_at, item.source_time, item.observation_id))
            for symbol, rows in result.items()
        }

    def read_quotes(
        self,
        trade_date: date,
        *,
        through: datetime | None = None,
        observed_through: datetime | None = None,
    ) -> list[PointQuote]:
        observations = self.read_quote_observations(
            trade_date,
            through=through,
            observed_through=observed_through,
        )
        selected: dict[tuple[str, datetime, str], PointQuote] = {}
        for quote in observations:
            key = (quote.symbol, quote.timestamp, quote.source)
            prior = selected.get(key)
            if prior is None or (quote.fetched_at, quote.observation_id) > (
                prior.fetched_at,
                prior.observation_id,
            ):
                selected[key] = quote
        return sorted(selected.values(), key=lambda item: (item.timestamp, item.symbol))

    def read_quote_observations(
        self,
        trade_date: date,
        *,
        through: datetime | None = None,
        observed_through: datetime | None = None,
    ) -> list[PointQuote]:
        """Return every immutable quote observation, including corrections."""

        rows: list[PointQuote] = []
        day_root = self.root / "quotes" / trade_date.isoformat()
        if not day_root.exists():
            return rows
        for path in sorted(day_root.rglob("*.jsonl")):
            for item in _jsonl_rows(path):
                quote = _quote_from_dict(item)
                if (through is None or quote.timestamp <= through) and (
                    observed_through is None or quote.fetched_at <= observed_through
                ):
                    rows.append(quote)
        return sorted(rows, key=lambda item: (item.fetched_at, item.source_time, item.symbol, item.observation_id))

    def available_dates(self) -> tuple[date, ...]:
        root = self.root / "minute"
        if not root.exists():
            return ()
        result: list[date] = []
        for item in root.iterdir():
            try:
                result.append(date.fromisoformat(item.name))
            except ValueError:
                continue
        return tuple(sorted(result))

def _bar_from_dict(item: dict[str, object]) -> MinuteBar:
    timestamp = datetime.fromisoformat(str(item["timestamp"]))
    return MinuteBar(
        symbol=str(item["symbol"]).upper(),
        timestamp=timestamp,
        open=float(item["open"]),
        high=float(item["high"]),
        low=float(item["low"]),
        close=float(item["close"]),
        volume=float(item["volume"]),
        amount=float(item["amount"]),
        source_time=datetime.fromisoformat(str(item.get("source_time") or timestamp.isoformat())),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        source=str(item["source"]),
        observation_id=str(item.get("observation_id") or _record_id(item)),
        trade_date=str(item.get("trade_date") or timestamp.date().isoformat()),
        provider=str(item.get("provider") or item.get("source") or "unknown"),
    )


def _quote_from_dict(item: dict[str, object]) -> PointQuote:
    timestamp = datetime.fromisoformat(str(item["timestamp"]))
    return PointQuote(
        symbol=str(item["symbol"]).upper(),
        timestamp=timestamp,
        price=float(item["price"]),
        pre_close=_optional_float(item.get("pre_close")),
        open=_optional_float(item.get("open")),
        high=_optional_float(item.get("high")),
        low=_optional_float(item.get("low")),
        volume=_optional_float(item.get("volume")),
        amount=_optional_float(item.get("amount")),
        source_time=datetime.fromisoformat(str(item.get("source_time") or timestamp.isoformat())),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        source=str(item["source"]),
        phase=str(item.get("phase") or ""),
        observation_id=str(item.get("observation_id") or _record_id(item)),
        trade_date=str(item.get("trade_date") or timestamp.date().isoformat()),
        provider=str(item.get("provider") or item.get("source") or "unknown"),
    )


def _jsonl_rows(path: Path) -> Iterable[dict[str, object]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            yield item


def _atomic_write_once(path: Path, content: str) -> None:
    """Create one content-addressed archive member without replacing prior bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content.encode("utf-8"):
            raise RuntimeError(f"observation id collision: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            if path.read_bytes() != content.encode("utf-8"):
                raise RuntimeError(f"observation id collision: {path}")
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _slug(value: str) -> str:
    clean = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in clean.split("-") if part) or "unknown"


def _observation_record(value: MinuteBar | PointQuote, *, trade_date: date, provider: str) -> dict[str, object]:
    record = dict(contract_dict(value))
    record["trade_date"] = trade_date.isoformat()
    record["provider"] = provider
    record.pop("observation_id", None)
    record["observation_id"] = _record_id(record)
    return record


def _record_id(item: dict[str, object]) -> str:
    payload = dict(item)
    payload.pop("observation_id", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
