# Agent-Governed Product Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Give InsightRadar a bounded, evidence-led multi-agent operating system that permits at most one active product experiment, limits the queue to two, exposes the real feature state to `evolve`, and equips Codex with narrow read-only analyst, product, and verification roles while the lead agent remains the only workspace writer.

**Architecture:** Add a project-governance configuration and parser as the source of truth for experiment admission; make the evolution report consume the full feature catalog and governance snapshot instead of a hard-coded legacy list; define project-scoped Codex custom agents as narrow read-only task roles; mirror those roles in the product roster and validate the two representations together. The human owner keeps approval authority, the root Codex agent acts as lead/CEO-CPO/architect, and at most three child agents may run concurrently. Workspace writes remain serialized by the lead.

**Tech Stack:** Python 3.10+, standard library (`dataclasses`, `datetime`, `json`, `pathlib`, `re`), pytest/unittest-compatible tests, JSON configuration, Codex project agent TOML, existing InsightRadar CLI/report helpers, PowerShell verification commands.

## Global Constraints

- The canonical product contract is `docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md`. The Chinese review copy is non-normative and must not drive implementation decisions.
- This plan implements the iteration control plane only. It does not implement event ingestion, candidate ranking, Alpha Report generation, or trade execution.
- The root Codex agent is the sole writer and integrator. All custom child agents added here are read-only and may not spawn descendants.
- Keep the runtime limit at one lead plus at most three task agents. Do not raise recursive spawn depth.
- Admit at most one active product experiment and two queued experiments. `evolve` may recommend only enough candidates to fill remaining queue capacity; it must never change experiment state automatically.
- New evidence and recommendations do not have trade authority. No agent may turn research confidence into an order or an unconditional buy/sell instruction.
- Preserve existing Markdown report commands and outputs.
- Use test-driven development for each behavior change. Run the focused failure before implementation, then the focused pass.
- Do not edit or commit ignored `.learnings` files as part of this feature.
- `feat-054` is the bootstrap implementation of this control plane, not an admitted user-facing product experiment. It may be `in_progress` while `active_experiments` is empty; governed product admission begins with queued `feat-044` after the bootstrap is verified.

---

## Delivery Boundary and Follow-on Plans

This plan is the first of four independently verifiable increments:

1. **This plan — agent-governed iteration control plane:** experiment admission, truthful evolution reporting, Codex role contracts, and roster visibility.
2. **Event intelligence plan:** official filings, Jin10/7x24 macro events, international-market context, entity/theme mapping, severity, deduplication, freshness, and key-alert routing. This begins with the already-prioritized `feat-044` source-discovery slice.
3. **Controlled candidate-pool plan:** generate zero to five evidence-backed candidates only when holdings are absent or portfolio-specific coverage is complete; include abstention and rejection reasons.
4. **Alpha delivery and calibration plan:** deliver event-driven Alpha Reports across user-relevant decision windows and close the loop through 1/5/20-session outcome calibration.

Do not combine those later increments into this implementation. Completing this plan should leave `feat-044` as the next product experiment awaiting explicit start by the owner/lead.

### Task 1: Add the Experiment-Governance Domain and Queue Contract

**Files:**

- Create: `stock_assist/product_governance.py`
- Create: `tests/test_product_governance.py`
- Create: `configs/product_governance.json`
- Modify: `feature_list.json`

**Step 1: Register the implementation feature before changing code**

Append this entry to `feature_list.json` and leave every existing feature unchanged:

```json
{
  "id": "feat-054",
  "name": "Agent-governed product iteration control plane",
  "description": "Add bounded product-experiment admission, truthful full-catalog evolution reporting, project-scoped read-only Codex task roles, serialized lead-only writes, and validated agent-roster contracts so InsightRadar converges on decision quality instead of feature count.",
  "dependencies": ["feat-004", "feat-035", "feat-053"],
  "status": "in_progress",
  "evidence": "User-approved design and implementation plan on 2026-07-19. Scope is limited to product-iteration governance and agent-role contracts; event ingestion, candidate ranking, Alpha delivery, and trade execution remain out of scope."
}
```

Run:

```powershell
.venv\Scripts\python -c "import json; p=json.load(open('feature_list.json', encoding='utf-8')); assert p['features'][-1]['id']=='feat-054'; assert p['features'][-1]['status']=='in_progress'"
```

Expected: exit code `0`.

Commit:

```powershell
git add feature_list.json
git commit -m "chore: start agent governance feature"
```

**Step 2: Write the failing governance tests**

Create `tests/test_product_governance.py`:

