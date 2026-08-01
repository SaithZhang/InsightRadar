# Session Handoff

## Latest Update - 2026-07-09 19:02 Asia/Shanghai

- Added and verified `feat-026 - Actionable after-close playbook`.
- Holding guidance now avoids vague internal language like `趋势未给出强动作信号`.
- Each current holding action can include:
  - `仓位动作`;
  - `上行条件`;
  - `下行条件`;
  - `震荡处理`;
  - `明日优先级`.
- Latest report:
  - `reports/20260709-190126-after-close.json`
  - `reports/20260709-190126-after-close.md`
  - `reports/20260709-190126-after-close.html`
- Latest examples:
  - ????C: `高仓位持有，优先降集中度`;
  - 沪硅产业: `持有观察`;
  - ????D: `持有，保护浮盈`.
- Product judgment for future AI use:
  - deterministic rules should generate facts, levels, and triggers first;
  - AI/API can later polish wording or summarize, but should not invent price levels, risk lines, or unsupported trade actions.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- payload assertion for required action fields
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-190220-evolution.md`, with `feat-026` pass.

Recommended continuation:

- Upgrade HTML cards so the new playbook fields appear as a compact decision strip rather than ordinary bullet text.

## Latest Update - 2026-07-09 18:40 Asia/Shanghai

- Added and verified `feat-025 - Manual broker portfolio input`.
- New private manual holdings file:
  - `data/portfolio.manual.tsv`
  - ignored by git;
  - currently contains the user-provided broker table.
- New tracked template:
  - `data/portfolio.manual.example.tsv`
- Portfolio loader priority:
  - `data/portfolio.json`;
  - `data/portfolio.manual.tsv`;
  - `data/portfolio.galaxy.tsv`.
- Parser behavior:
  - supports the copied Chinese broker table header;
  - treats `当前持仓` as the true current position;
  - uses `股票余额` only as a fallback when `当前持仓` is missing;
  - ignores rows with `当前持仓=0`, so same-day sold rows or frozen historical balances do not become current holdings.
- Latest parsed current holdings from `data/portfolio.manual.tsv`:
  - `HOLDING-C.EX` ????C, 300 shares;
  - `688126.SH` 沪硅产业, 3404 shares;
  - `HOLDING-D.EX` ????D, 1000 shares.
- Latest report:
  - `reports/20260709-183940-after-close.json`
  - `reports/20260709-183940-after-close.md`
  - `reports/20260709-183940-after-close.html`

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- Parser smoke test via `load_portfolio()`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-184001-evolution.md`, with `feat-025` pass.

Recommended continuation:

- Add `insight-radar portfolio-check` to validate pasted broker tables before full report generation. It should show included rows, ignored rows, inferred exchange suffixes, computed weights, and missing thesis/context.

## Latest Update - 2026-07-09 18:31 Asia/Shanghai

- Added and verified `feat-024 - After-close payload bridge`.
- New shared module:
  - `stock_assist/report_payload.py`
  - owns the common `insight-payload/v1` envelope, title extraction, Markdown section parsing, and section item extraction.
- `market-pulse` now uses the shared envelope helper while keeping its existing JSON fields stable.
- `after-close` now writes:
  - `reports/20260709-182917-after-close.json`
  - `reports/20260709-182917-after-close.md`
  - `reports/20260709-182917-after-close.html`
- Latest after-close payload includes:
  - `schema_version=insight-payload/v1`;
  - `kind=after_close`;
  - 3 summary cards;
  - 4 components;
  - 14 Markdown-derived sections;
  - 5 parsed holding actions;
  - 1 explicit data gap.
- `market-pulse` was rerun after the shared helper refactor:
  - `reports/20260709-183101-market-pulse.json`
  - `reports/20260709-183101-market-pulse.md`
  - `reports/20260709-183101-market-pulse.html`
  - source labels still do not appear in the user-facing Markdown/HTML.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli market-pulse`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-183121-evolution.md`, with `feat-024` pass.

Current state:

- Portfolio Intelligence and Market Radar both have JSON-first report outputs.
- Markdown and HTML remain preserved renderers.
- The after-close payload is a bridge based on parsed report sections; it is not yet a fully typed domain model.

Recommended continuation:

- Next best sprint: convert after-close internals to produce typed domain payload arrays directly (`holdings`, `risk_lines`, `thesis_checks`, `peer_evidence`, `filings`, `events`, `research_deltas`, `external_views`) and then render Markdown/HTML from that model.
- Product next: add `insight-radar serve` for local payload browsing/API so future Windows/iOS/Android shells can consume the same contracts.

## Latest Update - 2026-07-09 15:52 Asia/Shanghai

- Added and verified `feat-023 - Insight payload contract`.
- `market-pulse` is now JSON-first:
  - `reports/*-market-pulse.json` is the product payload contract;
  - Markdown and HTML are rendered from that same payload;
  - source details remain out of the user-facing report and are traceable through `data/market_pulse_sources.jsonl`.
- Latest product reports:
  - `reports/20260709-154915-market-pulse.json`
  - `reports/20260709-154915-market-pulse.md`
  - `reports/20260709-154915-market-pulse.html`
- Payload contract currently includes:
  - `schema_version=insight-payload/v1`;
  - workflow/product metadata;
  - summary cards;
  - component list for client renderers;
  - index and ETF snapshot grids;
  - futures-basis table data;
  - conditional action table;
  - explicit data gaps;
  - backend audit pointer.
- Temporary local static server at `http://127.0.0.1:8765` was stopped.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> JSON, Markdown, and HTML with the same timestamp.
- Payload inspection: 6 components, 4 summary cards, 7 indexes, 5 ETFs, 8 basis rows, 3 action rows, backend-log-only audit visibility, explicit data gaps.
- Local HTML structure check: 16 cards, 2 tables, 8 basis rows, 3 action rows, 0 visible source terms.
- `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260709-155319-evolution.md` with `feat-023` pass.
- In-app browser QA was attempted but not claimed: after `node_repl` reset, the browser automation context no longer exposed `agent`.

Recommended continuation:

- Extract shared `report_payload` domain objects and move `after-close` to the same JSON-first output model. That is the clean path toward iOS/Android/Windows clients while keeping the current HTML dashboard useful.

## Latest Update - 2026-07-09 13:06 Asia/Shanghai

- Added and verified `feat-022 - Realtime futures-basis pulse`.
- `market-pulse` now computes live IF/IH/IC/IM futures basis using Galaxy AmazingData snapshots:
  - gets CFFEX contract list through `get_future_code_list("ZJ_FUTURE")`;
  - selects the nearest two contracts for IF/IH/IC/IM;
  - queries each futures/spot code serially through `query_snapshot`;
  - aligns futures and spot by common timestamp;
  - computes current basis, basis rate, and 4-minute basis change.
- Latest product reports:
  - `reports/20260709-130317-market-pulse.md`
  - `reports/20260709-130317-market-pulse.html`
- The report now has:
  - Basis conclusion card;
  - 8-row futures-basis table;
  - 3-row conditional action table;
  - Markdown basis summary and action lines.
- Source details remain hidden from the UI and are written to `data/market_pulse_sources.jsonl`; the latest run appended 8 `futures_basis` audit records.
- Config updated:
  - `basis_lookback_minutes`
  - `futures_basis_watch`
- Browser QA used a temporary local static server at `http://127.0.0.1:8765`, then the server was stopped.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-130317-market-pulse.md` and `.html`
- Audit-log check: 8 `futures_basis` records, all without error.
- Browser QA: 16 cards, 6 panels, 2 tables, 8 basis rows, 3 action rows, no console errors, no horizontal overflow at desktop or 390px mobile width.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-130607-evolution.md`, with `feat-022` pass.

Recommended continuation:

- Add market breadth and industry rotation next:上涨/下跌家数、涨停/跌停、炸板率、行业涨跌幅。This will let InsightRadar distinguish “index pull” from broad participation and make the futures-basis signal less lonely.

## Latest Update - 2026-07-09 12:56 Asia/Shanghai

- Added and verified `feat-021 - Market pulse source audit log`.
- The `market-pulse` user-facing reports no longer show raw source labels such as `source: Galaxy AmazingData query_snapshot`.
- Source traceability moved to backend audit log:
  - `data/market_pulse_sources.jsonl`
  - latest run appended 12 snapshot records with code, category, price, update time, source, and error state.
- Latest clean product reports:
  - `reports/20260709-125534-market-pulse.md`
  - `reports/20260709-125534-market-pulse.html`
- Harness updated: A-share market-pulse reports should stay conclusion-first and source-light; source/fallback details belong in the audit log.
- In-app browser `file://` navigation was blocked by browser security policy during QA, so browser visual verification was not claimed. Local HTML/text checks passed.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-125534-market-pulse.md` and `.html`
- `Select-String` source-term check returned no visible source labels in the generated reports.
- Local audit-log check confirmed `data/market_pulse_sources.jsonl` has 12 latest snapshot records from Galaxy AmazingData.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-125622-evolution.md`, with `feat-021` pass.

Recommended continuation:

- Build the futures-basis adapter next: current-month IF/IH/IC/IM selection, one-contract snapshot probes, spot-index join, absolute/percent/annualized basis, and a clean data-gap fallback if any leg fails.

## Latest Update - 2026-07-09 12:50 Asia/Shanghai

- Added and verified `feat-020 - A-share live market pulse`.
- New command: `.venv\Scripts\python -m stock_assist.cli market-pulse`.
- New reports:
  - `reports/20260709-125013-market-pulse.md`
  - `reports/20260709-125013-market-pulse.html`
- The market pulse report is a PPT-style card dashboard for A-share intraday direction:
  - direction verdict and score,
  - strongest/weakest style,
  - 7 index cards,
  - 5 ETF support proxy cards,
  - futures-basis section,
  - Central Huijin/state-team ETF proxy notes,
  - explicit data gaps.
- Source priority is now Galaxy first:
  - `stock_assist/data_sources/xysz.py` gained `query_snapshot`, `get_future_code_list`, `get_fund_share`, and `get_etf_pcf`.
  - `stock_assist/data_sources/a_share_market.py` tries Galaxy AmazingData `query_snapshot` first.
  - Eastmoney public intraday trends are only fallback.
- Added product config:
  - `configs/a_share_pulse.json`
  - `configs/a_share_pulse.example.json`
- CFFEX future code list works through AmazingData, but a combined futures/index snapshot probe timed out. Do not fabricate IF/IH/IC/IM basis; next work should harden futures one contract at a time.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m stock_assist.cli --help`
- `.venv\Scripts\python -m stock_assist.cli market-pulse`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-125028-evolution.md`
- Browser QA via Codex `node_repl`: 16 cards, 12 Galaxy source rows, 5 panels, no console errors, no horizontal overflow at desktop and 390px mobile width.

Recommended continuation:

- Build the futures-basis adapter: current-month IF/IH/IC/IM selection, one-contract snapshot probes, spot-index join, absolute/percent/annualized basis, and data-gap fallback if any leg fails.

## Latest Update - 2026-07-09 12:38 Asia/Shanghai

- Added and verified `feat-019 - Source-priority signal queue`.
- The after-close HTML now has a Top Signals row immediately after the executive brief and before the per-position cards.
- Top Signals ranks only the 3 highest-priority items from:
  - portfolio risk actions,
  - data gaps,
  - research deltas,
  - event risks,
  - external viewpoints.
- Full Markdown evidence remains unchanged; HTML evidence sections remain collapsed by default.
- Latest report: `reports/20260709-123453-after-close.html`.
- Recorded a local QA tooling gotcha in `.learnings/ERRORS.md`: repo-local Node cannot resolve Playwright; use Codex bundled browser runtime or `node_repl` for dashboard QA.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-123453-after-close.md` and `.html`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-123734-evolution.md`
- Browser QA via Codex `node_repl` confirmed 3 priority cards, 4 brief cards, 5 decision cards, 5 heat tiles, 14 collapsed evidence sections, no console errors, and no horizontal overflow at desktop and 390px mobile widths.

Recommended continuation:

- Add recommendation aftertest persistence: write each daily action/signal to a local JSONL ledger and compute 1/5/20-trading-day outcomes in later reports.

## Latest Update - 2026-07-09 12:15 Asia/Shanghai

- Added and verified `feat-018 - Conclusion-first card report`.
- Refined the after-close HTML from a chart-heavy dashboard into a simpler card-led decision surface:
  - one executive conclusion row,
  - 5 per-position decision cards,
  - action / one-line reason / PnL / day move / weight / risk line,
  - charts retained below the decision cards,
  - long evidence collapsed by default.
- Latest report: `reports/20260709-121513-after-close.html`.
- Updated `docs/harness.md` so future after-close HTML changes must keep conclusion-first cards and collapsed evidence.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-121513-after-close.md` and `.html`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-121557-evolution.md`
- Playwright QA confirmed 4 brief cards, 5 decision cards, 5 heat tiles, 14 evidence sections, 0 evidence sections open by default, no console errors, and no horizontal overflow at desktop and 390px mobile widths.

Recommended continuation:

- Add a source-priority queue for research deltas/external viewpoints: top 3 signals only on the first screen, with the rest collapsed.

## Latest Update - 2026-07-09 12:04 Asia/Shanghai

- Added and verified `feat-017 - Visual intelligence dashboard`.
- Refactored after-close HTML from text-heavy report toward a HyperInsight-style dashboard:
  - `Intelligence Signals`
  - `Action Mix`
  - `Market Breadth`
  - KPI cards
  - position charts
  - `Position Heatmap`
  - collapsible evidence sections
- Markdown report remains unchanged as the full evidence artifact.
- HTML now keeps long-form sections available but collapsed, so the first screen is chart/card led.
- Updated `docs/harness.md` to require visual-first HTML and browser overflow checks for future dashboard changes.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-120437-after-close.md` and `.html`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-120542-evolution.md`
- Static HTML check confirmed `Intelligence Signals`, `Action Mix`, `Market Breadth`, `Position Heatmap`, and 14 collapsible sections.
- Playwright QA confirmed 5 heat tiles, 14 detail sections, no console errors, and no horizontal overflow at desktop and 390px mobile widths.

Recommended continuation:

- Add small trend sparklines from recent daily K-line history for each holding.
- Build a source-quality / priority queue for research deltas and external viewpoints so the dashboard can rank signals, not just display them.

## Latest Update - 2026-07-09 09:11 Asia/Shanghai

