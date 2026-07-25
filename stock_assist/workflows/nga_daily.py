"""Daily NGA Great Times topic digest with optional LLM synthesis."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import time
from typing import Any, Callable

from stock_assist.data_sources.nga import (
    DEFAULT_BOARD_FID,
    NGADailyTopic,
    NGAReply,
    fetch_author_thread_replies,
    fetch_daily_topics,
)
from stock_assist.llm import LLMConfig, LLMError, OpenAICompatibleClient, parse_json_response
from stock_assist.paths import CONFIG_DIR
from stock_assist.reports import markdown_report_to_html


DEFAULT_CONFIG_PATH = CONFIG_DIR / "nga_monitor.json"

FALLBACK_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("指数、成交与市场信心", ("大盘", "指数", "上证", "成交", "量化", "清仓", "信心", "牛市", "熊市")),
    ("科技、半导体与AI", ("科技", "科创", "半导体", "芯片", "存储", "光模块", "AI", "算力", "通信")),
    ("医药与创新药", ("医药", "创新药", "药明", "猴", "CXO", "疫苗")),
    ("消费、养殖与汽车", ("消费", "白酒", "五粮液", "茅台", "养殖", "猪", "牧原", "汽车", "比亚迪")),
    ("金融、红利与防御", ("银行", "保险", "券商", "红利", "电力", "高股息")),
)


def build_nga_daily_bundle(
    config_path: Path | None = None,
    *,
    target_date: str | None = None,
    window: str = "day",
    use_llm: bool = False,
    model: str | None = None,
    topics: list[NGADailyTopic] | None = None,
    client_factory: Callable[..., OpenAICompatibleClient] = OpenAICompatibleClient,
) -> tuple[dict[str, object], str, str]:
    config = _load_config(config_path)
    day = target_date or date.today().isoformat()
    window_start, window_end = _window_bounds(day, window, config)
    influencer_watchlist = _influencer_watchlist(config)
    influencer_profiles = _influencer_profiles(config)
    source_topics = topics
    influencer_thread_activity: dict[tuple[str, str], dict[str, object]] = {}
    influencer_collection_gaps: list[str] = []
    if source_topics is None:
        detail_key = "morning_detail_limit" if window == "morning" else "daily_detail_limit"
        pages_key = "morning_listing_pages" if window == "morning" else "daily_listing_pages"
        source_topics = fetch_daily_topics(
            int(config.get("board_fid", DEFAULT_BOARD_FID)),
            target_date=day,
            detail_limit=int(config.get(detail_key, 20 if window == "morning" else 35)),
            listing_pages=int(config.get(pages_key, 5 if window == "morning" else 10)),
            window_start=window_start,
            window_end=window_end,
            request_delay_seconds=float(config.get("detail_request_delay_seconds", 0.12)),
            detail_retries=int(config.get("detail_retries", 2)),
            priority_author_ids=set(influencer_watchlist),
            timeout=float(config.get("timeout_seconds", 20)),
        )
        tracked_threads = _tracked_influencer_threads(config, source_topics, influencer_watchlist)
        for index, thread in enumerate(tracked_threads):
            uid = str(thread["uid"])
            tid = str(thread["thread_id"])
            try:
                replies = fetch_author_thread_replies(
                    tid,
                    uid,
                    window_start=window_start,
                    window_end=window_end,
                    max_pages=int(config.get("influencer_reply_max_pages", 8)),
                    request_delay_seconds=float(config.get("detail_request_delay_seconds", 0.12)),
                    timeout=float(config.get("timeout_seconds", 20)),
                )
                influencer_thread_activity[(uid, tid)] = {
                    **thread,
                    "replies": tuple(reply for reply in replies if reply.floor > 0),
                }
            except Exception as exc:
                influencer_collection_gaps.append(f"{thread['name']} tid={tid}: {_safe_error(exc)}")
            if index + 1 < len(tracked_threads):
                time.sleep(float(config.get("influencer_thread_delay_seconds", 0.5)))
    if not source_topics:
        raise ValueError(f"NGA 大时代在 {day} 未采集到可用于日报的主题。")

    ai_gap = ""
    usage: dict[str, Any] = {}
    actual_model = "rule-based"
    clusters: list[dict[str, object]]
    if use_llm:
        try:
            client = client_factory() if model is None else client_factory(LLMConfig.from_local(model=model))
            response = client.complete(
                system=_system_prompt(int(config.get("daily_cluster_count", 5))),
                user=json.dumps(_llm_input(day, source_topics), ensure_ascii=False),
                temperature=0.15,
                max_tokens=int(config.get("daily_max_tokens", 3800)),
                json_mode=True,
            )
            clusters = _validate_clusters(parse_json_response(response.content), source_topics)
            usage = response.usage
            actual_model = response.model
        except Exception as exc:
            clusters = _fallback_clusters(source_topics)
            ai_gap = f"AI 综述不可用，已生成规则降级版：{_safe_error(exc)}"
    else:
        clusters = _fallback_clusters(source_topics)
        ai_gap = "本次未启用 AI；主题归类和摘要为规则降级版，不能替代跨帖语义判断。"

    payload: dict[str, object] = {
        "schema_version": "insight-nga-daily/v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target_date": day,
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "board_fid": int(config.get("board_fid", DEFAULT_BOARD_FID)),
        "source_url": f"https://bbs.nga.cn/thread.php?fid={int(config.get('board_fid', DEFAULT_BOARD_FID))}",
        "topic_count": len(source_topics),
        "summary_mode": "llm" if not ai_gap and use_llm else "rule-based",
        "model": actual_model,
        "usage": usage,
        "data_gap": ai_gap,
        "influencer_scope": (
            "统计当前板块翻页、已抓取主题页，以及配置内长期主帖按作者 UID 筛出的时间窗内楼层；"
            "不代表该账号全站所有主题的完整发言历史。"
        ),
        "influencer_data_gap": influencer_collection_gaps,
        "influencer_activity": _influencer_activity(
            source_topics,
            influencer_watchlist,
            window_start=window_start,
            window_end=window_end,
            profiles=influencer_profiles,
            extra_thread_activity=influencer_thread_activity,
        ),
        "clusters": clusters,
        "topics": [item.to_dict() for item in source_topics],
    }
    markdown = _render_markdown(payload, source_topics)
    return payload, markdown, markdown_report_to_html(markdown)


def _window_bounds(day: str, window: str, config: dict[str, Any]) -> tuple[str, str]:
    if window not in {"morning", "day"}:
        raise ValueError(f"不支持的 NGA 时间窗：{window}")
    start_key = "morning_window_start" if window == "morning" else "day_window_start"
    end_key = "morning_window_end" if window == "morning" else "day_window_end"
    start_time = str(config.get(start_key, "00:00:00"))
    default_end = "09:00:00" if window == "morning" else "15:59:59"
    end_time = str(config.get(end_key, default_end))
    return f"{day} {start_time}", f"{day} {end_time}"


def _load_config(path: Path | None) -> dict[str, Any]:
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"NGA 配置必须是 JSON object: {target}")
    return payload


def _influencer_watchlist(config: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in config.get("influential_authors", []):
        if not isinstance(row, dict):
            continue
        uid = str(row.get("uid", "")).strip()
        name = str(row.get("name", "")).strip()
        if uid and name:
            result[uid] = name
    return result


def _influencer_profiles(config: dict[str, Any]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in config.get("influential_authors", []):
        if not isinstance(row, dict):
            continue
        uid = str(row.get("uid", "")).strip()
        if not uid:
            continue
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
        prior_weight = float(row.get("signal_prior_weight", 1.0))
        result[uid] = {
            "signal_prior_weight": min(1.25, max(0.75, prior_weight)),
            "profile": profile,
        }
    return result


def _tracked_influencer_threads(
    config: dict[str, Any],
    topics: list[NGADailyTopic],
    watchlist: dict[str, str],
) -> list[dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    for row in config.get("influential_authors", []):
        if not isinstance(row, dict):
            continue
        uid = str(row.get("uid", "")).strip()
        if uid not in watchlist:
            continue
        for thread in row.get("tracked_threads", []):
            if not isinstance(thread, dict):
                continue
            tid = str(thread.get("thread_id", "")).strip()
            if not tid:
                continue
            result[(uid, tid)] = {
                "uid": uid,
                "name": watchlist[uid],
                "thread_id": tid,
                "thread_title": str(thread.get("title", "长期主帖")).strip() or "长期主帖",
                "url": f"https://bbs.nga.cn/read.php?tid={tid}",
            }
    for topic in topics:
        if topic.author_id not in watchlist:
            continue
        result.setdefault(
            (topic.author_id, topic.thread_id),
            {
                "uid": topic.author_id,
                "name": watchlist[topic.author_id],
                "thread_id": topic.thread_id,
                "thread_title": topic.title,
                "url": topic.url,
            },
        )
    return list(result.values())


def _influencer_activity(
    topics: list[NGADailyTopic],
    watchlist: dict[str, str],
    *,
    window_start: str,
    window_end: str,
    profiles: dict[str, dict[str, object]] | None = None,
    extra_thread_activity: dict[tuple[str, str], dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for uid, name in watchlist.items():
        active_authored_threads = [
            {"thread_id": topic.thread_id, "title": topic.title, "url": topic.url, "posted_at": topic.posted_at}
            for topic in topics
            if topic.author_id == uid
        ]
        new_topic_posts = [
            item for item in active_authored_threads if window_start <= str(item["posted_at"]) <= window_end
        ]
        seen_replies: set[str] = set()
        authored_replies: list[dict[str, object]] = []
        for topic in topics:
            for reply in (*topic.high_score_replies, *topic.latest_replies):
                if (
                    reply.author_id != uid
                    or reply.pid in seen_replies
                    or not (window_start <= reply.posted_at <= window_end)
                ):
                    continue
                seen_replies.add(reply.pid)
                authored_replies.append(
                    {
                        "thread_id": topic.thread_id,
                        "thread_title": topic.title,
                        "url": topic.url,
                        "pid": reply.pid,
                        "floor": reply.floor,
                        "score": reply.score,
                        "posted_at": reply.posted_at,
                        "content": reply.content,
                    }
                )
        for (reply_uid, tid), thread in (extra_thread_activity or {}).items():
            if reply_uid != uid:
                continue
            for reply in thread.get("replies", ()):
                if not isinstance(reply, NGAReply) or reply.pid in seen_replies:
                    continue
                if not (window_start <= reply.posted_at <= window_end):
                    continue
                seen_replies.add(reply.pid)
                authored_replies.append(
                    {
                        "thread_id": tid,
                        "thread_title": str(thread.get("thread_title", "长期主帖")),
                        "url": str(thread.get("url", f"https://bbs.nga.cn/read.php?tid={tid}")),
                        "pid": reply.pid,
                        "floor": reply.floor,
                        "score": reply.score,
                        "posted_at": reply.posted_at,
                        "content": reply.content,
                        "source_scope": "author_filtered_long_thread",
                    }
                )
        profile = (profiles or {}).get(uid, {})
        result.append(
            {
                "uid": uid,
                "name": name,
                "signal_prior_weight": profile.get("signal_prior_weight", 1.0),
                "profile": profile.get("profile", {}),
                "topic_posts": new_topic_posts,
                "active_authored_threads": active_authored_threads,
                "replies": authored_replies,
                "activity_count": len(new_topic_posts) + len(authored_replies),
                "context_thread_count": len(active_authored_threads),
            }
        )
    return result


def _system_prompt(cluster_count: int) -> str:
    return f"""你是A股论坛舆情编辑。只依据用户提供的NGA帖子与回复，生成中文日报聚类，不补充或断言外部事实。
