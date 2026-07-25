"""Leakage-aware local cross-sectional factor research for A-shares."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.universe import UniverseSpec, apply_universe, resolve_universe


FACTOR_COLUMNS = (
    "momentum_20_5",
    "reversal_5",
    "trend_60",
    "low_vol_20",
    "downside_20",
    "liquidity_20",
    "amihud_20",
    "volume_surprise",
)


@dataclass(frozen=True)
class FactorLabConfig:
    universe_name: str
    universe_type: str
    codes: tuple[str, ...]
    benchmark: str = "000852.SH"
    begin_date: int = 20250101
    end_date: int | None = None
    horizon_days: int = 5
    rebalance_days: int = 5
    min_train_days: int = 100
    train_window_days: int = 252
    ridge_alpha: float = 10.0
    top_n: int = 5
    transaction_cost_bps: float = 10.0
    csv_path: str | None = None
    universe_mode: str = "static_codes"
    universe_id: str = "custom_pilot_v1"
    membership_path: str | None = None

    @classmethod
    def load(cls, path: Path) -> "FactorLabConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            universe_name=str(data["universe_name"]),
            universe_type=str(data.get("universe_type", "explicit_custom")),
            codes=tuple(str(code) for code in data.get("codes", [])),
            benchmark=str(data.get("benchmark", "000852.SH")),
            begin_date=int(data.get("begin_date", 20250101)),
            end_date=int(data["end_date"]) if data.get("end_date") else None,
            horizon_days=int(data.get("horizon_days", 5)),
            rebalance_days=int(data.get("rebalance_days", 5)),
            min_train_days=int(data.get("min_train_days", 100)),
            train_window_days=int(data.get("train_window_days", 252)),
            ridge_alpha=float(data.get("ridge_alpha", 10.0)),
            top_n=int(data.get("top_n", 5)),
            transaction_cost_bps=float(data.get("transaction_cost_bps", 10.0)),
            csv_path=str(data["csv_path"]) if data.get("csv_path") else None,
            universe_mode=str(data.get("universe_mode", "static_codes")),
            universe_id=str(data.get("universe_id", "custom_pilot_v1")),
            membership_path=str(data["membership_path"]) if data.get("membership_path") else None,
        )


def load_price_history(config: FactorLabConfig, universe: UniverseSpec | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Load long-form OHLCV history from CSV or the repository AmazingData adapter."""

    gaps: list[str] = []
    if config.csv_path:
        frame = pd.read_csv(config.csv_path)
        source = "local_csv"
    else:
        end_date = config.end_date or int(date.today().strftime("%Y%m%d"))
        universe = universe or resolve_universe(config)
        client = AmazingDataClient()
        try:
            raw = client.query_daily_kline([*universe.codes_union, config.benchmark], config.begin_date, end_date)
        finally:
            client.logout()
        frames = [value.copy() for value in raw.values() if isinstance(value, pd.DataFrame) and not value.empty]
        if not frames:
            raise RuntimeError("AmazingData returned no daily K-line rows for the configured universe.")
        frame = pd.concat(frames, ignore_index=True)
        source = "amazingdata"

    required = {"code", "kline_time", "close", "volume", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Price history is missing columns: {', '.join(missing)}")
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["kline_time"], errors="coerce")
    for column in ("close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"])
    frame = frame[frame["close"] > 0].drop_duplicates(["code", "date"], keep="last")
    now = datetime.now()
    if now.time() < time(15, 10) and (frame["date"].dt.date == now.date()).any():
        frame = frame[frame["date"].dt.date < now.date()]
        gaps.append("当日日K尚未收盘，已剔除未完成K线。")
    universe = universe or resolve_universe(config)
    expected = set(universe.codes_union) | {config.benchmark}
    absent = sorted(expected - set(frame["code"].astype(str)))
    if absent:
        gaps.append("以下标的无历史行情：" + "、".join(absent))
    frame.attrs["source"] = source
    return frame, gaps


