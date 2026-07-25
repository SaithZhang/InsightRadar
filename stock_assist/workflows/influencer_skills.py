"""Influencer-view skill cards and observation workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stock_assist.paths import CONFIG_DIR, DATA_DIR
from stock_assist.reports import bullet


DEFAULT_PROFILES_PATH = CONFIG_DIR / "influencers.json"
DEFAULT_OBSERVATIONS_PATH = DATA_DIR / "influencer_observations.jsonl"


@dataclass(frozen=True)
class InfluencerObservation:
    id: str
    date: str
    author: str
    source: str
    source_url: str
    source_type: str
    summary: str
    direction: str = "neutral"
    confidence: str = "low"
    impact_horizon: str = "unknown"
    status: str = "unverified"
    symbols: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, item: dict[str, object]) -> "InfluencerObservation":
        return cls(
            id=str(item.get("id", "")),
            date=str(item.get("date", "未知日期")),
            author=str(item.get("author", "未知")),
            source=str(item.get("source", "未知来源")),
            source_url=str(item.get("source_url", "")),
            source_type=str(item.get("source_type", "unknown")),
            summary=str(item.get("summary", "")),
            direction=str(item.get("direction", "neutral")),
            confidence=str(item.get("confidence", "low")),
            impact_horizon=str(item.get("impact_horizon", "unknown")),
            status=str(item.get("status", "unverified")),
            symbols=[str(value) for value in item.get("symbols", [])],
            industries=[str(value) for value in item.get("industries", [])],
            themes=[str(value) for value in item.get("themes", [])],
            verification=[str(value) for value in item.get("verification", [])],
        )

    @property
    def has_target(self) -> bool:
        return bool(self.symbols or self.industries or self.themes)

    @property
    def source_label(self) -> str:
        labels = {
            "first_party": "一手来源",
            "secondary": "二手转述",
            "manual": "人工记录",
        }
        return labels.get(self.source_type, self.source_type)


def build_influencer_skills_report(
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    observations_path: Path = DEFAULT_OBSERVATIONS_PATH,
) -> str:
    profiles = _load_profiles(profiles_path)
    observations = _load_observations(observations_path)
    gaps: list[str] = []
    if not profiles:
        gaps.append(f"未配置大V画像：{profiles_path}")
    if not observations:
        gaps.append(f"未采集大V观点流水：{observations_path}")
    weak_observations = [
        item
        for item in observations
        if item.status != "verified" or item.confidence in {"low", "unknown"}
    ]
    unmapped_observations = [item for item in observations if not item.has_target]

    lines = [
        "# 大V视角技能库",
        "",
        "## 使用原则",
        "- 只把公开观点转成可审计的观察，不直接复制为交易指令。",
        "- 每个大V先沉淀为一张 skill card：关注市场、偏好风格、常见触发器、反证条件。",
        "- 观点必须落到股票、时间、价格区间、催化剂和风险点，否则只作情绪参考。",
        "",
        "## Skill Cards",
    ]
    if profiles:
        for profile in profiles:
            lines.extend(
                [
                    f"### {profile.get('name', '未命名')}",
                    f"- 来源：{profile.get('source', '未填写')}",
                    f"- 风格假设：{profile.get('style', '未填写')}",
                    f"- 关注领域：{', '.join(profile.get('focus', [])) or '未填写'}",
                    f"- 触发器：{', '.join(profile.get('triggers', [])) or '未填写'}",
                    f"- 反证条件：{', '.join(profile.get('invalidation', [])) or '未填写'}",
                ]
            )
    else:
        lines.append("- 暂无。")

    lines.extend(["", "## 最新观察"])
    if observations:
        for item in observations[-20:]:
            lines.extend(_render_observation(item))
    else:
        lines.append("- 暂无。")

    lines.extend(
        [
            "",
            "## 可落地影响",
            bullet(_impact_lines(observations)),
            "",
            "## 待验证观点",
            bullet(_verification_lines(weak_observations)),
        ]
    )
    if unmapped_observations:
        gaps.append("存在未映射到股票、产业或主题的观点，不能进入交易报告。")
    lines.extend(["", "## 数据缺口", bullet(gaps)])
    return "\n".join(lines)


def load_observations(path: Path = DEFAULT_OBSERVATIONS_PATH) -> list[InfluencerObservation]:
    return _load_observations(path)


def _load_profiles(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("profiles", []))


def _load_observations(path: Path) -> list[InfluencerObservation]:
    if not path.exists():
        return []
    observations: list[InfluencerObservation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            observations.append(InfluencerObservation.from_dict(json.loads(line)))
    return observations


def _render_observation(item: InfluencerObservation) -> list[str]:
    targets = []
    if item.symbols:
        targets.append(f"标的：{', '.join(item.symbols)}")
    if item.industries:
        targets.append(f"产业：{', '.join(item.industries)}")
    if item.themes:
        targets.append(f"主题：{', '.join(item.themes)}")
    target_text = "；".join(targets) if targets else "未落标的"
    source = f"{item.source_label}"
    if item.source_url:
        source = f"{source}：{item.source_url}"
    return [
        f"### {item.author} | {item.date}",
        f"- 摘要：{item.summary or '未填写'}",
        f"- 方向/置信度：{item.direction} / {item.confidence}",
        f"- 影响范围：{target_text}",
        f"- 来源：{source}",
        f"- 状态：{item.status}；周期：{item.impact_horizon}",
    ]


def _impact_lines(observations: list[InfluencerObservation]) -> list[str]:
    lines = []
    for item in observations[-20:]:
        if item.has_target:
            targets = ", ".join(item.symbols or item.industries or item.themes)
            lines.append(
                f"{item.author} -> {targets}：{item.summary} "
                f"（{item.source_label}，{item.confidence}）"
            )
    return lines


def _verification_lines(observations: list[InfluencerObservation]) -> list[str]:
    lines = []
    for item in observations[-20:]:
        checks = "；".join(item.verification) if item.verification else "补一手来源、产业数据和价格反应"
        lines.append(f"{item.author} / {item.id or item.date}：{checks}")
    return lines
