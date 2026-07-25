"""Evidence-bound AI infrastructure capital-expenditure monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import statistics
from typing import Iterable


CAPEX_COMPONENT_WEIGHTS = {
    "guidance_revision": 0.35,
    "expansion": 0.30,
    "breadth": 0.20,
    "ai_dc_linkage": 0.15,
}

OPTICAL_CATEGORY_WEIGHTS = {
    "network_revenue": 0.35,
    "network_allocation": 0.25,
    "module_demand": 0.20,
    "supplier_fundamentals": 0.20,
}


@dataclass(frozen=True)
class MetricResult:
    key: str
    label: str
    score: float | None
    coverage: float
    state: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1) if self.score is not None else None,
            "coverage": round(self.coverage, 4),
            "state": self.state,
            "detail": self.detail,
        }


def score_ai_capex_watch(config: dict[str, object], as_of: date) -> dict[str, object]:
    """Score capex momentum and optical transmission without filling disclosure gaps."""

    max_age_days = _positive_int(config.get("max_age_days"), 180)
    companies = _valid_records(config.get("companies"), as_of, max_age_days)
    optical = _valid_records(config.get("optical_evidence"), as_of, max_age_days)
    supplier_checks = _as_records(config.get("supplier_checks"))
    expected_companies = max(1, len(_as_records(config.get("companies"))))

    revisions = [
        _guidance_revision(item)
        for item in companies
        if _guidance_revision(item) is not None
    ]
    expansions = [
        _expansion_rate(item)
        for item in companies
        if _expansion_rate(item) is not None
    ]
    directions = [str(item.get("guidance_direction", "")).lower() for item in companies]
    directions = [item for item in directions if item in {"up", "flat", "down"}]
    linked = [item for item in companies if str(item.get("ai_dc_link", "")).lower() == "explicit"]

    capex_components = [
        _component(
            "guidance_revision",
            "指引修正",
            _symmetric_score(_median(revisions), scale=0.20),
            len(revisions) / expected_companies,
            _revision_detail(revisions),
        ),
        _component(
            "expansion",
            "支出扩张",
            _symmetric_score(_median(expansions), scale=1.00),
            len(expansions) / expected_companies,
            _expansion_detail(expansions),
        ),
        _component(
            "breadth",
            "上调广度",
            _breadth_score(directions),
            len(directions) / expected_companies,
            _breadth_detail(directions),
        ),
        _component(
            "ai_dc_linkage",
            "AI/数据中心关联",
            100.0 * len(linked) / len(companies) if companies else None,
            len(companies) / expected_companies,
            f"{len(linked)}/{len(companies)}家有效披露明确关联AI或数据中心" if companies else "没有有效公司披露",
        ),
    ]
    capex_raw_score = _weighted_score(capex_components, CAPEX_COMPONENT_WEIGHTS)
    capex_coverage = sum(
        CAPEX_COMPONENT_WEIGHTS[item.key] * item.coverage for item in capex_components
    )
    capex_score = _confidence_adjusted(capex_raw_score, capex_coverage)
    capex_metric = MetricResult(
        key="capex_momentum",
        label="云厂商CapEx动量",
        score=capex_score,
        coverage=capex_coverage,
        state=_score_state(capex_score, capex_coverage),
        detail=_capex_summary(capex_raw_score, capex_coverage),
    )

    optical_components = []
    for category, weight in OPTICAL_CATEGORY_WEIGHTS.items():
        observations = [item for item in optical if str(item.get("category")) == category]
        values = [_evidence_score(item) for item in observations]
        values = [value for value in values if value is not None]
        optical_components.append(
            _component(
                category,
                _optical_label(category),
                _median(values),
                min(1.0, len(values)) if observations else 0.0,
                _optical_detail(observations),
            )
        )
    optical_raw_score = _weighted_score(optical_components, OPTICAL_CATEGORY_WEIGHTS)
    optical_coverage = sum(
        OPTICAL_CATEGORY_WEIGHTS[item.key] * item.coverage for item in optical_components
    )
    optical_score = _confidence_adjusted(optical_raw_score, optical_coverage)
    optical_metric = MetricResult(
        key="optical_transmission",
        label="光模块需求传导",
        score=optical_score,
        coverage=optical_coverage,
        state=_score_state(optical_score, optical_coverage),
        detail=_optical_summary(optical_raw_score, optical_coverage),
    )

    completed_supplier_checks = [
        item for item in supplier_checks if str(item.get("status", "")).lower() == "official"
    ]
    supplier_metric = MetricResult(
        key="supplier_realization",
        label="中际业绩兑现",
        score=None,
        coverage=len(completed_supplier_checks) / max(1, len(supplier_checks)),
        state="pending" if not completed_supplier_checks else "partial",
        detail=(
            "半年报/官方调研验证尚未闭环"
            if not completed_supplier_checks
            else f"{len(completed_supplier_checks)}/{len(supplier_checks)}项已有官方验证"
        ),
    )

    data_gaps = _data_gaps(config, companies, optical, supplier_checks, as_of, max_age_days)
    actions = _conditional_actions(capex_metric, optical_metric, supplier_metric)
    conclusion = _conclusion(capex_metric, optical_metric, supplier_metric)
    return {
        "as_of": as_of.isoformat(),
        "metrics": [capex_metric.to_dict(), optical_metric.to_dict(), supplier_metric.to_dict()],
        "capex_components": [item.to_dict() for item in capex_components],
        "optical_components": [item.to_dict() for item in optical_components],
        "companies": companies,
        "optical_evidence": optical,
        "supplier_checks": supplier_checks,
        "conclusion": conclusion,
        "actions": actions,
        "data_gaps": data_gaps,
    }


def _valid_records(value: object, as_of: date, max_age_days: int) -> list[dict[str, object]]:
    records = []
    for item in _as_records(value):
        if str(item.get("verification_status", "")).lower() != "official":
            continue
        observed_at = _optional_date(item.get("observed_at"))
        if observed_at is None or observed_at > as_of or (as_of - observed_at).days > max_age_days:
            continue
        records.append(item)
    return records


def _as_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _guidance_revision(item: dict[str, object]) -> float | None:
    current = _midpoint(item.get("guidance_low_billion_usd"), item.get("guidance_high_billion_usd"))
    previous = _midpoint(item.get("prior_guidance_low_billion_usd"), item.get("prior_guidance_high_billion_usd"))
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def _expansion_rate(item: dict[str, object]) -> float | None:
    current_guide = _midpoint(item.get("guidance_low_billion_usd"), item.get("guidance_high_billion_usd"))
    prior_actual = _number(item.get("prior_actual_capex_billion_usd"))
    if current_guide is not None and prior_actual not in (None, 0):
        return current_guide / prior_actual - 1
    actual = _number(item.get("actual_capex_billion_usd"))
    prior = _number(item.get("prior_actual_capex_billion_usd"))
    if actual is not None and prior not in (None, 0):
        return actual / prior - 1
    return None


def _evidence_score(item: dict[str, object]) -> float | None:
    direction = str(item.get("direction", "")).lower()
    if direction not in {"positive", "neutral", "negative"}:
        return None
    strength = _number(item.get("strength"))
    strength = 1.0 if strength is None else max(0.0, min(1.0, strength))
    sign = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}[direction]
    return max(0.0, min(100.0, 50.0 + 50.0 * sign * strength))


def _component(key: str, label: str, score: float | None, coverage: float, detail: str) -> MetricResult:
    bounded_coverage = max(0.0, min(1.0, coverage))
    return MetricResult(
        key=key,
        label=label,
        score=score,
        coverage=bounded_coverage,
        state=_score_state(score, bounded_coverage),
        detail=detail,
    )


def _weighted_score(items: Iterable[MetricResult], weights: dict[str, float]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for item in items:
        if item.score is None or item.coverage <= 0:
            continue
        weight = weights[item.key]
        numerator += item.score * weight
        denominator += weight
    return numerator / denominator if denominator else None


def _symmetric_score(value: float | None, *, scale: float) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * value / scale))


def _confidence_adjusted(score: float | None, coverage: float) -> float | None:
    """Shrink sparse evidence toward neutral instead of presenting false precision."""

    if score is None:
        return None
    bounded = max(0.0, min(1.0, coverage))
    return 50.0 + (score - 50.0) * bounded


def _breadth_score(directions: list[str]) -> float | None:
    if not directions:
        return None
    values = {"up": 100.0, "flat": 50.0, "down": 0.0}
    return statistics.fmean(values[item] for item in directions)


def _score_state(score: float | None, coverage: float) -> str:
    if score is None or coverage < 0.35:
        return "insufficient"
    if score >= 65:
        return "positive" if coverage >= 0.75 else "positive_low_confidence"
    if score < 45:
        return "negative" if coverage >= 0.75 else "negative_low_confidence"
    return "neutral"


def _capex_summary(score: float | None, coverage: float) -> str:
    if score is None:
        return "没有足够的官方CapEx披露"
    tone = "扩张" if score >= 65 else "收缩" if score < 45 else "中性"
    return f"方向偏{tone}，证据覆盖{coverage:.0%}；不同公司口径不可直接汇总为一个美元总额"


def _optical_summary(score: float | None, coverage: float) -> str:
    if score is None:
        return "缺少网络和光模块传导证据"
    tone = "正向" if score >= 65 else "负向" if score < 45 else "中性"
    return f"当前传导证据偏{tone}，覆盖{coverage:.0%}；总CapEx不等于光模块订单"


def _conclusion(capex: MetricResult, optical: MetricResult, supplier: MetricResult) -> str:
    if capex.score is None:
        return "云厂商投入方向尚不能确认；不据此改变科技仓位。"
    if capex.score >= 65 and optical.score is not None and optical.score >= 65:
        if supplier.state == "pending":
            return "云厂商投入与网络传导偏强，但中际业绩兑现尚未闭环：产业逻辑获支持，不构成追涨依据。"
        return "CapEx、网络传导和供应商兑现形成正向证据链，仍需结合估值与价格结构决定仓位。"
    if capex.score >= 65:
        return "云厂商投入偏强，但网络/光模块传导不足；不能把总CapEx直接映射为中际利润。"
    if capex.score < 45:
        return "云厂商投入动量转弱，应降低远期景气假设权重并复核科技高β仓位。"
    return "CapEx方向中性，维持观察，等待下一轮官方指引和供应商财务验证。"


def _conditional_actions(capex: MetricResult, optical: MetricResult, supplier: MetricResult) -> list[str]:
    actions = ["本模块只调整产业论点置信度，不直接发出买卖或清仓指令。"]
    if capex.score is not None and capex.score >= 65:
        actions.append("CapEx动量偏强：保留AI基础设施景气假设，但禁止仅凭总支出上升追涨CPO。")
    elif capex.score is not None and capex.score < 45:
        actions.append("CapEx动量偏弱：停止上调远期利润假设，检查高β仓位是否超出风险预算。")
    if optical.coverage < 0.60:
        actions.append("光模块传导覆盖不足：等待网络收入、800G/1.6T订单或交付证据补齐。")
    if supplier.state == "pending":
        actions.append("等待中际半年报/官方调研验证毛利率、经营现金流、库存、应收和1.6T收入。")
    actions.append("若CapEx上调而供应商毛利率/现金流恶化，按价格竞争或份额兑现不足处理，不用景气叙事覆盖反证。")
    return actions


def _data_gaps(
    config: dict[str, object],
    companies: list[dict[str, object]],
    optical: list[dict[str, object]],
    supplier_checks: list[dict[str, object]],
    as_of: date,
    max_age_days: int,
) -> list[str]:
    gaps: list[str] = []
    all_companies = _as_records(config.get("companies"))
    if len(companies) < len(all_companies):
        gaps.append(f"{len(all_companies) - len(companies)}家公司披露未验证、已过期或晚于评分日，未参与评分。")
    missing_prior = sum(_guidance_revision(item) is None for item in companies)
    if missing_prior:
        gaps.append(f"{missing_prior}/{len(companies)}家公司缺少同口径前次CapEx指引，指引修正覆盖不完整。")
    missing_network = sum(_number(item.get("network_share")) is None for item in companies)
    if missing_network:
        gaps.append(f"{missing_network}/{len(companies)}家公司未披露纯网络设备占比；GPU、建筑和电力投入不能当作光模块需求。")
    present_categories = {str(item.get("category")) for item in optical}
    for category in OPTICAL_CATEGORY_WEIGHTS:
        if category not in present_categories:
            gaps.append(f"缺少{_optical_label(category)}的有效官方证据。")
    pending = [item for item in supplier_checks if str(item.get("status", "")).lower() != "official"]
    if pending:
        gaps.append(f"中际业绩兑现仍有{len(pending)}项待官方数据验证。")
    return gaps


def _revision_detail(values: list[float]) -> str:
    return "无同口径前次指引" if not values else f"可比公司指引修正中位数{_median(values):+.1%}"


def _expansion_detail(values: list[float]) -> str:
    return "无同口径同比支出" if not values else f"可比支出扩张中位数{_median(values):+.1%}"


def _breadth_detail(values: list[str]) -> str:
    if not values:
        return "没有方向性披露"
    return f"上调{values.count('up')}家、持平{values.count('flat')}家、下调{values.count('down')}家"


def _optical_detail(items: list[dict[str, object]]) -> str:
    if not items:
        return "暂无有效官方证据"
    return "；".join(str(item.get("detail") or item.get("metric_name") or item.get("key")) for item in items)


def _optical_label(category: str) -> str:
    return {
        "network_revenue": "网络设备收入",
        "network_allocation": "网络投入占比",
        "module_demand": "800G/1.6T需求",
        "supplier_fundamentals": "供应商财务兑现",
    }[category]


def _midpoint(low: object, high: object) -> float | None:
    low_number = _number(low)
    high_number = _number(high)
    if low_number is None and high_number is None:
        return None
    if low_number is None:
        return high_number
    if high_number is None:
        return low_number
    return (low_number + high_number) / 2


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