```python
import json
from pathlib import Path

import pytest

from stock_assist.product_governance import (
    governance_markdown_lines,
    load_governance_snapshot,
)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _features(tmp_path: Path, status: str = "pending") -> Path:
    return _write_json(
        tmp_path / "feature_list.json",
        {"features": [{"id": "feat-044", "name": "Official IR discovery", "status": status}]},
    )


def _experiment(feature_id: str = "feat-044") -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "problem": "Official evidence arrives faster than the current manual ingestion path.",
        "loop_stage": "observe",
        "baseline": "feat-044 is pending and there is no official discovery ingestion.",
        "outcome_metric": "All admitted records retain source URL, source timestamp, and observed-at timestamp.",
        "smallest_experiment": "Replay one hyperscaler source and one supplier disclosure source.",
        "safety_boundaries": ["Official sources only", "No trade authority"],
        "kill_criterion": "Stop if any admitted record loses point-in-time provenance.",
        "review_date": "2026-07-27",
    }


def _governance(tmp_path: Path, active: list[dict] | None = None, queued: list[dict] | None = None) -> Path:
    return _write_json(
        tmp_path / "product_governance.json",
        {
            "schema_version": "insightradar-product-governance/v1",
            "limits": {"max_active_experiments": 1, "max_queued_experiments": 2},
            "active_experiments": active or [],
            "queued_experiments": queued or [],
        },
    )


def test_loads_valid_governance_snapshot(tmp_path: Path) -> None:
    snapshot = load_governance_snapshot(
        _governance(tmp_path, queued=[_experiment()]),
        _features(tmp_path),
    )

    assert snapshot.max_active_experiments == 1
    assert snapshot.max_queued_experiments == 2
    assert snapshot.active_experiments == ()
    assert snapshot.queued_experiments[0].feature_id == "feat-044"
    assert snapshot.remaining_queue_slots == 1


@pytest.mark.parametrize(
    ("active", "queued", "message"),
    [
        ([_experiment(), _experiment()], [], "active experiment limit"),
        ([], [_experiment(), _experiment(), _experiment()], "queued experiment limit"),
    ],
)
def test_rejects_experiment_limit_violations(
    tmp_path: Path,
    active: list[dict],
    queued: list[dict],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        load_governance_snapshot(
            _governance(tmp_path, active=active, queued=queued),
            _features(tmp_path),
        )


def test_rejects_unknown_or_completed_features(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown feature feat-999"):
        load_governance_snapshot(
            _governance(tmp_path, queued=[_experiment("feat-999")]),
            _features(tmp_path),
        )

    with pytest.raises(ValueError, match="completed feature feat-044"):
        load_governance_snapshot(
            _governance(tmp_path, queued=[_experiment()]),
            _features(tmp_path, status="pass"),
        )


def test_rejects_missing_gate_field(tmp_path: Path) -> None:
    experiment = _experiment()
    del experiment["kill_criterion"]

    with pytest.raises(ValueError, match="kill_criterion"):
        load_governance_snapshot(
            _governance(tmp_path, queued=[experiment]),
            _features(tmp_path),
        )


def test_governance_markdown_exposes_owner_gate_and_kill_criterion(tmp_path: Path) -> None:
    snapshot = load_governance_snapshot(
        _governance(tmp_path, queued=[_experiment()]),
        _features(tmp_path),
    )

    lines = governance_markdown_lines(snapshot)

    assert any("活跃实验 0/1" in line for line in lines)
    assert any("feat-044" in line and "待负责人启动" in line for line in lines)
    assert any("2026-07-27" in line for line in lines)
    assert any("Stop if any admitted record" in line for line in lines)
```

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_product_governance.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'stock_assist.product_governance'`.

**Step 3: Implement the governance model and validation**

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
    if not isinstance(boundaries, list) or not all(isinstance(item, str) and item.strip() for item in boundaries):
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

    active = tuple(_parse_experiment(item, f"active_experiments[{index}]") for index, item in enumerate(active_raw))
    queued = tuple(_parse_experiment(item, f"queued_experiments[{index}]") for index, item in enumerate(queued_raw))
    statuses = _feature_statuses(feature_path)
    feature_ids: set[str] = set()
    for experiment in (*active, *queued):
        if experiment.feature_id in feature_ids:
            raise ValueError(f"duplicate governed feature {experiment.feature_id}")
        feature_ids.add(experiment.feature_id)
        if experiment.feature_id not in statuses:
            raise ValueError(f"unknown feature {experiment.feature_id}")
        if statuses[experiment.feature_id] == "pass":
            raise ValueError(f"completed feature {experiment.feature_id} cannot remain governed")

    return GovernanceSnapshot(
        max_active_experiments=max_active,
        max_queued_experiments=max_queued,
        active_experiments=active,
        queued_experiments=queued,
    )


def governance_markdown_lines(snapshot: GovernanceSnapshot) -> list[str]:
    lines = [
        f"活跃实验 {len(snapshot.active_experiments)}/{snapshot.max_active_experiments}",
        f"排队实验 {len(snapshot.queued_experiments)}/{snapshot.max_queued_experiments}",
        "实验状态只能由负责人或主 Agent 在明确批准后修改；evolve 只提供候选。",
    ]
    for experiment in snapshot.active_experiments:
        lines.append(
            f"{experiment.feature_id} 进行中：{experiment.problem}；复核日 {experiment.review_date.isoformat()}；"
            f"终止条件：{experiment.kill_criterion}"
        )
    for experiment in snapshot.queued_experiments:
        lines.append(
            f"{experiment.feature_id} 待负责人启动：{experiment.smallest_experiment}；复核日 "
            f"{experiment.review_date.isoformat()}；终止条件：{experiment.kill_criterion}"
        )
    return lines
```

