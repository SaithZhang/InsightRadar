# InsightRadar Architecture

Status: **V3.1 active local runtime architecture**

## Technology Stack

- Python `>=3.10`
- Setuptools project metadata in `pyproject.toml`
- Local CLI via `argparse`
- Data processing with pandas and provider SDKs
- Standard-library `ThreadingHTTPServer` for the loopback application
- Self-contained server-rendered HTML/CSS/JavaScript
- File-based JSON, JSONL, TSV, CSV, Markdown, and HTML persistence
- `unittest` test suite; pytest compatibility is declared but pytest is not the canonical runner

There is no `package.json`, Node lock file, React/Vue/Next application, standalone `src/app/pages/components` frontend tree, database server, ORM, or migration system.

## Entry Points

| Entry | Purpose |
|---|---|
| `InsightRadar.cmd` | Starts/reuses the local loopback workspace |
| `生成盘后报告.cmd` | Runs `after-close` and opens the fresh HTML |
| `导入持仓.cmd` | Opens the loopback import/workspace service |
| `打开最新报告.cmd` | Opens the latest HTML without refreshing |
| `python -m stock_assist.cli <command>` | Canonical workflow interface |
| `insight-radar` | Installed console-script alias |

## Runtime Layers

```text
Provider adapters and local files
  stock_assist/data_sources/*
  stock_assist/portfolio.py
           |
           v
Workflow builders
  stock_assist/workflows/*
           |
           v
Decision composition
  unified_decision.py
  decision_workspace.py
           |
           v
Canonical payload and renderers
  reports/*-after-close.json
  reports/*-after-close.md
  reports/*-after-close.html
           |
           v
Loopback service
  portfolio_import_server.py
  http://127.0.0.1:8765/
```

## User Routes

The V3.1 HTML renderer retains four stable hash routes:

- `#today` — after-close/weekend conclusion workbench plus point-in-time radar state.
- `#portfolio` — exposure, completeness, reconciliation, holdings and risk blockers.
- `#lookup` — research intent and current evidence boundary.
- `#review` — plan versions, user responses, and matured signal outcomes.

Desktop sidebar and mobile bottom navigation use the same route set. Market detail is a drawer, not a fifth route.

## Product Modules and Rings

`stock_assist/product.py` registers 26 CLI commands under four engineering modules:

- Portfolio Intelligence
- Research Intelligence
- Market Radar
- Product Ops

`configs/architecture.json` currently has 22 nodes and 28 edges across data, research, market, decision, and operations lanes. Lifecycle rings are Core, Lab, Extension, and Governance. No Satellite remains in this repository.

The module registry and lifecycle rings are internal architecture classifications. They do not replace the four stable user tasks.

## Decision and Persistence Flow

1. `load_portfolio()` resolves the approved local snapshot and context; missing account fields remain `None`.
2. `build_after_close_report()` combines holding signals, provider evidence, explicit gaps, and outcome refresh.
3. `build_unified_decision()` loads the latest risk, market, levels, style, and AI-capex payloads from `reports/`.
4. `build_decision_workspace()` turns the canonical payload into route data, source health, market permission, versioned plans, and response state.
5. `record_plan_versions()` appends only new content-addressed versions to a local JSONL ledger.
6. The loopback service overlays user responses and may perform a freshness-only morning restage.
7. `signal_outcomes` matures T+1/T+5/T+20 evidence without scoring incomplete horizons early.

## Service and Security Boundary

The local service:

- binds only to `127.0.0.1`;
- uses a random per-process token for every POST;
- sends `Cache-Control: no-store`;
- applies a restrictive same-origin Content Security Policy;
- requires explicit approval before saving portfolio data;
- uses atomic writes/backups in the import path;
- never accepts or emits a trade order.

The GET workspace can be viewed locally. State-changing APIs are inaccessible without the current in-page token.

## Data Stores

There is no production database. Runtime persistence is local file storage:

- private portfolio/context/risk files under `data/`;
- plan versions, responses, and runtime state under `data/`;
- generated workflow payloads and renderers under `reports/`;
- repository-external NGA and AI keys under `%LOCALAPPDATA%\InsightRadar\secrets`;
- provider credentials in ignored `.env` or process environment.

Schemas, examples, source code, and reproducible configs are version controlled. Runtime state is not.

## Build and Verification

```powershell
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m compileall stock_assist
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python scripts\validate_project_memory.py
.\.venv\Scripts\python -m stock_assist.cli after-close
.\.venv\Scripts\python -m build
```

No repository lint or static type-check configuration existed at the V3.0 freeze point. Historical baseline audit results record that absence separately from actual lint/type-check findings; V3.1 increments report the checks they actually run.

## Generated and Reference Assets

- `docs/architecture.html` is generated from `configs/architecture.json`.
- `reports/` contains runtime output and is ignored.
- `.superpowers/brainstorm/0830-decision-loop-v1/` is a fixed-data prototype and design audit.
- `review-package/` is a synthetic, public-review artifact set.
- `tmp/` and `review-delivery/archive/` are local build/staging outputs.
