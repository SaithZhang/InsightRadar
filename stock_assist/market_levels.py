"""Deterministic multi-timeframe market structure and level analysis."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from statistics import mean
from statistics import pstdev

from stock_assist.data_sources.eastmoney_klines import Candle


@dataclass(frozen=True)
class Pivot:
    index: int
    kind: str
    price: float


@dataclass(frozen=True)
class LevelZone:
    lower: float
    upper: float
    midpoint: float
    evidence: tuple[str, ...]
    strength: int


@dataclass(frozen=True)
class TimeframeAnalysis:
    timeframe: str
    label: str
    as_of: str
    bars: int
    latest: float
    latest_bar_low: float
    latest_bar_high: float
    change_pct: float | None
    phase: str
    macd_state: str
    divergence: str
    stroke_direction: str
    center: dict[str, float | str] | None
    support_zones: tuple[LevelZone, ...]
    resistance_zones: tuple[LevelZone, ...]
    response: tuple[str, ...]
    data_note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


TIMEFRAME_LABELS = {
    "month": "月线",
    "week": "周线",
    "day": "日线",
    "60m": "60分钟",
    "15m": "15分钟",
    "3m": "3分钟",
}


def analyze_timeframe(timeframe: str, candles: list[Candle], data_note: str = "") -> TimeframeAnalysis:
    if len(candles) < 20:
        raise ValueError(f"{timeframe} requires at least 20 bars, got {len(candles)}")
    closes = [item.close for item in candles]
    highs = [item.high for item in candles]
    lows = [item.low for item in candles]
    latest = closes[-1]
    previous = closes[-2] if len(closes) > 1 else None
    change_pct = ((latest / previous) - 1) * 100 if previous and previous > 0 else None
    atr = _atr(candles, 14) or latest * 0.01
    macd_line, signal_line, histogram = _macd(closes)
    pivots = _pivots(candles)
    strokes = _alternating_pivots(pivots)
    center = _latest_center(strokes)
    support = _level_zones(candles, pivots, center, atr, side="support")
    resistance = _level_zones(candles, pivots, center, atr, side="resistance")
    ma20 = _sma(closes, 20)
    phase = _phase(latest, ma20, macd_line[-1], signal_line[-1], histogram[-1])
    divergence = _divergence(pivots, closes, histogram)
    stroke_direction = _stroke_direction(strokes, latest)
    center_payload = _center_payload(center, latest)
    response = _response_lines(latest, support, resistance, center_payload)
    macd_state = _macd_state(macd_line, signal_line, histogram)
    return TimeframeAnalysis(
        timeframe=timeframe,
        label=TIMEFRAME_LABELS.get(timeframe, timeframe),
        as_of=candles[-1].time.strftime("%Y-%m-%d %H:%M" if candles[-1].time.hour else "%Y-%m-%d"),
        bars=len(candles),
        latest=latest,
        latest_bar_low=lows[-1],
        latest_bar_high=highs[-1],
        change_pct=change_pct,
        phase=phase,
        macd_state=macd_state,
        divergence=divergence,
        stroke_direction=stroke_direction,
        center=center_payload,
        support_zones=tuple(support),
        resistance_zones=tuple(resistance),
        response=tuple(response),
        data_note=data_note,
    )


def synthesize_market_view(items: list[TimeframeAnalysis]) -> dict[str, object]:
    valid = [item for item in items if item.support_zones]
    if not valid:
        return {"verdict": "点位证据不足", "tone": "warn", "primary_zone": None, "conditions": []}
    intraday = next((item for item in valid if item.timeframe == "60m"), valid[-1])
    daily = next((item for item in valid if item.timeframe == "day"), valid[0])
    primary = intraday.support_zones[0]
    confluence = _intraday_confluence(items, primary)
    weak_count = sum(1 for item in items if "下" in item.stroke_direction or "弱" in item.phase)
    divergence_count = sum(1 for item in items if item.divergence != "未识别到明确背驰")
    if weak_count >= 3 and divergence_count == 0:
        verdict, tone = "下跌结构未确认结束", "risk"
    elif weak_count >= 2:
        verdict, tone = "弱势中的支撑试探", "warn"
    else:
        verdict, tone = "结构修复观察期", "ok"
    conditions = [
        f"支撑预案：{confluence['lower']:.2f}-{confluence['upper']:.2f} 不破，并出现3/15分钟止跌，按日内反弹处理。",
        f"失效预案：15分钟有效收在 {confluence['lower']:.2f} 下方且不能快速收回，上午低点失效。",
    ]
    confirmation = _confirmation_zone(items)
    if confirmation:
        conditions.append(f"确认预案：站稳 {confirmation['lower']:.2f}-{confirmation['upper']:.2f}，才把反弹级别上调。")
    next_support = _higher_timeframe_support(items)
    return {
        "verdict": verdict,
        "tone": tone,
        "primary_zone": asdict(primary),
        "confluence_zone": confluence,
        "observed_intraday_low": daily.latest_bar_low,
        "confirmation_zone": confirmation,
        "next_support_zone": next_support,
        "reference_klines": [
            {"timeframe": item.label, "as_of": item.as_of, "signal": _reference_signal(item)}
            for item in items
            if item.timeframe in {"week", "day", "60m", "15m", "3m"}
        ],
        "win_rate_status": "未回测，不声称统计高胜率；当前为多周期最高共振区。",
        "weak_timeframes": weak_count,
        "divergence_timeframes": divergence_count,
        "conditions": conditions,
    }


def _intraday_confluence(items: list[TimeframeAnalysis], fallback: LevelZone) -> dict[str, object]:
    selected = [
        item.support_zones[0]
        for item in items
        if item.timeframe in {"60m", "15m", "3m"} and item.support_zones
    ]
    if not selected:
        selected = [fallback]
    lower = max(item.lower for item in selected)
    upper = min(item.upper for item in selected)
    if lower > upper:
        lower = min(item.lower for item in selected)
        upper = max(item.upper for item in selected)
    return {
        "lower": lower,
        "upper": upper,
        "midpoint": (lower + upper) / 2,
        "timeframes": [item.label for item in items if item.timeframe in {"60m", "15m", "3m"} and item.support_zones],
    }


def _confirmation_zone(items: list[TimeframeAnalysis]) -> dict[str, object] | None:
    selected = [
        item.resistance_zones[0]
        for item in items
        if item.timeframe in {"15m", "3m"} and item.resistance_zones
    ]
    if not selected:
        return None
    lower = max(item.lower for item in selected)
    upper = min(item.upper for item in selected)
    if lower > upper:
        lower = min(item.lower for item in selected)
        upper = max(item.upper for item in selected)
    return {"lower": lower, "upper": upper, "timeframes": ["3分钟", "15分钟"]}


def _higher_timeframe_support(items: list[TimeframeAnalysis]) -> dict[str, object] | None:
    selected = [
        item.support_zones[0]
        for item in items
        if item.timeframe in {"month", "week"} and item.support_zones
    ]
    if not selected:
        return None
    lower = max(item.lower for item in selected)
    upper = min(item.upper for item in selected)
    if lower > upper:
        lower = min(item.lower for item in selected)
        upper = max(item.upper for item in selected)
    return {"lower": lower, "upper": upper, "focus": (lower + upper) / 2, "timeframes": ["月线", "周线"]}


def _reference_signal(item: TimeframeAnalysis) -> str:
    zone = item.support_zones[0] if item.support_zones else None
    zone_text = f"支撑 {zone.lower:.0f}-{zone.upper:.0f}" if zone else "支撑证据不足"
    return f"{zone_text}；{item.stroke_direction}；{item.divergence}"


def _pivots(candles: list[Candle], window: int = 2) -> list[Pivot]:
    result: list[Pivot] = []
    for index in range(window, len(candles) - window):
        group = candles[index - window : index + window + 1]
        current = candles[index]
        if current.high >= max(item.high for item in group):
            result.append(Pivot(index, "high", current.high))
        if current.low <= min(item.low for item in group):
            result.append(Pivot(index, "low", current.low))
    return result


def _alternating_pivots(pivots: list[Pivot]) -> list[Pivot]:
    result: list[Pivot] = []
    for pivot in sorted(pivots, key=lambda item: (item.index, item.kind)):
        if not result:
            result.append(pivot)
            continue
        previous = result[-1]
        if pivot.index == previous.index:
            continue
        if pivot.kind == previous.kind:
            if (pivot.kind == "high" and pivot.price >= previous.price) or (
                pivot.kind == "low" and pivot.price <= previous.price
            ):
                result[-1] = pivot
            continue
        result.append(pivot)
    return result


def _latest_center(strokes: list[Pivot]) -> tuple[float, float] | None:
    if len(strokes) < 4:
        return None
    for end in range(len(strokes), 3, -1):
        segments = []
        for left, right in zip(strokes[end - 4 : end - 1], strokes[end - 3 : end]):
            segments.append((min(left.price, right.price), max(left.price, right.price)))
        lower = max(item[0] for item in segments)
        upper = min(item[1] for item in segments)
        if lower <= upper:
            return lower, upper
    return None


def _level_zones(
    candles: list[Candle],
    pivots: list[Pivot],
    center: tuple[float, float] | None,
    atr: float,
    side: str,
) -> list[LevelZone]:
    latest = candles[-1].close
    closes = [item.close for item in candles]
    candidates: list[tuple[float, str]] = []
    pivot_kind = "low" if side == "support" else "high"
    for pivot in [item for item in pivots if item.kind == pivot_kind][-8:]:
        candidates.append((pivot.price, f"分型{('低' if side == 'support' else '高')}点"))
    for period in (5, 10, 20, 60):
        value = _sma(closes, period)
        if value is not None:
            candidates.append((value, f"MA{period}"))
    if len(closes) >= 20:
        basis = mean(closes[-20:])
        deviation = pstdev(closes[-20:])
        candidates.append((basis - 2 * deviation if side == "support" else basis + 2 * deviation, f"BOLL{'下' if side == 'support' else '上'}轨"))
    for period in (20, 60, 120):
        window = candles[-min(period, len(candles)) :]
        value = min(item.low for item in window) if side == "support" else max(item.high for item in window)
        candidates.append((value, f"近{period}根{'低' if side == 'support' else '高'}点"))
    candidates.extend(_fib_candidates(candles, side))
    if center:
        candidates.append((center[0] if side == "support" else center[1], "中枢边界"))
    tolerance = max(atr * 0.55, latest * 0.0035)
    if side == "support":
        candidates = [item for item in candidates if item[0] <= latest + tolerance]
    else:
        candidates = [item for item in candidates if item[0] >= latest - tolerance]
    clusters: list[list[tuple[float, str]]] = []
    for candidate in sorted(candidates, key=lambda item: item[0]):
        if not isfinite(candidate[0]) or candidate[0] <= 0:
            continue
        if clusters and abs(candidate[0] - mean(item[0] for item in clusters[-1])) <= tolerance:
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])
    zones = []
    for cluster in clusters:
        evidence = tuple(dict.fromkeys(item[1] for item in cluster))
        families = {_evidence_family(item) for item in evidence}
        midpoint = mean(item[0] for item in cluster)
        if len(families) < 2:
            continue
        if (side == "support" and midpoint > latest) or (side == "resistance" and midpoint < latest):
            continue
        prices = [item[0] for item in cluster]
        zones.append(
            LevelZone(
                lower=max(0.01, min(prices) - tolerance * 0.2),
                upper=max(prices) + tolerance * 0.2,
                midpoint=midpoint,
                evidence=evidence,
                strength=len(families),
            )
        )
    zones.sort(key=lambda item: abs(item.midpoint - latest))
    return zones[:3]


def _evidence_family(label: str) -> str:
    if label.startswith("分型"):
        return "pivot"
    if label.startswith("MA"):
        return "ma"
    if label.startswith("BOLL"):
        return "volatility"
    if label.startswith("近"):
        return "rolling_extreme"
    if label.startswith("波段"):
        return "fibonacci"
    if label.startswith("中枢"):
        return "chan_center"
    return label


def _fib_candidates(candles: list[Candle], side: str) -> list[tuple[float, str]]:
    window = candles[-min(120, len(candles)) :]
    high_index = max(range(len(window)), key=lambda index: window[index].high)
    low_before = min(window[: high_index + 1], key=lambda item: item.low)
    high = window[high_index].high
    span = high - low_before.low
    if span <= 0:
        return []
    ratios = (0.382, 0.5, 0.618)
    if side == "support":
        return [(high - span * ratio, f"波段回撤{ratio:.3f}") for ratio in ratios]
    return [(low_before.low + span * ratio, f"波段反抽{ratio:.3f}") for ratio in ratios]


def _macd(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    line = [left - right for left, right in zip(fast, slow)]
    signal = _ema(line, 9)
    histogram = [(left - right) * 2 for left, right in zip(line, signal)]
    return line, signal, histogram


def _ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return mean(values[-period:])


def _atr(candles: list[Candle], period: int) -> float | None:
    if len(candles) < 2:
        return None
    ranges = []
    for previous, current in zip(candles[:-1], candles[1:]):
        ranges.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    return mean(ranges[-min(period, len(ranges)) :])


def _divergence(pivots: list[Pivot], closes: list[float], histogram: list[float]) -> str:
    lows = [item for item in pivots if item.kind == "low"]
    highs = [item for item in pivots if item.kind == "high"]
    if len(lows) >= 2:
        first, second = lows[-2], lows[-1]
        if second.price < first.price and histogram[second.index] > histogram[first.index]:
            return "底背驰候选（价格新低、MACD柱未新低）"
    if len(highs) >= 2:
        first, second = highs[-2], highs[-1]
        if second.price > first.price and histogram[second.index] < histogram[first.index]:
            return "顶背驰候选（价格新高、MACD柱未新高）"
    return "未识别到明确背驰"


def _phase(latest: float, ma20: float | None, macd: float, signal: float, histogram: float) -> str:
    if ma20 is None:
        return "样本不足"
    if latest >= ma20 and macd >= signal and histogram >= 0:
        return "结构偏强"
    if latest < ma20 and macd < signal and histogram < 0:
        return "结构偏弱"
    return "震荡/修复"


def _macd_state(line: list[float], signal: list[float], histogram: list[float]) -> str:
    direction = "扩张" if abs(histogram[-1]) > abs(histogram[-2]) else "收敛"
    axis = "零轴上" if line[-1] >= 0 else "零轴下"
    cross = "DIF在DEA上" if line[-1] >= signal[-1] else "DIF在DEA下"
    color = "红柱" if histogram[-1] >= 0 else "绿柱"
    return f"{axis}，{cross}，{color}{direction}"


def _stroke_direction(strokes: list[Pivot], latest: float) -> str:
    if not strokes:
        return "笔结构不足"
    last = strokes[-1]
    if last.kind == "high" and latest < last.price:
        return "向下一笔延续中"
    if last.kind == "low" and latest > last.price:
        return "向上一笔修复中"
    return "笔方向待确认"


def _center_payload(center: tuple[float, float] | None, latest: float) -> dict[str, float | str] | None:
    if not center:
        return None
    lower, upper = center
    relation = "中枢内" if lower <= latest <= upper else ("中枢上方" if latest > upper else "中枢下方")
    return {"lower": lower, "upper": upper, "relation": relation}


def _response_lines(
    latest: float,
    support: list[LevelZone],
    resistance: list[LevelZone],
    center: dict[str, float | str] | None,
) -> list[str]:
    lines = []
    if support:
        zone = support[0]
        lines.append(f"若 {zone.lower:.2f}-{zone.upper:.2f} 出现小级别底分型/背驰，只按支撑试探处理。")
        lines.append(f"若连续收在 {zone.lower:.2f} 下方，当前支撑假设失效，转看下一聚类区。")
    else:
        lines.append("附近没有形成两类以上证据重合的支撑区，不给出伪精确低点。")
    if resistance:
        zone = resistance[0]
        lines.append(f"若重新站稳 {zone.lower:.2f}-{zone.upper:.2f} 且回踩不破，才上调反弹级别。")
    if center:
        lines.append(f"当前位于{center['relation']}；中枢边界 {float(center['lower']):.2f}-{float(center['upper']):.2f}。")
    return lines
