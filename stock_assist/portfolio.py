"""Portfolio file loading and validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_assist.paths import DATA_DIR

DEFAULT_PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
DEFAULT_MANUAL_PORTFOLIO_PATH = DATA_DIR / "portfolio.manual.tsv"
DEFAULT_GALAXY_PORTFOLIO_PATH = DATA_DIR / "portfolio.galaxy.tsv"
DEFAULT_PORTFOLIO_CONTEXT_PATH = DATA_DIR / "portfolio_context.json"


BROKER_HEADER_ALIASES = {
    "code": ("证券代码",),
    "name": ("证券名称",),
    "shares": ("当前持仓", "当前股份"),
    "shares_fallback": ("股票余额",),
    "available": ("股份可用", "自有股份可用"),
    "cost": ("成本价",),
    "market_price": ("市价",),
    "pnl": ("盈亏",),
    "pnl_pct": ("盈亏比例(%)",),
    "day_pnl": ("当日盈亏",),
    "day_pnl_pct": ("当日盈亏比(%)", "当日盈亏比例(%)"),
    "market_value": ("市值",),
    "weight_pct": ("仓位占比(%)",),
    "market": ("交易市场",),
}


@dataclass(frozen=True)
class AdjustmentRecord:
    date: str = ""
    action: str = ""
    reason: str = ""
    risk_line_after: str = ""


@dataclass(frozen=True)
class BetaEvidence:
    """Deterministic market-data evidence behind one beta classification."""

    beta: float | None = None
    r_squared: float | None = None
    benchmark: str = ""
    window_sessions: int = 0
    minimum_observations: int = 0
    observations: int = 0
    as_of: str = ""
    asset_as_of: str = ""
    source: str = ""
    quality_status: str = "unknown"
    fit_quality: str = "unknown"
    reason: str = ""
    calculation: str = ""


@dataclass(frozen=True)
class Holding:
    code: str
    name: str = ""
    shares: float | None = None
    cost: float | None = None
    market_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    market_value: float | None = None
    weight_pct: float | None = None
    available: float | None = None
    market: str = ""
    beta_classification: str = "unknown"
    beta_evidence: BetaEvidence | None = None
    thesis: str = ""
    risk_line: str = ""
    initial_risk_line: str = ""
    horizon: str = ""
    review_status: str = ""
    catalysts: tuple[str, ...] = ()
    falsification_signals: tuple[str, ...] = ()
    observation_window: str = ""
    next_review_date: str = ""
    adjustment_records: tuple[AdjustmentRecord, ...] = ()


@dataclass(frozen=True)
class Portfolio:
    cash: float | None
    holdings: list[Holding]
    source: Path
    missing: bool = False
    as_of: str = ""
    source_note: str = ""
    context_source: Path = DEFAULT_PORTFOLIO_CONTEXT_PATH
    context_missing: bool = False
    risk_reconciliation_status: str = "unverified"


def portfolio_version(portfolio: Portfolio) -> str:
    """Return a stable content version for refresh/report binding."""

    payload = {
        "cash": portfolio.cash,
        "as_of": portfolio.as_of,
        "missing": portfolio.missing,
        "risk_reconciliation_status": portfolio.risk_reconciliation_status,
        "holdings": [asdict(holding) for holding in portfolio.holdings],
    }
    digest = sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return f"portfolio-{digest[:16]}"


def load_portfolio(path: Path = DEFAULT_PORTFOLIO_PATH) -> Portfolio:
    """Load a JSON portfolio or Galaxy Securities copied position table.

    Missing portfolio data is represented explicitly so reports can lead with
    the data gap instead of inventing positions.
    """

    if path.exists():
        try:
            return _with_position_context(_load_json_portfolio(path))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return Portfolio(
                cash=None,
                holdings=[],
                source=path,
                missing=True,
                source_note=f"持仓JSON不可读取：{type(exc).__name__}",
                context_missing=True,
            )
    if DEFAULT_MANUAL_PORTFOLIO_PATH.exists():
        return _with_position_context(load_manual_broker_portfolio(DEFAULT_MANUAL_PORTFOLIO_PATH))
    if DEFAULT_GALAXY_PORTFOLIO_PATH.exists():
        return _with_position_context(load_galaxy_portfolio(DEFAULT_GALAXY_PORTFOLIO_PATH))
    return Portfolio(cash=None, holdings=[], source=path, missing=True, context_missing=True)


def _load_json_portfolio(path: Path) -> Portfolio:
    payload = json.loads(path.read_text(encoding="utf-8"))
    holdings = [
        Holding(
            code=str(item["code"]),
            name=str(item.get("name", "")),
            shares=_optional_float(item.get("shares")),
            cost=_optional_float(item.get("cost")),
            market_price=_optional_float(item.get("market_price")),
            pnl=_optional_float(item.get("pnl")),
            pnl_pct=_optional_float(item.get("pnl_pct")),
            day_pnl=_optional_float(item.get("day_pnl")),
            day_pnl_pct=_optional_float(item.get("day_pnl_pct")),
            market_value=_optional_float(item.get("market_value")),
            weight_pct=_optional_float(item.get("weight_pct")),
            available=_optional_float(item.get("available")),
            market=str(item.get("market", "")),
            beta_classification=str(item.get("beta_classification") or "unknown"),
            beta_evidence=_parse_beta_evidence(item.get("beta_evidence")),
            thesis=str(item.get("thesis", "")),
            risk_line=str(item.get("risk_line", "")),
            initial_risk_line=str(item.get("initial_risk_line", "")),
            horizon=str(item.get("horizon", "")),
            review_status=str(item.get("review_status", "")),
            catalysts=_parse_string_list(item.get("catalysts", [])),
            falsification_signals=_parse_string_list(item.get("falsification_signals", [])),
            observation_window=str(item.get("observation_window", "")),
            next_review_date=str(item.get("next_review_date", "")),
            adjustment_records=_parse_adjustment_records(item.get("adjustments", [])),
        )
        for item in payload.get("holdings", [])
    ]
    reconciliation = payload.get("risk_reconciliation") if isinstance(payload.get("risk_reconciliation"), dict) else {}
    return Portfolio(
        cash=_optional_float(payload.get("cash")),
        holdings=holdings,
        source=path,
        missing=False,
        as_of=str(payload.get("as_of", "")),
        source_note=str(payload.get("source_note", "")),
        risk_reconciliation_status=str(reconciliation.get("status") or "unverified"),
    )


def load_galaxy_portfolio(path: Path = DEFAULT_GALAXY_PORTFOLIO_PATH) -> Portfolio:
    """Load a Galaxy Securities copied position table."""

    rows = parse_galaxy_position_table(path.read_text(encoding="utf-8-sig"))
    holdings: list[Holding] = []
    raw_holdings: list[Holding] = []
    for row in rows:
        shares = _optional_float(row.get("当前持仓") or row.get("股票余额"))
        if not shares or shares <= 0:
            continue
        raw_holdings.append(
            Holding(
                code=_normalize_a_share_code(str(row.get("证券代码", "")), str(row.get("交易市场", ""))),
                name=str(row.get("证券名称", "")),
                shares=shares,
                cost=_optional_float(row.get("成本价")),
                market_price=_optional_float(row.get("市价")),
                pnl=_optional_float(row.get("盈亏")),
                pnl_pct=_optional_float(row.get("盈亏比例(%)")),
                day_pnl=_optional_float(row.get("当日盈亏")),
                day_pnl_pct=_optional_float(row.get("当日盈亏比(%)")),
                market_value=_optional_float(row.get("市值")),
                weight_pct=_optional_float(row.get("仓位占比(%)")),
                available=_optional_float(row.get("股份可用") or row.get("自有股份可用")),
                market=str(row.get("交易市场", "")),
                beta_classification="unknown",
                thesis="券商持仓导入，待补买入逻辑。",
                risk_line="按成本回撤、单日跌幅、仓位集中度和原始买入逻辑复核。",
                initial_risk_line="",
                horizon="position",
                review_status="needs_context",
                catalysts=(),
                falsification_signals=(),
                observation_window="",
                next_review_date="",
            )
        )
    holdings = _fill_missing_weights(raw_holdings)
    return Portfolio(cash=None, holdings=holdings, source=path, missing=False)


def load_manual_broker_portfolio(path: Path = DEFAULT_MANUAL_PORTFOLIO_PATH) -> Portfolio:
    """Load a manually pasted broker position table.

    Paste the broker table into data/portfolio.manual.tsv. The parser prefers
    当前持仓 because 股票余额 can stay non-zero after same-day sells or freezes.
    """

    rows = parse_galaxy_position_table(path.read_text(encoding="utf-8-sig"))
    raw_holdings: list[Holding] = []
    for row in rows:
        shares = _broker_float(row, "shares")
        if shares is None:
            shares = _broker_float(row, "shares_fallback")
        if not shares or shares <= 0:
            continue
        market_price = _broker_float(row, "market_price")
        market_value = _broker_float(row, "market_value")
        if (not market_value or market_value <= 0) and market_price is not None:
            market_value = shares * market_price
        raw_holdings.append(
            Holding(
                code=_normalize_a_share_code(_broker_text(row, "code"), _broker_text(row, "market")),
                name=_broker_text(row, "name"),
                shares=shares,
                cost=_broker_float(row, "cost"),
                market_price=market_price,
                pnl=_broker_float(row, "pnl"),
                pnl_pct=_broker_float(row, "pnl_pct"),
                day_pnl=_broker_float(row, "day_pnl"),
                day_pnl_pct=_broker_float(row, "day_pnl_pct"),
                market_value=market_value,
                weight_pct=_broker_float(row, "weight_pct"),
                available=_broker_float(row, "available"),
                market=_broker_text(row, "market"),
                beta_classification="unknown",
                thesis="券商持仓导入，待补买入逻辑。",
                risk_line="按成本回撤、单日跌幅、仓位集中度和原始买入逻辑复核。",
                initial_risk_line="",
                horizon="position",
                review_status="needs_context",
                catalysts=(),
                falsification_signals=(),
                observation_window="",
                next_review_date="",
            )
        )
    holdings = _fill_missing_weights(raw_holdings)
    return Portfolio(cash=None, holdings=holdings, source=path, missing=False)


def parse_galaxy_position_table(text: str) -> list[dict[str, str]]:
    lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header_index = next((index for index, line in enumerate(lines) if "证券代码" in line), 0)
    headers = [value.strip() for value in lines[header_index].split("\t")]
    rows: list[dict[str, str]] = []
    for line in lines[header_index + 1 :]:
        values = [value.strip() for value in line.split("\t")]
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        row = dict(zip(headers, values[: len(headers)]))
        if row.get("证券代码"):
            rows.append(row)
    return rows


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "").replace("%", ""))


def _with_position_context(
    portfolio: Portfolio,
    context_path: Path = DEFAULT_PORTFOLIO_CONTEXT_PATH,
) -> Portfolio:
    contexts = _load_position_contexts(context_path)
    if not contexts:
        return Portfolio(
            cash=portfolio.cash,
            holdings=portfolio.holdings,
            source=portfolio.source,
            missing=portfolio.missing,
            as_of=portfolio.as_of,
            source_note=portfolio.source_note,
            context_source=context_path,
            context_missing=True,
            risk_reconciliation_status=portfolio.risk_reconciliation_status,
        )
    return Portfolio(
        cash=portfolio.cash,
        holdings=[_merge_holding_context(holding, contexts.get(holding.code, {})) for holding in portfolio.holdings],
        source=portfolio.source,
        missing=portfolio.missing,
        as_of=portfolio.as_of,
        source_note=portfolio.source_note,
        context_source=context_path,
        context_missing=False,
        risk_reconciliation_status=portfolio.risk_reconciliation_status,
    )


def _load_position_contexts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_positions = payload.get("positions", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_positions, list):
        return {}
    contexts: dict[str, dict[str, Any]] = {}
    for item in raw_positions:
        if isinstance(item, dict) and item.get("code"):
            contexts[str(item["code"])] = item
    return contexts


def _merge_holding_context(holding: Holding, context: dict[str, Any]) -> Holding:
    if not context:
        return holding
    context_conflict = _context_conflicts_with_snapshot(holding, context)
    conflict_note = (
        "旧持仓上下文与最新券商盈亏状态冲突，已停用原风险叙事；"
        "请按当前技术结构和基本面证据重新确认。"
    )
    return Holding(
        code=holding.code,
        name=holding.name or str(context.get("name", "")),
        shares=holding.shares,
        cost=holding.cost,
        market_price=holding.market_price,
        pnl=holding.pnl,
        pnl_pct=holding.pnl_pct,
        day_pnl=holding.day_pnl,
        day_pnl_pct=holding.day_pnl_pct,
        market_value=holding.market_value,
        weight_pct=holding.weight_pct,
        available=holding.available,
        market=holding.market,
        beta_classification=holding.beta_classification,
        beta_evidence=holding.beta_evidence,
        thesis=str(context.get("buy_thesis") or context.get("thesis") or holding.thesis),
        risk_line=(
            conflict_note
            if context_conflict
            else str(context.get("current_risk_line") or context.get("risk_line") or holding.risk_line)
        ),
        initial_risk_line=(
            "旧风险线基于已失效的账户盈亏状态，待用户重建。"
            if context_conflict
            else str(context.get("initial_risk_line") or holding.initial_risk_line)
        ),
        horizon=str(context.get("horizon") or holding.horizon),
        review_status=(
            "stale_context"
            if context_conflict
            else str(context.get("review_status") or holding.review_status)
        ),
        catalysts=_parse_string_list(context.get("catalysts", holding.catalysts)),
        falsification_signals=_parse_string_list(
            context.get("falsification_signals", holding.falsification_signals)
        ),
        observation_window=(
            ""
            if context_conflict
            else str(context.get("observation_window") or holding.observation_window)
        ),
        next_review_date=(
            ""
            if context_conflict
            else str(context.get("next_review_date") or holding.next_review_date)
        ),
        adjustment_records=_parse_adjustment_records(context.get("adjustments", holding.adjustment_records)),
    )


def _context_conflicts_with_snapshot(
    holding: Holding,
    context: dict[str, Any],
) -> bool:
    """Reject account-state narratives contradicted by the latest broker row."""

    pnl_pct = holding.pnl_pct
    if pnl_pct is None:
        return False
    review_status = str(context.get("review_status") or "").lower()
    account_text = " ".join(
        str(context.get(key) or "")
        for key in (
            "initial_risk_line",
            "current_risk_line",
            "risk_line",
            "observation_window",
        )
    )
    profit_context = (
        review_status in {"profit_protect", "take_profit", "protect_profit"}
        or "浮盈" in account_text
        or "止盈" in account_text
        or "保护利润" in account_text
    )
    loss_context = (
        review_status in {"loss_review", "deep_drawdown"}
        or "深度回撤" in account_text
        or "亏损" in account_text
    )
    return (pnl_pct < 0 and profit_context) or (pnl_pct > 0 and loss_context)


def _parse_adjustment_records(value: Any) -> tuple[AdjustmentRecord, ...]:
    if not value:
        return ()
    if isinstance(value, tuple) and all(isinstance(item, AdjustmentRecord) for item in value):
        return value
    records: list[AdjustmentRecord] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        records.append(
            AdjustmentRecord(
                date=str(item.get("date", "")),
                action=str(item.get("action", "")),
                reason=str(item.get("reason", "")),
                risk_line_after=str(item.get("risk_line_after", "")),
            )
        )
    return tuple(records)


def _parse_beta_evidence(value: Any) -> BetaEvidence | None:
    if not isinstance(value, dict):
        return None
    return BetaEvidence(
        beta=_optional_float(value.get("beta")),
        r_squared=_optional_float(value.get("r_squared")),
        benchmark=str(value.get("benchmark") or ""),
        window_sessions=int(value.get("window_sessions") or 0),
        minimum_observations=int(value.get("minimum_observations") or 0),
        observations=int(value.get("observations") or 0),
        as_of=str(value.get("as_of") or ""),
        asset_as_of=str(value.get("asset_as_of") or ""),
        source=str(value.get("source") or ""),
        quality_status=str(value.get("quality_status") or "unknown"),
        fit_quality=str(value.get("fit_quality") or "unknown"),
        reason=str(value.get("reason") or ""),
        calculation=str(value.get("calculation") or ""),
    )


def _parse_string_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _normalize_a_share_code(code: str, market: str) -> str:
    clean = code.strip()
    if "." in clean:
        return clean
    if market.startswith("沪") or clean.startswith(("6", "9")):
        return f"{clean}.SH"
    if market.startswith("深") or clean.startswith(("0", "2", "3")):
        return f"{clean}.SZ"
    return clean


def _fill_missing_weights(holdings: list[Holding]) -> list[Holding]:
    total_market_value = sum(holding.market_value or 0 for holding in holdings)
    if total_market_value <= 0:
        return holdings
    if any((holding.weight_pct or 0) > 0 for holding in holdings):
        return holdings
    return [
        Holding(
            code=holding.code,
            name=holding.name,
            shares=holding.shares,
            cost=holding.cost,
            market_price=holding.market_price,
            pnl=holding.pnl,
            pnl_pct=holding.pnl_pct,
            day_pnl=holding.day_pnl,
            day_pnl_pct=holding.day_pnl_pct,
            market_value=holding.market_value,
            weight_pct=(holding.market_value or 0) / total_market_value * 100,
            available=holding.available,
            market=holding.market,
            beta_classification=holding.beta_classification,
            beta_evidence=holding.beta_evidence,
            thesis=holding.thesis,
            risk_line=holding.risk_line,
            initial_risk_line=holding.initial_risk_line,
            horizon=holding.horizon,
            review_status=holding.review_status,
            catalysts=holding.catalysts,
            falsification_signals=holding.falsification_signals,
            observation_window=holding.observation_window,
            next_review_date=holding.next_review_date,
            adjustment_records=holding.adjustment_records,
        )
        for holding in holdings
    ]


def parse_galaxy_position_table(text: str) -> list[dict[str, str]]:  # type: ignore[no-redef]  # noqa: F811
    """Parse a tab-separated broker position table with Chinese or legacy headers."""

    lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if any(alias in line for alias in BROKER_HEADER_ALIASES["code"])
        ),
        0,
    )
    headers = [value.strip() for value in lines[header_index].split("\t")]
    rows: list[dict[str, str]] = []
    for line in lines[header_index + 1 :]:
        values = [value.strip() for value in line.split("\t")]
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        row = dict(zip(headers, values[: len(headers)]))
        if _broker_text(row, "code"):
            rows.append(row)
    return rows


def _broker_value(row: dict[str, str], key: str) -> str:
    for header in BROKER_HEADER_ALIASES[key]:
        value = row.get(header)
        if value not in (None, ""):
            return value
    return ""


def _broker_text(row: dict[str, str], key: str) -> str:
    return str(_broker_value(row, key)).strip()


def _broker_float(row: dict[str, str], key: str) -> float | None:
    return _optional_float(_broker_value(row, key))


def _normalize_a_share_code(code: str, market: str) -> str:  # type: ignore[no-redef]
    clean = code.strip()
    if "." in clean:
        return clean
    if market.startswith("沪") or clean.startswith(("6", "9")):
        return f"{clean}.SH"
    if market.startswith("深") or clean.startswith(("0", "2", "3")):
        return f"{clean}.SZ"
    return clean