- Added and verified `feat-016 - Product-grade InsightRadar foundation`.
- Added `stock_assist/product.py` as the product registry for:
  - product modules,
  - CLI workflow ownership,
  - expected command inputs/outputs,
  - retry guidance,
  - product config/private data/template/generated-output classification.
- Added `stock_assist/workflows/product_map.py` and new CLI command `product-map`.
- Updated `insight-radar --help` to show module boundaries and product-map.
- Updated CLI command failure handling to print expected inputs, expected outputs, and a retry/fix hint.
- Updated README with four modules: Portfolio Intelligence, Research Intelligence, Market Radar, Product Ops.
- Updated `docs/harness.md` with a Product Foundation sprint contract.
- Updated `evolve` capability status to include `feat-015` and `feat-016`.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli product-map` -> `reports/20260709-090959-product-map.md`
- `.venv\Scripts\insight-radar.exe --help`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-091030-after-close.md` and `.html`
- `.venv\Scripts\python -m stock_assist.cli research-monitor` -> `reports/20260709-091104-research-monitor.md`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-091145-evolution.md`
- `rg` check confirmed generated reports and CLI/product registry do not use the old product names.

Recommended continuation:

- Next product-grade increment should add lightweight validators for `portfolio_context`, `event_calendar`, `crypto_watchlist`, `research_sources`, and influencer observation streams.
- Keep the `stock_assist` package name until a migration layer exists; user-facing surfaces should continue to say InsightRadar.

## Latest Update - 2026-07-09 09:05 Asia/Shanghai

- Added and verified `feat-015 - Product rename to InsightRadar`.
- User-facing product name is now `InsightRadar`; checkout path, Python package `stock_assist`, and legacy CLI commands remain compatible.
- Added `stock_assist/branding.py` as the shared source for product name, slug, legacy slug, tagline, and description.
- New console script alias: `insight-radar = stock_assist.cli:main`.
- Compatibility aliases remain: `shenyan-radar = stock_assist.cli:main` and `stock-assist = stock_assist.cli:main`.
- Added explicit setuptools package discovery so editable install only packages `stock_assist*`.
- Updated README, AGENTS notes, harness notes, CLI description, package metadata, HTML report brand, and architecture view brand.
- Regenerated `docs/architecture.html`.
- Fresh branded after-close report: `reports/20260709-090401-after-close.md` and `reports/20260709-090401-after-close.html`.

Verification run:

- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m stock_assist.cli architecture-view`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `Select-String` confirmed `docs\architecture.html` and `reports\20260709-090401-after-close.html` contain `InsightRadar`.
- `.venv\Scripts\python -m pip install -e .`
- `.venv\Scripts\insight-radar.exe --help`
- `.venv\Scripts\shenyan-radar.exe --help`
- `.venv\Scripts\stock-assist.exe --help`

Recommended continuation:

- If `InsightRadar` is accepted as final, update Windows scheduled task names and any Codex automation prompts from `stock-assist` to `insight-radar` / `InsightRadar`.
- Next product sprint can build the HyperInsight-like surface on top of the existing research report monitor and after-close dashboard.

## Latest Update - 2026-07-08 23:18 Asia/Shanghai

- Added and verified `feat-014 - Stable research report provider`.
- `report-cli` is now the priority provider in `stock_assist/workflows/research_monitor.py`; Eastmoney public metadata remains enabled as fallback.
- `configs/research_sources.json` and `.example.json` now support provider controls for `report_cli` and `eastmoney_public`.
- `pyproject.toml` includes both `pypdf` and `report-cli`.
- PDF download now first tries `urlopen`, then falls back to `curl.exe -L -A ...`; this resolved the prior anti-bot script response for the tested report-cli PDF URLs.
- Fresh monitor report: `reports/20260708-231817-research-monitor.md`.
- Evidence from the fresh run: `report-cli 93` records, `eastmoney_public 60` records, and 5 matched PDFs with `status=ok`正文 extraction.
- `data/research_deltas.jsonl` now has full-text-backed `source_status=ok` rows in addition to metadata-only and previously blocked rows.

Verification run:

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\research_sources.example.json`
- `.venv\Scripts\python -m json.tool configs\research_sources.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli evolve`

Recommended continuation:

- Build alert rules on top of the stable source: new coverage, rating/target-price changes, strategy/macro conflict with holdings, and high-confidence thesis weakening/strengthening.
- Then wire high-priority report alerts into the after-close dashboard or a separate intraday intelligence queue.

## Latest Update - 2026-07-08 22:57 Asia/Shanghai

- Added and verified `feat-012 - Research report monitor`.
- New command: `.venv\Scripts\python -m stock_assist.cli research-monitor`.
- New report: `reports/20260708-225710-research-monitor.md`.
- New config: `configs/research_sources.json` with watch keywords for AI, semiconductor, storage, compute, energy storage, lithium, gold, nonferrous, innovative drug, and medical devices.
- New data source wrapper: `stock_assist/data_sources/eastmoney_reports.py`, reading Eastmoney stock/industry/strategy research-report metadata.
- The monitor records relevant SkillHub candidates (`report-ea`, `report-analysis`, `jrj-fin-search-skill`, `yanbaoke-research-report-download`) and GitHub candidates (`manymore13/report-cli`, `lzhttn/EastmoneyCrawler`, `qingxuantang/eastmoney_parser`).
- `feature_list.json` now marks `feat-012` pass; `reports/20260708-225728-evolution.md` confirms the next backlog is again long-term recommendation aftertest/backtest evaluation.

Verification run:

- `.venv\Scripts\python -m json.tool configs\research_sources.example.json`
- `.venv\Scripts\python -m json.tool configs\research_sources.json`
- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli evolve`

Recommended continuation:

- Keep this as the metadata collection layer.
- Next add PDF正文 extraction through SkillHub `report-ea` / `report-analysis` or GitHub `manymore13/report-cli`.
- Then attach `thesis_delta` to each matched holding/theme and later wire high-priority matches into after-close or intraday alerts.

## Latest Update - 2026-07-08 23:06 Asia/Shanghai

- Added and verified `feat-013 - Research report thesis delta`.
- `pyproject.toml` now includes `pypdf`; `.venv` has `pypdf` installed.
- `stock_assist/data_sources/eastmoney_reports.py` now exposes `pdf_url`.
- `stock_assist/workflows/research_monitor.py` now:
  - tries PDF download for matched reports,
  - validates the `%PDF` header before parsing,
  - marks Eastmoney anti-bot responses as `blocked`,
  - generates metadata-based `thesis_delta` records when正文 is unavailable,
  - appends deduped rows to `data/research_deltas.jsonl`.
- `stock_assist/workflows/after_close.py` now surfaces recent `research_deltas` under `研报观点变化`.
- Generated `reports/20260708-230238-research-monitor.md`.
- Generated `reports/20260708-230607-after-close.md` and `.html`.
- Generated `reports/20260708-230633-evolution.md`; it shows `feat-012` and `feat-013` pass.

Important limitation:

- Eastmoney PDF URLs such as `https://pdf.dfcfw.com/pdf/H3_<infoCode>_1.pdf` exist, but direct CLI download currently returns an anti-bot script page, not PDF bytes. The current implementation records this honestly as `source_status=blocked` and falls back to metadata-based deltas.

Recommended continuation:

- Integrate `manymore13/report-cli` or SkillHub `report-ea` / `report-analysis` for richer正文 and target-price fields.
- Add alert rules for high-confidence `反证/削弱`, new coverage, rating changes, target-price changes, and strategy/macro conflicts.

## Current Objective

- Goal: Finish external viewpoint evidence audit after config readiness.
- Current status: `feat-004`, `feat-006`, `feat-007`, `feat-008`, `feat-009`, `feat-010`, and `feat-011` are complete. Formal `configs/event_calendar.json` and `configs/crypto_watchlist.json` now exist. External viewpoints now render source links, source quality, portfolio/peer mapping, verification prompts, and initial A-share price aftertests. `evolve` reports `关键本地输入已就绪`; the next backlog is long-term backtest/evaluation.
- Branch / commit: `master`, latest visible commit `64e7eb9 feat: add replayable portfolio context`.

## Completed This Session

- [x] Compared SkillHub `harness-engineering-pro` with `walkinglabs/learn-harness-engineering`.
- [x] Installed `walkinglabs/learn-harness-engineering/skills/harness-creator`.
- [x] Removed `%USERPROFILE%\.codex\skills\harness-engineering-pro`.
- [x] Added stock-assist harness state and continuity files.
- [x] Validated walkinglabs harness structure at 100/100.
- [x] Added replayable position context fields: buy thesis, initial/current risk line, adjustment history, horizon, and review status.
- [x] Added `data/portfolio_context.example.json`.
- [x] Added `组合上下文与复盘状态` to after-close reports.
- [x] Installed SkillHub `hyperliquid` and `crypto-whale-monitor` under `%USERPROFILE%\.codex\skills`.
- [x] Added read-only Hyperliquid Info API wrapper.
- [x] Added `crypto-monitor` CLI command.
- [x] Added example crypto watchlist config with watched symbols, address placeholder, and alert thresholds.
- [x] Generated a crypto monitor report with market overview and explicit missing-address data gap.
- [x] Added `dex=xyz` support and verified the matched `xyz:XYZ100` short 600 plus `xyz:BRENTOIL` long 50,000 positions.
- [x] Added market anomaly radar for top positions and liquidation-risk scans on watched markets, so new wallets can still surface if the known address changes.
- [x] Upgraded `evolve` to read current feature status, separate missing local data from missing product capability, and avoid repeating stale backlog.
- [x] Marked `feat-004` pass after compile and fresh evolution report verification.
- [x] Created ignored local `data/portfolio_context.json` for the current five Galaxy holdings.
- [x] Extended portfolio context with catalysts, falsification signals, observation windows, and next review dates.
- [x] Added `研究假设与反证` to after-close reports and marked `feat-006` pass after verification.
- [x] Added peer groups for the current holdings and rendered `同业比较证据` with 5日/20日表现、市值、预告PE and sector anchors.
- [x] Marked `feat-007` pass after compile, after-close report generation, and evolution verification.
- [x] Added best-effort A股/美股/韩国 macro snapshots from Yahoo chart data.
- [x] Rebuilt HTML rendering into a dark research dashboard with KPI cards, market cards, and CSS bar charts.
- [x] Verified the dashboard in the in-app browser via localhost preview, including desktop and 390px mobile overflow checks.
- [x] Added `configs/event_calendar.example.json` and a configured upcoming-event watchlist.
- [x] Added `事件日历与公告 watchlist` to after-close reports, combining configured upcoming events with CNInfo latest filing monitoring.
- [x] Marked `feat-008` pass after compile, after-close report generation, and evolution verification.
- [x] Promoted `configs/event_calendar.example.json` to formal `configs/event_calendar.json`.
- [x] Promoted `configs/crypto_watchlist.example.json` to formal `configs/crypto_watchlist.json`.
- [x] Verified after-close, crypto-monitor, and evolve with formal configs.
- [x] Upgraded external viewpoint lines with source links, source quality, portfolio/peer mapping, verification prompts, and A-share price aftertests.
- [x] Marked `feat-011` pass and verified the next evolution backlog moved to recommendation backtest evaluation.

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Compile | `.venv\Scripts\python -m compileall stock_assist` | Pass | Python modules compile. |
| After-close workflow | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated Markdown and HTML reports. |
| Harness validation | `node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target %USERPROFILE%\Documents\stock-assist` | Pass | Overall 100/100 after standard root files were added. |
| Replayable context report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-195401-after-close.md` and `.html`; report includes context gap and context section. |
| Context overlay smoke check | inline Python using `data/portfolio_context.example.json` | Pass | Returned `watch 1`, proving example context overlays onto a holding. |
| Crypto compile | `.venv\Scripts\python -m compileall stock_assist` | Pass | Hyperliquid modules and CLI compile. |
| Crypto monitor | `.venv\Scripts\python -m stock_assist.cli crypto-monitor` | Pass | Generated `reports/20260708-215545-crypto-monitor.md`; report uses example config with dex=xyz, the verified 0xec4 address, and market anomaly radar. |
| Evolution compile | `.venv\Scripts\python -m compileall stock_assist` | Pass | Evolution workflow compiles. |
| Evolution backlog | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-220226-evolution.md`; report shows `feat-004: pass`, local data gaps, and capability-aware backlog. |
| Local context JSON | `.venv\Scripts\python -m json.tool data\portfolio_context.json` | Pass | Local ignored context parses as JSON. |
| Hypothesis report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-220857-after-close.md` and `.html`; includes `研究假设与反证`. |
| Post-hypothesis evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-220904-evolution.md`; report shows `feat-006: pass`. |
| Peer comparison report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-221420-after-close.md` and `.html`; includes `同业比较证据`. |
| Post-peer evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-221429-evolution.md`; report shows `feat-007: pass`. |
| Dashboard report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-222957-after-close.md` and `.html`; includes macro section and dashboard HTML. |
| Browser dashboard QA | localhost preview | Pass | Confirmed 3 market cards, 3 chart panels, no console errors, and no desktop/mobile horizontal overflow. |
| Post-dashboard evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-223125-evolution.md`; report shows `feat-010: pass`. |
| Event watchlist report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-223430-after-close.md` and `.html`; includes `事件日历与公告 watchlist`. |
| Post-event evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-223458-evolution.md`; report shows `feat-008: pass`. |
| Formal-config after-close | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-223928-after-close.md` and `.html`; data gaps show `暂无`. |
| Formal-config crypto monitor | `.venv\Scripts\python -m stock_assist.cli crypto-monitor` | Pass | Generated `reports/20260708-223944-crypto-monitor.md`; uses `configs\crypto_watchlist.json`. |
| Config-readiness evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-223948-evolution.md`; report shows `关键本地输入已就绪`. |
| External-view audit report | `.venv\Scripts\python -m stock_assist.cli after-close` | Pass | Generated `reports/20260708-224507-after-close.md` and `.html`; includes links, mappings, verification prompts, and A-share price aftertests. |
| Final evolve | `.venv\Scripts\python -m stock_assist.cli evolve` | Pass | Generated `reports/20260708-224536-evolution.md`; report shows `feat-011: pass` and next backlog is backtest evaluation. |

## Files Changed

