"""Translate conditional trim ratios into safe A-share board-lot quantities."""

from __future__ import annotations

import math
import re
from typing import Iterable

from stock_assist.portfolio import Holding


def calculate_executable_trim(
    shares: float | None,
    available_shares: float | None,
    target_trim_ratio: float | None,
    *,
    lot_size: int = 100,
) -> dict[str, object]:
    ratio = float(target_trim_ratio) if isinstance(target_trim_ratio, (int, float)) else None
    raw = shares * ratio if shares is not None and ratio is not None else None
    result: dict[str, object] = {
        "target_trim_ratio": ratio,
        "raw_target_shares": round(raw, 4) if raw is not None else None,
        "executable_lot_shares": None,
        "available_shares": available_shares,
        "lot_constraint": f"A股默认{lot_size}股整数手；向下取整，不得超过目标比例或可卖数量。",
        "execution_readiness": "unavailable",
        "reason": "缺少持仓股数、可靠可卖数量或减仓比例。",
    }
    if shares is None or available_shares is None or ratio is None:
        return result
    if shares <= 0 or available_shares < 0 or not (0 < ratio <= 1):
        result["execution_readiness"] = "blocked"
        result["reason"] = "持仓股数、可卖数量或减仓比例不在有效范围。"
        return result
    if raw is None or raw < lot_size:
        result["executable_lot_shares"] = 0
        result["execution_readiness"] = "blocked"
        result["reason"] = f"当前持仓无法按{ratio:.0%}整手执行；需人工选择不执行或整仓处理，系统不会向上取整。"
        return result
    executable_cap = min(raw, available_shares)
    executable = math.floor((executable_cap + 1e-9) / lot_size) * lot_size
    result["executable_lot_shares"] = int(executable)
    if executable <= 0:
        result["execution_readiness"] = "blocked"
        result["reason"] = f"可靠可卖数量不足{lot_size}股，无法生成整数手委托建议。"
    elif executable < raw and available_shares < raw:
        result["execution_readiness"] = "ready_limited_by_available"
        result["reason"] = "整数手数量受可靠可卖股份限制，已向下取整。"
    else:
        result["execution_readiness"] = "ready"
        result["reason"] = "已按目标比例和可卖数量向下取整；仅为条件化委托建议，不自动下单。"
    return result


def build_holding_execution_plans(
    actions: list[dict[str, object]],
    holdings: Iterable[Holding],
    risk_budget: dict[str, object],
) -> list[dict[str, object]]:
    by_code = {holding.code: holding for holding in holdings}
    high_beta = _number(risk_budget.get("high_beta_exposure_pct"))
    over_cap = _number(risk_budget.get("high_beta_over_cap_pct"))
    portfolio_ratio = over_cap / high_beta if high_beta and over_cap and over_cap > 0 else None
    plans: list[dict[str, object]] = []
    for action in actions:
        code = str(action.get("code") or "")
        holding = by_code.get(code)
        if holding is None:
            continue
        ratio = portfolio_ratio or _ratio_from_action(action)
        plan = calculate_executable_trim(holding.shares, holding.available, ratio)
        plan.update(
            {
                "code": holding.code,
                "name": holding.name,
                "shares": holding.shares,
                "beta_classification": holding.beta_classification,
                "authority": "conditional_support_only_no_order_execution",
            }
        )
        plans.append(plan)
    return plans


def _ratio_from_action(action: dict[str, object]) -> float | None:
    text = " ".join(str(action.get(key) or "") for key in ("position_action", "downside_trigger", "action"))
    if any(token in text for token in ("1/4", "四分之一", "25%", "25％")):
        return 0.25
    match = re.search(r"(?:减|降低|下降).*?(\d+(?:\.\d+)?)\s*[%％]", text)
    if match:
        return float(match.group(1)) / 100.0
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