Create `configs/product_governance.json`:

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
      "feature_id": "feat-044",
      "problem": "Official hyperscaler and supplier disclosures can change the AI CapEx evidence state before the current manual research path captures them.",
      "loop_stage": "observe",
      "baseline": "feat-044 is pending; official IR discovery, point-in-time provenance, deduplication, and freshness checks are not implemented.",
      "outcome_metric": "On the acceptance replay set, 100% of admitted records retain source URL, source timestamp, observed-at timestamp, and explicit missing fields; duplicate records are not emitted twice.",
      "smallest_experiment": "Replay official disclosures from one hyperscaler and ????C through a bounded discovery and normalization slice; do not add scheduling, candidate ranking, or trade actions.",
      "safety_boundaries": [
        "Official first-party sources only for the acceptance slice",
        "Point-in-time provenance is mandatory",
        "Missing values remain explicit and are never imputed as facts",
        "Research evidence has no trade authority"
      ],
      "kill_criterion": "Stop the slice if any admitted record cannot retain its official source identity, source timestamp, and observed-at timestamp.",
      "review_date": "2026-07-27"
    }
  ]
}
```

**Step 4: Run the focused tests**

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_product_governance.py -q
```

Expected: `6 passed`.

**Step 5: Commit the governance domain**

```powershell
git add configs/product_governance.json stock_assist/product_governance.py tests/test_product_governance.py
git commit -m "feat: add bounded product experiment governance"
```

### Task 2: Make `evolve` Read the Full Catalog and Respect Capacity

**Files:**

- Create: `tests/test_evolution.py`
- Modify: `stock_assist/workflows/evolution.py`

**Step 1: Write failing evolution tests**

Create `tests/test_evolution.py`:

```python
import json
from pathlib import Path

from stock_assist.product_governance import GovernanceSnapshot
from stock_assist.workflows import evolution


def test_feature_lines_show_full_catalog_and_latest_pass() -> None:
    features = [
        {"id": "feat-027", "name": "Signal outcome ledger", "status": "pass"},
        {"id": "feat-044", "name": "Official IR discovery", "status": "pending"},
        {"id": "feat-053", "name": "Guarded futures basis", "status": "pass"},
    ]

    lines = evolution._feature_lines(features)

    assert any("pending=1" in line and "pass=2" in line for line in lines)
    assert any("feat-044 Official IR discovery: pending" in line for line in lines)
    assert any("feat-053 Guarded futures basis: pass" in line for line in lines)


def test_governed_backlog_is_bounded_by_remaining_queue_slots() -> None:
    snapshot = GovernanceSnapshot(
        max_active_experiments=1,
        max_queued_experiments=2,
        active_experiments=(),
        queued_experiments=(),
    )

    assert evolution._bound_backlog(["one", "two", "three"], snapshot) == ["one", "two"]


def test_full_queue_blocks_new_admission_recommendations() -> None:
    queued = (object(), object())
    snapshot = GovernanceSnapshot(
        max_active_experiments=1,
        max_queued_experiments=2,
        active_experiments=(),
        queued_experiments=queued,  # type: ignore[arg-type]
    )

    lines = evolution._bound_backlog(["one"], snapshot)

    assert lines == ["实验队列已满；先完成、终止或移出既有实验，不新增功能。"]


def test_build_report_contains_governance_and_excludes_old_evolution_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "20260719-after-close.md").write_text("Missing required", encoding="utf-8")
    (report_dir / "20260719-evolution.md").write_text("Missing required", encoding="utf-8")
    feature_path = tmp_path / "feature_list.json"
    feature_path.write_text(
        json.dumps(
            {
                "features": [
                    {"id": "feat-044", "name": "Official IR discovery", "status": "pending"},
                    {"id": "feat-053", "name": "Guarded futures basis", "status": "pass"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evolution, "FEATURE_PATH", feature_path)
    monkeypatch.setattr(
        evolution,
        "load_governance_snapshot",
        lambda: GovernanceSnapshot(1, 2, (), ()),
    )
    monkeypatch.setattr(evolution, "_local_data_state", lambda: {
        "portfolio_input": True,
        "portfolio_context": True,
        "amazingdata_env": True,
        "crypto_watchlist": True,
        "crypto_watchlist_example": True,
        "research_sources": True,
        "influencer_observations": True,
        "signal_outcomes": True,
    })

    report = evolution.build_evolution_report(report_dir)

    assert "## 产品实验治理" in report
    assert "活跃实验 0/1" in report
    assert "feat-044 Official IR discovery: pending" in report
    assert "feat-053 Guarded futures basis: pass" in report
    assert "data_source: 1" in report
```

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_evolution.py -q
```

Expected: failures because `_feature_lines` still expects a status dictionary, `_bound_backlog` does not exist, and the report has no governance section.

**Step 2: Replace the hard-coded feature view**

In `stock_assist/workflows/evolution.py`, add these imports/constants and replace `_load_feature_status` plus `_feature_lines`:

```python
from collections import Counter