- `AGENTS.md`
- `docs/harness.md`
- `feature_list.json`
- `progress.md`
- `session-handoff.md`
- `init.sh`
- `stock_assist/portfolio.py`
- `stock_assist/workflows/after_close.py`
- `stock_assist/data_sources/hyperliquid.py`
- `stock_assist/data_sources/global_markets.py`
- `configs/event_calendar.example.json`
- `configs/event_calendar.json`
- `configs/crypto_watchlist.json`
- `stock_assist/workflows/crypto_monitor.py`
- `stock_assist/workflows/evolution.py`
- `stock_assist/reports.py`
- `stock_assist/portfolio.py`
- `stock_assist/workflows/after_close.py`
- `stock_assist/cli.py`
- `configs/crypto_watchlist.example.json`
- `data/portfolio_context.example.json`
- `data/portfolio_context.json` (ignored local file)
- `README.md`

## Decisions Made

- Keep only walkinglabs `harness-creator` for harness work.
- Use root `feature_list.json` because walkinglabs validators and templates expect that name.
- Keep `docs/harness.md` as stock-assist-specific operating notes rather than the primary state tracker.
- Keep `data/portfolio_context.json` separate from broker snapshots so daily Galaxy refreshes do not erase research memory.
- Let `evolve` use `feature_list.json` as the source of truth for implemented/planned features, then layer report scan counts and local data gaps on top.
- Use `data/portfolio_context.json` for testable hypotheses, but keep placeholder `待补` text explicit until the user's original trade notes are available.
- Start peer comparison with explicit in-code peer groups for current holdings; later this can move into `configs/industries.json` once the peer taxonomy stabilizes.
- Use Yahoo chart data as best-effort macro context for A股/美股/韩国; macro failures are reported as data gaps and do not block after-close portfolio analysis.
- Keep dashboard charts CSS-only for now, which avoids adding a JS chart dependency and works in static HTML reports.
- Keep event calendar config-driven first; use CNInfo latest filings as automatic critical-filing evidence, and promote to a formal local `configs/event_calendar.json` only when the example event shape feels right.
- Formal event and crypto configs are project configs, not secrets; credentials/private broker snapshots remain ignored under `.env` and `data/*`.
- Treat external views as auditable evidence only: links and price aftertests help judge quality, but unverified opinions still should not directly become trading instructions.

## Blockers / Risks

- Existing unrelated modified/untracked files remain in the working tree.
- AmazingData checks should remain serial because account login/query flows are not safe to parallelize.
- Real `data/portfolio_context.json` now exists and is ignored by git, but several fields are conservative placeholders rather than the user's true original trade logic.
- RWA/HIP-3 account monitoring needs the correct dex. Querying the verified address on the main dex returns empty positions; querying `dex=xyz` returns the BlockBeats-matching RWA positions.

## Next Session Startup

1. Read `AGENTS.md`.
2. Read `feature_list.json` and `progress.md`.
3. Review this handoff.
4. Run `./init.sh` where available, or on Windows run the equivalent PowerShell commands listed in `AGENTS.md`.

## Recommended Next Step

- P0 data cleanup: replace placeholder `待补` trade theses in `data/portfolio_context.json` with the user's real original trade logic.
- Researcher-view A-share next sprint: add backtest/evaluation persistence so recommendations and external-view signals can be judged after 1/5/20 trading days.
- UI follow-up: observe a few daily reports before adding heavier chart types; current dashboard already has KPI cards, market cards, and CSS bar charts.
- Crypto follow-up: copy `configs/crypto_watchlist.example.json` to `configs/crypto_watchlist.json`, adjust thresholds/extra addresses, then run `.venv\Scripts\python -m stock_assist.cli crypto-monitor`.

## 2026-07-10 Handoff - Signal Outcome Ledger

Changed:
- Added persistent after-close outcome tracking in `stock_assist/signal_outcomes.py` and integrated it into after-close payload/renderers plus `evolve`.
- Added a durable official-product benchmark in `docs/product-benchmark.md`.
- Added `feat-027` with verification evidence.

Verified:
- Compile, deterministic fake-price outcome calculations, and real AmazingData-backed after-close generation passed.
- Fresh artifact: `reports/20260710-083803-after-close.json` with matching Markdown and HTML.
- Runtime ledger: `data/signal_outcomes.jsonl` (private/ignored), currently 6 unique pending signals as of the 2026-07-09 close.

Current state:
- Signal dates are deduplicated by `YYYY-MM-DD:CODE`.
- Hold actions score later positive returns as hits; risk-reduction actions score later negative returns as hits.
- No horizon is scored until its trading-session count matures.

Next:
- Let daily runs accumulate observations, then add benchmark-relative contribution and outcome-calibrated alerts. Keep sample count visible and do not optimize against a tiny history.

## 2026-07-10 Handoff - Native Windows Discipline Reminder

Changed:
- Added the native WinForms resident app in `windows/InsightRadar.DisciplineReminder`.
- Added `configs/trading_discipline.json`, build/install/uninstall scripts, and `docs/trading-discipline-reminder.md`.
- Added `feat-028` and ignored generated .NET/publish output.

Verified:
- Native publish and JSON config validation passed.
- `InsightRadar-DisciplineReminder` is an interactive Windows logon task in `Running` state.
- Controlled `--show-now` verification found the visible borderless reminder banner; normal after-hours startup stayed hidden in the tray.

Current state:
- The app is installed and running independently of Codex.
- Default schedule is weekdays 09:10-15:05, with five-minute visual/audio reinforcement.

Next:
- After using it for a trading day, adjust banner height, sound, reminder interval, or copy in `configs/trading_discipline.json` if needed.

## 2026-07-14 Handoff - Multi-timeframe Market Levels

Changed:
- Added `market-levels` under Market Radar with a shared JSON/Markdown/HTML report contract.
- Added public K-line routing, 3-minute aggregation, Chan-theory approximation, MACD state/divergence candidates, and multi-evidence support/resistance clusters.
- Added `feat-029`, config/example files, unit tests, README instructions, and a dedicated harness contract.

Verified:
- Unit tests, compileall, config JSON validation, and the real public-data workflow passed.
- Fresh artifact: `reports/20260714-114930-market-levels.json` with matching Markdown and HTML, all six timeframes, and zero data gaps.
- Browser QA passed desktop and 390px mobile layouts with no console errors or horizontal overflow.

Current state:
- The report is intentionally an execution map, not a predictor. It reports hold, invalidation, and reclaim conditions.
- Chan output is a deterministic approximation, not a claim to reproduce every analyst's manual stroke segmentation.
- Current intraday support is clustered around 3865-3889; the larger weekly cluster is 3762-3829. These values come from the 2026-07-14 11:30 incomplete bars and will move.

Next:
- Accumulate daily level-map outcomes, then measure which zones held, broke, or reclaimed before changing weights or tolerances.

Conclusion-first refinement:
- The primary report surface now leads with observed low 3869.30 and the 3867-3881 intersection of the first 3m/15m/60m support zones.
- It shows 3912-3927 as the first reclaim confirmation and 3762-3820 as the next monthly/weekly support if the intraday low fails.
- Full timeframe calculations remain in JSON and a collapsed HTML detail block; normal reading is now conclusion plus plan plus reference K-lines.

## 2026-07-14 Handoff - Local Factor Lab

Changed:
- Added `factor-lab` with eight interpretable daily factors, rolling ridge estimation, five-day benchmark-relative labels, an embargo, quintile/IC/VIF diagnostics, costs, and hard validation gates.
- Added config/example files, product/CLI registry entries, tests, README instructions, and a Factor Lab harness contract.

Verified:
- Unit tests, compileall, config validation, a real AmazingData run, strict JSON parsing, and static HTML checks passed.
- Fresh artifact: `reports/20260714-143250-factor-lab.json` with matching Markdown and HTML, as of the completed 2026-07-13 daily bar.

Current state:
- The implementation works, but the strategy itself failed: negative average RankIC, negative Top-Bottom spread, reversed quintile monotonicity, and high liquidity/Amihud collinearity.
- The latest ranking remains diagnostic only. It must not feed `after-close` actions or a paper portfolio while validation status is `failed_validation`.
- The current 20-stock pool is explicit and survivor-biased; it is not an official historical CSI 1000 universe.

Next:
- Cache dated official CSI 1000 constituents, add industry/size neutralization, ST/new-listing/limit-up/down filters and realistic impact cost, then test factor families separately with nested walk-forward selection.

## 2026-07-14 Handoff - Personal Factor Pipeline MVP

Changed:
- Added `factor-pipeline` with a private daily observation ledger, T+5 label maturation, versioned Ridge v1 challengers, hard gates, and champion-only production scoring.
- Added config/example, model schema, registry example, tests, product/CLI entries, local runner, optional scheduled-task installer, and `docs/personal-factor-model.md`.

Verified:
- Six factor tests, compileall, JSON validation, real AmazingData pipeline generation, same-data idempotency, registry dedupe, and UTF-8 task-log checks passed.
- Fresh artifact: `reports/20260714-144314-factor-pipeline.json` with matching Markdown and HTML.

Current state:
- The ledger has 6,447 observations, 6,347 mature labels, and 100 pending T+5 labels.
- Candidate `20260713-07d5a907da` has healthy collinearity diagnostics after removing Amihud from Ridge v1, but still fails every predictive gate. No champion exists and rankings remain diagnostic only.
- The optional Windows scheduled-task installer has not been run, so no new external scheduler state was created.

Next:
- Add point-in-time CSI 1000 membership, industry and float-market-cap exposures, then neutralize factors and run family-by-family ablations. Preserve hard gates and never force promotion by loosening thresholds after seeing results.

## 2026-07-14 Handoff - Point-in-time CSI 1000 Universe

Changed:
- Added `factor-universe-sync`, `stock_assist/universe.py`, PIT interval filtering, universe lineage, model schema v2, separate CSI 1000 example configs, and `feat-032`.

Verified:
- Nine focused tests, compileall, JSON checks, static HTML checks, and a real AmazingData sync passed.
- Fresh sync artifact: `reports/20260714-183223-factor-universe.json` with matching Markdown/HTML and 3,439 interval rows / 1,000 open members.
- Fresh compatibility artifact: `reports/20260714-183404-factor-pipeline.json`; same-data rerun remained idempotent and no champion exists.

Current state:
- Historical CSI 1000 membership can now remove current-constituent survivor bias and is locked by manifest hash.
- The default 20-stock pilot remains intentionally separate and unchanged in meaning.
- Index weights/free-float, industry/size neutralization, and tradability constraints remain incomplete.

Next:
- Implement one feature only: point-in-time industry and float-market-cap exposures plus neutralization diagnostics. Do not expand to LightGBM or live trading yet.

## 2026-07-14 Handoff - Project Memory and Architecture Freshness

Changed:
- Added `PROJECT_MEMORY.md` plus architecture, product-state, and decision-log topics in `docs/memory/`.
- Added executable memory validation and wired it into AGENTS startup, the harness contract, and `init.sh`.
- Refreshed the interactive architecture topology to 18 nodes / five lanes / all 17 registered product commands, including recent market, factor, Windows reminder, and feedback-loop work.
- Replaced the mojibake-prone architecture renderer with a clean responsive implementation.

Verified:
- Project memory validator passes with 3 topics, bounded index size, fresh generated topology, and architecture command coverage 17/17.
- Harness validator remains 100/100; compileall, JSON validation, and `git diff --check` pass.
- In-app browser QA passed desktop and 390px layouts, node interaction, console checks, and Chinese text checks.

Current state:
- New sessions must read `PROJECT_MEMORY.md`, then load only the triggered topic. Architecture and cross-module work must load `docs/memory/architecture.md`.
- `configs/architecture.json` is the graph source; `docs/architecture.html` is generated and must not be edited directly.
- No external memory skill was installed. The existing harness now owns project memory without a parallel framework.

Next:
- Resume `feat-033`: point-in-time industry and float-market-cap exposures plus neutralization diagnostics. Keep model promotion gates unchanged.

## 2026-07-14 Handoff - Product Continuity and Module Rings

Changed:
- Added `CURRENT_STATE.md`, `docs/product-charter.md`, two ADRs, bounded-history startup routing, and product-ring validation.
- Classified the 18 architecture nodes as Core, Lab, Satellite, Extension, or Governance and regenerated the topology with visible ring labels.
- Recorded `feat-035` as passed without installing a second memory framework.

Verified:
- Project-memory validation passes with the bounded current snapshot, four topics, valid next feature, 5/5 rings, and 17/17 command coverage.
- Harness validation remains 100/100; compileall, JSON/static HTML checks, and `git diff --check` pass.

Current state:
- New sessions read `AGENTS.md`, `PROJECT_MEMORY.md`, and `CURRENT_STATE.md`, then query only the exact feature and matching history.
- Core is the A-share portfolio decision loop. Factor work is Lab-only; the reminder is a Satellite; crypto/X are optional Extensions; memory/architecture/evolution are Governance.
- Keep one repo and a modular monolith until a component has an independent lifecycle, security boundary, scaling need, runtime conflict, or stable contract.

Next:
- Resume `feat-033` point-in-time industry/free-float neutralization. Do not expand model complexity or automated execution before the evidence-to-outcome loop is reliable.

## 2026-07-14 Handoff - Reminder Extraction and Core Focus Freeze

Changed:
- Added `scripts/export-discipline-reminder.ps1` and a self-contained standalone harness/context template under `docs/extractions/discipline-reminder/`.
- Generated directory and ZIP artifacts under `dist/InsightRadar.DisciplineReminder-extraction*` with source hashes and cutover/rollback instructions.
- Added ADR-0003, extraction planning, `feat-036` pass, and `feat-037` pending; parked `feat-033`.

Verified:
- The isolated reminder package builds Release with 0 warnings/errors and parses all 24 configured rules.
- Standalone harness validation is 100/100; file hashes and archive membership pass.
- Windows task `InsightRadar-DisciplineReminder` is unchanged and still targets the original repository.

Current state:
- Open the extracted directory in a new task and follow its `AGENTS.md`, `CURRENT_STATE.md`, and `session-handoff.md`; no original chat memory is needed.
- The new task should complete only `dr-002`. Do not remove the original source until task-path, tray controls, launch/logon, and rollback have passed.
- Main InsightRadar expansion is frozen. Core stays portfolio decisions, A-share market/research evidence, outcomes, and governance.

Next:
- In the standalone task: choose the permanent path and perform explicit Task Scheduler cutover.
- In this main repo: run `feat-037` core decision-loop reliability baseline. Do not resume factor/crypto/X expansion yet.

## 2026-07-14 Handoff - Reminder Cutover and Source Retirement

Changed:
- Standalone `dr-002` completed at `D:\work\reminder`; the Windows logon task and resident process now use the D-drive executable.
- Removed the C-drive intermediate repository and all reminder source/config/scripts/docs/export artifacts from `stock-assist`.
- Removed the reminder ProductFile/architecture node and refreshed product-scope, ADR, current-state, and extraction documentation.
- Migrated 128 historical log records into the standalone log, producing 138 verified JSONL entries after cutover testing.

