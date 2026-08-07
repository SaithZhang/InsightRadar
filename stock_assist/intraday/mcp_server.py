"""Read-only MCP adapter for InsightRadar intraday evidence."""

from __future__ import annotations

import argparse
from datetime import date as date_type
from datetime import time as time_type
from typing import Annotated, Generic, Literal, TypeVar

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from stock_assist.intraday.evidence import (
    MAX_COMPARE_SYMBOLS,
    MAX_REVIEW_TRADES,
    IntradayEvidenceService,
    default_service,
    evidence_to_dict,
)
from stock_assist.intraday.evidence_cli import parse_trade_rows

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
EvidenceStatus = Literal["ok", "degraded", "stale", "blocked", "no_data"]
ResponseDataT = TypeVar("ResponseDataT")
ResponseT = TypeVar("ResponseT", bound=BaseModel)


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceStampOutput(OutputModel):
    provider: str
    source: str
    symbol: str | None
    provider_status: str
    source_time: str | None
    fetched_at: str
    trade_date: str | None
    gaps: list[str]
    errors: list[str]


class SourceConflictOutput(OutputModel):
    primary_provider: str
    fallback_provider: str
    field: str
    primary_value: JsonValue
    fallback_value: JsonValue
    tolerance: float | None


class EvidenceOutput(OutputModel, Generic[ResponseDataT]):
    schema_version: str
    status: EvidenceStatus
    reason: str | None
    source_time: str | None
    fetched_at: str
    stale_seconds: float | None
    data: ResponseDataT | None
    provenance: list[SourceStampOutput]
    gaps: list[str]
    conflicts: list[SourceConflictOutput]
    analysis_authority: Literal["read_only_evidence"]
    trade_authority: Literal["none"]


class IntradayMinuteOutput(OutputModel):
    time: str
    price: float
    avg_price: float | None
    volume: float | None
    amount: float | None


class IntradayDataOutput(OutputModel):
    symbol: str
    qualified_symbol: str
    name: str | None
    market: str
    trade_date: str
    source: str
    pre_close: float | None
    open: float | None
    last: float | None
    high: float | None
    low: float | None
    day_pct: float | None
    vwap: float | None
    return_5m: float | None
    return_15m: float | None
    return_30m: float | None
    distance_to_vwap_pct: float | None
    distance_to_high_pct: float | None
    volume_acceleration: float | None
    minutes: list[IntradayMinuteOutput]
    amount_unit: Literal["CNY", "unknown"]
    volume_unit: Literal["share", "lot", "unknown"]


class IntradayCompareRowOutput(OutputModel):
    symbol: str
    qualified_symbol: str
    name: str | None
    time: str | None
    return_from_open: float | None
    return_5m: float | None
    return_15m: float | None
    distance_to_vwap_pct: float | None
    distance_to_high_pct: float | None
    volume_acceleration: float | None
    relative_strength_vs_benchmark: float | None
    rank: int | None
    status: EvidenceStatus
    reason: str | None


class IntradayCompareDataOutput(OutputModel):
    trade_date: str
    requested_time: str | None
    benchmark: str
    rows: list[IntradayCompareRowOutput]


class MarketAmountDataOutput(OutputModel):
    market: str
    trade_date: str
    previous_trade_date: str
    time: str
    today_amount: float
    previous_day_same_time_amount: float
    delta: float
    delta_pct: float | None


class TradeOutput(OutputModel):
    trade_date: str
    time: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float


class DecisionContextOutput(OutputModel):
    evidence_time: str | None
    trade_price: float
    vwap: float | None
    distance_to_vwap_pct: float | None
    day_high: float | None
    day_low: float | None
    distance_to_high_pct: float | None
    distance_to_low_pct: float | None
    range_position_pct: float | None
    return_before_5m: float | None
    return_before_15m: float | None
    relative_strength_vs_benchmark: float | None
    current_minute_volume: float | None
    average_volume_previous_5m: float | None
    volume_acceleration: float | None
    above_vwap: bool | None
    near_day_high: bool | None
    volume_confirmation: bool | None
    trend: Literal["strong", "weak", "mixed", "unknown"]


class TradeOutcomeOutput(OutputModel):
    return_after_5m: float | None
    return_after_15m: float | None
    return_after_30m: float | None
    mae_5m: float | None
    mae_15m: float | None
    mae_30m: float | None
    mfe_5m: float | None
    mfe_15m: float | None
    mfe_30m: float | None
    max_continue_up_5m: float | None
    max_continue_up_15m: float | None
    max_continue_up_30m: float | None
    max_down_5m: float | None
    max_down_15m: float | None
    max_down_30m: float | None
    pending_horizons: list[int]


