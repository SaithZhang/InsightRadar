"""Auditable ETF-share proxy for disclosed state-team positions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


SHARES_PER_YI = 100_000_000
SHARES_PER_WAN = 10_000


def build_state_team_etf_proxy(
    raw_history: dict[str, Any],
    config: dict[str, object],
    *,
    as_of: date | None = None,
) -> dict[str, object]:
    """Build a lower-bound exit estimate from ETF total-share history.

    The estimate is deliberately one-sided: disclosed state-team units minus
    the ETF's current *total* units.  Because one holder cannot own more than
    all outstanding units, a positive difference is a hard lower bound on
    units no longer held in that ETF.  It is not a cash-flow estimate.
    """

    target = as_of or date.today()
    items = config.get("items")
    baselines = config.get("baseline_dates")
    configured_items = items if isinstance(items, list) else []
    configured_baselines = baselines if isinstance(baselines, dict) else {}
    rows: list[dict[str, object]] = []
    gaps: list[str] = []

    for raw_item in configured_items:
        if not isinstance(raw_item, dict):
            continue
        code = str(raw_item.get("code") or "").upper()
        if not code:
            continue
        observations = _observations(raw_history.get(code), target)
        if not observations:
            gaps.append(f"{code} 未取得截至 {target.isoformat()} 的ETF份额历史。")
            continue

        current_date, current_wan = observations[-1]
        disclosed_shares = _positive_number(raw_item.get("disclosed_state_shares"))
        current_shares = current_wan * SHARES_PER_WAN
        minimum_exited = max((disclosed_shares or 0) - current_shares, 0)
        minimum_exit_ratio = minimum_exited / disclosed_shares if disclosed_shares else None
        recent_changes = {
            key: change
            for key, offset in (
                ("one_observation", 1),
                ("five_observations", 5),
                ("twenty_observations", 20),
            )
            if (change := _observation_change(observations, offset)) is not None
        }
        baseline_payload: dict[str, object] = {}
        for baseline_id, raw_date in configured_baselines.items():
            baseline_date = _parse_date(raw_date)
            if baseline_date is None:
                gaps.append(f"{code} 基线 {baseline_id} 日期无效：{raw_date}。")
                continue
            observation = _latest_on_or_before(observations, baseline_date)
            if observation is None:
                gaps.append(f"{code} 缺少基线 {baseline_id}（{baseline_date.isoformat()}）前的份额数据。")
                continue
            effective_date, baseline_wan = observation
            baseline_shares = baseline_wan * SHARES_PER_WAN
            baseline_payload[str(baseline_id)] = {
                "requested_date": baseline_date.isoformat(),
                "effective_date": effective_date.isoformat(),
                "total_shares": round(baseline_shares),
                "yi_shares": round(baseline_shares / SHARES_PER_YI, 2),
                "current_change_pct": _pct_change(current_shares, baseline_shares),
            }

        rows.append(
            {
                "code": code,
                "label": str(raw_item.get("label") or code),
                "current_date": current_date.isoformat(),
                "current_total_shares": round(current_shares),
                "current_yi_shares": round(current_shares / SHARES_PER_YI, 2),
                "disclosure_as_of": str(config.get("disclosure_as_of") or ""),
                "disclosed_state_shares": round(disclosed_shares) if disclosed_shares else None,
                "disclosed_state_yi_shares": round(disclosed_shares / SHARES_PER_YI, 2) if disclosed_shares else None,
                "minimum_exited_shares": round(minimum_exited) if disclosed_shares else None,
                "minimum_exited_yi_shares": round(minimum_exited / SHARES_PER_YI, 2) if disclosed_shares else None,
                "minimum_exit_ratio": round(minimum_exit_ratio, 4) if minimum_exit_ratio is not None else None,
                "recent_changes": recent_changes,
                "baselines": baseline_payload,
                "source_label": str(raw_item.get("source_label") or ""),
                "source_url": str(raw_item.get("source_url") or ""),
            }
        )

    if not rows:
        gaps.append("国家队ETF份额代理没有可计算的有效产品。")
    direct_holding_gap = str(config.get("direct_holding_gap") or "").strip()
    if direct_holding_gap:
        gaps.append(direct_holding_gap)

    summary = _aggregate(rows, configured_baselines)
    summary["state"] = _state(summary.get("minimum_exit_ratio"))
    summary["change_signal"] = _change_signal(summary.get("recent_changes"))
    summary["as_of"] = max((str(row["current_date"]) for row in rows), default=target.isoformat())
    summary["disclosure_as_of"] = str(config.get("disclosure_as_of") or "")
    return {
        "summary": summary,
        "rows": rows,
        "data_gaps": _dedupe(gaps),
        "methodology": [
            "最低退出份额 = max(年报披露的汇金持有份额 - 当前ETF总份额, 0)。",
            "该值是ETF份额退出下界，不等于二级市场净卖出金额；ETF赎回可发生实物交割，底层股票也可能转持。",
            "仅覆盖配置中的4只沪深300ETF，不代表2015年证金直接持股或全部国家队账户。",
            "最近1/5/20次变化描述ETF总份额代理；份额收缩会抬高累计退出下界，但不能证明当期卖方就是国家队。",
        ],
    }


def _observations(frame: Any, as_of: date) -> list[tuple[date, float]]:
    if frame is None or not hasattr(frame, "iterrows"):
        return []
    observations: dict[date, float] = {}
    for _, row in frame.iterrows():
        observed = _parse_date(row.get("CHANGE_DATE"))
        total_wan = _positive_number(row.get("TOTAL_SHARE")) or _positive_number(row.get("FUND_SHARE"))
        if observed is None or observed > as_of or total_wan is None:
            continue
        observations[observed] = total_wan
    return sorted(observations.items())


def _latest_on_or_before(
    observations: list[tuple[date, float]], target: date
) -> tuple[date, float] | None:
    eligible = [item for item in observations if item[0] <= target]
    return eligible[-1] if eligible else None


def _observation_change(
    observations: list[tuple[date, float]], offset: int
) -> dict[str, object] | None:
    if offset <= 0 or len(observations) <= offset:
        return None
    current_date, current_wan = observations[-1]
    from_date, from_wan = observations[-1 - offset]
    current_shares = current_wan * SHARES_PER_WAN
    from_shares = from_wan * SHARES_PER_WAN
    change_shares = current_shares - from_shares
    return {
        "observations": offset,
        "from_date": from_date.isoformat(),
        "to_date": current_date.isoformat(),
        "from_total_shares": round(from_shares),
        "from_yi_shares": round(from_shares / SHARES_PER_YI, 2),
        "share_change": round(change_shares),
        "yi_share_change": round(change_shares / SHARES_PER_YI, 2),
        "change_pct": _pct_change(current_shares, from_shares),
    }


def _aggregate(rows: list[dict[str, object]], baseline_dates: dict[object, object]) -> dict[str, object]:
    current = sum(float(row.get("current_total_shares") or 0) for row in rows)
    disclosed = sum(float(row.get("disclosed_state_shares") or 0) for row in rows)
    minimum_exited = sum(float(row.get("minimum_exited_shares") or 0) for row in rows)
    baseline_totals: dict[str, object] = {}
    recent_changes: dict[str, object] = {}
    for change_id in ("one_observation", "five_observations", "twenty_observations"):
        from_total = 0.0
        current_total = 0.0
        tightening = 0.0
        covered = 0
        from_dates: list[str] = []
        to_dates: list[str] = []
        for row in rows:
            row_changes = row.get("recent_changes")
            item = row_changes.get(change_id) if isinstance(row_changes, dict) else None
            if not isinstance(item, dict) or item.get("from_total_shares") is None:
                continue
            row_current = float(row.get("current_total_shares") or 0)
            row_from = float(item["from_total_shares"])
            disclosed_row = float(row.get("disclosed_state_shares") or 0)
            from_total += row_from
            current_total += row_current
            tightening += max(disclosed_row - row_current, 0) - max(disclosed_row - row_from, 0)
            from_dates.append(str(item.get("from_date") or ""))
            to_dates.append(str(item.get("to_date") or ""))
            covered += 1
        share_change = current_total - from_total
        recent_changes[change_id] = {
            "coverage": f"{covered}/{len(rows)}",
            "from_date_min": min(from_dates) if from_dates else None,
            "from_date_max": max(from_dates) if from_dates else None,
            "to_date": max(to_dates) if to_dates else None,
            "from_total_shares": round(from_total) if covered else None,
            "from_yi_shares": round(from_total / SHARES_PER_YI, 2) if covered else None,
            "share_change": round(share_change) if covered else None,
            "yi_share_change": round(share_change / SHARES_PER_YI, 2) if covered else None,
            "change_pct": _pct_change(current_total, from_total) if covered else None,
            "lower_bound_tightening_shares": round(tightening) if covered else None,
            "lower_bound_tightening_yi_shares": round(tightening / SHARES_PER_YI, 2) if covered else None,
        }
    for baseline_id in baseline_dates:
        total = 0.0
        covered = 0
        for row in rows:
            row_baselines = row.get("baselines")
            item = row_baselines.get(str(baseline_id)) if isinstance(row_baselines, dict) else None
            if isinstance(item, dict) and item.get("total_shares") is not None:
                total += float(item["total_shares"])
                covered += 1
        baseline_totals[str(baseline_id)] = {
            "requested_date": str(baseline_dates[baseline_id]),
            "coverage": f"{covered}/{len(rows)}",
            "total_shares": round(total) if covered else None,
            "yi_shares": round(total / SHARES_PER_YI, 2) if covered else None,
            "current_change_pct": _pct_change(current, total) if covered else None,
        }
    return {
        "product_count": len(rows),
        "current_total_shares": round(current),
        "current_yi_shares": round(current / SHARES_PER_YI, 2),
        "disclosed_state_shares": round(disclosed) if disclosed else None,
        "disclosed_state_yi_shares": round(disclosed / SHARES_PER_YI, 2) if disclosed else None,
        "minimum_exited_shares": round(minimum_exited) if disclosed else None,
        "minimum_exited_yi_shares": round(minimum_exited / SHARES_PER_YI, 2) if disclosed else None,
        "minimum_exit_ratio": round(minimum_exited / disclosed, 4) if disclosed else None,
        "recent_changes": recent_changes,
        "baselines": baseline_totals,
    }


def _state(value: object) -> str:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return "待核验"
    if ratio >= 0.75:
        return "ETF份额近清仓式退出"
    if ratio >= 0.5:
        return "ETF份额大幅退出"
    if ratio > 0:
        return "ETF份额部分退出"
    return "未观察到可证明退出"


def _change_signal(value: object) -> str:
    if not isinstance(value, dict):
        return "短周期变化待核验"
    five = value.get("five_observations")
    twenty = value.get("twenty_observations")
    five_pct = five.get("change_pct") if isinstance(five, dict) else None
    twenty_pct = twenty.get("change_pct") if isinstance(twenty, dict) else None
    if isinstance(five_pct, (int, float)) and isinstance(twenty_pct, (int, float)):
        if five_pct >= 1 and twenty_pct <= -3:
            return "短期回补、近20次仍净收缩"
        if five_pct <= -1 and twenty_pct >= 3:
            return "短期再收缩、近20次仍净回升"
    if (isinstance(five_pct, (int, float)) and five_pct <= -1) or (
        isinstance(twenty_pct, (int, float)) and twenty_pct <= -3
    ):
        return "ETF总份额继续收缩"
    if (isinstance(five_pct, (int, float)) and five_pct >= 1) or (
        isinstance(twenty_pct, (int, float)) and twenty_pct >= 3
    ):
        return "ETF总份额回升"
    if five_pct is not None or twenty_pct is not None:
        return "ETF总份额基本稳定"
    return "短周期变化待核验"


def _pct_change(current: float, baseline: float) -> float | None:
    if baseline <= 0:
        return None
    return round((current / baseline - 1) * 100, 2)


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().split(" ", 1)[0]
    if text.endswith(".0"):
        text = text[:-2]
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