from stock_assist.product_governance import (
    GovernanceSnapshot,
    governance_markdown_lines,
    load_governance_snapshot,
)


FEATURE_PATH = PROJECT_ROOT / "feature_list.json"


def _load_features(path: Path | None = None) -> list[dict[str, object]]:
    target = path or FEATURE_PATH
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
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
        "状态汇总：" + ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    ]
    unfinished = [item for item in features if str(item.get("status")) != "pass"]
    latest_pass = sorted(
        [item for item in features if str(item.get("status")) == "pass"],
        key=_feature_number,
    )[-8:]
    visible = sorted(unfinished, key=_feature_number) + latest_pass
    for item in visible:
        lines.append(f"{item['id']} {item.get('name', 'Unnamed feature')}: {item.get('status', 'unknown')}")
    return lines
```

**Step 3: Bound recommendations and add the governance section**

Add:

```python
def _bound_backlog(backlog: list[str], snapshot: GovernanceSnapshot) -> list[str]:
    remaining = snapshot.remaining_queue_slots
    if remaining == 0:
        return ["实验队列已满；先完成、终止或移出既有实验，不新增功能。"]
    if not backlog:
        return ["暂无足够证据形成新实验；保留队列容量，不为填满 backlog 而造功能。"]
    return [f"候选（尚未获准）：{item}" for item in backlog[:remaining]]
```

At the start of `build_evolution_report`, use:

```python
    features = _load_features()
    feature_status = _feature_status(features)
    governance = load_governance_snapshot()
```

After `_build_backlog(...)`, use:

```python
    backlog = _bound_backlog(backlog, governance)
```

Delete the old fallback that branches only on `feat-027`, then change the return assembly so the feature and governance sections are:

```python
            "## 当前能力状态",
            bullet(_feature_lines(features)),
            "",
            "## 产品实验治理",
            bullet(governance_markdown_lines(governance)),
```

Leave keyword scanning, local-data diagnostics, and signal-outcome rendering intact.

**Step 4: Run focused tests**

```powershell
.venv\Scripts\python -m pytest tests\test_evolution.py tests\test_product_governance.py -q
```

Expected: `10 passed`.

**Step 5: Commit truthful evolution reporting**

```powershell
git add stock_assist/workflows/evolution.py tests/test_evolution.py
git commit -m "feat: govern evolution recommendations"
```

### Task 3: Define Project-Scoped Read-Only Codex Roles and Validate Them

**Files:**

- Create: `.codex/agents/evidence_analyst.toml`
- Create: `.codex/agents/market_benchmark_analyst.toml`
- Create: `.codex/agents/product_critic.toml`
- Create: `.codex/agents/implementation_verifier.toml`
- Replace: `configs/agents.json`
- Create: `stock_assist/agent_contracts.py`
- Create: `scripts/validate_agent_contracts.py`
- Create: `tests/test_agent_contracts.py`

**Step 1: Write failing contract tests**

Create `tests/test_agent_contracts.py`:

```python
import json
from pathlib import Path

from stock_assist.agent_contracts import validate_agent_contracts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_agent_contracts_match_roster() -> None:
    errors = validate_agent_contracts(
        PROJECT_ROOT / ".codex" / "agents",
        PROJECT_ROOT / "configs" / "agents.json",
    )

    assert errors == []


