"""Typed normalization for the after-close decision workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Mapping


CARD_SPECS = (
    ("risk_assets", "a_share_technology", "A股科技", "risk", "star50"),
    ("risk_assets", "us_technology", "美股科技", "macro", "qqq"),
    ("risk_assets", "us_semiconductors", "美股半导体", "macro", "sox"),
    ("risk_assets", "korea", "韩国", "macro", "kospi"),
    ("risk_assets", "japan", "日本", "risk", "nikkei"),
    ("macro_pressure", "crude_oil", "原油与能源", "macro", "brent"),
    ("macro_pressure", "us_duration", "美国10年期利率", "macro", "us10y"),
)


def plain_gap(value: object) -> str:
    text = " ".join(str(value or "").split())
    lowered = text.lower()
    if "httpsconnectionpool" in lowered or "read timed out" in lowered:
        return "上游市场数据源超时"
    if "connection" in lowered and "closed" in lowered:
        return "上游市场数据源连接中断"
    if "missing_series:" in lowered:
        return "所需市场序列不可用"
    return text or "数据不可用"


def build_market_matrix_contract(
    unified_decision: Mapping[str, object],
    *,
    report_dir: Path,
    generated_at: datetime,
) -> dict[str, object]:
    risk_payload = _load_risk_payload(unified_decision, report_dir)
    cards = [
        _card(spec, risk_payload, generated_at.date())
        for spec in CARD_SPECS
    ]
    return {
        "authority": "diagnostic_only",
        "groups": [
            {
                "id": "risk_assets",
                "label": "全球科技与风险资产",
                "cards": [
                    card for card in cards if card["group"] == "risk_assets"
                ],
            },
            {
                "id": "macro_pressure",
                "label": "宏观压力",
                "cards": [
                    card for card in cards if card["group"] == "macro_pressure"
                ],
            },
        ],
        "portfolio_translation": _portfolio_translation(
            unified_decision,
            cards,
        ),
    }


def _load_risk_payload(
    unified_decision: Mapping[str, object],
    report_dir: Path,
) -> dict[str, object]:
    sources = unified_decision.get("source_reports")
    if not isinstance(sources, list):
        return {}
    root = report_dir.resolve()
    for item in sources:
        if not isinstance(item, dict) or item.get("workflow") != "risk_watch":
            continue
        raw_path = item.get("path")
        if not raw_path:
            return {}
        path = Path(str(raw_path)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _card(
    spec: tuple[str, str, str, str, str],
    risk_payload: Mapping[str, object],
    report_date: date,
) -> dict[str, object]:
    group, card_id, label, family, key = spec
    if family == "risk":
        source = _risk_series(risk_payload, key)
    else:
        source = _macro_series(risk_payload, key)
    if not source:
        return {
            "group": group,
            "id": card_id,
            "label": label,
            "state": "unavailable",
            "state_label": "不可用",
            "day_change": None,
            "as_of": None,
            "freshness": "unavailable",
            "source": None,
            "points": [],
            "authority": "diagnostic_only",
            "gap": "数据源超时或该序列尚未形成有效收盘数据",
        }
    as_of = _parse_date(source.get("as_of"))
    points = source.get("points")
    values = points if isinstance(points, list) else []
    return {
        "group": group,
        "id": card_id,
        "label": label,
        "state": _state(source),
        "state_label": _state_label(source),
        "day_change": _day_change(values),
        "as_of": as_of.isoformat() if as_of else None,
        "freshness": _freshness(as_of, report_date),
        "source": source.get("source"),
        "points": values[-30:],
        "authority": "diagnostic_only",
        "gap": None,
    }


def _risk_series(
    risk_payload: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    replay = risk_payload.get("replay")
    rows = replay.get("rows") if isinstance(replay, dict) else None
    if not isinstance(rows, list):
        return {}
    points: list[dict[str, object]] = []
    latest_metrics: dict[str, object] = {}
    for row in rows[-30:]:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics")
        metric = metrics.get(key) if isinstance(metrics, dict) else None
        if not isinstance(metric, dict) or metric.get("close") is None:
            continue
        points.append({"date": row.get("date"), "close": metric["close"]})
        latest_metrics = metric
    if not points:
        return {}
    return {
        "source": latest_metrics.get("source") or "risk-watch",
        "as_of": points[-1]["date"],
        "points": points,
        "ma20_gap": latest_metrics.get("ma20_gap"),
    }


def _macro_series(
    risk_payload: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    macro = risk_payload.get("macro_transmission")
    trajectories = macro.get("series_30d") if isinstance(macro, dict) else None
    item = trajectories.get(key) if isinstance(trajectories, dict) else None
    return item if isinstance(item, dict) else {}


def _state(source: Mapping[str, object]) -> str:
    gap = number(source.get("ma20_gap"))
    if gap is None:
        return "observed"
    if gap < -0.005:
        return "below_ma20"
    if gap > 0.005:
        return "above_ma20"
    return "near_ma20"


def _state_label(source: Mapping[str, object]) -> str:
    return {
        "below_ma20": "低于20日均线",
        "above_ma20": "高于20日均线",
        "near_ma20": "20日均线附近",
        "observed": "观察中",
    }[_state(source)]


def _day_change(points: list[object]) -> float | None:
    valid = [
        number(item.get("close"))
        for item in points
        if isinstance(item, dict)
    ]
    values = [value for value in valid if value is not None]
    if len(values) < 2 or values[-2] == 0:
        return None
    return values[-1] / values[-2] - 1


def _freshness(as_of: date | None, report_date: date) -> str:
    if as_of is None:
        return "unavailable"
    return "fresh" if (report_date - as_of).days <= 1 else "stale"


def _portfolio_translation(
    unified_decision: Mapping[str, object],
    cards: list[dict[str, object]],
) -> str:
    unavailable = sum(card["freshness"] == "unavailable" for card in cards)
    first_action = str(
        unified_decision.get("first_action")
        or "市场矩阵不改变当前持仓计划"
    )
    if unavailable:
        return f"{first_action}；{unavailable}项跨市场数据不可用，不据此升级风险预算。"
    return f"{first_action}；矩阵仅用于解释环境，不独立授权交易。"


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FreshnessBadge:
    id: str
    label: str
    as_of: str | None
    state: str


@dataclass(frozen=True)
class MatrixCardView:
    id: str
    label: str
    state_label: str
    day_change: float | None
    as_of: str | None
    freshness: str
    source: str | None
    authority: str
    gap: str | None
    points: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class MatrixGroupView:
    id: str
    label: str
    cards: tuple[MatrixCardView, ...]


@dataclass(frozen=True)
class HoldingActionView:
    name: str
    code: str
    action: str
    upside: str
    flat: str
    downside: str
    priority: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class WorkbenchView:
    generated_at: str
    plan_date: str
    stance: str
    first_action: str
    risk_label: str
    risk_score: int | None
    holding_count: int
    decision_ready_text: str
    freshness: tuple[FreshnessBadge, ...]
    matrix_groups: tuple[MatrixGroupView, ...]
    portfolio_translation: str
    holdings: tuple[HoldingActionView, ...]
    gaps: tuple[str, ...]
    research_sections: tuple[dict[str, object], ...]
    signal_outcomes: Mapping[str, object]
    default_route: str = "today"


def build_workbench_view(
    payload: Mapping[str, object],
    markdown: str,
) -> WorkbenchView:
    decision = (
        payload.get("unified_decision")
        if isinstance(payload.get("unified_decision"), dict)
        else {}
    )
    reliability = (
        payload.get("reliability")
        if isinstance(payload.get("reliability"), dict)
        else {}
    )
    budget = (
        decision.get("risk_budget")
        if isinstance(decision.get("risk_budget"), dict)
        else {}
    )
    holding_rows = (
        decision.get("holding_plans")
        if isinstance(decision.get("holding_plans"), list)
        else []
    )
    blockers = (
        tuple(
            plain_gap(item)
            for item in decision.get("blocked_actions", [])
            if str(item).strip()
        )
        if isinstance(decision.get("blocked_actions"), list)
        else ()
    )
    holdings = tuple(
        HoldingActionView(
            name=str(item.get("name") or item.get("code") or "未命名持仓"),
            code=str(item.get("code") or ""),
            action=str(
                item.get("position_action")
                or item.get("action")
                or "等待确认"
            ),
            upside=str(item.get("upside_trigger") or "不追涨"),
            flat=str(item.get("flat_trigger") or "维持原计划"),
            downside=str(item.get("downside_trigger") or "复核风险线"),
            priority=str(item.get("priority") or "中"),
            blockers=blockers,
        )
        for item in holding_rows
        if isinstance(item, dict)
    )
    matrix = (
        payload.get("market_matrix")
        if isinstance(payload.get("market_matrix"), dict)
        else {}
    )
    gaps = _plain_gaps(payload, decision)
    holding_count = int(reliability.get("holding_count") or len(holdings))
    ready = int(reliability.get("decision_ready_holdings") or 0)
    generated_at_text = str(payload.get("generated_at") or "")
    generated_date = _parse_datetime(generated_at_text).date()
    score = number(budget.get("risk_score"))
    return WorkbenchView(
        generated_at=generated_at_text,
        plan_date=str(decision.get("plan_date") or "待确认"),
        stance=str(decision.get("stance") or "等待确认"),
        first_action=str(decision.get("first_action") or "等待确认"),
        risk_label={
            "green": "绿灯",
            "yellow": "黄灯",
            "orange": "橙灯",
            "red": "红灯",
        }.get(str(budget.get("risk_level")), "待确认"),
        risk_score=int(score) if score is not None else None,
        holding_count=holding_count,
        decision_ready_text=f"{ready}/{holding_count}",
        freshness=_freshness_badges(decision, generated_date),
        matrix_groups=_matrix_groups(matrix),
        portfolio_translation=str(
            matrix.get("portfolio_translation")
            or "市场矩阵不改变当前计划。"
        ),
        holdings=holdings,
        gaps=gaps,
        research_sections=_research_sections(payload),
        signal_outcomes=(
            payload.get("signal_outcomes")
            if isinstance(payload.get("signal_outcomes"), dict)
            else {}
        ),
    )


def _freshness_badges(
    decision: Mapping[str, object],
    report_date: date,
) -> tuple[FreshnessBadge, ...]:
    rows = decision.get("source_reports")
    sources = rows if isinstance(rows, list) else []
    badges: list[FreshnessBadge] = []
    labels = {
        "risk_watch": "市场风险",
        "market_pulse": "盘中脉冲",
        "market_levels": "关键价位",
        "ai_capex_watch": "产业研究",
        "style_rotation": "风格轮动",
    }
    for item in sources:
        if not isinstance(item, dict):
            continue
        workflow = str(item.get("workflow") or "")
        as_of = str(item.get("as_of") or "") or None
        status = str(item.get("status") or "unavailable")
        source_date = _parse_date(as_of)
        if status != "current" or source_date is None:
            state = "unavailable"
        elif (report_date - source_date).days > 1:
            state = "stale"
        else:
            state = "fresh"
        badges.append(
            FreshnessBadge(
                id=workflow,
                label=labels.get(workflow, workflow),
                as_of=as_of,
                state=state,
            )
        )
    return tuple(badges)


def _matrix_groups(
    matrix: Mapping[str, object],
) -> tuple[MatrixGroupView, ...]:
    raw_groups = matrix.get("groups")
    groups = raw_groups if isinstance(raw_groups, list) else []
    result: list[MatrixGroupView] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        raw_cards = group.get("cards")
        cards = raw_cards if isinstance(raw_cards, list) else []
        result.append(
            MatrixGroupView(
                id=str(group.get("id") or ""),
                label=str(group.get("label") or ""),
                cards=tuple(
                    MatrixCardView(
                        id=str(card.get("id") or ""),
                        label=str(card.get("label") or ""),
                        state_label=str(card.get("state_label") or "不可用"),
                        day_change=number(card.get("day_change")),
                        as_of=str(card.get("as_of") or "") or None,
                        freshness=str(card.get("freshness") or "unavailable"),
                        source=str(card.get("source") or "") or None,
                        authority=str(
                            card.get("authority") or "diagnostic_only"
                        ),
                        gap=(
                            plain_gap(card.get("gap"))
                            if card.get("gap")
                            else None
                        ),
                        points=tuple(
                            (
                                str(point.get("date") or ""),
                                float(point["close"]),
                            )
                            for point in (
                                card.get("points")
                                if isinstance(card.get("points"), list)
                                else []
                            )
                            if isinstance(point, dict)
                            and number(point.get("close")) is not None
                        ),
                    )
                    for card in cards
                    if isinstance(card, dict)
                ),
            )
        )
    return tuple(result)


def _plain_gaps(
    payload: Mapping[str, object],
    decision: Mapping[str, object],
) -> tuple[str, ...]:
    values: list[object] = []
    for source in (payload.get("data_gaps"), decision.get("data_gaps")):
        if isinstance(source, list):
            values.extend(source)
    return tuple(dict.fromkeys(plain_gap(value) for value in values))


def _research_sections(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    sections = payload.get("sections")
    rows = sections if isinstance(sections, list) else []
    markers = ("公告", "研究", "研报", "假设", "同行", "AI", "产业")
    return tuple(
        item
        for item in rows
        if isinstance(item, dict)
        and any(marker in str(item.get("title") or "") for marker in markers)
    )


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime(1970, 1, 1)
