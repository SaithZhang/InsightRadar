from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.harness_eval.models import PrivacyClass
from stock_assist.harness_eval.trace import MAX_EVENTS, MAX_FILE_BYTES, MAX_LINE_BYTES, TraceWriter, validate_public_trace


NOW = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)
CREDENTIAL_REFERENCES = {
    "github_classic": "ghp_" + "a" * 36,
    "github_fine_grained": "github_pat_" + "a" * 22 + "_" + "b" * 59,
    "gitlab": "glpat-" + "a" * 20,
    "slack_bot": "xoxb-" + "1" * 12 + "-" + "a" * 24,
    "slack_user": "xoxp-" + "1" * 12 + "-" + "a" * 24,
    "aws_long_term": "AKIA" + "A" * 16,
    "aws_temporary": "ASIA" + "A" * 16,
    "google_api": "AIza" + "a" * 35,
    "npm": "npm_" + "a" * 36,
}


def _event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": "insightradar-harness-trace/v1",
        "run_id": "run-001",
        "sequence": 1,
        "event_type": "run_started",
        "occurred_at": NOW.isoformat(),
        "privacy_class": "public",
        "payload": {"task_id": "task-1"},
    }
    event.update(overrides)
    return event


def _write_rows(path: Path, rows: list[object]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows), encoding="utf-8")


