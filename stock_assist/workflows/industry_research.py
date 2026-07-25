"""Industry research and candidate pool workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from stock_assist.paths import CONFIG_DIR
from stock_assist.reports import bullet


DEFAULT_INDUSTRY_PATH = CONFIG_DIR / "industries.json"


@dataclass(frozen=True)
class IndustryCandidate:
    code: str
    name: str
    role: str
    reason: str
    watch_items: list[str]


def build_industry_pool_report(industry: str, config_path: Path = DEFAULT_INDUSTRY_PATH) -> str:
    payload = _load_industries(config_path)
    item = payload.get(industry)
    gaps: list[str] = []
    if item is None:
        gaps.append(f"未配置产业：{industry}；请在 {config_path} 增加研究条目")
        item = {}

    candidates = [
        IndustryCandidate(
            code=str(candidate.get("code", "")),
            name=str(candidate.get("name", "")),
            role=str(candidate.get("role", "")),
            reason=str(candidate.get("reason", "")),
            watch_items=[str(value) for value in candidate.get("watch_items", [])],
        )
        for candidate in item.get("candidates", [])
    ]
    if not candidates:
        gaps.append("暂无候选股票池；先用研究员假设手工录入，再接入数据筛选。")

    lines = [
        f"# 产业研究股票池：{industry}",
        "",
        "## 研究框架",
        bullet(
            [
                f"产业位置：{item.get('chain_position', '未填写')}",
                f"核心变量：{item.get('key_variables', '未填写')}",
                f"景气验证：{item.get('validation', '未填写')}",
                f"主要风险：{item.get('risks', '未填写')}",
            ]
        ),
        "",
        "## 候选股票池",
    ]
    if candidates:
        for candidate in candidates:
            lines.extend(
                [
                    f"### {candidate.name}（{candidate.code}）",
                    f"- 产业角色：{candidate.role or '未填写'}",
                    f"- 入池理由：{candidate.reason or '未填写'}",
                    f"- 跟踪事项：{'; '.join(candidate.watch_items) if candidate.watch_items else '未填写'}",
                ]
            )
    else:
        lines.append("- 暂无。")

    lines.extend(
        [
            "",
            "## 数据缺口",
            bullet(gaps),
            "",
            "## 下一步",
            "- 为该产业补齐龙头、弹性、卖铲人、上游约束、下游应用五类候选。",
            "- 后续接入财务、估值、技术面、公告和订单数据，自动淘汰证据不足的标的。",
        ]
    )
    return "\n".join(lines)


def _load_industries(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