Verified:
- D-drive publish/build/config validation passed with 24 rules and 0 build errors.
- Banner capture, acknowledge, 10-minute snooze, SAPI speech, and a normal scheduled-task restart passed.
- Task action/working directory and the sole resident process resolve to `D:\work\reminder` with no temporary arguments.

Current state:
- The reminder is fully independent and no longer part of the InsightRadar repository or architecture graph.
- Future reminder work and rollback belong exclusively to `D:\work\reminder`.
- InsightRadar next feature remains `feat-037`; do not reintroduce a reminder dependency into the core decision loop.

## 2026-07-14 Handoff - Canonical InsightRadar Workspace

Changed:
- The canonical main repository is now `D:\work\InsightRadar`; it contains the complete latest Git worktree and all uncommitted July 14 changes.
- The older `D:\work\stock-assist` directory is archived at `D:\work\_archive\stock-assist-legacy-20260707` and must not be treated as a source of truth or merged automatically.
- Active project context uses InsightRadar. The internal `stock_assist` package and legacy CLI aliases remain for compatibility only.

Verified:
- Before destination edits, source and destination matched Git HEAD, all 51 worktree status lines, and Robocopy mirror state.
- Project-memory validation, 17/17 command coverage, harness 100/100, Python compilation, `git diff --check`, `insight-radar --help`, and D-drive editable-install resolution passed from the canonical workspace.
- Codex config uses the D-drive trust/open path. The weekday automation name and prompt use InsightRadar and explicitly route source reads to `D:\work\InsightRadar`.
- The standalone reminder task is `Running` with one process from `D:\work\reminder`; the main-project migration did not change its action or working directory.

Current state:
- New code, private data, reports, state updates, and Codex automation runs belong only in `D:\work\InsightRadar`.
- Historical `stock-assist` references in append-only evidence and provenance are intentional and should not be rewritten as if they were current paths.
- The C-drive reminder path is a junction to `D:\work\reminder`. The old main checkout is gone; only a two-file compatibility shell remains because this resumed task is still bound to its root. Codex still lists the old path until the D-drive folder is opened as a project.

Next:
- Open `D:\work\InsightRadar` as a new InsightRadar project/task. From that D-drive task, remove the old two-file C-drive shell, create a junction to the canonical workspace, and retarget the weekday automation project id to D.
- Resume `feat-037` from the D-drive workspace.

## 2026-07-14 Handoff - Workspace Migration Closeout Blocked by Directory Handle

Changed:
- The existing `InsightRadar 工作日交易晨报` automation now uses `D:\work\InsightRadar` for both its project id and working directory.
- The automation name, active state, weekday 08:00 Asia/Shanghai schedule, model, fixed Chinese brief structure, and business prompt were preserved.
- The two migration-only notice files were removed from `%USERPROFILE%\Documents\stock-assist` after a recursive inventory confirmed there were no unique project files.

Verified:
- `40d119e` is in the current `HEAD`; the D-drive worktree was clean before these documentation edits.
- The reminder task and sole resident process still resolve to `D:\work\reminder`; nothing in the standalone reminder repository was changed.
- Automation persistence records `target.project_id = D:\work\InsightRadar` and `cwds = [D:\work\InsightRadar]` with the prior schedule and prompt intact.
- Both destructive attempts rechecked exact source and target absolute paths and an empty, non-reparse source directory before acting.
- Project-memory validation passed with 17/17 architecture command coverage; Harness validation passed at 100/100 with no bottleneck; `git diff --check` passed. `CURRENT_STATE.md` remains within its line and byte limits.

Blocker:
- Windows still reports the empty `%USERPROFILE%\Documents\stock-assist` root as in use, even after the automation cutover. It could not be removed normally, so no junction was created.
- The empty ordinary directory was preserved. No forced deletion or unknown-process termination was attempted.

Next:
- Close or identify the external owner of the empty C-drive directory, then remove it normally and create the junction to `D:\work\InsightRadar`.
- Verify the junction target, automation target, reminder ownership, project-memory validation, harness validation, `git diff --check`, and clean Git state; only then remove the migration Known Gap and begin `feat-037`.

## 2026-07-14 Handoff - Project and Product Status Audit

Reviewed:
- Canonical D-drive repository state, product memory/direction, exact `feat-037` scope, latest Core report artifacts, current local holdings, signal outcomes, tests, and governance validators.

Verified:
- The code/governance baseline is healthy: compileall, 13 unit tests, project-memory validation with 17/17 commands, Harness 100/100, CLI help, JSON parsing, and `git diff --check` passed.
- The decision surface is structurally present for all 3 holdings, but no current-day post-close Core artifact exists from the post-migration D-drive workspace.

Current state:
- `feat-037` remains pending and must not start until the empty old C-drive directory can be replaced safely with a junction.
- Latest `after-close` is 20260714-084139 with prices through 2026-07-13; strict current-day decision-ready coverage is therefore 0/3 while structural plan coverage is 3/3.
- Latest `market-pulse` predates migration and still records the old C-drive audit path. Research deltas and the latest research-monitor artifact date to 2026-07-09. Outcome samples are too immature for quality claims.

Next:
- Close or identify the owner of the old C-drive root, create and verify the junction, then run `feat-037` from D with real local inputs and fresh `after-close`, `market-pulse`, `market-levels`, `research-monitor`, outcome, and `evolve` evidence. Keep Factor Lab and Extensions parked.

## 2026-07-14 Handoff - Iwencai Portable Data Candidate

Changed:
- Installed Iwencai SkillHub CLI under `%USERPROFILE%\.iwencai-skillhub`, its PowerShell wrapper under the user-local bin directory, and `hithink-market-query` under the Codex skills directory.
- Configured the Windows PowerShell all-hosts profile with Iwencai PATH/base URL/key loading; the real key remains in the Windows current-user environment store and must never be copied into the repository.
- Added ADR-0005 and the decision-log/current-state pointers. Iwencai remains a candidate adapter outside Core during the expansion freeze.

Verified:
- New-shell CLI and environment loading passed; the profile contains no literal API key.
- A live one-row Shanghai Composite query succeeded from the installed cross-platform Python skill.

Risk / Next:
- Vendor skill download uses HTTP without published checksum verification, and the 0.0.4 outer installer filename does not match its ZIP. Require a pinned HTTPS/checksum or reviewed mirror before cloud automation.
- Do not integrate or replace Galaxy/AmazingData yet. Finish the workspace junction prerequisite and `feat-037`, then validate Iwencai on macOS ARM/Linux plus multi-day source reconciliation under a separately scoped feature.

## 2026-07-14 Handoff - Local-First Core Value Validation

Decision:
- ADR-0006 keeps the product local-first. Cloud deployment, production Docker, WSL/macOS migration, new clients, and infrastructure expansion are parked because their cost is premature before the Core proves decision value.
- The proof standard is broader than backtest win rate: require sufficient matured samples, benchmark-relative expectancy after realistic costs, drawdown and payoff ratio, MFE/MAE, regime/time-split stability, point-in-time inputs, bias controls, and out-of-sample evidence. Historical performance must later survive paper/live shadow validation; do not claim guaranteed returns or stable compounding.

Current state:
- `feat-037` remains the only active next feature and is still blocked by the old empty C-drive root that Windows reports in use.
- Canonical work remains local at `D:\work\InsightRadar`. Iwencai stays a manual candidate under ADR-0005; no provider or platform migration was started.

Tomorrow:
- Close or identify the old-path owner, create and verify the junction, confirm clean migration state, then run `feat-037` serially with fresh real `after-close`, `market-pulse`, `market-levels`, `research-monitor`, outcome, and `evolve` evidence.
- After the reliability baseline passes, scope Core value validation and outcome maturation before any portability, Docker, cloud, client, factor, crypto/X, or automated-execution work.

## 2026-07-15 Handoff - feat-038 NGA Great Times Monitor

Current state:
- The user explicitly reprioritized a narrow NGA public-viewpoint Extension before `feat-037`.
- `nga-auth set/status/clear` and `nga-monitor` are implemented. Cookie storage is outside the repository at `%LOCALAPPDATA%\InsightRadar\secrets\nga_cookie.txt`; no secret has been read from the browser or written to Git.
- The collector targets confirmed `fid=706`, appends ignored board snapshots, ranks reply velocity, counts configured watch terms, and labels sentiment as a title-only proxy.
- Unit tests, compileall, JSON checks, CLI help, and diff checks pass. Architecture generation and project-memory validation should be rerun after live completion evidence is recorded.

Blocker / next:
- The user must enter the Cookie once via the hidden `nga-auth set` prompt; browser automation must not export it.
- Run two live `nga-monitor` captures several minutes apart, inspect parsing and delta ranking, then activate and verify the recurring automation.
- After `feat-038` passes, restore `feat-037` as `next_feature_id` and resume the Core reliability baseline.

Completion update:
- The user stored a refreshed Cookie outside the repository. Two live captures succeeded and snapshot inspection confirmed no secret fields.
- Codex automation `nga` is ACTIVE against `D:\work\InsightRadar`, scheduled only at 08:50 and 15:50 on workdays with read-only report behavior. Manual runs are reserved for exceptional event days.
- `feat-038` now passes; `feat-037` is again the next feature. If NGA later returns 401/403, rerun `nga-auth set` locally without placing the Cookie in chat or command arguments.
## 2026-07-15 Handoff - feat-039 NGA AI Daily Digest

- `nga-daily --llm` now produces JSON/Markdown/HTML editorial-style reports from authenticated fid=706 JSON data. AI controls only grouping and prose; thread ids are validated and all links, floors, scores, and excerpts are program-owned evidence.
- Local API secret is outside the repository at `%LOCALAPPDATA%\InsightRadar\secrets\openai_api_key.txt`; never print it or add it to `.env`/Git. Because the user pasted the current key in chat during setup, recommend rotating it and updating through hidden `llm-auth set`.
- The normal schedule is workdays 08:50 lightweight snapshot and 15:50 one-call AI daily digest. The final commissioning artifact is `reports/20260715-212002-nga-daily.*`.
- `feat-037` remains the next Core feature; feat-039 is an optional Extension and cannot block Core.

### Codex-native automation update

- The default `nga` automation no longer calls aiapi.world. At 15:50 it runs `nga-daily` without `--llm`, reads the generated JSON evidence, and writes the five-topic report with the automation's own `gpt-5.4` model at medium reasoning.
- Quality target is NGA thread `47185220`; the full structural and anti-filler contract is embedded in the automation prompt. The OpenAI-compatible client remains an opt-in manual fallback for future tuning, not part of the schedule.
## 2026-07-15 Handoff - feat-040 NGA Time-Window Acceptance

- `nga-daily` now supports `--window morning` (00:00-09:00) and `--window day` (00:00-15:59). It discovers candidates across paged board metadata, throttles detail calls to respect NGA behavior, prioritizes page 1, and falls back to page e when the first page has no in-window replies.
- Verified retrospective day evidence: 35 topics, 31 with reply evidence after throttling. Source artifact: `reports/20260715-215836-nga-daily.json`.
- Codex-native acceptance artifact: `reports/20260715-nga-codex-preview.md` / `.html`; no external AI was called. User acceptance is still pending, so feat-040 remains in progress and `feat-037` should be restored only after acceptance.
- ACTIVE automation id `nga` is named `NGA大时代盘前盘后日报`, scheduled workdays at 08:50 and 15:50 with gpt-5.4 medium reasoning and time-window-specific commands.
### feat-040 review feedback - sentiment and KOL layer

- Acceptance remains pending. The next preview must lead with a visual sentiment dashboard and separate direction (bullish/bearish) from intensity stage (icepoint/climax).
- `configs/nga_monitor.json` contains nine influential NGA UIDs supplied by the user. `NGADailyTopic` and `NGAReply` now retain author_id; watched-author activity is emitted separately and excluded from public consensus in the automation contract.
- Current source limitation: no stable per-UID full-history JSON endpoint was verified. Report only board-sample UID hits and phrase no activity as “current board sample did not match.”

### feat-040 review feedback - long-thread KOL replies

- Thread-local `authorid` filtering works, but author-filtered JSON can truncate. `fetch_author_thread_replies` therefore reads complete HTML, checks exact UIDs, and walks backward through author-only pages to the time-window boundary.
- Configured long threads: fuelish tid 47002314, 文驹 47047228, 幸运阿sai 46906089, -阿狼- 45974302, 村上吹树 46872529. Current KOL-authored sample threads are added dynamically.
- Fresh evidence `reports/20260715-223952-nga-daily.json` has zero KOL collection gaps and recovers 8 fuelish, 10 铁锤狂砸盘, and 11 村上吹树 replies for 00:00–15:59. The revised Codex preview is `reports/20260715-nga-codex-preview.md/.html`.
- 幸运阿sai's 1.15 prior is capped, KOL-only, and explicitly user-provided/unverified. The ACTIVE automation `nga` consumes long-thread reply evidence and preserves the no-external-AI rule.
- User acceptance is still pending; do not mark feat-040 passed until the revised preview is accepted.

### feat-040 review feedback - technology-mainline discipline contract

- `configs/nga_monitor.json` and its example now retain a provenance-labelled decision framework for 幸运阿sai / tid=46906089. It records candidate 6%-8% / 10%-12% / 15% response bands, separates industry and trading structure, and requires core-stock, chain-rotation, and sustained style-switch checks.
- Treat this review as user-provided and page-unverified. The public web fetch returned 403 and the bounded author-only adapter found no 2026-07-16 reply; do not describe it as an independently captured same-day post.
- ACTIVE automation `nga` now adds “策略契约与反证检查” when relevant and must report conflicts with current evidence. Candidate thresholds cannot become universal stops or Core actions without user-specific risk configuration and independent data.
- ADR-0007 records the durable evidence boundary. `feat-040` remains in progress pending acceptance; `feat-037` remains parked only for this explicit review cycle.
- Fresh verification artifact: `reports/20260716-165153-nga-morning.*` (12 topics, zero influencer collection gaps, zero 幸运阿sai in-window activity, framework provenance present in JSON).
- Follow-up loss review: 盛新锂能 closed 45.65 on 2026-07-01, 43.60 on 07-02, and 42.10 on 07-03 before the later 38.14 limit-down close. The product framework now treats external views as research-only, flags post-entry thesis substitution, requires filing/expectation/price confirmation for earnings claims, and exposes inactive candidate monthly-profit giveback bands pending user approval.

