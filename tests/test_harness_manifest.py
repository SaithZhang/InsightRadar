from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.harness_eval.manifest import MAX_MANIFEST_BYTES, load_task_manifest
from stock_assist.harness_eval.models import PrivacyClass


REVIEWER_TRADE_INFLECTIONS = (
    "buy",
    "buys",
    "buying",
    "buyer",
    "buyers",
    "sell",
    "sells",
    "selling",
    "seller",
    "sellers",
    "trade",
    "trades",
    "traded",
    "trading",
    "trader",
    "traders",
    "order",
    "orders",
    "ordered",
    "ordering",
    "authorize",
    "authorizes",
    "authorized",
    "authorizing",
    "authorise",
    "authorises",
    "authorised",
    "authorising",
    "authorization",
    "authorizations",
    "authorisation",
    "authorisations",
    "authority",
    "authorities",
)


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "insightradar-harness-task/v1",
        "task_id": "harness-smoke-001",
        "title": "Harness contract smoke",
        "goal": "Validate task, trace, privacy, and checkpoint contracts without a model call.",
        "starting_state": {"references": ["CURRENT_STATE.md"]},
        "context_refs": ["AGENTS.md", "CURRENT_STATE.md"],
        "memory_refs": ["docs/memory/product-state.md"],
        "allowed_tools": ["read_project_files", "write_runtime_artifacts"],
        "budget": {"max_steps": 8, "max_tool_calls": 4, "max_elapsed_seconds": 30},
        "expected_artifacts": ["trace.jsonl", "checkpoint.json", "harness-smoke.md"],
        "acceptance_checks": [
            {"id": "trace", "kind": "file_exists", "target": "trace.jsonl", "expected": "true"},
            {
                "id": "trade",
                "kind": "text_contains",
                "target": "harness-smoke.md",
                "expected": "\u4ea4\u6613\u6743\u9650\uff1anone",
            },
        ],
        "privacy_class": "public",
    }


