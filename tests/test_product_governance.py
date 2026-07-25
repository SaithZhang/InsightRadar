from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.product_governance import (
    governance_markdown_lines,
    load_governance_snapshot,
)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _feature_payload(status: str = "pending") -> dict[str, object]:
    return {
        "features": [
            {"id": "feat-044", "name": "Official IR discovery", "status": status}
        ]
    }


def _experiment(feature_id: str = "feat-044") -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "problem": "Official evidence arrives faster than the manual path.",
        "loop_stage": "observe",
        "baseline": "No automatic official discovery exists.",
        "outcome_metric": "Every admitted record keeps point-in-time provenance.",
        "smallest_experiment": "Replay one official source.",
        "safety_boundaries": ["Official sources only", "No trade authority"],
        "kill_criterion": "Stop if provenance is lost.",
        "review_date": "2026-08-17",
    }


def _governance(
    active: list[dict[str, object]] | None = None,
    queued: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "insightradar-product-governance/v1",
        "limits": {"max_active_experiments": 1, "max_queued_experiments": 2},
        "active_experiments": active or [],
        "queued_experiments": queued or [],
    }


class ProductGovernanceTests(unittest.TestCase):
    def _paths(
        self,
        root: Path,
        governance: dict[str, object],
        feature_status: str = "pending",
    ) -> tuple[Path, Path]:
        return (
            _write_json(root / "product_governance.json", governance),
            _write_json(root / "feature_list.json", _feature_payload(feature_status)),
        )

    def test_loads_valid_snapshot_and_renders_owner_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[_experiment()])
            )
            snapshot = load_governance_snapshot(config_path, feature_path)

        self.assertEqual(snapshot.max_active_experiments, 1)
        self.assertEqual(snapshot.max_queued_experiments, 2)
        self.assertEqual(snapshot.remaining_queue_slots, 1)
        lines = governance_markdown_lines(snapshot)
        self.assertTrue(any("活跃实验 0/1" in line for line in lines))
        self.assertTrue(any("feat-044" in line and "待负责人启动" in line for line in lines))
        self.assertTrue(any("Stop if provenance is lost" in line for line in lines))

    def test_rejects_more_than_one_active_experiment(self) -> None:
        with TemporaryDirectory() as tmp:
            item = _experiment()
            config_path, feature_path = self._paths(
                Path(tmp), _governance(active=[item, item])
            )
            with self.assertRaisesRegex(ValueError, "active experiment limit"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_more_than_two_queued_experiments(self) -> None:
        with TemporaryDirectory() as tmp:
            item = _experiment()
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[item, item, item])
            )
            with self.assertRaisesRegex(ValueError, "queued experiment limit"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_unknown_feature(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[_experiment("feat-999")])
            )
            with self.assertRaisesRegex(ValueError, "unknown feature feat-999"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_completed_feature(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[_experiment()]), "pass"
            )
            with self.assertRaisesRegex(ValueError, "completed feature feat-044"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_missing_gate_field(self) -> None:
        with TemporaryDirectory() as tmp:
            item = _experiment()
            del item["kill_criterion"]
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[item])
            )
            with self.assertRaisesRegex(ValueError, "kill_criterion"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_blank_gate_field(self) -> None:
        with TemporaryDirectory() as tmp:
            item = _experiment()
            item["kill_criterion"] = "   "
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[item])
            )
            with self.assertRaisesRegex(ValueError, "kill_criterion"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_basic_iso_date_form(self) -> None:
        with TemporaryDirectory() as tmp:
            item = _experiment()
            item["review_date"] = "20260817"
            config_path, feature_path = self._paths(
                Path(tmp), _governance(queued=[item])
            )
            with self.assertRaisesRegex(ValueError, "review_date"):
                load_governance_snapshot(config_path, feature_path)

    def test_rejects_non_integer_limits(self) -> None:
        with TemporaryDirectory() as tmp:
            governance = _governance()
            governance["limits"] = {
                "max_active_experiments": True,
                "max_queued_experiments": 2.0,
            }
            config_path, feature_path = self._paths(Path(tmp), governance)
            with self.assertRaisesRegex(ValueError, "limits must use integers"):
                load_governance_snapshot(config_path, feature_path)


if __name__ == "__main__":
    unittest.main()