### feat-040 visual-first acceptance revision

- `stock_assist.reports.markdown_report_to_html` now recognizes NGA sentiment/KOL reports and builds a visual-first dashboard from fixed Markdown fields: sentiment mix, four intensity scores, sector heat, KOL signals, and five conclusion cards.
- Long-form sections remain in the same HTML but are collapsed by default. The ACTIVE `nga` automation now writes 120-180 character conclusion-first theme bodies instead of 280-450 character essays and keeps exact field labels for deterministic chart parsing.
- The current user-facing artifact remains `reports/20260715-nga-codex-preview.html`. Browser automation cannot reload local `file://` pages, so the user must refresh the existing tab manually. feat-040 remains in progress pending acceptance.

## 2026-07-18 Handoff - feat-041 Daily Risk Watch

- `risk-watch` is implemented and verified in the canonical D-drive workspace. It fetches optional Iwencai 883957.TI breadth, Tencent/Eastmoney A-share indexes, Yahoo QQQ/SOX/KOSPI/Nikkei histories, and the ignored private `data/risk_watch_profile.json`.
- The report separates market temperature from the locked execution budget. Orange/red require confirmation and multiple evidence families; after a red budget, exposure cannot be expanded until three confirmed green sessions.
- Fresh artifact `reports/20260718-214135-risk-watch.*` reports red 76/100 for 2026-07-17, with first replay alerts on 05-19 yellow, 06-03 orange, and 06-09 red. Current 20% total exposure is under the red 30% total cap; high-beta concentration is 20% versus a 15% cap.
- The Korea event gate detected the second June KOSPI circuit breaker on 06-23, marked it as the second 8% shock within 20 sessions, and kept the event active through 07-01. The event-only review artifact is `reports/20260718-214008-risk-watch.*`.
- ACTIVE automation id `insightradar` runs the read-only command at 16:20 on workdays, compares the prior artifact, and headlines newly activated Korea gates. It must not trade or overwrite the user's current profile from old broker screenshots.
- `feat-041` passes. `feat-040` is parked pending user acceptance; resume `feat-037` and accumulate alert outcomes before recalibrating thresholds.

## 2026-07-18 Handoff - feat-042 Crowding and cross-market shock extension

- `risk-watch` now adds a current Iwencai turnover-concentration snapshot and includes S&P 500 alongside QQQ/SOX/KOSPI/KOSDAQ/Nikkei.
- US/Japan shocks use absolute drawdown floors plus volatility-standardized 10-session shocks/repeats; Korea retains the explicit circuit-breaker and second-shock gates. `cross_region_shock` activates when US and Japan/Korea event windows overlap.
- Fresh artifact `reports/20260718-233503-risk-watch.*` reports top-20 turnover concentration 14.7%, top-50 24.2%, and ????C as the turnover leader. Concentration is visible but does not score until 20 daily snapshots mature.
- The active `insightradar` automation was updated through the automation API to headline any cross-market event gate and include the new crowding snapshot.
- Futu community feeds can supply timestamped narrative text for selected symbols, but current responses lack engagement fields and historical samples. Keep long-horizon narrative/FOMO diagnostic-only until a point-in-time archive is validated.
- `feat-042` passes focused verification; resume `feat-037` after this explicit user reprioritization.

## 2026-07-19 Handoff - feat-043 AI CapEx Watch

- `ai-capex-watch` is implemented and verified as a Core research workflow. It generates JSON/Markdown/HTML from `configs/ai_capex_watch.json` and exposes CapEx momentum, optical transmission, supplier realization, conditional actions, official links, freshness, and explicit gaps.
- Fresh artifact `reports/20260719-002412-ai-capex-watch.*` reports 70.3 CapEx momentum (54% coverage), 74.4 optical transmission (60% coverage), and pending 中际 realization. The conclusion supports the industry thesis but explicitly forbids using total CapEx as a chasing signal.
- The active `insightradar` automation still runs workdays at 16:20 and now executes both `risk-watch` and `ai-capex-watch`, comparing each with its previous payload. It remains read-only and cannot trade.
- Official evidence is currently curated in config rather than auto-discovered. The next logical indicator work is official-IR change discovery, then 中际 financial ingestion; resume `feat-037` unless the user explicitly reprioritizes again.
- Direct local `file://` browser QA was blocked by Browser URL policy. Structural report validation passed, but do not claim responsive visual QA until an allowed viewing path is available.

## 2026-07-19 Handoff - feat-037 Core Reliability Baseline

- `feat-037` passes. The canonical D-drive workspace now has fresh Core after-close, market-pulse, market-levels, research-monitor, risk-watch, ai-capex-watch, outcome, and evolve evidence.
- Current private portfolio routing uses ignored `data/portfolio.json`, dated 2026-07-18, with only ????C at about CNY100k / 20%. It intentionally leaves shares, cost, broker price, single-position P&L, and the original risk line empty because the user did not provide them; do not restore the older three-position TSV as current state.
- Fresh after-close artifact `reports/20260719-012054-after-close.*` reports 1/1 structural action coverage and 0/1 strict decision-ready coverage. Missing broker fields render as `未提供`, not zero; optional influencer evidence is separately labelled and does not block Core.
- Weekend market-pulse no longer waits indefinitely for AmazingData. `reports/20260719-011009-market-pulse.*` completed with explicit upstream/public-fallback gaps. Market-levels no longer crashes when a timeframe has no qualifying support zone; `reports/20260719-011118-market-levels.*` completed across all six timeframes.
- Research and outcome artifacts are fresh, but only 15 1d and 6 5d samples have matured, so do not claim calibrated predictive edge or stable compounding.
- Next feature is `feat-044`: automatically discover official IR changes and bind 中际 gross margin, operating cash flow, inventory, receivables, and disclosed 800G/1.6T realization to the existing supplier gate. Keep research evidence read-only and subordinate to `risk-watch`.

## 2026-07-19 Handoff - feat-045 State-team ETF proxy

- `feat-045` passes. `market-pulse` now carries a state-team ETF-share table in JSON/Markdown/HTML using four CSI 300 ETF histories, dated Huijin annual-report holdings, public source links, and three 2023 baselines.
- Fresh artifact `reports/20260719-151119-market-pulse.*` is current through 2026-07-17: 462.74亿 current units, 2069.34亿 disclosed Huijin units at 2025 year-end, and a provable minimum 1606.59亿-unit exit (77.64%).
- The formula is deliberately one-sided and conservative. It cannot establish cash net selling, the destination of in-kind redemptions, underlying-stock disposal, or the status of all 2015 CSF/Huijin direct holdings.
- Verification passed: 48 full tests, compileall, JSON and static report checks, real CLI output, regenerated architecture, 23/23 project-memory validation, harness 100/100, and diff checks.
- Resume `feat-044` unless the user explicitly reprioritizes. A future 2015 rescue-book tracker should start only after the 2026 interim-report shareholder set is complete and should remain separate from the ETF-unit proxy.

## 2026-07-19 Handoff - feat-046 Recurring state-team delta monitor

- `feat-046` passes. `market-pulse` now exposes aggregate and per-ETF 1/5/20-observation changes plus lower-bound tightening and mixed-horizon classification.
- Fresh `reports/20260719-153523-market-pulse.*` reports +17.88% over five observations but -33.38% over twenty; the correct product wording is short-term replenishment inside a still-contracting medium window, not continued daily state-team selling.
- The ACTIVE workday 16:20 `insightradar` automation now runs risk-watch, market-pulse, and ai-capex-watch, compares prior artifacts, and preserves the attribution and no-trade guardrails.
- The full five-workflow product run succeeded. Verification passed with 50 tests, compileall, report/automation assertions, architecture regeneration, project-memory validation, harness 100/100, and diff checks.
- Highest-value next integration: make `after-close` consume the three native monitor payloads and make `evolve` aware of features after feat-027. Current next feature remains feat-044 until the user chooses between source ingestion and Core synthesis.

## 2026-07-19 Handoff - feat-047 Unified next-session decision layer

- `feat-047` passes. `after-close` now consumes the latest risk-watch, market-pulse state-team proxy, and ai-capex-watch artifacts through `stock_assist/unified_decision.py` and exposes a structured `unified_decision` in JSON plus matching Markdown/HTML.
- Fresh `reports/20260719-181600-after-close.*` is the current decision surface for 2026-07-20: defensive observation, no added high beta, preferentially use a rebound below 1187.29 to reduce about one quarter and move high beta from 20% toward 15%, do not panic-sell an untriggered open, reduce one quarter below 950.08 or on clear sector weakness, and treat a confirmed reclaim as hold-only until risk and supplier-realization gates unlock.
- HTML visual QA passed from `reports/20260719-181030-after-close.png`: the first screen shows the unified four-card plan, red risk budget, one CNY100k holding, and unknown P&L as NA rather than zero.
- The ACTIVE workday 16:20 `insightradar` automation now runs risk-watch, market-pulse, ai-capex-watch, then after-close and leads with the unified plan. It remains read-only and cannot trade.
- Verification passed with 8 focused and 54 full tests, compileall, real CLI output, static JSON/Markdown/HTML checks, architecture regeneration, project-memory validation, harness 100/100, automation TOML assertions, and diff checks.
- Next documented feature remains `feat-044` official-IR discovery. The most urgent governance follow-up is repairing `evolve`, which still only recognizes capabilities through feat-027.

## 2026-07-19 Handoff - feat-048 Market regime cockpit and local broker import

- `feat-048` passes. `after-close` now consumes `market-levels` and exposes `market_regime`, `market_levels`, and `tomorrow_watchlist` in JSON, Markdown, and the first-screen HTML cockpit.
- Fresh `reports/20260719-184801-after-close.*` is the current 2026-07-20 decision surface: bear-bull 2.0/10, fear-greed 28/100, crowding 52/100; Shanghai support 3742.07-3770.09, first confirmation 3789.96-3826.16, stronger resistance 3863.12-3913.11, and daily repair 3943.56-3980.25.
- The HTML has three labelled gauges, a state ladder, and a local-only broker TSV import modal. Saving requires a user gesture and the report explicitly requires an `after-close` rerun; the automation cannot use this UI or modify holdings.
- Verification passed with 10 focused and 56 full tests, compileall, live output, inline-JS/static report checks, architecture regeneration, JSON/project-memory validation, harness 100/100, automation assertions, and diff checks. Direct in-app `file://` visual automation remains policy-blocked and was not bypassed.
- Next documented feature remains `feat-044`. Highest-value product follow-ups are composite calibration/history, a reliable pre-open basis/breadth refresh, and repairing `evolve` capability discovery beyond feat-027.
- Portfolio import does not update `data/risk_watch_profile.json`; keep this visible until a typed portfolio-risk adapter can synchronize total/high-beta exposure from explicit user classifications.

## 2026-07-19 Handoff - feat-049 Fixed-anchor breadth and index-divergence cockpit

- `feat-049` passes. `risk-watch` now fetches a complete paginated 同花顺问财 A-share cross-section against 2024-09-24, requires listing-date eligibility and provider-adjusted interval returns, and fails closed on incomplete coverage.
- Fresh `reports/20260719-192028-risk-watch.*` and `reports/20260719-192054-after-close.*` return 5538 unique rows, exclude 230 post-anchor listings and 9 missing listing dates, and cover 5299/5299 eligible stocks. Only 925, 17.46%, are below the anchor, so the same-method “3900 stocks” claim is not supported. Median-stock equivalent Shanghai is 3845.54; arithmetic equal-weight equivalent is 5060.68 versus official 3764.15.
- The after-close first screen now carries `market_structure`, a fourth cumulative anchor-width gauge, and a width/divergence panel. It explicitly separates the 78/100 long-anchor position from the current red risk and 2.0/10 bear-bull short-cycle diagnosis.
- Source/coverage guardrails are durable: equivalent points are not official indexes; current free-float weighting is not historical point contribution; incomplete pagination or coverage cannot validate the viral count or authorize trades.
- Next documented feature remains `feat-044`. For market structure, the next useful increment is daily archival/calibration and a reliable pre-open breadth refresh.

## 2026-07-19 Handoff - feat-050/051/052 Core P0 decision closure

- All three explicitly reprioritized Core P0 features pass. `after-close` now uses a persisted candidate/formal score state machine, typed market-level stance/budget effects, an auditable rule ledger, red-risk veto, and a first-screen four-window operator timeline. The formal score changes only at the close checkpoint and remains capped at ±1 per market day.
- `portfolio-import` is a loopback-only preview/approval workflow with validation, old/new diff, explicit beta class, fail-closed risk reconciliation, timestamped backups, atomic replacement, rollback, five sequential Core refreshes, and report reopening. It has no trading API. Board-lot calculation never exceeds requested/available shares and returns zero/manual choice for targets below one 100-share lot.
- `style-rotation` uses fixed technology, large-financial, high-dividend, and CSI 300 proxies with 5/20/60 relative strength, breadth, MA participation, approximate turnover, persistence, conflicts, and source coverage. The current 2026-07-17 result is `信号冲突`: large financials lead and technology weakens, but three sessions plus weak breadth/turnover and missing earnings confirmation cannot prove a lasting switch.
- Final decision artifact is `reports/20260719-203143-after-close.*`: formal 2.0, candidate 2.0, `support_testing` inside 3742.07-3770.09, `RISK_VETO`, defensive observation, holding count 0, strict readiness 0%. `data/portfolio.json` is empty/invalid; the older broker TSV was previewed read-only but not adopted because the user did not approve it and weights/beta classes are unknown.
- Verification passed: 80 tests, compileall, configs/feature JSON, fresh sequential real workflows, final after-close smoke, artifact assertions, generated architecture with 25/25 command coverage, project-memory validation, harness 100/100, desktop 1440x900 visual inspection, exact 390px no-overflow CDP check, and diff checks. `init.sh` itself cannot run through PowerShell's WSL-routed `bash`; its Windows-equivalent commands passed directly.
- No Git commit or push was created. Resume `feat-044` only if the user does not reprioritize; do not claim a calibrated score/style edge or executable holding quantities until history and approved portfolio inputs exist.

## 2026-07-19 Handoff - feat-053 Guarded Iwencai futures-basis close adapter

