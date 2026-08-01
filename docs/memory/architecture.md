# Architecture Memory

## Why This Topic Exists

InsightRadar has a generated interactive topology at `docs/architecture.html`. It survived earlier sessions, but later work stopped routing agents to it and the graph drifted behind the product registry. This topic makes the asset discoverable, gives it an explicit refresh contract, and keeps every node classified by product ring.

## Sources of Truth

- `stock_assist/product.py`: product modules, CLI commands, input/output contracts, and file classifications.
- `configs/architecture.json`: visual lanes, Core/Lab/Satellite/Extension/Governance rings, non-command infrastructure nodes, command coverage, and graph edges.
- `stock_assist/workflows/architecture_view.py`: deterministic HTML renderer.
- `docs/architecture.html`: generated view; never edit it by hand.

## Refresh Contract

Refresh the topology whenever a change adds, removes, renames, or materially rewires any of these:

- a `ProductCommand` in `stock_assist/product.py`;
- a data source or private runtime store;
- a report/payload workflow;
- a resident Windows component;
- a feedback or model-promotion loop.
- a product-ring assignment or extraction boundary.

Required commands:

```powershell
.venv\Scripts\python scripts\validate_project_memory.py
.venv\Scripts\python -m stock_assist.cli architecture-view
.venv\Scripts\python scripts\validate_project_memory.py
```

The first validation may intentionally report stale or missing command coverage. The final validation must pass. Freshness is content-based: the generated HTML embeds the SHA-256 of `configs/architecture.json`, so validation remains deterministic after Git checkout on another machine.

## Current Shape

`intraday_radar` is now the Core decision seam. The loopback page starts before provider work; one pre-registered single-flight scheduler owns the initial refresh and remaining 09:25/09:35/10:00 checks. `AmazingData` and the per-symbol public fallback feed immutable JSONL minute/quote archives through declared domestic-direct routes; foreign Yahoo uses the system proxy and loopback/Futu stays local-only. Real calendar/archive/probed dates determine the current versus latest-completed session, and a terminable child bounds a refresh below 60 seconds. `portfolio_memory` supplies approved holdings; `IntradaySnapshotBuilder` owns point-time derived state; four deterministic rule modules consume only the typed contract. Every state preserves provider `source_time` and local `fetched_at`, and no rule module calls a provider directly.

The topology has two complementary classifications. Lanes describe data flow: data, research, market, decision, and operations/feedback. Rings describe product lifecycle: Core, Lab, Satellite, Extension, and Governance. `after-close` is the main portfolio decision surface. Its persisted bear-bull state machine separates candidate observations from close-finalized formal scores, consumes typed market-level states, and records auditable rule/veto evidence. The after-close JSON remains the canonical client contract. `stock_assist/holding_decision.py` owns the pure holding-level technical contract: account cost is `reference_only`, while moving averages, price structure, available ATR/volume evidence, persistence, reachability, and the repair/risk/wait branches determine the plan. `stock_assist/decision_evidence.py` joins evidence to source health and holding plans by stable ids; data-health status is rendered separately from decision facts. The HTML renderer in `stock_assist/after_close_workbench.py` and `stock_assist/after_close_workbench_html.py` consumes the typed workspace and preserves the four frozen first-level tasks. Provider access remains upstream in Core monitor workflows; the workbench renderer performs no provider queries.

`portfolio-import` is a loopback-only, approval-gated Core intake path with atomic backup/rollback and explicit risk reconciliation; it cannot trade or infer beta class. The active frontend lives in `stock_assist/portfolio_import_web.py`, while `stock_assist/portfolio_import_server.py` owns HTTP routing. An approved import commits the portfolio first and then enqueues a single-flight serial refresh through `stock_assist/refresh_jobs.py`; HTTP returns a durable run id instead of waiting for Core. Local SQLite stores refresh runs/steps, last-good source metadata, evidence and plan mirrors, and explicit user responses. A zero process return code is insufficient: each step must produce a new parseable artifact, and `after-close` must produce one same-stem JSON/Markdown/HTML triplet bound to the refresh-start `portfolio_version`. JSON/Markdown/HTML and JSONL remain the reproducible audit artifacts, and a refresh failure never rolls back the saved portfolio or hides the last-good report.

`style-rotation` is a Core diagnostic monitor using fixed technology, financial, high-dividend, and benchmark proxies across multiple horizons; conflicts and missing evidence remain visible and cannot override the risk budget. `risk-watch` is the Core after-close risk-budget input: it combines five capped signal families, keeps missing sources explicit, and never executes trades. The `iwencai_market` node is now a guarded local Core source shared by `risk-watch` and `market-pulse`: it provides failure-tolerant A-share breadth plus date-aligned completed-close IF/IH/IC/IM basis/positioning, while stale live-session closes are rejected in favor of serial AmazingData realtime fallback. Completed-close basis remains diagnostic-only and the provider is not yet declared cross-platform/cloud-ready. S&P 500, QQQ, SOX, Nikkei, and Korea event gates use market-specific absolute floors plus normalized shock evidence, while unvalidated community narratives remain diagnostic-only. `ai-capex-watch` is a separate Core research workflow: it scores official hyperscaler CapEx momentum, requires optical-network and supplier-financial transmission checks, shrinks sparse evidence toward neutral, and cannot override the portfolio risk budget. Factor rankings remain Lab-only unless a candidate passes hard gates and becomes a champion; crypto and public-viewpoint collection remain optional Extensions. Satellite remains an allowed lifecycle class, but no Satellite node currently lives in this repository because the Windows reminder completed external ownership transfer to `D:\work\reminder`.

## Retrieval Rule

Load this topic before architecture or cross-module work. Do not load the full HTML into model context unless visual or embedded graph inspection is necessary; inspect `configs/architecture.json` or use the generated page instead.
