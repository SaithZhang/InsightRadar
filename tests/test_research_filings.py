from __future__ import annotations

import base64
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from stock_assist import research_board as board
from stock_assist import research_filings as filings


SYMBOL = "900001"
PDF = b"%PDF-1.7 synthetic input"
ORIGIN = "http://127.0.0.1:8765"
PERIODS = ("2025-01-01/2025-09-30", "2024-01-01/2024-09-30")
SOURCE = "https://static.cninfo.com.cn/finalpage/2025-10-30/example.pdf"
PROFIT = "归属于上市公司股东的净利润（元） 1,200.25 1,000.25"
CASH = "经营活动产生的现金流量净额（元） 80.50 100.50"


def context():
    return {"symbol": SYMBOL, "thesis": {"text": "检查利润与现金流", "as_of": "2025-10-01", "url": SOURCE},
            "holding": {"as_of": "2025-10-01", "url": SOURCE}}


def answer():
    common = {"page": 1, "period": PERIODS[0], "comparison_period": PERIODS[1], "unit": "元"}
    return {"symbol": SYMBOL,
            "net_profit": {**common, "current": "1200.25", "previous": "1000.25", "quote": PROFIT},
            "operating_cash_flow": {**common, "current": "80.50", "previous": "100.50", "quote": CASH},
            "explanation": None}


def packet(result=None, text=PROFIT + "\n" + CASH):
    return filings.make_packet({"published_at": "2025-10-30", "total_pages": 1}, context(),
                               {1: text}, PERIODS, result if result is not None else answer(), SOURCE)


