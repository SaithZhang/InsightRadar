# InsightRadar Project Memory

This bounded index is the always-on entry point for durable project context. Read it at every non-trivial startup, then load only the topic that matches the task. Keep this file under 200 lines and 25 KB; detailed history belongs in topic files, not here.

<!-- project-memory-manifest
{
  "schema_version": "insight-radar-project-memory/v1",
  "max_lines": 200,
  "max_bytes": 25600,
  "current_state": {
    "path": "CURRENT_STATE.md",
    "max_lines": 120,
    "max_bytes": 16384
  },
  "topics": [
    {
      "id": "architecture",
      "path": "docs/memory/architecture.md",
      "triggers": ["architecture", "topology", "module", "workflow", "data flow", "new command"],
      "sources": ["stock_assist/product.py", "configs/architecture.json", "stock_assist/workflows/architecture_view.py"],
      "generated": [
        {"source": "configs/architecture.json", "output": "docs/architecture.html", "digest_meta": "architecture-source-sha256"}
      ]
    },
    {
      "id": "product-state",
      "path": "docs/memory/product-state.md",
      "triggers": ["roadmap", "feature", "resume", "handoff", "current state", "next sprint"],
      "sources": ["CURRENT_STATE.md", "feature_list.json", "progress.md", "session-handoff.md", "docs/harness.md"],
      "generated": []
    },
    {
      "id": "product-direction",
      "path": "docs/product-charter.md",
      "triggers": ["product strategy", "north star", "scope", "split", "modular", "core", "lab", "satellite", "extension"],
      "sources": ["CURRENT_STATE.md", "docs/PRODUCT_BASELINE.md", "docs/V3.0_FROZEN.md", "docs/V3.1_DELTA.md", "stock_assist/product.py", "configs/architecture.json", "docs/product-benchmark.md", "docs/extractions/README.md", "docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md"],
      "generated": []
    },
    {
      "id": "decision-log",
      "path": "docs/memory/decision-log.md",
      "triggers": ["why", "decision", "tradeoff", "replace", "deprecate", "design rationale"],
      "sources": ["AGENTS.md", "docs/DECISION_LOG.md", "docs/DATA_BOUNDARIES.md", "docs/harness.md", "docs/memory/decisions/0001-bounded-repository-memory.md", "docs/memory/decisions/0002-modular-monolith-product-rings.md", "docs/memory/decisions/0003-extract-discipline-reminder-and-freeze-expansion.md", "docs/memory/decisions/0004-canonical-insightradar-workspace.md", "docs/memory/decisions/0005-iwencai-cross-platform-market-data-candidate.md", "docs/memory/decisions/0006-local-first-core-value-validation.md", "docs/memory/decisions/0007-evidence-bound-discipline-contracts.md", "docs/memory/decisions/0008-guarded-iwencai-futures-basis.md", "docs/memory/decisions/0009-personal-investment-decision-intelligence.md", "docs/memory/decisions/0010-v3-pilot-scope-frozen.md", "docs/memory/decisions/0011-public-v3-baseline.md"],
      "generated": []
    }
  ]
}
-->

## Topic Index

| Topic | Load when | Durable source |
|---|---|---|
| [Architecture](docs/memory/architecture.md) | Adding/changing modules, commands, data sources, workflows, reports, or diagrams | `stock_assist/product.py`, `configs/architecture.json`, `docs/architecture.html` |
| [Product state](docs/memory/product-state.md) | Resuming work, choosing the next feature, or checking current capability status | `feature_list.json`, `progress.md`, `session-handoff.md` |
| [Product direction](docs/product-charter.md) | Changing product scope, goals, module rings, extraction boundaries, or roadmap order | `CURRENT_STATE.md`, `stock_assist/product.py`, `configs/architecture.json` |
| [Decision log](docs/memory/decision-log.md) | A prior design choice or constraint affects a new change | Append-only durable decisions and links to evidence |

## Write Protocol

1. Write or update the detailed topic file first.
2. Add or update one short pointer in this index only when routing changes.
3. Prefer links to sources of truth over copied facts that can drift.
4. Record durable decisions and invariants, not chat transcripts or easily re-derived code details.
5. Refresh `CURRENT_STATE.md` when the verified baseline, next feature, blockers, or product direction changes.
6. Run `.venv\Scripts\python scripts\validate_project_memory.py` before claiming a memory-sensitive change is complete.
