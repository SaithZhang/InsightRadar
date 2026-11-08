"""Sampling and evidence-time regressions; no network, named themes or model doubles as acceptance."""
import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
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


class EvidencePolicyTests(unittest.TestCase):
    def sample(self, source="nga"):
        packet = {"schema": 2, "cutoff": CUTOFF, "items": [
            {"id": "D001", "source": source, "source_id": "synthetic-1", "author": "synthetic",
             "title": "合成转述", "text": "网传合成企业拟发特别股息一百亿元，但尚未查到正式公告。",
             "period": "overnight", "url": "https://example.com/1", "published_at": CUTOFF, "first_seen_at": CUTOFF},
            {"id": "D002", "source": "news", "source_id": "synthetic-2", "author": "synthetic",
             "title": "合成反向材料", "text": "另一则归档称合成企业现金流下降，股息方案仍有不确定性。",
             "period": "overnight", "url": "https://example.com/2", "published_at": CUTOFF, "first_seen_at": CUTOFF}]}
        row = {"title": "股息转述待核验", "reason": "若转述属实，可能影响预期；先核验原文", "keyword": "合成股息",
               "symbols": [], "evidence_ids": ["D001"], "counter_evidence_ids": [], "next_check": "查正式公告",
               "claims": [{"text": "来源称拟发股息", "kind": "fact", "evidence_id": "D001", "quote": packet["items"][0]["text"]}],
               "counter_evidence_gap": ""}
        return packet, {"opportunities": [row], "risks": [], "summary": "合成测试；转述未经核验"}

    def test_forum_and_news_cannot_self_certify_facts_and_raw_answer_is_retained(self):
        for source in ("nga", "xueqiu", "news"):
            with self.subTest(source=source):
                packet, raw = self.sample(source)
                before = deepcopy(raw)
                checked, warnings = d.apply_evidence_policy(raw, packet)
                self.assertEqual(raw, before)
                self.assertEqual(checked["opportunities"][0]["claims"][0]["kind"], "rumor")
                self.assertEqual(len(warnings), 1)

    def test_missing_counter_is_explicit_and_policy_is_idempotent(self):
        packet, raw = self.sample()
        checked, _ = d.apply_evidence_policy(raw, packet)
        self.assertIn("未检出不代表不存在", checked["opportunities"][0]["counter_evidence_gap"])
        self.assertEqual(d.apply_evidence_policy(checked, packet)[0], checked)
        self.assertEqual(checked["opportunities"][0]["counter_evidence_ids"], [])

    def test_real_counter_quote_and_kind_are_preserved(self):
        packet, raw = self.sample()
        row = raw["opportunities"][0]
        row["counter_evidence_ids"] = ["D002"]
        row["claims"].append({"text": "现金流转述削弱股息预期", "kind": "inference", "evidence_id": "D002", "quote": packet["items"][1]["text"]})
        checked, _ = d.apply_evidence_policy(raw, packet)
        self.assertEqual(checked["opportunities"][0]["claims"][1]["kind"], "inference")
        self.assertEqual(checked["opportunities"][0]["counter_evidence_gap"], "")

    def test_fabricated_or_changed_numeric_quote_is_rejected(self):
        packet, raw = self.sample()
        for quote in ("网传合成企业拟发特别股息二百亿元", "不存在的原文摘句", "股息"):
            raw["opportunities"][0]["claims"][0]["quote"] = quote
            with self.assertRaisesRegex(ValueError, "QUOTE_UNSUPPORTED"):
                d.apply_evidence_policy(raw, packet)

    def test_unquoted_or_conflicting_stance_cannot_enter_board(self):
        packet, raw = self.sample()
        row = raw["opportunities"][0]
        row["counter_evidence_ids"] = ["D002"]
        with self.assertRaisesRegex(ValueError, "UNQUOTED_CITATION"):
            d.apply_evidence_policy(raw, packet)
        row["counter_evidence_ids"] = ["D001"]
        with self.assertRaisesRegex(ValueError, "CONFLICTING_STANCE"):
            d.apply_evidence_policy(raw, packet)

    def test_legacy_free_text_cannot_pass_new_run_contract(self):
        packet, raw = self.sample()
        del raw["opportunities"][0]["claims"]
        del raw["opportunities"][0]["counter_evidence_gap"]
        d.validate(raw, packet)  # Historical archives remain readable.
        with self.assertRaisesRegex(ValueError, "CARD_INVALID"):
            d.apply_evidence_policy(raw, packet)

    def test_claims_and_counter_gap_survive_card_continuation_without_rewriting_history(self):
        from stock_assist.research_board import _import_discoveries
        packet, raw = self.sample()
        board = {"cards": [], "events": [], "revision": 0}
        result = {"claim_schema": 1, "packet": packet, "answer": raw}
        _import_discoveries(board, result, "synthetic-run-1")
        card = board["cards"][0]
        original = deepcopy(card["history"])
        card["entry"] = "用户条件保持"
        _import_discoveries(board, result, "synthetic-run-2")
        self.assertEqual(card["history"][:len(original)], original)
        self.assertEqual(card["entry"], "用户条件保持")
        self.assertEqual(card["discovery_update"]["claims"][0]["kind"], "rumor")
        gap = card["discovery_update"]["counter_evidence_gap"]
        self.assertTrue(any(g["text"] == gap and not g["resolved_by"] for g in card["gaps"]))
        before = deepcopy(board)
        _import_discoveries(board, result, "synthetic-run-2")
        self.assertEqual(board, before)


