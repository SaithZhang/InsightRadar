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

The topology has two complementary classifications. Lanes describe data flow: data, research, market, decision, and operations/feedback. Rings describe product lifecycle: Core, Lab, Satellite, Extension, and Governance. `after-close` is the main portfolio decision surface. Its persisted bear-bull state machine separates candidate observations from close-finalized formal scores, consumes typed market-level states, and records auditable rule/veto evidence. The after-close JSON remains the canonical client contract. The HTML renderer in `stock_assist/after_close_workbench.py` and `stock_assist/after_close_workbench_html.py` consumes a typed workbench view derived from that payload and renders five hash-routed interfaces in one file. Provider access remains upstream in Core monitor workflows; the workbench renderer performs no provider queries. `portfolio-import` is a loopback-only, approval-gated Core intake path with atomic backup/rollback and explicit risk reconciliation; it cannot trade or infer beta class. `style-rotation` is a Core diagnostic monitor using fixed technology, financial, high-dividend, and benchmark proxies across multiple horizons; conflicts and missing evidence remain visible and cannot override the risk budget. `risk-watch` is the Core after-close risk-budget input: it combines five capped signal families, keeps missing sources explicit, and never executes trades. The `iwencai_market` node is now a guarded local Core source shared by `risk-watch` and `market-pulse`: it provides failure-tolerant A-share breadth plus date-aligned completed-close IF/IH/IC/IM basis/positioning, while stale live-session closes are rejected in favor of serial AmazingData realtime fallback. Completed-close basis remains diagnostic-only and the provider is not yet declared cross-platform/cloud-ready. S&P 500, QQQ, SOX, Nikkei, and Korea event gates use market-specific absolute floors plus normalized shock evidence, while unvalidated community narratives remain diagnostic-only. `ai-capex-watch` is a separate Core research workflow: it scores official hyperscaler CapEx momentum, requires optical-network and supplier-financial transmission checks, shrinks sparse evidence toward neutral, and cannot override the portfolio risk budget. Factor rankings remain Lab-only unless a candidate passes hard gates and becomes a champion; crypto and public-viewpoint collection remain optional Extensions. Satellite remains an allowed lifecycle class, but no Satellite node currently lives in this repository because the Windows reminder completed external ownership transfer to `D:\work\reminder`.

## Retrieval Rule

Load this topic before architecture or cross-module work. Do not load the full HTML into model context unless visual or embedded graph inspection is necessary; inspect `configs/architecture.json` or use the generated page instead.
