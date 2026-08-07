"""JSON-only command line adapter for intraday evidence."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from stock_assist.intraday.evidence import (
    IntradayEvidenceService,
    default_service,
    evidence_to_dict,
)
from stock_assist.intraday.evidence_contracts import TradeInput

SHANGHAI = ZoneInfo("Asia/Shanghai")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insight-radar intraday-evidence",
        description="Read-only A-share/ETF intraday evidence as structured JSON.",
    )
    commands = parser.add_subparsers(dest="evidence_command", required=True)

    get = commands.add_parser("get", help="get one normalized minute series")
    get.add_argument("symbol")
    get.add_argument("--date", type=_date, default=None)
    get.add_argument("--time", type=_time, default=None, help="optional HH:MM no-lookahead cutoff")

    compare = commands.add_parser("compare", help="compare symbols against a benchmark")
    compare.add_argument("symbols", nargs="+")
    compare.add_argument("--benchmark", required=True)
    compare.add_argument("--date", type=_date, default=None)
    compare.add_argument("--time", type=_time, default=None)

    amount = commands.add_parser("amount", help="compare CN A-share amount at the same minute")
    amount.add_argument("--date", type=_date, default=None)
    amount.add_argument("--time", type=_time, default=None)

    review = commands.add_parser("review", help="review private trade JSON against the tape")
    review.add_argument("file", type=Path)
    review.add_argument("--benchmark", required=True)
    review.add_argument("--date", type=_date, default=None, help="default date for rows without trade_date")
    return parser


def execute(
    argv: Sequence[str],
    *,
    service: IntradayEvidenceService | None = None,
) -> object:
    args = build_parser().parse_args(list(argv))
    evidence = service or default_service()
    default_day = args.date or datetime.now(SHANGHAI).date()
    result: object
    if args.evidence_command == "get":
        result = evidence.get_intraday(args.symbol, default_day, as_of=args.time)
    elif args.evidence_command == "compare":
        result = evidence.get_intraday_compare(
            args.symbols,
            benchmark=args.benchmark,
            trade_date=default_day,
            as_of=args.time,
        )
    elif args.evidence_command == "amount":
        result = evidence.get_market_amount_compare(default_day, as_of=args.time)
    elif args.evidence_command == "review":
        trades = load_trades(args.file, default_date=args.date)
        result = evidence.review_trades(trades, benchmark=args.benchmark)
    else:  # pragma: no cover - argparse owns the finite choices
        raise ValueError(f"unsupported evidence command: {args.evidence_command}")
    return evidence_to_dict(result)


def load_trades(path: Path, *, default_date: date | None = None) -> tuple[TradeInput, ...]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("trades") if isinstance(payload, dict) else payload
    return parse_trade_rows(rows, default_date=default_date)


def parse_trade_rows(rows: object, *, default_date: date | None = None) -> tuple[TradeInput, ...]:
    if not isinstance(rows, list):
        raise TypeError("trade file must contain a JSON list or {\"trades\": [...]}")
    result: list[TradeInput] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TypeError(f"trade row {index} must be an object")
        day_value = row.get("trade_date") or row.get("date")
        day = _date(str(day_value)) if day_value else default_date
        if day is None:
            raise ValueError(f"trade row {index} is missing trade_date and no --date was supplied")
        side = str(row.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"trade row {index} side must be buy or sell")
        quantity = _json_float(row.get("quantity"), field="quantity", row_index=index)
        price = _json_float(row.get("price"), field="price", row_index=index)
        result.append(
            TradeInput(
                trade_date=day,
                time=_time(str(row.get("time") or "")),
                symbol=str(row.get("symbol") or "").strip(),
                side=side,  # type: ignore[arg-type]
                quantity=quantity,
                price=price,
            )
        )
    return tuple(result)


def main(argv: Sequence[str] | None = None) -> int:
    payload = execute(argv if argv is not None else sys.argv[1:])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _json_float(value: object, *, field: str, row_index: int) -> float:
    if not isinstance(value, (int, float, str)):
        raise TypeError(f"trade row {row_index} {field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"trade row {row_index} {field} must be finite")
    return result


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def _time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be HH:MM or HH:MM:SS") from exc
    return parsed.replace(tzinfo=None)


if __name__ == "__main__":
    raise SystemExit(main())
