from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from stock_assist.research_board import _import_discoveries, _read, _run_research, _write, mutate, read_board
from stock_assist.research_board_web import render_research_board
from stock_assist.research_discovery import collect, quarantine_unsupported_symbols, validate


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "board.json"
        self.card_id = mutate({"revision": 0, "action": "create", "question": "验证一个独立研究问题",
                               "keyword": "样例", "symbols": ["900001"], "valid_until": "2020-01-01"}, self.path)["card_id"]

    def change(self, action, **data):
        return mutate({"revision": _read(self.path)["revision"], "card_id": self.card_id,
                       "action": action, **data}, self.path)

    def test_revisions_remain_immutable_after_edit_freeze_and_review(self):
        first = deepcopy(_read(self.path)["cards"][0]["history"][0])
        self.change("revise", entry="条件一", invalidation="失效一", exit="退出一", note="形成草案")
        self.change("freeze", note="盘前观察版")
        self.change("revise", entry="条件二", note="新材料改变判断")
        self.change("review", outcome="未触发", note="没有达到观察条件")
        card = read_board(self.path)["cards"][0]
        self.assertEqual(card["history"][0], first)
        self.assertEqual(card["history"][2]["snapshot"]["entry"], "条件一")
        self.assertEqual(card["reviews"][0]["plan_version"], 4)
        self.assertEqual(card["version"], 5)
        self.assertTrue(card["expired"])
        self.assertEqual(card["trade_authority"], "none")

    def test_stale_page_cannot_overwrite_current_card(self):
        raw = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "新版本"):
            mutate({"revision": 0, "card_id": self.card_id, "action": "revise", "note": "old"}, self.path)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_gap_resolution_requires_traceable_fact_and_does_not_authorize_trade(self):
        gap = _read(self.path)["cards"][0]["gaps"][0]["id"]
        args = dict(title="公开材料", text="明确的来源内容", as_of="2020-01-01", kind="sentiment", gap_id=gap)
        with self.assertRaisesRegex(ValueError, "事实"):
            self.change("evidence", **args)
        self.assertEqual(len(_read(self.path)["cards"][0]["evidence"]), 0)
        self.change("evidence", **{**args, "kind": "fact", "url": "https://example.com/filing"})
        card = read_board(self.path)["cards"][0]
        self.assertEqual(card["open_gaps"], 2)
        self.assertEqual(card["status"], "watch")
        self.assertEqual(card["trade_authority"], "none")

    def test_untrusted_links_are_rejected_before_persistence(self):
        raw = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.change("evidence", title="bad", text="x", kind="fact", as_of="2020-01-01", url="javascript:alert(1)")
        self.assertEqual(self.path.read_bytes(), raw)

    def test_pending_job_survives_restart_as_unknown_without_retry(self):
        board = _read(self.path)
        board["cards"][0]["job"] = {"status": "running"}
        board["discovery"] = {"status": "running"}
        _write(self.path, board)
        recovered = read_board(self.path)
        self.assertEqual(recovered["cards"][0]["job"]["status"], "interrupted")
        self.assertEqual(recovered["discovery"]["status"], "interrupted")
        self.assertEqual(read_board(self.path)["revision"], recovered["revision"])

    def test_unsupported_status_cannot_become_buy_signal(self):
        with self.assertRaises(ValueError):
            self.change("status", status="buy", note="please buy")

    def test_private_file_and_empty_runtime(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertIsNone(read_board(self.path)["holdings_snapshot"])
        self.assertEqual(read_board(Path(self.temp.name)/"empty.json")["cards"], [])

    def test_corruption_does_not_get_replaced_with_empty_board(self):
        self.path.write_text("broken")
        with self.assertRaises(ValueError):
            read_board(self.path)
        self.assertEqual(self.path.read_text(), "broken")

    def test_four_route_entry_and_existing_account_navigation(self):
        html = render_research_board("test-session")
        for route in ("today", "portfolio", "lookup", "review"):
            self.assertIn(f'data-route="{route}"', html)
        self.assertIn('href="/portfolio-import"', html)
        self.assertIn('href="/report#portfolio"', html)
        self.assertEqual(html.count("test-session"), 1)

    def test_missing_url_does_not_drop_readable_archive_evidence(self):
        board = _read(self.path)
        card = board["cards"][0]
        card["job"] = {"status": "running", "mode": "offline"}
        _write(self.path, board)
        root = Path(self.temp.name)
        run_id = "20261025-001333-abcd1234"
        folder = root / "runtime" / "runs" / run_id
        (folder / "evidence").mkdir(parents=True)
        (folder / "state.json").write_text(json.dumps({"status": "EVIDENCE_ONLY"}))
        (folder / "answer.json").write_text("null")
        (folder / "evidence" / "E0001.json").write_text(json.dumps({"tool": "search_archive", "result": {
            "source": "news", "items": [{"source_id": "test", "url": None, "excerpt": "synthetic source", "published_at": "2020-01-01"}]}}))
        with patch("stock_assist.research_board.PILOT_ROOT", root), patch("stock_assist.research_board.subprocess.run", return_value=SimpleNamespace(stdout="运行编号："+run_id, returncode=0)):
            _run_research(card, self.path)
        saved = _read(self.path)["cards"][0]
        self.assertEqual(saved["job"]["status"], "completed")
        self.assertEqual(saved["evidence"][0]["url"], "")
        self.assertEqual(len(saved["gaps"]), 3)


class DiscoveryTests(unittest.TestCase):
    def sample(self):
        packet = {"cutoff": "2026-10-24T20:00:00+08:00", "items": [{"id": "D001", "source_id": "post-1", "text": "合成样例900001披露新的业务线索", "title": "样例来源", "source": "news", "author": "test", "url": "https://example.com/news", "published_at": "2026-10-23", "first_seen_at": "2026-10-23"}]}
        answer = {"opportunities": [{"title": "样例新线索", "reason": "需要进一步研究", "keyword": "样例", "symbols": ["900001"], "evidence_ids": ["D001"], "counter_evidence_ids": [], "next_check": "核验公告原文"}], "risks": [], "summary": "仅为有限材料"}
        return packet, answer

    def test_fabricated_citations_and_symbols_fail_closed(self):
        packet, answer = self.sample()
        self.assertEqual(validate(answer, packet), answer)
        answer["opportunities"][0]["evidence_ids"] = ["D999"]
        with self.assertRaisesRegex(ValueError, "CITATION"):
            validate(answer, packet)
        answer["opportunities"][0]["evidence_ids"] = ["D001"]
        answer["opportunities"][0]["symbols"] = ["900002"]
        with self.assertRaisesRegex(ValueError, "SYMBOL"):
            validate(answer, packet)

    def test_empty_result_is_valid_and_creates_no_fake_card(self):
        packet, _ = self.sample()
        answer = {"opportunities": [], "risks": [], "summary": "证据不足"}
        validate(answer, packet)
        board = {"cards": [], "events": [], "revision": 0}
        _import_discoveries(board, {"answer": answer, "packet": packet}, "test")
        self.assertEqual(board["cards"], [])

    def test_quarantine_retains_theme_without_invented_instrument(self):
        packet, raw = self.sample()
        raw["opportunities"][0]["symbols"] = ["900002"]
        checked, warnings = quarantine_unsupported_symbols(raw, packet)
        self.assertEqual(checked["opportunities"][0]["symbols"], [])
        self.assertEqual(raw["opportunities"][0]["symbols"], ["900002"])
        self.assertEqual(len(warnings), 1)

    def test_discovery_update_preserves_edited_conditions_and_manual_case(self):
        packet, answer = self.sample()
        board = {"cards": [], "events": [], "revision": 0}
        _import_discoveries(board, {"answer": answer, "packet": packet}, "test1")
        card = board["cards"][0]
        card["entry"] = "用户定义条件"
        before = deepcopy(card["history"][0])
        _import_discoveries(board, {"answer": answer, "packet": packet}, "test2")
        self.assertEqual(len(board["cards"]), 1)
        self.assertEqual(card["entry"], "用户定义条件")
        self.assertEqual(card["history"][0], before)
        self.assertEqual(len(card["evidence"]), 2)
        self.assertEqual({e["run_id"] for e in card["evidence"]}, {"test1", "test2"})
        revision = board["revision"]
        _import_discoveries(board, {"answer": answer, "packet": packet}, "test2")
        self.assertEqual(board["revision"], revision)
        self.assertEqual(len(card["evidence"]), 2)

    def test_collection_cutoff_and_diversity_without_theme_filter(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "nga.db"
            conn = sqlite3.connect(p)
            conn.execute("CREATE TABLE posts(tid,identity,content_text,author_uid,posted_at,first_seen_at,fetched_at,source_url)")
            for i in range(8):
                conn.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)", (1, str(i), f"与任何预置题材无关的合成业务材料足够长文本{i}" * 3, "A" if i<6 else "B", "2026-10-24T10:00:00+08:00", "2026-10-24T10:01:00+08:00", "2026-10-24T10:01:00+08:00", "https://example.com"))
            conn.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)", (1,"future","未来采集的材料不能被视为当时已知的任何证据","C","2026-10-24T09:00:00+08:00","2026-10-25T10:00:00+08:00","2026-10-25T10:00:00+08:00","https://example.com"))
            conn.commit();conn.close()
            cfg = {"archives": {"nga": str(p), "news": str(Path(root)/"missing"), "xueqiu": str(Path(root)/"missing2")}}
            packet = collect(cfg, "2026-10-24T12:00:00+08:00", calendar={"rows": [{"date": "2026-10-23", "is_open": True}, {"date": "2026-10-24", "is_open": False}]})
            self.assertEqual(len(packet["items"]), 5)
            self.assertNotIn("future", [r["source_id"] for r in packet["items"]])
            self.assertEqual(packet["coverage"][0]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