class FilingEvidenceTests(unittest.TestCase):
    def test_only_official_pdf_links_and_matching_disclosure_date(self):
        self.assertEqual(filings.normalize_input({"url": SOURCE})[0]["published_at"], "2025-10-30")
        for url in ("http://static.cninfo.com.cn/a.pdf", "https://127.0.0.1/a.pdf",
                    "https://static.cninfo.com.cn@localhost/a.pdf", SOURCE + "?token=x"):
            with self.assertRaises(ValueError):
                filings.normalize_input({"url": url})
        with self.assertRaisesRegex(ValueError, "不符"):
            filings.normalize_input({"url": SOURCE, "published_at": "2025-11-01"})

    def test_identity_and_supported_period_come_from_document(self):
        pages = ["证券代码：900001\n合成公司 2025年第三季度报告"]
        self.assertEqual(filings.identify(pages, SYMBOL), PERIODS)
        with self.assertRaisesRegex(ValueError, "证券代码"):
            filings.identify(pages, "900002")
        self.assertIsNone(filings.identify(["证券代码：900001\n回购进展公告"], SYMBOL))

    def test_wrong_quote_period_currency_or_value_order_rejected(self):
        self.assertEqual(filings.evaluate_change(packet())["status"], "needs_review")
        formatted = answer()
        formatted["net_profit"].update(current="1,200.25", previous="1,000.25")
        self.assertEqual(packet(formatted)["metrics"]["net_profit"]["current"], "1200.25")
        for change in ({"quote": PROFIT + "编造"}, {"period": "2025-07-01/2025-09-30"},
                       {"unit": "万元"}, {"current": "1000.25", "previous": "1200.25"}):
            candidate = answer()
            candidate["net_profit"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                packet(candidate)
        candidate = answer()
        candidate["net_profit"]["quote"] = PROFIT.replace("（元）", "（万元）")
        candidate["operating_cash_flow"]["quote"] = CASH.replace("（元）", "（万元）")
        with self.assertRaisesRegex(ValueError, "计量"):
            packet(candidate, (PROFIT + "\n" + CASH).replace("（元）", "（万元）"))

    def test_missing_report_metrics_do_not_yield_no_change(self):
        self.assertEqual(filings.evaluate_change(packet({"symbol": SYMBOL}))["status"],
                         "insufficient_coverage")

    def test_continued_profit_table_keeps_preceding_header(self):
        pages = ["证券代码：900001", "合并利润表\n单位：元\n2025 年前三季度 / 2024 年前三季度", PROFIT]
        self.assertEqual(list(filings.evidence_pages(pages)), [1, 2, 3])

    def test_variant_continuation_header_keeps_row_under_context_limit(self):
        header = "2、合并年初到报告期末利润表\n单位：元\n项目 本期发生额 上期发生额"
        padding = "主要会计数据\n" + "附" * 1800
        pages = ["证券代码：900001", "上一张报表末尾\n" + header + "\n营业成本 100 200",
                 PROFIT, padding, padding, padding, padding]
        selected = filings.evidence_pages(pages)
        self.assertEqual(selected[2], header)
        self.assertEqual(selected[3], PROFIT)
        self.assertLessEqual(sum(len(text.encode()) for text in selected.values()), 21_000)

    def test_budget_slots_are_durable_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expiry = (datetime.now(filings.TZ) + timedelta(minutes=1)).isoformat()
            filings.save_json(root / "budget.json", {"expires_at": expiry, "model": filings.MODEL,
                              "max_calls": 15, "max_usd": 3})
            for slot in range(1, 16):
                receipt = filings._reserve(root, f"run-{slot}", 30_000)
                self.assertEqual(json.loads(receipt.read_text())["status"], "attempted")
            with self.assertRaisesRegex(ValueError, "已达上限"):
                filings._reserve(root, "extra", 1)
            with self.assertRaisesRegex(ValueError, "单次"):
                filings._reserve(root, "oversize", 100_000)


class FilingLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "board.json"
        self.addCleanup(board._RUNNING.clear)
        self.card_id = board.mutate({"revision": 0, "action": "create", "question": "检查公告",
                                     "symbols": [SYMBOL], "valid_until": "2030-01-01"}, self.path)["card_id"]
        board.mutate({"revision": 1, "action": "revise", "card_id": self.card_id,
                      "note": "写入理由", "thesis": context()["thesis"]["text"]}, self.path)
        self.body = {"revision": 2, "card_id": self.card_id, "pdf": base64.b64encode(PDF).decode(),
                     "published_at": "2025-10-30", "thesis_as_of": "2025-10-01", "thesis_url": SOURCE,
                     "holding_as_of": "2025-10-01", "holding_url": SOURCE}

    def run_draft(self):
        with patch.object(board.threading, "Thread") as thread:
            start = board.start_filing(self.body, ORIGIN, self.path)
        folder = board._filing_folder(self.path, start["run_id"])
        draft = {"run_id": start["run_id"], "packet": packet(), "assessment": filings.evaluate_change(packet()),
                 "source": {"sha256": "a" * 64, "received_at": filings.timestamp(),
                            "published_at": "2025-10-30"}, "model": {"returned_model": "test"}}
        filings.save_json(folder / "draft.json", draft)
        with patch.object(filings, "prepare_draft", return_value=draft):
            board._run_filing(*thread.call_args.kwargs["args"])
        return start

    def test_draft_retry_adopt_and_stale_retry(self):
        before = deepcopy(board._read(self.path)["cards"][0]["history"])
        start = self.run_draft()
        state = board.read_board(self.path)
        self.assertEqual(state["cards"][0]["history"], before)
        self.assertNotIn("change_check", state["cards"][0])
        self.assertTrue(state["cards"][0]["filing_draft"]["can_adopt"])
        self.assertTrue(board.start_filing(self.body, ORIGIN, self.path)["unchanged"])
        adopt = {"revision": state["revision"], "action": "adopt_filing", "card_id": self.card_id,
                 "run_id": start["run_id"], "reviewed": False}
        with self.assertRaisesRegex(ValueError, "确认"):
            board.mutate(adopt, self.path)
        adopt["reviewed"] = True
        board.mutate(adopt, self.path)
        self.assertTrue(board.mutate(adopt, self.path)["unchanged"])
        self.assertTrue(board.start_filing(self.body, ORIGIN, self.path)["unchanged"])
        current = board.read_board(self.path)["cards"][0]
        self.assertEqual(current["history"][:-1], before)
        self.assertEqual(current["change_check"]["filing"]["run_id"], start["run_id"])

    def test_restart_recovers_running_job_without_redispatch(self):
        with patch.object(board.threading, "Thread") as thread:
            start = board.start_filing(self.body, ORIGIN, self.path)
            board._RUNNING.clear()
            recovered = board.read_board(self.path)["cards"][0]
            self.assertEqual(recovered["job"]["status"], "interrupted")
            retry = board.start_filing({**self.body, "revision": board._read(self.path)["revision"]},
                                       ORIGIN, self.path)
            self.assertTrue(retry["unchanged"])
            self.assertEqual(thread.call_count, 1)
        self.assertEqual(recovered["job"]["run_id"], start["run_id"])
        self.assertNotIn("change_check", recovered)
