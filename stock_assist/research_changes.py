"""Validate a financial evidence packet and derive a bounded review cue."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
METRICS = {"net_profit": "归母净利润", "operating_cash_flow": "经营活动现金流净额"}
STATUS_LABELS = {
    "needs_review": "理由需要复核",
    "no_material_change": "无实质变化（本次核验范围）",
    "insufficient_coverage": "覆盖不足",
}
MODES = {
    "live_review": "实际材料核验",
    "historical_validation": "历史材料验证",
    "missing_source_validation": "缺源场景验证",
}
RULE_TEXT = (
    "仅检查所给同期间财报：经营现金流为负、同比下降，或归母净利润同比下降时提示复核。"
    "该工程复核规则由程序计算；结果仅覆盖这两个指标，完整投资理由仍需人工判断。"
)


def _object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name}须为对象")
    return value


def _text(value: object, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name}须为非空文字，长度上限{maximum}")
    return value.strip()


def _date(value: object, name: str) -> date:
    text = _text(value, name, 10)
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValueError(f"{name}须为YYYY-MM-DD")
    return date.fromisoformat(text)


def _instant(value: object, name: str) -> datetime:
    text = _text(value, name, 40)
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"{name}须包含时区")
    return result.astimezone(TZ)


def _url(value: object, name: str) -> str:
    text = _text(value, name)
    parsed = urlparse(text)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{name}须为不含凭据的http或https链接")
    return text


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name}须为有限数值或十进制字符串")
    text = str(value)
    if len(text) > 60:
        raise ValueError(f"{name}数值过长")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{name}数值无效") from error
    if not result.is_finite() or result.copy_abs() > Decimal("1e18"):
        raise ValueError(f"{name}须为有限数值且绝对值不超过1e18")
    if result.as_tuple().exponent < -8:
        raise ValueError(f"{name}最多保留8位小数")
    return result


def _amount(value: Decimal) -> str:
    return format(value, "f")


def _compact(value: str) -> str:
    return re.sub(r"[\s,，]", "", value).replace("−", "-").replace("－", "-")


def _citation(row: dict, sources: dict[str, dict]) -> tuple[str, str]:
    source_id = _text(row.get("source_id"), "source_id", 80)
    if source_id not in sources:
        raise ValueError("引用source_id不存在")
    quote = _text(row.get("quote"), "quote", 5000)
    if _compact(quote) not in _compact(sources[source_id]["text"]):
        raise ValueError("引用摘句与来源原文不匹配")
    return source_id, quote


def _period(value: object, name: str) -> tuple[date, date]:
    text = _text(value, name, 21)
    parts = text.split("/")
    if len(parts) != 2:
        raise ValueError(f"{name}须为开始日/结束日")
    start, end = (_date(part, name) for part in parts)
    if end < start or (end - start).days > 365:
        raise ValueError(f"{name}期间顺序或长度无效")
    return start, end


def _metric(value: object, name: str, sources: dict[str, dict], cutoff: date) -> dict:
    row = _object(value, name)
    current = _decimal(row.get("current"), name + ".current")
    previous = _decimal(row.get("previous"), name + ".previous")
    if row.get("unit") != "元":
        raise ValueError("财务指标单位须统一为元")
    period = _period(row.get("period"), name + ".period")
    prior = _period(row.get("comparison_period"), name + ".comparison_period")
    if any((a.month, a.day) != (b.month, b.day) or a.year != b.year + 1
           for a, b in zip(period, prior)):
        raise ValueError("同比期间必须为上年相同起止月日")
    if period[1] > cutoff:
        raise ValueError("财务期间晚于核验截止时间")
    source_id, quote = _citation(row, sources)
    if _date(sources[source_id]["published_at"], "published_at") < period[1]:
        raise ValueError("财报发布时间早于财务期间结束")
    numeric_quote = quote.replace(",", "").replace("，", "").replace("−", "-").replace("－", "-")
    quoted_numbers = {
        Decimal(token) for token in re.findall(r"(?<![\d.])[-+]?[0-9]+(?:\.[0-9]+)?(?![\d.])", numeric_quote)
    }
    if current not in quoted_numbers or previous not in quoted_numbers:
        raise ValueError("本期与上期金额必须完整出现在引用摘句中")
    yoy = float((current / previous - 1) * 100) if previous > 0 else None
    return {
        "current": _amount(current), "previous": _amount(previous), "unit": "元",
        "period": "/".join(map(str, period)), "comparison_period": "/".join(map(str, prior)),
        "source_id": source_id, "quote": quote, "yoy_pct": round(yoy, 4) if yoy is not None else None,
        "delta": _amount(current - previous),
    }


def evaluate_change(payload: dict, *, current_time: datetime | None = None) -> dict:
    """Return a validated assessment without fetching sources or mutating input."""
    payload = _object(payload, "变化检查")
    if type(payload.get("schema")) is not int or payload["schema"] != 1:
        raise ValueError("变化检查schema须为1")
    symbol = _text(payload.get("symbol"), "symbol", 6)
    if not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("symbol须为6位证券代码")
    current_time = current_time or datetime.now(TZ)
    if not isinstance(current_time, datetime) or current_time.tzinfo is None:
        raise ValueError("current_time须为含时区的datetime")
    cutoff = _instant(payload.get("as_of"), "as_of")
    if cutoff > current_time:
        raise ValueError("核验截止时间不能晚于当前时间")
    mode = payload.get("mode", "live_review")
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("变化检查mode无效")
    normalized = {"schema": 1, "symbol": symbol, "as_of": cutoff.isoformat(), "mode": mode,
                  "scope": _text(payload.get("scope"), "scope")}
    for name in ("thesis", "holding"):
        row = _object(payload.get(name), name)
        stamp = _date(row.get("as_of"), name + ".as_of")
        if stamp > cutoff.date():
            raise ValueError(f"{name}日期晚于核验截止时间")
        normalized[name] = {"as_of": str(stamp), "url": _url(row.get("url"), name + ".url")}
        if name == "thesis":
            normalized[name]["text"] = _text(row.get("text"), "thesis.text")
    coverage = _object(payload.get("coverage"), "coverage")
    if not isinstance(coverage.get("status"), str) or coverage["status"] not in {"complete", "partial", "unavailable"}:
        raise ValueError("coverage.status无效")
    checked = _instant(coverage.get("checked_at"), "coverage.checked_at")
    if checked > cutoff:
        raise ValueError("覆盖检查时间晚于核验截止时间")
    normalized["coverage"] = {"status": coverage["status"], "checked_at": checked.isoformat(),
                              "note": _text(coverage.get("note"), "coverage.note")}
    source_rows = payload.get("sources", [])
    if not isinstance(source_rows, list) or len(source_rows) > 10:
        raise ValueError("sources须为最多10条来源的列表")
    sources = {}
    for source in source_rows:
        row = _object(source, "source")
        ident = _text(row.get("id"), "source.id", 80)
        if ident in sources:
            raise ValueError("source.id重复")
        published = _date(row.get("published_at"), "source.published_at")
        if published > cutoff.date():
            raise ValueError("来源发布时间晚于核验截止时间")
        page = row.get("page", "")
        if type(page) is int and page > 0:
            page = str(page)
        if not isinstance(page, str) or len(page) > 100:
            raise ValueError("source.page须为页码文字或正整数")
        sources[ident] = {"id": ident, "title": _text(row.get("title"), "source.title", 300),
                          "url": _url(row.get("url"), "source.url"), "published_at": str(published),
                          "text": _text(row.get("text"), "source.text", 50000), "page": page}
    normalized["sources"] = list(sources.values())
    metric_rows = _object(payload.get("metrics", {}), "metrics")
    if set(metric_rows) - set(METRICS):
        raise ValueError("存在不支持的财务指标")
    metrics = {name: _metric(value, name, sources, cutoff.date()) for name, value in metric_rows.items()}
    if len({(row["period"], row["comparison_period"]) for row in metrics.values()}) > 1:
        raise ValueError("净利润与经营现金流须采用相同财务期间")
    normalized["metrics"] = metrics
    explanation = payload.get("explanation")
    if explanation is not None:
        explanation = _object(explanation, "explanation")
        source_id, quote = _citation(explanation, sources)
        normalized["explanation"] = {"text": _text(explanation.get("text"), "explanation.text"),
                                     "source_id": source_id, "quote": quote}
    gaps = []
    if coverage["status"] != "complete":
        gaps.append("声明的来源范围尚未完整核验")
    if cutoff - checked > timedelta(days=1):
        gaps.append("覆盖检查距本次截止时间超过一天，需重新确认")
    if not sources:
        gaps.append("缺少可追溯来源")
    gaps.extend("缺少" + label + "的可核对数据" for name, label in METRICS.items() if name not in metrics)
    if mode == "missing_source_validation" and not gaps:
        raise ValueError("缺源验证须提供实际覆盖缺口")
    basis, concerns = [], []
    for name, row in metrics.items():
        current, previous = Decimal(row["current"]), Decimal(row["previous"])
        direction = "下降" if current < previous else "上升" if current > previous else "持平"
        basis.append(f"{METRICS[name]}本期{row['current']}元，上年同期{row['previous']}元，同比{direction}")
        if current < previous:
            concerns.append(METRICS[name] + "同比下降")
        if name == "operating_cash_flow" and current < 0:
            concerns.append("经营活动现金流净额为负")
    status = "insufficient_coverage" if gaps else "needs_review" if concerns else "no_material_change"
    summary = "；".join(gaps) if gaps else "；".join(concerns) if concerns else "所给同期净利润与经营现金流未触发本次复核规则"
    next_check = "补齐列明来源与期间后重新核验" if gaps else "核对回款、应收及季节性，人工复核原研究理由" if concerns else "继续跟踪下一期披露及原理由的其他条件"
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                                            allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    return {**normalized, "status": status, "status_label": STATUS_LABELS[status], "summary": summary,
            "basis": basis, "gaps": gaps, "next_check": next_check, "mode_label": MODES[mode],
            "rule_text": RULE_TEXT, "rule_origin": "engineering_review_rule",
            "trade_authority": "none", "fingerprint": fingerprint}