- `feat-053` passes. `market-pulse` now gets completed-close IF/IH/IC/IM basis from a project-owned Iwencai OpenAPI adapter before the existing live-session AmazingData fallback.
- The adapter first resolves one shared spot close date, then requests every CFFEX contract for that date, drops zero-open-interest expiry rows, and selects the nearest two active contracts per family. No contract month is hard-coded.
- Final `reports/20260719-212631-market-pulse.*` has eight 2026-07-17 rows for 2608/2609 with basis, basis rate, volume, open interest and available daily open-interest change. All four families are in discount; this remains descriptive, not a standalone bearish authorization.
- Completed-close rows deliberately have no four-minute basis change. The report's first action is diagnostic-only and retains missing long/short seats and historical basis percentile as explicit gaps.
- Latest backend audit contains eight error-free `同花顺问财 OpenAPI close snapshot` rows. Secret-redaction assertions passed; provider details remain out of normal report cards.
- Verification passed: seven focused tests, full 85-test suite, compileall, config/feature/architecture JSON, real CLI generation, artifact/secret/audit assertions, architecture regeneration, project-memory validation, harness validation and diff checks. Browser QA found no console/desktop overflow; 390px kept page width bounded and the basis table horizontally scrollable inside its own container.
- Commit is created in this session after final governance validation. Next documented feature remains `feat-044`; do not treat the one-day close reconciliation as cross-platform/cloud production readiness.

## 2026-07-19 Handoff - Personal investment decision-intelligence design

- The user approved the final North Star: InsightRadar is a personal A-share investment decision-intelligence system that turns fragmented evidence into relevant, auditable, conditional guidance and key alerts, then reviews later outcomes.
- Holdings remain primary. With no or sparse approved holdings, the product may produce zero to five transparent observation candidates; zero is valid, and each candidate requires rationale, trigger, invalidation, horizon, risk, and later benchmark-relative review.
- `Alpha Report` is a delivery family rather than the mission. Scheduled briefs, event-driven alerts, dashboards, archives, and interactive answers must share the same evidence, relevance, uncertainty, and outcome contracts.
- Fast-news discovery, including Jin10, cannot directly authorize action. Critical claims require primary-source confirmation, new-versus-cumulative classification, relevance mapping, counter-evidence, and a decision-impact check.
- Multi-agent roles are temporary templates under one lead. Only one evidence-backed product experiment may be active, with at most two queued; read-heavy discovery can be parallel, but repository writes are serialized and independently verified.
- Durable sources: `docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md`, ADR-0009, `docs/product-charter.md`, and `docs/product-benchmark.md`.
- No implementation feature was activated by the design. After user review of the committed spec, create a separate implementation plan before reprioritizing `feat-044`.

## 2026-07-19 Handoff - Agent-governance execution deferred

- The user selected execution option 1: `superpowers:subagent-driven-development`, with the root Codex agent acting as lead and integrator.
- Execution is explicitly deferred. No child agent was spawned, no implementation file changed, and `feat-054` was not added to or activated in `feature_list.json`.
- The committed execution source is `docs/superpowers/plans/2026-07-19-agent-governed-product-iteration.md` at commit `eee1093`.
- On an explicit resume request, read the canonical English design and this plan, then begin Task 1. Keep one lead plus at most three read-only task agents, serialize repository writes through the lead, and independently verify before completion.
- Until that resume request, retain the current feature state and continue to treat `feat-044` as the documented next product feature; unrelated analysis may proceed without starting the implementation plan.

## 2026-07-20 Handoff - feat-055 Jin10 event-intelligence design

- The user approved the recommended independent event-intelligence architecture: `Jin10 discovery -> normalized event -> classification/deduplication -> primary-source verification -> portfolio/market relevance -> impact assessment -> report or key alert`.
- `feat-055` is registered as pending and queued behind `feat-044`. The current next feature and expansion-freeze order are unchanged; no product implementation or automation started.
- Canonical English AI guidance is `docs/superpowers/specs/2026-07-20-jin10-event-intelligence-design.md`; the adjacent `.zh-CN.md` file is the non-normative Chinese human-review copy.
- The global Codex MCP setup is verified development evidence, not an InsightRadar runtime dependency. Future implementation must own protocol `2025-11-25`, structuredContent-first parsing, cursor pagination, sanitized error handling, bounded reconnect, and external `JIN10_MCP_TOKEN` secret access.
- The design uses the 2026-07-19 China Reform Holdings and China Chengtong disclosures as cumulative-versus-incremental acceptance cases and generic “国家队” sports/industry results as false-positive cases.
- Jin10 is discovery-only: material events require primary-source confirmation, holdings-first relevance, positive and counter-transmission paths, risk/plan impact, explicit gaps, and no standalone trade authority.
- After the user reviews the committed spec, invoke `superpowers:writing-plans` before any implementation. Do not resume the deferred multi-agent execution plan unless the user separately requests it.
- The user subsequently confirmed the spec and added Jin10's repeated important-news compilations as digest reconciliation checkpoints. Live MCP inspection found only `content/time/title/url` item fields and no structured red/highlight/importance metadata, so digest child events may recover misses but APP red state remains an explicit unknown; never infer it from presentation.
- The implementation plan is `docs/superpowers/plans/2026-07-20-jin10-event-intelligence.md`. It remains queued behind `feat-044`; execute it only after explicit reprioritization, preferably with subagent-driven development and serialized repository writes. No implementation or agent dispatch started.

## 2026-07-21 Handoff - Agent Harness engineering and job-readiness design

- The user chose the Agent Harness R&D / Engineering target and approved the recommended six-to-eight-week dual-delivery strategy: InsightRadar remains the private OPC product and real-task proving ground; stable generic components and sanitized evidence are extracted into the public working project `EvidenceHarness`.
- The approved architecture treats Codex, Claude Code, or another compatible agent as a replaceable backend. InsightRadar owns product governance, task/context/memory/tool contracts, trace, checkpoint/recovery, privacy export, deterministic evaluation, and adoption gates rather than building a new model runtime.
- The initial benchmark has 20 to 30 private/sanitized tasks and four profiles: no project Harness, root instructions only, current InsightRadar Harness, and the improved Harness. Context, memory, checkpoint, and bounded multi-agent strategies require preregistered safety, quality, recovery, and cost gates.
- Critical unauthorized investment actions, privacy leaks, unauthorized writes, and false completion must remain zero. Harness experiments run in shadow mode and cannot change formal Core investment workflows until their gates pass.
- Canonical specification: `docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md`; Chinese review copy: the adjacent `.zh-CN.md` file.
- The user approved reprioritizing this program ahead of `feat-044`, but written-spec review remains the gate before implementation planning. `feat-054` is not registered or activated yet; current feature state remains unchanged for now.
- On written-spec approval, invoke `superpowers:writing-plans`, create a revised implementation plan that supersedes the governance-only plan where necessary, then register `feat-054` immediately before implementation and update `CURRENT_STATE.md` consistently. Do not start code before that review.
- The user subsequently approved the committed written specification but explicitly deferred both implementation planning and execution. This supersedes the prior automatic next-step wording: do not invoke `writing-plans`, register `feat-054`, dispatch agents, or change code until a new explicit resume request.
- The user then explicitly resumed the Agent Harness project for planning. The current execution source is `docs/superpowers/plans/2026-07-21-agent-harness-bootstrap.md`; it supersedes the 2026-07-19 governance-only plan where scopes differ. Planning is complete, but `feat-054` remains unregistered/inactive and no implementation agent or code change may start until the user chooses an execution approach.

## 2026-07-21 Handoff - `feat-054` Agent Harness bootstrap complete

- `feat-054` is complete. Fresh closeout evidence is `reports/20260721-232226-agents.md`, `reports/20260721-233536-evolution.md`, `reports/20260721-232237-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t152237z`; the independent verifier returned PASS with no findings.
- The lead remains the sole workspace writer. At most three project-scoped read-only, non-recursive task agents may run when justified; they cannot delegate, write, approve experiments, or grant trade authority.
- Versioned task, trace, privacy, failure, and goal-bound checkpoint contracts now exist, including standard credential-pattern rejection. The deterministic smoke makes no model call and proves contract behavior only; behavioral or model-performance improvement is not yet proven.
- `feat-056` is pending as the sole queued experiment and requires its own written implementation plan before a five-task pilot or benchmark run. Do not start it automatically.
- `feat-044` and `feat-055` remain pending outside the Harness queue and are not authorized to jump ahead of the resumed Harness program.

## 2026-07-21 Handoff - `feat-054` final hardening active

- Final whole-branch review reopened `feat-054` to repair all three Important and three Minor contract findings. Treat the prior PASS and artifacts as historical until focused/full verification and a fresh independent verifier pass.
- Keep `feat-054` as the next work and sole active implementation. `feat-056` remains pending and the sole queued Harness experiment; do not plan, implement, or run its benchmark yet.

## 2026-07-21 Handoff - `feat-054` hardening ready for fresh verifier

- Review fixes are implemented in `0e584e0`, `53224ac`, and `b13a105`: executable smoke budgets/artifacts/acceptance, shared fail-closed public validation and bounded reads, exact six-identity sole-writer roster, truthful runtime/product/architecture inputs, and current normative design state.
- Full discovery is 184/184 PASS. Compileall, agent-contract validation, project-memory validation, Harness 100/100, actual `agents`, `evolve`, and `harness-smoke`, plus UTF-8 JSON/Markdown/hash inspection pass.
- Fresh evidence: `reports/20260722-003048-agents.md`, `reports/20260722-003056-evolution.md`, `reports/20260722-003101-harness-smoke.md`, and ignored `data/harness_eval/runs/smoke-20260721t163101z` with 13 events and trace SHA-256 `30c5fb449688ce6b43e8ff530349b2975537154961236f982d81c2075452f7b5`.
- `feat-054` intentionally remains `in_progress`; next action is a fresh independent read-only whole-branch verifier. `feat-056` remains pending and sole queued, with no pilot or benchmark started.

## 2026-07-22 Handoff - `feat-054` follow-up fixes ready for fresh verifier

- Commit `8479be6` closes the second review's two Important and two Minor findings. V1 now rejects `exit_code` because the in-process smoke cannot observe a separate process result; it retains executable file/text checks, exact artifacts, budgets, trace, checkpoint, and transactional publication. This is an intentional deviation from the historical plan example, whose history remains unchanged.
- Public validation rejects punctuation-embedded Windows/UNC/POSIX paths with marker-free errors and no run residue. Clause-aware scanning accepts negated safety and ordinary slash prose, rejects positive/granted or double-negated trade actions, and keeps credential/private/reasoning/raw-conversation cases closed.
- Focused 90/90 and full 188/188 tests pass. Compileall, agent contracts, project memory, Harness 100/100, actual `agents`/`evolve`/`harness-smoke`, adversarial CLI probes, and UTF-8 JSON/Markdown/hash inspection pass.
- Fresh evidence: `reports/20260722-005149-agents.md`, `reports/20260722-005155-evolution.md`, `reports/20260722-005159-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t165159z` with trace SHA-256 `7c088a19e9753ad835362bf1641b043c778f623ba69f27e5744c2cba8ae53c06`.
- `CURRENT_STATE.md` is dated `2026-07-22`; `feat-054` remains `in_progress` and next, while `feat-056` remains pending and sole queued. Next action is a fresh independent read-only whole-branch verifier, not the benchmark.

## 2026-07-22 Handoff - `feat-054` deterministic parser fixes ready for verifier

- Commit `676479a` replaces ad-hoc public path/trade regexes with bounded deterministic scanners: drive/UNC/POSIX path tokens are recognized after punctuation, and trade clauses use explicit safety-cue parity before each action.
- Requested TDD matrices pass for numeric POSIX, numeric/IPv4 slash-UNC, punctuation, safe spaced slash prose, odd safety cues, even/reversed negation, plain positive orders, Chinese positive actions, and existing credential/private/reasoning cases.
- Focused 90/90 and fresh full 188/188 tests pass. Compileall, agent contracts, project memory, Harness 100/100, actual adversarial CLI probes, canonical `agents`/`evolve`/`harness-smoke`, and UTF-8 JSON/Markdown/hash inspection pass.
- Fresh evidence is `reports/20260722-011257-agents.md`, `reports/20260722-011257-evolution.md`, `reports/20260722-011258-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t171258z` with trace SHA-256 `2a807d9af8659210d4feefc2d53e51ede5134a3a688c238faea73b532fa147b1`.
- `CURRENT_STATE.md` remains dated `2026-07-22`; `feat-054` remains `in_progress` and next, and `feat-056` remains pending and sole queued. The next action is a fresh independent read-only whole-branch verdict, not benchmark execution.

## 2026-07-22 Handoff - `feat-054` final parser corrections ready for verifier

- Commit `359a2f6` closes the final parser review findings with ordered non-overlapping Chinese safety-cue tokens, bounded standalone `不`, Chinese odd/even parity for `买入`/`卖出`/`下单`/`交易`, and exact benign English compound exclusions for `buy-side`, `sell-side`, and noun `buy-in`.
- Loader and CLI TDD matrices reject Chinese reverse/double negations and positive actions while preserving single-cue safety prose, the canonical `交易权限：none` label, and the three explicit English compounds. `buy-now`, `sell-now`, and plain actions still reject.
- Focused 91/91 and fresh full 189/189 tests pass. Python 3.10 parsing, compileall, agent contracts, project memory, Harness 100/100, external marker/no-residue CLI verification, canonical `agents`/`evolve`/`harness-smoke`, and UTF-8 JSON/Markdown/hash inspection pass.
- Fresh evidence is `reports/20260722-012926-agents.md`, `reports/20260722-012927-evolution.md`, `reports/20260722-012928-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t172928z` with trace SHA-256 `bec7b4541efb7a83c4108869b072faa91cb5f40aea6b52601bae11f5459064a1`.
- `CURRENT_STATE.md` remains dated `2026-07-22`; `feat-054` remains `in_progress` and next, and `feat-056` remains pending and sole queued. Next action is a new independent read-only whole-branch verdict, not benchmark execution.

## 2026-07-22 Handoff - adjacent Chinese cue parity ready for verifier

- Commit `1c08681` counts every adjacent standalone `不` exactly once after longest-first non-overlapping multi-cue matching in the single bounded prefix scan.
- One/three-cue goals load and two/four-cue `买入`/`卖出`/`下单`/`交易` actions reject; focused 91/91 and full 189/189 tests plus Python 3.10 parsing, compileall, validators, Harness 100/100, and external marker/no-residue CLI verification pass.
- Fresh evidence is `reports/20260722-014043-agents.md`, `reports/20260722-014044-evolution.md`, `reports/20260722-014044-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t174044z` with trace SHA-256 `51050c943deb5e0180c05a4448441c926e5aaa6c7440890e0eb44993d2149c9d`.
- `feat-054` remains `in_progress`/next and dated `2026-07-22`; `feat-056` remains pending and sole queued. Request a fresh independent read-only verdict; do not start the benchmark.

