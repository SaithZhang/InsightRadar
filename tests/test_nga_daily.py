from __future__ import annotations

import json
import unittest

from stock_assist.data_sources.nga import (
    NGADailyTopic,
    NGAReply,
    fetch_author_thread_replies,
    fetch_daily_topics,
)
from stock_assist.llm import LLMResponse
from stock_assist.workflows.nga_daily import _influencer_activity, _influencer_profiles, build_nga_daily_bundle


def _topic(tid: str, title: str, score: int) -> NGADailyTopic:
    reply = NGAReply(
        pid=f"p{tid}",
        floor=4,
        author="tester",
        author_id="9",
        posted_at="2026-07-15 15:00:00",
        score=score,
        content=f"{title} 的样本回复，包含观点分歧和情绪变化。",
    )
    return NGADailyTopic(
        thread_id=tid,
        title=title,
        url=f"https://bbs.nga.cn/read.php?tid={tid}",
        author="tester",
        author_id="9",
        posted_at="2026-07-15 09:00:00",
        last_posted_at="2026-07-15 15:00:00",
        replies=20,
        recommend=score,
        latest_replies=(reply,),
        high_score_replies=(reply,),
    )


TOPICS = [
    _topic("1", "科技半导体高开低走", 43),
    _topic("2", "科创50还能抄底吗", 21),
    _topic("3", "创新药行情能走多远", 32),
    _topic("4", "银行红利为何上涨", 8),
]


class _FakeClient:
    def complete(self, **_: object) -> LLMResponse:
        clusters = [
            {
                "title": f"主题 {index}",
                "analysis": "论坛讨论围绕板块走势展开，既有继续看多者，也有担忧拥挤和兑现者。帖子把变化归因于资金轮动与筹码结构，情绪从期待逐渐转向谨慎。隐含判断是方向与节奏需要分开观察，单一外部映射不足以解释盘面。",
                "topic_ids": [tid, "999"],
            }
            for index, tid in enumerate(("1", "2", "3", "4"), start=1)
        ]
        return LLMResponse(content=json.dumps({"clusters": clusters}, ensure_ascii=False), usage={"total_tokens": 100}, model="fake")


class _FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}
    text = ""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class _FakeHTMLResponse:
    status_code = 200
    headers = {"content-type": "text/html; charset=utf-8"}

    def __init__(self, html: str) -> None:
        self.content = html.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class _PagingSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, **_: object) -> _FakeResponse:
        self.urls.append(url)
        if "thread.php" in url and "page=1" in url:
            return _FakeResponse(
                {"data": {"__T": [
                    {"tid": 1, "subject": "早间新帖", "author": "a", "postdate": "2026-07-15 07:00:00", "lastpost": "2026-07-15 08:00:00", "replies": 8, "recommend": 2},
                    {"tid": 2, "subject": "午后新帖", "author": "b", "postdate": "2026-07-15 10:00:00", "lastpost": "2026-07-15 10:30:00", "replies": 5, "recommend": 1},
                ]}}
            )
        if "thread.php" in url and "page=2" in url:
            return _FakeResponse(
                {"data": {"__T": [
                    {"tid": 3, "subject": "旧帖早间更新", "author": "c", "postdate": "2026-07-14 21:00:00", "lastpost": "2026-07-15 08:30:00", "replies": 20, "recommend": 3},
                ]}}
            )
        tid = "1" if "tid=1" in url else "3"
        return _FakeResponse(
            {"data": {"__R": [{"pid": f"p{tid}", "lou": 1, "authorid": 9, "postdate": "2026-07-15 08:15:00", "score": 5, "content": "早间回复"}], "__U": {"9": {"username": "u"}}}}
        )


class _AuthorThreadSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, **_: object) -> _FakeHTMLResponse:
        self.urls.append(url)
        if "page=e" in url:
            return _FakeHTMLResponse(
                _author_html_page(3, [(90, "900", "9", "2026-07-15 17:00", "盘后回复")])
            )
        if "page=2" in url:
            return _FakeHTMLResponse(
                _author_html_page(
                    2,
                    [
                        (55, "550", "9", "2026-07-15 14:30", "科技仍是主线，但不追高。"),
                        (56, "560", "8", "2026-07-15 14:31", "其他人的热评"),
                    ],
                )
            )
        return _FakeHTMLResponse(
            _author_html_page(1, [(10, "100", "9", "2026-07-14 23:30", "旧回复")])
        )


def _author_html_page(page: int, rows: list[tuple[int, str, str, str, str]]) -> str:
    body = [f"<script>__CURRENT_PAGE={page};</script>"]
    for floor, pid, uid, posted_at, content in rows:
        body.append(
            f"<table><tr><td><a href='nuke.php?func=ucp&uid={uid}' id='postauthor{floor}'></a></td>"
            f"<td id='postcontainer{floor}'><a id='pid{pid}Anchor'></a>"
            f"<span id='postdate{floor}'>{posted_at}</span>"
            f"<span id='postcontent{floor}'>{content}</span></td></tr></table>"
        )
    return "".join(body)


