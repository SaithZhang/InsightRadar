"""Deterministic portfolio beta estimation and evidence persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite, sqrt
from pathlib import Path
from typing import Callable, Iterable, Sequence

from stock_assist.data_sources.a_share_klines import fetch_public_klines
from stock_assist.data_sources.eastmoney_klines import Candle
from stock_assist.paths import CONFIG_DIR
from stock_assist.portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    load_portfolio,
    portfolio_version,
)
from stock_assist.portfolio_import import (
    DEFAULT_RISK_PROFILE_PATH,
    apply_portfolio_beta_evidence,
)
from stock_assist.report_payload import create_report_payload
from stock_assist.reports import markdown_report_to_html

DEFAULT_CONFIG_PATH = CONFIG_DIR / "portfolio_beta.json"
CALCULATION = "beta=cov(asset_simple_daily_return,benchmark_simple_daily_return)/var(benchmark_simple_daily_return)"
KlineFetcher = Callable[..., tuple[list[Candle], str]]


@dataclass(frozen=True)
class PricePoint:
    session: date
    close: float


@dataclass(frozen=True)
class BetaConfig:
    benchmark: str
    benchmark_name: str
    benchmark_secid: str
    benchmark_tencent_code: str
    window_sessions: int
    minimum_observations: int
    history_limit: int
    high_beta_threshold: float
    require_same_latest_session: bool
    moderate_r_squared: float
    strong_r_squared: float


@dataclass(frozen=True)
class BetaResult:
    code: str
    classification: str
    beta: float | None
    r_squared: float | None
    benchmark: str
    window_sessions: int
    minimum_observations: int
    observations: int
    as_of: str
    asset_as_of: str
    source: str
    quality_status: str
    fit_quality: str
    reason: str
    calculation: str = CALCULATION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def calculate_beta(
    code: str,
    asset_prices: Sequence[PricePoint],
    benchmark_prices: Sequence[PricePoint],
    config: BetaConfig,
    *,
    source: str,
) -> BetaResult:
    """Calculate one beta from aligned returns; every invalid state fails closed."""

    asset = _normalized_prices(asset_prices)
    benchmark = _normalized_prices(benchmark_prices)
    if len(benchmark) < config.minimum_observations + 1:
        return _unavailable_result(
            code,
            config,
            quality_status="insufficient",
            source=source,
            observations=max(0, len(benchmark) - 1),
            reason="基准有效历史不足以满足最小样本数。",
        )
    if len(asset) < 2:
        return _unavailable_result(
            code,
            config,
            quality_status="insufficient",
            source=source,
            observations=0,
            reason="标的有效日收盘价不足。",
            as_of=benchmark[-1].session.isoformat(),
            asset_as_of=asset[-1].session.isoformat() if asset else "",
        )

    benchmark_window = benchmark[-(config.window_sessions + 1) :]
    benchmark_as_of = benchmark_window[-1].session
    asset_as_of = asset[-1].session
    if config.require_same_latest_session and asset_as_of != benchmark_as_of:
        return _unavailable_result(
            code,
            config,
            quality_status="stale",
            source=source,
            observations=0,
            reason="标的与基准的最新交易日不一致。",
            as_of=benchmark_as_of.isoformat(),
            asset_as_of=asset_as_of.isoformat(),
        )

    asset_by_session = {item.session: item.close for item in asset}
    aligned_asset: list[float | None] = []
    latest_asset_close: float | None = None
    for item in benchmark_window:
        if item.session in asset_by_session:
            latest_asset_close = asset_by_session[item.session]
        aligned_asset.append(latest_asset_close)

    asset_returns: list[float] = []
    benchmark_returns: list[float] = []
    for index in range(1, len(benchmark_window)):
        previous_asset = aligned_asset[index - 1]
        current_asset = aligned_asset[index]
        previous_benchmark = benchmark_window[index - 1].close
        current_benchmark = benchmark_window[index].close
        if previous_asset is None or current_asset is None:
            continue
        if previous_asset <= 0 or previous_benchmark <= 0:
            continue
        asset_return = current_asset / previous_asset - 1.0
        benchmark_return = current_benchmark / previous_benchmark - 1.0
        if not (isfinite(asset_return) and isfinite(benchmark_return)):
            continue
        asset_returns.append(asset_return)
        benchmark_returns.append(benchmark_return)

    observations = len(asset_returns)
    if observations < config.minimum_observations:
        return _unavailable_result(
            code,
            config,
            quality_status="insufficient",
            source=source,
            observations=observations,
            reason="标的与基准的有效重叠收益率样本不足。",
            as_of=benchmark_as_of.isoformat(),
            asset_as_of=asset_as_of.isoformat(),
        )

    benchmark_mean = sum(benchmark_returns) / observations
    asset_mean = sum(asset_returns) / observations
    benchmark_sum_squares = sum(
        (value - benchmark_mean) ** 2 for value in benchmark_returns
    )
    asset_sum_squares = sum((value - asset_mean) ** 2 for value in asset_returns)
    if benchmark_sum_squares <= 0 or not isfinite(benchmark_sum_squares):
        return _unavailable_result(
            code,
            config,
            quality_status="failed",
            source=source,
            observations=observations,
            reason="基准收益率方差为零或无效，无法计算beta。",
            as_of=benchmark_as_of.isoformat(),
            asset_as_of=asset_as_of.isoformat(),
        )
    covariance_sum = sum(
        (asset_value - asset_mean) * (benchmark_value - benchmark_mean)
        for asset_value, benchmark_value in zip(
            asset_returns,
            benchmark_returns,
            strict=True,
        )
    )
    beta = covariance_sum / benchmark_sum_squares
    if not isfinite(beta):
        return _unavailable_result(
            code,
            config,
            quality_status="failed",
            source=source,
            observations=observations,
            reason="beta计算结果不是有限数值。",
            as_of=benchmark_as_of.isoformat(),
            asset_as_of=asset_as_of.isoformat(),
        )
    r_squared = (
        (covariance_sum / sqrt(asset_sum_squares * benchmark_sum_squares)) ** 2
        if asset_sum_squares > 0
        else 0.0
    )
    r_squared = max(0.0, min(1.0, r_squared))
    classification = (
        "high_beta"
        if beta + 1e-12 >= config.high_beta_threshold
        else "normal"
    )
    return BetaResult(
        code=code,
        classification=classification,
        beta=round(beta, 6),
        r_squared=round(r_squared, 6),
        benchmark=config.benchmark,
        window_sessions=config.window_sessions,
        minimum_observations=config.minimum_observations,
        observations=observations,
        as_of=benchmark_as_of.isoformat(),
        asset_as_of=asset_as_of.isoformat(),
        source=source,
        quality_status="ready",
        fit_quality=_fit_quality(r_squared, config),
        reason=(
            f"beta {'达到' if classification == 'high_beta' else '低于'} "
            f"{config.high_beta_threshold:.2f}分类阈值。"
        ),
    )


def build_portfolio_beta_bundle(
    config_path: Path | None = None,
    *,
    portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
    risk_profile_path: Path = DEFAULT_RISK_PROFILE_PATH,
    fetcher: KlineFetcher = fetch_public_klines,
) -> tuple[dict[str, object], str, str]:
    """Fetch public daily bars, calculate beta, and persist evidence atomically."""

    actual_config = config_path or DEFAULT_CONFIG_PATH
    config = _load_config(actual_config)
    portfolio = load_portfolio(portfolio_path)
    version_before = portfolio_version(portfolio)
    results: list[BetaResult] = []
    benchmark_prices: list[PricePoint] = []
    benchmark_source = ""
    benchmark_error = ""
    try:
        benchmark_bars, benchmark_source = fetcher(
            secid=config.benchmark_secid,
            tencent_code=config.benchmark_tencent_code,
            interval="day",
            limit=config.history_limit,
        )
        benchmark_prices = _price_points(benchmark_bars)
    except Exception as exc:
        benchmark_error = f"基准日线不可用（{type(exc).__name__}）。"

    for holding in portfolio.holdings:
        if benchmark_error:
            results.append(
                _unavailable_result(
                    holding.code,
                    config,
                    quality_status="failed",
                    source=benchmark_source,
                    observations=0,
                    reason=benchmark_error,
                )
            )
            continue
        try:
            secid, tencent_code = _public_identifiers(holding.code)
            asset_bars, asset_source = fetcher(
                secid=secid,
                tencent_code=tencent_code,
                interval="day",
                limit=config.history_limit,
            )
            source = _combined_source(asset_source, benchmark_source)
            results.append(
                calculate_beta(
                    holding.code,
                    _price_points(asset_bars),
                    benchmark_prices,
                    config,
                    source=source,
                )
            )
        except Exception as exc:
            results.append(
                _unavailable_result(
                    holding.code,
                    config,
                    quality_status="failed",
                    source=benchmark_source,
                    observations=0,
                    reason=f"标的日线不可用（{type(exc).__name__}）。",
                    as_of=(
                        benchmark_prices[-1].session.isoformat()
                        if benchmark_prices
                        else ""
                    ),
                )
            )

    model = _model_payload(config)
    reconciliation: dict[str, object] = {
        "status": "blocked",
        "reason": "持仓文件不可读取，未写入beta证据。",
    }
    version_after = version_before
    if not portfolio.missing:
        write_result = apply_portfolio_beta_evidence(
            [item.to_dict() for item in results],
            model=model,
            portfolio_path=portfolio_path,
            risk_profile_path=risk_profile_path,
        )
        raw_reconciliation = write_result.get("risk_reconciliation")
        if isinstance(raw_reconciliation, dict):
            reconciliation = raw_reconciliation
        version_after = portfolio_version(load_portfolio(portfolio_path))

    ready_count = sum(item.quality_status == "ready" for item in results)
    data_gaps = [
        f"{item.code}：{item.reason}"
        for item in results
        if item.quality_status != "ready"
    ]
    if portfolio.missing:
        data_gaps.append("持仓文件缺失或不可读取。")
    payload = create_report_payload(
        kind="portfolio_beta",
        workflow="portfolio-beta",
        title="组合Beta自动计算",
        config=str(actual_config),
        model=model,
        portfolio_version_before=version_before,
        portfolio_version_after=version_after,
        status=("ready" if ready_count == len(results) and results else "blocked"),
        coverage={
            "ready": ready_count,
            "total": len(results),
            "ratio": ready_count / len(results) if results else 0.0,
        },
        risk_reconciliation=reconciliation,
        results=[item.to_dict() for item in results],
        data_gaps=data_gaps,
        authority="deterministic_classification_only_no_trade_authority",
        disclaimer="beta只用于组合风险分类；低拟合度、样本不足、过期或异常数据不会生成交易动作。",
    )
    markdown = _render_markdown(payload)
    return payload, markdown, markdown_report_to_html(markdown)


def _load_config(path: Path) -> BetaConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("portfolio beta配置必须是JSON object。")
    benchmark = raw.get("benchmark")
    if not isinstance(benchmark, dict):
        raise ValueError("portfolio beta配置缺少benchmark。")
    thresholds = raw.get("fit_quality_thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
    config = BetaConfig(
        benchmark=str(benchmark.get("code") or "000300.SH"),
        benchmark_name=str(benchmark.get("name") or "沪深300"),
        benchmark_secid=str(benchmark.get("secid") or "1.000300"),
        benchmark_tencent_code=str(
            benchmark.get("tencent_code") or "sh000300"
        ),
        window_sessions=int(raw.get("window_sessions") or 120),
        minimum_observations=int(raw.get("minimum_observations") or 60),
        history_limit=int(raw.get("history_limit") or 180),
        high_beta_threshold=float(raw.get("high_beta_threshold") or 1.2),
        require_same_latest_session=bool(
            raw.get("require_same_latest_session", True)
        ),
        moderate_r_squared=float(thresholds.get("moderate_r_squared") or 0.1),
        strong_r_squared=float(thresholds.get("strong_r_squared") or 0.3),
    )
    if config.window_sessions < config.minimum_observations:
        raise ValueError("window_sessions不能小于minimum_observations。")
    if config.minimum_observations < 2:
        raise ValueError("minimum_observations至少为2。")
    if config.history_limit < config.window_sessions + 1:
        raise ValueError("history_limit必须覆盖window_sessions加一个收盘价。")
    if not 0 <= config.moderate_r_squared <= config.strong_r_squared <= 1:
        raise ValueError("R²质量阈值必须满足0 <= moderate <= strong <= 1。")
    return config


def _normalized_prices(values: Iterable[PricePoint]) -> list[PricePoint]:
    by_session = {
        item.session: float(item.close)
        for item in values
        if item.close > 0 and isfinite(float(item.close))
    }
    return [
        PricePoint(session=session, close=by_session[session])
        for session in sorted(by_session)
    ]


def _price_points(values: Iterable[Candle]) -> list[PricePoint]:
    return [
        PricePoint(session=item.time.date(), close=float(item.close))
        for item in values
        if item.close > 0 and isfinite(float(item.close))
    ]


def _public_identifiers(code: str) -> tuple[str, str]:
    normalized = code.strip().upper()
    if normalized.endswith(".SH"):
        bare = normalized.removesuffix(".SH")
        return f"1.{bare}", f"sh{bare}"
    if normalized.endswith(".SZ"):
        bare = normalized.removesuffix(".SZ")
        return f"0.{bare}", f"sz{bare}"
    raise ValueError("只支持带.SH或.SZ后缀的A股代码。")


def _combined_source(asset_source: str, benchmark_source: str) -> str:
    sources = [value for value in (asset_source, benchmark_source) if value]
    return " + ".join(dict.fromkeys(sources))


def _fit_quality(r_squared: float, config: BetaConfig) -> str:
    if r_squared >= config.strong_r_squared:
        return "strong"
    if r_squared >= config.moderate_r_squared:
        return "moderate"
    return "weak"


def _unavailable_result(
    code: str,
    config: BetaConfig,
    *,
    quality_status: str,
    source: str,
    observations: int,
    reason: str,
    as_of: str = "",
    asset_as_of: str = "",
) -> BetaResult:
    return BetaResult(
        code=code,
        classification="unknown",
        beta=None,
        r_squared=None,
        benchmark=config.benchmark,
        window_sessions=config.window_sessions,
        minimum_observations=config.minimum_observations,
        observations=observations,
        as_of=as_of,
        asset_as_of=asset_as_of,
        source=source,
        quality_status=quality_status,
        fit_quality="unknown",
        reason=reason,
    )


def _model_payload(config: BetaConfig) -> dict[str, object]:
    return {
        "benchmark": config.benchmark,
        "benchmark_name": config.benchmark_name,
        "window_sessions": config.window_sessions,
        "minimum_observations": config.minimum_observations,
        "history_limit": config.history_limit,
        "high_beta_threshold": config.high_beta_threshold,
        "return_method": "simple_daily_return",
        "price_adjustment": "qfq_for_holdings_provider_native_for_index",
        "require_same_latest_session": config.require_same_latest_session,
        "calculation": CALCULATION,
    }


def _render_markdown(payload: dict[str, object]) -> str:
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
    reconciliation = payload.get("risk_reconciliation")
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    lines = [
        "# 组合Beta自动计算",
        "",
        "## 结论",
        "",
        f"- 计算状态：{payload.get('status') or 'blocked'}。",
        f"- 有效覆盖：{coverage.get('ready', 0)}/{coverage.get('total', 0)}。",
        f"- 风险对账：{reconciliation.get('status') or 'blocked'}；{reconciliation.get('reason') or '原因未知'}",
        "- 计算完全由结构化日线和代码规则完成，不调用AI，也不生成交易动作。",
        "",
        "## 持仓证据",
        "",
        "| 代码 | 分类 | Beta | R² | 样本 | 截止 | 数据质量 | 拟合质量 |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    results = payload.get("results")
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        beta = item.get("beta")
        r_squared = item.get("r_squared")
        lines.append(
            "| {code} | {classification} | {beta} | {r_squared} | {observations} | {as_of} | {quality} | {fit} |".format(
                code=item.get("code") or "",
                classification=item.get("classification") or "unknown",
                beta=f"{float(beta):.3f}" if isinstance(beta, (int, float)) else "unknown",
                r_squared=(
                    f"{float(r_squared):.3f}"
                    if isinstance(r_squared, (int, float))
                    else "unknown"
                ),
                observations=item.get("observations") or 0,
                as_of=item.get("as_of") or "unknown",
                quality=item.get("quality_status") or "unknown",
                fit=item.get("fit_quality") or "unknown",
            )
        )
    gaps = payload.get("data_gaps")
    if isinstance(gaps, list) and gaps:
        lines.extend(["", "## 数据缺口", ""])
        lines.extend(f"- {item}" for item in gaps)
    lines.extend(["", f"> {payload.get('disclaimer') or ''}", ""])
    return "\n".join(lines)