输出单个JSON object，格式为：{{"clusters":[{{"title":"一句话主题标题","analysis":"220至360字综述","topic_ids":["帖子tid"]}}]}}。
生成恰好{max(4, cluster_count)}个互不重复的主题，按当日讨论重要性排序；每个帖子最多归入一个主题，每组尽量包含2至7个帖子，优先覆盖高讨论度帖子，topic_ids只能使用输入中的id。
analysis应自然包含：讨论核心与主要分歧、帖子中声称的催化或风险、情绪变化、隐含判断。把未经核验的原因写成“帖子认为/讨论将其归因于”，不要写成已证实事实。
不编造标题、点赞、回复、链接或行情数字，不给确定性买卖建议，不输出Markdown。"""


def _llm_input(day: str, topics: list[NGADailyTopic]) -> dict[str, object]:
    compact = []
    for topic in topics:
        replies = sorted(
            {item.pid: item for item in (*topic.latest_replies, *topic.high_score_replies)}.values(),
            key=lambda item: (item.score, item.posted_at),
            reverse=True,
        )[:6]
        compact.append(
            {
                "id": topic.thread_id,
                "title": topic.title,
                "replies": topic.replies,
                "recommend": topic.recommend,
                "samples": [
                    {"score": item.score, "floor": item.floor, "text": item.content[:360]}
                    for item in replies
                    if item.content
                ],
            }
        )
    return {"date": day, "board": "NGA 大时代", "topics": compact}


def _validate_clusters(payload: dict[str, Any], topics: list[NGADailyTopic]) -> list[dict[str, object]]:
    known = {item.thread_id for item in topics}
    rows = payload.get("clusters")
    if not isinstance(rows, list):
        raise LLMError("AI 返回缺少 clusters 数组。")
    seen: set[str] = set()
    valid: list[dict[str, object]] = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()[:80]
        analysis = str(row.get("analysis", "")).strip()
        ids = [str(item) for item in row.get("topic_ids", []) if str(item) in known and str(item) not in seen]
        if not title or len(analysis) < 80 or not ids:
            continue
        seen.update(ids)
        valid.append({"title": title, "analysis": analysis[:700], "topic_ids": ids})
    coverage = len(seen) / max(1, len(topics))
    if len(valid) < 4:
        raise LLMError(f"AI 主题覆盖不足（{len(valid)} 组、{coverage:.0%} 帖子），已拒绝不完整结果。")
    return valid


def _fallback_clusters(topics: list[NGADailyTopic]) -> list[dict[str, object]]:
    buckets: dict[str, list[NGADailyTopic]] = defaultdict(list)
    for topic in topics:
        title = topic.title
        group = next((name for name, terms in FALLBACK_GROUPS if any(term.lower() in title.lower() for term in terms)), "其他活跃讨论")
        buckets[group].append(topic)
    rows = sorted(buckets.items(), key=lambda item: sum(topic.replies + topic.recommend * 3 for topic in item[1]), reverse=True)
    result: list[dict[str, object]] = []
    for name, items in rows[:6]:
        ranked = sorted(items, key=lambda item: (item.recommend, item.replies), reverse=True)
        titles = "、".join(item.title for item in ranked[:4])
        positive = sum(1 for item in ranked for reply in item.high_score_replies if reply.score > 0)
        analysis = (
            f"该组共收录 {len(items)} 个当日活跃主题，讨论集中于“{titles}”。"
            f"样本中可识别到 {positive} 条正点赞回复。当前为关键词规则归类，只能展示讨论焦点和热度，"
            "不能可靠还原跨帖分歧、催化归因或情绪转折；启用 AI 后才会生成接近人工编辑的一段式综述。"
        )
        result.append({"title": name, "analysis": analysis, "topic_ids": [item.thread_id for item in ranked]})
    return result


def _render_markdown(payload: dict[str, object], topics: list[NGADailyTopic]) -> str:
    topic_map = {item.thread_id: item for item in topics}
    lines = [
        f"# NGA 大时代今日话题 {payload['target_date']}",
        "",
        f"- 来源：[NGA 大时代]({payload['source_url']})；收录当日活跃主题 {payload['topic_count']} 个。",
        f"- 时间窗：{payload['window_start']} 至 {payload['window_end']}（Asia/Shanghai）。",
        f"- 综述方式：{payload['summary_mode']}（{payload['model']}）。",
        "- 说明：主题、链接、楼层和点赞由程序从 NGA 回填；AI 只负责聚类与文字综述。",
    ]
    if payload.get("data_gap"):
        lines.append(f"- 数据缺口：{payload['data_gap']}")
    active_influencers = [item for item in payload.get("influencer_activity", []) if item.get("activity_count")]
    lines.extend(["", "## 大V采样活动", ""])
    if not active_influencers:
        lines.append("- 当前采样窗口未命中观察名单发言；这不等于大V当日没有发言。")
    for item in active_influencers:
        lines.append(f"- {item['name']}（uid={item['uid']}）：命中 {item['activity_count']} 条主题或回复证据。")
    for index, cluster in enumerate(payload["clusters"], start=1):
        assert isinstance(cluster, dict)
        ids = [str(item) for item in cluster.get("topic_ids", [])]
        selected = [topic_map[item] for item in ids if item in topic_map]
        lines.extend(["", f"## {index}. {cluster['title']}", "", str(cluster["analysis"]), "", "### 相关主题", ""])
        for topic in selected[:7]:
            lines.append(f"- [{topic.title}]({topic.url})｜回复 {topic.replies}｜推荐 {topic.recommend}")
        lines.extend(["", "### 高赞回复", ""])
        high = _cluster_high_replies(selected)
        if not high:
            lines.append("- 当日采样未取得正点赞回复。")
        for topic, reply in high[:3]:
            excerpt = reply.content[:260].strip()
            lines.append(f"- 👍{reply.score}｜[{topic.title}]({topic.url}#pid{reply.pid}) #{reply.floor}")
            lines.append(f"  {excerpt}")
    lines.extend(
        [
            "",
            "## 数据边界",
            "",
            "- 仅覆盖采集时仍在板块列表中的当日活跃主题；被删除、沉底或超出抓取上限的帖子可能遗漏。",
            "- 点赞与回复为采集时快照，不代表全体投资者观点；论坛归因未经外部事实核验。",
            "- 本报告用于情绪观察，不构成交易建议。",
        ]
    )
    return "\n".join(lines)


def _cluster_high_replies(topics: list[NGADailyTopic]) -> list[tuple[NGADailyTopic, NGAReply]]:
    rows = [(topic, reply) for topic in topics for reply in topic.high_score_replies if reply.score > 0 and reply.content]
    unique: dict[str, tuple[NGADailyTopic, NGAReply]] = {}
    for topic, reply in rows:
        unique.setdefault(reply.pid, (topic, reply))
    return sorted(unique.values(), key=lambda item: (item[1].score, item[1].posted_at), reverse=True)


def _safe_error(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    return message[:240] or exc.__class__.__name__