## 2026-07-22 Handoff - final verifier fixes ready for independent verdict

- Commit `4544fb3` closes the latest verifier's three Important and one Minor findings: action-local English/Chinese conjunction clauses, exact none/no/disabled authority declarations plus `submit order`, Unicode-adjacent absolute paths, v1 public-only trace privacy, and the writer-side 64-event cap.
- Focused 93/93 and full 191/191 tests pass. Python 3.10 parsing, compileall, agent contracts, project memory, Harness 100/100, and external marker-free/no-residue CLI probes pass.
- Fresh evidence is `reports/20260722-021236-agents.md`, `reports/20260722-021237-evolution.md`, `reports/20260722-021237-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t181237z`; it has 13 monotonic public events, final pass, zero pending steps, and matching trace SHA-256 `b7746054b6ac0a0fd22f69fa85a0bcd094e39b60faa861378cbe3b8578686a3a`.
- `CURRENT_STATE.md` remains dated `2026-07-22` with `feat-054` `in_progress` and next. `feat-056` remains pending and sole queued. Request a fresh independent read-only whole-branch verdict; do not start the pilot or benchmark.

## 2026-07-22 Handoff - authority suffix bypass fixed

- Commit `93b2a5b` moves explicit authority validation ahead of general clause splitting and requires each complete sentence-bounded declaration value to be one exact safe enum. This closes all English/Chinese conjunction and comma suffix forms, extra words, and safe+unsafe multiple declarations while adding Chinese exact values `无`/`没有`/`禁用`.
- Reviewer 13/13, exact-safe, multiple-declaration, and CLI no-residue matrices pass. Focused 95/95 and full 193/193 tests, Python 3.10 parse, compileall, agent contracts, project memory, Harness 100/100, and real external English/Chinese marker-free probes pass.
- Fresh evidence is `reports/20260722-022905-agents.md`, `reports/20260722-022906-evolution.md`, `reports/20260722-022906-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t182906z`; it has 13 public events, final pass, zero pending steps, and matching trace SHA-256 `15735887855e36a5679718e14c4d0eb16170a62df7f27443ddfbbd80b9686bb2`.
- `CURRENT_STATE.md` remains dated `2026-07-22`; `feat-054` remains `in_progress` and next pending a new independent read-only verdict. `feat-056` remains pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 Handoff - semicolon suffix bypass fixed

- Commit `4b85b32` keeps `;`/`；` inside complete authority declaration values until a true period/question/exclamation/newline/end boundary. English/Chinese single and repeated semicolon suffixes now reject, while genuine new sentences/newlines and non-authority clause splitting retain their intended behavior.
- Focused 96/96 and full 194/194 tests, Python 3.10 parse, compileall, agent contracts, project memory, Harness 100/100, and real external English/Chinese marker-free no-residue probes pass.
- Fresh evidence is `reports/20260722-023845-agents.md`, `reports/20260722-023845-evolution.md`, `reports/20260722-023846-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t183846z`; it has 13 public events, final pass, zero pending steps, and matching trace SHA-256 `b8f39de6ed8cb3d3c4de84a7a6a9adcefe54841d227392886c1be018626a000b`.
- `CURRENT_STATE.md` remains dated `2026-07-22`; `feat-054` remains `in_progress`/next pending a new independent verdict. `feat-056` remains pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 Handoff - structural public v1 ready for verifier

- Commit `781429e` replaces free-form cue-parity/authority parsing with structural fail-closed v1. PUBLIC/SANITIZED title/goal reject any trade-action/authority lexeme; all public strings reject sensitive assignments and holdings/account/broker/cost/risk/conversation/reasoning material; only the fixed structured `交易权限：none` acceptance remains approved.
- PUBLIC project inputs use the bounded allowlist `.codex/agents/`, `configs/`, `docs/`, `stock_assist/`, `tests/`, and exact safe root state files. PRIVATE retains bounded local refs; SANITIZED still requires verified transformation evidence.
- RED exposed 76 policy misses and the `.codex` reference gap. GREEN passes focused 91/91, full 193/193, Python 3.10 parse, compileall, agent contracts, project memory, Harness 100/100, and three real external marker-free/no-residue probes.
- Fresh evidence is `reports/20260722-030739-agents.md`, `reports/20260722-030746-evolution.md`, `reports/20260722-030747-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t190747z`; the run has three files, 13 public events, final pass, zero pending steps, and matching trace SHA-256 `9c7aa263d5ba4c18dea3975a4d781fb55ba350a8ff2bef83da3224d67e4c8427`.
- `CURRENT_STATE.md` stays dated `2026-07-22`; `feat-054` stays `in_progress`/next pending a fresh independent read-only whole-branch verdict. `feat-056` stays pending and sole queued; do not start pilot or benchmark work.

## 2026-07-22 Handoff - English inflection follow-up ready for verifier

- Commit `4fead97` fixes the Important common-inflection bypass with complete ASCII word tokenization and an explicit bounded US/UK inflection set; no broad prefix matching was added. Hyphen compounds reject, `traditional`/`orderly`/`inventory` remain safe, and `authorised`/`authority-free` reject.
- RED produced 73 failures. GREEN passes focused 93/93 and full 195/195; all 34 reviewer forms separately exit 1 through the real CLI with empty stdout, marker-free stderr, no output directory, and no probe residue. Python 3.10 parse, compileall, agent contracts, project memory, and Harness 100/100 pass.
- Fresh evidence is `reports/20260722-032055-agents.md`, `reports/20260722-032056-evolution.md`, `reports/20260722-032057-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t192056z`; it has three files, 13 public events, final pass, zero pending steps, and trace SHA-256 `9161fe76eeb9408cbacdf16c548bef00a1ebba5bcf37c0a7646e0d03ce5b7c8a`.
- `CURRENT_STATE.md` stays dated `2026-07-22`; `feat-054` stays `in_progress`/next pending a fresh independent verdict, and `feat-056` stays pending and sole queued. No pilot or benchmark work started.

## 2026-07-22 Handoff - final Minor corrections ready for verifier

- Commit `f2693b6` shares the 64-event capacity between trace and checkpoint validation without a circular import. Checkpoint sequences 0/64 save and load; 65/1,000,000 reject on both paths. The structural plan now has exactly one terminal LF, and full-range `git diff --check` passes.
- Focused 94/94, full 196/196, Python 3.10 parse, compileall, agent contracts, project memory, and Harness 100/100 pass. Fresh evidence is `reports/20260722-033837-agents.md`, `reports/20260722-033838-evolution.md`, `reports/20260722-033838-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t193838z` with 13 events, checkpoint sequence 13, final pass, zero pending steps, and trace SHA-256 `067e2c5d7335fa07ec9f4f59c8f7ae11baf05db04b32676ee096614abcd39e24`.
- `CURRENT_STATE.md` stays dated `2026-07-22`; `feat-054` stays `in_progress`/next pending a fresh independent verdict, and `feat-056` stays pending and sole queued. No pilot or benchmark work started.

## 2026-07-22 Handoff - `feat-054` closed after ultimate PASS

- Ultimate independent read-only review at `d115e2e` returned PASS with Critical/Important/Minor `0/0/0`. `feat-054` is closed `pass`; `feat-056` is pending next and remains the sole queued Harness experiment, while active experiments remain empty.
- Status-transition RED exposed two stale integration assertions for final-hardening/`feat-054`-next state. The minimal GREEN contract update now asserts the normative PASS status, `feat-054=pass`, and `next_feature_id=feat-056`; no runtime behavior changed.
- Final verification passes focused `111/111`, full `196/196`, Python 3.10 parsing, compileall, agent contracts, project memory, Harness `100/100`, state/governance assertions, final evolution markers, and current/full-range diff checks.
- Final evidence is `reports/20260722-034028-agents.md`, `reports/20260722-035031-evolution.md`, `reports/20260722-034029-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t194029z`; the run has exactly three files, 13 sequential public events, checkpoint sequence 13, final pass, zero pending steps, all four fixed report assertions, and trace SHA-256 `08b5c8cfb1ffd2d779ebe71e6b019f421bb8871607e8f0cf99d3c15abb57b217`.
- No runtime, model/provider/network, investment, or trade-authority work was added during status closeout; only the stale state-contract assertions changed. Next action is to write the separate `feat-056` plan; do not start its pilot or benchmark automatically.

## 2026-07-23 Handoff - feat-057 macro-transmission shadow activated

- The user explicitly reprioritized the approved macro-transmission shadow ahead of `feat-056` and chose single-agent inline execution.
- `feat-057` is the sole active experiment in isolated branch `codex/feat-057-macro-transmission-shadow`; `feat-056` remains pending and queued.
- Canonical design: `docs/superpowers/specs/2026-07-23-energy-tech-hbm-shadow-design.md`.
- Execution plan: `docs/superpowers/plans/2026-07-23-macro-transmission-shadow.md`.
- Baseline before product-code changes: 197/197 tests passed. Continue Task 1 with strict TDD; the layer remains diagnostic-only and cannot affect risk budgets or trade authority.

## 2026-07-22 Handoff - Windows merge portability verified

- During local integration, the main CRLF checkout failed the generated-architecture digest gate while the LF feature worktree passed at the same commit. The root cause was raw-byte hashing of a text source, not stale architecture content.
- Regression coverage now proves LF/CRLF digest equivalence and normalizes checkout newlines when comparing the tracked HTML while still requiring renderer output to be LF. The renderer and validator share the same newline-canonical digest helper. Fresh serial verification passes 197/197 tests, both project validators, and Harness 100/100.
- `feat-054` remains closed `pass`; `feat-056` remains pending next and sole queued. Finish the local merge/cleanup only after the merged main checkout repeats these checks successfully; do not start the pilot automatically.

## 2026-07-23 Handoff - feat-057 macro-transmission shadow PASS

- `feat-057` is complete on `codex/feat-057-macro-transmission-shadow`. It adds three independent diagnostic macro states, primary-event validation, point-in-time replay/calibration, source/as-of/gap evidence, and JSON/Markdown/HTML rendering inside existing `risk-watch`.
- Non-interference is executable: the macro payload never enters risk scoring, budgets, actions, alerts, event alerts, strict readiness, or trade authority. Oil-only stays observation; promotion remains blocked below 60 independent episodes or without held-out evidence.
- Verification passes 218/218 tests, compileall, JSON validation, project-memory validation, generated architecture parity, and Harness 100/100.
- Real evidence is `reports/20260723-150747-risk-watch.{json,md,html}`. It has `diagnostic_only` authority and clickable sources, but Yahoo SP500/QQQ timed out, so only 5/7 macro series were available, event count is 0, calibration is `insufficient_events`, and the 2026 causal thesis is not confirmed.
- `feat-056` is restored as pending next and remains the sole queued experiment. Its pilot/benchmark has not started; begin only from its separate approved plan.

## 2026-07-23 Handoff - feat-058 after-close decision workbench activated

- The user approved `docs/superpowers/specs/2026-07-23-after-close-decision-workbench-design.md` and chose single-agent inline execution of `docs/superpowers/plans/2026-07-23-after-close-decision-workbench.md`.
- Work is isolated on `codex/feat-058-after-close-decision-workbench`; `feat-058` is the sole active experiment and `feat-056` remains pending and queued.
- Preserve the timestamp-aligned JSON/Markdown/HTML triplet. The new HTML is market-first with Today, Holdings, Market, Research, and Review routes, but diagnostic market context cannot change risk budget or trade authority.
- Clean baseline: Harness integration 15/15 and macro-transmission workflow 4/4 tests passed before feature changes.

## 2026-07-23 Handoff - feat-058 ready for manual UX acceptance

- Production code is implemented through commit `a9ccc46` plus the final key-level usability correction in the working tree. The `after-close` CLI now writes the market-first five-route workbench while preserving the timestamp-aligned JSON and Markdown.
- Representative canonical-portfolio artifact: `reports/20260723-203853-after-close.html` with matching JSON/Markdown. It contains three holdings and three conditional plans, two semantic market groups, explicit freshness, and diagnostic-only authority.
- Fresh verification: 232/232 full tests, compileall, project-memory validation, architecture parity, and Harness smoke 8/8 pass. Static report QA passes all five routes, action/level/research order, three key-level labels, mobile CSS, holding jumps, raw-provider sanitization, and internal-state hiding.
- Automated visual QA is blocked only by the in-app Browser's `file://` security policy; its instructions prohibit working around this with localhost or another browser. The user must open the report manually and confirm desktop/mobile usability.
- The user explicitly chose single-agent execution, so no independent read-only reviewer was spawned. Keep `feat-058` active and do not mark PASS until manual UX acceptance is recorded. `feat-056` remains pending and queued.

## 2026-07-24 Handoff - feat-058 Windows one-click entrypoints

- The user reported that the product had no application/script entry and that portfolio import depended on asking an agent. This was confirmed: the root had no clickable launcher and `.venv\Scripts\python.exe` remains absent.
- Direct global-Python `after-close` also exceeded 60 seconds. A faulthandler stack showed sequential Yahoo TLS waits in `fetch_global_market_groups`; the eight best-effort public snapshots now execute concurrently while retaining deterministic output order and explicit failure gaps.
- Root launchers are `InsightRadar.cmd`, `生成盘后报告.cmd`, `导入持仓.cmd`, and `打开最新报告.cmd`, backed by `scripts/insightradar-launcher.ps1`. They resolve a Python that can import the product, show failures, verify fresh output, open reports, and expose the existing token-protected loopback portfolio importer.
- Real launcher verification completed in about 15 seconds and produced `reports/20260724-170655-after-close.{json,md,html}`. Focused entrypoint, importer contract, and global-market concurrency tests pass. Keep `feat-058` in progress until user visual acceptance.
- The project `.venv` was rebuilt from local Python 3.13 AmazingData/tgw wheels and editable dependencies. AmazingData doctor passes; the real launcher now selects `.venv`, completes in 19 seconds, and produces `reports/20260724-171413-after-close.*`. Full discovery passes 237/237.
- The latest report has 3/3 structural actions, 0/3 strict readiness, and five explicit gaps. The remaining user action is to use `导入持仓.cmd` with a current broker snapshot, complete weights and beta classes, and fill missing position context; do not describe the current blocked reconciliation as trade-ready.

## 2026-07-24 Handoff - loopback importer app live, approval pending