def test_operating_model_caps_parallelism_and_serializes_writes() -> None:
    payload = json.loads((PROJECT_ROOT / "configs" / "agents.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "insightradar-agent-roster/v2"
    assert payload["operating_model"]["max_parallel_task_agents"] == 3
    assert payload["operating_model"]["write_policy"] == "lead_serializes_workspace_changes"
    assert payload["operating_model"]["max_active_experiments"] == 1
    assert payload["operating_model"]["max_queued_experiments"] == 2


def test_every_custom_agent_is_read_only_and_non_recursive() -> None:
    for path in sorted((PROJECT_ROOT / ".codex" / "agents").glob("*.toml")):
        text = path.read_text(encoding="utf-8")
        assert 'sandbox_mode = "read-only"' in text
        assert "Do not modify the workspace" in text
        assert "Do not spawn subagents" in text
        assert "personal-investment-decision-intelligence-design.md" in text
```

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_agent_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'stock_assist.agent_contracts'`.

**Step 2: Replace the human-readable roster with the v2 operating model**

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
      "mission": "批准北极星、优先级、范围扩大、实验启动和发布；主要承担审核与确认，不负责日常功能发散。",
      "authority": ["approve_product_priority", "approve_experiment_start", "approve_release"],
      "inputs": ["设计规范", "实验卡", "验收证据"],
      "outputs": ["批准", "否决", "范围调整"]
    },
    {
      "id": "lead",
      "name": "主 Agent / CEO-CPO / 架构负责人",
      "runtime_agent": "default",
      "engagement": "always",
      "mission": "围绕观察-解释-决策-验证闭环管理产品，只启动必要角色，串行集成所有写入，并向审核人提交可验证结果。",
      "authority": ["delegate_read_only_analysis", "integrate_workspace_changes", "propose_experiments"],
      "inputs": ["英文主设计", "CURRENT_STATE.md", "feature_list.json", "验证证据"],
      "outputs": ["范围明确的计划", "集成提交", "阶段验收"]
    },
    {
      "id": "evidence_analyst",
      "name": "证据分析师",
      "runtime_agent": "evidence_analyst",
      "engagement": "on_demand",
      "mission": "核对来源、时点、实体映射、缺失字段和事实边界；只提交证据摘要，不给交易结论。",
      "authority": ["read_workspace", "read_approved_sources", "report_evidence_gaps"],
      "inputs": ["目标问题", "相关本地数据", "允许的来源清单"],
      "outputs": ["带来源的事实", "冲突与缺口", "置信度边界"]
    },
    {
      "id": "market_benchmark_analyst",
      "name": "市场与竞品分析师",
      "runtime_agent": "market_benchmark_analyst",
      "engagement": "on_demand",
      "mission": "检查市场产品、用户工作流和可验证最佳实践，区分可借鉴闭环与表面功能。",
      "authority": ["read_workspace", "research_public_sources", "report_benchmark_gaps"],
      "inputs": ["产品问题", "目标用户", "当前闭环"],
      "outputs": ["竞品证据", "可借鉴机制", "不建议复制的功能"]
    },
    {
      "id": "product_critic",
      "name": "产品批评者",
      "runtime_agent": "product_critic",
      "engagement": "before_experiment_admission",
      "mission": "挑战问题定义、结果指标、最小实验、终止条件和功能膨胀风险；无权批准或新增功能。",
      "authority": ["read_workspace", "challenge_experiment", "recommend_rejection"],
      "inputs": ["实验卡", "基线", "用户价值证据"],
      "outputs": ["反例", "范围削减建议", "准入意见"]
    },
    {
      "id": "implementation_verifier",
      "name": "独立测试与运维验收者",
      "runtime_agent": "implementation_verifier",
      "engagement": "before_completion",
      "mission": "独立检查需求覆盖、测试、真实产物、数据缺口、可恢复性和运行证据；不修改实现。",
      "authority": ["read_workspace", "run_read_only_verification", "block_completion_claim"],
      "inputs": ["实现差异", "验收标准", "测试和真实产物"],
      "outputs": ["验收结论", "缺陷清单", "残余风险"]
    }
  ]
}
```

**Step 3: Add four project-scoped Codex custom agents**

Create `.codex/agents/evidence_analyst.toml`:

```toml
name = "evidence_analyst"
description = "Read-only analyst for source provenance, point-in-time facts, entity mapping, and explicit data gaps."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md before analysis.
Work only on the bounded evidence question assigned by the lead.
Do not modify the workspace, create commits, or change product state.
Do not spawn subagents.
Separate verified fact, inference, conflict, stale input, and unknown field.
Prefer first-party sources and preserve source URL, source timestamp, and observed-at timestamp.
Research evidence has no trade authority. Never produce an unconditional buy or sell instruction.
Return a concise evidence table, gaps, risks, and exact file or source references to the lead.
"""
nickname_candidates = ["Ledger", "Beacon", "Trace"]
```

Create `.codex/agents/market_benchmark_analyst.toml`:

```toml
name = "market_benchmark_analyst"
description = "Read-only product and market benchmark analyst focused on proven user workflows instead of feature imitation."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md before analysis.
Work only on the bounded benchmark question assigned by the lead.
Do not modify the workspace, create commits, or change product state.
Do not spawn subagents.
Use current public primary sources when the question is time-sensitive.
Compare user problem, workflow, evidence, and outcome measurement; do not equate feature count with product quality.
Do not propose a feature unless the evidence identifies a concrete decision-loop gap.
Return source-linked findings, transferable mechanisms, anti-patterns, and open questions to the lead.
"""
nickname_candidates = ["Scout", "Signal", "Compass"]
```

Create `.codex/agents/product_critic.toml`:

```toml
name = "product_critic"
description = "Read-only challenger for experiment admission, user value, scope control, and falsifiable kill criteria."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md before analysis.
Review only the experiment or product decision assigned by the lead.
Do not modify the workspace, create commits, approve scope, or change product state.
Do not spawn subagents.
Challenge the problem statement, baseline, outcome metric, smallest experiment, safety boundary, and kill criterion.
Reject feature-count reasoning and identify where the proposal fails to improve observe-explain-decide-verify.
Research evidence has no trade authority.
Return blocking objections first, then scope reductions and a clear admit, revise, or reject recommendation.
"""
nickname_candidates = ["Skeptic", "Prism", "Gate"]
```

Create `.codex/agents/implementation_verifier.toml`:

```toml
name = "implementation_verifier"
description = "Read-only independent verifier for requirements, tests, real artifacts, restartability, and residual risk."
sandbox_mode = "read-only"
developer_instructions = """
Read AGENTS.md and docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md before verification.
Verify only the bounded implementation assigned by the lead.
Do not modify the workspace, create commits, or repair failures.
Do not spawn subagents.
Inspect the diff, focused tests, full tests where proportionate, real report artifacts, explicit gaps, and restart instructions.
Treat passing unit tests without a fresh required artifact as incomplete.
Block completion when evidence is missing, stale, masked by later commands, or outside the approved scope.
Return findings ordered by severity, exact reproduction commands, and a final pass or fail verdict.
"""
nickname_candidates = ["Sentinel", "Proof", "Audit"]
```

**Step 4: Implement a Python 3.10-compatible contract validator**

Create `stock_assist/agent_contracts.py`:

```python
"""Validation for project-scoped Codex agent contracts."""

from __future__ import annotations

import json
from pathlib import Path
import re


SINGLE_LINE_FIELD = re.compile(r'^([a-z_]+)\s*=\s*"([^"]*)"\s*$', re.MULTILINE)
INSTRUCTION_BLOCK = re.compile(r'developer_instructions\s*=\s*"""(.*?)"""', re.DOTALL)


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
        for required in (
            "personal-investment-decision-intelligence-design.md",
            "Do not modify the workspace",
            "Do not spawn subagents",
        ):
            if required not in instructions:
                errors.append(f"{path}: developer_instructions missing {required}")
    missing = sorted(runtime_agents - contracts.keys())
    extra = sorted(contracts.keys() - runtime_agents)
    errors.extend(f"roster runtime agent has no TOML contract: {name}" for name in missing)
    errors.extend(f"TOML contract is not routed by roster: {name}" for name in extra)
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
    print("Agent contracts valid: roster and project-scoped Codex roles are aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The validator intentionally parses only the required top-level subset instead of importing `tomllib`, because InsightRadar supports Python 3.10 and `tomllib` is standard only from Python 3.11.

**Step 5: Run tests and the validator**

```powershell
.venv\Scripts\python -m pytest tests\test_agent_contracts.py -q
.venv\Scripts\python scripts\validate_agent_contracts.py
```

Expected: `3 passed`, followed by `Agent contracts valid: roster and project-scoped Codex roles are aligned.`

**Step 6: Commit role contracts**

```powershell
git add .codex/agents configs/agents.json stock_assist/agent_contracts.py scripts/validate_agent_contracts.py tests/test_agent_contracts.py
git commit -m "feat: define bounded Codex product roles"
```

### Task 4: Render the Operating Model in the `agents` Report

**Files:**

- Create: `tests/test_agent_roster.py`
- Modify: `stock_assist/workflows/agent_roster.py`

**Step 1: Write failing roster-report tests**

Create `tests/test_agent_roster.py`:

```python
import json
from pathlib import Path

from stock_assist.workflows.agent_roster import build_agent_roster_report


def test_roster_report_shows_limits_authority_and_runtime_agent(tmp_path: Path) -> None:
    path = tmp_path / "agents.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "insightradar-agent-roster/v2",
                "operating_model": {
                    "lead_role": "lead",
                    "max_parallel_task_agents": 3,
                    "write_policy": "lead_serializes_workspace_changes",
                    "max_active_experiments": 1,
                    "max_queued_experiments": 2,
                    "product_authority": "human_owner_approves_priority_scope_and_release",
                    "trade_authority": "none",
                },
                "agents": [
                    {
                        "id": "product_critic",
                        "name": "产品批评者",
                        "runtime_agent": "product_critic",
                        "engagement": "before_experiment_admission",
                        "mission": "挑战实验。",
                        "authority": ["challenge_experiment"],
                        "inputs": ["实验卡"],
                        "outputs": ["准入意见"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_agent_roster_report(path)

    assert "最多并行任务 Agent：3" in report
    assert "活跃实验上限：1；排队实验上限：2" in report
    assert "写入策略：lead_serializes_workspace_changes" in report
    assert "交易权限：none" in report
    assert "运行时角色：product_critic" in report
    assert "介入时点：before_experiment_admission" in report
    assert "权限边界：challenge_experiment" in report


def test_roster_report_preserves_missing_config_diagnostic(tmp_path: Path) -> None:
    report = build_agent_roster_report(tmp_path / "missing.json")

    assert "数据缺口" in report
    assert "missing.json" in report
```

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_agent_roster.py -q
```

Expected: the first test fails because the current renderer knows only `command`, `mission`, `inputs`, and `outputs`.

**Step 2: Replace the roster renderer**

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
        lines.extend(
            [
                f"## {agent.get('name', '未命名')} ({agent.get('id', 'missing-id')})",
                f"- 运行时角色：{agent.get('runtime_agent') or '人工角色'}",
                f"- 介入时点：{agent.get('engagement', '未填写')}",
                f"- 任务：{agent.get('mission', '未填写')}",
                f"- 权限边界：{_joined(agent.get('authority'))}",
                f"- 输入：{_joined(agent.get('inputs'))}",
                f"- 输出：{_joined(agent.get('outputs'))}",
                "",
            ]
        )
    return "\n".join(lines)
```

**Step 3: Run the focused tests**

```powershell
.venv\Scripts\python -m pytest tests\test_agent_roster.py tests\test_agent_contracts.py -q
```

Expected: `5 passed`.

**Step 4: Commit roster reporting**

```powershell
git add stock_assist/workflows/agent_roster.py tests/test_agent_roster.py
git commit -m "feat: render agent operating boundaries"
```

### Task 5: Wire the Control Plane into Product and Architecture Contracts

**Files:**

- Modify: `stock_assist/product.py`
- Modify: `configs/architecture.json`
- Modify: `docs/harness.md`
- Regenerate: `docs/architecture.html`

**Step 1: Update the product command/file map**

In the `agents` command entry in `stock_assist/product.py`, replace `inputs` with:

```python
        inputs=("configs/agents.json", ".codex/agents/*.toml"),
```

In the `evolve` command entry, replace `inputs` with:

```python
        inputs=("feature_list.json", "configs/product_governance.json", "reports/*.md", "local config/data state"),
```

Add these `ProductFile` entries immediately after `configs/agents.json`:

```python
    ProductFile("configs/product_governance.json", "product_config", "ops", "Bounded active and queued product experiments with falsifiable gates."),
    ProductFile(".codex/agents/*.toml", "agent_contract", "ops", "Project-scoped read-only Codex task-role contracts."),
```

**Step 2: Update architecture inputs and descriptions**

In `configs/architecture.json`, make the `agent_roster` node contain:

```json
"inputs": ["configs/agents.json", ".codex/agents/*.toml"],
"summary": "Renders human authority, lead-only write policy, on-demand read-only Codex task roles, and concurrency boundaries."
```

Make the `evolution` node contain:

```json
"inputs": ["feature_list.json", "configs/product_governance.json", "reports/*.md", "local config/data state"],
"summary": "Scans evidence gaps, reports the full feature catalog, and recommends only enough unapproved experiments to fit remaining queue capacity."
```

Do not change node IDs or edges.

**Step 3: Add the harness operating rule**

Under the product-success and feature-iteration rules in `docs/harness.md`, add:

```markdown
### Agent-governed iteration

- The human owner approves product priority, experiment start, scope expansion, and release.
- The root Codex agent is the lead and sole workspace writer; it may run at most three narrow task agents concurrently.
- Task agents are read-only evidence, market-benchmark, product-critique, or implementation-verification roles. They cannot approve features, modify product state, spawn descendants, or grant research evidence trade authority.
- Product experiments are declared in `configs/product_governance.json`: at most one active and two queued. Every admitted experiment needs a problem, loop stage, baseline, outcome metric, smallest experiment, safety boundaries, kill criterion, and review date.
- `evolve` may propose only unapproved candidates that fit remaining queue capacity. It never starts, completes, or reprioritizes an experiment automatically.
```

**Step 4: Regenerate architecture and run structural checks**

```powershell
.venv\Scripts\python -m stock_assist.cli architecture-view
.venv\Scripts\python -c "import json; [json.load(open(p, encoding='utf-8')) for p in ['configs/agents.json','configs/product_governance.json','configs/architecture.json','feature_list.json']]"
.venv\Scripts\python scripts\validate_agent_contracts.py
.venv\Scripts\python scripts\validate_project_memory.py
```

Expected:

- `architecture-view` prints the path to `docs/architecture.html`.
- JSON validation exits `0`.
- Agent contract validation prints its success line.
- Project-memory validation exits `0`.

**Step 5: Commit product-map and architecture integration**

```powershell
git add stock_assist/product.py configs/architecture.json docs/architecture.html docs/harness.md
git commit -m "docs: wire agent governance into product architecture"
```

### Task 6: Generate Real Reports, Verify the Whole Increment, and Close Feature State

**Files:**

- Generate: `reports/*-agents.md`
- Generate: `reports/*-evolution.md`
- Modify: `feature_list.json`
- Modify: `progress.md`
- Modify: `session-handoff.md`
- Modify: `CURRENT_STATE.md`

**Step 1: Run focused and full automated verification**

Run each command separately and retain every exit status:

```powershell
.venv\Scripts\python -m pytest tests\test_product_governance.py tests\test_evolution.py tests\test_agent_contracts.py tests\test_agent_roster.py -q
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m compileall stock_assist scripts
.venv\Scripts\python scripts\validate_agent_contracts.py
.venv\Scripts\python scripts\validate_project_memory.py
node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar
```

Expected:

- Focused suite: `15 passed`.
- Full suite: all tests pass; record the actual count rather than assuming the prior 85-test baseline.
- Compileall: exit code `0`.
- Both validators: exit code `0`.
- Harness validation: success with no blocking findings.

If any command fails, stop the completion sequence, apply `superpowers:systematic-debugging`, repair the narrow cause, and rerun the failed command plus every later command.

**Step 2: Generate and inspect the real reports**

```powershell
.venv\Scripts\python -m stock_assist.cli agents
.venv\Scripts\python -m stock_assist.cli evolve
$agentReport = Get-ChildItem reports\*-agents.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$evolutionReport = Get-ChildItem reports\*-evolution.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -Path $agentReport.FullName -Pattern "最多并行任务 Agent：3", "lead_serializes_workspace_changes", "product_critic", "交易权限：none"
Select-String -Path $evolutionReport.FullName -Pattern "产品实验治理", "活跃实验 0/1", "排队实验 1/2", "feat-044", "feat-053"
```

Expected:

- `agents` generates a fresh Markdown report containing all four operating-model assertions.
- `evolve` generates a fresh Markdown report containing both feature IDs, zero active experiments, one queued experiment, and the explicit owner-start gate.
- No report says a queued experiment has started automatically.

**Step 3: Independently review the implementation before claiming completion**

Use the `implementation_verifier` role through `superpowers:subagent-driven-development` with this bounded prompt. If the current orchestration tool cannot select a custom agent type explicitly, spawn one child named `implementation_verifier` with the exact same prompt; the prompt preserves the read-only and non-repair boundary:

```text
Verify feat-054 read-only. Check the approved English design, this implementation plan, the full git diff, focused/full test evidence, the latest agents/evolution reports, experiment limits, lead-only write policy, custom-agent contracts, and absence of automatic feature or trade authority. Do not modify files. Return findings by severity and a pass/fail verdict with exact evidence paths.
```

The lead must address every blocking finding and rerun the affected verification. Do not ask the verifier to repair its own findings.

**Step 4: Record durable closeout evidence**

Update the `feat-054` entry in `feature_list.json`:

- Set `status` to `pass` only after Steps 1–3 pass.
- Replace `evidence` with a compact factual paragraph containing:
  - one-active/two-queued governance validation;
  - the four project-scoped read-only custom agents;
  - full-catalog `evolve` visibility including `feat-053`;
  - the actual focused and full test counts;
  - the two fresh report filenames printed in Step 2;
  - validator and independent-verifier results.

Append a dated `feat-054` entry to `progress.md` with scope, files changed, verification commands/results, residual limitation that custom-agent discovery is applied on a fresh Codex task, and recommended next step `feat-044`.

Append a concise handoff section to `session-handoff.md` stating:

- `feat-054` is complete;
- the operating model is one lead plus at most three task agents;
- child roles are read-only and writes are serialized by the lead;
- `configs/product_governance.json` has no active experiment and queues `feat-044`;
- the next session must explicitly start `feat-044` before implementation;
- the event-intelligence, candidate-pool, and Alpha-delivery plans remain separate.

Update `CURRENT_STATE.md` so the verified baseline includes the control plane and `next_feature_id` remains `feat-044`. Do not mark `feat-044` in progress during this plan.

**Step 5: Re-run closeout validators and inspect the final diff**

```powershell
.venv\Scripts\python -c "import json; p=json.load(open('feature_list.json', encoding='utf-8')); f=next(x for x in p['features'] if x['id']=='feat-054'); assert f['status']=='pass'; assert next(x for x in p['features'] if x['id']=='feat-044')['status']=='pending'"
.venv\Scripts\python scripts\validate_project_memory.py
node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar
git diff --check
git status --short
git diff --stat
```

Expected: all checks pass; the diff contains only feat-054 closeout records and intended generated reports, with no `.env`, credentials, or `.learnings` files.

**Step 6: Commit the verified closeout**

```powershell
git add feature_list.json progress.md session-handoff.md CURRENT_STATE.md reports/*-agents.md reports/*-evolution.md
git commit -m "feat: complete agent-governed product iteration"
git status --short
```

Expected: commit succeeds and the final status is clean.

## Acceptance Checklist

- `feat-054` is `pass`; `feat-044` remains `pending` and is the sole queued experiment.
- Governance rejects more than one active or two queued experiments, missing gate fields, unknown features, duplicates, and completed features.
- `evolve` reads every real feature entry, shows `feat-053`, and limits recommendations to remaining queue capacity.
- The project has exactly four narrow custom task-agent contracts; all are read-only, non-recursive, and aligned with `configs/agents.json`.
- The root lead remains the only workspace writer and no more than three task agents run concurrently.
- The roster report makes human approval, agent engagement timing, permissions, trade-authority absence, and experiment limits visible.
- Fresh `agents` and `evolve` Markdown artifacts pass static content assertions.
- Product map, architecture HTML, harness contract, project memory, feature evidence, progress, and handoff agree.
- Focused tests, the full suite, compileall, JSON parsing, agent-contract validation, project-memory validation, harness validation, independent read-only verification, and `git diff --check` all pass.
- No event ingestion, candidate ranking, Alpha delivery, or trade execution leaked into this increment.
