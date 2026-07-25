from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.cli import main
from stock_assist.workflows.agent_roster import build_agent_roster_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentRosterTests(unittest.TestCase):
    def _copy_contracts(self, root: Path) -> tuple[Path, Path]:
        roster_path = root / "agents.json"
        roster_path.write_bytes((PROJECT_ROOT / "configs" / "agents.json").read_bytes())
        agent_dir = root / "agents"
        shutil.copytree(PROJECT_ROOT / ".codex" / "agents", agent_dir)
        return roster_path, agent_dir

    def test_report_shows_validated_limits_authority_and_runtime_agent(self) -> None:
        report = build_agent_roster_report()
        self.assertIn("Agent：3", report)
        self.assertIn("：1；", report)
        self.assertIn("lead_serializes_workspace_changes", report)
        self.assertIn("：none", report)
        self.assertIn("：product_critic", report)

    def test_report_fails_closed_when_roster_and_toml_contracts_diverge(self) -> None:
        with TemporaryDirectory() as tmp:
            roster_path, agent_dir = self._copy_contracts(Path(tmp))
            payload = json.loads(roster_path.read_text(encoding="utf-8"))
            payload["agents"][2]["runtime_agent"] = "default"
            roster_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "agent roster validation failed"):
                build_agent_roster_report(roster_path, agent_dir)

    def test_report_fails_closed_for_missing_config_without_echo(self) -> None:
        marker = "PRIVATE-MARKER-MISSING-9981"
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "agent roster validation failed") as caught:
                build_agent_roster_report(Path(tmp) / f"{marker}.json", PROJECT_ROOT / ".codex" / "agents")
        self.assertNotIn(marker, str(caught.exception))

    def test_agents_cli_returns_visible_failure_without_writing_report(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch("stock_assist.cli.build_agent_roster_report", side_effect=ValueError("agent roster validation failed")),
            patch("stock_assist.cli.write_report") as write_report,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main(["agents"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("agent roster validation failed", stderr.getvalue())
        write_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