- Root cause of the browser `ERR_CONNECTION_REFUSED` was no listener on `127.0.0.1:8765`; the static report cannot start a Windows process. `InsightRadar.cmd` now starts/reuses the loopback app directly, and reports explain that lifecycle.
- The app now has readable differences, per-holding beta dropdowns, approval-gated save/refresh, latest-report serving, and token-protected shutdown. The user's four holdings are pasted and previewed in the live page, but all beta values remain `unknown`; no approval or write occurred.
- Focused tests and live HTTP/browser QA pass. The user must choose beta classes or deliberately keep them unknown, review the removal of the prior China Life row, then personally check approval and save.

## 2026-07-24 Handoff - 08:30 decision-loop V1 approved

- The owner approved `docs/superpowers/specs/2026-07-24-0830-decision-loop-v1-design.md` after a product grilling session. This is a delivery refinement, not a North-Star change: InsightRadar remains personal A-share decision intelligence with the `Observe -> Explain -> Decide -> Verify` loop and no automated trading.
- The V1 wedge is a local single-user 08:30 plan-confirmation flow: preserve the prior confirmed plan, apply overnight US and early Japan/Korea changes, show zero to three machine-testable IF-THEN decisions, obtain lightweight confirmation, and review strategy quality separately from execution quality.
- Rules retain authority; inexpensive AI may extract and explain new unstructured evidence, with JSON reuse keyed by evidence/rule/prompt/model versions. Unchanged evidence must not repeat AI calls. Five-minute continuous alerts, Redis/MySQL, hosted multi-user delivery, and AI action authority stay deferred.
- This document does not implement the new runtime or close `feat-058`. Preserve the current workbench, launchers, importer, JSON/Markdown contracts, and rollback path. A separate bounded implementation plan and the outstanding current desktop/mobile UX acceptance are still required.

## 2026-07-24 Handoff - selected action-brief prototype ready for owner inspection

- The owner selected visual direction 1 and approved the refined palette: blue-black default, warm-white primary actions, restrained vermilion for A-share positive movement/highest priority/invalidation, amber for waiting or insufficient evidence, and cool blue for freshness/neutral confirmation/A-share decline.
- The exact visual target is `.superpowers/brainstorm/0830-decision-loop-v1/selected-action-brief-blue-red.png`; the implemented four-route fixed-data prototype is `.superpowers/brainstorm/0830-decision-loop-v1/today-prototype.html`.
- Fresh browser evidence covers Today, Holdings, Stock Lookup, and Review at 1440x1024 plus 390x844. All four routes have no horizontal overflow; confirm-all, evidence drawer, holdings filter, stock lookup, and review detail interactions passed. The side-by-side source/implementation comparison and iteration captures are under `audit-2026-07-24/`.
- `design-qa.md` says `final result: passed`. Keep the local port-8890 preview running and leave the Today route open for owner inspection.
- Do not close `feat-058` from this prototype alone. It remains fixed and sanitized; the next bounded step after owner acceptance is a runtime integration plan that preserves the current JSON/Markdown/HTML triplet, importer approval gates, explicit unknowns, and rollback path.

## 2026-07-24 Handoff - decision-response and AI-hardware temperature refinement verified

- The active prototype remains `.superpowers/brainstorm/0830-decision-loop-v1/today-prototype.html`; keep the local port-8890 preview available for owner inspection.
- Today now supports accept/dispute/reject/defer. Structured objections keep the rule draft and user reason separate; batch accept touches only unhandled plans. Only accepted plans attach to the labelled V2 alert preview, and that preview is not a real five-minute runtime.
- Stock Lookup shows the Shanghai Composite as a market-risk gate beside the board benchmark. Review exposes backtest readiness without invented returns. The secondary `theme` route shows the nine-ETF AI-hardware basket, unified median trend, 35 floor, 80 ceiling, and a low-temperature-plus-confirmation rule contract.
- Fresh browser QA covered 1280 desktop and 390x844 mobile with no horizontal overflow. Objection save, accepted-plan alert attachment, theme navigation/chart, all task routes, and empty browser diagnostics passed.
- `feat-058` stays `in_progress`. The next bounded implementation step, after owner feedback, is to design the runtime plan/version contract and persistence schema before building any real intraday polling or notification delivery.

## 2026-07-25 Handoff - P0 runtime integration awaiting owner acceptance

- Execute no P1/P2 work until the owner accepts P0. The working acceptance entry is the loopback app at `http://127.0.0.1:8765/#today`; the static evidence triplet is `reports/20260725-000005-after-close.{json,md,html}`.
- P0 adds `stock_assist/decision_workspace.py`, the four-route renderer, loopback workspace/response/morning APIs, an approval-gated portfolio-import subflow, atomic response JSONL, quiet content-addressed plan history, and source-report-scoped morning runtime state.
- The latest real workspace has four positions, three visible changes, six source-health entries, zero simulated sources, and an explicitly unimplemented P2 monitor. Research and Review are truthful P0 read-only surfaces; the P1 orchestrator/history center is not present.
- Fresh verification passes compileall, 247/247 tests, project-memory validation, four responsive browser sizes, interaction checks, source/implementation comparisons, and empty final browser diagnostics. `design-qa.md` records the P0 comparison history and `final result: passed`.
- Keep `feat-058` `in_progress` until the owner accepts the stage. If accepted, record acceptance before planning P1; do not imply that morning restage fetches fresh market data or that intraday monitoring exists.

## 2026-07-25 Handoff - strict V3 runtime match ready for acceptance

- Acceptance entry: `http://127.0.0.1:8765/`. Latest static triplet: `reports/20260725-003439-after-close.{json,md,html}`.
- The supplied `InsightRadar-重构原型-v3.html` is now the visual authority. The live P0 runtime matches its blue-black four-task shell, route ids (`today`, `portfolio`, `lookup`, `review`), hierarchy, data drawer, and responsive behavior.
- Prototype-only values and its simulated technical chart were not copied. The runtime renders four real positions, three current plan changes, six typed source-health rows, zero simulated rows, and an explicit P1 boundary where real technical/research data is not yet wired.
- Same-viewport reference comparisons, route screenshots, and mobile evidence are under `tmp/v3-strict-match/`; `design-qa.md` ends with the current authority and `final result: passed`.
- Keep the loopback app running for owner inspection. Do not start P1 research/history or P2 five-minute alerts until P0 acceptance is recorded.

## 2026-07-25 Handoff - final P0 repair ready for acceptance

- Acceptance artifact: `reports/20260725-010125-after-close.html`, with matching JSON/Markdown retained as canonical generation evidence.
- Today now contains exactly the pending actionable plans. Current real state is four positions, four active blocked plans, three pending cards, and pending ????D included; ????A remains version-matched `deferred`.
- Blocked versions have no accept action in HTML or the loopback API. `确认已知悉阻断` records audit state only and cannot enter the effective-plan or monitor handoff.
- Same-version/same-rule cards show an execution-only blocked transition; first and genuinely revised versions keep separate labels.
- Verification: 250/250 full tests, compileall, four frozen routes exercised, zero browser runtime errors, and zero console errors. Do not start P1/P2; wait for owner acceptance before recording `InsightRadar V3.0 Pilot — Scope Frozen`.

## 2026-07-25 Handoff - Scope Frozen ten-run Pilot active

- P0 owner acceptance is recorded. Current version: **InsightRadar V3.0 Pilot — Scope Frozen**.
- `feat-058` remains the sole active experiment for ten consecutive real morning trials, not for further feature expansion.
- Only admit reproducible data errors, plan mismatches, state-persistence failures, security issues, or core-flow blockers. Add regression coverage and preserve the frozen four pages and authority boundary.
- Record ordinary experience suggestions without implementing them. Do not start P1 research/backtest orchestration or P2 five-minute alerts before the consolidated review after trial ten.
- Trial and review protocol: `review-package/13-Scope-Frozen与10次试用协议.md`. Durable decision: ADR-0010.

## 2026-07-25 Handoff - sanitized public V3 baseline

- The active delivery remains **InsightRadar V3.0 Pilot — Scope Frozen**. No runtime source or test was changed for the publication pass, and V3.1 implementation remains out of scope.
- New public-baseline documents are `docs/PRODUCT_BASELINE.md`, `docs/V3.0_FROZEN.md`, `docs/V3.1_DELTA.md`, `docs/DECISION_LOG.md`, `docs/ARCHITECTURE.md`, and `docs/DATA_BOUNDARIES.md`. ADR-0011 records the fresh-public-history decision.
- Current verification passes dependency check, compileall, project-memory validation, 250/250 tests, isolated package build, real `after-close`, loopback HTTP security checks, and browser switching across Today, Portfolio, Lookup, and Review with no console errors.
- Audit-only Ruff and Mypy checks remain red with 301 and 377 findings respectively. Treat these as existing technical debt; do not perform a broad cleanup during the frozen pilot.
- Keep all real holdings, account state, generated reports, runtime ledgers, cookies, tokens, raw screenshots, databases, and caches local. The fresh real artifact `reports/20260725-160125-after-close.*` is verification evidence only and must not be published.
- The public repository must start from a fresh sanitized history. Retain the 98-commit legacy history locally; do not force-push, rewrite, or publish it.

## 2026-07-30 Handoff - risk-card workbench branch ready for owner review

- Branch: `codex/risk-card-workbench`. This is an owner-requested implementation of a private local prototype, not an implicit V3.0 baseline promotion.
- Acceptance used a loopback-only service and a private local report triplet; neither runtime data nor raw captures belong in the public repository.
- Today now follows the latest action-command hierarchy while retaining the production decision-workspace contract and version-scoped response API.
- Review now follows the latest decision-value layout but blocks the curve and attribution until the required account, execution, point-in-time proxy, and no-action-baseline evidence exists. Current evidence strength is correctly based on matured T+20 decision episodes.
- Portfolio and Lookup were intentionally preserved. The product still has exactly four first-level routes and no trade authority.
- Visual comparison, responsive evidence, interaction coverage, and final diagnostics are recorded in `design-qa.md`; its latest section ends with `final result: passed`.
- Pre-existing uncommitted unified-decision null-contract repair and CNInfo files were preserved and not folded into this implementation. Wait for owner visual acceptance before merging or changing the frozen-version documents.

## 2026-07-30 Handoff - P0 repair ready for owner re-review

- Branch: `codex/risk-card-workbench`. The latest verified artifact and local QA entry remain private and loopback-only.
- Today now distinguishes pending responses from unresolved blocked attention. All four acknowledged blocked plans remain visible, the primary branch is `继续等待`, and Portfolio shows four items requiring attention instead of a false zero.
- Blockers are attached per plan unless genuinely portfolio-wide. Authoritative source timestamps remain separate from report generation time. An incompatible historical price basis is visibly quarantined from Review and excluded from all outcome aggregates.
- Review has no fake interaction: comparison and horizon buttons are disabled until the required series exists; decision value, drawdown, execution, and baseline fields remain `unknown` or `blocked`.
- Verification is green: 42 focused tests, 260/260 full tests, compileall, project-memory validation, JSON validation, diff check, desktop/mobile browser QA, empty browser warning/error log, and final source/runtime comparisons in `design-qa.md`.
- Independent product re-audit returned PASS after verifying that a quarantined record is retained only as quarantine evidence and no longer affects tracked, matured, hit-rate, average-effect, or ordinary latest rows.
- Keep `feat-058` `in_progress` until owner re-review. P1/P2, public deployment, automatic execution, and frozen-scope expansion remain out of scope.
- Raw CNInfo query artifacts remain private and ignored. The earlier unified-decision null-contract fix is part of the now-verified source/test files.

## 2026-07-30 Handoff - decision service and restartable refresh ready for owner re-review

- Branch: `codex/risk-card-workbench`. The implementation plan, technical-decision repair, and latest private artifact were verified locally.
- The active holding state is no longer the repair branch. Synthetic regression fixtures prove that the current card can say `降低仓位复核`, with its next confirmation derived from prior completed-bar structure while cost remains explanation-only.
- The Today conclusion now combines market risk, market levels, AI-capex transmission, and style rotation with explicit confidence and counter-evidence. Each holding has stable, plan-linked technical evidence with source time and gaps; source availability remains in a separate repair drawer.
- Portfolio import saves atomically before returning HTTP 202. The SQLite-backed single-flight coordinator persists refresh runs/steps/source snapshots/evidence/plan versions/user responses and serially includes `ai-capex-watch` before the final `after-close`. It now requires a new parseable artifact per step plus a same-stem final triplet whose embedded `portfolio_version` matches the refresh-start snapshot.
- Real browser QA verified non-blocking progress, duplicate-refresh prevention, one-time automatic reload, persistent failed/interrupted visibility, and a completed one-step stale refresh bound to the exact private artifact. An anomalous provider series is quarantined because it contains an undeclared large one-bar discontinuity. Keep `feat-058` in progress until owner acceptance; do not add automatic execution, a fifth route, hosted multi-user infrastructure, P1, or P2.
- Keep raw CNInfo query artifacts private and ignored.

## 2026-08-01 Handoff - IR-001 passed; IR-002 live shadow is next

- Product position is now “A股盘前/盘中风险与机会雷达，叠加持仓与候选逻辑记忆” under ADR-0012. Keep exactly four first-level route ids and no automatic trade execution.
- Acceptance artifacts are an ignored local IR-001 JSON/Markdown/HTML triplet. The private case, account-linked values, report names, and all minute archives must not enter a public commit.
- Replay facts: 255 point-time snapshots, zero no-lookahead violations, a 40-60% human-confirmed risk-reduction range near 09:25, catalyst yellow/orange/red escalation, software/robot confirmation only after structure gates, and price-only re-entry blocking.
- Strategy facts: bounded opening reduction improved profit protection versus full hold, while unconditional re-entry failed. Exact account-linked values stay in the private report; `improvement_vs_actual` is null until real broker executions are supplied.
- Restart commands: double-click `盘中雷达.cmd` for one live refresh plus the loopback four-page app, or use `.venv\Scripts\python -m stock_assist.cli intraday-replay` for the offline acceptance case and `.venv\Scripts\python -m stock_assist.cli intraday-poll --iterations 1` for the CLI live path. Do not enable notifications yet.
- Verified gates: focused 7/7, full 290/290, compileall, report assertions, architecture regeneration, and project-memory validation. Rerun the narrow checks after any threshold or provider change.
- Known next gaps: replace scenario external mapping with a verified point-time source; collect multiple 09:25/09:35/10:00 shadow sessions; measure alert timing/false escalation/missed protection; keep actual operations unknown until broker evidence exists.
