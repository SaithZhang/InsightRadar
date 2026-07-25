"""Deterministic technology-financial-dividend rotation confirmation matrix."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean
from typing import Any

from stock_assist.data_sources.eastmoney_klines import Candle


HORIZONS = (5, 20, 60)


def build_style_rotation_matrix(
    config: dict[str, object],
    series: dict[str, list[Candle]],
    *,
    as_of: date,
    sources: dict[str, str] | None = None,
    source_gaps: list[str] | None = None,
) -> dict[str, object]:
    benchmark_config = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}
    benchmark_code = str(benchmark_config.get("code") or "")
    benchmark = _bars(series.get(benchmark_code, []), as_of)
    effective_as_of = benchmark[-1].time.date() if benchmark else as_of
    styles_config = config.get("styles") if isinstance(config.get("styles"), list) else []
    minimum_coverage = float(config.get("minimum_style_coverage") or 0.67)
    turnover_threshold = float(config.get("turnover_share_change_threshold") or 0.02)
    rows: list[dict[str, object]] = []
    all_members: list[str] = []
    style_members: dict[str, list[str]] = {}
    for item in styles_config:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        members = item.get("members") if isinstance(item.get("members"), list) else []
        codes = [str(member.get("code")) for member in members if isinstance(member, dict) and member.get("code")]
        style_members[key] = codes
        all_members.extend(codes)

    turnover_history = _turnover_share_history(style_members, series, as_of)
    benchmark_returns = {f"{h}d": _return(benchmark, h) for h in HORIZONS}
    for item in styles_config:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        label = str(item.get("label") or key)
        members = item.get("members") if isinstance(item.get("members"), list) else []
        member_rows: list[dict[str, object]] = []
        for member in members:
            if not isinstance(member, dict):
                continue
            code = str(member.get("code") or "")
            bars = _bars(series.get(code, []), as_of)
            member_rows.append(_member_metrics(member, bars, benchmark_returns, sources or {}))
        valid_latest = [row for row in member_rows if row.get("as_of")]
        coverage = len(valid_latest) / len(member_rows) if member_rows else 0.0
        relative_strength = {
            f"{h}d": _average([row.get("excess_returns", {}).get(f"{h}d") for row in valid_latest if isinstance(row.get("excess_returns"), dict)])
            for h in HORIZONS
        }
        breadth = {
            "up_count": sum(row.get("up_today") is True for row in valid_latest),
            "valid_count": len(valid_latest),
            "up_ratio": _ratio(sum(row.get("up_today") is True for row in valid_latest), len(valid_latest)),
            "above_ma20_count": sum(row.get("above_ma20") is True for row in valid_latest),
            "above_ma20_ratio": _ratio(sum(row.get("above_ma20") is True for row in valid_latest), len(valid_latest)),
            "above_ma60_count": sum(row.get("above_ma60") is True for row in valid_latest),
            "above_ma60_ratio": _ratio(sum(row.get("above_ma60") is True for row in valid_latest), len(valid_latest)),
        }
        turnover_rows = turnover_history.get(key, [])
        latest_share = turnover_rows[-1][1] if turnover_rows else None
        prior = [value for _, value in turnover_rows[-21:-1] if value is not None]
        prior20 = mean(prior) if prior else None
        turnover_change = latest_share - prior20 if latest_share is not None and prior20 is not None else None
        turnover = {
            "latest_share": latest_share,
            "prior20_average_share": prior20,
            "share_change": turnover_change,
            "confirmation": (
                "supportive" if turnover_change is not None and turnover_change >= turnover_threshold
                else "weakening" if turnover_change is not None and turnover_change <= -turnover_threshold
                else "neutral" if turnover_change is not None else "unavailable"
            ),
        }
        rows.append(
            {
                "style_key": key,
                "style_label": label,
                "definition": item.get("definition"),
                "member_count": len(member_rows),
                "valid_member_count": len(valid_latest),
                "coverage_ratio": round(coverage, 4),
                "relative_strength": _round_map(relative_strength),
                "breadth": breadth,
                "turnover": _round_map(turnover),
                "fund_proxy": {
                    "state": turnover.get("confirmation"),
                    "proxy": "固定ETF篮子公开K线收盘价×成交量近似成交额占比，相对20日均值",
                    "limitation": "近似成交额不等于官方逐日成交额，也不是ETF份额、净申购或国家队买卖。",
                },
                "earnings_confirmation": {
                    "state": "unavailable",
                    "coverage_ratio": 0.0,
                    "reason": "尚无固定口径的点时盈利预测修正源，未补0。",
                },
                "members": member_rows,
            }
        )

    leader = _rank_style(rows, "20d", reverse=True)
    weakening = _rank_style(rows, "20d", reverse=False)
    leader_key = str(leader.get("style_key") or "") if leader else None
    confirmation_days = _confirmation_days(style_members, series, benchmark, as_of, leader_key)
    evidence = _evidence(rows, leader_key, turnover_threshold)
    independent_positive = {item["family"] for item in evidence["positive"] if item.get("independent")}
    horizon_leaders = {key: (_rank_style(rows, key, reverse=True) or {}).get("style_key") for key in ("5d", "20d", "60d")}
    horizon_conflict = len({value for value in horizon_leaders.values() if value}) > 1
    coverage_ok = bool(rows) and all(float(row.get("coverage_ratio") or 0) >= minimum_coverage for row in rows) and all(value is not None for value in benchmark_returns.values())
    initial_days = int(config.get("initial_confirmation_days") or 2)
    persistent_days = int(config.get("persistent_confirmation_days") or 5)
    leader_row = next((row for row in rows if row.get("style_key") == leader_key), {})
    leader_breadth = leader_row.get("breadth") if isinstance(leader_row.get("breadth"), dict) else {}
    leader_turnover = leader_row.get("turnover") if isinstance(leader_row.get("turnover"), dict) else {}
    if not coverage_ok:
        status = "数据不足"
    elif horizon_conflict and len(independent_positive) < 2:
        status = "信号冲突"
    elif (
        confirmation_days >= persistent_days
        and not horizon_conflict
        and {"relative_strength", "breadth", "turnover"}.issubset(independent_positive)
        and float(leader_breadth.get("above_ma60_ratio") or 0) >= 0.5
        and leader_turnover.get("confirmation") == "supportive"
    ):
        status = "持续确认"
    elif confirmation_days >= initial_days and len(independent_positive) >= 2 and not horizon_conflict:
        status = "初步确认"
    elif horizon_conflict:
        status = "信号冲突"
    else:
        status = "轮动未确认"

    blocked = ["风格矩阵不得单独授权买入或提高风险预算。"]
    if status in {"数据不足", "信号冲突", "轮动未确认"}:
        blocked.append("当前证据不足以改变风险预算。")
    blocked.append("ETF成交额或份额代理不得解释为国家队买卖。")
    technology = next((row for row in rows if row.get("style_key") == "technology_growth"), {})
    financial = next((row for row in rows if row.get("style_key") == "large_financials"), {})
    dividend = next((row for row in rows if row.get("style_key") == "high_dividend"), {})
    tech20 = _metric(technology, "20d")
    fin20 = _metric(financial, "20d")
    div20 = _metric(dividend, "20d")
    tech_weaker = tech20 is not None and any(value is not None and tech20 < value for value in (fin20, div20))
    return {
        "as_of": effective_as_of.isoformat(),
        "requested_as_of": as_of.isoformat(),
        "style_rotation_status": status,
        "leader_style": leader.get("style_label") if leader else None,
        "leader_style_key": leader_key,
        "weakening_style": weakening.get("style_label") if weakening else None,
        "confirmation_days": confirmation_days,
        "relative_strength": {row["style_key"]: row["relative_strength"] for row in rows},
        "breadth_confirmation": {row["style_key"]: row["breadth"] for row in rows},
        "turnover_confirmation": {row["style_key"]: row["turnover"] for row in rows},
        "fund_proxy_confirmation": {row["style_key"]: row["fund_proxy"] for row in rows},
        "earnings_confirmation": {row["style_key"]: row["earnings_confirmation"] for row in rows},
        "positive_evidence": evidence["positive"],
        "negative_evidence": evidence["negative"],
        "blocked_conclusions": blocked,
        "source_coverage": {
            "minimum_required": minimum_coverage,
            "benchmark": benchmark_code,
            "benchmark_returns": _round_map(benchmark_returns),
            "styles": {row["style_key"]: row["coverage_ratio"] for row in rows},
            "sources": sources or {},
            "gaps": source_gaps or [],
        },
        "calibration": "diagnostic_unbacktested",
        "horizon_leaders": horizon_leaders,
        "styles": rows,
        "questions": {
            "technology_vs_financial_dividend": "科技20日相对强弱弱于金融/高股息。" if tech_weaker else "科技尚未持续弱于金融和高股息两者。",
            "single_day_or_rotation": "达到持续风格轮动合同。" if status == "持续确认" else "尚不能排除单日跷跷板或短期切换。",
            "enough_to_change_risk_budget": status == "持续确认",
        },
        "authority": "diagnostic_evidence_only_no_trade_authority",
    }


def _member_metrics(member: dict[str, object], bars: list[Candle], benchmark_returns: dict[str, float | None], sources: dict[str, str]) -> dict[str, object]:
    returns = {f"{h}d": _return(bars, h) for h in HORIZONS}
    excess = {key: value - benchmark_returns[key] if value is not None and benchmark_returns.get(key) is not None else None for key, value in returns.items()}
    latest = bars[-1] if bars else None
    return {
        "code": member.get("code"),
        "name": member.get("name"),
        "industry": member.get("industry"),
        "as_of": latest.time.date().isoformat() if latest else None,
        "returns": _round_map(returns),
        "excess_returns": _round_map(excess),
        "up_today": bool(len(bars) >= 2 and bars[-1].close > bars[-2].close) if bars else None,
        "above_ma20": _above_ma(bars, 20),
        "above_ma60": _above_ma(bars, 60),
        "latest_amount": latest.amount if latest and latest.amount > 0 else None,
        "source": sources.get(str(member.get("code"))) or "unavailable",
    }


def _turnover_share_history(style_members: dict[str, list[str]], series: dict[str, list[Candle]], as_of: date) -> dict[str, list[tuple[date, float]]]:
    by_code = {code: {bar.time.date(): bar.amount for bar in _bars(series.get(code, []), as_of) if bar.amount > 0} for codes in style_members.values() for code in codes}
    dates = sorted({day for rows in by_code.values() for day in rows})
    result: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for day in dates:
        totals = {key: sum(by_code.get(code, {}).get(day, 0.0) for code in codes) for key, codes in style_members.items()}
        all_amount = sum(totals.values())
        if all_amount <= 0:
            continue
        for key, value in totals.items():
            result[key].append((day, value / all_amount))
    return result


def _confirmation_days(style_members: dict[str, list[str]], series: dict[str, list[Candle]], benchmark: list[Candle], as_of: date, leader_key: str | None) -> int:
    if not leader_key:
        return 0
    dates = [bar.time.date() for bar in benchmark if bar.time.date() <= as_of]
    count = 0
    for day in reversed(dates[-20:]):
        scores: dict[str, float] = {}
        for key, codes in style_members.items():
            values = [_return(_bars(series.get(code, []), day), 20) for code in codes]
            valid = [value for value in values if value is not None]
            if valid:
                scores[key] = mean(valid)
        if not scores or max(scores, key=scores.get) != leader_key:
            break
        count += 1
    return count


def _evidence(rows: list[dict[str, object]], leader_key: str | None, turnover_threshold: float) -> dict[str, list[dict[str, object]]]:
    positive: list[dict[str, object]] = []
    negative: list[dict[str, object]] = []
    if not leader_key:
        return {"positive": positive, "negative": negative}
    leader = next((row for row in rows if row.get("style_key") == leader_key), {})
    rs = leader.get("relative_strength") if isinstance(leader.get("relative_strength"), dict) else {}
    breadth = leader.get("breadth") if isinstance(leader.get("breadth"), dict) else {}
    turnover = leader.get("turnover") if isinstance(leader.get("turnover"), dict) else {}
    if float(rs.get("20d") or 0) > 0:
        positive.append({"family": "relative_strength", "independent": True, "detail": f"20日超额{float(rs['20d']):+.2%}"})
    else:
        negative.append({"family": "relative_strength", "independent": True, "detail": "20日超额未转正"})
    if float(breadth.get("above_ma20_ratio") or 0) >= 0.5:
        positive.append({"family": "breadth", "independent": True, "detail": f"MA20上方占比{float(breadth['above_ma20_ratio']):.0%}"})
    else:
        negative.append({"family": "breadth", "independent": True, "detail": "MA20宽度不足50%"})
    change = turnover.get("share_change")
    if isinstance(change, (int, float)) and change >= turnover_threshold:
        positive.append({"family": "turnover", "independent": True, "detail": f"成交额占比高于20日均值{change:+.2%}"})
    else:
        negative.append({"family": "turnover", "independent": True, "detail": "成交额占比未同步增强"})
    negative.append({"family": "earnings", "independent": True, "detail": "盈利预测修正数据缺失，未补0"})
    return {"positive": positive, "negative": negative}


def _rank_style(rows: list[dict[str, object]], horizon: str, *, reverse: bool) -> dict[str, object] | None:
    valid = [row for row in rows if _metric(row, horizon) is not None]
    if not valid:
        return None
    return sorted(valid, key=lambda row: float(_metric(row, horizon) or 0), reverse=reverse)[0]


def _metric(row: dict[str, object], horizon: str) -> float | None:
    rs = row.get("relative_strength") if isinstance(row.get("relative_strength"), dict) else {}
    value = rs.get(horizon)
    return float(value) if isinstance(value, (int, float)) else None


def _bars(values: list[Candle], as_of: date) -> list[Candle]:
    return sorted((bar for bar in values if bar.close > 0 and bar.time.date() <= as_of), key=lambda bar: bar.time)


def _return(bars: list[Candle], horizon: int) -> float | None:
    if len(bars) <= horizon or bars[-horizon - 1].close <= 0:
        return None
    return bars[-1].close / bars[-horizon - 1].close - 1.0


def _above_ma(bars: list[Candle], window: int) -> bool | None:
    if len(bars) < window:
        return None
    return bars[-1].close > mean(bar.close for bar in bars[-window:])


def _average(values: list[object]) -> float | None:
    valid = [float(value) for value in values if isinstance(value, (int, float))]
    return mean(valid) if valid else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _round_map(values: dict[str, Any]) -> dict[str, Any]:
    return {key: round(value, 6) if isinstance(value, float) else value for key, value in values.items()}
