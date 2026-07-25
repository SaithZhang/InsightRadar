"""Reply-thread sentiment for influencer observations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stock_assist.paths import DATA_DIR
from stock_assist.reports import bullet


DEFAULT_THREADS_PATH = DATA_DIR / "influencer_threads.json"

SUPPORTIVE_TERMS = [
    "不错的框架",
    "大量买入",
    "反弹",
    "散户总是",
    "FUD",
    "抢走",
    "碾压",
    "下个季度会更好",
    "被计入价格",
]
SKEPTICAL_TERMS = [
    "顶部",
    "收入",
    "回调",
    "冲上云霄",
    "抛售",
    "泡沫",
]
QUESTION_TERMS = ["吗", "？", "?", "想知道"]
NOISE_TERMS = ["广告", "现在就玩", "资金公司"]


@dataclass(frozen=True)
class ThreadReply:
    author: str
    text: str
    age: str = ""
    category: str = "unknown"


@dataclass(frozen=True)
class InfluencerThread:
    id: str
    observation_id: str
    author: str
    source: str
    source_url: str
    captured_at: str
    main_text: str
    replies: list[ThreadReply] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadSentiment:
    thread: InfluencerThread
    supportive: int
    skeptical: int
    questions: int
    neutral: int
    noise: int

    @property
    def valid_count(self) -> int:
        return self.supportive + self.skeptical + self.questions + self.neutral

    @property
    def score(self) -> float:
        if self.valid_count == 0:
            return 0.0
        return (self.supportive - self.skeptical) / self.valid_count

    @property
    def label(self) -> str:
        if self.score >= 0.35:
            return "偏多共识"
        if self.score <= -0.2:
            return "偏空/质疑"
        if self.questions >= max(self.supportive, self.skeptical):
            return "疑问较多"
        return "分歧观察"


def build_influencer_sentiment_report(path: Path = DEFAULT_THREADS_PATH) -> str:
    threads = load_threads(path)
    sentiments = [score_thread(thread) for thread in threads]
    gaps: list[str] = []
    if not path.exists():
        gaps.append(f"未找到回复区数据：{path}")
    if not threads:
        gaps.append("暂无可分析 thread；可先手工导入 X 主贴和回复。")

    lines = [
        "# 大V回复情绪指示器",
        "",
        "## 读法",
        "- 主贴用于记录观点，回复区用于观察共识、质疑、疑问和噪音。",
        "- 指示器只衡量讨论结构，不直接产生买卖动作。",
        "- 广告、游戏推广、无关资金广告等会进入噪音桶。",
        "",
        "## Thread 情绪",
    ]
    if sentiments:
        for sentiment in sentiments:
            lines.extend(_render_sentiment(sentiment))
    else:
        lines.append("- 暂无。")

    lines.extend(["", "## 数据缺口", bullet(gaps)])
    return "\n".join(lines)


def load_thread_sentiments(path: Path = DEFAULT_THREADS_PATH) -> list[ThreadSentiment]:
    return [score_thread(thread) for thread in load_threads(path)]


def load_threads(path: Path = DEFAULT_THREADS_PATH) -> list[InfluencerThread]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    threads: list[InfluencerThread] = []
    for item in payload.get("threads", []):
        replies = [
            ThreadReply(
                author=str(reply.get("author", "未知")),
                text=str(reply.get("text", "")),
                age=str(reply.get("age", "")),
                category=str(reply.get("category", "unknown")),
            )
            for reply in item.get("replies", [])
        ]
        threads.append(
            InfluencerThread(
                id=str(item.get("id", "")),
                observation_id=str(item.get("observation_id", "")),
                author=str(item.get("author", "未知")),
                source=str(item.get("source", "")),
                source_url=str(item.get("source_url", "")),
                captured_at=str(item.get("captured_at", "")),
                main_text=str(item.get("main_text", "")),
                replies=replies,
            )
        )
    return threads


def score_thread(thread: InfluencerThread) -> ThreadSentiment:
    counts = {
        "supportive": 0,
        "skeptical": 0,
        "question": 0,
        "neutral": 0,
        "noise": 0,
    }
    for reply in thread.replies:
        category = reply.category if reply.category != "unknown" else classify_reply(reply.text)
        counts[category] = counts.get(category, 0) + 1
    return ThreadSentiment(
        thread=thread,
        supportive=counts["supportive"],
        skeptical=counts["skeptical"],
        questions=counts["question"],
        neutral=counts["neutral"],
        noise=counts["noise"],
    )


def classify_reply(text: str) -> str:
    if any(term in text for term in NOISE_TERMS):
        return "noise"
    if any(term in text for term in QUESTION_TERMS):
        return "question"
    supportive_hits = sum(1 for term in SUPPORTIVE_TERMS if term in text)
    skeptical_hits = sum(1 for term in SKEPTICAL_TERMS if term in text)
    if supportive_hits > skeptical_hits:
        return "supportive"
    if skeptical_hits > supportive_hits:
        return "skeptical"
    return "neutral"


def _render_sentiment(sentiment: ThreadSentiment) -> list[str]:
    thread = sentiment.thread
    return [
        f"### {thread.author} / {thread.id}",
        f"- 关联观点：{thread.observation_id}",
        f"- 指示器：{sentiment.label}；score={sentiment.score:.2f}；有效回复={sentiment.valid_count}；噪音={sentiment.noise}",
        f"- 结构：支持/共鸣 {sentiment.supportive}，质疑/偏空 {sentiment.skeptical}，疑问 {sentiment.questions}，中性 {sentiment.neutral}",
        f"- 主贴摘要：{thread.main_text[:140]}",
    ]