class HarnessManifestTests(unittest.TestCase):
    def _write(self, root: Path, payload: object) -> Path:
        path = root / "task.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _write_json(self, root: Path, content: str) -> Path:
        path = root / "task.json"
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_valid_manifest_with_structured_no_trade_acceptance(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = load_task_manifest(self._write(Path(tmp), _manifest()))
        self.assertEqual(manifest.task_id, "harness-smoke-001")
        self.assertEqual(manifest.privacy_class, PrivacyClass.PUBLIC)
        self.assertEqual(manifest.starting_state.references, ("CURRENT_STATE.md",))
        self.assertEqual(manifest.budget.max_tool_calls, 4)
        self.assertEqual(manifest.acceptance_checks[1].expected, "\u4ea4\u6613\u6743\u9650\uff1anone")

    def test_rejects_missing_or_embedded_starting_state(self) -> None:
        payload = _manifest()
        del payload["starting_state"]
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "missing required field"):
                load_task_manifest(self._write(Path(tmp), payload))

        payload = _manifest()
        payload["starting_state"] = {
            "references": ["CURRENT_STATE.md"],
            "snapshot": {"private": "data"},
        }
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown starting_state field"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_missing_required_field(self) -> None:
        payload = _manifest()
        del payload["goal"]
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "missing required field goal"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_unknown_privacy_class(self) -> None:
        payload = _manifest()
        payload["privacy_class"] = "internal-ish"
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "invalid privacy_class"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_embedded_secret_keys(self) -> None:
        payload = _manifest()
        payload["api_key"] = "must-not-be-here"
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "forbidden public material"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_unknown_manifest_field(self) -> None:
        payload = _manifest()
        payload["unrecognized"] = "fail closed"
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown manifest field"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_boolean_budget_value(self) -> None:
        payload = _manifest()
        payload["budget"] = {"max_steps": True, "max_tool_calls": 4, "max_elapsed_seconds": 30}
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "budget max_steps must be a positive integer"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_trade_authority_or_unknown_tool(self) -> None:
        for tool in ("execute_trade", "invented_tool"):
            with self.subTest(tool=tool), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload["allowed_tools"] = [tool]
                with self.assertRaisesRegex(ValueError, "unsupported allowed tool|forbidden public material"):
                    load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_unobservable_exit_code_check_in_v1(self) -> None:
        payload = _manifest()
        payload["acceptance_checks"].append(
            {"id": "exit", "kind": "exit_code", "target": "smoke", "expected": "0"}
        )
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "acceptance check kind is invalid"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_rejects_duplicate_json_keys(self) -> None:
        cases = (
            (
                '"task_id": "harness-smoke-001"',
                '"task_id": "first", "task_id": "second"',
            ),
            ('"max_steps": 8', '"max_steps": 8, "max_steps": 9'),
        )
        for original, replacement in cases:
            with self.subTest(original=original), TemporaryDirectory() as tmp:
                content = json.dumps(_manifest()).replace(original, replacement)
                with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                    load_task_manifest(self._write_json(Path(tmp), content))

    def test_public_manifest_rejects_paths_credentials_and_material_without_echo(self) -> None:
        marker = "PRIVATE-MARKER-9981"
        credential = "github_pat_" + "a" * 22 + "_" + "b" * 59
        cases = (
            ("goal", credential),
            ("title", f"C:\\Users\\Saith\\{marker}\\broker.tsv"),
            ("context_refs", [f"//server/{marker}/raw.json"]),
            ("memory_refs", [f"docs/../{marker}.json"]),
            ("goal", f"raw conversation {marker}"),
            ("goal", f"chain of thought {marker}"),
            ("goal", f"execute trade {marker}"),
        )
        for field, value in cases:
            with self.subTest(field=field), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload[field] = value
                with self.assertRaisesRegex(
                    ValueError, "forbidden public material|bounded public project references"
                ) as caught:
                    load_task_manifest(self._write(Path(tmp), payload))
                self.assertNotIn(marker, str(caught.exception))
                self.assertNotIn(credential, str(caught.exception))

    def test_public_free_text_rejects_any_trade_or_authority_lexeme(self) -> None:
        forbidden = (
            "Refuse to buy 100 shares when evidence is missing.",
            "Compare buy-side and sell-side research.",
            "Seek stakeholder buy-in.",
            "Do not execute trade when evidence is stale.",
            "Never place order without explicit authority.",
            "No trading authorization.",
            "No trade authority.",
            "Trade authority: none or full.",
            "Never buy 100 shares; never submit order.",
            "\u4e0d\u4e70\u5165100\u80a1\u3002",
            "\u4e0d\u5356\u51fa100\u80a1\u3002",
            "\u4e0d\u4e0b\u5355\u3002",
            "\u7981\u6b62\u4ea4\u6613\u3002",
            "\u4ea4\u6613\u6743\u9650\uff1anone\u3002",
            "\u4e0d\u8c03\u7528\u6a21\u578b\u5e76\u4e14\u4e0d\u4ea4\u6613\u3002",
        )
        for field in ("title", "goal"):
            for text in forbidden:
                with self.subTest(field=field, text=text), TemporaryDirectory() as tmp:
                    payload = _manifest()
                    payload[field] = text
                    with self.assertRaisesRegex(ValueError, "forbidden public material"):
                        load_task_manifest(self._write(Path(tmp), payload))

        payload = _manifest()
        payload["acceptance_checks"][0]["expected"] = "Never execute trade."
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "forbidden public material"):
                load_task_manifest(self._write(Path(tmp), payload))

    def test_public_free_text_rejects_bounded_reviewer_inflections_and_hyphen_compounds(self) -> None:
        for lexeme in REVIEWER_TRADE_INFLECTIONS:
            for text in (f"Review {lexeme} evidence.", f"Review {lexeme}-side evidence."):
                with self.subTest(lexeme=lexeme, text=text), TemporaryDirectory() as tmp:
                    payload = _manifest()
                    payload["goal"] = text
                    with self.assertRaisesRegex(ValueError, "forbidden public material"):
                        load_task_manifest(self._write(Path(tmp), payload))

        for safe_word in ("traditional", "orderly", "inventory"):
            with self.subTest(safe_word=safe_word), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload["goal"] = f"Review {safe_word} evidence."
                manifest = load_task_manifest(self._write(Path(tmp), payload))
                self.assertEqual(manifest.goal, payload["goal"])

        for unsafe_text in ("Review authorised evidence.", "Use authority-free wording."):
            with self.subTest(unsafe_text=unsafe_text), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload["goal"] = unsafe_text
                with self.assertRaisesRegex(ValueError, "forbidden public material"):
                    load_task_manifest(self._write(Path(tmp), payload))

    def test_public_strings_reject_sensitive_assignments_and_private_phrases(self) -> None:
        assignments = (
            "password=hunter2",
            "Pass-Wd: hunter2",
            "pwd = hunter2",
            "token: abc",
            "secret=abc",
            "api_key: abc",
            "access-key = abc",
            "credential: abc",
            "session_id=abc",
            "account identifier: abc",
            "account_id=abc",
            "account: abc",
        )
        private_phrases = (
            "holdings snapshot",
            "open positions",
            "100 shares",
            "broker export",
            "broker account",
            "account identifier",
            "cost basis",
            "personal risk",
            "risk profile",
            "risk tolerance",
            "raw conversation",
            "chat history",
            "hidden reasoning",
            "chain of thought",
            "\u6301\u4ed3\u5feb\u7167",
            "\u5238\u5546\u5bfc\u51fa",
            "\u6210\u672c\u4ef7",
            "\u539f\u59cb\u5bf9\u8bdd",
            "\u601d\u7ef4\u94fe",
        )
        for privacy_class in ("public", "sanitized"):
            for text in assignments + private_phrases:
                with self.subTest(privacy_class=privacy_class, text=text), TemporaryDirectory() as tmp:
                    payload = _manifest()
                    payload["privacy_class"] = privacy_class
                    payload["acceptance_checks"][0]["expected"] = text
                    with self.assertRaisesRegex(ValueError, "forbidden public material") as caught:
                        load_task_manifest(self._write(Path(tmp), payload))
                    self.assertNotIn(text, str(caught.exception))

    def test_public_project_references_use_allowlist_but_private_refs_stay_bounded(self) -> None:
        allowed = (
            ".codex/agents/researcher.toml",
            "configs/harness_eval/smoke_task.json",
            "docs/harness.md",
            "stock_assist/harness_eval/manifest.py",
            "tests/test_harness_manifest.py",
            "AGENTS.md",
            "PROJECT_MEMORY.md",
            "CURRENT_STATE.md",
            "feature_list.json",
            "progress.md",
            "session-handoff.md",
        )
        for reference in allowed:
            with self.subTest(reference=reference), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload["context_refs"] = [reference]
                manifest = load_task_manifest(self._write(Path(tmp), payload))
                self.assertEqual(manifest.context_refs, (reference,))

        rejected = (
            "data/private.json",
            "reports/latest.md",
            "portfolio.manual.tsv",
            "broker/export.tsv",
            "risk_profile.json",
            "README.md",
            "scripts/probe.py",
        )
        for reference in rejected:
            with self.subTest(reference=reference), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload["memory_refs"] = [reference]
                with self.assertRaisesRegex(
                    ValueError,
                    "bounded public project references|forbidden public material",
                ):
                    load_task_manifest(self._write(Path(tmp), payload))

        private_payload = _manifest()
        private_payload["privacy_class"] = "private"
        private_payload["context_refs"] = ["data/private.json", "reports/latest.md"]
        with TemporaryDirectory() as tmp:
            manifest = load_task_manifest(self._write(Path(tmp), private_payload))
        self.assertEqual(manifest.context_refs, ("data/private.json", "reports/latest.md"))

    def test_private_manifest_stays_local_and_sanitized_label_alone_is_rejected(self) -> None:
        private_payload = _manifest()
        private_payload["privacy_class"] = "private"
        private_payload["goal"] = "Review a private broker account locally."
        with TemporaryDirectory() as tmp:
            manifest = load_task_manifest(self._write(Path(tmp), private_payload))
        self.assertEqual(manifest.privacy_class, PrivacyClass.PRIVATE)

        sanitized_payload = _manifest()
        sanitized_payload["privacy_class"] = "sanitized"
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "verified transformation record"):
                load_task_manifest(self._write(Path(tmp), sanitized_payload))

    def test_identifiers_references_and_containers_are_bounded_and_duplicate_free(self) -> None:
        cases = (
            ("task_id", "9-invalid"),
            ("context_refs", ["AGENTS.md"] * 17),
            ("memory_refs", ["docs/memory/product-state.md"] * 2),
            ("expected_artifacts", ["trace.jsonl", "trace.jsonl"]),
        )
        for field, value in cases:
            with self.subTest(field=field), TemporaryDirectory() as tmp:
                payload = _manifest()
                payload[field] = value
                with self.assertRaises(ValueError):
                    load_task_manifest(self._write(Path(tmp), payload))

    def test_manifest_reads_once_with_exact_size_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), _manifest())
            raw = path.read_bytes()
            path.write_bytes(raw + b" " * (MAX_MANIFEST_BYTES - len(raw)))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded helper used")):
                manifest = load_task_manifest(path)
            self.assertEqual(manifest.task_id, "harness-smoke-001")
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "maximum size"):
                load_task_manifest(path)


if __name__ == "__main__":
    unittest.main()