class NGADailyTests(unittest.TestCase):
    def test_author_filtered_long_thread_recovers_only_exact_uid_inside_window(self) -> None:
        session = _AuthorThreadSession()
        replies = fetch_author_thread_replies(
            "45974302",
            "9",
            window_start="2026-07-15 00:00:00",
            window_end="2026-07-15 15:59:59",
            cookie="local-test-cookie",
            session=session,
        )
        self.assertEqual(["550"], [item.pid for item in replies])
        self.assertEqual("9", replies[0].author_id)
        self.assertTrue(all("authorid=9" in url for url in session.urls))

    def test_influencer_activity_separates_new_statements_from_old_active_threads(self) -> None:
        activity = _influencer_activity(
            TOPICS[:1],
            {"9": "watched"},
            window_start="2026-07-15 00:00:00",
            window_end="2026-07-15 15:59:59",
        )[0]
        self.assertEqual(2, activity["activity_count"])
        self.assertEqual(1, len(activity["topic_posts"]))
        self.assertEqual(1, len(activity["replies"]))
        outside = _influencer_activity(
            TOPICS[:1],
            {"9": "watched"},
            window_start="2026-07-16 00:00:00",
            window_end="2026-07-16 15:59:59",
        )[0]
        self.assertEqual(0, outside["activity_count"])
        self.assertEqual(1, outside["context_thread_count"])

    def test_extra_long_thread_reply_and_profile_prior_are_exposed(self) -> None:
        reply = NGAReply(
            pid="long-reply",
            floor=321,
            author="幸运阿sai",
            author_id="21321600",
            posted_at="2026-07-15 11:20:00",
            score=18,
            content="继续看好科技，但短线拥挤。",
        )
        profiles = _influencer_profiles(
            {"influential_authors": [{
                "uid": "21321600",
                "name": "幸运阿sai",
                "signal_prior_weight": 1.15,
                "profile": {"source_type": "user_provided", "verification_status": "unverified"},
            }]}
        )
        activity = _influencer_activity(
            [],
            {"21321600": "幸运阿sai"},
            window_start="2026-07-15 00:00:00",
            window_end="2026-07-15 15:59:59",
            profiles=profiles,
            extra_thread_activity={
                ("21321600", "46906089"): {
                    "thread_title": "科技主线坚守指南",
                    "url": "https://bbs.nga.cn/read.php?tid=46906089",
                    "replies": (reply,),
                }
            },
        )[0]
        self.assertEqual(1, activity["activity_count"])
        self.assertEqual("author_filtered_long_thread", activity["replies"][0]["source_scope"])
        self.assertEqual(1.15, activity["signal_prior_weight"])
        self.assertEqual("unverified", activity["profile"]["verification_status"])

    def test_user_provided_decision_framework_keeps_provenance_and_guardrails(self) -> None:
        profiles = _influencer_profiles(
            {
                "influential_authors": [
                    {
                        "uid": "21321600",
                        "name": "幸运阿sai",
                        "profile": {
                            "decision_framework": {
                                "source_type": "user_provided_review",
                                "verification_status": "page_unverified",
                                "mainline_gates": ["核心大票", "产业链轮动", "风格切换"],
                                "product_guardrails": ["不能把震荡自动解释为洗盘"],
                                "external_view_firewall": {"action_authority": "forbidden"},
                                "profit_giveback_template": {
                                    "threshold_status": "candidate_requires_user_approval"
                                },
                            }
                        },
                    }
                ]
            }
        )
        framework = profiles["21321600"]["profile"]["decision_framework"]
        self.assertEqual("user_provided_review", framework["source_type"])
        self.assertEqual("page_unverified", framework["verification_status"])
        self.assertEqual(3, len(framework["mainline_gates"]))
        self.assertIn("洗盘", framework["product_guardrails"][0])
        self.assertEqual("forbidden", framework["external_view_firewall"]["action_authority"])
        self.assertEqual(
            "candidate_requires_user_approval",
            framework["profit_giveback_template"]["threshold_status"],
        )

    def test_morning_window_uses_multiple_listing_pages_and_excludes_later_topics(self) -> None:
        session = _PagingSession()
        topics = fetch_daily_topics(
            target_date="2026-07-15",
            listing_pages=2,
            detail_limit=10,
            window_start="2026-07-15 00:00:00",
            window_end="2026-07-15 09:00:00",
            cookie="local-test-cookie",
            session=session,
        )
        self.assertEqual({"1", "3"}, {item.thread_id for item in topics})
        self.assertTrue(any("page=2" in url for url in session.urls))
        self.assertTrue(all(item.high_score_replies[0].posted_at <= "2026-07-15 09:00:00" for item in topics))

    def test_rule_fallback_is_explicit_and_keeps_real_reply_score(self) -> None:
        payload, markdown, html = build_nga_daily_bundle(target_date="2026-07-15", topics=TOPICS)
        self.assertEqual("rule-based", payload["summary_mode"])
        self.assertIn("规则降级版", markdown)
        self.assertIn("👍43", markdown)
        self.assertIn("https://bbs.nga.cn/read.php?tid=1", markdown)
        self.assertIn("<!doctype html>", html)

    def test_llm_cluster_ids_are_validated_before_rendering(self) -> None:
        payload, markdown, _ = build_nga_daily_bundle(
            target_date="2026-07-15",
            topics=TOPICS,
            use_llm=True,
            client_factory=lambda: _FakeClient(),
        )
        self.assertEqual("llm", payload["summary_mode"])
        self.assertNotIn("999", json.dumps(payload["clusters"]))
        self.assertIn("主题 1", markdown)
        self.assertIn("fake", markdown)


if __name__ == "__main__":
    unittest.main()
