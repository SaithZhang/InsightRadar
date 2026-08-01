from __future__ import annotations

import json
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.cli import main
from stock_assist.product import FILES, command_for
from stock_assist.workflows.architecture_view import build_architecture_view
from stock_assist.harness_eval.smoke import run_contract_smoke


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HarnessIntegrationTests(unittest.TestCase):
    def test_product_registry_exposes_smoke_and_contract_files(self) -> None:
        command = command_for("harness-smoke")
        self.assertIn("configs/harness_eval/smoke_task.json", command.inputs)
        self.assertIn("configs/product_governance.json", command.inputs)
        self.assertIn("feature_list.json", command.inputs)
        self.assertIn("configs/agents.json", command.inputs)
        self.assertIn(".codex/agents/*.toml", command.inputs)
        self.assertIn("data/harness_eval/runs/*", command.outputs)
        paths = {item.path for item in FILES}
        self.assertIn("configs/product_governance.json", paths)
        self.assertIn(".codex/agents/*.toml", paths)
        self.assertIn("configs/harness_eval/*.json", paths)
        self.assertIn("data/harness_eval/*", paths)

    def test_architecture_registers_harness_command_and_evolution_edge(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "configs" / "architecture.json").read_text(encoding="utf-8")
        )
        node = next(item for item in payload["nodes"] if item["id"] == "harness_eval")
        self.assertEqual(node["commands"], ["harness-smoke"])
        self.assertIn("configs/harness_eval/smoke_task.json", node["inputs"])
        self.assertIn("configs/product_governance.json", node["inputs"])
        self.assertIn("feature_list.json", node["inputs"])
        self.assertIn("configs/agents.json", node["inputs"])
        self.assertIn(".codex/agents/*.toml", node["inputs"])
        self.assertTrue(
            any(
                edge["from"] == "harness_eval" and edge["to"] == "evolution"
                for edge in payload["edges"]
            )
        )

    def test_architecture_render_is_lf_and_matches_tracked_artifact(self) -> None:
        with TemporaryDirectory() as temporary:
            rendered_path = Path(temporary) / "architecture.html"
            build_architecture_view(output_path=rendered_path)
            rendered = rendered_path.read_bytes()

        tracked = (PROJECT_ROOT / "docs" / "architecture.html").read_bytes()
        normalized_tracked = tracked.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        self.assertNotIn(b"\r\n", rendered)
        self.assertEqual(rendered, normalized_tracked)

    def test_architecture_source_digest_ignores_checkout_line_endings(self) -> None:
        payload = '{\n  "lanes": [],\n  "nodes": [],\n  "edges": [],\n  "ideas": []\n}\n'
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            lf_config = root / "architecture-lf.json"
            crlf_config = root / "architecture-crlf.json"
            lf_output = root / "architecture-lf.html"
            crlf_output = root / "architecture-crlf.html"
            lf_config.write_bytes(payload.encode("utf-8"))
            crlf_config.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))

            build_architecture_view(lf_config, lf_output)
            build_architecture_view(crlf_config, crlf_output)
            digest_pattern = 'name="architecture-source-sha256" content="'
            lf_digest = lf_output.read_text(encoding="utf-8").split(digest_pattern, 1)[1][:64]
            crlf_digest = crlf_output.read_text(encoding="utf-8").split(digest_pattern, 1)[1][:64]
        self.assertEqual(lf_digest, crlf_digest)

    def test_normative_design_status_reflects_feat_054_pass(self) -> None:
        text = (
            PROJECT_ROOT
            / "docs"
            / "superpowers"
            / "specs"
            / "2026-07-21-agent-harness-job-readiness-design.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Status: approved; `feat-054` bootstrap independently verified PASS; `feat-056` pending",
            text,
        )
        self.assertIn("## Historical Activation Transition", text)
        self.assertIn("`feat-056` remains pending and is the sole queued Harness experiment", text)
        self.assertNotIn("execution not started", text)
        self.assertNotIn("`feat-054` is not registered or activated", text)

    def test_macro_shadow_remains_closed_under_intraday_activation(self) -> None:
        current_state = (PROJECT_ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
        self.assertRegex(current_state, r'"updated_at": "\d{4}-\d{2}-\d{2}"')
        self.assertIn('"next_feature_id": "IR-002"', current_state)

        feature_payload = json.loads((PROJECT_ROOT / "feature_list.json").read_text(encoding="utf-8"))
        feature_status = {item["id"]: item["status"] for item in feature_payload["features"]}
        self.assertEqual(feature_status["feat-054"], "pass")
        self.assertEqual(feature_status["feat-056"], "pending")
        self.assertEqual(feature_status["feat-057"], "pass")

        governance = json.loads(
            (PROJECT_ROOT / "configs" / "product_governance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["feature_id"] for item in governance["active_experiments"]],
            ["IR-002"],
        )
        self.assertEqual(
            [item["feature_id"] for item in governance["queued_experiments"]],
            ["feat-058", "feat-056"],
        )

    def test_macro_shadow_is_registered_as_diagnostic_risk_watch_input(self) -> None:
        command = command_for("risk-watch")
        self.assertIn("configs/macro_transmission.json", command.inputs)
        self.assertIn(
            "diagnostic-only macro transmission shadow and replay calibration",
            command.outputs,
        )
        self.assertIn(
            "configs/macro_transmission.json",
            {item.path for item in FILES},
        )

        architecture = json.loads(
            (PROJECT_ROOT / "configs" / "architecture.json").read_text(
                encoding="utf-8"
            )
        )
        node = next(
            item for item in architecture["nodes"] if item["id"] == "risk_watch"
        )
        self.assertIn(
            "Brent/WTI/US10Y/SP500/QQQ/SOX/KOSPI point-in-time history",
            node["inputs"],
        )
        self.assertIn("primary-source macro event evidence", node["inputs"])
        self.assertIn(
            "diagnostic-only macro transmission shadow and replay calibration",
            node["outputs"],
        )
        self.assertFalse(
            any(
                edge["from"] == "risk_watch"
                and edge["to"] == "portfolio_intelligence"
                and "macro" in str(edge.get("label", "")).lower()
                for edge in architecture["edges"]
            )
        )

        harness = (PROJECT_ROOT / "docs" / "harness.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("### Macro Transmission Shadow", harness)
        self.assertIn("authority=diagnostic_only", harness)

    def test_cli_harness_smoke_writes_public_artifacts_and_fails_closed_on_collision(self) -> None:
        class FixedDateTime:
            @staticmethod
            def now(tz: object = None) -> datetime:
                return datetime(2026, 7, 21, 14, 55, tzinfo=tz)

        with TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            output_dir = temporary_root / "runs"
            report_dir = temporary_root / "reports"

            def write_temporary_report(name: str, content: str) -> Path:
                report_dir.mkdir()
                report_path = report_dir / f"{name}.md"
                report_path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")
                return report_path

            first_stdout = StringIO()
            first_stderr = StringIO()
            with (
                patch("stock_assist.cli.write_report", side_effect=write_temporary_report),
                patch("stock_assist.harness_eval.smoke.datetime", FixedDateTime),
                redirect_stdout(first_stdout),
                redirect_stderr(first_stderr),
            ):
                first_exit = main(["harness-smoke", "--output-dir", str(output_dir)])

            emitted_paths = [Path(line) for line in first_stdout.getvalue().splitlines()]
            self.assertEqual(first_exit, 0)
            self.assertEqual(first_stderr.getvalue(), "")
            self.assertEqual(len(emitted_paths), 3)
            self.assertTrue(all(path.is_file() for path in emitted_paths))
            trace_path, checkpoint_path, report_path = emitted_paths
            self.assertEqual(report_path, report_dir / "harness-smoke.md")
            report = report_path.read_text(encoding="utf-8")
            for expected in ("模型调用：none", "交易权限：none", "Checkpoint 目标连续性：PASS", "公开 Trace 校验：PASS"):
                self.assertIn(expected, report)
            self.assertNotIn(str(temporary_root), report)
            self.assertNotIn("private", report.casefold())
            trace_before = trace_path.read_bytes()
            checkpoint_before = checkpoint_path.read_bytes()

            second_stdout = StringIO()
            second_stderr = StringIO()
            with (
                patch("stock_assist.cli.write_report", side_effect=write_temporary_report),
                patch("stock_assist.harness_eval.smoke.datetime", FixedDateTime),
                redirect_stdout(second_stdout),
                redirect_stderr(second_stderr),
            ):
                second_exit = main(["harness-smoke", "--output-dir", str(output_dir)])

            self.assertEqual(second_exit, 1)
            self.assertEqual(second_stdout.getvalue(), "")
            self.assertIn("smoke run directory already exists", second_stderr.getvalue())
            self.assertEqual(trace_path.read_bytes(), trace_before)
            self.assertEqual(checkpoint_path.read_bytes(), checkpoint_before)

    def test_smoke_executes_declared_governance_and_roster_validators(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("stock_assist.harness_eval.smoke.load_governance_snapshot") as governance,
                patch("stock_assist.harness_eval.smoke.validate_agent_contracts", return_value=[]) as contracts,
            ):
                run_contract_smoke(
                    output_dir=Path(temporary),
                    run_id="smoke-wiring",
                    clock=lambda: datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc),
                )
        governance.assert_called_once_with()
        contracts.assert_called_once()

    def test_cli_manifest_failure_is_marker_free_and_publishes_nothing(self) -> None:
        marker = "IMPOSSIBLE-PUBLIC-MARKER-9981"
        payload = json.loads(
            (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(encoding="utf-8")
        )
        payload["acceptance_checks"].append(
            {"id": "impossible", "kind": "text_contains", "target": "harness-smoke.md", "expected": marker}
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            output_dir = root / "runs"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["harness-smoke", "--manifest", str(manifest_path), "--output-dir", str(output_dir)])
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(marker, stderr.getvalue())
        self.assertFalse(any(output_dir.iterdir()) if output_dir.exists() else False)

    def test_cli_embedded_private_paths_are_marker_free_and_leave_no_run_residue(self) -> None:
        marker = "PRIVATE-PATH-MARKER-4421"
        goals = (
            f"Inspect source=C:\\Users\\Saith\\{marker}\\broker.tsv safely.",
            f"Inspect (C:\\Users\\Saith\\{marker}\\broker.tsv) safely.",
            f"Inspect path:C:\\Users\\Saith\\{marker}\\broker.tsv safely.",
            f"Inspect source=\\\\server\\share\\{marker}\\broker.tsv safely.",
            f"Inspect source=//server/share/{marker}/broker.tsv safely.",
            f"Inspect source=/private/{marker}/raw.json safely.",
            f"Inspect source=/123/{marker}/raw.json safely.",
            f"Inspect source=//10.0.0.1/share/{marker}/raw.json safely.",
            f"Inspect source:(/123/{marker}/raw.json) safely.",
            f"Inspect path=[//10.0.0.1/share/{marker}/raw.json] safely.",
            f"\u8bfb\u53d6C:\\Users\\Saith\\{marker}\\broker.tsv\u3002",
            f"\u8bfb\u53d6\\\\server\\share\\{marker}\\broker.tsv\u3002",
            f"\u8bfb\u53d6\\\\?\\C:\\{marker}\\raw.json\u3002",
            f"\u8bfb\u53d6/private/{marker}/raw.json\u3002",
            f"\u8bfb\u53d6//10.0.0.1/share/{marker}/raw.json\u3002",
        )
        for index, goal in enumerate(goals):
            with self.subTest(goal=goal), TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest_path = root / "manifest.json"
                output_dir = root / "runs"
                payload = json.loads(
                    (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(
                        encoding="utf-8"
                    )
                )
                payload["goal"] = goal
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "harness-smoke",
                            "--manifest",
                            str(manifest_path),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )
                self.assertEqual(exit_code, 1, index)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn(marker, stderr.getvalue())
                self.assertFalse(output_dir.exists())

    def test_cli_chinese_double_negation_is_marker_free_and_leaves_no_run_residue(self) -> None:
        marker = "CHINESE-DOUBLE-NEGATION-MARKER-7319"
        goals = (
            f"\u4e0d\u4e0d\u4e70\u5165100\u80a1\uff0c{marker}\u3002",
            f"\u4e0d\u4e0d\u5356\u51fa100\u80a1\uff0c{marker}\u3002",
            f"\u4e0d\u4e0d\u4e0b\u5355\uff0c{marker}\u3002",
            f"\u4e0d\u4e0d\u4ea4\u6613\uff0c{marker}\u3002",
            f"\u4e0d\u5f97\u4e0d\u4e70\u5165100\u80a1\uff0c{marker}\u3002",
            f"\u62d2\u7edd\u4e0d\u4e70\u5165100\u80a1\uff0c{marker}\u3002",
        )
        for goal in goals:
            with self.subTest(goal=goal), TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest_path = root / "manifest.json"
                output_dir = root / "runs"
                payload = json.loads(
                    (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(
                        encoding="utf-8"
                    )
                )
                payload["goal"] = goal
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "harness-smoke",
                            "--manifest",
                            str(manifest_path),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )
                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn(marker, stderr.getvalue())
                self.assertFalse(output_dir.exists())

    def test_cli_authority_safe_prefix_unsafe_suffix_is_marker_free_and_leaves_no_residue(self) -> None:
        marker = "AUTHORITY-SUFFIX-MARKER-9187"
        goals = (
            f"Trade authority: none or full. {marker}",
            f"\u4ea4\u6613\u6743\u9650\uff1anone\uff0c\u4f46full\u3002{marker}",
            f"Trade authority: none; full. {marker}",
            f"\u4ea4\u6613\u6743\u9650\uff1a\u65e0\uff1bfull\u3002{marker}",
        )
        for goal in goals:
            with self.subTest(goal=goal), TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest_path = root / "manifest.json"
                output_dir = root / "runs"
                payload = json.loads(
                    (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(
                        encoding="utf-8"
                    )
                )
                payload["goal"] = goal
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "harness-smoke",
                            "--manifest",
                            str(manifest_path),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )
                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn(marker, stderr.getvalue())
                self.assertFalse(output_dir.exists())

    def test_cli_structural_public_policy_is_marker_free_and_leaves_no_residue(self) -> None:
        marker = "STRUCTURAL-PUBLIC-MARKER-7241"
        cases = (
            ("goal", f"No trade authority. {marker}"),
            ("goal", f"Never buy shares and never sell shares. {marker}"),
            ("goal", f"session_id={marker}"),
            ("context_refs", [f"reports/{marker}.md"]),
        )
        for field, value in cases:
            with self.subTest(field=field), TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest_path = root / "manifest.json"
                output_dir = root / "runs"
                payload = json.loads(
                    (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(
                        encoding="utf-8"
                    )
                )
                payload[field] = value
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "harness-smoke",
                            "--manifest",
                            str(manifest_path),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )
                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn(marker, stderr.getvalue())
                self.assertFalse(output_dir.exists())

    def test_cli_reviewer_inflections_are_marker_free_and_leave_no_residue(self) -> None:
        inflections = (
            "buy", "buys", "buying", "buyer", "buyers",
            "sell", "sells", "selling", "seller", "sellers",
            "trade", "trades", "traded", "trading", "trader", "traders",
            "order", "orders", "ordered", "ordering",
            "authorize", "authorizes", "authorized", "authorizing",
            "authorise", "authorises", "authorised", "authorising",
            "authorization", "authorizations", "authorisation", "authorisations",
            "authority", "authorities",
        )
        marker = "INFLECTION-REVIEW-MARKER-8231"
        for inflection in inflections:
            with self.subTest(inflection=inflection), TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest_path = root / "manifest.json"
                output_dir = root / "runs"
                payload = json.loads(
                    (PROJECT_ROOT / "configs" / "harness_eval" / "smoke_task.json").read_text(
                        encoding="utf-8"
                    )
                )
                payload["goal"] = f"Review {inflection} evidence. {marker}"
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "harness-smoke",
                            "--manifest",
                            str(manifest_path),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )
                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn(marker, stderr.getvalue())
                self.assertFalse(output_dir.exists())

    def test_restart_snapshot_activates_intraday_acceptance(self) -> None:
        current_state = (PROJECT_ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
        self.assertIn('"next_feature_id": "IR-002"', current_state)

        feature_payload = json.loads(
            (PROJECT_ROOT / "feature_list.json").read_text(encoding="utf-8")
        )
        feature_status = {
            item["id"]: item["status"]
            for item in feature_payload["features"]
        }
        self.assertEqual(feature_status["feat-056"], "pending")
        self.assertEqual(feature_status["feat-058"], "pending")
        self.assertEqual(feature_status["IR-001"], "pass")
        self.assertEqual(feature_status["IR-002"], "pending")

        governance = json.loads(
            (PROJECT_ROOT / "configs" / "product_governance.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [item["feature_id"] for item in governance["active_experiments"]],
            ["IR-002"],
        )
        self.assertEqual(
            [item["feature_id"] for item in governance["queued_experiments"]],
            ["feat-058", "feat-056"],
        )


if __name__ == "__main__":
    unittest.main()
