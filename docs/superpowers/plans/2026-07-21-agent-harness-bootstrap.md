# Agent Harness Governance and Observability Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `feat-054` as the first independently verifiable Agent Harness increment: bounded product governance, truthful evolution reporting, read-only agent contracts, versioned task/trace/checkpoint/privacy contracts, and a real deterministic smoke artifact without changing investment decisions or adding model/runtime dependencies.

**Architecture:** Keep InsightRadar's modular monolith and treat Codex or another agent as a replaceable backend. Add the governance source of truth beside a focused `stock_assist/harness_eval/` package that owns manifests, traces, privacy validation, checkpoints, and a no-model smoke workflow. Existing `agents`, `evolve`, product-map, CLI, architecture, and project-memory surfaces expose the contracts; production investment workflows remain untouched.

**Tech Stack:** Python 3.10+, standard library only (`dataclasses`, `datetime`, `enum`, `hashlib`, `json`, `os`, `pathlib`, `re`, `tempfile`, `unittest`), JSON and TOML contracts, existing InsightRadar CLI/report helpers, PowerShell verification commands.

## Global Constraints

- Canonical specification: `docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md`; the adjacent Chinese copy is non-normative.
- This plan supersedes `docs/superpowers/plans/2026-07-19-agent-governed-product-iteration.md` for `feat-054` execution.
- This plan covers only weeks 1-2 governance and observability. The real-task benchmark, ablations, and EvidenceHarness extraction require separate plans after this increment produces stable interfaces.
- Do not implement a new LLM runtime, model call, vector database, web console, cloud service, event ingestion, candidate ranking, or trade execution.
- The human owner approves priority, scope expansion, experiment start, and release. `evolve` never mutates feature or experiment state.
- The lead is the sole workspace writer. Project-scoped task agents are read-only, non-recursive, and capped at three concurrent task agents when the chosen execution mode permits them.
- No agent, trace, checkpoint, report, or experiment may grant trade authority or turn missing/stale evidence into an unconditional investment action.
- Holdings, broker exports, cost basis, account identifiers, personal risk rules, credentials, and raw private conversations remain `private` or `secret` and never enter public artifacts.
- Traces record structured events and high-level outcome metadata, never hidden chain-of-thought.
- Use TDD for every behavior change: write the focused failing test, run and record the intended failure, implement the minimum behavior, rerun the focused test, then commit.
- Use `unittest`, not an undeclared test dependency. Every new test module must run through `.venv\Scripts\python -m unittest`.
- Preserve existing Markdown report commands and ignored runtime artifact policy. Do not force-add `reports/` or `data/` runtime outputs to Git.
- Run AmazingData commands serially if any unrelated verification reaches them; this plan's focused tests and smoke workflow must not require AmazingData or network access.
- Do not edit or commit `.env`, credentials, ignored `.learnings`, private portfolio files, or generated runtime traces.

## Delivery Boundary and Follow-On Features

This is the first of four separately planned increments:

1. **`feat-054` — this plan:** governance, task-agent contracts, manifest/trace/privacy/checkpoint schemas, and deterministic smoke evidence.
2. **`feat-056` — next plan:** 20-30 private/sanitized tasks, four Harness profiles, deterministic evaluation, and a baseline report.
3. **Later focused experiment plan:** bounded-context, structured-memory, checkpoint-recovery, and single-versus-multi-agent ablations with preregistered gates.
4. **Later extraction plan:** EvidenceHarness public package, synthetic suite, reproducible benchmark, documentation, case study, and demonstration.

At `feat-054` closeout, register `feat-056` as pending and make it the sole queued product experiment. Keep `feat-044` and `feat-055` pending but outside the active Harness queue. Do not start `feat-056` during this plan.

---

### Task 1: Activate `feat-054` and Add Bounded Experiment Governance

**Files:**

- Modify: `feature_list.json`
- Create: `configs/product_governance.json`
- Create: `stock_assist/product_governance.py`
- Create: `tests/test_product_governance.py`

**Interfaces:**

- Consumes: `feature_list.json` entries with `id`, `name`, and `status`.
- Produces: `Experiment`, `GovernanceSnapshot`, `load_governance_snapshot(config_path, feature_path)`, and `governance_markdown_lines(snapshot)` for Task 2 and Task 8.

- [ ] **Step 1: Register the active bootstrap feature**

Insert exactly this object immediately before the existing `feat-055` entry in `feature_list.json`; do not change existing features:

```json
{
  "id": "feat-054",
  "name": "Agent Harness governance and observability bootstrap",
  "description": "Add bounded product-experiment governance, truthful full-catalog evolution reporting, project-scoped read-only agent contracts, versioned task/trace/checkpoint/privacy contracts, and deterministic smoke evidence without changing investment decisions or adding trade authority.",
  "dependencies": ["feat-004", "feat-035", "feat-053"],
  "status": "in_progress",
  "evidence": "User approved the canonical Agent Harness engineering design and explicitly resumed the project on 2026-07-21. Scope is the governance and observability bootstrap only; benchmark execution, ablations, public extraction, event ingestion, candidate ranking, and trade execution remain outside this feature."
}
```

Run:

```powershell
.venv\Scripts\python -c "import json; p=json.load(open('feature_list.json', encoding='utf-8')); f=next(x for x in p['features'] if x['id']=='feat-054'); assert f['status']=='in_progress'"
```

Expected: exit code `0`.

Commit:

```powershell
git add feature_list.json
git commit -m "chore: start agent harness bootstrap"
```

- [ ] **Step 2: Write the failing governance tests**

Create `tests/test_product_governance.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the governance test to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_product_governance
```

Expected: import fails with `ModuleNotFoundError: No module named 'stock_assist.product_governance'`.

- [ ] **Step 4: Implement the governance domain**

Create `stock_assist/product_governance.py`:

```python
"""Bounded product-experiment governance for InsightRadar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

from stock_assist.paths import CONFIG_DIR, PROJECT_ROOT


DEFAULT_GOVERNANCE_PATH = CONFIG_DIR / "product_governance.json"
DEFAULT_FEATURE_PATH = PROJECT_ROOT / "feature_list.json"
VALID_LOOP_STAGES = {"observe", "explain", "decide", "verify", "governance"}
REQUIRED_EXPERIMENT_FIELDS = (
    "feature_id",
    "problem",
    "loop_stage",
    "baseline",
    "outcome_metric",
    "smallest_experiment",
    "safety_boundaries",
    "kill_criterion",
    "review_date",
)


@dataclass(frozen=True)
class Experiment:
    feature_id: str
    problem: str
    loop_stage: str
    baseline: str
    outcome_metric: str
    smallest_experiment: str
    safety_boundaries: tuple[str, ...]
    kill_criterion: str
    review_date: date


@dataclass(frozen=True)
class GovernanceSnapshot:
    max_active_experiments: int
    max_queued_experiments: int
    active_experiments: tuple[Experiment, ...]
    queued_experiments: tuple[Experiment, ...]

    @property
    def remaining_queue_slots(self) -> int:
        return max(0, self.max_queued_experiments - len(self.queued_experiments))


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _feature_statuses(path: Path) -> dict[str, str]:
    payload = _read_object(path)
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{path} must contain a features list")
    return {
        str(item["id"]): str(item.get("status", "unknown"))
        for item in features
        if isinstance(item, dict) and item.get("id")
    }


def _parse_experiment(raw: object, location: str) -> Experiment:
    if not isinstance(raw, dict):
        raise ValueError(f"{location} must be an object")
    missing = [field for field in REQUIRED_EXPERIMENT_FIELDS if not raw.get(field)]
    if missing:
        raise ValueError(f"{location} missing required fields: {', '.join(missing)}")
    loop_stage = str(raw["loop_stage"])
    if loop_stage not in VALID_LOOP_STAGES:
        raise ValueError(f"{location} has invalid loop_stage {loop_stage}")
    boundaries = raw["safety_boundaries"]
    if not isinstance(boundaries, list) or not boundaries or not all(
        isinstance(item, str) and item.strip() for item in boundaries
    ):
        raise ValueError(f"{location} safety_boundaries must be a non-empty string list")
    try:
        review_date = date.fromisoformat(str(raw["review_date"]))
    except ValueError as exc:
        raise ValueError(f"{location} review_date must use YYYY-MM-DD") from exc
    return Experiment(
        feature_id=str(raw["feature_id"]),
        problem=str(raw["problem"]),
        loop_stage=loop_stage,
        baseline=str(raw["baseline"]),
        outcome_metric=str(raw["outcome_metric"]),
        smallest_experiment=str(raw["smallest_experiment"]),
        safety_boundaries=tuple(str(item) for item in boundaries),
        kill_criterion=str(raw["kill_criterion"]),
        review_date=review_date,
    )


def load_governance_snapshot(
    config_path: Path = DEFAULT_GOVERNANCE_PATH,
    feature_path: Path = DEFAULT_FEATURE_PATH,
) -> GovernanceSnapshot:
    payload = _read_object(config_path)
    if payload.get("schema_version") != "insightradar-product-governance/v1":
        raise ValueError("unsupported product governance schema_version")
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("product governance limits must be an object")
    max_active = int(limits.get("max_active_experiments", 0))
    max_queued = int(limits.get("max_queued_experiments", 0))
    if max_active != 1:
        raise ValueError("max_active_experiments must equal 1")
    if max_queued != 2:
        raise ValueError("max_queued_experiments must equal 2")
    active_raw = payload.get("active_experiments", [])
    queued_raw = payload.get("queued_experiments", [])
    if not isinstance(active_raw, list) or not isinstance(queued_raw, list):
        raise ValueError("experiment collections must be lists")
    if len(active_raw) > max_active:
        raise ValueError("active experiment limit exceeded")
    if len(queued_raw) > max_queued:
        raise ValueError("queued experiment limit exceeded")
    active = tuple(
        _parse_experiment(item, f"active_experiments[{index}]")
        for index, item in enumerate(active_raw)
    )
    queued = tuple(
        _parse_experiment(item, f"queued_experiments[{index}]")
        for index, item in enumerate(queued_raw)
    )
    statuses = _feature_statuses(feature_path)
    seen: set[str] = set()
    for experiment in (*active, *queued):
        if experiment.feature_id in seen:
            raise ValueError(f"duplicate governed feature {experiment.feature_id}")
        seen.add(experiment.feature_id)
        if experiment.feature_id not in statuses:
            raise ValueError(f"unknown feature {experiment.feature_id}")
        if statuses[experiment.feature_id] == "pass":
            raise ValueError(
                f"completed feature {experiment.feature_id} cannot remain governed"
            )
    return GovernanceSnapshot(max_active, max_queued, active, queued)


def governance_markdown_lines(snapshot: GovernanceSnapshot) -> list[str]:
    lines = [
        f"活跃实验 {len(snapshot.active_experiments)}/{snapshot.max_active_experiments}",
        f"排队实验 {len(snapshot.queued_experiments)}/{snapshot.max_queued_experiments}",
        "实验状态只能由负责人或主 Agent 在明确批准后修改；evolve 只提供候选。",
    ]
    for experiment in snapshot.active_experiments:
        lines.append(
            f"{experiment.feature_id} 进行中：{experiment.problem}；复核日 "
            f"{experiment.review_date.isoformat()}；终止条件：{experiment.kill_criterion}"
        )
    for experiment in snapshot.queued_experiments:
        lines.append(
            f"{experiment.feature_id} 待负责人启动：{experiment.smallest_experiment}；复核日 "
            f"{experiment.review_date.isoformat()}；终止条件：{experiment.kill_criterion}"
        )
    return lines
```

