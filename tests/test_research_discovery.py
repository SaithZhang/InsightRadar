"""Sampling and evidence-time regressions; no network, named themes or model doubles as acceptance."""
import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from stock_assist import research_discovery as d


CALENDAR = {"source": "synthetic", "rows": [
    {"date": "2026-10-23", "is_open": True},
    {"date": "2026-10-24", "is_open": False},
    {"date": "2026-10-25", "is_open": False},
    {"date": "2026-10-26", "is_open": True},
    {"date": "2026-10-27", "is_open": False},
    {"date": "2026-10-28", "is_open": False},
    {"date": "2026-10-29", "is_open": True},
]}
CUTOFF = "2026-10-25T12:00:00+08:00"
CLAIM = "合成企业公布了新的经营安排，因为前置条件变化所以需要重新观察供需关系。如果实际订单未能兑现，判断就可能失效，需要关注后续正式公告与交付数量。"


class WindowTests(unittest.TestCase):
    def test_weekend_and_explicit_weekday_closures(self):
        self.assertEqual(d.resolve_window(CUTOFF, CALENDAR)["window_start"], "2026-10-23T15:00:00+08:00")
        self.assertEqual(d.resolve_window("2026-10-29T08:00:00+08:00", CALENDAR)["window_start"], "2026-10-26T15:00:00+08:00")

    def test_daytime_click_stops_at_premarket_and_after_close_starts_new_window(self):
        morning = d.resolve_window("2026-10-26T13:00:00+08:00", CALENDAR)
        self.assertEqual(morning["cutoff"], "2026-10-26T09:25:00+08:00")
        self.assertEqual(morning["window_start"], "2026-10-23T15:00:00+08:00")
        self.assertEqual(d.resolve_window("2026-10-26T15:01:00+08:00", CALENDAR)["window_start"], "2026-10-26T15:00:00+08:00")

    def test_unknown_dates_and_naive_time_never_guess_weekdays(self):
        for cutoff in ("2026-10-30T08:00:00+08:00", "2026-10-25T08:00:00"):
            with self.assertRaises(ValueError):
                d.resolve_window(cutoff, CALENDAR)
        packet = d.collect({}, CUTOFF, calendar={"rows": []})
        self.assertEqual(packet["window_status"], "blocked")
        self.assertEqual(packet["items"], [])

    def test_calendar_rejects_missing_duplicate_and_unknown_day_flags(self):
        rows = [{"jyrq": f"2026-10-{i:02}", "jybz": "1"} for i in range(1, 32)]
        self.assertEqual(len(d._calendar_month({"data": rows}, 2026, 10)), 31)
        for broken in (rows[:-1], rows[:-1] + [rows[0]], rows[:-1] + [{"jyrq": "2026-10-31", "jybz": None}]):
            with self.assertRaises(ValueError):
                d._calendar_month({"data": broken}, 2026, 10)


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "nga.db"
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.execute("CREATE TABLE posts(tid,identity,content_text,content_raw,author_uid,posted_at,first_seen_at,fetched_at,content_changed_at,source_url)")
        self.cfg = {"archives": {"nga": str(self.path), "news": str(self.root / "missing"), "xueqiu": str(self.root / "missing2")}}

    def add(self, ident, text=CLAIM, author=None, at="2026-10-23T16:00:00+08:00", seen=None, changed=None, raw=None, fetched=CUTOFF, thread=1):
        self.conn.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?,?)", (thread, str(ident), text, raw, author or str(ident), at, seen or at, fetched, changed, "https://example.com/post/" + str(ident)))
        self.conn.commit()

    def collect(self):
        audit = []
        packet = d.collect(self.cfg, CUTOFF, calendar=CALENDAR, audit=audit)
        return packet, audit, next(r for r in packet["coverage"] if r["source"] == "nga")

    def test_busy_recent_thread_cannot_remove_earlier_independent_claim(self):
        self.add("early", thread=7)
        for i in range(300):
            self.add(i, CLAIM + str(i), author="busy", at="2026-10-25T11:00:00+08:00")
        packet, audit, state = self.collect()
        self.assertIn("7:early", [r["source_id"] for r in packet["items"]])
        self.assertEqual(state["scanned"], 301)
        self.assertEqual(sum(state["dispositions"].values()), 301)
        self.assertLessEqual(sum(r["author"] == "busy" for r in packet["items"]), 3)
        self.assertTrue(state["scan_complete"])
        self.assertEqual(len(audit), 301)

    def test_cutoff_distinguishes_post_time_first_seen_and_mutable_version(self):
        self.add("good")
        self.add("future-seen", CLAIM + "乙", seen="2026-10-25T13:00:00+08:00")
        self.add("edited-later", CLAIM + "丙", changed="2026-10-25T13:00:00+08:00")
        self.add("missing-time", CLAIM + "丁", at=None, seen="2026-10-23T16:00:00+08:00")
        self.add("future-post", CLAIM + "戊", at="2026-10-26T16:00:00+08:00")
        p, audit, state = self.collect()
        self.assertEqual([r["source_id"] for r in p["items"]], ["1:good"])
        self.assertEqual(state["dispositions"]["not_known_at_cutoff"], 2)
        self.assertEqual(state["dispositions"]["missing_time"], 1)
        self.assertEqual(state["scanned"], 4)

    def test_quotes_do_not_become_repeated_independent_support(self):
        self.add("original")
        self.add("reply", "copied text", raw="[quote]" + CLAIM + "[quote]nested[/quote][/quote]谢谢分享")
        self.add("duplicate", CLAIM)
        self.add("template", "我刚刚调整了雪球组合 $某个测试组合$ 的仓位。")
        p, a, state = self.collect()
        self.assertEqual(len(p["items"]), 1)
        self.assertEqual(state["dispositions"]["duplicate_text"], 1)
        self.assertEqual(state["dispositions"]["portfolio_template"], 1)
        reply = next(r for r in a if r["source_id"] == "1:reply")
        self.assertEqual(reply["own_text"], "谢谢分享")
        self.assertEqual(reply["disposition"], "short_text")

    def test_no_new_stale_empty_and_unavailable_are_distinct(self):
        p, _, state = self.collect()
        self.assertEqual(state["status"], "empty_archive")
        self.assertEqual(p["coverage"][0]["status"], "unavailable")
        self.add("old", at="2026-10-23T14:00:00+08:00")
        p, _, state = self.collect()
        self.assertEqual(state["status"], "no_new")
        self.assertEqual(p["items"][0]["period"], "context")
        self.conn.execute("UPDATE posts SET fetched_at='2026-10-23T14:01:00+08:00'"); self.conn.commit()
        self.assertEqual(self.collect()[2]["status"], "stale")
        self.conn.close()
        self.path.write_bytes(b"not a database")
        self.assertEqual(self.collect()[2]["status"], "unavailable")

    def test_equal_close_is_background_and_new_statement_is_required(self):
        self.add("close", at="2026-10-23T15:00:00+08:00")
        p, _, _ = self.collect()
        answer = {"opportunities": [{"title": "合成案例", "reason": "待核验", "keyword": "测试", "symbols": [], "evidence_ids": ["D001"], "counter_evidence_ids": [], "next_check": "需要公告"}], "risks": [], "summary": "背景"}
        with self.assertRaisesRegex(ValueError, "NO_OVERNIGHT"):
            d.validate(answer, p)

    def test_budget_does_not_erase_dispositions_and_model_input_stays_bounded(self):
        for i in range(200):
            self.add(i, (CLAIM + str(i)) * 15, thread=i % 9, at=f"2026-10-{23+i%3}T{16 if i%3==0 else i%12:02}:00:00+08:00")
        p, a, state = self.collect()
        self.assertLess(len(json.dumps(p, ensure_ascii=False).encode()), 85_000)
        self.assertTrue(all(len(r["text"]) <= 500 for r in p["items"]))
        self.assertFalse(any(r["disposition"] in {"eligible", "pending_budget"} for r in a))
        self.assertEqual(Counter(r["disposition"] for r in a), state["dispositions"])
        self.assertTrue(all(r["truncated"] for r in p["items"]))


if __name__ == "__main__":
    unittest.main()