def build_factor_panel(
    prices: pd.DataFrame,
    benchmark: str,
    horizon_days: int,
    universe: UniverseSpec | None = None,
) -> pd.DataFrame:
    """Create point-in-time factors and a future benchmark-relative label."""

    rows: list[pd.DataFrame] = []
    for code, group in prices.groupby("code", sort=False):
        item = group.sort_values("date").copy()
        close = item["close"].astype(float)
        raw_return = close.pct_change(fill_method=None)
        daily_return = raw_return.where(raw_return.abs() <= 0.30)
        amount = item["amount"].astype(float).where(item["amount"].astype(float) > 0)
        volume = item["volume"].astype(float).where(item["volume"].astype(float) > 0)

        item["momentum_20_5"] = close.shift(5) / close.shift(20) - 1.0
        item["reversal_5"] = -(close / close.shift(5) - 1.0)
        item["trend_60"] = close / close.rolling(60, min_periods=45).mean() - 1.0
        item["low_vol_20"] = -daily_return.rolling(20, min_periods=15).std()
        downside = daily_return.clip(upper=0).pow(2).rolling(20, min_periods=15).mean()
        item["downside_20"] = -np.sqrt(downside)
        item["liquidity_20"] = np.log1p(amount.rolling(20, min_periods=15).mean())
        item["amihud_20"] = -(daily_return.abs() / amount * 1e8).rolling(20, min_periods=15).mean()
        item["volume_surprise"] = np.log(volume / volume.rolling(20, min_periods=15).mean())
        item["forward_return"] = close.shift(-horizon_days) / close - 1.0
        rows.append(item)

    panel = pd.concat(rows, ignore_index=True)
    benchmark_rows = panel.loc[panel["code"] == benchmark, ["date", "forward_return"]].rename(
        columns={"forward_return": "benchmark_forward_return"}
    )
    panel = panel.loc[panel["code"] != benchmark].merge(benchmark_rows, on="date", how="left")
    panel["label"] = panel["forward_return"] - panel["benchmark_forward_return"]
    if universe is not None:
        panel = apply_universe(panel, universe)
    else:
        panel["universe_id"] = "legacy_static"
        panel["universe_manifest_hash"] = ""
    panel = cross_sectional_preprocess(panel)
    return panel.sort_values(["date", "code"]).reset_index(drop=True)


def cross_sectional_preprocess(panel: pd.DataFrame) -> pd.DataFrame:
    """MAD winsorize and rank-standardize every factor independently by date."""

    result = panel.copy()
    for factor in FACTOR_COLUMNS:
        result[factor] = result.groupby("date", group_keys=False)[factor].transform(_robust_rank_score)
    result["label_train"] = result.groupby("date", group_keys=False)["label"].transform(_mad_winsorize)
    return result


def _mad_winsorize(series: pd.Series, scale: float = 5.0) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    median = values.median()
    mad = (values - median).abs().median()
    if pd.isna(median) or pd.isna(mad) or mad <= 1e-12:
        return values
    width = 1.4826 * mad * scale
    return values.clip(median - width, median + width)


def _robust_rank_score(series: pd.Series) -> pd.Series:
    values = _mad_winsorize(series)
    valid = values.notna()
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if valid.sum() < 4:
        return result
    ranks = values.loc[valid].rank(method="average", pct=True)
    result.loc[valid] = (ranks - 0.5) * math.sqrt(12.0)
    return result


def fit_ridge(
    train: pd.DataFrame,
    alpha: float,
    feature_names: tuple[str, ...] = FACTOR_COLUMNS,
) -> tuple[np.ndarray, float, float, dict[str, float]]:
    """Fit an interpretable ridge model without an external ML dependency."""

    clean = train.dropna(subset=[*feature_names, "label_train"])
    if clean.empty:
        raise ValueError("No complete training rows are available.")
    x = clean.loc[:, feature_names].to_numpy(dtype=float)
    y = clean["label_train"].to_numpy(dtype=float)
    x_mean = x.mean(axis=0)
    y_mean = float(y.mean())
    centered = x - x_mean
    matrix = centered.T @ centered + np.eye(centered.shape[1]) * alpha
    weights = np.linalg.solve(matrix, centered.T @ (y - y_mean))
    intercept = y_mean - float(x_mean @ weights)
    condition = float(np.linalg.cond((centered.T @ centered) / max(1, len(centered))))
    standard_deviation = centered.std(axis=0)
    nonconstant = standard_deviation > 1e-12
    vif = {factor: math.inf for factor in feature_names}
    if nonconstant.any():
        correlation = np.corrcoef(centered[:, nonconstant], rowvar=False)
        correlation = np.atleast_2d(correlation)
        inverse = np.linalg.pinv(correlation)
        original_indices = np.flatnonzero(nonconstant)
        for local_index, original_index in enumerate(original_indices):
            vif[feature_names[original_index]] = float(max(1.0, inverse[local_index, local_index]))
    return weights, intercept, condition, vif