class HarnessTraceTests(unittest.TestCase):
    def _writer(self, tmp: str, name: str = "trace.jsonl", run_id: str = "run-001") -> TraceWriter:
        root = Path(tmp) / "runtime"
        root.mkdir(exist_ok=True)
        return TraceWriter(root, Path(name), run_id, clock=lambda: NOW)

    def test_writer_assigns_monotonic_sequence_and_version(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            first = writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            second = writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            rows = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
            errors = validate_public_trace(writer.path)
            writer.close()
        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(rows[0]["schema_version"], "insightradar-harness-trace/v1")
        self.assertEqual(errors, [])

    def test_v1_writer_and_validator_reject_sanitized_without_transformation_record(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            try:
                with self.assertRaisesRegex(ValueError, "v1 traces require public privacy class"):
                    writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.SANITIZED)
                self.assertFalse(writer.path.exists())
            finally:
                writer.close()

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            _write_rows(
                path,
                [
                    _event(privacy_class="sanitized"),
                    _event(sequence=2, event_type="run_completed", payload={"status": "pass"}),
                ],
            )
            errors = validate_public_trace(path)
        self.assertTrue(any("v1 traces require public privacy class" in error for error in errors), errors)

    def test_writer_enforces_exact_maximum_event_boundary_before_append(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            for _ in range(2, MAX_EVENTS):
                writer.append(
                    "verification_result",
                    {"check": "event_budget", "status": "pass"},
                    PrivacyClass.PUBLIC,
                )
            final = writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            self.assertEqual(final.sequence, MAX_EVENTS)
            self.assertEqual(validate_public_trace(writer.path), [])
            writer.close()

        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            try:
                writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
                for _ in range(1, MAX_EVENTS):
                    writer.append(
                        "verification_result",
                        {"check": "event_budget", "status": "pass"},
                        PrivacyClass.PUBLIC,
                    )
                before = writer.path.read_bytes()
                with self.assertRaisesRegex(ValueError, "trace exceeds maximum event count"):
                    writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
                self.assertEqual(writer.sequence, MAX_EVENTS)
                self.assertEqual(writer.path.read_bytes(), before)
                self.assertEqual(validate_public_trace(writer.path, require_completed=False), [])
            finally:
                writer.close()

    def test_closed_schemas_accept_planned_task_7_smoke_events(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "harness-smoke-001"}, PrivacyClass.PUBLIC)
            writer.append(
                "context_loaded",
                {
                    "starting_state_refs": ["CURRENT_STATE.md"],
                    "context_refs": ["AGENTS.md", "CURRENT_STATE.md"],
                    "memory_refs": ["docs/memory/product-state.md"],
                },
                PrivacyClass.PUBLIC,
            )
            writer.append("checkpoint_saved", {"checkpoint_ref": "checkpoint.json"}, PrivacyClass.PUBLIC)
            writer.append("checkpoint_restored", {"verified_steps": ["manifest_loaded", "context_refs_recorded"]}, PrivacyClass.PUBLIC)
            writer.append(
                "verification_result",
                {"check": "checkpoint_goal_continuity", "status": "pass"},
                PrivacyClass.PUBLIC,
            )
            writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            errors = validate_public_trace(writer.path)
            writer.close()
        self.assertEqual(errors, [])

    def test_writer_and_public_validation_reject_standard_credential_references(self) -> None:
        for kind, credential in CREDENTIAL_REFERENCES.items():
            with self.subTest(kind=kind), TemporaryDirectory() as tmp:
                writer = self._writer(tmp)
                writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
                try:
                    with self.assertRaisesRegex(ValueError, "credential-like value"):
                        writer.append(
                            "context_loaded",
                            {"starting_state_refs": ["CURRENT_STATE.md"], "context_refs": [credential], "memory_refs": []},
                            PrivacyClass.PUBLIC,
                        )
                finally:
                    writer.close()

            with self.subTest(kind=f"public-{kind}"), TemporaryDirectory() as tmp:
                path = Path(tmp) / "trace.jsonl"
                _write_rows(
                    path,
                    [
                        _event(),
                        _event(
                            sequence=2,
                            event_type="context_loaded",
                            payload={"starting_state_refs": ["CURRENT_STATE.md"], "context_refs": [credential], "memory_refs": []},
                        ),
                        _event(sequence=3, event_type="run_completed", payload={"status": "pass"}),
                    ],
                )
                errors = validate_public_trace(path)
                self.assertTrue(any("credential-like value" in error for error in errors), errors)
                self.assertNotIn(credential, "\n".join(errors))

    def test_safe_relative_references_and_sha256_named_artifact_still_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            writer.append(
                "context_loaded",
                {
                    "starting_state_refs": ["CURRENT_STATE.md"],
                    "context_refs": ["AGENTS.md", "artifacts/trace.sha256"],
                    "memory_refs": ["docs/memory/product-state.md"],
                },
                PrivacyClass.PUBLIC,
            )
            writer.append("checkpoint_saved", {"checkpoint_ref": "checkpoint.json"}, PrivacyClass.PUBLIC)
            writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            errors = validate_public_trace(writer.path)
            writer.close()
        self.assertEqual(errors, [])

    def test_writer_rejects_secret_private_reasoning_and_trade_material(self) -> None:
        cases = (
            ({"token": "secret"}, "sensitive key"),
            ({"portfolio": "private"}, "private key"),
            ({"chain_of_thought": "hidden"}, "hidden reasoning key"),
            ({"trade_authority": "none"}, "trade authority key"),
            ({"status": "sessionid=abcdef123456"}, "sensitive assignment"),
            ({"status": "execute-trade"}, "trade authority lexeme"),
        )
        with TemporaryDirectory() as tmp:
            for payload, message in cases:
                with self.subTest(payload=payload):
                    writer = self._writer(tmp, name=f"{len(payload)}-{message[:4]}.jsonl")
                    with self.assertRaisesRegex(ValueError, message):
                        writer.append("tool_completed", payload, PrivacyClass.PUBLIC)

    def test_public_validation_rejects_review_bypass_payloads_and_run_ids(self) -> None:
        payloads = (
            {"to-ken": "secret"},
            {"锝旓綇锝嬶絽锝?": "secret"},
            {"details": {"id": "BROKER-123456"}},
            {"positions": [{"symbol": "300308.SZ", "shares": 4200}]},
            {"purchase_price": 12.34},
            {"loss_tolerance": "low"},
            {"messages": [{"role": "user", "content": "my private prompt"}]},
            {"analysis": "private hidden rationale"},
            {"status": "sessionid=abcdef123456"},
            {"reference": "https://user:password@example.test/private?token=abcdef"},
            {"artifact": "text C:\\Users\\Saith\\private.txt"},
            {"artifact": "  /private/portfolio.json"},
            {"action": "BUY 100 shares"},
            {"status": "execute-trade"},
            {"action": "下单买入"},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "trace.jsonl"
                    _write_rows(path, [_event(payload=payload)])
                    self.assertTrue(validate_public_trace(path))
        for run_id in ("Bearer abcdefghijklmnop", "C:\\Users\\Saith\\private"):
            with self.subTest(run_id=run_id):
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "trace.jsonl"
                    _write_rows(path, [_event(run_id=run_id)])
                    self.assertTrue(validate_public_trace(path))

    def test_event_snapshot_is_immutable_and_independent_of_nested_caller_mutation(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            source = {
                "starting_state_refs": ["CURRENT_STATE.md"],
                "context_refs": ["AGENTS.md"],
                "memory_refs": ["docs/memory/product-state.md"],
            }
            event = writer.append("context_loaded", source, PrivacyClass.PUBLIC)
            source["context_refs"].append("private.txt")
            source["memory_refs"][0] = "private.txt"
            with self.assertRaises(TypeError):
                event.payload["context_refs"] = ()
            writer.close()
        self.assertEqual(event.payload["context_refs"], ("AGENTS.md",))
        self.assertEqual(event.payload["memory_refs"], ("docs/memory/product-state.md",))

    def test_writer_exclusively_creates_new_trace_and_rejects_reopen_or_partial_path(self) -> None:
        with TemporaryDirectory() as tmp:
            first = self._writer(tmp)
            first.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            with self.assertRaisesRegex(ValueError, "trace target already exists"):
                self._writer(tmp)
            first.close()
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            root.mkdir()
            (root / "trace.jsonl").write_text("{partial", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "trace target already exists"):
                TraceWriter(root, Path("trace.jsonl"), "run-001", clock=lambda: NOW)

    def test_writer_contains_relative_target_under_explicit_runtime_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            root.mkdir()
            writer = TraceWriter(root, Path("run-001") / "trace.jsonl", "run-001", clock=lambda: NOW)
            self.assertTrue(writer.path.is_relative_to(root.resolve()))
            for target in (Path("..") / "escape.jsonl", Path("C:/private.jsonl"), Path("/private.jsonl"), Path("//server/share.jsonl")):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(ValueError, "relative trace path"):
                        TraceWriter(root, target, "run-001", clock=lambda: NOW)

    def test_writer_rejects_replaced_or_hard_linked_target_before_later_append(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            outside = Path(tmp) / "outside.jsonl"
            outside.write_text("outside\n", encoding="utf-8")
            before = outside.read_bytes()
            try:
                writer.path.unlink()
            except PermissionError:
                self.assertEqual(outside.read_bytes(), before)
            else:
                os.link(outside, writer.path)
                with self.assertRaisesRegex(ValueError, "trace target identity changed"):
                    writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            self.assertEqual(outside.read_bytes(), before)
            writer.close()
        with TemporaryDirectory() as tmp:
            writer = self._writer(tmp)
            writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            outside_link = Path(tmp) / "outside-link.jsonl"
            os.link(writer.path, outside_link)
            before = outside_link.read_bytes()
            with self.assertRaisesRegex(ValueError, "trace target identity changed"):
                writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            self.assertEqual(outside_link.read_bytes(), before)
            writer.close()

    def test_public_validation_never_echoes_untrusted_markers(self) -> None:
        marker = "PRIVATE-MARKER-ACCOUNT-9981"
        cases = (
            _event(payload={marker: "secret"}),
            _event(**{marker: "secret"}),
        )
        for row in cases:
            with self.subTest(row=row):
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "trace.jsonl"
                    _write_rows(path, [row])
                    errors = validate_public_trace(path)
                self.assertTrue(errors)
                self.assertNotIn(marker, "\n".join(errors))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text(
                '{"schema_version":"insightradar-harness-trace/v1",'
                f'"{marker}":"one","{marker}":"two"}}\n',
                encoding="utf-8",
            )
            errors = validate_public_trace(path)
        self.assertTrue(any("duplicate JSON key" in error for error in errors), errors)
        self.assertNotIn(marker, "\n".join(errors))

    def test_public_validation_returns_stable_errors_for_invalid_utf8_surrogates_and_depth(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_bytes(b"\xff")
            self.assertEqual(validate_public_trace(path), ["trace invalid utf-8"])
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text(json.dumps(_event(payload={"task_id": "\ud800"}), ensure_ascii=True) + "\n", encoding="utf-8")
            self.assertTrue(any("invalid unicode scalar" in error for error in validate_public_trace(path)))
        nested: object = "leaf"
        for _ in range(20):
            nested = [nested]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            _write_rows(path, [_event(payload={"task_id": nested})])
            self.assertTrue(any("payload exceeds maximum depth" in error for error in validate_public_trace(path)))

    def test_public_validation_rejects_unknown_schema_fields_events_and_malformed_rows(self) -> None:
        cases = (
            (_event(schema_version="future/v2"), "unsupported trace schema_version"),
            (_event(event_type="unknown_event"), "unsupported trace event_type"),
            (_event(unexpected="fail closed"), "unknown trace field"),
            (_event(sequence=True), "sequence must be a positive integer"),
            (_event(payload=[]), "payload must be an object"),
            (_event(occurred_at="not-a-time"), "occurred_at must be an ISO-8601 UTC timestamp"),
            (_event(payload={"artifact": "/private/portfolio.json"}), "invalid payload"),
        )
        for row, message in cases:
            with self.subTest(row=row):
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "trace.jsonl"
                    _write_rows(path, [row])
                    errors = validate_public_trace(path)
                self.assertTrue(any(message in error for error in errors), errors)

    def test_public_validation_rejects_duplicate_keys_nonstandard_json_and_private_events(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text(
                '{"schema_version":"insightradar-harness-trace/v1","schema_version":"insightradar-harness-trace/v1"}\n'
                '{"schema_version":NaN}\n',
                encoding="utf-8",
            )
            errors = validate_public_trace(path)
        self.assertTrue(any("duplicate JSON key" in error for error in errors), errors)
        self.assertTrue(any("non-standard JSON value" in error for error in errors), errors)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            _write_rows(
                path,
                [
                    _event(),
                    _event(sequence=2, event_type="run_completed", payload={"status": "pass"}, privacy_class="private"),
                ],
            )
            self.assertTrue(any("privacy class is not public-exportable" in error for error in validate_public_trace(path)))

    def test_public_validation_enforces_lifecycle_and_nondecreasing_utc_time(self) -> None:
        rows = [
            _event(occurred_at=(NOW + timedelta(hours=1)).isoformat()),
            _event(sequence=2, event_type="run_completed", payload={"status": "pass"}, occurred_at=NOW.isoformat()),
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            _write_rows(path, rows)
            errors = validate_public_trace(path)
        self.assertTrue(any("timestamps must be non-decreasing" in error for error in errors), errors)
        for events, expected in (
            (("run_completed",), "first event must be run_started"),
            (("run_started", "run_started", "run_completed"), "run_started may occur only once"),
            (("run_started", "run_completed", "context_loaded"), "event after run_completed"),
        ):
            with self.subTest(events=events):
                rows = []
                for sequence, event_type in enumerate(events, start=1):
                    payload = {"task_id": "task-1"} if event_type == "run_started" else {"status": "pass"} if event_type == "run_completed" else {"starting_state_refs": [], "context_refs": [], "memory_refs": []}
                    rows.append(_event(sequence=sequence, event_type=event_type, payload=payload))
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "trace.jsonl"
                    _write_rows(path, rows)
                    errors = validate_public_trace(path)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_public_trace_reads_once_at_exact_size_boundary(self) -> None:
        rows = [_event()]
        for sequence in range(2, 64):
            rows.append(
                _event(
                    sequence=sequence,
                    event_type="context_loaded",
                    payload={
                        "starting_state_refs": ["CURRENT_STATE.md"],
                        "context_refs": ["AGENTS.md"],
                        "memory_refs": [],
                    },
                )
            )
        rows.append(_event(sequence=64, event_type="run_completed", payload={"status": "pass"}))
        lines = [json.dumps(row, ensure_ascii=True, separators=(",", ":")) for row in rows]
        remaining = MAX_FILE_BYTES - sum(len(line.encode("utf-8")) + 1 for line in lines)
        self.assertGreaterEqual(remaining, 0)
        for index, line in enumerate(lines):
            capacity = MAX_LINE_BYTES - len(line.encode("utf-8"))
            added = min(remaining, capacity)
            lines[index] = line + " " * added
            remaining -= added
        self.assertEqual(remaining, 0)
        exact = ("\n".join(lines) + "\n").encode("utf-8")
        self.assertEqual(len(exact), MAX_FILE_BYTES)

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_bytes(exact)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded helper used")):
                self.assertEqual(validate_public_trace(path), [])
            path.write_bytes(exact + b" ")
            self.assertEqual(validate_public_trace(path), ["trace exceeds maximum file size"])


if __name__ == "__main__":
    unittest.main()