class StanceContractTests(unittest.TestCase):
    def sample(self):
        packet, raw = EvidencePolicyTests().sample()
        packet["window_status"] = "verified"
        row = raw["opportunities"][0]
        del row["evidence_ids"], row["counter_evidence_ids"]
        row["reason"] = "若归档转述属实，可能影响预期，但现金流约束尚需核验"
        row["claims"][0].update(kind="rumor", stance="supports", stance_reason="股息安排说法支持股东回报改善的待验命题", counter_quote="")
        packet["items"][1]["text"] = "合成企业收入增长，可能支持景气改善。但现金流下降，削弱盈利兑现预期。"
        row["claims"].append({"text": "收入与现金流提供相反方向的说法", "kind": "rumor", "evidence_id": "D002",
            "quote": "合成企业收入增长，可能支持景气改善", "stance": "mixed",
            "counter_quote": "但现金流下降，削弱盈利兑现预期", "stance_reason": "收入增长支持景气改善，现金流下降则削弱回报兑现"})
        return packet, raw

    def test_claim_stances_derive_both_lists_and_keep_raw_answer(self):
        packet, raw = self.sample()
        before = deepcopy(raw)
        checked, _, _ = d.prepare_answer(raw, packet)
        row = checked["opportunities"][0]
        self.assertEqual(row["evidence_ids"], ["D001", "D002"])
        self.assertEqual(row["counter_evidence_ids"], ["D002"])
        self.assertEqual(row["counter_evidence_gap"], "")
        self.assertTrue(all(c["text"].startswith("来源称：") for c in row["claims"]))
        self.assertEqual(raw, before)
        self.assertEqual(d.apply_evidence_policy(checked, packet, require_stances=True)[0], checked)

    def test_mixed_requires_distinct_actual_counter_quote(self):
        packet, raw = self.sample()
        for quote in ("", "不存在的反向原文片段", raw["opportunities"][0]["claims"][1]["quote"],
                      "可能支持景气改善。但现金流下降，削弱盈利兑现预期"):
            raw["opportunities"][0]["claims"][1]["counter_quote"] = quote
            with self.assertRaisesRegex(ValueError, "COUNTER_QUOTE_UNSUPPORTED"):
                d.prepare_answer(raw, packet)

    def test_derived_lists_cannot_be_changed_to_hide_counter(self):
        packet, raw = self.sample()
        checked, _, _ = d.prepare_answer(raw, packet)
        checked["opportunities"][0]["counter_evidence_ids"] = []
        with self.assertRaisesRegex(ValueError, "STANCE_CITATIONS_MISMATCH"):
            d.apply_evidence_policy(checked, packet, require_stances=True)

    def test_source_fact_wording_cannot_replace_conditional_inference(self):
        packet, raw = self.sample()
        raw["opportunities"][0]["reason"] = "合成企业已经确认改善，将带动行业"
        with self.assertRaisesRegex(ValueError, "CONDITIONAL_INFERENCE_REQUIRED"):
            d.prepare_answer(raw, packet)

    def test_source_level_manual_list_and_unexplained_stance_rejected(self):
        packet, raw = self.sample()
        raw["opportunities"][0]["evidence_ids"] = ["D001"]
        with self.assertRaisesRegex(ValueError, "STANCE_CARD_INVALID"):
            d.prepare_answer(raw, packet)
        del raw["opportunities"][0]["evidence_ids"]
        raw["opportunities"][0]["claims"][0]["stance_reason"] = "支持"
        with self.assertRaisesRegex(ValueError, "STANCE_REASON_INVALID"):
            d.prepare_answer(raw, packet)

    def test_mixed_source_survives_card_storage_and_continuation(self):
        from stock_assist.research_board import _import_discoveries
        packet, raw = self.sample()
        checked, _, _ = d.prepare_answer(raw, packet)
        result = {"claim_schema": 2, "answer": checked, "packet": packet}
        board = {"schema_version": 1, "cards": [], "events": [], "revision": 0}
        _import_discoveries(board, result, "synthetic-v2-1")
        history = deepcopy(board["cards"][0]["history"])
        result["review_note"] = "Codex审阅更正；不是自动发现验收通过"
        _import_discoveries(board, result, "synthetic-v2-2")
        self.assertEqual(board["cards"][0]["history"][:len(history)], history)
        self.assertEqual([e["stance"] for e in board["cards"][0]["evidence"]], ["supports", "mixed", "supports", "mixed"])
        self.assertEqual(board["cards"][0]["discovery_update"]["claims"][1]["counter_quote"], raw["opportunities"][0]["claims"][1]["counter_quote"])
        self.assertEqual(board["cards"][0]["history"][-1]["action"], "冻结案例审阅")
        self.assertEqual(board["cards"][0]["history"][-1]["snapshot"]["discovery_update"]["review_note"], result["review_note"])

    def test_failed_discovery_never_imports_partial_answer(self):
        from stock_assist.research_board import _import_discoveries
        board = {"cards": []}
        with self.assertRaisesRegex(ValueError, "不能导入"):
            _import_discoveries(board, {"status": "failed"}, "rejected-run")
        self.assertEqual(board, {"cards": []})

    def test_frozen_run_never_recollects_and_retains_rejected_answer(self):
        packet, raw = self.sample()
        raw["opportunities"][0]["reason"] = "未经归因的确定事实"
        model = SimpleNamespace(reserve=lambda *args: .02, cost=lambda *args: .001, call=lambda *args: raw)
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp)/"frozen.json", Path(temp)/"replay.json"
            source.write_text(json.dumps({"packet": packet}))
            original = source.read_bytes()
            with patch.object(d, "collect", side_effect=AssertionError("must not recollect")), patch.dict("sys.modules", {
                "pilot.core": SimpleNamespace(config=lambda: {}), "pilot.model": SimpleNamespace(DeepSeek=lambda cfg: model)}):
                d.run(output, frozen_result=source)
            result = json.loads(output.read_text())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["validation_error"], "DISCOVERY_CONDITIONAL_INFERENCE_REQUIRED")
            self.assertEqual(result["raw_answer"], raw)
            self.assertNotIn("answer", result)
            self.assertEqual(result["packet"], packet)
            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
