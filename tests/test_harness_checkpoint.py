from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.harness_eval import checkpoint as checkpoint_module
from stock_assist.harness_eval import smoke as smoke_module
from stock_assist.harness_eval.checkpoint import (
    Checkpoint,
    MAX_ARTIFACT_HASHES,
    MAX_CHECKPOINT_BYTES,
    MAX_STEPS,
    goal_digest,
    load_checkpoint,
    save_checkpoint,
)
from stock_assist.harness_eval.smoke import run_contract_smoke
from stock_assist.harness_eval.trace import MAX_EVENTS, MAX_FILE_BYTES, validate_public_trace


NOW = datetime(2026, 7, 21, 4, 30, tzinfo=timezone.utc)
MANIFEST = Path(__file__).resolve().parents[1] / "configs" / "harness_eval" / "smoke_task.json"


class HarnessCheckpointTests(unittest.TestCase):
    def _checkpoint(self) -> Checkpoint:
        return Checkpoint(
            schema_version="insightradar-harness-checkpoint/v1",
            run_id="run-001",
            task_id="harness-smoke-001",
            goal_hash=goal_digest("same goal"),
            sequence=3,
            verified_steps=("manifest_loaded",),
            pending_steps=("trace_verified",),
            artifact_hashes={"trace.jsonl": "a" * 64},
            created_at=NOW.isoformat(),
        )

    def test_smoke_trace_hash_uses_the_shared_bounded_reader(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_bytes(b"a" * MAX_FILE_BYTES)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded helper used")):
                digest = smoke_module._sha256(path)
            self.assertEqual(digest, hashlib.sha256(b"a" * MAX_FILE_BYTES).hexdigest())
            path.write_bytes(b"a" * (MAX_FILE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "maximum size"):
                smoke_module._sha256(path)

    def test_atomic_checkpoint_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(self._checkpoint(), path)
            restored = load_checkpoint(path, "harness-smoke-001", "same goal")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])
        self.assertEqual(restored.sequence, 3)
        self.assertEqual(restored.verified_steps, ("manifest_loaded",))

    def test_checkpoint_sequence_is_bounded_by_trace_event_capacity(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sequence in (0, MAX_EVENTS):
                with self.subTest(sequence=sequence):
                    checkpoint = Checkpoint(
                        **{**self._checkpoint().__dict__, "sequence": sequence}
                    )
                    path = root / f"accepted-{sequence}.json"
                    save_checkpoint(checkpoint, path)
                    restored = load_checkpoint(path, "harness-smoke-001", "same goal")
                    self.assertEqual(restored.sequence, sequence)

            for sequence in (MAX_EVENTS + 1, 1_000_000):
                with self.subTest(sequence=sequence):
                    checkpoint = Checkpoint(
                        **{**self._checkpoint().__dict__, "sequence": sequence}
                    )
                    save_path = root / f"rejected-save-{sequence}.json"
                    with self.assertRaisesRegex(ValueError, "checkpoint sequence"):
                        save_checkpoint(checkpoint, save_path)
                    self.assertFalse(save_path.exists())

                    load_path = root / f"rejected-load-{sequence}.json"
                    payload = {
                        **checkpoint.__dict__,
                        "verified_steps": list(checkpoint.verified_steps),
                        "pending_steps": list(checkpoint.pending_steps),
                    }
                    load_path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "checkpoint sequence"):
                        load_checkpoint(load_path, "harness-smoke-001", "same goal")

    def test_restore_rejects_goal_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(self._checkpoint(), path)
            with self.assertRaisesRegex(ValueError, "goal drift"):
                load_checkpoint(path, "harness-smoke-001", "different goal")

    def test_restore_rejects_corrupt_json(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkpoint is not valid JSON"):
                load_checkpoint(path, "harness-smoke-001", "same goal")

    def test_restore_rejects_duplicate_json_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            path.write_text(
                "{"
                '\"schema_version\": \"insightradar-harness-checkpoint/v1\", '
                '\"schema_version\": \"insightradar-harness-checkpoint/v1\"'
                "}",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_checkpoint(path, "harness-smoke-001", "same goal")

    def test_restore_rejects_malformed_checkpoint_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            path.write_text(
                "{"
                '\"schema_version\": \"insightradar-harness-checkpoint/v1\", '
                '\"run_id\": \"run-001\", '
                '\"task_id\": \"harness-smoke-001\", '
                f'\"goal_hash\": \"{goal_digest("same goal")}\", '
                '\"sequence\": true, '
                '\"verified_steps\": [], '
                '\"pending_steps\": [], '
                '\"artifact_hashes\": {}, '
                f'\"created_at\": \"{NOW.isoformat()}\"'
                "}",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "checkpoint sequence"):
                load_checkpoint(path, "harness-smoke-001", "same goal")

    def test_checkpoint_limits_accept_exact_counts_and_reject_over_limit_inputs(self) -> None:
        checkpoint = Checkpoint(
            schema_version="insightradar-harness-checkpoint/v1",
            run_id="run-001",
            task_id="harness-smoke-001",
            goal_hash=goal_digest("same goal"),
            sequence=MAX_STEPS,
            verified_steps=tuple(f"step-{index}" for index in range(MAX_STEPS)),
            pending_steps=(),
            artifact_hashes={f"artifact-{index}.json": "a" * 64 for index in range(MAX_ARTIFACT_HASHES)},
            created_at=NOW.isoformat(),
        )
        too_many_steps = Checkpoint(
            **{**checkpoint.__dict__, "verified_steps": checkpoint.verified_steps + ("one-too-many",)}
        )
        too_many_hashes = Checkpoint(
            **{
                **checkpoint.__dict__,
                "artifact_hashes": {**checkpoint.artifact_hashes, "one-too-many.json": "a" * 64},
            }
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(checkpoint, path)
            self.assertEqual(load_checkpoint(path, "harness-smoke-001", "same goal").verified_steps, checkpoint.verified_steps)
            with self.assertRaisesRegex(ValueError, "verified_steps"):
                save_checkpoint(too_many_steps, path)
            with self.assertRaisesRegex(ValueError, "artifact_hashes"):
                save_checkpoint(too_many_hashes, path)
            oversized = Path(tmp) / "oversized.json"
            oversized.write_bytes(b" " * (MAX_CHECKPOINT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "maximum size"):
                load_checkpoint(oversized, "harness-smoke-001", "same goal")

    def test_checkpoint_reads_once_at_exact_size_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(self._checkpoint(), path)
            raw = path.read_bytes()
            exact = raw + b" " * (MAX_CHECKPOINT_BYTES - len(raw))
            path.write_bytes(exact)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded helper used")):
                restored = load_checkpoint(path, "harness-smoke-001", "same goal")
            self.assertEqual(restored.run_id, "run-001")
            path.write_bytes(exact + b" ")
            with self.assertRaisesRegex(ValueError, "maximum size"):
                load_checkpoint(path, "harness-smoke-001", "same goal")

    def test_checkpoint_write_permission_failure_leaves_no_randomized_temp_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            with patch.object(checkpoint_module.os, "replace", side_effect=PermissionError):
                with self.assertRaisesRegex(ValueError, "cannot be saved"):
                    save_checkpoint(self._checkpoint(), path)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_checkpoint_rejects_excessive_depth_and_invalid_bounded_fields(self) -> None:
        nested: object = {"leaf": "value"}
        for _ in range(6):
            nested = {"nested": nested}
        overlong_run_id = Checkpoint(
            **{**self._checkpoint().__dict__, "run_id": "r" + "a" * 64}
        )
        invalid_hash = Checkpoint(
            **{**self._checkpoint().__dict__, "artifact_hashes": {"trace.jsonl": "abc123"}}
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            path.write_text(json.dumps({"nested": nested}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "maximum depth"):
                load_checkpoint(path, "harness-smoke-001", "same goal")
            with self.assertRaisesRegex(ValueError, "run_id"):
                save_checkpoint(overlong_run_id, path)
            with self.assertRaisesRegex(ValueError, "artifact hash"):
                save_checkpoint(invalid_hash, path)

    def test_smoke_rejects_reduced_safe_tool_set_before_creating_artifacts(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, tools in (
                ("read-only", ["read_project_files"]),
                ("duplicate", ["read_project_files", "write_runtime_artifacts", "write_runtime_artifacts"]),
            ):
                with self.subTest(name=name):
                    payload["allowed_tools"] = tools
                    manifest_path = root / f"{name}.json"
                    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                    output_dir = root / f"runtime-{name}"
                    with self.assertRaisesRegex(ValueError, "exact safe tool set|contains duplicates"):
                        run_contract_smoke(manifest_path, output_dir, "smoke-002", clock=lambda: NOW)
                    self.assertFalse(output_dir.exists())

    def test_smoke_enforces_budget_artifacts_and_every_acceptance_before_publication(self) -> None:
        base = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cases: list[tuple[str, dict[str, object], str]] = []

        low_steps = json.loads(json.dumps(base))
        low_steps["budget"]["max_steps"] = 1
        cases.append(("steps", low_steps, "step budget exceeded"))

        low_tools = json.loads(json.dumps(base))
        low_tools["budget"]["max_tool_calls"] = 1
        cases.append(("tools", low_tools, "tool-call budget exceeded"))

        missing_artifact = json.loads(json.dumps(base))
        missing_artifact["expected_artifacts"] = ["trace.jsonl", "checkpoint.json", "missing.bin"]
        cases.append(("missing-artifact", missing_artifact, "artifact set mismatch"))

        unexpected_artifact = json.loads(json.dumps(base))
        unexpected_artifact["expected_artifacts"] = ["trace.jsonl", "checkpoint.json"]
        cases.append(("unexpected-artifact", unexpected_artifact, "artifact set mismatch"))

        impossible_text = json.loads(json.dumps(base))
        impossible_text["acceptance_checks"].append(
            {"id": "impossible", "kind": "text_contains", "target": "harness-smoke.md", "expected": "IMPOSSIBLE-PUBLIC-TEXT"}
        )
        cases.append(("impossible-text", impossible_text, "acceptance check failed"))

        unsupported_exit = json.loads(json.dumps(base))
        unsupported_exit["acceptance_checks"].append(
            {"id": "exit", "kind": "exit_code", "target": "smoke", "expected": "1"}
        )
        cases.append(("unsupported-exit", unsupported_exit, "acceptance check kind is invalid"))

        for name, payload, expected_error in cases:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest_path = root / "manifest.json"
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                output_dir = root / "runs"
                run_id = f"smoke-{name}"
                with self.assertRaisesRegex(ValueError, expected_error) as caught:
                    run_contract_smoke(manifest_path, output_dir, run_id, clock=lambda: NOW)
                self.assertNotIn("IMPOSSIBLE-PUBLIC-TEXT", str(caught.exception))
                self.assertFalse((output_dir / run_id).exists())
                if output_dir.exists():
                    self.assertEqual(list(output_dir.iterdir()), [])

    def test_smoke_enforces_elapsed_budget_before_creating_or_publishing_artifacts(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        payload["budget"]["max_elapsed_seconds"] = 1
        calls = 0

        def clock() -> datetime:
            nonlocal calls
            calls += 1
            return NOW if calls == 1 else NOW + timedelta(seconds=2)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            output_dir = root / "runs"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "elapsed-time budget exceeded"):
                run_contract_smoke(manifest_path, output_dir, "smoke-elapsed", clock=clock)
            self.assertFalse(output_dir.exists())

    def test_smoke_cleans_owned_temp_directory_for_injected_failures(self) -> None:
        for failure in ("trace", "checkpoint", "summary"):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                output_dir = Path(tmp) / "runtime"
                run_id = f"smoke-{failure}"
                if failure == "trace":
                    patcher = patch.object(smoke_module, "validate_public_trace", return_value=["forced"])
                elif failure == "summary":
                    patcher = patch.object(
                        smoke_module,
                        "_write_text_atomically",
                        side_effect=ValueError("forced summary failure"),
                    )
                else:
                    original_save = smoke_module.save_checkpoint
                    calls = 0

                    def fail_final_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise ValueError("forced final checkpoint failure")
                        original_save(checkpoint, path)

                    patcher = patch.object(smoke_module, "save_checkpoint", side_effect=fail_final_checkpoint)
                with patcher, self.assertRaises(ValueError):
                    run_contract_smoke(MANIFEST, output_dir, run_id, clock=lambda: NOW)
                self.assertFalse((output_dir / run_id).exists())
                self.assertEqual(list(output_dir.glob(f".{run_id}.*")), [])

    def test_smoke_rejects_fixed_clock_run_id_collision_without_temp_remnants(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "runtime"
            first = run_contract_smoke(MANIFEST, output_dir, clock=lambda: NOW)
            with self.assertRaisesRegex(ValueError, "run directory already exists"):
                run_contract_smoke(MANIFEST, output_dir, clock=lambda: NOW)
            self.assertTrue(first.summary_path.exists())
            self.assertEqual(list(output_dir.glob(f".{first.run_id}.*")), [])

    def test_smoke_never_cleans_replaced_staging_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "runtime"
            run_id = "smoke-replaced"
            original_publish = smoke_module._publish_run_directory

            def replace_before_publish(staging: object) -> None:
                temporary_run_dir = staging.temporary_run_dir
                temporary_run_dir.rename(output_dir / "attacker-stash")
                temporary_run_dir.mkdir()
                (temporary_run_dir / "not-owned.txt").write_text("preserve", encoding="utf-8")
                original_publish(staging)

            with patch.object(smoke_module, "_publish_run_directory", side_effect=replace_before_publish):
                with self.assertRaisesRegex(ValueError, "operator cleanup required"):
                    run_contract_smoke(MANIFEST, output_dir, run_id, clock=lambda: NOW)
            self.assertFalse((output_dir / run_id).exists())
            replaced = next(output_dir.glob(f".{run_id}.*"))
            self.assertEqual((replaced / "not-owned.txt").read_text(encoding="utf-8"), "preserve")
            self.assertTrue((output_dir / "attacker-stash" / "trace.jsonl").exists())

    def test_smoke_never_publishes_or_cleans_symlink_replacement(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "runtime"
            run_id = "smoke-symlink"
            outside = output_dir / "not-owned"
            original_publish = smoke_module._publish_run_directory

            def replace_before_publish(staging: object) -> None:
                temporary_run_dir = staging.temporary_run_dir
                temporary_run_dir.rename(output_dir / "attacker-stash")
                outside.mkdir()
                (outside / "not-owned.txt").write_text("preserve", encoding="utf-8")
                try:
                    os.symlink(outside, temporary_run_dir, target_is_directory=True)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f"directory symlinks unavailable: {exc}")
                original_publish(staging)

            with patch.object(smoke_module, "_publish_run_directory", side_effect=replace_before_publish):
                with self.assertRaisesRegex(ValueError, "operator cleanup required"):
                    run_contract_smoke(MANIFEST, output_dir, run_id, clock=lambda: NOW)
            self.assertFalse((output_dir / run_id).exists())
            self.assertEqual((outside / "not-owned.txt").read_text(encoding="utf-8"), "preserve")
            self.assertTrue((output_dir / "attacker-stash" / "trace.jsonl").exists())

    def test_contract_smoke_creates_public_trace_checkpoint_and_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = run_contract_smoke(
                MANIFEST,
                output_dir,
                run_id="smoke-001",
                clock=lambda: NOW,
            )
            self.assertTrue(result.trace_path.exists())
            self.assertTrue(result.checkpoint_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.trace_path.is_relative_to(output_dir.resolve()))
            self.assertTrue(result.checkpoint_path.is_relative_to(output_dir.resolve()))
            self.assertTrue(result.summary_path.is_relative_to(output_dir.resolve()))
            self.assertEqual(validate_public_trace(result.trace_path), [])
            restored = load_checkpoint(result.checkpoint_path, "harness-smoke-001", "Validate task, trace, privacy, and checkpoint contracts without a model call or investment side effect.")
            self.assertEqual(result.summary_path.read_text(encoding="utf-8"), result.markdown + "\n")
            trace_hash = hashlib.sha256(result.trace_path.read_bytes()).hexdigest()
        self.assertEqual(restored.artifact_hashes.keys(), {"trace.jsonl"})
        self.assertEqual(restored.artifact_hashes["trace.jsonl"], trace_hash)
        self.assertIn("\u4ea4\u6613\u6743\u9650\uff1anone", result.markdown)
        self.assertIn("\u6a21\u578b\u8c03\u7528\uff1anone", result.markdown)
        self.assertIn("\u516c\u5f00 Trace \u6821\u9a8c\uff1aPASS", result.markdown)


if __name__ == "__main__":
    unittest.main()