def run_walk_forward(panel: pd.DataFrame, config: FactorLabConfig) -> dict[str, Any]:
    """Evaluate non-overlapping forecasts, keeping a horizon-sized embargo."""

    dated = panel.dropna(subset=[*FACTOR_COLUMNS]).copy()
    all_dates = list(pd.Index(dated["date"].drop_duplicates()).sort_values())
    label_dates = set(dated.loc[dated["label"].notna(), "date"])
    evaluations: list[dict[str, Any]] = []
    previous_selection: set[str] = set()
    latest_fit: tuple[np.ndarray, float, float, dict[str, float]] | None = None

    for position in range(config.min_train_days + config.horizon_days, len(all_dates), config.rebalance_days):
        forecast_date = all_dates[position]
        if forecast_date not in label_dates:
            continue
        cutoff_position = position - config.horizon_days
        start_position = max(0, cutoff_position - config.train_window_days)
        train_dates = set(all_dates[start_position:cutoff_position])
        train = dated[dated["date"].isin(train_dates)]
        if train["date"].nunique() < config.min_train_days:
            continue
        weights, intercept, condition, vif = fit_ridge(train, config.ridge_alpha)
        current = dated[dated["date"] == forecast_date].dropna(subset=["label"]).copy()
        if len(current) < max(4, config.top_n):
            continue
        current["score"] = current.loc[:, FACTOR_COLUMNS].to_numpy(dtype=float) @ weights + intercept
        current = current.sort_values("score", ascending=False)
        selected = set(current.head(config.top_n)["code"].astype(str))
        turnover = 1.0 if not previous_selection else 1.0 - len(selected & previous_selection) / config.top_n
        previous_selection = selected
        rank_ic = float(current["score"].corr(current["label"], method="spearman"))
        top_excess = float(current.head(config.top_n)["label"].mean())
        bottom_excess = float(current.tail(config.top_n)["label"].mean())
        buckets = [current.iloc[positions] for positions in np.array_split(np.arange(len(current)), 5)]
        quintile_returns = [float(bucket["label"].mean()) if not bucket.empty else None for bucket in buckets]
        cost = turnover * config.transaction_cost_bps / 10000.0
        evaluations.append(
            {
                "date": forecast_date.date().isoformat(),
                "rank_ic": rank_ic,
                "top_excess_return": top_excess,
                "bottom_excess_return": bottom_excess,
                "long_short_return": top_excess - bottom_excess,
                "quintile_returns": quintile_returns,
                "turnover": turnover,
                "cost": cost,
                "net_top_excess_return": top_excess - cost,
                "selected": sorted(selected),
                "condition_number": condition,
            }
        )
        latest_fit = (weights, intercept, condition, vif)

    latest_date = all_dates[-1]
    cutoff_position = max(0, len(all_dates) - 1 - config.horizon_days)
    start_position = max(0, cutoff_position - config.train_window_days)
    latest_train = dated[dated["date"].isin(set(all_dates[start_position:cutoff_position]))]
    if latest_train["date"].nunique() >= config.min_train_days:
        latest_fit = fit_ridge(latest_train, config.ridge_alpha)

    ranking: list[dict[str, Any]] = []
    weights_map: dict[str, float] = {}
    vif_map: dict[str, float] = {}
    condition = None
    if latest_fit is not None:
        weights, intercept, condition, vif_map = latest_fit
        weights_map = {factor: float(weight) for factor, weight in zip(FACTOR_COLUMNS, weights)}
        current = dated[dated["date"] == latest_date].copy()
        current["score"] = current.loc[:, FACTOR_COLUMNS].to_numpy(dtype=float) @ weights + intercept
        current = current.sort_values("score", ascending=False)
        ranking = [
            {
                "rank": index + 1,
                "code": str(row.code),
                "score": float(row.score),
                "close": float(row.close),
            }
            for index, row in enumerate(current.head(max(config.top_n * 2, 10)).itertuples())
        ]

    return _summarize_walk_forward(evaluations, ranking, weights_map, vif_map, condition, latest_date, panel, config)