class TradeReviewItemOutput(OutputModel):
    trade: TradeOutput
    benchmark: str
    status: EvidenceStatus
    reason: str | None
    decision_context: DecisionContextOutput | None
    outcome: TradeOutcomeOutput | None
    provenance: list[SourceStampOutput]
    gaps: list[str]


class TradeReviewDataOutput(OutputModel):
    trades: list[TradeReviewItemOutput]
    summary: dict[str, JsonValue]


class TradeRequest(BaseModel):
    trade_date: str = Field(description="A-share trade date in YYYY-MM-DD format.")
    time: str = Field(description="Execution time in HH:MM or HH:MM:SS format.")
    symbol: str = Field(description="Six-digit A-share/ETF symbol; suffix is allowed.")
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, allow_inf_nan=False)
    price: float = Field(gt=0, allow_inf_nan=False)


def create_server(service: IntradayEvidenceService | None = None) -> MCPServer:
    evidence = service or default_service()
    server = MCPServer(
        "InsightRadar Intraday Evidence",
        version="1.0.0",
        instructions=(
            "Read-only market evidence and trade review. Tape first, narrative second. "
            "Every response carries freshness, provenance, gaps, analysis_authority, and "
            "trade_authority=none. Never treat risk signals as automatic trade instructions."
        ),
    )

    @server.tool(title="Get intraday tape", annotations=READ_ONLY)
    def get_intraday(
        symbol: str,
        date: str,
        time: str | None = None,
    ) -> EvidenceOutput[IntradayDataOutput]:
        """Get normalized A-share/ETF/index minutes, VWAP, trend, volume, and provenance."""

        result = evidence.get_intraday(symbol, _date(date), as_of=_time(time))
        return _payload(result, EvidenceOutput[IntradayDataOutput])

    @server.tool(title="Compare intraday strength", annotations=READ_ONLY)
    def get_intraday_compare(
        symbols: Annotated[list[str], Field(min_length=1, max_length=MAX_COMPARE_SYMBOLS)],
        benchmark: str,
        date: str,
        time: str | None = None,
    ) -> EvidenceOutput[IntradayCompareDataOutput]:
        """Rank transparent intraday strength versus one supported benchmark."""

        result = evidence.get_intraday_compare(
            symbols,
            benchmark=benchmark,
            trade_date=_date(date),
            as_of=_time(time),
        )
        return _payload(result, EvidenceOutput[IntradayCompareDataOutput])

    @server.tool(title="Compare same-time A-share amount", annotations=READ_ONLY)
    def get_market_amount_compare(
        date: str,
        time: str | None = None,
    ) -> EvidenceOutput[MarketAmountDataOutput]:
        """Compare today's cumulative Shanghai+Shenzhen amount with the prior session."""

        result = evidence.get_market_amount_compare(_date(date), as_of=_time(time))
        return _payload(result, EvidenceOutput[MarketAmountDataOutput])

    @server.tool(title="Review user-confirmed trades", annotations=READ_ONLY)
    def review_trades(
        trades: Annotated[list[TradeRequest], Field(min_length=1, max_length=MAX_REVIEW_TRADES)],
        benchmark: str,
    ) -> EvidenceOutput[TradeReviewDataOutput]:
        """Return decision context and later outcomes without assigning buy/sell advice."""

        rows = [item.model_dump() for item in trades]
        parsed = parse_trade_rows(rows)
        result = evidence.review_trades(parsed, benchmark=benchmark)
        return _payload(result, EvidenceOutput[TradeReviewDataOutput])

    return server


mcp = create_server()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InsightRadar read-only intraday MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--endpoint", default="/mcp")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("first-party local server is loopback-only; deploy separately for remote access")
    if not args.endpoint.startswith("/"):
        parser.error("--endpoint must begin with /")
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=args.port,
            streamable_http_path=args.endpoint,
            stateless_http=True,
            json_response=True,
        )
    return 0


def _date(value: str) -> date_type:
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _time(value: str | None) -> time_type | None:
    if value is None:
        return None
    try:
        parsed = time_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("time must be HH:MM or HH:MM:SS") from exc
    return parsed.replace(tzinfo=None)


def _payload(value: object, response_type: type[ResponseT]) -> ResponseT:
    payload = evidence_to_dict(value)
    if not isinstance(payload, dict):
        raise TypeError("intraday evidence result must serialize to an object")
    return response_type.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(main())