Create `configs/product_governance.json` with no admitted product experiment during the bootstrap:

```json
{
  "schema_version": "insightradar-product-governance/v1",
  "limits": {
    "max_active_experiments": 1,
    "max_queued_experiments": 2
  },
  "active_experiments": [],
  "queued_experiments": []
}
```

- [ ] **Step 5: Run focused tests and commit the governance domain**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_product_governance
```

Expected: `Ran 6 tests` and `OK`.

Commit:

```powershell
git add configs/product_governance.json stock_assist/product_governance.py tests/test_product_governance.py
git commit -m "feat: add bounded product experiment governance"
```

### Task 2: Make `evolve` Truthful and Capacity-Aware

**Files:**

- Create: `tests/test_evolution.py`
- Modify: `stock_assist/workflows/evolution.py`

**Interfaces:**

- Consumes: `GovernanceSnapshot`, `load_governance_snapshot`, and the complete `feature_list.json`.
- Produces: `_load_features(path)`, `_feature_status(features)`, `_feature_lines(features)`, `_bound_backlog(backlog, snapshot)`, and a governance section in `build_evolution_report`.

- [ ] **Step 1: Write the failing evolution tests**

Create `tests/test_evolution.py`:

```python
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
            ["候选（尚未获准）：one", "候选（尚未获准）：two"],
        )

    def test_full_queue_blocks_new_recommendations(self) -> None:
        queued = (object(), object())
        snapshot = GovernanceSnapshot(1, 2, (), queued)  # type: ignore[arg-type]
        self.assertEqual(
            evolution._bound_backlog(["one"], snapshot),
            ["实验队列已满；先完成、终止或移出既有实验，不新增功能。"],
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
        self.assertIn("## 产品实验治理", report)
        self.assertIn("活跃实验 0/1", report)
        self.assertIn("feat-053 Guarded futures basis: pass", report)
        self.assertIn("feat-054 Harness bootstrap: in_progress", report)
        self.assertIn("data_source: 1", report)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the evolution tests to verify the intended failures**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_evolution
```

Expected: failures because `_feature_lines` still expects a dictionary, `_bound_backlog` does not exist, and `build_evolution_report` has no feature/governance path parameters.

- [ ] **Step 3: Replace the hard-coded feature view and add capacity gating**

In `stock_assist/workflows/evolution.py`, add these imports and constant:

```python
from collections import Counter

from stock_assist.product_governance import (
    DEFAULT_GOVERNANCE_PATH,
    GovernanceSnapshot,
    governance_markdown_lines,
    load_governance_snapshot,
)


FEATURE_PATH = PROJECT_ROOT / "feature_list.json"
```

Replace `_load_feature_status` and `_feature_lines` with:

```python
def _load_features(path: Path = FEATURE_PATH) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_features = payload.get("features", []) if isinstance(payload, dict) else []
    return [item for item in raw_features if isinstance(item, dict) and item.get("id")]


def _feature_status(features: list[dict[str, object]]) -> dict[str, str]:
    return {str(item["id"]): str(item.get("status", "unknown")) for item in features}


def _feature_number(item: dict[str, object]) -> int:
    try:
        return int(str(item["id"]).split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def _feature_lines(features: list[dict[str, object]]) -> list[str]:
    counts = Counter(str(item.get("status", "unknown")) for item in features)
    lines = [
        "状态汇总：" + ", ".join(
            f"{status}={counts[status]}" for status in sorted(counts)
        )
    ]
    unfinished = [item for item in features if str(item.get("status")) != "pass"]
    latest_pass = sorted(
        [item for item in features if str(item.get("status")) == "pass"],
        key=_feature_number,
    )[-8:]
    visible = sorted(unfinished, key=_feature_number) + latest_pass
    lines.extend(
        f"{item['id']} {item.get('name', 'Unnamed feature')}: "
        f"{item.get('status', 'unknown')}"
        for item in visible
    )
    return lines


def _bound_backlog(backlog: list[str], snapshot: GovernanceSnapshot) -> list[str]:
    if snapshot.remaining_queue_slots == 0:
        return ["实验队列已满；先完成、终止或移出既有实验，不新增功能。"]
    if not backlog:
        return ["暂无足够证据形成新实验；保留队列容量，不为填满 backlog 而造功能。"]
    return [
        f"候选（尚未获准）：{item}"
        for item in backlog[: snapshot.remaining_queue_slots]
    ]
```

Replace the complete `build_evolution_report` function with:

```python
def build_evolution_report(
    report_dir: Path = REPORT_DIR,
    feature_path: Path = FEATURE_PATH,
    governance_path: Path = DEFAULT_GOVERNANCE_PATH,
) -> str:
    features = _load_features(feature_path)
    feature_status = _feature_status(features)
    governance = load_governance_snapshot(governance_path, feature_path)
    local_state = _local_data_state()
    gaps: dict[str, int] = {key: 0 for key in KEYWORDS}
    files = (
        [path for path in sorted(report_dir.glob("*.md")) if not path.name.endswith("-evolution.md")]
        if report_dir.exists()
        else []
    )
    for path in files[-30:]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key, words in KEYWORDS.items():
            if any(word in text for word in words):
                gaps[key] += 1
    backlog = _bound_backlog(
        _build_backlog(gaps, feature_status, local_state), governance
    )
    outcome_snapshot = load_outcome_snapshot()
    return "\n".join(
        [
            "# 自我进化报告",
            "",
            "## 最近报告扫描",
            bullet([f"{key}: {value}" for key, value in gaps.items()]),
            "",
            "## 当前能力状态",
            bullet(_feature_lines(features)),
            "",
            "## 产品实验治理",
            bullet(governance_markdown_lines(governance)),
            "",
            "## 本地数据缺口",
            bullet(_local_state_lines(local_state)),
            "",
            "## 信号后验评分",
            bullet(outcome_markdown_lines(outcome_snapshot)),
            "",
            "## 下一轮 backlog",
            bullet(backlog),
        ]
    )
```

- [ ] **Step 4: Run focused tests and commit truthful evolution reporting**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_product_governance tests.test_evolution
```

Expected: `Ran 10 tests` and `OK`.

Commit:

```powershell
git add stock_assist/workflows/evolution.py tests/test_evolution.py
git commit -m "feat: govern evolution recommendations"
```

### Task 3: Define and Validate Project-Scoped Read-Only Agent Contracts

**Files:**

- Create: `.codex/agents/evidence_analyst.toml`
- Create: `.codex/agents/market_benchmark_analyst.toml`
- Create: `.codex/agents/product_critic.toml`
- Create: `.codex/agents/implementation_verifier.toml`
- Replace: `configs/agents.json`
- Create: `stock_assist/agent_contracts.py`
- Create: `scripts/validate_agent_contracts.py`
- Create: `tests/test_agent_contracts.py`

**Interfaces:**

- Consumes: the canonical Harness specification and `configs/agents.json` roster.
- Produces: exactly four read-only runtime contracts and `validate_agent_contracts(agent_dir, roster_path) -> list[str]`.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_agent_contracts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
import unittest

from stock_assist.agent_contracts import validate_agent_contracts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentContractTests(unittest.TestCase):
    def test_project_contracts_match_roster(self) -> None:
        errors = validate_agent_contracts(
            PROJECT_ROOT / ".codex" / "agents",
            PROJECT_ROOT / "configs" / "agents.json",
        )
        self.assertEqual(errors, [])

    def test_operating_model_caps_parallelism_and_serializes_writes(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "configs" / "agents.json").read_text(encoding="utf-8")
        )
        model = payload["operating_model"]
        self.assertEqual(model["max_parallel_task_agents"], 3)
        self.assertEqual(model["write_policy"], "lead_serializes_workspace_changes")
        self.assertEqual(model["max_active_experiments"], 1)
        self.assertEqual(model["max_queued_experiments"], 2)
        self.assertEqual(model["trade_authority"], "none")

    def test_exactly_four_runtime_contracts_are_read_only_and_non_recursive(self) -> None:
        paths = sorted((PROJECT_ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn('sandbox_mode = "read-only"', text)
            self.assertIn("agent-harness-job-readiness-design.md", text)
            self.assertIn("Do not modify the workspace", text)
            self.assertIn("Do not spawn subagents", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract test to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_agent_contracts
```

Expected: import fails with `ModuleNotFoundError: No module named 'stock_assist.agent_contracts'`.

- [ ] **Step 3: Replace the roster with the v2 operating model**

Replace `configs/agents.json` with:

```json
{
  "schema_version": "insightradar-agent-roster/v2",
  "operating_model": {
    "lead_role": "lead",
    "max_parallel_task_agents": 3,
    "write_policy": "lead_serializes_workspace_changes",
    "max_active_experiments": 1,
    "max_queued_experiments": 2,
    "product_authority": "human_owner_approves_priority_scope_and_release",
    "trade_authority": "none"
  },
  "agents": [
    {
      "id": "owner_reviewer",
      "name": "产品所有者 / 审核人",
      "runtime_agent": null,
      "engagement": "always",
      "mission": "批准北极星、优先级、范围扩大、实验启动和发布。",
      "authority": ["approve_product_priority", "approve_experiment_start", "approve_release"],
      "inputs": ["设计规范", "实验卡", "验收证据"],
      "outputs": ["批准", "否决", "范围调整"]
    },
    {
      "id": "lead",
      "name": "主 Agent / CEO-CPO / 架构负责人",
      "runtime_agent": "default",
      "engagement": "always",
      "mission": "管理产品闭环，只启动必要角色，串行集成所有写入，并提交可验证结果。",
      "authority": ["delegate_read_only_analysis", "integrate_workspace_changes", "propose_experiments"],
      "inputs": ["英文主设计", "CURRENT_STATE.md", "feature_list.json", "验证证据"],
      "outputs": ["范围明确的计划", "集成提交", "阶段验收"]
    },
    {
      "id": "evidence_analyst",
      "name": "证据分析师",
      "runtime_agent": "evidence_analyst",
      "engagement": "on_demand",
      "mission": "核对来源、时点、实体映射、缺失字段和事实边界；不给交易结论。",
      "authority": ["read_workspace", "read_approved_sources", "report_evidence_gaps"],
      "inputs": ["目标问题", "相关本地数据", "允许的来源清单"],
      "outputs": ["带来源的事实", "冲突与缺口", "置信度边界"]
    },
    {
      "id": "market_benchmark_analyst",
      "name": "市场与竞品分析师",
      "runtime_agent": "market_benchmark_analyst",
      "engagement": "on_demand",
      "mission": "检查产品、用户工作流和可验证最佳实践，区分有效闭环与表面功能。",
      "authority": ["read_workspace", "research_public_sources", "report_benchmark_gaps"],
      "inputs": ["产品问题", "目标用户", "当前闭环"],
      "outputs": ["竞品证据", "可借鉴机制", "不建议复制的功能"]
    },
    {
      "id": "product_critic",
      "name": "产品批评者",
      "runtime_agent": "product_critic",
      "engagement": "before_experiment_admission",
      "mission": "挑战问题、指标、最小实验、终止条件和功能膨胀；无权批准功能。",
      "authority": ["read_workspace", "challenge_experiment", "recommend_rejection"],
      "inputs": ["实验卡", "基线", "用户价值证据"],
      "outputs": ["反例", "范围削减建议", "准入意见"]
    },
    {
      "id": "implementation_verifier",
      "name": "独立测试与运维验收者",
      "runtime_agent": "implementation_verifier",
      "engagement": "before_completion",
      "mission": "独立检查需求、测试、真实产物、数据缺口、恢复与运行证据；不修改实现。",
      "authority": ["read_workspace", "run_read_only_verification", "block_completion_claim"],
      "inputs": ["实现差异", "验收标准", "测试和真实产物"],
      "outputs": ["验收结论", "缺陷清单", "残余风险"]
    }
  ]
}
```

- [ ] **Step 4: Create the four exact read-only runtime contracts**

Create `.codex/agents/evidence_analyst.toml`:

```toml
name = "evidence_analyst"
description = "Read-only analyst for provenance, point-in-time facts, entity mapping, and explicit gaps."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.
Work only on the bounded evidence question assigned by the lead.
Do not modify the workspace, create commits, or change product state.
Do not spawn subagents.
Separate verified fact, inference, conflict, stale input, and unknown field.
Research evidence has no trade authority. Return source and file references to the lead.
"""
nickname_candidates = ["Ledger", "Beacon", "Trace"]
```

Create `.codex/agents/market_benchmark_analyst.toml`:

```toml
name = "market_benchmark_analyst"
description = "Read-only benchmark analyst focused on proven workflows instead of feature imitation."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.
Work only on the bounded benchmark question assigned by the lead.
Do not modify the workspace, create commits, or change product state.
Do not spawn subagents.
Compare the user problem, workflow, evidence, and outcome measurement.
Return source-linked mechanisms, anti-patterns, and open questions to the lead.
"""
nickname_candidates = ["Scout", "Signal", "Compass"]
```

Create `.codex/agents/product_critic.toml`:

```toml
name = "product_critic"
description = "Read-only challenger for experiment admission, value, scope, and kill criteria."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.
Review only the experiment assigned by the lead.
Do not modify the workspace, create commits, approve scope, or change product state.
Do not spawn subagents.
Challenge the problem, baseline, metric, smallest experiment, safety boundary, and kill criterion.
Return blocking objections first, then an admit, revise, or reject recommendation.
"""
nickname_candidates = ["Skeptic", "Prism", "Gate"]
```

Create `.codex/agents/implementation_verifier.toml`:

```toml
name = "implementation_verifier"
description = "Read-only verifier for requirements, tests, artifacts, restartability, and residual risk."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.
Verify only the bounded implementation assigned by the lead.
Do not modify the workspace, create commits, or repair failures.
Do not spawn subagents.
Inspect the diff, focused tests, full tests, real artifacts, explicit gaps, and restart instructions.
Return findings by severity, reproduction commands, and a pass or fail verdict.
"""
nickname_candidates = ["Sentinel", "Proof", "Audit"]
```

- [ ] **Step 5: Implement the Python 3.10-compatible validator**

Create `stock_assist/agent_contracts.py`:

```python
"""Validation for project-scoped agent contracts."""

from __future__ import annotations

import json
from pathlib import Path
import re


SINGLE_LINE_FIELD = re.compile(r'^([a-z_]+)\s*=\s*"([^"]*)"\s*$', re.MULTILINE)
INSTRUCTION_BLOCK = re.compile(r'developer_instructions\s*=\s*"""(.*?)"""', re.DOTALL)
REQUIRED_INSTRUCTIONS = (
    "agent-harness-job-readiness-design.md",
    "Do not modify the workspace",
    "Do not spawn subagents",
)


def _parse_contract(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    fields = {match.group(1): match.group(2) for match in SINGLE_LINE_FIELD.finditer(text)}
    instructions = INSTRUCTION_BLOCK.search(text)
    return fields, instructions.group(1).strip() if instructions else ""


def validate_agent_contracts(agent_dir: Path, roster_path: Path) -> list[str]:
    errors: list[str] = []
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    runtime_agents = {
        str(agent["runtime_agent"])
        for agent in roster.get("agents", [])
        if agent.get("runtime_agent") not in {None, "default"}
    }
    files = sorted(agent_dir.glob("*.toml")) if agent_dir.exists() else []
    if len(files) != 4:
        errors.append(f"expected exactly 4 agent contracts, found {len(files)}")
    contracts: dict[str, Path] = {}
    for path in files:
        fields, instructions = _parse_contract(path)
        name = fields.get("name", "")
        if not name:
            errors.append(f"{path}: missing name")
            continue
        contracts[name] = path
        if not fields.get("description"):
            errors.append(f"{path}: missing description")
        if fields.get("sandbox_mode") != "read-only":
            errors.append(f"{path}: sandbox_mode must be read-only")
        if not instructions:
            errors.append(f"{path}: missing developer_instructions")
        for required in REQUIRED_INSTRUCTIONS:
            if required not in instructions:
                errors.append(f"{path}: developer_instructions missing {required}")
    errors.extend(
        f"roster runtime agent has no TOML contract: {name}"
        for name in sorted(runtime_agents - contracts.keys())
    )
    errors.extend(
        f"TOML contract is not routed by roster: {name}"
        for name in sorted(contracts.keys() - runtime_agents)
    )
    return errors
```

Create `scripts/validate_agent_contracts.py`:

```python
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_assist.agent_contracts import validate_agent_contracts


def main() -> int:
    errors = validate_agent_contracts(
        PROJECT_ROOT / ".codex" / "agents",
        PROJECT_ROOT / "configs" / "agents.json",
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Agent contracts valid: roster and read-only runtime roles are aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run focused tests and commit the contracts**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_agent_contracts
.venv\Scripts\python scripts\validate_agent_contracts.py
```

Expected: `Ran 3 tests`, `OK`, and `Agent contracts valid: roster and read-only runtime roles are aligned.`

Commit:

```powershell
git add .codex/agents configs/agents.json stock_assist/agent_contracts.py scripts/validate_agent_contracts.py tests/test_agent_contracts.py
git commit -m "feat: define bounded agent contracts"
```

### Task 4: Render the Operating Model in the `agents` Report

**Files:**

- Create: `tests/test_agent_roster.py`
- Modify: `stock_assist/workflows/agent_roster.py`

**Interfaces:**

- Consumes: `configs/agents.json` schema `insightradar-agent-roster/v2`.
- Produces: `build_agent_roster_report(config_path) -> str` with visible authority, capacity, role, and trade boundaries.

- [ ] **Step 1: Write the failing roster tests**

Create `tests/test_agent_roster.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.workflows.agent_roster import build_agent_roster_report


class AgentRosterTests(unittest.TestCase):
    def test_report_shows_limits_authority_and_runtime_agent(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agents.json"
            path.write_text(json.dumps({
                "schema_version": "insightradar-agent-roster/v2",
                "operating_model": {
                    "lead_role": "lead",
                    "max_parallel_task_agents": 3,
                    "write_policy": "lead_serializes_workspace_changes",
                    "max_active_experiments": 1,
                    "max_queued_experiments": 2,
                    "product_authority": "human_owner_approves_priority_scope_and_release",
                    "trade_authority": "none"
                },
                "agents": [{
                    "id": "product_critic",
                    "name": "产品批评者",
                    "runtime_agent": "product_critic",
                    "engagement": "before_experiment_admission",
                    "mission": "挑战实验。",
                    "authority": ["challenge_experiment"],
                    "inputs": ["实验卡"],
                    "outputs": ["准入意见"]
                }]
            }, ensure_ascii=False), encoding="utf-8")
            report = build_agent_roster_report(path)
        self.assertIn("最多并行任务 Agent：3", report)
        self.assertIn("活跃实验上限：1；排队实验上限：2", report)
        self.assertIn("lead_serializes_workspace_changes", report)
        self.assertIn("交易权限：none", report)
        self.assertIn("运行时角色：product_critic", report)
        self.assertIn("权限边界：challenge_experiment", report)

    def test_report_preserves_missing_config_diagnostic(self) -> None:
        with TemporaryDirectory() as tmp:
            report = build_agent_roster_report(Path(tmp) / "missing.json")
        self.assertIn("数据缺口", report)
        self.assertIn("missing.json", report)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the roster tests to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_agent_roster
```

Expected: the first test fails because the current renderer has no operating-model section.

- [ ] **Step 3: Replace the roster renderer**

Replace `stock_assist/workflows/agent_roster.py` with:

```python
"""Agent operating-model reporting."""

from __future__ import annotations

import json
from pathlib import Path

from stock_assist.paths import CONFIG_DIR


DEFAULT_AGENTS_PATH = CONFIG_DIR / "agents.json"


def _joined(values: object) -> str:
    if not isinstance(values, list):
        return "未填写"
    return ", ".join(str(value) for value in values) or "未填写"


def build_agent_roster_report(config_path: Path = DEFAULT_AGENTS_PATH) -> str:
    if not config_path.exists():
        return "\n".join(["# Agent 分工表", "", "## 数据缺口", f"- 未找到配置：{config_path}"])
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    operating_model = payload.get("operating_model", {})
    lines = [
        "# Agent 分工表",
        "",
        "## 运行模型",
        f"- 主角色：{operating_model.get('lead_role', '未填写')}",
        f"- 最多并行任务 Agent：{operating_model.get('max_parallel_task_agents', '未填写')}",
        f"- 写入策略：{operating_model.get('write_policy', '未填写')}",
        (
            f"- 活跃实验上限：{operating_model.get('max_active_experiments', '未填写')}；"
            f"排队实验上限：{operating_model.get('max_queued_experiments', '未填写')}"
        ),
        f"- 产品权限：{operating_model.get('product_authority', '未填写')}",
        f"- 交易权限：{operating_model.get('trade_authority', '未填写')}",
        "",
    ]
    for agent in payload.get("agents", []):
        lines.extend([
            f"## {agent.get('name', '未命名')} ({agent.get('id', 'missing-id')})",
            f"- 运行时角色：{agent.get('runtime_agent') or '人工角色'}",
            f"- 介入时点：{agent.get('engagement', '未填写')}",
            f"- 任务：{agent.get('mission', '未填写')}",
            f"- 权限边界：{_joined(agent.get('authority'))}",
            f"- 输入：{_joined(agent.get('inputs'))}",
            f"- 输出：{_joined(agent.get('outputs'))}",
            "",
        ])
    return "\n".join(lines)
```

- [ ] **Step 4: Run focused tests and commit roster reporting**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_agent_contracts tests.test_agent_roster
```

Expected: `Ran 5 tests` and `OK`.

Commit:

```powershell
git add stock_assist/workflows/agent_roster.py tests/test_agent_roster.py
git commit -m "feat: render agent operating boundaries"
```

### Task 5: Add Versioned Task Manifest and Failure Contracts

**Files:**

- Create: `stock_assist/harness_eval/__init__.py`
- Create: `stock_assist/harness_eval/models.py`
- Create: `stock_assist/harness_eval/manifest.py`
- Create: `configs/harness_eval/smoke_task.json`
- Create: `tests/test_harness_manifest.py`

**Interfaces:**

- Consumes: a JSON task manifest with schema `insightradar-harness-task/v1`.
- Produces: `PrivacyClass`, `FailureClass`, `TaskBudget`, `AcceptanceCheck`, `TaskManifest`, and `load_task_manifest(path) -> TaskManifest` for Tasks 6-8.

- [ ] **Step 1: Write the failing manifest tests**

Create `tests/test_harness_manifest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.harness_eval.manifest import load_task_manifest
from stock_assist.harness_eval.models import PrivacyClass


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "insightradar-harness-task/v1",
        "task_id": "harness-smoke-001",
        "title": "Harness contract smoke",
        "goal": "Validate task, trace, privacy, and checkpoint contracts without a model call.",
        "context_refs": ["AGENTS.md", "CURRENT_STATE.md"],
        "memory_refs": ["docs/memory/product-state.md"],
        "allowed_tools": ["read_project_files", "write_runtime_artifacts"],
        "budget": {"max_steps": 8, "max_tool_calls": 4, "max_elapsed_seconds": 30},
        "expected_artifacts": ["trace.jsonl", "checkpoint.json", "harness-smoke.md"],
        "acceptance_checks": [
            {"id": "trace", "kind": "file_exists", "target": "trace.jsonl", "expected": "true"},
            {"id": "trade", "kind": "text_contains", "target": "harness-smoke.md", "expected": "交易权限：none"}
        ],
        "privacy_class": "public"
    }


class HarnessManifestTests(unittest.TestCase):
    def _write(self, root: Path, payload: object) -> Path:
        path = root / "task.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_loads_valid_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = load_task_manifest(self._write(Path(tmp), _manifest()))
        self.assertEqual(manifest.task_id, "harness-smoke-001")
        self.assertEqual(manifest.privacy_class, PrivacyClass.PUBLIC)
        self.assertEqual(manifest.budget.max_tool_calls, 4)
        self.assertEqual(manifest.acceptance_checks[1].kind, "text_contains")

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
            with self.assertRaisesRegex(ValueError, "forbidden sensitive key api_key"):
                load_task_manifest(self._write(Path(tmp), payload))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the manifest tests to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_manifest
```

Expected: import fails with `ModuleNotFoundError: No module named 'stock_assist.harness_eval'`.

- [ ] **Step 3: Implement the versioned domain models**

Create `stock_assist/harness_eval/models.py`:

```python
"""Versioned Agent Harness evaluation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


TASK_SCHEMA_VERSION = "insightradar-harness-task/v1"
TRACE_SCHEMA_VERSION = "insightradar-harness-trace/v1"
CHECKPOINT_SCHEMA_VERSION = "insightradar-harness-checkpoint/v1"


class PrivacyClass(str, Enum):
    PUBLIC = "public"
    SANITIZED = "sanitized"
    PRIVATE = "private"
    SECRET = "secret"


class FailureClass(str, Enum):
    CONTEXT_MISSING = "context_missing"
    CONTEXT_MISROUTED = "context_misrouted"
    STALE_MEMORY = "stale_memory"
    CONFLICTING_MEMORY = "conflicting_memory"
    INCORRECT_MEMORY_RECALL = "incorrect_memory_recall"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_MALFORMED_RESULT = "tool_malformed_result"
    UNEXPECTED_SIDE_EFFECT = "unexpected_side_effect"
    SCOPE_DRIFT = "scope_drift"
    ARTIFACT_MISMATCH = "artifact_mismatch"
    FALSE_COMPLETION = "false_completion"
    AGENT_CONFLICT = "agent_conflict"
    DUPLICATE_AGENT_WORK = "duplicate_agent_work"
    CHECKPOINT_MISSING = "checkpoint_missing"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    GOAL_DRIFT = "goal_drift"
    UNSUPPORTED_INVESTMENT_ACTION = "unsupported_investment_action"
    PRIVACY_LEAK = "privacy_leak"


@dataclass(frozen=True)
class TaskBudget:
    max_steps: int
    max_tool_calls: int
    max_elapsed_seconds: int


@dataclass(frozen=True)
class AcceptanceCheck:
    id: str
    kind: str
    target: str
    expected: str


@dataclass(frozen=True)
class TaskManifest:
    schema_version: str
    task_id: str
    title: str
    goal: str
    context_refs: tuple[str, ...]
    memory_refs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    budget: TaskBudget
    expected_artifacts: tuple[str, ...]
    acceptance_checks: tuple[AcceptanceCheck, ...]
    privacy_class: PrivacyClass
```

Create `stock_assist/harness_eval/__init__.py`:

```python
"""Reusable Agent Harness governance and evaluation contracts."""

from stock_assist.harness_eval.manifest import load_task_manifest
from stock_assist.harness_eval.models import (
    AcceptanceCheck,
    FailureClass,
    PrivacyClass,
    TaskBudget,
    TaskManifest,
)

__all__ = [
    "AcceptanceCheck",
    "FailureClass",
    "PrivacyClass",
    "TaskBudget",
    "TaskManifest",
    "load_task_manifest",
]
```

- [ ] **Step 4: Implement strict manifest loading and secret-key rejection**

Create `stock_assist/harness_eval/manifest.py`:

```python
"""Strict loading for versioned Harness task manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_assist.harness_eval.models import (
    AcceptanceCheck,
    PrivacyClass,
    TASK_SCHEMA_VERSION,
    TaskBudget,
    TaskManifest,
)


REQUIRED_FIELDS = (
    "schema_version",
    "task_id",
    "title",
    "goal",
    "context_refs",
    "memory_refs",
    "allowed_tools",
    "budget",
    "expected_artifacts",
    "acceptance_checks",
    "privacy_class",
)
FORBIDDEN_KEYS = {
    "api_key",
    "token",
    "password",
    "cookie",
    "authorization",
    "broker_account",
    "cost_basis",
}
VALID_CHECK_KINDS = {"file_exists", "text_contains", "exit_code"}


def _reject_sensitive_keys(value: object, location: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_KEYS:
                raise ValueError(f"{location} contains forbidden sensitive key {normalized}")
            _reject_sensitive_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{location}[{index}]")


def _non_empty_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _string_tuple(raw: dict[str, Any], key: str, allow_empty: bool = False) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{key} must be a string list")
    if not allow_empty and not value:
        raise ValueError(f"{key} must not be empty")
    return tuple(item.strip() for item in value)


def load_task_manifest(path: Path) -> TaskManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("task manifest must be a JSON object")
    _reject_sensitive_keys(payload)
    for field in REQUIRED_FIELDS:
        if field not in payload:
            raise ValueError(f"missing required field {field}")
    if payload["schema_version"] != TASK_SCHEMA_VERSION:
        raise ValueError(f"unsupported task schema_version {payload['schema_version']}")
    try:
        privacy_class = PrivacyClass(str(payload["privacy_class"]))
    except ValueError as exc:
        raise ValueError(f"invalid privacy_class {payload['privacy_class']}") from exc
    budget_raw = payload["budget"]
    if not isinstance(budget_raw, dict):
        raise ValueError("budget must be an object")
    budget = TaskBudget(
        max_steps=int(budget_raw.get("max_steps", 0)),
        max_tool_calls=int(budget_raw.get("max_tool_calls", 0)),
        max_elapsed_seconds=int(budget_raw.get("max_elapsed_seconds", 0)),
    )
    if min(budget.max_steps, budget.max_tool_calls, budget.max_elapsed_seconds) <= 0:
        raise ValueError("budget values must be positive integers")
    checks_raw = payload["acceptance_checks"]
    if not isinstance(checks_raw, list) or not checks_raw:
        raise ValueError("acceptance_checks must be a non-empty list")
    checks: list[AcceptanceCheck] = []
    for index, item in enumerate(checks_raw):
        if not isinstance(item, dict):
            raise ValueError(f"acceptance_checks[{index}] must be an object")
        kind = _non_empty_string(item, "kind")
        if kind not in VALID_CHECK_KINDS:
            raise ValueError(f"acceptance_checks[{index}] has invalid kind {kind}")
        checks.append(AcceptanceCheck(
            id=_non_empty_string(item, "id"),
            kind=kind,
            target=_non_empty_string(item, "target"),
            expected=_non_empty_string(item, "expected"),
        ))
    return TaskManifest(
        schema_version=TASK_SCHEMA_VERSION,
        task_id=_non_empty_string(payload, "task_id"),
        title=_non_empty_string(payload, "title"),
        goal=_non_empty_string(payload, "goal"),
        context_refs=_string_tuple(payload, "context_refs"),
        memory_refs=_string_tuple(payload, "memory_refs", allow_empty=True),
        allowed_tools=_string_tuple(payload, "allowed_tools"),
        budget=budget,
        expected_artifacts=_string_tuple(payload, "expected_artifacts"),
        acceptance_checks=tuple(checks),
        privacy_class=privacy_class,
    )
```

Create `configs/harness_eval/smoke_task.json`:

```json
{
  "schema_version": "insightradar-harness-task/v1",
  "task_id": "harness-smoke-001",
  "title": "Harness contract smoke",
  "goal": "Validate task, trace, privacy, and checkpoint contracts without a model call or investment side effect.",
  "context_refs": ["AGENTS.md", "CURRENT_STATE.md"],
  "memory_refs": ["docs/memory/product-state.md"],
  "allowed_tools": ["read_project_files", "write_runtime_artifacts"],
  "budget": {
    "max_steps": 8,
    "max_tool_calls": 4,
    "max_elapsed_seconds": 30
  },
  "expected_artifacts": ["trace.jsonl", "checkpoint.json", "harness-smoke.md"],
  "acceptance_checks": [
    {"id": "trace", "kind": "file_exists", "target": "trace.jsonl", "expected": "true"},
    {"id": "checkpoint", "kind": "file_exists", "target": "checkpoint.json", "expected": "true"},
    {"id": "trade", "kind": "text_contains", "target": "harness-smoke.md", "expected": "交易权限：none"}
  ],
  "privacy_class": "public"
}
```

- [ ] **Step 5: Run focused tests and commit the manifest contracts**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_manifest
.venv\Scripts\python -m json.tool configs\harness_eval\smoke_task.json > $null
```

Expected: `Ran 4 tests`, `OK`, and JSON validation exits `0`.

Commit:

```powershell
git add stock_assist/harness_eval configs/harness_eval/smoke_task.json tests/test_harness_manifest.py
git commit -m "feat: add versioned harness task contracts"
```

### Task 6: Add Structured Trace Recording and Fail-Closed Public Validation

**Files:**

- Create: `stock_assist/harness_eval/trace.py`
- Create: `tests/test_harness_trace.py`

**Interfaces:**

- Consumes: `PrivacyClass` and schema `insightradar-harness-trace/v1`.
- Produces: `TraceEvent`, `TraceWriter.append(event_type, payload, privacy_class)`, and `validate_public_trace(path) -> list[str]` for Tasks 7-9.

- [ ] **Step 1: Write the failing trace tests**

Create `tests/test_harness_trace.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.harness_eval.models import PrivacyClass
from stock_assist.harness_eval.trace import TraceWriter, validate_public_trace


NOW = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)


class HarnessTraceTests(unittest.TestCase):
    def test_writer_assigns_monotonic_sequence_and_version(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            writer = TraceWriter(path, "run-001", clock=lambda: NOW)
            first = writer.append("run_started", {"task_id": "task-1"}, PrivacyClass.PUBLIC)
            second = writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(rows[0]["schema_version"], "insightradar-harness-trace/v1")
        self.assertNotIn("reasoning", rows[0]["payload"])

    def test_writer_rejects_secret_keys_and_secret_events(self) -> None:
        with TemporaryDirectory() as tmp:
            writer = TraceWriter(Path(tmp) / "trace.jsonl", "run-001", clock=lambda: NOW)
            with self.assertRaisesRegex(ValueError, "sensitive key token"):
                writer.append("tool_completed", {"token": "secret"}, PrivacyClass.PRIVATE)
            with self.assertRaisesRegex(ValueError, "secret events cannot be traced"):
                writer.append("tool_completed", {"status": "available"}, PrivacyClass.SECRET)

    def test_public_validation_rejects_private_events_and_absolute_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            writer = TraceWriter(path, "run-001", clock=lambda: NOW)
            writer.append("run_started", {"artifact": "C:\\private\\portfolio.json"}, PrivacyClass.PUBLIC)
            writer.append("run_completed", {"status": "pass"}, PrivacyClass.PRIVATE)
            errors = validate_public_trace(path)
        self.assertTrue(any("absolute path" in error for error in errors))
        self.assertTrue(any("private" in error for error in errors))

    def test_public_validation_accepts_sanitized_relative_references(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            writer = TraceWriter(path, "run-001", clock=lambda: NOW)
            writer.append("run_started", {"context_ref": "AGENTS.md"}, PrivacyClass.PUBLIC)
            writer.append("run_completed", {"status": "pass"}, PrivacyClass.SANITIZED)
            errors = validate_public_trace(path)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the trace tests to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_trace
```

Expected: import fails with `ModuleNotFoundError: No module named 'stock_assist.harness_eval.trace'`.

- [ ] **Step 3: Implement the trace writer and public validation**

Create `stock_assist/harness_eval/trace.py`:

```python
"""Structured trace recording without hidden reasoning or secret material."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Callable

from stock_assist.harness_eval.models import PrivacyClass, TRACE_SCHEMA_VERSION


ALLOWED_EVENT_TYPES = {
    "run_started",
    "context_loaded",
    "memory_retrieved",
    "tool_requested",
    "tool_completed",
    "checkpoint_saved",
    "checkpoint_restored",
    "verification_result",
    "policy_blocked",
    "human_correction",
    "failure_classified",
    "run_completed",
}
SENSITIVE_KEYS = {"api_key", "token", "password", "cookie", "authorization", "secret"}
HIDDEN_REASONING_KEYS = {"reasoning", "chain_of_thought", "hidden_thoughts"}
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
SECRET_VALUE = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._-]{8,}|api[_-]?key\s*[:=])")


@dataclass(frozen=True)
class TraceEvent:
    schema_version: str
    run_id: str
    sequence: int
    event_type: str
    occurred_at: str
    privacy_class: str
    payload: dict[str, object]


def _inspect_keys(value: object, location: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_KEYS:
                raise ValueError(f"{location} contains sensitive key {normalized}")
            if normalized in HIDDEN_REASONING_KEYS:
                raise ValueError(f"{location} contains hidden reasoning key {normalized}")
            _inspect_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _inspect_keys(child, f"{location}[{index}]")


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _string_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in _string_values(child)]
    return []


class TraceWriter:
    def __init__(
        self,
        path: Path,
        run_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.run_id = run_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sequence = 0

    def append(
        self,
        event_type: str,
        payload: dict[str, object],
        privacy_class: PrivacyClass,
    ) -> TraceEvent:
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported trace event_type {event_type}")
        if privacy_class is PrivacyClass.SECRET:
            raise ValueError("secret events cannot be traced")
        _inspect_keys(payload)
        if any(SECRET_VALUE.search(value) for value in _string_values(payload)):
            raise ValueError("payload contains a credential-like value")
        self.sequence += 1
        event = TraceEvent(
            schema_version=TRACE_SCHEMA_VERSION,
            run_id=self.run_id,
            sequence=self.sequence,
            event_type=event_type,
            occurred_at=self.clock().astimezone(timezone.utc).isoformat(),
            privacy_class=privacy_class.value,
            payload=payload,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return event


def validate_public_trace(path: Path) -> list[str]:
    errors: list[str] = []
    expected_sequence = 1
    expected_run_id: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if row.get("schema_version") != TRACE_SCHEMA_VERSION:
            errors.append(f"line {line_number}: unsupported trace schema_version")
        if row.get("sequence") != expected_sequence:
            errors.append(f"line {line_number}: non-monotonic sequence")
        expected_sequence += 1
        run_id = str(row.get("run_id", ""))
        expected_run_id = expected_run_id or run_id
        if not run_id or run_id != expected_run_id:
            errors.append(f"line {line_number}: inconsistent run_id")
        privacy = str(row.get("privacy_class", ""))
        if privacy not in {PrivacyClass.PUBLIC.value, PrivacyClass.SANITIZED.value}:
            errors.append(f"line {line_number}: privacy class {privacy or 'missing'} is not public-exportable")
        try:
            _inspect_keys(row.get("payload", {}))
        except ValueError as exc:
            errors.append(f"line {line_number}: {exc}")
        for value in _string_values(row.get("payload", {})):
            if WINDOWS_ABSOLUTE_PATH.match(value):
                errors.append(f"line {line_number}: unresolved absolute path")
            if SECRET_VALUE.search(value):
                errors.append(f"line {line_number}: credential-like value")
    return errors
```

- [ ] **Step 4: Run focused tests and commit tracing**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_manifest tests.test_harness_trace
```

Expected: `Ran 8 tests` and `OK`.

Commit:

```powershell
git add stock_assist/harness_eval/trace.py tests/test_harness_trace.py
git commit -m "feat: record privacy-bounded harness traces"
```

### Task 7: Add Atomic Checkpoints and a Deterministic Harness Smoke Run

**Files:**

- Create: `stock_assist/harness_eval/checkpoint.py`
- Create: `stock_assist/harness_eval/smoke.py`
- Create: `tests/test_harness_checkpoint.py`

**Interfaces:**

- Consumes: `TaskManifest`, `TraceWriter`, `validate_public_trace`, and runtime output directory.
- Produces: `Checkpoint`, `goal_digest(goal)`, `save_checkpoint`, `load_checkpoint`, `SmokeResult`, and `run_contract_smoke(manifest_path, output_dir, run_id, clock)` for CLI integration.

- [ ] **Step 1: Write failing checkpoint and smoke tests**

Create `tests/test_harness_checkpoint.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.harness_eval.checkpoint import (
    Checkpoint,
    goal_digest,
    load_checkpoint,
    save_checkpoint,
)
from stock_assist.harness_eval.smoke import run_contract_smoke
from stock_assist.harness_eval.trace import validate_public_trace


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
            artifact_hashes={"trace.jsonl": "abc123"},
            created_at=NOW.isoformat(),
        )

    def test_atomic_checkpoint_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(self._checkpoint(), path)
            restored = load_checkpoint(path, "harness-smoke-001", "same goal")
        self.assertEqual(restored.sequence, 3)
        self.assertEqual(restored.verified_steps, ("manifest_loaded",))

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

    def test_contract_smoke_creates_public_trace_checkpoint_and_report(self) -> None:
        with TemporaryDirectory() as tmp:
            result = run_contract_smoke(
                MANIFEST,
                Path(tmp),
                run_id="smoke-001",
                clock=lambda: NOW,
            )
            self.assertTrue(result.trace_path.exists())
            self.assertTrue(result.checkpoint_path.exists())
            self.assertEqual(validate_public_trace(result.trace_path), [])
            self.assertIn("交易权限：none", result.markdown)
            self.assertIn("模型调用：none", result.markdown)
            self.assertIn("公开 Trace 校验：PASS", result.markdown)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the checkpoint tests to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_checkpoint
```

Expected: import fails because `checkpoint.py` and `smoke.py` do not exist.

- [ ] **Step 3: Implement atomic checkpoint persistence and goal continuity**

Create `stock_assist/harness_eval/checkpoint.py`:

```python
"""Atomic, goal-bound checkpoints for long-running Harness tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path

from stock_assist.harness_eval.models import CHECKPOINT_SCHEMA_VERSION


@dataclass(frozen=True)
class Checkpoint:
    schema_version: str
    run_id: str
    task_id: str
    goal_hash: str
    sequence: int
    verified_steps: tuple[str, ...]
    pending_steps: tuple[str, ...]
    artifact_hashes: dict[str, str]
    created_at: str


def goal_digest(goal: str) -> str:
    return hashlib.sha256(goal.encode("utf-8")).hexdigest()


def save_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
    if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unsupported checkpoint schema_version")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_checkpoint(path: Path, expected_task_id: str, expected_goal: str) -> Checkpoint:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("checkpoint is not valid JSON") from exc
    if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unsupported checkpoint schema_version")
    if payload.get("task_id") != expected_task_id:
        raise ValueError("checkpoint task mismatch")
    if payload.get("goal_hash") != goal_digest(expected_goal):
        raise ValueError("checkpoint goal drift detected")
    return Checkpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        run_id=str(payload["run_id"]),
        task_id=str(payload["task_id"]),
        goal_hash=str(payload["goal_hash"]),
        sequence=int(payload["sequence"]),
        verified_steps=tuple(str(item) for item in payload.get("verified_steps", [])),
        pending_steps=tuple(str(item) for item in payload.get("pending_steps", [])),
        artifact_hashes={str(key): str(value) for key, value in payload.get("artifact_hashes", {}).items()},
        created_at=str(payload["created_at"]),
    )
```

- [ ] **Step 4: Implement the deterministic no-model smoke workflow**

Create `stock_assist/harness_eval/smoke.py`:

```python
"""Deterministic smoke workflow for Harness contracts and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Callable

from stock_assist.harness_eval.checkpoint import (
    Checkpoint,
    goal_digest,
    load_checkpoint,
    save_checkpoint,
)
from stock_assist.harness_eval.manifest import load_task_manifest
from stock_assist.harness_eval.models import CHECKPOINT_SCHEMA_VERSION, PrivacyClass
from stock_assist.harness_eval.trace import TraceWriter, validate_public_trace
from stock_assist.paths import CONFIG_DIR, DATA_DIR


DEFAULT_MANIFEST_PATH = CONFIG_DIR / "harness_eval" / "smoke_task.json"
DEFAULT_OUTPUT_DIR = DATA_DIR / "harness_eval" / "runs"


@dataclass(frozen=True)
class SmokeResult:
    run_id: str
    trace_path: Path
    checkpoint_path: Path
    markdown: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_contract_smoke(
    manifest_path: Path | None = None,
    output_dir: Path | None = None,
    run_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> SmokeResult:
    now = clock or (lambda: datetime.now(timezone.utc))
    manifest = load_task_manifest(manifest_path or DEFAULT_MANIFEST_PATH)
    actual_run_id = run_id or now().strftime("smoke-%Y%m%dT%H%M%SZ")
    run_dir = (output_dir or DEFAULT_OUTPUT_DIR) / actual_run_id
    trace_path = run_dir / "trace.jsonl"
    checkpoint_path = run_dir / "checkpoint.json"
    writer = TraceWriter(trace_path, actual_run_id, clock=now)
    writer.append("run_started", {"task_id": manifest.task_id}, PrivacyClass.PUBLIC)
    writer.append(
        "context_loaded",
        {"context_refs": list(manifest.context_refs), "memory_refs": list(manifest.memory_refs)},
        PrivacyClass.PUBLIC,
    )
    checkpoint = Checkpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        run_id=actual_run_id,
        task_id=manifest.task_id,
        goal_hash=goal_digest(manifest.goal),
        sequence=writer.sequence,
        verified_steps=("manifest_loaded", "context_refs_recorded"),
        pending_steps=("public_trace_verified",),
        artifact_hashes={},
        created_at=now().astimezone(timezone.utc).isoformat(),
    )
    save_checkpoint(checkpoint, checkpoint_path)
    writer.append(
        "checkpoint_saved",
        {"checkpoint_ref": checkpoint_path.name},
        PrivacyClass.PUBLIC,
    )
    restored = load_checkpoint(checkpoint_path, manifest.task_id, manifest.goal)
    writer.append(
        "checkpoint_restored",
        {"verified_steps": list(restored.verified_steps)},
        PrivacyClass.PUBLIC,
    )
    writer.append(
        "verification_result",
        {"check": "checkpoint_goal_continuity", "status": "pass"},
        PrivacyClass.PUBLIC,
    )
    writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)
    public_errors = validate_public_trace(trace_path)
    if public_errors:
        raise ValueError("public trace validation failed: " + "; ".join(public_errors))
    markdown = "\n".join([
        "# Agent Harness Contract Smoke",
        "",
        f"- Run ID：{actual_run_id}",
        f"- Task：{manifest.task_id}",
        f"- Privacy：{manifest.privacy_class.value}",
        "- 模型调用：none",
        "- 交易权限：none",
        "- Checkpoint 目标连续性：PASS",
        "- 公开 Trace 校验：PASS",
        f"- Trace SHA-256：{_sha256(trace_path)}",
        f"- Trace：{trace_path}",
        f"- Checkpoint：{checkpoint_path}",
    ])
    return SmokeResult(actual_run_id, trace_path, checkpoint_path, markdown)
```

- [ ] **Step 5: Run focused tests and commit checkpoint/smoke behavior**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_manifest tests.test_harness_trace tests.test_harness_checkpoint
```

Expected: `Ran 12 tests` and `OK`.

Commit:

```powershell
git add stock_assist/harness_eval/checkpoint.py stock_assist/harness_eval/smoke.py tests/test_harness_checkpoint.py
git commit -m "feat: add goal-bound harness checkpoints"
```

### Task 8: Expose the Bootstrap Through CLI, Product Map, Architecture, and Harness Contracts

**Files:**

- Create: `tests/test_harness_integration.py`
- Modify: `stock_assist/cli.py`
- Modify: `stock_assist/product.py`
- Modify: `configs/architecture.json`
- Modify: `docs/harness.md`
- Regenerate: `docs/architecture.html`

**Interfaces:**

- Consumes: all Tasks 1-7 interfaces.
- Produces: `harness-smoke` CLI, product/architecture registration, real ignored runtime artifacts, and a durable Definition of Done.

- [ ] **Step 1: Write failing product/architecture integration tests**

Create `tests/test_harness_integration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
import unittest

from stock_assist.product import FILES, command_for


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HarnessIntegrationTests(unittest.TestCase):
    def test_product_registry_exposes_smoke_and_contract_files(self) -> None:
        command = command_for("harness-smoke")
        self.assertIn("configs/harness_eval/smoke_task.json", command.inputs)
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
        self.assertTrue(any(
            edge["from"] == "harness_eval" and edge["to"] == "evolution"
            for edge in payload["edges"]
        ))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the integration tests to verify the intended failure**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_integration
```

Expected: one error for missing `harness-smoke` and one failure for missing `harness_eval` architecture node.

- [ ] **Step 3: Register the CLI command and runtime execution**

In `stock_assist/cli.py`, add this import:

```python
from stock_assist.harness_eval.smoke import run_contract_smoke
```

After the `agents` parser registration, add:

```python
    harness_smoke = subparsers.add_parser("harness-smoke", help=command_for("harness-smoke").help)
    harness_smoke.add_argument("--manifest", type=Path, default=None, help="optional Harness task manifest")
    harness_smoke.add_argument("--output-dir", type=Path, default=None, help="optional runtime artifact directory")
```

After the `args.command == "agents"` branch, add:

```python
        elif args.command == "harness-smoke":
            result = run_contract_smoke(args.manifest, args.output_dir)
            report_path = write_report("harness-smoke", result.markdown)
            path = f"{result.trace_path}\n{result.checkpoint_path}\n{report_path}"
```

- [ ] **Step 4: Register product files and command inputs/outputs**

In `stock_assist/product.py`, add this command immediately after `agents`:

```python
    ProductCommand(
        name="harness-smoke",
        module_key="ops",
        help="run deterministic Agent Harness task, trace, privacy, and checkpoint contracts",
        run_hint="Run after Harness contract changes; it performs no model call, network request, or trade action.",
        inputs=(
            "configs/harness_eval/smoke_task.json",
            "configs/product_governance.json",
            "configs/agents.json",
        ),
        outputs=("data/harness_eval/runs/*", "reports/*-harness-smoke.md"),
        retry="Fix the manifest, privacy, trace, or checkpoint contract named in the error and rerun `insight-radar harness-smoke`.",
    ),
```

Change the `agents` command inputs to:

```python
        inputs=("configs/agents.json", ".codex/agents/*.toml"),
```

Change the `evolve` command inputs to:

```python
        inputs=("feature_list.json", "configs/product_governance.json", "reports/*.md", "local config/data state"),
```

Add these `ProductFile` entries immediately after `configs/agents.json`:

```python
    ProductFile("configs/product_governance.json", "product_config", "ops", "Bounded product-experiment admission and kill gates."),
    ProductFile(".codex/agents/*.toml", "agent_contract", "ops", "Project-scoped read-only task-agent contracts."),
    ProductFile("configs/harness_eval/*.json", "schema", "ops", "Versioned Harness task manifests and reproducible smoke inputs."),
    ProductFile("data/harness_eval/*", "private_runtime_data", "ops", "Ignored local traces, checkpoints, and benchmark run state."),
```

- [ ] **Step 5: Add the architecture node and edges**

In `configs/architecture.json`, update the `agent_roster` node to:

```json
{
  "id": "agent_roster",
  "ring": "governance",
  "title": "Agent 分工表",
  "type": "governance",
  "lane": "ops",
  "status": "active",
  "commands": ["agents"],
  "command": "python -m stock_assist.cli agents",
  "summary": "呈现人工权限、主 Agent 串行写入、只读任务角色和并行上限。",
  "inputs": ["configs/agents.json", ".codex/agents/*.toml"],
  "outputs": ["reports/*-agents.md"],
  "next": ["保持角色契约一致", "只在任务可拆分时使用并行"]
}
```

Insert this node immediately after `agent_roster`:

```json
{
  "id": "harness_eval",
  "ring": "governance",
  "title": "Agent Harness 合同与评测",
  "type": "workflow",
  "lane": "ops",
  "status": "bootstrap",
  "commands": ["harness-smoke"],
  "command": "python -m stock_assist.cli harness-smoke",
  "summary": "用版本化 task、trace、privacy 和 checkpoint 合同生成无模型、无交易副作用的确定性 smoke 证据。",
  "inputs": ["configs/harness_eval/smoke_task.json", "configs/product_governance.json", "configs/agents.json"],
  "outputs": ["data/harness_eval/runs/*", "reports/*-harness-smoke.md"],
  "next": ["建立真实任务基线", "对 Context、Memory 和 Multi-Agent 做消融"]
}
```

Update the `evolution` node inputs and summary to:

```json
"summary": "扫描业务报告和完整 feature 目录，并只提出能够装入剩余实验容量的未批准候选。",
"inputs": ["feature_list.json", "configs/product_governance.json", "业务报告", "本地配置/数据状态"]
```

Add these edges without changing existing edges:

```json
{"from": "agent_roster", "to": "harness_eval", "label": "角色与权限合同"},
{"from": "harness_eval", "to": "evolution", "label": "失败与验证证据"}
```

- [ ] **Step 6: Add the Harness Definition of Done**

Under `### Evolution Backlog` in `docs/harness.md`, add this sibling section after its minimum checks:

```markdown
### Agent Harness Bootstrap (`feat-054`)

Done means:

- Product governance permits at most one active and two queued experiments; only the human owner or lead after explicit approval changes experiment state.
- `evolve` reads the complete feature catalog, exposes experiment capacity, and never starts, completes, or reprioritizes work.
- Exactly four project-scoped task-agent contracts match the roster; all are read-only, non-recursive, and subordinate to lead-only workspace writes.
- Versioned task, trace, privacy, failure, and checkpoint contracts use Python 3.10 standard-library code and do not depend on a model or network call.
- Traces contain structured events and artifact references, never secrets or hidden chain-of-thought. Public validation fails closed on private/secret events, credential-like values, or unresolved absolute private paths.
- Checkpoint restore verifies task identity and goal hash; corrupt JSON or goal drift fails visibly.
- `harness-smoke` generates a fresh ignored trace and checkpoint plus a Markdown report that states model call `none`, trade authority `none`, checkpoint continuity `PASS`, and public trace validation `PASS`.
- Production investment workflows remain unchanged. This bootstrap cannot authorize trades or claim that Context, Memory, checkpointing, or Multi-Agent improves performance before the benchmark phase.

Minimum checks:

- `.venv\Scripts\python -m unittest -v tests.test_product_governance tests.test_evolution tests.test_agent_contracts tests.test_agent_roster tests.test_harness_manifest tests.test_harness_trace tests.test_harness_checkpoint tests.test_harness_integration`
- `.venv\Scripts\python scripts\validate_agent_contracts.py`
- `.venv\Scripts\python -m stock_assist.cli agents`
- `.venv\Scripts\python -m stock_assist.cli evolve`
- `.venv\Scripts\python -m stock_assist.cli harness-smoke`
- Inspect the newest agents, evolution, and harness-smoke Markdown reports plus the referenced trace/checkpoint artifacts.
- `.venv\Scripts\python scripts\validate_project_memory.py`
- `node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar`
```

- [ ] **Step 7: Run integration tests, regenerate architecture, and commit**

Run:

```powershell
.venv\Scripts\python -m unittest -v tests.test_harness_integration
.venv\Scripts\python -m stock_assist.cli architecture-view
.venv\Scripts\python scripts\validate_agent_contracts.py
.venv\Scripts\python scripts\validate_project_memory.py
```

Expected: `Ran 2 tests`, `OK`; architecture generation prints `docs\architecture.html`; both validators exit `0`; project-memory command coverage includes `harness-smoke`.

Commit:

```powershell
git add stock_assist/cli.py stock_assist/product.py configs/architecture.json docs/architecture.html docs/harness.md tests/test_harness_integration.py
git commit -m "feat: expose agent harness bootstrap"
```

### Task 9: Generate Real Evidence, Independently Verify, and Close `feat-054`

**Files:**

- Generate but do not stage: `reports/*-agents.md`
- Generate but do not stage: `reports/*-evolution.md`
- Generate but do not stage: `reports/*-harness-smoke.md`
- Generate but do not stage: `data/harness_eval/runs/*`
- Modify: `feature_list.json`
- Modify: `configs/product_governance.json`
- Modify: `CURRENT_STATE.md`
- Modify: `docs/memory/product-state.md`
- Modify: `progress.md`
- Modify: `session-handoff.md`

**Interfaces:**

- Consumes: the completed bootstrap, full regression suite, real CLI artifacts, and an independent read-only verdict.
- Produces: `feat-054=pass`, pending `feat-056`, one queued Harness benchmark experiment, restartable state, and a clean worktree.

- [ ] **Step 1: Run focused and full verification with separate exit statuses**

Run each command separately; stop at the first failure and apply `superpowers:systematic-debugging` before continuing:

```powershell
.venv\Scripts\python -m unittest -v tests.test_product_governance tests.test_evolution tests.test_agent_contracts tests.test_agent_roster tests.test_harness_manifest tests.test_harness_trace tests.test_harness_checkpoint tests.test_harness_integration
.venv\Scripts\python -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python -m compileall stock_assist scripts
.venv\Scripts\python scripts\validate_agent_contracts.py
.venv\Scripts\python -c "import json; [json.load(open(p, encoding='utf-8')) for p in ['feature_list.json','configs/agents.json','configs/product_governance.json','configs/architecture.json','configs/harness_eval/smoke_task.json']]"
.venv\Scripts\python scripts\validate_project_memory.py
node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar
git diff --check
```

Expected:

- Focused suite: `Ran 29 tests` and `OK`.
- Full suite: all tests pass; record the actual count rather than assuming the prior 85-test baseline.
- Compileall, contract validator, JSON parsing, project-memory validation, Harness structural validation, and diff check exit `0`.

- [ ] **Step 2: Generate and inspect fresh real artifacts**

Run:

```powershell
.venv\Scripts\python -m stock_assist.cli agents
.venv\Scripts\python -m stock_assist.cli evolve
.venv\Scripts\python -m stock_assist.cli harness-smoke
$agentReport = Get-ChildItem reports\*-agents.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$evolutionReport = Get-ChildItem reports\*-evolution.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$smokeReport = Get-ChildItem reports\*-harness-smoke.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$smokeLines = Get-Content -LiteralPath $smokeReport.FullName -Encoding UTF8
$traceLine = $smokeLines | Where-Object { $_ -like '- Trace：*' } | Select-Object -First 1
$checkpointLine = $smokeLines | Where-Object { $_ -like '- Checkpoint：*' } | Select-Object -First 1
$tracePath = $traceLine.Substring('- Trace：'.Length)
$checkpointPath = $checkpointLine.Substring('- Checkpoint：'.Length)
Select-String -LiteralPath $agentReport.FullName -Pattern '最多并行任务 Agent：3','lead_serializes_workspace_changes','交易权限：none','implementation_verifier'
Select-String -LiteralPath $evolutionReport.FullName -Pattern '产品实验治理','活跃实验 0/1','排队实验 0/2','feat-054'
Select-String -LiteralPath $smokeReport.FullName -Pattern '模型调用：none','交易权限：none','Checkpoint 目标连续性：PASS','公开 Trace 校验：PASS'
Test-Path -LiteralPath $tracePath
Test-Path -LiteralPath $checkpointPath
.venv\Scripts\python -c "from pathlib import Path; from stock_assist.harness_eval.trace import validate_public_trace; import sys; errors=validate_public_trace(Path(sys.argv[1])); print(errors); raise SystemExit(bool(errors))" $tracePath
```

Expected:

- All three commands print fresh artifact paths.
- Every `Select-String` finds all requested contract lines.
- Both `Test-Path` commands return `True`.
- Public trace validation prints `[]` and exits `0`.
- No output claims a model comparison, performance improvement, or trade authority.

- [ ] **Step 3: Obtain an independent read-only verdict**

If executing with `superpowers:subagent-driven-development`, dispatch the project-scoped `implementation_verifier` with this exact prompt. If executing inline, start one fresh read-only verifier agent solely for this gate; it must not repair its own findings:

```text
Verify feat-054 read-only. Check the canonical 2026-07-21 Agent Harness specification, the 2026-07-21 bootstrap implementation plan, the full git diff, focused/full test evidence, agent/evolution/harness-smoke reports, referenced trace/checkpoint artifacts, experiment limits, lead-only writes, four read-only non-recursive task-agent contracts, public trace fail-closed behavior, checkpoint goal continuity, and absence of model-performance or trade-authority claims. Do not modify files. Return findings by severity and a final pass/fail verdict with exact evidence paths and reproduction commands.
```

Expected: the verifier returns `PASS` with no blocking findings. The lead fixes any blocking finding, reruns its focused test, and then reruns every later command from Step 1 onward.

- [ ] **Step 4: Register the next benchmark feature and queue it without starting it**

Append this object to `feature_list.json` after `feat-055` while preserving all existing objects:

```json
{
  "id": "feat-056",
  "name": "Agent Harness real-task benchmark baseline",
  "description": "Build 20-30 private or sanitized real-world tasks, run no-Harness, instructions-only, current-Harness, and improved-Harness profiles, and report deterministic success, evidence correctness, false completion, scope drift, privacy, recovery, cost, latency, and human-correction baselines without claiming unmeasured model superiority.",
  "dependencies": ["feat-054"],
  "status": "pending",
  "evidence": "Approved as phase two of the 2026-07-21 Agent Harness engineering design. No benchmark implementation plan or run has started; first action is a separate written plan after feat-054 closeout."
}
```

Replace `configs/product_governance.json` with:

```json
{
  "schema_version": "insightradar-product-governance/v1",
  "limits": {
    "max_active_experiments": 1,
    "max_queued_experiments": 2
  },
  "active_experiments": [],
  "queued_experiments": [
    {
      "feature_id": "feat-056",
      "problem": "InsightRadar has a structurally complete Harness but no behavioral baseline proving which controls improve real tasks.",
      "loop_stage": "verify",
      "baseline": "Harness structure scores 100/100, but no versioned 20-30-task suite or four-profile comparison exists.",
      "outcome_metric": "Every eligible task reports deterministic success, evidence correctness, false completion, scope drift, privacy, recovery, token or context volume when available, tool calls, elapsed time, and human corrections across declared profiles.",
      "smallest_experiment": "Plan and run a five-task pilot across the four profiles before scaling the accepted schema to 20-30 tasks.",
      "safety_boundaries": [
        "Use synthetic or private local tasks only",
        "No holdings, broker data, credentials, or raw private conversations in public artifacts",
        "Deterministic checks are primary; model judging is secondary",
        "No benchmark result grants trade authority or model-superiority claims"
      ],
      "kill_criterion": "Stop expansion if the five-task pilot cannot produce reproducible deterministic verdicts or leaks private/secret data.",
      "review_date": "2026-08-17"
    }
  ]
}
```

Run:

```powershell
.venv\Scripts\python -c "import json; from stock_assist.product_governance import load_governance_snapshot; p=json.load(open('feature_list.json', encoding='utf-8')); assert next(x for x in p['features'] if x['id']=='feat-056')['status']=='pending'; s=load_governance_snapshot(); assert [x.feature_id for x in s.queued_experiments]==['feat-056']"
```

Expected: exit code `0`; `feat-056` is queued but not active.

- [ ] **Step 5: Record factual closeout and restart state**

Update the `feat-054` object in `feature_list.json`:

- set `status` to `pass` only after Steps 1-4 pass;
- replace `evidence` with one compact paragraph containing the actual focused/full test counts, the three fresh report filenames, public trace/checkpoint validation, project-memory and Harness validation results, and independent verifier verdict;
- state explicitly that the smoke run makes no model-performance claim and that `feat-056` remains pending.

Update `CURRENT_STATE.md`:

- set manifest `updated_at` to the actual closeout date;
- set `next_feature_id` to `feat-056`;
- add one compact verified-baseline bullet for `feat-054`;
- replace the deferred Agent Harness note under `Next Feature` with `feat-056` and its separate-plan requirement;
- keep the file below 120 lines and 16 KB.

Update `docs/memory/product-state.md` with the verified `feat-054` contract boundary and a pointer to `feat-056`; do not copy volatile report values beyond the evidence filenames stored in the feature record.

Append a dated `progress.md` section with scope, files, actual verification results, real artifact filenames, verifier verdict, privacy/no-trade boundary, and recommended next step `feat-056` planning.

Append a concise `session-handoff.md` section stating:

- `feat-054` is complete;
- the lead is the sole writer and at most three read-only non-recursive task agents may run when justified;
- task/trace/privacy/checkpoint contracts exist, but behavioral improvement is not yet proven;
- `feat-056` is the sole queued experiment and requires its own implementation plan;
- `feat-044` and `feat-055` remain pending and are not authorized to jump ahead of the resumed Harness program.

Generate the final evolution artifact after these state changes:

```powershell
.venv\Scripts\python -m stock_assist.cli evolve
$finalEvolutionReport = Get-ChildItem reports\*-evolution.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -LiteralPath $finalEvolutionReport.FullName -Pattern '排队实验 1/2','feat-054','pass','feat-056','待负责人启动'
```

Expected: the final report shows `feat-054` as passed, `feat-056` as the sole queued experiment, and no automatic start. Use this final evolution filename in `feat-054` evidence, progress, and handoff instead of the pre-closeout evolution filename.

- [ ] **Step 6: Re-run closeout validation and inspect the final diff**

Run:

```powershell
.venv\Scripts\python -c "import json; p=json.load(open('feature_list.json', encoding='utf-8')); assert next(x for x in p['features'] if x['id']=='feat-054')['status']=='pass'; assert next(x for x in p['features'] if x['id']=='feat-056')['status']=='pending'"
.venv\Scripts\python -m unittest -v tests.test_product_governance tests.test_evolution tests.test_agent_contracts tests.test_agent_roster tests.test_harness_manifest tests.test_harness_trace tests.test_harness_checkpoint tests.test_harness_integration
.venv\Scripts\python scripts\validate_agent_contracts.py
.venv\Scripts\python scripts\validate_project_memory.py
node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar
git diff --check
git status --short
git diff --stat
```

Expected: all checks pass; focused suite remains `Ran 29 tests`; `CURRENT_STATE.md` stays within its limits; the diff contains only intended source, config, tests, generated architecture, and closeout documentation. Ignored runtime reports, traces, checkpoints, private data, secrets, and `.learnings` do not appear in staged changes.

- [ ] **Step 7: Commit the verified closeout**

Run:

```powershell
git add feature_list.json configs/product_governance.json CURRENT_STATE.md docs/memory/product-state.md progress.md session-handoff.md
git diff --cached --check
git commit -m "feat: complete agent harness bootstrap"
git status --short --branch
```

Expected: commit succeeds and the final worktree is clean. Do not stage ignored `reports/` or `data/harness_eval/` artifacts; their exact paths remain recorded as verification evidence.

## Acceptance Checklist

- `feat-054` is `pass`; `feat-056` is `pending` and the sole queued experiment; `feat-044` and `feat-055` remain pending outside the active Harness queue.
- Governance rejects capacity violations, unknown/completed/duplicate features, missing gates, invalid dates, and invalid loop stages.
- `evolve` reads the full feature catalog, exposes experiment capacity, excludes its own old reports, and cannot mutate state.
- Exactly four project-scoped task-agent contracts match the v2 roster; all are read-only, non-recursive, and subordinate to lead-only writes.
- Task manifests are versioned, budgeted, explicit about tools/artifacts/acceptance/privacy, and reject embedded secret keys.
- Traces have monotonic events, contain no secret or hidden-reasoning keys, and fail public validation on private/secret classes, credential-like values, or unresolved absolute private paths.
- Checkpoints are atomic and goal-bound; corrupt JSON, task mismatch, or goal drift fails visibly.
- `harness-smoke` makes no model or network call, has no trade authority, and generates a fresh report, public-valid trace, and goal-valid checkpoint.
- Product registry, CLI, architecture JSON/HTML, harness contract, project memory, feature state, progress, and handoff agree.
- Focused 29-test suite, full regression, compileall, JSON parsing, agent-contract validator, project-memory validator, Harness structural validator, real artifacts, independent read-only verdict, and diff checks pass.
- No investment workflow, provider adapter, event ingestion, candidate ranking, automatic trading, model-performance claim, or EvidenceHarness public extraction leaks into this increment.