def _summarize_walk_forward(
    evaluations: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    weights: dict[str, float],
    vif: dict[str, float],
    condition: float | None,
    latest_date: pd.Timestamp,
    panel: pd.DataFrame,
    config: FactorLabConfig,
) -> dict[str, Any]:
    values = pd.DataFrame(evaluations)
    period_count = len(values)
    if period_count:
        ic_mean = float(values["rank_ic"].mean())
        ic_std = float(values["rank_ic"].std(ddof=1)) if period_count > 1 else 0.0
        ic_ir = ic_mean / ic_std if ic_std > 1e-12 else None
        ic_hit = float((values["rank_ic"] > 0).mean())
        net = values["net_top_excess_return"].fillna(0)
        nav = (1 + net).cumprod()
        annualized = float(nav.iloc[-1] ** (252 / (config.rebalance_days * period_count)) - 1) if nav.iloc[-1] > 0 else -1.0
        drawdown = nav / nav.cummax() - 1
        max_drawdown = float(drawdown.min())
        avg_turnover = float(values["turnover"].mean())
        long_short = float(values["long_short_return"].mean())
        total_net = float(nav.iloc[-1] - 1)
        quintile_matrix = np.array(values["quintile_returns"].tolist(), dtype=float)
        quintile_average = np.nanmean(quintile_matrix, axis=0).tolist()
        quintile_monotonicity = float(pd.Series([5, 4, 3, 2, 1]).corr(pd.Series(quintile_average), method="spearman"))
    else:
        ic_mean = ic_ir = ic_hit = annualized = max_drawdown = avg_turnover = long_short = total_net = None
        quintile_average = []
        quintile_monotonicity = None

    factor_ics = {}
    labeled = panel.dropna(subset=["label"])
    for factor in FACTOR_COLUMNS:
        daily = labeled.groupby("date").apply(
            lambda group: group[factor].corr(group["label"], method="spearman"), include_groups=False
        )
        factor_ics[factor] = float(daily.mean()) if daily.notna().any() else None

    daily_sizes = panel.groupby("date")["code"].nunique()
    observed_size = int(daily_sizes.median()) if not daily_sizes.empty else 0
    current_size = int(daily_sizes.iloc[-1]) if not daily_sizes.empty else 0
    sufficient = period_count >= 12 and observed_size >= 15
    passed = bool(
        sufficient
        and ic_mean is not None
        and ic_mean >= 0.02
        and ic_hit is not None
        and ic_hit >= 0.52
        and long_short is not None
        and long_short > 0
        and quintile_monotonicity is not None
        and quintile_monotonicity >= 0.5
        and condition is not None
        and condition < 50
    )
    if not sufficient:
        validation_status = "insufficient_sample"
    elif passed:
        validation_status = "passed_pilot"
    else:
        validation_status = "failed_validation"
    return {
        "as_of": latest_date.date().isoformat(),
        "validation_status": validation_status,
        "period_count": period_count,
        "universe_size_configured": len(config.codes),
        "universe_size_observed_median": observed_size,
        "universe_size_current": current_size,
        "rank_ic_mean": ic_mean,
        "rank_ic_ir": ic_ir,
        "rank_ic_positive_rate": ic_hit,
        "average_long_short_return": long_short,
        "quintile_average_returns": quintile_average,
        "quintile_monotonicity": quintile_monotonicity,
        "net_top_excess_total": total_net,
        "net_top_excess_annualized": annualized,
        "net_top_excess_max_drawdown": max_drawdown,
        "average_turnover": avg_turnover,
        "condition_number": condition,
        "factor_weights": weights,
        "factor_vif": vif,
        "factor_ic_mean": factor_ics,
        "latest_ranking": ranking,
        "evaluations": evaluations,
    }
