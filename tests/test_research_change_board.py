from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stock_assist.research_board import _read, mutate, read_board
from stock_assist.research_changes import evaluate_change
from tests.test_research_changes import NOW, sample, set_cashflow


class ChangeBoardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "board.json"
        self.clock = patch("stock_assist.research_board.now", return_value=NOW.isoformat())
        self.clock.start()
        self.addCleanup(self.clock.stop)
        evaluator = patch("stock_assist.research_board.evaluate_change",
                          side_effect=lambda payload: evaluate_change(payload, current_time=NOW))
        evaluator.start()
        self.addCleanup(evaluator.stop)
        self.card_id = mutate({"action": "create", "revision": 0, "title": "合成财报变化研究",
                               "question": "合成标的的盈利和回款是否需要复核？", "keyword": "合成",
                               "symbols": ["900001"], "valid_until": "2026-12-31"}, self.path)["card_id"]
        mutate({"action": "revise", "revision": self.revision(), "card_id": self.card_id,
                "thesis": sample()["thesis"]["text"], "note": "保存合成研究理由"}, self.path)

    def revision(self):
        return _read(self.path)["revision"]

    def packet(self):
        historical = sample()
        historical["mode"] = "historical_validation"
        set_cashflow(historical, "150", "100")
        missing = sample()
        missing.update(mode="missing_source_validation", sources=[], metrics={})
        missing.pop("explanation")
        missing["coverage"]["status"] = "unavailable"
        return {"assessment": sample(), "validation_cases": [historical, missing]}

    def save(self, packet=None, revision=None):
        return mutate({"action": "change_check", "card_id": self.card_id,
                       "revision": self.revision() if revision is None else revision,
                       "packet": self.packet() if packet is None else packet}, self.path)

    def test_three_states_persist_with_provenance_and_immutable_history(self):
        self.save()
        saved = _read(self.path)
        card = saved["cards"][0]
        check = card["change_check"]
        self.assertEqual(check["assessment"]["status"], "needs_review")
        self.assertEqual([case["status"] for case in check["validation_cases"]],
                         ["no_material_change", "insufficient_coverage"])
        self.assertEqual(card["origin"], "holding_change")
        self.assertEqual(check["assessment"]["holding"]["url"], "https://example.com/holding")
        self.assertEqual(check["assessment"]["trade_authority"], "none")
        historical = deepcopy(card["history"])
        packet = self.packet()
        packet["assessment"]["coverage"]["note"] = "再次核对同一来源，记录新的检查说明"
        self.save(packet)
        updated = _read(self.path)["cards"][0]
        self.assertEqual(updated["history"][:-1], historical)
        self.assertEqual(updated["version"], card["version"] + 1)
        self.assertNotEqual(updated["change_check"]["assessment"]["fingerprint"],
                            historical[-1]["snapshot"]["change_check"]["assessment"]["fingerprint"])

    def test_exact_retry_with_stale_revision_does_not_rewrite_file(self):
        old_revision = self.revision()
        first = self.save(revision=old_revision)
        raw = self.path.read_bytes()
        read_board(self.path)
        repeat = self.save(revision=old_revision)
        self.assertTrue(repeat["unchanged"])
        self.assertFalse(first["unchanged"])
        self.assertEqual(repeat["revision"], first["revision"])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(len(_read(self.path)["cards"]), 1)

    def test_different_packet_with_stale_revision_is_rejected_atomically(self):
        old_revision = self.revision()
        self.save(revision=old_revision)
        raw = self.path.read_bytes()
        packet = self.packet()
        packet["assessment"]["scope"] += "，增加新的核验说明"
        with self.assertRaisesRegex(ValueError, "新版本"):
            self.save(packet, revision=old_revision)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_other_symbol_or_thesis_cannot_be_saved(self):
        self.save()
        raw = self.path.read_bytes()
        for field in ("symbol", "thesis"):
            with self.subTest(field=field):
                packet = self.packet()
                if field == "symbol":
                    packet["assessment"]["symbol"] = "900002"
                else:
                    packet["assessment"]["thesis"]["text"] = "另一个合成研究理由"
                with self.assertRaisesRegex(ValueError, "标的或研究理由不一致"):
                    self.save(packet)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_historical_case_cannot_replace_actual_assessment(self):
        self.save()
        raw = self.path.read_bytes()
        packet = self.packet()
        packet["assessment"] = deepcopy(packet["validation_cases"][0])
        with self.assertRaisesRegex(ValueError, "实际材料复核"):
            self.save(packet)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_validation_cases_must_remain_scoped_and_labelled(self):
        raw = self.path.read_bytes()
        for defect in ("live_mode", "thesis_source", "other_symbol", "too_many"):
            with self.subTest(defect=defect):
                packet = self.packet()
                case = packet["validation_cases"][0]
                if defect == "live_mode":
                    case["mode"] = "live_review"
                elif defect == "thesis_source":
                    case["thesis"]["url"] = "https://example.com/other-thesis"
                elif defect == "other_symbol":
                    case["symbol"] = "900002"
                else:
                    packet["validation_cases"].append(deepcopy(case))
                with self.assertRaises(ValueError):
                    self.save(packet)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_read_marks_previous_day_stale_without_rewriting_history(self):
        self.save()
        self.assertFalse(read_board(self.path)["cards"][0]["change_check"]["stale"])
        raw = self.path.read_bytes()
        with patch("stock_assist.research_board.now", return_value="2026-11-08T00:01:00+08:00"):
            self.assertTrue(read_board(self.path)["cards"][0]["change_check"]["stale"])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertNotIn("stale", _read(self.path)["cards"][0]["change_check"])

    def test_changed_thesis_invalidates_current_assessment_and_blocks_old_retry(self):
        old_revision = self.revision()
        self.save()
        original_check = deepcopy(_read(self.path)["cards"][0]["change_check"])
        mutate({"action": "revise", "card_id": self.card_id, "revision": self.revision(),
                "thesis": "合成的新研究理由", "note": "研究理由发生变化"}, self.path)
        self.assertTrue(read_board(self.path)["cards"][0]["change_check"]["stale"])
        self.assertEqual(_read(self.path)["cards"][0]["change_check"], original_check)
        raw = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "标的或研究理由不一致"):
            self.save(revision=old_revision)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_changed_symbols_invalidate_assessment(self):
        self.save()
        mutate({"action": "revise", "card_id": self.card_id, "revision": self.revision(),
                "symbols": ["900002"], "note": "更换合成研究标的"}, self.path)
        self.assertTrue(read_board(self.path)["cards"][0]["change_check"]["stale"])

    def test_invalid_financial_packet_cannot_partially_save(self):
        self.save()
        raw = self.path.read_bytes()
        packet = self.packet()
        packet["validation_cases"][0]["metrics"]["net_profit"]["current"] = "999999"
        with self.assertRaisesRegex(ValueError, "完整出现在引用摘句"):
            self.save(packet)
        self.assertEqual(self.path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
