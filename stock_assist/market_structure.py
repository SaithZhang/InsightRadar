"""Point-in-time A-share breadth and index-divergence diagnostics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import statistics
from typing import Iterable, Mapping


DEFAULT_TECH_INDUSTRIES = ("电子", "通信", "计算机")


def build_anchor_structure(
    records: Iterable[Mapping[str, object]],
    *,
    anchor_date: date,
    as_of: date,
    benchmark_anchor_close: float,
    benchmark_current_close: float | None,
    min_rows: int = 4000,
    min_coverage: float = 0.90,
    technology_industries: Iterable[str] = DEFAULT_TECH_INDUSTRIES,
    source: str,
    query: str,
) -> dict[str, object]:
    """Aggregate a fixed-anchor cross-section without hiding coverage gaps.

    The denominator is securities listed on or before ``anchor_date`` that are
    present in the returned cross-section. Returns are expected in decimal
    form and should already be adjusted by the upstream provider.
    """

    tech_set = {str(item).strip() for item in technology_industries if str(item).strip()}
    eligible: list[dict[str, object]] = []
    valid: list[dict[str, object]] = []
    seen: set[str] = set()
    missing_listing_date_count = 0
    post_anchor_listing_count = 0
    for raw in records:
        code = str(raw.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        listed = _date_value(raw.get("listing_date"))
        if listed is None:
            missing_listing_date_count += 1
            continue
        if listed > anchor_date:
            post_anchor_listing_count += 1
            continue
        row = {
            "code": code,
            "name": str(raw.get("name") or code),
            "listing_date": listed,
            "return_rate": _finite_number(raw.get("return_rate")),
            "anchor_close": _positive_number(raw.get("anchor_close")),
            "current_close": _positive_number(raw.get("current_close")),
            "industry": str(raw.get("industry") or "未分类").strip() or "未分类",
            "current_free_float_cap": _positive_number(raw.get("current_free_float_cap")),
        }
        eligible.append(row)
        if (
            row["return_rate"] is not None
            and row["anchor_close"] is not None
            and row["current_close"] is not None
        ):
            valid.append(row)

    eligible_count = len(eligible)
    valid_count = len(valid)
    coverage = valid_count / eligible_count if eligible_count else 0.0
    status = "verified" if valid_count >= min_rows and coverage >= min_coverage else "partial"
    if not valid:
        status = "unavailable"

    returns = [float(row["return_rate"]) for row in valid]
    below_count = sum(value < 0 for value in returns)
    below_ratio = below_count / valid_count if valid_count else None
    equal_weight_return = statistics.fmean(returns) if returns else None
    median_return = statistics.median(returns) if returns else None
    p25_return = _percentile(returns, 0.25)
    p75_return = _percentile(returns, 0.75)
    benchmark_return = (
        benchmark_current_close / benchmark_anchor_close - 1
        if benchmark_current_close is not None and benchmark_anchor_close > 0
        else None
    )
    equal_weight_equivalent = (
        benchmark_anchor_close * (1 + equal_weight_return)
        if equal_weight_return is not None
        else None
    )
    median_equivalent = (
        benchmark_anchor_close * (1 + median_return)
        if median_return is not None
        else None
    )
    divergence = (
        benchmark_return - equal_weight_return
        if benchmark_return is not None and equal_weight_return is not None
        else None
    )

    cap_rows = [row for row in valid if row["current_free_float_cap"] is not None]
    cap_total = sum(float(row["current_free_float_cap"]) for row in cap_rows)
    current_float_weighted_return = (
        sum(float(row["return_rate"]) * float(row["current_free_float_cap"]) for row in cap_rows) / cap_total
        if cap_total > 0
        else None
    )
    largest = sorted(cap_rows, key=lambda row: float(row["current_free_float_cap"]), reverse=True)
    top10_share = (
        sum(float(row["current_free_float_cap"]) for row in largest[:10]) / cap_total
        if cap_total > 0
        else None
    )
    tech_rows = [row for row in cap_rows if row["industry"] in tech_set]
    nontech_rows = [row for row in cap_rows if row["industry"] not in tech_set]
    tech_cap = sum(float(row["current_free_float_cap"]) for row in tech_rows)
    tech_share = tech_cap / cap_total if cap_total > 0 else None

    industry_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in valid:
        industry_groups[str(row["industry"])].append(row)
    industries = []
    for industry, rows in industry_groups.items():
        values = [float(row["return_rate"]) for row in rows]
        industries.append(
            {
                "industry": industry,
                "count": len(rows),
                "below_anchor_count": sum(value < 0 for value in values),
                "below_anchor_ratio": round(sum(value < 0 for value in values) / len(values), 4),
                "median_return": round(statistics.median(values), 4),
                "equal_weight_return": round(statistics.fmean(values), 4),
            }
        )
    industries.sort(key=lambda row: (-float(row["below_anchor_ratio"]), -int(row["count"])))

    health_score = _health_score(below_ratio, median_return, divergence) if status != "unavailable" else None
    claim_status = "unverified"
    if status == "verified":
        claim_status = "supported" if below_count >= 3900 else "not_supported"

    return {
        "as_of": as_of.isoformat(),
        "anchor_date": anchor_date.isoformat(),
        "status": status,
        "source": source,
        "query": query,
        "universe_definition": "返回横截面中上市日期不晚于锚点日、且两端收盘与前复权区间收益均有效的A股",
        "returned_unique_count": len(seen),
        "post_anchor_listing_count": post_anchor_listing_count,
        "missing_listing_date_count": missing_listing_date_count,
        "eligible_count": eligible_count,
        "valid_count": valid_count,
        "coverage_ratio": round(coverage, 4),
        "below_anchor_count": below_count if valid else None,
        "below_anchor_ratio": round(below_ratio, 4) if below_ratio is not None else None,
        "claim_3900_status": claim_status,
        "equal_weight_return": _rounded(equal_weight_return),
        "median_return": _rounded(median_return),
        "p25_return": _rounded(p25_return),
        "p75_return": _rounded(p75_return),
        "benchmark_anchor_close": round(benchmark_anchor_close, 4),
        "benchmark_current_close": _rounded(benchmark_current_close, 4),
        "benchmark_return": _rounded(benchmark_return),
        "equal_weight_equivalent_point": _rounded(equal_weight_equivalent, 2),
        "median_equivalent_point": _rounded(median_equivalent, 2),
        "benchmark_equal_weight_gap": _rounded(divergence),
        "current_float_weighted_return_proxy": _rounded(current_float_weighted_return),
        "top10_current_free_float_share": _rounded(top10_share),
        "technology_definition": sorted(tech_set),
        "technology_current_free_float_share": _rounded(tech_share),
        "technology_equal_weight_return": _group_mean(tech_rows),
        "nontechnology_equal_weight_return": _group_mean(nontech_rows),
        "health_score": health_score,
        "health_label": _health_label(health_score),
        "breadth_label": _breadth_label(below_ratio),
        "industry_weakness": industries[:8],
        "methodology": [
            "个股区间收益使用数据源返回的前复权区间涨跌幅；原始收盘价只用于覆盖校验。",
            "等权等效上证=锚点上证收盘×(1+固定股票池个股收益算术平均)，不是官方指数。",
            "中位数等效点位描述典型股票体感；与等权组合收益不是同一概念。",
            "科技口径固定为申万一级电子、通信、计算机；自由流通市值权重只作当前权重代理，不冒充历史指数点位贡献。",
        ],
    }


def _health_score(
    below_ratio: float | None,
    median_return: float | None,
    divergence: float | None,
) -> int | None:
    if below_ratio is None or median_return is None:
        return None
    breadth = 100.0 - _scale(below_ratio, 0.30, 0.80)
    median = _scale(median_return, -0.40, 0.40)
    divergence_health = 50.0 if divergence is None else 100.0 - _scale(abs(divergence), 0.05, 0.35)
    return int(round(0.50 * breadth + 0.30 * median + 0.20 * divergence_health))


def _health_label(score: int | None) -> str:
    if score is None:
        return "待确认"
    if score <= 20:
        return "多数深度低于锚点"
    if score <= 40:
        return "累计位置偏弱"
    if score <= 60:
        return "累计位置分化"
    if score <= 75:
        return "多数高于锚点"
    return "多数显著高于锚点"


def _breadth_label(value: float | None) -> str:
    if value is None:
        return "待确认"
    if value >= 0.75:
        return "极端破位"
    if value >= 0.60:
        return "多数股票深度弱势"
    if value >= 0.50:
        return "过半股票弱于锚点"
    return "未见多数股票低于锚点"


def _group_mean(rows: list[dict[str, object]]) -> float | None:
    values = [float(row["return_rate"]) for row in rows]
    return _rounded(statistics.fmean(values)) if values else None


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip().replace("-", "")
    if len(text) < 8 or not text[:8].isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _finite_number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_number(value: object) -> float | None:
    parsed = _finite_number(value)
    return parsed if parsed is not None and parsed > 0 else None


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None
