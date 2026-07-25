"""NGA Great Times board snapshots and lightweight heat/sentiment proxies."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

from stock_assist.data_sources.nga import DEFAULT_BOARD_FID, NGATopic, fetch_board_topics
from stock_assist.paths import CONFIG_DIR, DATA_DIR, PROJECT_ROOT


DEFAULT_CONFIG_PATH = CONFIG_DIR / "nga_monitor.json"
DEFAULT_SNAPSHOT_PATH = DATA_DIR / "nga" / "board_snapshots.jsonl"

BULLISH_TERMS = ("抄底", "大涨", "反弹", "新高", "涨停", "机会", "看多", "起飞", "牛市")
BEARISH_TERMS = ("大跌", "跌停", "被套", "割肉", "崩", "风险", "哀嚎", "利空", "看空")


def build_nga_monitor_report(config_path: Path | None = None) -> str:
    config = _load_config(config_path)
    snapshot_path = _runtime_path(config.get("snapshot_path", DEFAULT_SNAPSHOT_PATH))
    previous = _load_latest_snapshot(snapshot_path)
    topics = fetch_board_topics(
        int(config.get("board_fid", DEFAULT_BOARD_FID)),
        timeout=float(config.get("timeout_seconds", 20)),
    )
    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    snapshot = {
        "schema_version": "insight-nga-board/v1",
        "captured_at": captured_at,
        "board_fid": int(config.get("board_fid", DEFAULT_BOARD_FID)),
        "source_url": f"https://bbs.nga.cn/thread.php?fid={int(config.get('board_fid', DEFAULT_BOARD_FID))}",
        "topics": [topic.to_dict() for topic in topics],
    }
    _append_snapshot(snapshot_path, snapshot)
    return _render_report(snapshot, previous, config)


def _load_config(path: Path | None) -> dict[str, Any]:
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"NGA 配置必须是 JSON object: {target}")
    return payload


def _runtime_path(value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_latest_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            latest = item
    return latest


def _append_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def _render_report(snapshot: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> str:
    topics = [NGATopic(**item) for item in snapshot["topics"]]
    previous_counts = {
        str(item.get("thread_id")): int(item.get("replies", 0))
        for item in (previous or {}).get("topics", [])
    }
    elapsed_minutes = _elapsed_minutes(previous, str(snapshot["captured_at"]))
    ranked: list[tuple[float, int, NGATopic]] = []
    for topic in topics:
        delta = max(0, topic.replies - previous_counts.get(topic.thread_id, topic.replies))
        velocity = delta / elapsed_minutes if elapsed_minutes else 0.0
        score = velocity * 60.0 + math.log1p(topic.replies)
        ranked.append((score, delta, topic))
    ranked.sort(key=lambda item: (item[0], item[2].replies), reverse=True)

    sentiment = Counter(_title_sentiment(topic.title) for topic in topics)
    watch_terms = [str(item) for item in config.get("watch_terms", []) if str(item).strip()]
    term_counts = Counter(
        term for topic in topics for term in watch_terms if term.lower() in topic.title.lower()
    )
    top_n = max(1, int(config.get("top_n", 12)))

    lines = [
        "# NGA 大时代情绪与热帖监控",
        "",
        f"- 抓取时间：{snapshot['captured_at']}",
        f"- 板块：[大时代]({snapshot['source_url']})（fid={snapshot['board_fid']}）",
        f"- 当前主题：{len(topics)}；标题偏多 {sentiment['bullish']}；标题偏空 {sentiment['bearish']}；中性 {sentiment['neutral']}",
        "- 定位：公开讨论热度与标题情绪代理，不构成交易信号。",
        "",
        "## 热帖与升温",
    ]
    if previous is None:
        lines.append("- 本次为首个快照，只建立回复数基线；下次采集开始计算回复增速。")
    for _, delta, topic in ranked[:top_n]:
        delta_text = f"+{delta}" if previous is not None else "基线"
        lines.append(f"- [{topic.title}]({topic.url})｜回复 {topic.replies}｜本周期 {delta_text}")

    lines.extend(["", "## 关注词"])
    if term_counts:
        for term, count in term_counts.most_common(12):
            lines.append(f"- {term}：{count} 个标题")
    else:
        lines.append("- 当前首页标题未命中配置关注词。")

    lines.extend(
        [
            "",
            "## 数据边界",
            "- 当前情绪统计只分析主题标题；回复正文、独立发言人数和作者历史权重尚未纳入。",
            "- 热度以相邻快照的回复增量为主，首轮或长时间断档时不可直接比较。",
            "- NGA 页面结构或登录校验变化会显式报错，不会用旧数据冒充实时结果。",
        ]
    )
    return "\n".join(lines)


def _title_sentiment(title: str) -> str:
    bullish = sum(term in title for term in BULLISH_TERMS)
    bearish = sum(term in title for term in BEARISH_TERMS)
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return "neutral"


def _elapsed_minutes(previous: dict[str, Any] | None, current: str) -> float | None:
    if not previous or not previous.get("captured_at"):
        return None
    try:
        before = datetime.fromisoformat(str(previous["captured_at"]))
        after = datetime.fromisoformat(current)
    except ValueError:
        return None
    seconds = (after - before).total_seconds()
    return max(seconds / 60.0, 1.0) if seconds > 0 else None
