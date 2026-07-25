from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.product_governance import GovernanceSnapshot
from stock_assist.workflows import evolution


class EvolutionTests(unittest.TestCase):
    def test_feature_lines_show_full_catalog_and_latest_pass(self) -> None:
        features = [
            {"id": "feat-027", "name": "Signal outcome ledger", "status": "pass"},
            {"id": "feat-044", "name": "Official IR discovery", "status": "pending"},
            {"id": "feat-053", "name": "Guarded futures basis", "status": "pass"},
            {"id": "feat-054", "name": "Harness bootstrap", "status": "in_progress"},
        ]
        lines = evolution._feature_lines(features)
        self.assertTrue(any("in_progress=1" in line and "pass=2" in line for line in lines))
        self.assertTrue(any("feat-044 Official IR discovery: pending" in line for line in lines))
        self.assertTrue(any("feat-054 Harness bootstrap: in_progress" in line for line in lines))

    def test_backlog_is_bounded_by_remaining_queue_slots(self) -> None:
        snapshot = GovernanceSnapshot(1, 2, (), ())
        self.assertEqual(
            evolution._bound_backlog(["one", "two", "three"], snapshot),
            ["\u5019\u9009\uff08\u5c1a\u672a\u83b7\u51c6\uff09\uff1aone", "\u5019\u9009\uff08\u5c1a\u672a\u83b7\u51c6\uff09\uff1atwo"],
        )

    def test_full_queue_blocks_new_recommendations(self) -> None:
        queued = (object(), object())
        snapshot = GovernanceSnapshot(1, 2, (), queued)  # type: ignore[arg-type]
        self.assertEqual(
            evolution._bound_backlog(["one"], snapshot),
            ["\u5b9e\u9a8c\u961f\u5217\u5df2\u6ee1\uff1b\u5148\u5b8c\u6210\u3001\u7ec8\u6b62\u6216\u79fb\u51fa\u65e2\u6709\u5b9e\u9a8c\uff0c\u4e0d\u65b0\u589e\u529f\u80fd\u3002"],
        )

    @patch("stock_assist.workflows.evolution.load_outcome_snapshot", return_value={"horizons": {}, "latest": []})
    @patch("stock_assist.workflows.evolution._local_data_state")
    def test_report_uses_full_catalog_governance_and_excludes_old_evolution(
        self, local_state_mock, _outcome_mock
    ) -> None:
        local_state_mock.return_value = {
            "portfolio_input": True,
            "portfolio_context": True,
            "amazingdata_env": True,
            "crypto_watchlist": True,
            "crypto_watchlist_example": True,
            "research_sources": True,
            "influencer_observations": True,
            "signal_outcomes": True,
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "reports"
            report_dir.mkdir()
            (report_dir / "20260721-after-close.md").write_text("Missing required", encoding="utf-8")
            (report_dir / "20260721-evolution.md").write_text("Missing required", encoding="utf-8")
            feature_path = root / "feature_list.json"
            feature_path.write_text(
                json.dumps({"features": [
                    {"id": "feat-044", "name": "Official IR discovery", "status": "pending"},
                    {"id": "feat-053", "name": "Guarded futures basis", "status": "pass"},
                    {"id": "feat-054", "name": "Harness bootstrap", "status": "in_progress"}
                ]}),
                encoding="utf-8",
            )
            governance_path = root / "product_governance.json"
            governance_path.write_text(json.dumps({
                "schema_version": "insightradar-product-governance/v1",
                "limits": {"max_active_experiments": 1, "max_queued_experiments": 2},
                "active_experiments": [],
                "queued_experiments": []
            }), encoding="utf-8")
            report = evolution.build_evolution_report(
                report_dir, feature_path, governance_path
            )
        self.assertIn("## \u4ea7\u54c1\u5b9e\u9a8c\u6cbb\u7406", report)
        self.assertIn("\u6d3b\u8dc3\u5b9e\u9a8c 0/1", report)
        self.assertIn("feat-053 Guarded futures basis: pass", report)
        self.assertIn("feat-054 Harness bootstrap: in_progress", report)
        self.assertIn("data_source: 1", report)


if __name__ == "__main__":
    unittest.main()
