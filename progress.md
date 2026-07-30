# Session Progress Log

## Update - 2026-07-09 19:02 Asia/Shanghai

- [x] Added `feat-026 - Actionable after-close playbook`.
- [x] Replaced vague holding guidance such as `趋势未给出强动作信号` with execution-oriented next-day playbooks.
- [x] Extended `HoldingSignal` with:
  - `position_action`;
  - `upside_trigger`;
  - `downside_trigger`;
  - `flat_trigger`;
  - `priority`.
- [x] Updated generated Markdown and JSON payload actions so each current holding includes a concrete next-day condition set.
- [x] Kept AI usage as an optional later layer: facts and triggers are deterministic first; AI can later polish wording without inventing data.
- [x] Updated after-close harness standard.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-190126-after-close.json`, `.md`, and `.html`
- Payload check confirmed 3 actions with `position_action`, `upside_trigger`, `downside_trigger`, `flat_trigger`, and `priority`.
- Generated Markdown contains 0 occurrences of `趋势未给出强动作信号`.
- Examples:
  - ????C -> `高仓位持有，优先降集中度`;
  - ????D -> `持有，保护浮盈`.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-190220-evolution.md` with `feat-026` pass.

### Recommended Next Step

Improve the HTML presentation of the playbook fields: make each position card show a compact decision strip with `仓位动作 / 上行 / 下行 / 震荡 / 优先级`, instead of burying these fields as ordinary bullet text.

## Update - 2026-07-09 18:40 Asia/Shanghai

- [x] Added `feat-025 - Manual broker portfolio input`.
- [x] Added support for private `data/portfolio.manual.tsv` as the easiest manual holdings input.
- [x] Added tracked template `data/portfolio.manual.example.tsv`.
- [x] Loader priority is now:
  - `data/portfolio.json`;
  - `data/portfolio.manual.tsv`;
  - `data/portfolio.galaxy.tsv`.
- [x] The manual broker parser:
  - supports the copied Chinese broker table header;
  - uses `当前持仓` as the true current position;
  - falls back to `股票余额` only when `当前持仓` is absent;
  - ignores rows where `当前持仓=0`, preventing same-day sold rows from becoming false holdings;
  - computes missing weights from market value when broker weight is 0.
- [x] Wrote the user-provided table to ignored private file `data/portfolio.manual.tsv`.
- [x] Updated README, harness docs, product registry, feature list, and evolve tracking.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- Parser smoke test loaded `data/portfolio.manual.tsv` as 3 holdings: `HOLDING-C.EX`, `688126.SH`, `HOLDING-D.EX`.
- `git status --short --ignored data\portfolio.manual.tsv data\portfolio.manual.example.tsv` confirmed:
  - `data/portfolio.manual.tsv` is ignored private runtime data;
  - `data/portfolio.manual.example.tsv` is trackable template data.
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-183940-after-close.json`, `.md`, and `.html`.
- Latest after-close payload has 3 parsed holding actions; sold rows with `当前持仓=0` did not enter current holdings.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-184001-evolution.md` with `feat-025` pass.

### Recommended Next Step

Turn manual portfolio ingestion into a small CLI utility, e.g. `insight-radar portfolio-check`, that validates pasted rows, shows included/excluded positions, and explains why each row was ignored or accepted before running the full report.

## Update - 2026-07-09 18:31 Asia/Shanghai

- [x] Added `feat-024 - After-close payload bridge`.
- [x] Added `stock_assist/report_payload.py` as the shared `insight-payload/v1` envelope helper:
  - common product/schema metadata;
  - Markdown title extraction;
  - Markdown section parsing for native clients;
  - section item extraction for data gaps and action blocks.
- [x] Refactored `market-pulse` to use the shared payload envelope while preserving its existing JSON contract.
- [x] Added `build_after_close_bundle(...)` so `after-close` now emits JSON, Markdown, and HTML with one timestamp.
- [x] Added an `after_close` payload bridge with summary cards, section list, parsed holding actions, and explicit data gaps.
- [x] Updated README, product registry, harness docs, feature list, and evolve tracking.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli after-close` -> `reports/20260709-182917-after-close.json`, `.md`, and `.html`
- After-close payload inspection: `schema_version=insight-payload/v1`, `kind=after_close`, 4 components, 3 summary cards, 14 sections, 5 parsed actions, 1 data gap.
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-183101-market-pulse.json`, `.md`, and `.html`
- Market-pulse payload remained `insight-payload/v1`; visible source-term count remained 0 in Markdown and HTML.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-183121-evolution.md` with `feat-024` pass.

### Current State

- InsightRadar now has two JSON-first product surfaces:
  - Portfolio Intelligence: `after-close`;
  - Market Radar: `market-pulse`.
- HTML is still useful as the current dashboard renderer, but the product contract is no longer trapped inside browser markup.
- The after-close payload is currently a bridge: it preserves Markdown-derived sections and parsed actions rather than a full domain-native position model.

### Recommended Next Plan

1. Promote after-close from Markdown-derived payload to domain-native payload: holdings, risk lines, thesis, peer evidence, filings, events, research deltas, and external viewpoints as typed arrays.
2. Add a validated market-breadth adapter: advancing/declining count, limit-up/down, hot industries,成交额分布, and rotation strength.
3. Add a small local API/server mode (`insight-radar serve`) so Web, desktop shell, and future mobile clients consume the same payloads.
4. Add payload schema tests and golden fixture reports before deeper UI work.

## Update - 2026-07-09 15:52 Asia/Shanghai

- [x] Added `feat-023 - Insight payload contract`.
- [x] Refactored `market-pulse` into a JSON-first product contract:
  - emits `reports/*-market-pulse.json` with `schema_version`, workflow metadata, summary cards, component sections, index/ETF snapshots, futures-basis rows, action rows, data gaps, and backend audit pointer;
  - renders Markdown and HTML from the same payload instead of treating HTML as the primary product surface;
  - keeps visible reports source-light while preserving traceability in `data/market_pulse_sources.jsonl`.
- [x] Added `write_payload_report_triplet(...)` so compatible workflows can write JSON, Markdown, and HTML with one timestamp.
- [x] Updated README and harness docs to document the JSON payload as the future iOS/Android/Windows/Web client contract.
- [x] Registered `feat-023` in the evolve workflow.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-154915-market-pulse.json`, `.md`, and `.html`
- Payload inspection confirmed `schema_version=insight-payload/v1`, 6 components, 4 summary cards, 7 indexes, 5 ETFs, 8 futures-basis rows, 3 action rows, backend-log-only source visibility, and explicit data gaps.
- Local HTML structure check confirmed 16 cards, 2 tables, 8 basis rows, 3 action rows, and 0 visible source terms.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-155319-evolution.md` with `feat-023` pass.
- In-app browser QA was attempted via local `http://127.0.0.1:8765`, but the browser `node_repl` context lost the injected `agent` handle after reset; screenshot/overflow browser QA was not claimed for this increment.

### Recommended Next Step

Extract a small `report_payload` module and move after-close onto the same JSON-first contract, then the HTML dashboard can evolve without locking the product to browser-only output.

## Update - 2026-07-09 13:06 Asia/Shanghai

- [x] Added `feat-022 - Realtime futures-basis pulse`.
- [x] Added IF/IH/IC/IM futures-basis adapter using Galaxy AmazingData:
  - reads CFFEX futures code list;
  - selects the nearest two contracts for each family;
  - queries futures and spot snapshots one code at a time to avoid AmazingData timeout/concurrency issues;
  - aligns futures and spot by common timestamp;
  - computes current basis, basis rate, and 4-minute basis change.
- [x] Upgraded `market-pulse` output with:
  - a Basis conclusion card;
  - an HTML futures-basis table;
  - a conditional action table inspired by intraday basis workflows;
  - Markdown basis lines and action suggestions.
- [x] Kept source labels out of the visible product report; futures-basis source/audit details now append to `data/market_pulse_sources.jsonl`.
- [x] Updated `configs/a_share_pulse.json` and `.example.json` with `basis_lookback_minutes` and `futures_basis_watch`.
- [x] Updated README and harness docs for the verified basis adapter.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-130317-market-pulse.md` and `.html`
- Latest report contains 8 verified IF/IH/IC/IM basis rows and 3 conditional action rows.
- `data/market_pulse_sources.jsonl` appended 8 `futures_basis` audit records.
- Source-text check remained 0 for `source:`, `Galaxy AmazingData`, `Eastmoney`, and `来源` in the generated report.
- Browser QA via local `http://127.0.0.1:8765` confirmed 16 cards, 6 panels, 2 tables, 8 basis rows, 3 action rows, no console errors, and no desktop/mobile horizontal overflow.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-130607-evolution.md` with `feat-022` pass.

### Recommended Next Step

Add market breadth and industry rotation:上涨/下跌家数、涨停/跌停、炸板率、行业涨跌幅，把“期指确认”与“现货广度”合成更可靠的盘中方向判断。

## Update - 2026-07-09 12:56 Asia/Shanghai

- [x] Added `feat-021 - Market pulse source audit log`.
- [x] Removed visible data-source labels from the `market-pulse` Markdown and HTML report.
- [x] Added backend source audit logging to `data/market_pulse_sources.jsonl`:
  - report generation time;
  - workflow/product/config;
  - direction verdict and score;
  - every index/ETF snapshot with code, category, price, update time, source, and error state.
- [x] Updated the A-share market-pulse harness contract so source/fallback details stay in the backend audit log, not in normal report cards.
- [x] Recorded a low-risk local verification regex error in `.learnings/ERRORS.md`.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m stock_assist.cli market-pulse` -> `reports/20260709-125534-market-pulse.md` and `.html`
- `Select-String` found no `source:`, `Galaxy AmazingData`, `Eastmoney`, or `来源` text in the generated market-pulse report.
- `data/market_pulse_sources.jsonl` appended 12 traceable snapshot source records.
- Local HTML check counted 16 cards, 6 panel-class blocks, and 0 visible source terms.
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-125622-evolution.md` with `feat-021` pass.
- In-app browser `file://` QA was blocked by browser security policy, so visual browser verification was not claimed.

### Recommended Next Step

Harden the futures-basis adapter: query IF/IH/IC/IM one contract at a time, cache current-month contract selection, then compute spot-vs-future basis and annualized basis.

## Update - 2026-07-09 12:50 Asia/Shanghai

- [x] Added `feat-020 - A-share live market pulse`.
- [x] Added `market-pulse` CLI workflow for a PPT-style real-time A-share market board.
- [x] Added `stock_assist/data_sources/a_share_market.py`:
  - priority source: Galaxy AmazingData `query_snapshot`;
  - fallback source: Eastmoney public intraday trends.
- [x] Extended `stock_assist/data_sources/xysz.py` with snapshot, future-code-list, ETF share, and ETF PCF methods.
- [x] Added `configs/a_share_pulse.json` and `.example.json` for index, ETF, and futures-basis watch configuration.
- [x] Generated `reports/20260709-125013-market-pulse.md` and `.html` using Galaxy AmazingData for 7 indexes and 5 ETFs.
- [x] Kept futures basis, market breadth, limit-up/down, ETF share/subscription/redemption, premium/discount, and Central Huijin ETF activity as explicit data gaps until the adapters are verified.
- [x] Probed CFFEX future code list successfully, but a combined futures/index snapshot query timed out; recorded the issue in `.learnings/ERRORS.md`.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.venv\Scripts\python -m json.tool configs\a_share_pulse.example.json`
- `.venv\Scripts\python -m stock_assist.cli --help`
- `.venv\Scripts\python -m stock_assist.cli market-pulse`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-125028-evolution.md`
- Browser QA via Codex `node_repl` confirmed 16 cards, 12 Galaxy source rows, 5 panels, no console errors, and no desktop/mobile horizontal overflow.

### Recommended Next Step

Harden the futures-basis adapter: query IF/IH/IC/IM one contract at a time, cache current-month contract selection, then compute spot-vs-future basis and annualized basis.

## Update - 2026-07-09 12:38 Asia/Shanghai

- [x] Added `feat-019 - Source-priority signal queue`.
- [x] Added a Top Signals row before the per-position cards in the after-close HTML:
  - ranks portfolio risk actions, data gaps, research deltas, event risks, and external viewpoints;
  - shows only the 3 highest-priority signals on the first screen;
  - keeps the full Markdown evidence and collapsed HTML evidence archive intact.
- [x] Added resilient section parsing for the priority queue so existing report headings remain compatible.
- [x] Recorded the local Playwright module-resolution issue in `.learnings/ERRORS.md` and verified with the Codex bundled browser runtime instead.
- [x] Updated `docs/harness.md` so future after-close HTML work preserves the top-signal queue.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-123734-evolution.md`
- Generated `reports/20260709-123453-after-close.md` and `reports/20260709-123453-after-close.html`.
- Browser QA via Codex `node_repl` confirmed 3 priority cards, 4 brief cards, 5 decision cards, 5 heat tiles, 14 collapsed evidence sections, no console errors, and no desktop/mobile horizontal overflow.

### Recommended Next Step

Add recommendation aftertest persistence so each Top Signal can later show 1/5/20-trading-day outcome and gradually learn which sources are useful.

## Update - 2026-07-09 12:15 Asia/Shanghai

- [x] Added `feat-018 - Conclusion-first card report`.
- [x] Simplified the after-close HTML into a card-led decision surface:
  - 4 executive brief cards.
  - 5 per-position decision cards.
  - concise action, reason, PnL/day/weight, and risk line for each holding.
  - visual signal/charts retained below the decision cards.
- [x] Collapsed all long evidence sections by default; latest HTML has 14 evidence sections and 0 open on load.
- [x] Updated the after-close harness contract to require conclusion-first cards and collapsed evidence.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-121557-evolution.md`
- Generated `reports/20260709-121513-after-close.md` and `reports/20260709-121513-after-close.html`.
- Playwright QA confirmed 4 brief cards, 5 decision cards, 5 heat tiles, 14 evidence sections, 0 open evidence sections, no console errors, and no desktop/mobile horizontal overflow.

### Recommended Next Step

Add source-priority cards for research deltas and external viewpoints, so the report ranks the 3 highest-impact signals instead of listing every source equally.

## Update - 2026-07-09 12:04 Asia/Shanghai

- [x] Added `feat-017 - Visual intelligence dashboard`.
- [x] Refactored after-close HTML output toward a HyperInsight-style intelligence cockpit: signal cards, action donut, market breadth, KPI cards, position charts, and a position heatmap before evidence text.
- [x] Converted long report sections into collapsible evidence panels; the latest HTML has 14 collapsible sections and only the core holding/action evidence opens by default.
- [x] Preserved Markdown output and all existing evidence text.
- [x] Updated the harness after-close contract so future dashboard work must keep visual-first output and browser overflow checks.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-120542-evolution.md`
- Generated `reports/20260709-120437-after-close.md` and `reports/20260709-120437-after-close.html`.
- Static HTML check confirmed `Intelligence Signals`, `Action Mix`, `Market Breadth`, `Position Heatmap`, and 14 `details.report-section` blocks.
- Playwright QA confirmed 5 heat tiles, 14 collapsible details sections, no console errors, and no desktop/mobile horizontal overflow.

### Recommended Next Step

Move from static charts to richer visual intelligence: add per-holding sparkline history and a source-quality/risk-priority queue for research deltas and external viewpoints.

## Update - 2026-07-09 09:11 Asia/Shanghai

- [x] Added `feat-016 - Product-grade InsightRadar foundation`.
- [x] Added `stock_assist/product.py` as the product registry for modules, CLI workflow ownership, expected inputs/outputs, and file/data classifications.
- [x] Added `product-map` workflow and CLI command, generating `reports/20260709-090959-product-map.md`.
- [x] Updated CLI help to show InsightRadar module boundaries and derive command help from the product registry.
- [x] Added product-level command failure advice: expected inputs, expected outputs, suggested fix, and retry command.
- [x] Updated README around four product modules: Portfolio Intelligence, Research Intelligence, Market Radar, and Product Ops.
- [x] Updated README and `docs/harness.md` to distinguish `product_config`, `private_runtime_data`, `template/schema`, and `generated_output`.
- [x] Updated `evolve` capability status to include `feat-015` and `feat-016`.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli product-map`
- `.venv\Scripts\insight-radar.exe --help`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli evolve` -> `reports/20260709-091145-evolution.md`
- `rg` check confirmed generated reports and CLI/product registry do not use the old product names.

### Recommended Next Step

Promote the product registry into lightweight validators for key configs and local private data: `portfolio_context`, `event_calendar`, `crypto_watchlist`, `research_sources`, and influencer observation streams.

## Update - 2026-07-09 09:05 Asia/Shanghai

- [x] Renamed the user-facing product to `InsightRadar`.
- [x] Added `stock_assist/branding.py` as the single source for product name, slug, legacy slug, tagline, and description.
- [x] Updated README, AGENTS notes, harness notes, CLI description, package metadata, HTML report branding, and architecture view branding.
- [x] Added the new console script alias `insight-radar` while preserving `shenyan-radar`, `stock-assist`, and `python -m stock_assist.cli` compatibility.
- [x] Regenerated `docs/architecture.html` and generated `reports/20260709-090401-after-close.md` / `.html`; both verified to show `InsightRadar` with the `IR` mark.
- [x] Added explicit setuptools package discovery so editable install only packages `stock_assist*`.
- [x] Reinstalled with `.venv\Scripts\python -m pip install -e .`; `.venv\Scripts\insight-radar.exe --help`, `.venv\Scripts\shenyan-radar.exe --help`, and `.venv\Scripts\stock-assist.exe --help` show `InsightRadar`.
- [x] Added and marked `feat-015 - Product rename to InsightRadar` as pass.

### Verification

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

### Recommended Next Step

If `InsightRadar` is final, the next sprint should update the Windows scheduled task name and any external automation prompts from `stock-assist` to `insight-radar` / `InsightRadar`.

## Update - 2026-07-08 23:18 Asia/Shanghai

- [x] Added `feat-014 - Stable research report provider`.
- [x] Promoted `report-cli` to the priority research-report provider while keeping Eastmoney public metadata as fallback.
- [x] Added `report-cli` provider controls to `configs/research_sources.json` and `configs/research_sources.example.json`: watched stock codes, industry codes, and strategy/macro/morning report types.
- [x] Added a curl-based PDF download fallback for Eastmoney PDF URLs; this turns previously blocked report pages into readable PDF bytes when the browser-like curl path succeeds.
- [x] Generated `reports/20260708-231817-research-monitor.md`: `report-cli 93` records, `eastmoney_public 60` records, and 5 matched PDFs extracted with `status=ok`.
- [x] `data/research_deltas.jsonl` now contains full-text-backed `source_status=ok` thesis delta records alongside metadata-only records.

### Verification

- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\research_sources.example.json`
- `.venv\Scripts\python -m json.tool configs\research_sources.json`
- TOML parse check for `pyproject.toml`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli evolve`

### Recommended Next Step

Use the stable report source as the product substrate: add alert rules for new coverage, rating/target-price changes, and conflicts between strategy/macro reports and current holding theses.

## Update - 2026-07-08 22:57 Asia/Shanghai

- [x] Added `feat-012 - Research report monitor`.
- [x] Searched SkillHub for research-report capabilities and recorded the strongest candidates in the generated report: `report-ea`, `report-analysis`, `jrj-fin-search-skill`, and `yanbaoke-research-report-download`.
- [x] Checked GitHub/open-source options and recorded practical references: `manymore13/report-cli`, `lzhttn/EastmoneyCrawler`, and `qingxuantang/eastmoney_parser`.
- [x] Added Eastmoney research-report metadata collection for stock, industry, and strategy/macro reports.
- [x] Added `research-monitor` CLI workflow and formal `configs/research_sources.json`.
- [x] Generated `reports/20260708-225710-research-monitor.md` with report stream, holdings/theme matches, reusable SkillHub/GitHub candidates, and product-gap roadmap.
- [x] Marked `feat-012` pass and generated `reports/20260708-225728-evolution.md`, where the next backlog returned to long-term recommendation aftertest/backtest evaluation.

### Files Added / Modified For feat-012

- `stock_assist/data_sources/eastmoney_reports.py`
- `stock_assist/workflows/research_monitor.py`
- `configs/research_sources.example.json`
- `configs/research_sources.json`
- `stock_assist/cli.py`
- `stock_assist/workflows/evolution.py`
- `feature_list.json`

### Verification

- `.venv\Scripts\python -m json.tool configs\research_sources.example.json`
- `.venv\Scripts\python -m json.tool configs\research_sources.json`
- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli evolve`

### Recommended Next Step

Use this monitor as the collection layer, then connect either SkillHub `report-ea` / `report-analysis` or GitHub `manymore13/report-cli` for PDF download and正文抽取. After that, write each report's `thesis_delta` back into portfolio research memory and add alerts for new coverage, rating changes, target-price changes, and macro/strategy conflicts.

## Update - 2026-07-08 23:06 Asia/Shanghai

- [x] Added `feat-013 - Research report thesis delta`.
- [x] Added `pypdf` to `pyproject.toml` and installed it into `.venv` for best-effort PDF text extraction.
- [x] Added `pdf_url` to Eastmoney research-report metadata.
- [x] `research-monitor` now attempts PDF download and validates the `%PDF` header before parsing; current Eastmoney PDF requests return an anti-bot script page, so the report marks them as `blocked` instead of pretending the正文 was read.
- [x] Added append-only local research memory at `data/research_deltas.jsonl`; current file contains 16 deduped `thesis_delta` records.
- [x] Added a `研报观点变化` section to after-close reports, sourced from `data/research_deltas.jsonl`.
- [x] Generated `reports/20260708-230238-research-monitor.md` with `PDF 正文抽取` and `Thesis Delta` sections.
- [x] Generated `reports/20260708-230607-after-close.md` and `.html` with `研报观点变化`.
- [x] Generated `reports/20260708-230633-evolution.md`; `feat-012` and `feat-013` both show `pass`.

### Verification

- `.venv\Scripts\python -m pip install pypdf`
- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m json.tool configs\research_sources.example.json`
- `.venv\Scripts\python -m json.tool configs\research_sources.json`
- `.venv\Scripts\python -m stock_assist.cli research-monitor`
- `.venv\Scripts\python -m stock_assist.cli after-close`
- `.venv\Scripts\python -m stock_assist.cli evolve`
- `.venv\Scripts\python -m json.tool feature_list.json`
- TOML parse check for `pyproject.toml` using `tomllib`.

### Current Limitation

Eastmoney PDF URLs are discoverable, but direct CLI download currently returns an anti-bot script page rather than a real PDF. The product now records `source_status=blocked` for those attempts and falls back to metadata-based deltas. Next best path for full正文 is to integrate `manymore13/report-cli` or SkillHub `report-ea` if either handles the site challenge better.

## Current State

**Last Updated:** 2026-07-08 22:45 Asia/Shanghai
**Session ID:** codex-stock-assist-external-view-audit
**Active Feature:** feat-011 - External viewpoint evidence audit

## Status

### What's Done

- [x] Installed walkinglabs `harness-creator` skill.
- [x] Removed the unrelated `harness-engineering-pro` skill to keep one harness skill.
- [x] Added project harness docs and feature state for stock-assist.
- [x] Verified core after-close workflow still generates Markdown and HTML reports.
- [x] Raised walkinglabs harness structural validation from 32/100 to 100/100.
- [x] Added replayable portfolio context fields and overlay loading from `data/portfolio_context.json`.
- [x] Added `data/portfolio_context.example.json` with buy thesis, risk lines, adjustment history, horizon, and review status.
- [x] Added a `组合上下文与复盘状态` section to after-close Markdown/HTML reports.
- [x] Added researcher-view planned features: hypothesis tracker, peer comparison evidence layer, and event calendar/filing watchlist.
- [x] Installed SkillHub `hyperliquid` and `crypto-whale-monitor` skills; both installed despite the known PowerShell GBK checkmark print error.
- [x] Added a read-only Hyperliquid data source wrapper for market snapshots and account positions.
- [x] Added `crypto-monitor` CLI workflow and `configs/crypto_watchlist.example.json`.
- [x] Generated a Hyperliquid monitoring report with market overview and explicit missing-address data gap.
- [x] Found and verified the BlockBeats/HyperInsight `0xec4` RWA trader address: `0xec4a6f59960fb55a7fa49262e2628687b322cf62`.
- [x] Updated crypto monitor to support Hyperliquid `dex=xyz` and generated a report showing the matched XYZ100 and BRENTOIL positions.
- [x] Added market anomaly radar for watched `xyz` markets using top-position and liquidation-risk scans, so monitoring remains useful if a known address changes wallets.
- [x] Upgraded `evolve` to read `feature_list.json`, detect local data/config gaps, and generate capability-aware next-sprint backlog.
- [x] Marked `feat-004` pass after compile and fresh evolution report verification.
- [x] Created local ignored `data/portfolio_context.json` for the five current Galaxy holdings, with conservative placeholder buy theses, current risk lines, review status, and adjustment records.
- [x] Extended portfolio context with catalysts, falsification signals, observation windows, and next review dates.
- [x] Added a `研究假设与反证` section to after-close reports and marked `feat-006` pass after verification.
- [x] Added a `同业比较证据` section to after-close reports, covering each current holding's peer group with 5日/20日表现、市值、预告PE and sector anchor.
- [x] Marked `feat-007` pass after compile, after-close report generation, and evolution verification.
- [x] Added best-effort A股/美股/韩国 macro index snapshots via Yahoo chart data.
- [x] Upgraded HTML reports into a dark research dashboard with KPI cards, market cards, and CSS bar charts for positions and PnL.
- [x] Verified the dashboard in the in-app browser via localhost preview: 3 market cards, 3 chart panels, no console errors, no desktop/mobile horizontal overflow.
- [x] Added `configs/event_calendar.example.json` for upcoming events and risk windows.
- [x] Added `事件日历与公告 watchlist` to after-close reports, combining configured upcoming events with CNInfo latest filing monitoring.
- [x] Marked `feat-008` pass after compile, after-close generation, and evolution verification.
- [x] Promoted `configs/event_calendar.example.json` to formal `configs/event_calendar.json`.
- [x] Promoted `configs/crypto_watchlist.example.json` to formal `configs/crypto_watchlist.json`.
- [x] Verified `evolve` now reports `关键本地输入已就绪`.
- [x] Upgraded external viewpoint report lines with source links, source quality, portfolio/peer mapping, verification prompts, and A-share price aftertests.
- [x] Marked `feat-011` pass and verified `evolve` now moves the next backlog to long-term backtest evaluation.

### What's In Progress

- [ ] Replace placeholder buy theses in `data/portfolio_context.json` with the user's real original trade logic.
  - Details: The file exists and is ignored by git, but several buy theses intentionally begin with `待补`.
  - Blockers: Needs user research notes for each holding.

### What's Next

1. Replace placeholder `待补` text in local `data/portfolio_context.json` with the user's real original trade logic.
2. Maintain `configs/event_calendar.json` as real upcoming events change.
3. Next product direction is backtest/evaluation: write each recommendation's later outcome back into evolution reports.
4. For crypto monitoring, copy `configs/crypto_watchlist.example.json` to `configs/crypto_watchlist.json`, adjust addresses/thresholds, then run `.venv\Scripts\python -m stock_assist.cli crypto-monitor`.
5. Treat watched addresses as one signal only; if they go quiet, use the market anomaly radar to identify new large RWA/indice/oil addresses before media reports them.

## Blockers / Risks

- [ ] Windows users may prefer `init.ps1`; walkinglabs validator expects `init.sh`, so both may be useful if this grows.
- [ ] The repo has uncommitted user/project changes predating this harness cleanup; do not stage or revert unrelated files blindly.
- [ ] Real `data/portfolio_context.json` is still missing, so current reports correctly show context gaps and default `needs_context` rows.
- [ ] RWA/HIP-3 monitoring must use the correct Hyperliquid dex (`xyz` for trade.xyz markets); the main dex returns empty positions for this address.

## Decisions Made

- **Keep walkinglabs harness-creator**: It is the course-source skill for creating and auditing project harnesses.
  - Context: The previously installed community skill was a broad execution-discipline method, while walkinglabs provides templates, scripts, and validation.
  - Alternatives considered: Keeping `harness-engineering-pro`; rejected to avoid overlapping harness triggers.

## Files Modified This Session

- `AGENTS.md` - routed future agents to the standard harness files.
- `docs/harness.md` - stock-assist harness guide.
- `feature_list.json` - root-level feature state tracker.
- `progress.md` - restart state and decisions.
- `session-handoff.md` - handoff template/current state.
- `init.sh` - standard verification entrypoint for structural harness checks.
- `stock_assist/portfolio.py` - replayable position context data model and overlay loading.
- `stock_assist/workflows/after_close.py` - context gap checks and report section.
- `data/portfolio_context.example.json` - local context template.
- `README.md` - local data note for replayable portfolio context.
- `stock_assist/data_sources/hyperliquid.py` - read-only Hyperliquid Info API wrapper.
- `stock_assist/workflows/crypto_monitor.py` - crypto monitoring report workflow with market anomaly radar.
- `stock_assist/workflows/evolution.py` - capability-aware backlog generation from feature status and local data gaps.
- `stock_assist/portfolio.py` - research hypothesis fields on holdings.
- `stock_assist/workflows/after_close.py` - `研究假设与反证` report section.
- `stock_assist/workflows/after_close.py` - `同业比较证据` report section with peer 5日/20日表现、市值、预告PE.
- `stock_assist/data_sources/global_markets.py` - A股/美股/韩国 index snapshots for macro context.
- `stock_assist/reports.py` - dark research dashboard HTML renderer with KPI cards, market cards, and CSS bar charts.
- `stock_assist/workflows/after_close.py` - `跨市场宏观温度` report section.
- `configs/event_calendar.example.json` - example upcoming event calendar.
- `configs/event_calendar.json` - formal upcoming event calendar used by after-close reports.
- `configs/crypto_watchlist.json` - formal crypto monitoring watchlist used by `crypto-monitor`.
- `stock_assist/workflows/after_close.py` - `事件日历与公告 watchlist` report section.
- `stock_assist/workflows/after_close.py` - external viewpoint evidence audit with source links, mapping, and price aftertests.
- `stock_assist/workflows/evolution.py` - recognizes `feat-011` and shifts next backlog to backtest evaluation.
- `stock_assist/cli.py` - added `crypto-monitor` command.
- `configs/crypto_watchlist.example.json` - example symbols, verified 0xec4 address, dex, alert thresholds, and radar thresholds.
- `feature_list.json` - added `feat-009` status and verification evidence.
- `data/portfolio_context.example.json` - template now includes catalysts, falsification signals, observation window, and next review date.
- `data/portfolio_context.json` - ignored local real context for current holdings; not tracked by git.
- `progress.md` - current session status and next step.

## Evidence of Completion

- [x] Core workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-194022-after-close.md` and `reports/20260708-194022-after-close.html`.
- [x] Compile check: `.venv\Scripts\python -m compileall stock_assist`.
- [x] Harness structural validation: `node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target %USERPROFILE%\Documents\stock-assist` returned 100/100.
- [x] Replayable context workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-195401-after-close.md` and `reports/20260708-195401-after-close.html`.
- [x] Context overlay smoke check: inline Python loaded `data/portfolio_context.example.json` and returned `watch 1`.
- [x] Crypto monitor compile check: `.venv\Scripts\python -m compileall stock_assist`.
- [x] Crypto monitor workflow: `.venv\Scripts\python -m stock_assist.cli crypto-monitor` generated `reports/20260708-215545-crypto-monitor.md`.
- [x] Evolution alignment compile check: `.venv\Scripts\python -m compileall stock_assist`.
- [x] Evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-220226-evolution.md` with `feat-004: pass`, local data gaps, and capability-aware backlog.
- [x] Local context JSON check: `.venv\Scripts\python -m json.tool data\portfolio_context.json`.
- [x] Hypothesis tracker workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-220857-after-close.md` and `.html` with `研究假设与反证`.
- [x] Post-hypothesis evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-220904-evolution.md` with `feat-006: pass`.
- [x] Peer comparison compile check: `.venv\Scripts\python -m compileall stock_assist`.
- [x] Peer comparison workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-221420-after-close.md` and `.html` with `同业比较证据`.
- [x] Post-peer evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-221429-evolution.md` with `feat-007: pass`.
- [x] Dashboard compile check: `.venv\Scripts\python -m compileall stock_assist`.
- [x] Dashboard workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-222957-after-close.md` and `.html`.
- [x] Browser verification: localhost preview confirmed dashboard elements, no console errors, and no horizontal overflow on desktop or 390px mobile viewport.
- [x] Post-dashboard evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-223125-evolution.md` with `feat-010: pass`.
- [x] Event calendar JSON check: `.venv\Scripts\python -m json.tool configs\event_calendar.example.json`.
- [x] Event watchlist workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-223430-after-close.md` and `.html` with `事件日历与公告 watchlist`.
- [x] Post-event evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-223458-evolution.md` with `feat-008: pass`.
- [x] Formal config JSON check: `.venv\Scripts\python -m json.tool configs\event_calendar.json`; `.venv\Scripts\python -m json.tool configs\crypto_watchlist.json`.
- [x] Formal-config after-close workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-223928-after-close.md` and `.html` with no data gaps.
- [x] Formal-config crypto workflow: `.venv\Scripts\python -m stock_assist.cli crypto-monitor` generated `reports/20260708-223944-crypto-monitor.md` using `configs\crypto_watchlist.json`.
- [x] Config-readiness evolve workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-223948-evolution.md` with `关键本地输入已就绪`.
- [x] External-view audit workflow: `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260708-224507-after-close.md` and `.html` with links, mappings, verification prompts, and A-share price aftertests.
- [x] Final evolution workflow: `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260708-224536-evolution.md` with `feat-011: pass` and next backlog `回测评估`.

## Notes for Next Session

Read `AGENTS.md`, `feature_list.json`, and this file first. `feat-004`, `feat-006`, `feat-007`, `feat-008`, `feat-009`, `feat-010`, and `feat-011` are complete. Formal event and crypto configs now exist. Next useful work is long-term evaluation: add backtest/aftertest persistence for recommendations and replace placeholder `待补` trade theses when real notes are available.

## 2026-07-10 - feat-027 Signal outcome ledger

### Changed

- Added `stock_assist/signal_outcomes.py` to import the latest after-close payload per day, deduplicate by signal date and stock code, and persist private `data/signal_outcomes.jsonl` rows.
- Added 1/5/20-session returns, direction-adjusted hit/miss, and 20-session maximum favorable/adverse excursion; immature horizons remain pending.
- Added a signal-outcome scorecard to after-close JSON/Markdown/HTML and to `evolve`.
- Added standard stock codes to payload actions, `data/signal_outcomes.example.jsonl`, and `docs/product-benchmark.md`.

### Verified

- `.venv\Scripts\python -m compileall stock_assist` passed.
- Controlled fake-client smoke verified 1/5/20-session returns of 1%/5%/20%, 20-session hit rate 100%, MFE/MAE, and the as-of boundary.
- `.venv\Scripts\python -m stock_assist.cli after-close` generated `reports/20260710-083803-after-close.json`, `.md`, and `.html`.
- The payload has `outcomes` summary, `signal_outcomes` component, three standard action codes, and the Markdown/HTML scorecard.
- The private ledger contains 6 unique signal ids; all are correctly pending because available AmazingData closes end on 2026-07-09.
- `.venv\Scripts\python -m stock_assist.cli evolve` generated `reports/20260710-083909-evolution.md` with `feat-027: pass`, the same scorecard, and a sample-size-aware next backlog.

### Current State / Next

- `feat-027` is pass. Repeated after-close runs update the same daily stock signal instead of duplicating it.
- Next high-value sprint: after enough 1/5/20-session samples mature, add benchmark-relative portfolio contribution and outcome-calibrated alerts while always displaying sample size.

## 2026-07-10 - feat-028 Native Windows discipline reminder

### Changed

- Added a dependency-free WinForms tray app under `windows/InsightRadar.DisciplineReminder`.
- The app starts silently at Windows logon, stays resident without Codex, shows a topmost red banner only during the configured weekday 09:10-15:05 session, and reinforces it every five minutes.
- Added tray actions for immediate display, 30-minute pause, config editing, and exit; the banner supports acknowledgement and 10-minute snooze.
- Added `configs/trading_discipline.json`, native build/install/uninstall scripts, local acknowledgement logging, and user documentation.

### Verified

- `powershell -ExecutionPolicy Bypass -File scripts\install-discipline-reminder.ps1` built the native EXE and registered `InsightRadar-DisciplineReminder` as an interactive `AtLogOn` task.
- Task state is `Running`; the resident process has no visible window after 15:05.
- A controlled `--show-now` probe found a visible 2560-pixel-wide banner titled `InsightRadar · 个人交易纪律（不是市场定律）`.
- `python -m json.tool configs\trading_discipline.json` passed.

### Current State / Next

- The reminder is installed and currently resident in the Windows system tray.
- Exchange holidays are not inferred; on a weekday holiday, pause or exit from the tray.
- Edit `configs/trading_discipline.json` to change rules, hours, sound, or frequency, then restart the tray app.

### 2026-07-10 Rule expansion

- Replaced the fixed headline with `10点前不交易｜大涨次日高开、平开一定卖｜满仓猛干一定死`.
- Consolidated the user's full rule list into 24 rotating reminders ordered by risk importance: highest discipline, exit/risk warnings, planned entries, structure/emotion checks, then low-priority market aphorisms.
- Restarted the resident task and verified the new headline in `data/discipline_reminder_log.jsonl`; task state returned to `Running` with one resident process.
- Hardened visibility for trading software: while visible, the banner now reapplies native `HWND_TOPMOST` every two seconds with `SWP_NOACTIVATE`, so it rises above ordinary/topmost windows without stealing keyboard focus.
- Added offline Windows SAPI speech. The app reads the configurable core discipline at session start and every five minutes, and the tray menu can immediately read the core plus the currently displayed rule.
- Resolved the rule conflict: before 10:00, new buys/adds/T are prohibited while preplanned reductions remain mandatory.
- Blocked tray snooze and exit during the configured trading session, and configured Task Scheduler to restart crashes every minute up to 10 times.

### 2026-07-12 DPI-safe banner layout

- Replaced the fixed percentage-row banner layout with content-measured rows based on the active font, primary-screen width, DPI, and the longest rotating rule.
- Disabled label ellipsis and added button-safe minimum row heights so long rules and both action buttons remain fully visible.
- Kept taskbar visibility limited to explicit `--show-now` review mode; normal login residency remains tray-only.
- `scripts\build-discipline-reminder.ps1` published the updated EXE with zero build warnings or errors and passed config validation.
- Computer-use visual QA captured the 2560px-wide banner and confirmed complete title, primary rule, rotating rule, status text, `我已执行`, and `10分钟后提醒`, with no clipping.
- Restored the registered `InsightRadar-DisciplineReminder` AtLogOn task to normal resident operation after review.

### 2026-07-13 User-controlled close and exit

- Removed the trading-session guards that blocked the 10/30-minute snooze and tray exit actions.
- The banner close button can now always hide the current reminder, and the tray menu can always pause or fully exit the resident app.
- Updated the tray labels and documentation so the UI no longer claims these actions are limited to non-trading hours.
- `powershell -ExecutionPolicy Bypass -File scripts\install-discipline-reminder.ps1` rebuilt and reinstalled the app; config validation passed and the scheduled task returned to `Running`.
- `.venv\Scripts\python -m json.tool feature_list.json` passed.

## 2026-07-14 - feat-029 Multi-timeframe market level indicator

### Changed

- Added the `market-levels` CLI workflow with matching JSON, Markdown, and responsive HTML reports.
- Added resilient Tencent public K-line routing with Eastmoney fallback for monthly, weekly, daily, 60-minute, 15-minute, and 1-minute data; 3-minute bars are aggregated locally from 1-minute bars.
- Added deterministic fractal, alternating-stroke, overlap-center, MACD divergence-candidate, BOLL/MA, rolling-extreme, and Fibonacci analysis.
- Level zones now require at least two distinct evidence families; repeated rolling-window lows count as one family.
- Added `configs/market_levels.json`, an example config, unit tests, README usage, product registry entries, and a Market Levels harness contract.

### Verified

- `.venv\Scripts\python -m unittest tests.test_market_levels` passed 3 tests.
- `.venv\Scripts\python -m compileall stock_assist` passed.
- Both market-level config files passed `json.tool`.
- `.venv\Scripts\python -m stock_assist.cli market-levels` generated `reports/20260714-114930-market-levels.json`, `.md`, and `.html` with all six timeframes and zero data gaps.
- Browser QA confirmed 4 summary cards, 6 timeframe panels, no console errors, and no horizontal overflow at desktop or 390px mobile width.

### Current State / Next

- Current 2026-07-14 11:30 evidence places the nearest 60/15/3-minute support cluster around 3865-3889 and the larger weekly support cluster around 3762-3829; these are conditional zones, not predicted lows.
- Daily and weekly down-strokes remain unconfirmed as finished. The module labels current 15/3-minute bottom divergence only as a candidate and requires reclaim/hold conditions before upgrading the rebound level.
- Next useful extension: persist each daily level map and score later hold/break/reclaim outcomes before tuning cluster tolerances.

### 2026-07-14 Conclusion-first refinement

- Replaced the text-heavy first screen with one explicit conclusion: observed morning low 3869.30, highest 3/15/60-minute confluence zone 3867-3881, midpoint about 3874.
- Reduced the action plan to support hold, 15-minute invalidation, 3/15-minute reclaim confirmation, and the monthly/weekly fallback zone around 3800.
- Added a compact reference-K-line table and collapsed the full six-timeframe calculations by default.
- Explicitly labels the zone as highest current confluence, not a statistically verified high-win-rate signal.
- Fresh artifacts: `reports/20260714-120410-market-levels.json`, `.md`, and `.html`.

## 2026-07-14 - feat-030 Local factor lab

### Changed

- Added `factor-lab`, a local daily cross-sectional research workflow using eight interpretable price/volume factors and a rolling ridge model.
- Labels are future five-session returns relative to CSI 1000; each forecast uses a five-session embargo and at most 252 prior sessions.
- Added MAD winsorization, cross-sectional rank standardization, RankIC, five-bucket returns, VIF/condition number, turnover costs, drawdown, validation gates, current diagnostic ranking, JSON/Markdown/HTML output, config/example, and tests.
- The default 20-stock universe is explicitly labeled a custom pilot and never represented as the official CSI 1000 constituent set.

### Verified

- `.venv\Scripts\python -m unittest tests.test_factor_lab` passed 3 tests.
- `.venv\Scripts\python -m compileall stock_assist` and JSON validation passed.
- `.venv\Scripts\python -m stock_assist.cli factor-lab` generated `reports/20260714-143250-factor-lab.json`, `.md`, and `.html` from real AmazingData daily K-lines.
- The unfinished 2026-07-14 daily bar was removed. The artifact is as of 2026-07-13 and strict JSON/static HTML checks passed.

### Current State / Next

- The first model correctly failed validation: 43 out-of-sample periods, RankIC -0.89%, positive-IC rate 46.5%, average Top-Bottom -0.67%, quintile monotonicity -0.50, and condition number 83.57.
- The apparent +61.5% Top-versus-index cumulative result is not accepted as factor evidence because the custom current universe has survivor/selection bias and its bottom bucket also outperformed.
- Next: obtain dated official CSI 1000 constituent snapshots, add industry/size neutralization and tradability constraints, then rerun nested out-of-sample tests before any paper portfolio.
- In-app visual QA was blocked by the browser local-file policy; static responsive HTML checks passed.

## 2026-07-14 - feat-031 Personal factor-model daily pipeline

### Changed

- Added `factor-pipeline`: a private observation ledger, T+5 label maturation, local Ridge v1 retraining, candidate/champion model registry, deterministic data/model hashes, and hard promotion gates.
- Added idempotent `date + code` upserts, atomic CSV/JSON writes, deduplicated registry records, diagnostic-only rankings when no champion exists, config/example, model schema, tests, and a concise operating document.
- Ridge v1 stores eight raw factors but trains on seven; Amihud is excluded because it duplicates the liquidity factor in the MVP. This reduced actual validation condition number from 84.71 to 20.54 and maximum VIF from 16.19 to 4.31.
- Added a UTF-8 PowerShell runner and an optional weekday 15:40 Task Scheduler installer. The installer is not automatically executed.

### Verified

- Six focused factor-lab/pipeline tests passed; compileall and JSON checks passed.
- Real `factor-pipeline` run generated `reports/20260714-144314-factor-pipeline.json`, `.md`, and `.html`.
- Runtime ledger contains 6,447 rows: 6,347 mature labels and 100 pending rows. Same-data rerun reported `new_rows=0`; model registry versions were not duplicated.
- Candidate `20260713-07d5a907da` failed RankIC, IC-positive-rate, net Top-Bottom, and monotonicity gates, so `champion.json` correctly remains absent.
- PowerShell runner completed and its UTF-8 log contains no NUL bytes.

### Current State / Next

- Local CPU training costs no incremental cloud compute and currently completes in seconds to tens of seconds.
- The pipeline is production-safe as a research data accumulator, but there is deliberately no production scoring model yet.
- Next: acquire dated CSI 1000 constituents plus industry/float-cap exposures, then add neutralization and test factor families separately. Do not tune promotion thresholds to force a champion.

## 2026-07-14 - feat-032 Point-in-time CSI 1000 universe lineage

### Changed

- Added `factor-universe-sync`, AmazingData constituent normalization, atomic membership CSV persistence, and matching JSON/Markdown/HTML audit reports.
- Added PIT half-open interval filtering after lookback-factor calculation, plus universe id/manifest lineage in observations, model hashes, candidate metadata, and model schema v2.
- Kept the existing 20-stock custom pilot backward compatible and added separate CSI 1000 example configs/data directory so old and official-universe samples cannot silently mix.
- Added focused tests for entry/exit dates, pre-entry lookback availability, and cross-universe observation-key isolation.

### Verified

- Nine universe/factor/pipeline tests passed; compileall, JSON checks, static responsive HTML checks, and `git diff --check` passed.
- Real sync generated `reports/20260714-183223-factor-universe.json`, `.md`, and `.html`; private membership contains 3,439 intervals, 2,839 historical codes, exactly 1,000 open intervals, and starts at 2014-10-17.
- Real legacy pipeline migration generated `reports/20260714-183404-factor-pipeline.json`, `.md`, and `.html`; same-data rerun had `new_rows=0`, lineage was `custom_pilot_v1`, and no failed candidate created a champion.
- In-app `file://` visual QA remained blocked by browser policy; no visual pass was claimed. Static responsive structure passed.

### Current State / Next

- Survivor bias is now removable through the separate PIT configuration, but the full CSI 1000 factor run has not been enabled as the default and no model quality claim changed.
- AmazingData index weight/free-float retrieval remains a data gap because an empty recent range triggers an SDK `TRADE_DATE` error.
- Next single feature: add industry and float-market-cap exposures with point-in-time neutralization. Preserve hard gates and keep the custom and CSI 1000 ledgers separate.

## 2026-07-14 - feat-034 Version-controlled project memory

### Changed

- Added bounded root `PROJECT_MEMORY.md` with machine-readable routing metadata and on-demand architecture, product-state, and decision-log topics under `docs/memory/`.
- Added `scripts/validate_project_memory.py` to verify index caps, topic/source existence, source/generated freshness, and complete `ProductCommand` coverage in the architecture graph.
- Wired project memory into `AGENTS.md`, `docs/harness.md`, `init.sh`, and README startup guidance.
- Refreshed `configs/architecture.json` from the current product surface: 18 nodes, five lanes, all 17 registered commands, resident Windows reminder, signal outcome loop, and champion-only factor boundary.
- Rebuilt the interactive HTML renderer with correct Chinese text, adaptive canvas height, desktop sidebars, mobile containment, draggable local layout, and memory/source visibility.

### Verified

- `.venv\Scripts\python -m json.tool configs\architecture.json` passed.
- `.venv\Scripts\python -m compileall stock_assist scripts\validate_project_memory.py` passed.
- The memory validator first failed only because the generated topology was stale, then passed after `.venv\Scripts\python -m stock_assist.cli architecture-view` with 3 topics and command coverage 17/17.
- Harness validation remained 100/100 and `git diff --check` passed.
- In-app browser QA confirmed 18 nodes, five lanes, interactive node selection, no console errors, no replacement characters, desktop sidebar/inspector visibility, and no body-level horizontal overflow at 390px.

### Current State / Next

- The earlier topology was not lost; it had become undiscoverable and stale. It is now a routed, freshness-gated project asset.
- External SkillHub candidates were reviewed, but no new memory skill was installed because the repo-local bounded index solves the portability problem without a second overlapping memory system.
- Resume the user-prioritized `feat-033` next: point-in-time industry/free-float exposure and neutralization diagnostics.

## 2026-07-14 - feat-035 Bounded current state and product continuity charter

### Changed

- Added bounded `CURRENT_STATE.md` so startup context contains the north star, verified baseline, product rings, gaps, and one next feature without loading full chronological history.
- Changed AGENTS/harness startup routing to query exact feature and matching recent history instead of reading all of `feature_list.json`, `progress.md`, and `session-handoff.md`.
- Added `docs/product-charter.md` with the A-share Observe-Explain-Decide-Verify loop, decision-ready holding coverage north-star metric, non-goals, roadmap order, and extraction criteria.
- Added ADR-0001 for bounded repository memory and ADR-0002 for the modular-monolith/product-ring decision.
- Classified all 18 architecture nodes as Core, Lab, Satellite, Extension, or Governance; the generated topology now shows ring labels and validation rejects missing/unknown rings.

### Verified

- `.venv\Scripts\python scripts\validate_project_memory.py` passed with a bounded current-state snapshot, four routed topics, `feat-033` as the valid pending next feature, all five product rings, and 17/17 command coverage.
- `.venv\Scripts\python -m stock_assist.cli architecture-view` regenerated `docs/architecture.html` with the updated source SHA-256.
- Harness validation remained 100/100; compileall, JSON validation, static HTML checks, and `git diff --check` passed.
- SkillHub searches covered persistent memory, session handoff, project memory, context engineering, ADR, modular-monolith, and product-strategy skills. No new framework was installed because it would duplicate the repository source of truth.

### Current State / Next

- The repo is not split into services. It remains a modular monolith with explicit lifecycle rings; the Windows reminder is the only current separately deployed satellite.
- Factor workflows are Lab-only, crypto/X are optional Extensions, and neither can silently drive the A-share core roadmap.
- Resume `feat-033` next. After the reliability layer matures, prioritize portfolio/benchmark attribution and event-to-position alerting before new clients or automated execution.

## 2026-07-14 - feat-036 Standalone discipline-reminder extraction kit

### Changed

- Added a manifest-driven export for the Windows reminder that packages source, personal config, build/install scripts, docs, standalone AGENTS/state/handoff files, and SHA-256 provenance.
- Added a two-phase cutover contract: standalone build first, real Task Scheduler ownership second, original source removal only after a verified launch/logon cycle and rollback.
- Added ADR-0003 and `docs/extractions/README.md`; froze Lab/Extension expansion and parked `feat-033`.
- Reprioritized the next InsightRadar sprint to `feat-037`, a core decision-loop reliability baseline with no new capabilities.

### Verified

- `scripts\export-discipline-reminder.ps1` generated `dist\InsightRadar.DisciplineReminder-extraction` and the matching ZIP with 18 mapped files plus `SOURCE_MANIFEST.json`.
- Isolated `init.ps1` parsed 24 rules and built the .NET 8 Release target with zero warnings and zero errors.
- Every exported SHA-256 hash and required ZIP member passed; the standalone harness scored 100/100.
- The real scheduled task remained `Ready` and still points to the original `stock-assist\dist\InsightRadar.DisciplineReminder` executable. No cutover or uninstall occurred.

### Current State / Next

- The package is ready to open in a memory-free new task. Its only pending feature is `dr-002` standalone cutover and ownership transfer.
- InsightRadar still contains the source as a rollback copy and marks the satellite `extraction_ready`.

## 2026-07-14 - Standalone reminder ownership transfer completed

### Done

- Published and validated the canonical standalone app at `D:\work\reminder`.
- Re-registered `InsightRadar-DisciplineReminder` to the D-drive executable and working directory without renaming the task, assembly, mutex, or product.
- Verified the real D-drive process, visible no-activate banner, complete Chinese copy, acknowledge and 10-minute snooze controls, SAPI speech, and a normal no-argument restart cycle.
- Merged 128 historical `stock-assist` reminder log entries with 10 cutover entries into 138 standalone JSONL records.
- Removed the C-drive intermediate repository and retired all reminder source/config/scripts/docs/export bundles, runtime log, product-file registration, and architecture node from InsightRadar.

### Verification

- D-drive Release build: 0 warnings, 0 errors; published config contains 24 rules.
- Scheduled task: `Running`, AtLogOn, action `D:\work\reminder\dist\InsightRadar.DisciplineReminder\InsightRadar.DisciplineReminder.exe`, working directory `D:\work\reminder`, one matching resident process.
- UI automation captured the banner and exercised `我已执行` plus `10分钟后提醒`; application logs recorded `acknowledged` and `snoozed_10_minutes`.
- Standalone SAPI `--speak-test` returned exit code 0; normal restart restored the resident process with no temporary arguments.

### Next

- Keep all future reminder changes in `D:\work\reminder`. Continue InsightRadar with `feat-037`; the reminder is no longer an in-repository component.
- Next main-repo feature is `feat-037`; factor neutralization, crypto/X improvements, new clients, and automated execution remain parked.

## 2026-07-14 - Canonical InsightRadar workspace migration

### Changed

- Established `D:\work\InsightRadar` as the sole canonical main-project workspace and copied the complete current working tree, including Git metadata, ignored local data, and all uncommitted changes.
- Archived the abandoned `D:\work\stock-assist` checkout under `D:\work\_archive\stock-assist-legacy-20260707` instead of merging its 7 July legacy artifacts into the current product.
- Updated active repository, harness, project-memory, Codex, and automation context to use InsightRadar; retained `stock_assist` and legacy CLI aliases strictly for compatibility.
- Added ADR-0004 so future sessions can distinguish the canonical workspace from historical `stock-assist` references.

### Verified

- Pre-edit migration check matched Git HEAD `9adcf9c45561993cc7de57b2778b71e5461b214c`, all 51 worktree status lines, and a zero-difference Robocopy mirror comparison.
- From `D:\work\InsightRadar`, project-memory validation passed with 17/17 command coverage, harness validation remained 100/100, Python compilation and `git diff --check` passed, `insight-radar --help` worked, and editable package metadata resolved to the D-drive workspace.
- Codex config trusts and opens `D:\work\InsightRadar`; the weekday automation is named `InsightRadar 工作日交易晨报` and its prompt explicitly treats the D-drive path as the only source of truth.
- The independent reminder task was returned to `Running` with exactly one no-argument process from `D:\work\reminder`; its action and working directory were unchanged by the main-project migration.

### Current State / Next

- Continue with `feat-037` after the canonical-path and Codex/automation cutover checks pass.
- Post-restart cleanup replaced `%USERPROFILE%\Documents\Reminder` with a junction to `D:\work\reminder` and deleted every file/directory from the old main checkout. The resumed Codex task still locks the empty main root, so it now contains only a redirecting `AGENTS.md` and migration marker.
- Codex still lists the restored C-drive task entry because the user reopened the old task rather than opening the D-drive folder as a new project. Open `D:\work\InsightRadar`; then replace the two-file C-drive shell with a junction and retarget the weekday automation project id from C to D.

## 2026-07-14 - Workspace migration closeout follow-up

### Changed

- Retargeted the existing `InsightRadar 工作日交易晨报` automation project id and working directory from `%USERPROFILE%\Documents\stock-assist` to `D:\work\InsightRadar` through the Codex automation API.
- Preserved the automation name, active status, weekday 08:00 Asia/Shanghai schedule, model settings, fixed brief structure, conditional trading language, and all other business prompt content.
- Re-inspected the old C-drive compatibility shell: it contained only `AGENTS.md` and `MIGRATED_TO_D_WORK_INSIGHTRADAR.md`, both migration-only notices with no project code, data, Git metadata, or other unique project content. Those two notices were removed normally.

### Verified / Blocked

- Initial repository checks ran from `D:\work\InsightRadar`: `40d119e` is contained in `HEAD` and the Git worktree was clean before closeout edits.
- The standalone reminder remained untouched and externally owned: Task Scheduler was `Running` with action and working directory under `D:\work\reminder`, and exactly one matching resident process was observed.
- The automation TOML now records both `target.project_id` and `cwds` as `D:\work\InsightRadar`; its schedule and business configuration match the pre-change values.
- Immediately before both removal attempts, the source resolved exactly to `%USERPROFILE%\Documents\stock-assist` and the target resolved exactly to `D:\work\InsightRadar`. Windows refused to remove the verified empty source root because another process is using it, including after the automation cutover.
- No forced deletion or unknown-process termination was attempted. The old path remains an empty ordinary directory, not a junction; this is the only unresolved workspace-migration item.
- Project-memory validation passed with 17/17 architecture command coverage; Harness validation passed at 100/100 with no bottleneck; `git diff --check` passed. `CURRENT_STATE.md` remains bounded at 68 lines and 4,880 bytes.

### Next

- Close or identify the external process that owns the empty C-drive root, then remove it normally and create a junction to `D:\work\InsightRadar`. Re-verify the junction, automation target, reminder ownership, and clean Git state before removing this Known Gap.
- Do not start `feat-037` until this migration blocker is cleared; all parked expansion areas remain unchanged.

## 2026-07-14 - Project and product status audit before feat-037

### Reviewed

- Audited the canonical `D:\work\InsightRadar` checkout, bounded project memory, current state, product charter, exact `feat-037` entry, matching recent history, harness contracts, local holdings, latest Core report payloads, and recent commits.
- Measured feature-tracker completion separately from strict current-day decision readiness so historical pass counts do not overstate Core product maturity.

### Verified

- `compileall`, 13 unit tests, project-memory validation, 17/17 architecture command coverage, Harness 100/100, CLI help, feature JSON parsing, `git diff --check`, and a clean pre-audit Git worktree all passed from the D-drive workspace.
- The latest after-close payload contains conditional actions and upside/downside/flat handling for all 3 current holdings, with 1 explicit holding-context gap and 32 external links across the payload.
- Signal outcomes contain 9 tracked signals: 6 matured at 1 day with 1 hit; no 5-day or 20-day sample has matured.

### Findings / Next

- Strict 2026-07-14 post-close decision-ready holding coverage is 0/3 because the newest after-close artifact was generated at 08:41 and its prices stop at 2026-07-13; structural plan coverage remains 3/3.
- The newest market-pulse artifact was generated before the workspace migration and its audit metadata still points to the old C-drive checkout. Treat this as proof that migration-era artifacts cannot close `feat-037`, not as proof of a current runtime dependency.
- Keep `feat-037` pending. First close the old C-drive directory/junction blocker, then serially run the real Core workflows from D, record per-holding coverage/failures/fallbacks, and only then consider attribution, calibration, or parked Lab/Extension work.

## 2026-07-14 - Iwencai SkillHub and portable market-data candidate

### Changed

- Installed the Iwencai SkillHub CLI independently under the user profile without replacing the existing `skillhub.cn` CLI, and added a PowerShell wrapper through the user-local bin directory.
- Installed `hithink-market-query` under `%USERPROFILE%\.codex\skills`; the skill uses Python 3 standard-library HTTPS requests and has no third-party runtime dependency.
- Added a current-user PowerShell profile that loads the CLI path and Iwencai environment variables. The API key value is stored in the Windows current-user environment store, not as plaintext in the profile or repository.
- Added ADR-0005: Iwencai is a cross-platform provider candidate, not a Core dependency before `feat-037` and the portability/reliability gates pass.

### Verified / Risk

- A new PowerShell process loaded `IWENCAI_BASE_URL`, a non-empty 145-character API key, and the Iwencai CLI; the profile contains no literal API-key value.
- A live one-row `hithink-market-query` request for the latest Shanghai Composite price succeeded through `https://openapi.iwencai.com/v1/query2data`.
- The published 0.0.4 outer installer looks for `aime-install.sh`, while its ZIP contains `iwencai-install.sh`; Windows installation therefore mirrored the reviewed inner contract rather than executing the broken wrapper.
- The vendor CLI downloads skills over HTTP and does not verify a published SHA-256. Do not use this distribution path for unattended/cloud production until ADR-0005's supply-chain gate is satisfied.

### Next

- Keep the skill available for manual evaluation only. Close the workspace blocker and complete `feat-037`; then scope a separate portable-provider adapter feature with multi-day reconciliation and macOS ARM/Linux validation.

## 2026-07-14 - Local-first Core value decision

### Decision

- Added ADR-0006 and confirmed that InsightRadar remains local-first. Cloud deployment, production Docker work, WSL/macOS migration, and new client delivery are deferred rather than active roadmap work.
- The product's immediate proof question is whether the Core guidance improves benchmark-relative decision outcomes and can support durable compounding after realistic costs and risk. Win rate remains visible but is not sufficient without expectancy, drawdown, payoff ratio, MFE/MAE, sample size, regime stability, and out-of-sample controls.
- Updated the product charter roadmap so `feat-037` remains first, followed by outcome maturation and controlled replay/backtest validation before attribution, calibration, research restart, or delivery expansion.

### Current State / Next

- No implementation work started. The canonical runtime remains the local Windows checkout at `D:\work\InsightRadar`.
- Tomorrow: close or identify the owner of the old empty C-drive root, create and verify the junction, then begin `feat-037` with fresh real Core artifacts. Keep provider portability and infrastructure parked unless they directly unblock Core evidence.

## 2026-07-15 - feat-038 NGA Great Times monitor (in progress)

### Implemented

- Added a read-only NGA data-source adapter for the confirmed Great Times board `fid=706`.
- Added repository-external Cookie storage at `%LOCALAPPDATA%\InsightRadar\secrets\nga_cookie.txt` with hidden interactive entry through `nga-auth set`; status and clear commands never reveal the Cookie.
- Added `nga-monitor`, snapshot history under ignored `data/nga/`, reply-delta heat ranking, watch-term counts, and an explicitly labeled title-only sentiment proxy.
- Registered the two commands in the product registry and existing public-viewpoint Extension node; Core workflows do not depend on this collector.

### Verification

- `python -m unittest tests.test_nga_monitor` passed 3 tests.
- `python -m compileall stock_assist`, config/architecture JSON checks, CLI help, and `git diff --check` passed.
- Live completion remains pending because browser safety rules prohibit exporting the logged-in browser Cookie. The user must enter it once through the hidden local prompt, then two live captures and recurring automation can be verified.

### Next

- Run `nga-auth set`, then `nga-monitor` twice several minutes apart.
- Verify the parser against live HTML and activate the recurring local automation only after the first live report succeeds.
- Mark `feat-038` pass, return `CURRENT_STATE.md` to pending `feat-037`, and resume the Core reliability baseline.

### Completion

- The user refreshed the repository-external Cookie file; `nga-auth status` returned configured without exposing its contents.
- Two live `nga-monitor` runs parsed 35 topics each. The second snapshot measured real reply deltas (highest +3 in roughly two minutes), and a content scan confirmed neither snapshot contained Cookie fields.
- Created ACTIVE Codex local automation `nga` for workday ten-minute candidate slots. Its prompt gates execution to 09:20-11:40 and 12:55-15:10 Asia/Shanghai, reports authentication/parser failures, alerts on reply/keyword heat, and prohibits posting, reactions, and trading.
- `feat-038` is complete. `feat-037` is restored as the next feature.

### Schedule calibration

- The user preferred daily context over intraday high-frequency monitoring. Automation `nga` was changed from ten-minute candidate slots to workday 08:50 and 15:50 captures.
- A fresh post-change report parsed 35 topics: title proxy bullish 4, bearish 2, neutral 29. Technology/self-reliance discussion led reply growth while investigation, bear-market-stage, and technology-retreat threads showed visible disagreement.
- Manual `nga-monitor` remains available for exceptional event days; normal operation stays twice daily to reduce anti-bot and session risk.
## 2026-07-15 - feat-039 NGA AI daily topic digest

- Added `llm-auth` with repository-external hidden key storage and an OpenAI-compatible client defaulting to the previously validated aiapi.world / gpt-4o-mini contract.
- Added `nga-daily`: it collects current-day NGA JSON topics plus first-page/high-score replies, asks AI once for semantic clusters, validates every cited thread id, and deterministically backfills real links, floors, scores, and excerpts.
- Added explicit rule-based degradation for missing keys, gateway failures, or invalid model output. Live compatibility now accepts list/dict topic containers, Unix timestamps, invalid escapes, and per-thread truncated JSON fallback.
- Live final report `reports/20260715-212002-nga-daily.*` collected 24 topics and produced 5 AI clusters with `gpt-4o-mini-2024-07-18`; the formal call used 8,182 tokens.
- Updated ACTIVE automation `nga`: 08:50 runs `nga-monitor` without AI; 15:50 runs `nga-daily --llm` once.

### Codex-native automation calibration

- The user identified the external API call as redundant because the scheduled task already runs on Codex. The ACTIVE automation now runs `nga-daily` without `--llm` at 15:50 and uses its own `gpt-5.4` model with medium reasoning to synthesize the evidence.
- Inspected benchmark thread `https://bbs.nga.cn/read.php?tid=47185220` through the authenticated NGA JSON interface. Its five-section contract was encoded in the automation prompt: core conflict, competing explanations, claimed catalysts and invalidation, emotion transition, participant/flow split, implicit judgment, 4-6 real related topics, and up to 3 real high-score replies.
- The prompt explicitly bans generic filler and any invented market facts, causes, thread ids, scores, or quotations. External aiapi usage is now parked and remains manual opt-in only for later tuning.
- Raised the after-close detail pool from 24 to the full 35-topic board page so five themes can each cite 4-6 real threads without padding; collection frequency remains once after close.
## 2026-07-15 - feat-040 NGA time-window report acceptance

- Added explicit `morning` (00:00-09:00) and `day` (00:00-15:59) windows, including reply-level filtering and matching `nga-morning` / `nga-daily` artifacts.
- Added multi-page metadata discovery because late retrospective runs push daytime topics beyond the first three pages. Morning scans five pages and selects 20 details; day scans ten pages and selects 35 details.
- Live rapid requests became empty after roughly twenty detail calls. Calibrated the collector to about one detail request every three seconds, first-page priority, last-page fallback, and retry on empty/error responses. The verified day capture recovered reply evidence for 31/35 topics versus 9/35 before throttling.
- Codex wrote `reports/20260715-nga-codex-preview.md` and `.html` directly from `reports/20260715-215836-nga-daily.json`, without external AI. The HTML renderer now emits proper labelled anchors for Markdown links.
- Updated ACTIVE automation `NGA大时代盘前盘后日报`: 08:50 uses `--window morning`; 15:50 uses `--window day`; both use gpt-5.4 medium reasoning and explicitly prohibit `--llm`/external AI.
- Acceptance is pending. Do not mark feat-040 pass or treat it as an accepted InsightRadar product capability until the user reviews the preview.
### feat-040 review feedback - sentiment dashboard and influential authors

- User review correctly rejected the first preview as insufficiently visual: it lacked explicit bullish/bearish balance, risk appetite, panic/euphoria intensity, disagreement, stage, sector temperature, and morning-to-close change. These are now mandatory in the automation prompt; icepoint/climax confirmation requires at least 20 comparable sessions, otherwise only a candidate label is allowed.
- Added a nine-account UID watchlist: fuelish, 文驹, 幸运阿sai, -阿狼-, 神之使Ty, 铁锤狂砸盘, 路过的帅小伙, Plezl, and 村上吹树. Topic/reply evidence now retains author IDs, watched-author topics receive detail priority, and payloads expose separate influencer activity.
- Direct author-id topic queries and profile JSON were not stable. Scope is explicitly limited to UID matches in paged fid=706 metadata and collected topic pages; no-hit does not mean no post.
- Influencer stances are kept separate from public bullish/bearish percentages to avoid double-counting a leading opinion as crowd consensus. No subjective importance weights are assigned without an outcome history.

### feat-040 review feedback - long-thread KOL recovery

- NGA thread-local `authorid` filtering was verified. Because content-heavy JSON responses can truncate, the collector now uses complete author-filtered HTML pages, validates the exact UID, and walks backward from the author's last page until the report window is covered.
- Added explicit long-thread IDs for fuelish, 文驹, 幸运阿sai, -阿狼-, and 村上吹树. Current sampled KOL-authored threads are also checked, so old topics can contribute new replies without being mislabelled as new themes.
- Live artifact `reports/20260715-223952-nga-daily.json` selected 35 topics with zero influencer collection gaps. It recovered 8 fuelish replies, 10 铁锤狂砸盘 replies, and 11 村上吹树 replies inside 00:00–15:59; 文驹、幸运阿sai and -阿狼- had no long-thread reply in that window, while 幸运阿sai still had one new topic.
- 幸运阿sai now has a capped `signal_prior_weight=1.15` in the KOL layer. Its technology-bull and track-record profile is tagged `user_provided` / `unverified`, excluded from public sentiment, and must later be replaced by empirical viewpoint/outcome history.
- Updated the Codex preview and ACTIVE automation contract. Acceptance remains pending; feat-040 is not yet passed.

### feat-040 review feedback - visual-first report experience

- User requested more charts, fewer visible words, and more conclusions. The NGA HTML renderer now switches to a dedicated visual summary when it sees the sentiment/KOL contract.
- First-screen components: four decision cards, a 100% bullish/neutral/bearish composition bar, four 0-100 intensity bars, sector-temperature tiles, compact KOL stance rows, and five conclusion cards. The five narrative sections and their source evidence remain intact but collapsed by default.
- Updated the ACTIVE automation to preserve exact metric labels for deterministic rendering, lead every theme with its conclusion, reduce each theme body from 280-450 to 120-180 Chinese characters, cite 3-5 topics and at most two high-score replies, and move methodology below the first-screen decision path.
- Added report-rendering coverage for the NGA visual branch. Acceptance remains pending until the user refreshes and reviews `reports/20260715-nga-codex-preview.html`.

### feat-040 review feedback - evidence-bound strategy contracts

- Recorded the user-provided recent review of NGA tid=46906089 as a versioned `decision_framework` under 幸运阿sai's separately labelled profile. The source page returned 403 outside the authenticated adapter and the bounded author-only fetch found no 2026-07-16 reply, so `source_type=user_provided_review` and `verification_status=page_unverified` remain explicit.
- Preserved the useful structure: industry trend versus trading structure, portfolio drawdown response bands, core/trading sleeve boundaries, and the three mainline gates. Added guardrails that thresholds require a user risk budget, “科技主线结束” must become observable invalidation conditions, and not every unbroken move may be called a washout.
- Same-day Iwencai evidence showed material drift from the static post wording: several named leaders were already well below MA20 while 东山精密 and 拓荆科技 retained relative strength. The correct state is evidence-dependent “骨架受损/强分化/待确认,” not automatic washout or one-day industrial-trend invalidation.
- Updated ACTIVE automation `nga` to render a strategy-contract and falsification check when relevant, keep the framework outside public sentiment, and surface conflicts with current market evidence. ADR-0007 makes this separation durable. Acceptance remains pending.
- Fresh runtime verification `reports/20260716-165153-nga-morning.json/.md/.html` covered 12 topics with zero influencer collection gaps. 幸运阿sai had zero sampled activity, while the payload retained `source_type=user_provided_review`, `verification_status=page_unverified`, and the dated decision framework without mislabelling it as an in-window statement.
- The user identified the concrete loss mechanism: failure to reduce 盛新锂能 on 2026-07-02, followed by replacing price discipline with an external “mid-year earnings will be good” narrative, gave back June profit. Added an `external_view_firewall` with no action authority, thesis-substitution detection, three-part event validation (official filing / expectations / price response), and candidate 25% / 40% / 60% monthly-profit giveback bands that require user approval before activation. The ACTIVE `nga` automation consumes these rules.

## 2026-07-18 - feat-041 Daily cross-market and portfolio risk watch

### Implemented

- Added `risk-watch` as a read-only Core after-close workflow with JSON/Markdown/HTML artifacts.
- Added five capped signal families: 同花顺全A等权广度、A股内部结构、QQQ/SOX/韩国/日本、带生效日期的拥挤行为观察、组合总仓位/前三大/高β集中度。
- Added multi-family and data-coverage gates, two-session confirmation for orange/red, slow de-escalation, and a red risk-budget lock that releases only after three confirmed green sessions.
- Added private current and historical risk profiles. The current user-provided state is 20% total/high-beta exposure in one holding; the 2026-07-01 review profile records 86.92% total exposure and 62.37% top-three concentration without applying that snapshot before its effective date.
- Created ACTIVE Codex local automation `insightradar` for workdays at 16:20. It runs the read-only command, compares the previous artifact, reports changes and gaps, and cannot trade.

### Replay evidence

- `reports/20260718-214135-risk-watch.*` used only observations available through each replay date and reached 100% source coverage.
- First confirmed yellow: 2026-05-19; orange: 2026-06-03; red: 2026-06-09. Once red appeared, the execution budget stayed capped at 30% total / 15% high-beta through 2026-07-17 because no three-green-session re-entry gate occurred.
- The Korea event gate detected the second June KOSPI circuit breaker on 2026-06-23, escalated because it was the second 8% shock within 20 sessions, and remained active through 2026-07-01. A neutral-profile July-1 replay is in `reports/20260718-214008-risk-watch.*`.
- Latest state on 2026-07-17: red 76/100. The user's current 20% total exposure is below the total cap, so the report explicitly forbids mechanical panic liquidation; the single high-beta holding remains 5 percentage points above the red high-beta budget.

### Verification

- `python -m unittest discover -s tests -v`: 31/31 passed.
- `python -m compileall stock_assist`: passed.
- Live `risk-watch` CLI wrote fresh JSON/Markdown/HTML artifacts.
- Architecture regeneration and project-memory validation passed with 22/22 registered commands; CLI help and `git diff --check` passed.

### Boundary / next

- The system cannot identify the exact 2026-05-14 top without unacceptable false-positive risk. It is a drawdown-budget system, not a crash oracle.
- Iwencai is optional enrichment and fails visibly; it is not promoted to a required Core provider under ADR-0005.
- Resume `feat-037`; collect daily alert outcomes before changing thresholds or claiming predictive edge.

## 2026-07-18 - feat-042 Objective crowding and generalized global shocks

### Implemented

- Added an as-of Iwencai A-share crowding snapshot: total turnover, top-1/top-10/top-20/top-50 turnover share, partial turnover HHI, and the leading stock's turnover/free-float ratio.
- Exposed crowding in risk-watch JSON, Markdown, and HTML. It is diagnostic until at least 20 daily snapshots exist; it cannot yet add risk points or alter a historical replay.
- Added S&P 500 history plus volatility-normalized shock/repeat-shock gates for S&P 500, QQQ, SOX, and Nikkei. Existing Korea circuit-breaker logic remains, and simultaneous US/Asia shocks add a cross-region event signal.
- Updated the active `insightradar` automation to report concentration telemetry and headline any US, Japan, Korea, or cross-region event gate.
- Live-verified Futu community retrieval for ????C、新易盛、天孚通信 at 50 timestamped posts each. The endpoint exposes title/description/time/id but no interaction fields, so narrative/FOMO telemetry remains observation-only until point-in-time samples mature.

### Evidence

- Live artifact: `reports/20260718-233503-risk-watch.*`; red 76/100 at 100% coverage.
- 2026-07-17 crowding snapshot: total turnover CNY2.672tn; top-10 9.9%, top-20 14.7%, top-50 24.2%; ????C was top-1 at 2.1% of total turnover and 7.0% turnover/free-float.
- Focused tests: 8/8 passed; full suite: 33/33 passed; compileall, live JSON/Markdown/HTML, architecture regeneration, project-memory validation, CLI/JSON validation, and `git diff --check` passed.

### Boundary / next

- Do not calibrate concentration thresholds from this single crash. Archive at least 20 daily snapshots, then use rolling percentiles and replay/outcome evidence.
- Quantify long-horizon pricing with consensus forecast duration and timestamped narrative ratios, but keep community text outside action authority until its history, coverage, and false-positive behavior are validated.

## 2026-07-19 - feat-043 AI CapEx and optical-demand transmission watch

### Implemented

- Added `ai-capex-watch` as a Core read-only JSON/Markdown/HTML workflow using timestamped official IR evidence for Microsoft, Alphabet, Meta, Amazon, Oracle, NVIDIA, and Alphabet infrastructure mix.
- Added three decision layers: confidence-adjusted hyperscaler CapEx momentum, optical-network transmission, and 中际 supplier realization. Sparse evidence shrinks toward neutral; unverified/future/stale observations are excluded.
- Added explicit anti-FOMO guardrails: total CapEx is not treated as optical demand, industry scores cannot override `risk-watch`, and positive industry evidence cannot authorize chasing or cancel financial/price invalidation.
- Updated the active workday 16:20 automation to run `risk-watch` and `ai-capex-watch`; industry evidence is highlighted only when official inputs, freshness, or conclusions change.

### Evidence

- Fresh artifact `reports/20260719-002412-ai-capex-watch.*`: CapEx momentum 70.3/100 at 54% coverage; optical transmission 74.4/100 at 60% coverage; supplier realization pending.
- Current conclusion: cloud investment and network transmission are supportive, but 中际 realization is not closed and the signal is not a chasing trigger.
- Four focused and 37 full tests passed; compileall, live CLI, JSON validation, architecture regeneration with 23/23 command coverage, project-memory validation, CLI help, and `git diff --check` passed.
- In-app Browser rejected direct `file://` navigation under URL policy, so responsive visual QA remains explicit rather than falsely reported as passed.

### Next

- Resume `feat-037`. For the next explicit indicator sprint, add automatic official-IR change discovery and then bind 中际 official financial disclosures to the supplier-realization gate.
- Only after those sources mature should the product quantify market-implied forecast duration / 2030 pricing and replay thresholds.

## 2026-07-19 - feat-037 Core decision-loop reliability baseline

### Implemented

- Reconciled the active portfolio to the user's newest explicit snapshot: one live holding, ????C, about CNY100k and 20% account weight. The ignored private JSON supersedes the stale 2026-07-09 broker TSV; unavailable shares, cost, broker price, single-position P&L, and original risk line remain absent.
- Added a structured Core reliability scorecard to after-close JSON/Markdown/HTML. It separates structural action coverage from strict decision-ready coverage and requires a dated snapshot, complete position fields, context, evaluated market data, and position/upside/downside/flat action branches.
- Fixed after-close action parsing so only the holding-action section populates native-client actions, and missing broker values render as `未提供` instead of misleading zeroes.
- Fixed two real-run blockers: market-pulse now skips realtime AmazingData outside the A-share live session and uses bounded public fallback with explicit gaps; market-level synthesis ignores valid timeframes that have no qualifying support zone instead of indexing an empty tuple.

### Real evidence

- `reports/20260719-012054-after-close.*`: 1/1 structural action coverage, 0/1 strict decision-ready coverage, market data through 2026-07-17, one explicit position-snapshot gap, and a separate non-blocking optional-extension gap channel.
- `reports/20260719-011009-market-pulse.*`: completed in 13.8 seconds from the D-drive config with 17 explicit weekend/upstream gaps rather than hanging or inventing direction.
- `reports/20260719-011118-market-levels.*`: six timeframes through 2026-07-17, no report-level gaps, and a conditional weak-support-test verdict.
- `reports/20260719-011147-research-monitor.md`: added 34 research deltas, including current-holding HOLDING-C.EX evidence.
- `reports/20260719-011948-evolution.md`: outcome ledger tracks 16 signals with 15 matured 1d samples and 6 matured 5d samples; sample counts remain too small for stable edge claims.
- Fresh `reports/20260719-005525-risk-watch.*` and `reports/20260719-005525-ai-capex-watch.*` preserve the previously verified risk-budget and industry-transmission layers.

### Verification and boundary

- Added focused regression coverage for snapshot metadata, placeholder-gap filtering, strict readiness, missing-value rendering, out-of-session provider behavior, and sparse-support synthesis.
- Full unit regression, compileall, live workflow artifacts, JSON/config validation, project-memory validation, harness validation, CLI help, and diff checks passed.
- Baseline completion means real gaps are measured and fail visibly; it does not relabel the current 0/1 strict holding coverage as decision-ready.
- Next: `feat-044`, automatic official-IR discovery plus 中际 supplier-realization ingestion. Factor Lab, optional Extensions, deployment expansion, valuation-duration inference, and automated execution remain parked.

## 2026-07-19 - feat-045 State-team ETF share exit proxy

### Implemented

- Extended the existing `market-pulse` contract instead of adding a duplicate command. It serially queries AmazingData fund-share history for four CSI 300 ETFs and renders the same state-team evidence in JSON, Markdown, and HTML.
- Added dated 2025 annual-report Huijin holdings and source URLs plus 2023-03-31, 2023-08-01, and 2023-10-20 ETF-total-share baselines.
- Defined the conservative metric as `max(disclosed Huijin ETF units - current ETF total units, 0)`. It is a provable ETF-unit exit lower bound, not cash net selling, not proof of underlying-stock disposal, and not complete coverage of the 2015 rescue book.
- Added explicit gaps for ETF in-kind redemption destinations, intraday subscriptions/redemptions and premiums, and 2015-era CSF/Huijin direct stock holdings pending the completed 2026 interim-report set.

### Real evidence

- Fresh artifact `reports/20260719-151119-market-pulse.*` uses fund-share history through 2026-07-17. Four products total 462.74亿 units versus 2069.34亿 units disclosed to Huijin at 2025 year-end, proving a minimum 1606.59亿-unit exit or 77.64%.
- Current aggregate units are +25.33% versus 2023-03-31, -4.40% versus 2023-08-01, and -29.67% versus 2023-10-20. Per-product lower-bound exits range from 70.46% to 83.99%.
- Four focused state-team tests and the full 48-test suite passed. Compileall, JSON checks, real CLI generation, static JSON/Markdown/HTML contract assertions, architecture regeneration, project-memory validation at 23/23 command coverage, harness 100/100, and `git diff --check` passed.

### Boundary / next

- Do not convert ETF unit changes into yuan flow without verified NAV, creation/redemption mechanics, and in-kind transfer destinations.
- After 2026 interim-report disclosure is complete, build the separately scoped direct-stock shareholder comparison for the 2015 rescue book. The previously planned next feature remains `feat-044`.

## 2026-07-19 - feat-046 Recurring state-team ETF delta monitor

### Implemented

- Extended the four-ETF proxy with per-product and aggregate changes over the latest 1, 5, and 20 observations plus the corresponding tightening or loosening of the provable cumulative exit lower bound.
- Added mixed-horizon classification so a recent share rebound inside a still-contracting medium window is not flattened into either a rescue or liquidation narrative.
- Updated the ACTIVE workday 16:20 `insightradar` automation to run `risk-watch`, `market-pulse`, and `ai-capex-watch`, compare prior artifacts, and only emphasize a state-team change when the share date, lower bound, short/medium structure, or public holding disclosure changes.
- Preserved the attribution firewall: ETF total-share changes cannot identify the current seller, cash flow, in-kind redemption destination, underlying-stock disposal, or the 2015 direct rescue book.

### Real evidence

- Full product run wrote `reports/20260719-153506-risk-watch.*`, `20260719-153523-market-pulse.*`, `20260719-153524-ai-capex-watch.*`, `20260719-153542-after-close.*`, and `20260719-153543-evolution.md`.
- State-team proxy through 2026-07-17: +7.29% over one observation, +17.88% over five, and -33.38% over twenty; the twenty-observation contraction tightened the cumulative lower bound by 231.86亿 units. Product conclusion: short-term replenishment, medium-window net contraction.
- Six focused state-team tests and 50 full tests passed. Compileall, JSON/static report checks, automation TOML assertions, architecture regeneration, project-memory validation, harness 100/100, and diff checks passed.

### Product gaps exposed by the run

- `after-close` still does not ingest native risk-watch, state-team, or ai-capex conclusions, so the most important Core monitors remain separate from the final holding decision surface.
- `evolve` lists capability status only through feat-027 and therefore misses the gaps and freshness of risk-watch, ai-capex-watch, and state-team monitoring.
- `market-pulse` couples the state-team history query to intraday snapshot/futures sections, producing avoidable market-data gaps during after-close automation; a state-only mode or shared daily market context would reduce noise.
- A dedicated value/growth/bank/broker/high-dividend relative-strength adapter is still needed before the product can distinguish defensive bank support from a confirmed financial-led main line.

### Next

- Keep `feat-044` as the documented next feature pending user priority. Recommended competing priority is a Core synthesis feature that feeds risk/state-team/industry conclusions into `after-close` and repairs `evolve` coverage before adding more standalone monitors.

## 2026-07-19 - feat-047 Unified next-session decision layer

### Implemented

- Added a dedicated Core synthesis module that loads the newest risk-watch, market-pulse, and ai-capex-watch JSON artifacts, checks source freshness, and merges them with holding-level actions and strict reliability state.
- Added a structured `unified_decision` contract to after-close JSON: next-session date, defensive/expansion stance, confidence, first action, total/high-beta budget, opening/upside/flat/downside scenarios, blocked actions, unlock conditions, evidence effects, source report audit, and fail-closed gaps.
- Put the same plan near the top of Markdown and on the HTML first screen. The dashboard now shows the unified risk budget instead of deriving CALM from a hold action, and it keeps a live holding visible when cost/P&L are unknown rather than converting unknowns to zero or dropping the position.
- Updated the ACTIVE workday 16:20 `insightradar` automation to run after-close after risk-watch, market-pulse, and ai-capex-watch and lead its delivery with the unified plan.

### Real evidence

- Fresh `reports/20260719-181600-after-close.*` sets plan date 2026-07-20, stance `防守观察`, confidence `中低`, risk red 76, total exposure 20% versus 30% cap, and high-beta exposure 20% versus 15% cap.
- For ????C: no new high-beta exposure; preferentially use a rebound below 1187.29 to reduce about one quarter and move high beta toward 15%; if neither branch triggers, do not panic-sell the open; if 950.08 breaks or the sector clearly weakens, reduce one quarter; a confirmed reclaim remains hold-only until risk and supplier-realization gates also unlock.
- The plan explicitly blocks treating short state-team ETF replenishment as a confirmed broad re-entry or an automatic high-dividend rotation, and blocks chasing CPO from CapEx narrative alone.
- Headless Chrome rendered `reports/20260719-181030-after-close.png`; visual inspection confirmed the unified four-card layout, one live CNY100k holding, red risk label, and NA broker fields without horizontal overflow at 1440px; the subsequent 181600 artifact only tightened the risk-budget wording.

### Verification and remaining gap

- Eight focused and 54 full tests passed, plus compileall, real after-close generation, JSON/static contract assertions, architecture regeneration, project-memory validation, harness 100/100, automation assertions, and `git diff --check`.
- Strict holding readiness remains 0/1 because shares, cost, broker price, and single-position P&L are genuinely unknown; the unified plan therefore gives fractions/conditions but not an invented exact share count.
- `evolve` still stops capability discovery at feat-027. Repair that governance blind spot before using its automatic backlog as a complete product assessment; the documented source-ingestion next feature remains feat-044 unless reprioritized.

## 2026-07-19 - feat-048 Market regime cockpit and local broker import

### Implemented

- Added `market-levels` as a fourth native input to the unified next-session decision layer, with explicit support, first-confirmation, stronger-resistance, and daily-repair zones plus a four-stage intraday watchlist.
- Added transparent diagnostic composites: bear-bull 0-10, fear-greed 0-100, and crowding 0-100. Each exposes as-of and calibration state; crowding explicitly remains a fixed-threshold diagnostic until at least 20 daily snapshots exist.
- Added three first-screen radial gauges and an adjacent Shanghai state ladder. The display uses direct labels, units, dated context, and action meanings rather than decorative colour alone.
- Added a local-only after-close `导入持仓` modal. It parses pasted/uploaded broker TSV in the browser, prioritizes `当前持仓` over `股票余额`, previews with `textContent`, preserves missing numbers as null, and requires a user-approved save to `portfolio.json`; the static report states that after-close must be rerun.
- Updated the ACTIVE 16:20 workday automation to run `market-levels` between `market-pulse` and `ai-capex-watch`, then lead with `market_regime`, `market_levels`, and `tomorrow_watchlist` while preserving no-trade/no-silent-holdings-write boundaries.

### Real evidence

- Fresh `reports/20260719-184801-after-close.*` reports as of 2026-07-17: bear-bull 2.0/10 (`熊市风险开启`), fear-greed 28/100 (`恐慌`), and crowding 52/100 (`中性`; not a historical percentile).
- Shanghai state ladder: 3742.07-3770.09 support, 3789.96-3826.16 first confirmation, 3863.12-3913.11 stronger weekly resistance, and 3943.56-3980.25 daily repair.
- The exact user-provided Galaxy TSV row parses as HOLDING-C.EX, 100 shares, 1336.141 cost, 979.46 price, -35668.08 P&L, -26.695%, -13354 day P&L, and 19.17% portfolio weight.

### Verification and remaining calibration gaps

- Ten focused tests and the full 56-test suite passed. Compileall, real after-close generation, inline-JS syntax/static HTML assertions, JSON validation, architecture regeneration, project-memory validation (23/23 commands), harness 100/100, automation assertions, and `git diff --check` passed.
- In-app browser automation blocked direct `file://` navigation. The policy was not bypassed; visual automation remains an explicit limitation, while static DOM/CSS/interaction checks passed and the local report is available for user-side viewing.
- The three composites are not calibrated against forward returns or drawdown persistence. Crowd telemetry has fewer than 20 archived sessions, and the importer cannot refresh an already-open static report without a rerun.
- The importer updates canonical holding fields, but `risk-watch` still reads exposure and high-beta classification from `data/risk_watch_profile.json`. The modal states this boundary; a future canonical portfolio-risk adapter should synchronize the two without guessing beta class from ticker codes.

## 2026-07-19 - feat-049 Fixed-anchor A-share breadth and equivalent points

### Implemented

- Added a serial, paginated 同花顺问财 cross-section for the fixed 2024-09-24 anchor. The adapter requires listing-date eligibility, provider-returned forward-adjusted interval returns, complete pagination, and visible coverage before it will validate a stock-count claim.
- Added pure market-structure aggregation: below-anchor count/share, return quartiles and median, arithmetic equal-weight and median-stock equivalent Shanghai points, official-versus-equal-weight divergence, current-free-float concentration proxy, explicit 申万电子/通信/计算机 diagnostics, industry weakness, and a 0-100 cumulative anchor-width gauge.
- Added `anchor_structure` to risk-watch and `market_structure` to after-close. The HTML first screen now shows a fourth gauge and a dedicated market-width/index-divergence panel; the current short-cycle red risk state remains separate from cumulative position versus 9·24.
- Coverage failure is fail-closed: incomplete data cannot validate “3900 stocks,” calculate an action-authorizing equivalent point, or silently reuse a partial first page.

### Real evidence

- Fresh `reports/20260719-192028-risk-watch.*` and `reports/20260719-192054-after-close.*` return 5538 unique rows, exclude 230 post-anchor listings and 9 rows with missing listing dates, and cover 5299/5299 eligible A-shares through 2026-07-17.
- 925 stocks, 17.46%, are below their 2024-09-24 anchor; the same-method “3900 stocks below 9·24” claim is therefore not supported.
- Median stock return is +34.31%, giving a median-stock equivalent Shanghai level of 3845.54. Arithmetic equal-weight return is +76.75%, giving 5060.68; this skew-sensitive measure remains displayed beside the more robust median and the official 3764.15.
- The unified next-session plan remains defensive: red risk, bear-bull 2.0/10, no added high beta, and the existing conditional trim plan. The 78/100 anchor-width gauge says most stocks remain above the long anchor, not that the current selloff has ended.

### Verification and remaining gaps

- Added focused pagination, coverage, adjusted-return, equivalent-point, and cockpit tests. The full 59-test suite passed; live pagination completed in about 20 seconds and the final risk-watch plus after-close product chain completed successfully.
- The result is a single-provider, single-anchor snapshot rather than a survivorship-free rolling panel or official historical index-contribution decomposition. Current free-float weighting is labelled a proxy; equal-weight arithmetic mean is visibly paired with the median.
- Next documented feature returns to `feat-044` unless the user reprioritizes. The highest-value follow-up for this module is daily archive/history plus a pre-open/intraday breadth refresh, not another narrative score.

## 2026-07-19 - feat-050/051/052 Core P0 decision closure

### Implemented

- `feat-050`: added a persisted, configuration-driven bear-bull score state machine with formal/candidate separation, close-only finalization, daily ±1 cap, same-rule/day deduplication, zone hysteresis, two-bar support-failure gate, stale/missing fail-closed behavior, risk veto, structured ledger, and typed market-level authority. The first screen now shows score change, candidate state, current level/zone relation, risk veto, first action, and the exact four decision windows.
- `feat-051`: replaced the static broker-save concept with a token-protected `127.0.0.1` preview/approval service. It validates and diffs data, preserves nulls, requires explicit beta/risk inputs, atomically backs up/replaces canonical files, rolls back on refresh failure, reruns five Core workflows sequentially, and never trades. Trim ratios now floor to 100-share lots without overshooting; a 100-share position at 25% correctly yields zero executable shares plus a manual-choice blocker.
- `feat-052`: added `style-rotation` JSON/Markdown/HTML using fixed technology-growth, large-financial, high-dividend, and CSI 300 proxies across 5/20/60 sessions, breadth, MA participation, approximate turnover, persistence, conflicts, coverage, and explicit missing earnings evidence. `after-close` consumes the result but does not grant it trade authority.
- Updated product registry, architecture topology, harness contracts, product/architecture memory, current state, feature evidence, and responsive report rendering. No Git commit or push was created.

### Real evidence

- Sequential real run succeeded: `reports/20260719-202207-market-levels.*`, `20260719-202238-risk-watch.*`, `20260719-202256-market-pulse.*`, `20260719-202258-style-rotation.*`, then `20260719-202312-after-close.*`. A final post-wording smoke produced `reports/20260719-203143-after-close.*`.
- Formal/candidate score is 2.0/2.0 with `RISK_VETO`; Shanghai is inside 3742.07-3770.09 support (`support_testing`), so stance remains defensive and the budget cannot upgrade.
- Style result through 2026-07-17 is `信号冲突`: large financials lead, technology growth weakens, persistence is three sessions, financial breadth/turnover and earnings evidence do not confirm a durable rotation.
- Canonical `data/portfolio.json` is empty/invalid. A real read-only preview of the older TSV parsed three rows but left zero broker weights as unknown and beta classes unknown, so reconciliation remained blocked and no user file was written.

### Verification and gaps

- Final 80-test suite passed, plus compileall, relevant JSON/config checks, CLI help, real artifact assertions, architecture regeneration and 25/25 command coverage, project-memory validation, harness 100/100, and `git diff --check`.
- Desktop 1440x900 visual QA passed. Exact 390px CDP emulation returned inner width 390, document/body width 375, and zero overflowing elements.
- The score and style matrix remain `diagnostic_unbacktested`. Current portfolio readiness is 0%; no actual executable holding quantity exists until the user explicitly approves current broker data and beta/risk classifications. `feat-044` remains the next documented feature.

## 2026-07-19 - feat-053 Guarded Iwencai futures-basis close adapter

### Implemented

- Added a project-owned, standard-library HTTPS Iwencai adapter for completed-close IF/IH/IC/IM basis. It resolves one shared latest close date for CSI 300/SSE 50/CSI 500/CSI 1000, then queries all CFFEX contracts for that exact date.
- Active contracts are selected dynamically from actual provider codes. Zero-open-interest expiry rows are rejected; the nearest two valid months per family carry close, volume, open interest, available daily open-interest change, future-minus-spot basis and basis rate.
- Provider order is explicit: Iwencai close first; during the live session a previous-day close is rejected and the existing serial AmazingData snapshot adapter is used. Outside the live session AmazingData remains gated, so a provider failure is bounded and visible.
- Completed-close rows have `basis_change=null`, are labelled diagnostic-only, and cannot fabricate or substitute for the four-minute confirmation signal. Long/short seats and historical basis percentiles remain gaps.
- Updated the payload/audit contract, report rendering, product registry, harness, ADR-0008, architecture topology, product/architecture memory, current state and feature evidence.

### Real evidence

- `reports/20260719-212631-market-pulse.*` contains eight aligned 2026-07-17 rows: IF/IH/IC/IM 2608 and 2609. All have nonzero open interest; front-month rows also expose the available daily open-interest changes.
- The first basis action is `只作盘后诊断`; report copy says four-minute change is unavailable rather than manufacturing a direction signal.
- The latest `data/market_pulse_sources.jsonl` entry contains eight error-free `同花顺问财 OpenAPI close snapshot` audit rows. Normal JSON/Markdown/HTML contain no API key, credential name, or provider-source card leakage.

### Verification

- Seven focused futures/reliability tests passed.
- Full test suite: 85/85 passed.
- Compileall, both pulse configs, feature/architecture JSON, real `market-pulse`, artifact/secret/audit assertions, architecture regeneration, project-memory validation, harness validation and `git diff --check` passed.
- Browser QA: desktop had eight basis rows, zero console errors and no page overflow; at 390px, document/body width stayed 375px and the 876px table remained inside a 317px `overflow-x:auto` container.

### Remaining limits

- The real evidence is one reconciled completed session, not a multi-day latency/quota/freshness study. Cross-platform/cloud readiness remains open under ADR-0005/0008.
- Iwencai completed-close basis is useful after close; live four-minute basis still requires same-day AmazingData observations or a future verified intraday adapter.
- Resume `feat-044` unless the user reprioritizes again.

## 2026-07-19 - Approved personal investment decision-intelligence design

### Product decision

- The user approved personal A-share investment decision intelligence as the durable North Star. Information aggregation, investment guidance, key alerts, and outcome calibration are Core value; time-of-day report labels are delivery details.
- Approved holdings remain the primary relevance anchor. When holdings are absent or sparse, the product may return zero to five transparent observation candidates with rationale, trigger, invalidation, horizon, risk, and later review; it never fills a candidate quota.
- `Alpha Report` remains the conclusion-first delivery family. Fast news such as Jin10 is a discovery input that must be verified, distinguished as new versus cumulative, mapped to affected objects, and assessed for plan/risk impact before promotion.
- Multi-agent work uses one lead plus temporary bounded roles. Agents maintain an evidence-backed problem backlog, one active experiment, and at most two queued; feature count and agent count are not success metrics.

### Files and evidence

- Added the approved design at `docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md` and durable ADR-0009.
- Refreshed the product charter, competitor benchmark, decision log, product-state memory, bounded current state, and project-memory routing.
- This design authorizes a later implementation plan; it does not activate a new code feature or replace `feat-044` yet.

## 2026-07-20 - feat-055 Jin10 verified event-intelligence design

### Product decision

- The user approved the recommended independent event-intelligence approach: Jin10 discovery feeds a normalized, deduplicated event contract, then primary-source verification, portfolio/market relevance, impact assessment, and evidence-gated report or key-alert promotion.
- Direct provider-to-`after-close` coupling was rejected; a general multi-provider event bus was deferred until one provider has measured precision, recall, latency, quota, and failure behavior.
- The user-scoped Codex MCP installation is development and feasibility evidence only. A standalone InsightRadar implementation must own the standard MCP lifecycle and read `JIN10_MCP_TOKEN` from repository-external environment state without leaking credentials.
- Fast news has no trade authority. Critical claims must distinguish incremental execution, recent/historical cumulative amounts, future commitments, targets/capacity, and unknown semantics before they can affect monitoring priority.

### Source evidence and boundaries

- A live MCP session negotiated protocol `2025-11-25`, exposed eight expected tools plus `quote://codes`, and returned 20 `list_flash` items through `structuredContent.data` with `next_cursor` and `has_more`.
- Entity searches recovered the 2026-07-19 China Reform Holdings CNY50bn-plus already-used cumulative market-support disclosure and the China Chengtong recent near-CNY10bn cumulative buying disclosure. A generic “国家队” search produced sports and industrial false positives, proving the need for compound entity/action/market-object classification.
- Initial product scope is fast news, article details, and the economic calendar. Jin10 quote/K-line tools remain outside the first increment because existing market-data workflows already own those responsibilities.
- `feat-055` is pending and queued behind `feat-044`; no product runtime adapter, workflow, report, automation, or architecture node was implemented.

### Files

- Canonical AI specification: `docs/superpowers/specs/2026-07-20-jin10-event-intelligence-design.md`.
- Chinese human-review copy: `docs/superpowers/specs/2026-07-20-jin10-event-intelligence-design.zh-CN.md`.
- Registered `feat-055` in `feature_list.json` and added its future Definition of Done to `docs/harness.md`.
- Refreshed bounded current/product-state memory while retaining `feat-044` as `next_feature_id`.

### Next

- The user confirmed the written design. The implementation source is `docs/superpowers/plans/2026-07-20-jin10-event-intelligence.md`; do not begin it or reprioritize `feat-044` implicitly.

### User confirmation and digest amendment

- The user confirmed the written design and asked to treat Jin10's repeated weekend/pre-open/midday/after-close important-news compilations as an efficiency and coverage input.
- The design now models these compilations as digest containers and reconciliation checkpoints. Child items link to existing atomic events or recover genuinely missed discoveries; the digest never inflates event or alert counts.
- Live `search_flash("重要消息汇总")` returned 52 structured items. Their item-key union was only `content/time/title/url`; the target Sunday digest had `content/time/url`. The current MCP contract exposes no red/highlight/importance metadata.
- `provider_importance` and `provider_red_highlight` therefore remain explicit unknown fields. The product will not infer APP styling from words, page color, emojis, or ordering; a later provider field requires provenance and real-sample validation.
- The approved design remains queued behind `feat-044`; this amendment does not start implementation.
- Created the TDD implementation plan at `docs/superpowers/plans/2026-07-20-jin10-event-intelligence.md`. Recommended future execution is subagent-driven with serialized repository writes and independent review; no implementation agent was started.

## 2026-07-21 - Agent Harness engineering and job-readiness design

### Product and career decision

- The user selected the Agent Harness R&D / Engineering target and approved a six-to-eight-week real-product-driven extraction strategy.
- InsightRadar remains the user's first OPC product and private investment decision-intelligence proving ground. Stable generic Harness contracts, synthetic tasks, sanitized failure patterns, and reproducible experiments will later be extracted into the public working project `EvidenceHarness`.
- The approved program covers bounded product governance, task/trace/checkpoint/privacy contracts, a 20-to-30-task evaluation suite, four Harness baselines, context/memory/checkpoint/multi-agent ablations, shadow adoption, and public Chinese/English portfolio material.
- Investment usefulness remains a release gate. The design preserves explicit unknowns, source/time provenance, strict decision readiness, no automatic trading, and private holdings/broker/risk-rule boundaries.

### Priority and files

- The user explicitly approved placing the Agent Harness job-readiness program ahead of `feat-044`.
- Added the canonical specification at `docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md` and the non-normative Chinese review copy beside it.
- Written-spec review is still required before implementation planning. `feat-054` is not activated yet, and feature/current-state files remain unchanged during this review gate.

### Next

- After the user approves the committed written specification, invoke `superpowers:writing-plans` and write a revised plan that supersedes the governance-only 2026-07-19 plan where scopes differ.
- Register and activate `feat-054` immediately before implementation, then update `CURRENT_STATE.md` and governance state consistently. Keep `feat-044` and `feat-055` pending during the bootstrap unless the user changes priority again.

### Written approval and deferral

- The user approved the committed written specification and explicitly requested record-only handling for now.
- Do not invoke `superpowers:writing-plans`, register or activate `feat-054`, dispatch implementation agents, or change production code until a future explicit resume request.
- `CURRENT_STATE.md` and product-state memory now record the approved direction, priority intent, and pause while retaining `feat-044` as the existing product-backlog marker.

### Planning resumed

- The user explicitly resumed the Agent Harness project on 2026-07-21, authorizing implementation planning but not feature execution.
- Added `docs/superpowers/plans/2026-07-21-agent-harness-bootstrap.md`, a nine-task TDD plan for governance, full-catalog evolution, read-only agent contracts, task/trace/privacy/checkpoint contracts, deterministic smoke evidence, product/architecture integration, independent verification, and closeout into pending `feat-056`.
- The new plan supersedes the 2026-07-19 governance-only plan where scopes differ. It does not register `feat-054`, change production code, dispatch implementation agents, or start the benchmark phase.

## 2026-07-21 - `feat-054` Agent Harness bootstrap closeout

### Scope and files

- Closed the governance/observability bootstrap only: bounded experiment governance, truthful full-catalog evolution, lead-only workspace writes, four read-only non-recursive task-agent contracts, versioned task/trace/privacy/checkpoint contracts, deterministic smoke evidence, and product/architecture registration.
- Closeout state changed only `feature_list.json`, `configs/product_governance.json`, `CURRENT_STATE.md`, `docs/memory/product-state.md`, this log, and `session-handoff.md`; ignored runtime artifacts were not staged.

### Verification and evidence

- Focused 83/83 and full 168/168 tests passed. Compileall, JSON parsing, agent-contract validation, project-memory validation, Harness 100/100, credential-pattern rejection, public trace validation, checkpoint task/goal/run continuity, exact trace hash, and diff checks passed.
- Fresh reports are `20260721-232226-agents.md`, `20260721-233536-evolution.md`, and `20260721-232237-harness-smoke.md`. Smoke run `smoke-20260721t152237z` has trace SHA-256 `9749a46efa8e8403eed2508f7750d4f24e82ac68777b5b50dc82e36118d4989f`, sequence 6, and zero pending checkpoint steps.
- The independent read-only verifier returned PASS with 0 blocking, 0 important, and 0 advisory findings. Public output contains no private credential material, model-performance/superiority claim, or trade-authority grant.

### Next

- `feat-056` is pending and is the sole queued Harness experiment. Write a separate implementation plan before any five-task pilot or benchmark run; do not start it automatically. `feat-044` and `feat-055` remain pending outside this queue.

## 2026-07-21 - `feat-054` reopened for final hardening

- Final whole-branch review found blocking executable-manifest, public-privacy, and sole-writer contract gaps plus bounded-read, topology-input, and normative-status findings. The earlier PASS is historical rather than current closeout proof.
- `feat-054` is `in_progress` and is the only active implementation work until all six findings and a fresh independent verification pass.
- `feat-056` remains pending and the sole queued Harness experiment; no pilot, benchmark, provider, model, network, investment-workflow, or trade-authority work is authorized.

## 2026-07-21 - `feat-054` final hardening implemented, verification pending

### Findings and commits

- `0e584e0` closes the executable-manifest, public privacy/reproducibility, and bounded-read findings with strict starting state, shared normalized-key/all-string scanning, exact-limit readers, enforced step/tool/elapsed budgets, exact artifacts, every declared acceptance check, and fail-closed publication.
- `53224ac` closes the sole-writer finding with exact six-identity roster fields, engagement, authority, runtime bindings, matching TOML contracts, and fail-closed `agents` reporting.
- `b13a105` closes truthful topology and normative-status findings by validating governance/feature/roster/TOML sources at runtime, declaring all inputs in product/architecture artifacts, and recording current final-hardening state in the canonical design.

### Verification and evidence

- TDD exposed the original gaps, the undeclared `feature_list.json` input, and an unbounded smoke trace hash before each fix. Harness core 49/49, integration 7/7, and full discovery 184/184 tests pass; compileall, agent contracts, project memory, and worktree Harness 100/100 also pass.
- Fresh actual artifacts are `reports/20260722-003048-agents.md`, `reports/20260722-003056-evolution.md`, `reports/20260722-003101-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t163101z`.
- The run contains exactly three declared artifacts, 13 monotonic trace events, canonical `CURRENT_STATE.md` starting state, steps 8/8, tool calls 2/4, final pass, zero pending checkpoint steps, and trace SHA-256 `30c5fb449688ce6b43e8ff530349b2975537154961236f982d81c2075452f7b5`.

### Next

- Keep `feat-054` `in_progress` until a fresh independent read-only verifier reviews the full branch and returns PASS. `feat-056` stays pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 - `feat-054` final-hardening review corrections implemented

### Contract corrections

- Commit `8479be6` intentionally removes `exit_code` from the v1 acceptance kinds. The historical bootstrap plan contains an illustrative `exit_code` kind, but this in-process smoke has no separately observed subprocess result, so v1 now executes only `file_exists` and `text_contains` checks rather than treating a requested literal as observed evidence. Plan history was not rewritten.
- Public/sanitized scanning now rejects embedded Windows drive, UNC, slash-UNC, and POSIX absolute path tokens after punctuation such as `=`, `(`, and `:` with marker-free errors. CLI regressions prove invalid manifests create neither a final run nor staging residue.
- Clause-aware trade scanning accepts explicit negated safety requirements such as `Refuse to buy 100 shares` and ordinary `input / output` prose while still rejecting positive/granted and double-negated trade actions, credentials, private paths, reasoning, and raw conversation material.
- `CURRENT_STATE.md` is dated `2026-07-22`; `next_feature_id` remains `feat-054`, `feat-054` remains `in_progress`, and `feat-056` remains pending and sole queued.

### Verification and evidence

- TDD RED/GREEN covered unobservable `exit_code`, five punctuation-embedded path forms plus slash UNC, benign prose false positives, double-negated trade authority, CLI marker/no-residue behavior, and the local-date/state invariant. Focused tests are 90/90 PASS and full discovery is 188/188 PASS.
- Compileall, agent-contract validation, project-memory validation, and worktree Harness validation 100/100 pass. Actual adversarial CLI probes reject `exit_code`, embedded Windows paths, and embedded POSIX paths with exit 1, marker-free diagnostics, and no output directory.
- Fresh reports are `reports/20260722-005149-agents.md`, `reports/20260722-005155-evolution.md`, and `reports/20260722-005159-harness-smoke.md`. Ignored run `data/harness_eval/runs/smoke-20260721t165159z` has exactly three artifacts, 13 valid events, steps 8/8, tool calls 2/4, zero pending checkpoint steps, and trace SHA-256 `7c088a19e9753ad835362bf1641b043c778f623ba69f27e5744c2cba8ae53c06`.

### Next

- Keep `feat-054` `in_progress` until another fresh independent read-only verifier returns PASS. Do not start the pending `feat-056` pilot or benchmark.

## 2026-07-22 - `feat-054` deterministic public-validation rereview fixes

### Contract corrections

- Commit `676479a` replaces expanding absolute-path regex alternations with a bounded deterministic scanner for Windows drives, backslash UNC, slash UNC including numeric/IPv4 hosts, and POSIX tokens after punctuation. Ordinary spaced separator prose such as `input / output` and `123 / 456` remains accepted.
- Trade validation now splits bounded clauses, locates explicit English/Chinese trade actions and safety cues, and applies cue parity before each action: odd parity is safety prose; zero/even parity remains positive authority and is rejected.
- RED matrices exposed numeric POSIX and IPv4 slash-UNC publication plus reversed double-negation and `unsafe` false-positive gaps. GREEN matrices cover the requested punctuation/path/separator and `Refuse`/`not`/`never`/`unsafe` parity cases while retaining credential, private, reasoning, and Chinese positive-trade rejection.

### Verification and evidence

- Focused six-module suite is 90/90 PASS; fresh full discovery is 188/188 PASS. Compileall, agent-contract validation, project-memory validation, and worktree Harness 100/100 pass.
- Actual numeric-path, IPv4 slash-UNC, and even-parity trade manifests each exit 1, keep path markers out of diagnostics, and leave no output directory.
- Fresh reports are `reports/20260722-011257-agents.md`, `reports/20260722-011257-evolution.md`, and `reports/20260722-011258-harness-smoke.md`. Ignored run `data/harness_eval/runs/smoke-20260721t171258z` has exactly three artifacts, 13 monotonic events, final pass, steps 8/8, tool calls 2/4, zero pending checkpoint steps, and matching trace SHA-256 `2a807d9af8659210d4feefc2d53e51ede5134a3a688c238faea73b532fa147b1`.

### Next

- Keep `feat-054` `in_progress` and dated `2026-07-22` until a fresh independent read-only whole-branch verifier returns PASS. `feat-056` remains pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 - `feat-054` final parser review corrections

### Deterministic token corrections

- Commit `359a2f6` consumes configured multi-character Chinese safety cues before standalone `不`, without overlap. Standalone `不` counts only when directly composed with an action or another cue, so `不买入` and `拒绝买入` are safe odd parity while `不得不买入` and `拒绝不买入` are rejected even parity.
- The bounded cue matrix covers `不能`、`不可`、`禁止`、`避免`、`拒绝`、`不得`、`不是`、`并非` and standalone `不`; positive `买入`、`卖出`、`下单`、`交易` remain rejected. The canonical benign `交易权限：none` label stays accepted.
- English action tokenization exempts only exact hyphenated `buy-side`, `sell-side`, and noun `buy-in`; plain actions plus `buy-now` and `sell-now` still reject.

### Verification and evidence

- TDD RED reproduced Chinese reverse/double-negation publication and benign English-compound rejection; GREEN loader and real-CLI regressions pass. Focused six-module verification is 91/91 PASS and fresh full discovery is 189/189 PASS.
- Python 3.10 grammar parsing, compileall, agent-contract validation, project-memory validation, and worktree Harness 100/100 pass. An external Chinese double-negation CLI manifest exits 1 with empty stdout, marker-free stderr, and no output directory.
- Fresh reports are `reports/20260722-012926-agents.md`, `reports/20260722-012927-evolution.md`, and `reports/20260722-012928-harness-smoke.md`. Ignored run `data/harness_eval/runs/smoke-20260721t172928z` has exactly three artifacts, 13 monotonic events, final pass, steps 8/8, tool calls 2/4, zero pending checkpoint steps, and matching trace SHA-256 `bec7b4541efb7a83c4108869b072faa91cb5f40aea6b52601bae11f5459064a1`.

### Next

- Keep `feat-054` `in_progress` and dated `2026-07-22` until a new independent read-only whole-branch verdict passes. `feat-056` remains pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 - `feat-054` adjacent Chinese cue parity correction

- Commit `1c08681` simplifies Chinese cue parsing to one bounded linear prefix scan: at each index it consumes the longest configured multi-character cue first, otherwise counts each standalone `不` exactly once and advances one character.
- TDD matrices cover one through four adjacent standalone cues across `买入`、`卖出`、`下单`、`交易`: odd one/three sequences load, even two/four sequences reject. Existing `不得不` and `拒绝不` rejection remains intact.
- Focused six-module verification is 91/91 PASS and fresh full discovery is 189/189 PASS. Python 3.10 parsing, compileall, validators, and worktree Harness 100/100 pass; the external even-cue CLI exits 1 with empty stdout, marker-free stderr, and no residue, while an odd-cue manifest loads.
- Fresh reports are `reports/20260722-014043-agents.md`, `reports/20260722-014044-evolution.md`, and `reports/20260722-014044-harness-smoke.md`. Ignored run `data/harness_eval/runs/smoke-20260721t174044z` has 13 monotonic events, final pass, zero pending steps, and matching trace SHA-256 `51050c943deb5e0180c05a4448441c926e5aaa6c7440890e0eb44993d2149c9d`.
- `feat-054` remains `in_progress` and dated `2026-07-22`; `feat-056` remains pending and sole queued. Next action is another independent read-only whole-branch verdict.

## 2026-07-22 - `feat-054` final verifier contract fixes

### Finding closure

- Commit `4544fb3` splits English `and`/`or`/`but`/`then` and Chinese conjunctions before applying safety-cue parity. Cues now protect only their action subclause, `submit order` is an action, and explicit `trade authority` / `交易权限` declarations are safe only for exact `none`/`no`/`disabled` semantics.
- Absolute path scanning now catches drive, UNC/device, slash-UNC, and POSIX tokens immediately after Chinese text while retaining relative references and ordinary spaced separator prose. Loader and real-process CLI regressions are marker-free and leave no output directory.
- V1 has no transformation-record event, so `TraceWriter` and `validate_public_trace` accept only `PUBLIC`; hand-authored and writer `SANITIZED` traces fail closed. The writer also rejects a 65th event before append, while exactly 64 lifecycle-valid events pass and the validator retains its cap as defense in depth.

### Verification and evidence

- TDD RED reproduced all three Important findings and the event-cap Minor finding before implementation. Focused verification is 93/93 PASS and fresh full discovery is 191/191 PASS; Python 3.10 parsing, compileall, agent-contract validation, project-memory validation, and worktree Harness 100/100 pass.
- External clause-leakage and Chinese-adjacent-path CLI probes each exit 1 with empty stdout, marker-free stderr, no published output directory, and no staging residue.
- Fresh reports are `reports/20260722-021236-agents.md`, `reports/20260722-021237-evolution.md`, and `reports/20260722-021237-harness-smoke.md`. Ignored run `data/harness_eval/runs/smoke-20260721t181237z` has exactly three declared artifacts, 13 monotonic `public` events, final pass, steps 8/8, tool calls 2/4, zero pending checkpoint steps, and matching trace SHA-256 `b7746054b6ac0a0fd22f69fa85a0bcd094e39b60faa861378cbe3b8578686a3a`.

### Next

- Keep `feat-054` `in_progress`, next, and dated `2026-07-22` until a fresh independent read-only whole-branch verifier returns PASS. `feat-056` remains pending and sole queued; do not start its pilot or benchmark.

## 2026-07-22 - complete authority declaration validation

- Final review reproduced one remaining Important bypass: the general clause splitter detached `and/or/but/then`, Chinese conjunction, or comma suffixes from an exact safe authority prefix, so the suffix no longer carried the declaration label. Commit `93b2a5b` now scans every complete English or Chinese declaration through its sentence boundary before any general clause splitting.
- English authority values are safe only when the entire normalized value is exact `none`, `no`, or `disabled`. Chinese declarations additionally accept exact `无`, `没有`, or `禁用`. Any conjunction, comma, extra word, unsafe suffix, or unsafe member of multiple declarations rejects; only after this pass does action-local clause validation run on the bounded string.
- TDD RED reproduced all 13 reviewer suffix variants and real CLI publication, while the new Chinese safe enums initially failed. GREEN covers the 13 variants, colon/equal and exact-safe matrices, multiple all-safe and safe+unsafe declarations, plus English/Chinese CLI marker/no-residue cases. Focused verification is 95/95 PASS and full discovery is 193/193 PASS.
- Python 3.10 parsing, compileall, agent contracts, project memory, and worktree Harness 100/100 pass. External English and Chinese processes each exit 1 with empty stdout, marker-free generic failure, no output directory, and no probe residue.
- Fresh evidence is `reports/20260722-022905-agents.md`, `reports/20260722-022906-evolution.md`, `reports/20260722-022906-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t182906z`; it has exactly three files, 13 monotonic public events, final pass, zero pending steps, and matching trace SHA-256 `15735887855e36a5679718e14c4d0eb16170a62df7f27443ddfbbd80b9686bb2`.
- `feat-054` remains `in_progress`, next, and dated `2026-07-22` pending a fresh independent verdict. `feat-056` remains pending and sole queued; no pilot or benchmark work started.

## 2026-07-22 - authority semicolon boundary correction

- Commit `4b85b32` removes `;` and `；` only from the authority declaration's true sentence-boundary set. They remain inside the complete declaration value, so safe prefixes followed by single, repeated, mixed, or multi-value semicolon suffixes fail closed; the general non-authority clause splitter is unchanged.
- TDD RED reproduced 11 English/Chinese loader bypasses and two publishing CLI cases. GREEN covers those suffixes, multiple semicolons, CRLF/LF-separated exact declarations, exact declarations followed by genuinely new safe sentences, positive actions after a real sentence boundary, and unchanged safe/unsafe non-authority semicolon clauses.
- Focused verification is 96/96 PASS and full discovery is 194/194 PASS. Python 3.10 parse, compileall, agent contracts, project memory, Harness 100/100, and external English/Chinese marker-free no-residue processes pass.
- Fresh evidence is `reports/20260722-023845-agents.md`, `reports/20260722-023845-evolution.md`, `reports/20260722-023846-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t183846z`; it has exactly three files, 13 public events, final pass, zero pending steps, and matching trace SHA-256 `b8f39de6ed8cb3d3c4de84a7a6a9adcefe54841d227392886c1be018626a000b`.
- `feat-054` remains `in_progress`, next, and dated `2026-07-22` pending a fresh independent verdict. `feat-056` remains pending and sole queued; do not start the pilot or benchmark.

## 2026-07-22 - structural public v1 policy replaces semantic parsing

### Structural contract

- Final verification concluded that free-form cue parity, authority-value enums, sentence boundaries, conjunctions, and benign-compound exceptions could not be safely enumerated. Commit `781429e` deletes that semantic parser and makes PUBLIC/SANITIZED manifest free text fail closed on every English or Chinese trade-action/authority lexeme, including negated prose, conjunction variants, `buy-side`, `sell-side`, and `buy-in`.
- The shared all-string walker now rejects normalized password/passwd/pwd/token/secret/API/access-key/credential/session/account assignments followed by `=` or `:`, plus holdings, positions, shares, broker export/account, account identifiers, cost basis, personal risk/profile/tolerance, raw conversation, and reasoning phrases. Only the exact fixed structured `交易权限：none` acceptance check remains approved; other acceptance prose containing a trade/authority lexeme rejects.
- PUBLIC project input references now use a positive allowlist for `.codex/agents/`, `configs/`, `docs/`, `stock_assist/`, `tests/`, and exact safe root state files. `data/`, `reports/`, portfolio/broker/risk-profile, arbitrary roots, and traversal reject. PRIVATE manifests retain generic bounded relative references; SANITIZED still fails closed without a verified transformation record.

### RED/GREEN and evidence

- RED produced 76 expected structural-policy failures plus the leading-dot `.codex/agents/` reference error across 29 focused tests. GREEN passes 91/91 focused and 193/193 full tests; Python 3.10 parsing, compileall, agent-contract validation, project-memory validation, and worktree Harness 100/100 also pass.
- Real external trade-prose, `session_id=...`, and `reports/...` manifests each exit 1 with empty stdout, marker-free stderr, no output directory, and no retained probe. Fresh reports are `reports/20260722-030739-agents.md`, `reports/20260722-030746-evolution.md`, and `reports/20260722-030747-harness-smoke.md`.
- Ignored run `data/harness_eval/runs/smoke-20260721t190747z` has exactly `trace.jsonl`, `checkpoint.json`, and `harness-smoke.md`; 13 public events; final pass; zero pending steps; all four fixed report checks; and trace SHA-256 `9c7aa263d5ba4c18dea3975a4d781fb55ba350a8ff2bef83da3224d67e4c8427`.

### Next

- Keep `feat-054` `in_progress`, next, and dated `2026-07-22` until a fresh independent read-only whole-branch verifier returns PASS. `feat-056` remains pending and sole queued; no pilot or benchmark work started.

## 2026-07-22 - bounded English inflection follow-up

- Important review found that the structural scanner's English regex enumerated base forms but missed common complete-word inflections. TDD RED produced 73 loader/CLI failures for reviewer forms and hyphen variants. Commit `4fead97` now tokenizes bounded ASCII complete words and checks an explicit US/UK inflection set; it does not use broad prefix stems.
- Reviewer forms cover buy/buyer, sell/seller, trade/trader, order, authorize/authorise, authorization/authorisation, and authority singular/plural/verb forms. Hyphen compounds reject under zero-tolerance v1. Safe near-word controls `traditional`, `orderly`, and `inventory` still load; `authorised` and `authority-free` intentionally reject.
- Focused 93/93 and full 195/195 tests pass. A real subprocess loop ran all 34 reviewer forms independently: every CLI exits 1 with empty stdout, marker-free stderr, no output directory, and no retained probe. Python 3.10 parse, compileall, agent contracts, project memory, and Harness 100/100 pass.
- Fresh reports are `reports/20260722-032055-agents.md`, `reports/20260722-032056-evolution.md`, and `reports/20260722-032057-harness-smoke.md`. Run `data/harness_eval/runs/smoke-20260721t192056z` has exactly three files, 13 public events, final pass, zero pending steps, and trace SHA-256 `9161fe76eeb9408cbacdf16c548bef00a1ebba5bcf37c0a7646e0d03ce5b7c8a`.
- `feat-054` remains `in_progress`/next and dated `2026-07-22` pending a fresh independent read-only verdict. `feat-056` remains pending and sole queued; no pilot or benchmark work started.

## 2026-07-22 - final checkpoint-boundary and EOF corrections

- Commit `f2693b6` moves the 64-event capacity to one dependency-free model constant shared by trace and checkpoint validation. RED showed checkpoint save accepted both 65 and 1,000,000. GREEN accepts sequence 0 and 64 and rejects 65/1,000,000 on both save and load, preventing impossible trace/checkpoint continuity from being persisted or restored.
- The structural v1 plan's extra EOF blank line was removed; its tail is now exactly one LF. `git diff --check` passes both the current tree and the full `c75cede..HEAD` structural-review range.
- Focused 94/94 and full 196/196 tests pass. Python 3.10 parse, compileall, agent contracts, project memory, and Harness 100/100 pass. Fresh reports are `reports/20260722-033837-agents.md`, `reports/20260722-033838-evolution.md`, and `reports/20260722-033838-harness-smoke.md`.
- Run `data/harness_eval/runs/smoke-20260721t193838z` has exactly three files, 13 public events, checkpoint sequence 13, final pass, zero pending steps, all four fixed report checks, and trace SHA-256 `067e2c5d7335fa07ec9f4f59c8f7ae11baf05db04b32676ee096614abcd39e24`.
- `feat-054` remains `in_progress`/next and dated `2026-07-22` pending a fresh independent read-only verdict. `feat-056` remains pending and sole queued; no pilot or benchmark work started.

## 2026-07-22 - `feat-054` ultimate PASS and status closeout

- Ultimate independent read-only review at `d115e2e` returned PASS with Critical/Important/Minor `0/0/0`; `feat-054` is now closed `pass` and `feat-056` is pending next as the sole queued Harness experiment. Active experiments remain empty, and no pilot or benchmark work started.
- Status-transition RED exposed two stale integration assertions that still required final-hardening/`feat-054`-next state. The minimal GREEN test-contract update now requires the normative PASS status, `feat-054=pass`, and `next_feature_id=feat-056`; runtime behavior is unchanged.
- Final verification passes focused `111/111` and full `196/196` tests, Python 3.10 parsing, compileall, agent-contract and project-memory validators, Harness `100/100`, state/governance assertions, final evolution markers, and current/full-range diff checks.
- Final artifacts are `reports/20260722-034028-agents.md`, `reports/20260722-035031-evolution.md`, `reports/20260722-034029-harness-smoke.md`, and ignored run `data/harness_eval/runs/smoke-20260721t194029z`. The run has exactly three files, 13 sequential public events, checkpoint sequence 13, final pass, zero pending steps, all four fixed report assertions, and trace SHA-256 `08b5c8cfb1ffd2d779ebe71e6b019f421bb8871607e8f0cf99d3c15abb57b217`.
- This closeout proves deterministic Harness contracts only: it does not establish model-performance benefit or trade authority. The next authorized action is a separate written `feat-056` plan, not an automatic pilot or benchmark run.

## 2026-07-22 - Windows merge portability correction

- Local fast-forward integration exposed that `scripts/validate_project_memory.py` hashed the raw checkout bytes of `configs/architecture.json`. The feature worktree used LF while the main Windows checkout used CRLF, so identical Git content was incorrectly reported as a stale `docs/architecture.html` artifact.
- TDD RED proved LF and CRLF copies produced different architecture source digests. GREEN adds one shared newline-canonical digest function used by both the architecture renderer and project-memory validator; the artifact regression also normalizes checkout newlines before comparing while still requiring renderer output to be LF. No architecture payload or runtime decision behavior changed.
- Fresh serial verification passes 197/197 tests, agent-contract validation, project-memory validation, and Harness 100/100. `feat-054` remains `pass`; `feat-056` remains pending next and no pilot or benchmark was started.

## 2026-07-23 - feat-057 macro-transmission shadow activation

- The user explicitly paused `feat-056` priority and selected single-agent inline execution of the approved macro-transmission plan.
- Registered `feat-057` as the sole active experiment; `feat-056` remains pending in the queue and was not deleted or started.
- Work began in isolated branch `codex/feat-057-macro-transmission-shadow` from `30c7e6c`.
- Clean baseline: 197/197 tests passed using the existing compatible Python 3.13 dependency environment; no product code had changed at that checkpoint.
- Scope remains the diagnostic-only `energy_supply_shock`, `duration_pressure`, and `korea_import_stress` shadow plus point-in-time replay. Oil alone cannot confirm technology risk, and no shadow state may change risk lights, budgets, alerts, or trades.

## 2026-07-23 - feat-057 macro-transmission shadow PASS

- Implemented typed independent states, timezone/market-lag-safe price evaluation, verified-event parsing, no-lookahead replay, independent episode clustering, oil-only/oil-plus-rates/triple-confirmation comparisons, 5/20-session absolute and S&P-relative outcomes, threshold sensitivity, and a 60-event plus held-out-sample promotion gate.
- Added `macro_transmission` to `risk-watch` JSON/Markdown/HTML with clickable source links, as-of dates, calibration, counter-evidence, next conditions, explicit gaps, and `authority=diagnostic_only`. Isolation tests prove confirmed versus unavailable macro states do not change `latest`, budgets, actions, alerts, or event alerts.
- Product/architecture/Harness registration is current. `docs/architecture.html` was regenerated; project-memory validation passes with 26/26 commands and Harness validation is 100/100.
- Fresh verification: 218/218 full tests pass, including 13 macro state/calibration tests, four workflow integration tests, three exchange-timezone history tests, and eight existing risk-watch tests; compileall and JSON validation pass.
- Real replay generated `reports/20260723-150747-risk-watch.json`, `.md`, and `.html` for 2016-01-01 through 2026-07-23. Yahoo returned Brent, WTI, US10Y, SOX, and KOSPI but timed out for SP500 and QQQ; the payload therefore reports 5/7 sources, 0 independent triple-confirmation episodes, `insufficient_events`, energy `observe`, duration `unavailable`, and Korea `unavailable`.
- Conclusion: implementation passes, but the available live replay does not verify the proposed 2026 causal chain. The layer stays diagnostic and unpromoted; `feat-056` returns to pending next without starting its pilot.

## 2026-07-23 - feat-058 after-close decision workbench activation

- The user approved the market-first five-interface design and selected single-agent inline execution.
- `feat-058` is the sole active experiment in `codex/feat-058-after-close-decision-workbench`; `feat-056` remains pending and queued.
- Scope is bounded to existing data: one self-contained `file://` HTML workbench with Today, Holdings, Market, Research, and Review routes, explicit freshness, diagnostic-only market context, and no new provider, temperature score, holdings write, order action, or trade authority.
- Baseline before feature changes: Harness integration 15/15 and macro-transmission workflow 4/4 tests pass.

## 2026-07-23 - feat-058 implementation complete, visual acceptance pending

- Implemented the additive bounded macro trajectories, two-group diagnostic market matrix, typed workbench view, self-contained five-route HTML renderer, market-first Today route, holdings action playbooks, research/review routes, and the `after-close` CLI integration without changing the JSON/Markdown authority contract.
- The holdings detail now exposes the existing upside, flat, and downside conditions as explicit `上行确认位` / `盘整观察` / `风险触发位`; no price or level is inferred beyond the current payload.
- Fresh representative evidence using the canonical three-holding portfolio is `reports/20260723-203853-after-close.{json,md,html}`. Static QA confirms 3/3 holding-plan coverage, all five routes, action-before-levels-before-research ordering, diagnostic-only matrix authority, mobile overflow rules, holding deep links, and no raw provider exception or internal state leakage.
- Verification passes 232/232 tests, compileall, project-memory validation with 26/26 architecture commands, generated architecture parity, and Harness smoke 8/8 with public trace and checkpoint validation.
- Automated visual interaction remains unverified because the in-app Browser security policy rejects direct `file://` navigation and explicitly disallows a localhost or alternate-browser workaround. Independent multi-agent review was also not run because the user selected single-agent execution.
- Keep `feat-058` `in_progress` until the user manually opens the representative HTML and accepts desktop/mobile usability. `feat-056` remains pending and queued; no pilot or benchmark work started.

## 2026-07-24 - product status and progress report

- Generated the report-only pair `reports/20260724-120051-product-status.{md,html}` from the current feature catalog, architecture source, approved 2026-07-22 portfolio, and latest local Core artifacts. No feature status, product authority, holding data, or roadmap priority changed.
- The report records 52/58 features passed, `feat-058` as the sole active experiment, 22 architecture nodes / 28 edges, 26/26 command coverage, structural holding-action coverage 3/3, and strict decision-ready coverage 0/3. It explicitly distinguishes feature throughput from product-value validation.
- The report exposes two current restart/truth gaps: `.venv\Scripts\python.exe` is absent, and `CURRENT_STATE.md` still describes the canonical portfolio as empty/invalid even though `data/portfolio.json` contains the user-approved three-holding snapshot consumed by `reports/20260723-210049-after-close.json`.
- Fresh report verification: global Python 3.13 project-memory validation PASS; feature, architecture, and portfolio JSON parse PASS; every local HTML link resolves; all required report sections and responsive/print CSS are present; Playwright renders 1440px and 390px viewports with `scrollWidth == innerWidth`.
- This report QA does not close `feat-058`: its separate after-close workbench still requires the recorded user manual desktop/mobile UX acceptance.

## 2026-07-24 - morning brief HTML rendering

- The first attempt reused the generic long-form Markdown renderer and was rejected by the user as unusable: it added irrelevant dashboard elements and collapsed the five core sections.
- Root cause is confirmed as a renderer-contract mismatch, not empty source data: the morning brief contains all three holding values, but the generic dashboard's exact legacy parsers return zero holdings, markets, actions, and action cards because they require `券商持仓快照`, `跨市场宏观温度`, `持仓动作`, and `建议动作` grammar. Existing generic-renderer tests cover collapse/link behavior but not semantic source-to-dashboard consistency.
- Replaced `reports/20260724-085300-morning-brief.html` with a dedicated decision-first page while preserving the original output as `reports/20260724-085300-morning-brief-generic-backup.html`. No market, holding, or decision data was refreshed or changed.
- The replacement puts the yellow-light stance, four critical status fields, three holding action cards, market triggers, event timeline, and risks/gaps in open view. Static QA confirms five working navigation anchors, eight HTTPS sources, no collapsed sections, mobile/print CSS, and no broken internal anchors.
- Direct automated `file://` visual inspection remains blocked by the in-app browser URL policy, and `.venv\Scripts\python.exe` remains absent. User-side refresh and visual acceptance are still required; this report does not close `feat-058`.

## 2026-07-24 - feat-058 Windows one-click usability recovery

- Confirmed the reported usability failure with a deterministic entrypoint check: the repository root had no `.cmd`, `.bat`, `.ps1`, or `.exe` product launcher, while `.venv\Scripts\python.exe` was absent.
- Reproduced a second startup failure: direct `after-close` remained silent beyond 60 seconds. A 20-second faulthandler capture located the wait in sequential Yahoo TLS requests inside `fetch_global_market_groups`; eight independent public snapshots each accumulated their own timeout.
- Added `InsightRadar.cmd`, `生成盘后报告.cmd`, `导入持仓.cmd`, and `打开最新报告.cmd` backed by `scripts/insightradar-launcher.ps1`. The launcher resolves a usable Python, exposes generation/import/open actions, keeps errors visible, verifies a fresh HTML artifact, and opens it. Portfolio import starts the existing token-protected `127.0.0.1` preview/approval service.
- Global snapshot requests now overlap while preserving region/item order and per-source fail-closed gaps. The public-snapshot probe fell from about ten seconds at a one-second timeout to 1.67 seconds; the real no-open launcher completed in about 15 seconds and wrote `reports/20260724-170655-after-close.{json,md,html}`.
- Focused launcher, import-service contract, and global-market tests pass. `feat-058` remains `in_progress` until the user accepts the actual desktop/mobile workbench; no trading authority or provider scope changed.
- The fallback system Python initially passed 235/237 tests and lacked `scipy`. The project `.venv` was then rebuilt from the repository's Python 3.13 AmazingData/tgw wheels plus editable project dependencies. AmazingData doctor passed with 2026-07-24 calendar coverage and active permissions; a second real launcher run used `.venv`, completed in 19 seconds, and wrote `reports/20260724-171413-after-close.{json,md,html}`. Full discovery now passes 237/237.
- The restored report reduced data gaps from 12 to 5 and removed all missing-SDK gaps. It has 3/3 structural holding actions but remains 0/3 strict-ready because the approved 2026-07-22 snapshot still has blocked risk reconciliation, unknown beta classifications, missing weights, and incomplete context; the importer now lets the user correct these without an agent.

## 2026-07-24 - feat-058 loopback import application recovery

- Reproduced the user's report-button failure as a deterministic timeout to `http://127.0.0.1:8765/`; no process was listening. The report and server ports already matched, so the defect was delivery lifecycle: static `file://` HTML cannot start a Windows process, while the product entry still opened a developer menu instead of the required local app.
- `InsightRadar.cmd` now starts the loopback application directly and reuses an existing healthy instance. The app serves the latest report, exposes a token-protected stop action, and provides paste/file intake, readable old/new differences, per-holding `high_beta`/`normal`/`unknown` selectors, explicit approval, atomic save, serial Core refresh, and a latest-report link.
- Static after-close reports now say to start `InsightRadar.cmd`, label the action as opening the app, and make a best-effort clipboard copy of already pasted TSV instead of silently opening an unavailable localhost page.
- The user-provided four-row TSV was previewed without saving: all four rows parsed, weights covered 61.38%, and differences showed two added, two changed, and one removed holding. Risk reconciliation correctly remained blocked because all beta classes were unknown. No classification was inferred, approval was not checked, and no portfolio file was written.
- Real HTTP verification changed from timeout to 200; the live browser shows the pasted data, four beta selectors, disabled save-before-approval, and a readable difference table. Focused launcher/import tests pass. Fresh report evidence is `reports/20260724-172654-after-close.{json,md,html}`.

## 2026-07-24 - owner-approved 08:30 decision-loop V1 specification

- The user rejected feature count and broad market presentation as sufficient product value. A structured grilling session fixed the V1 job as remembering, revalidating, and confirming zero to three portfolio plans at 08:30 CST in under three minutes.
- Added `docs/superpowers/specs/2026-07-24-0830-decision-loop-v1-design.md`. It preserves the personal A-share decision-intelligence North Star and `Observe -> Explain -> Decide -> Verify`, while defining the Today/Holdings/Stock Lookup/Review task routes, action-first IF-THEN cards, technical-rule semantics, international-to-holding mapping, rule/AI authority, JSON AI reuse, local degradation, notification budget, and a ten-session usefulness pilot.
- V1 remains local and single-user. Continuous five-minute alerts, Redis/MySQL, hosted multi-user delivery, mobile clients, and AI strategy authority are explicitly deferred. The specification changes no runtime behavior and does not close `feat-058`; current manual workbench UX acceptance remains outstanding.

## 2026-07-24 - feat-058 selected action-brief prototype implemented

- Audited the four task routes from fresh 1440x1024 browser captures and saved the findings plus evidence under `.superpowers/brainstorm/0830-decision-loop-v1/audit-2026-07-24/`.
- The owner selected the action-brief direction, rejected the prior green-dominant financial palette, and approved a blue-black default with restrained vermilion, amber, cool-blue, and warm-white semantic emphasis.
- Updated `today-prototype.html`: the Today route now leads with a compact two-driver market constraint, makes `今日需要确认 3 项` the primary anchor, shows one dominant rule-complete decision plus two compact decisions, keeps evidence in drawers, and provides working individual and confirm-all actions. Holdings, Stock Lookup, and Review share the new visual tokens; A-share up candles are red and down candles cool blue.
- Browser verification passed at 1440x1024 and 390x844 across all four routes with no horizontal overflow. Confirm-all, all-market evidence, holdings filtering, stock lookup, and review detail interactions passed; browser diagnostic logs were empty.
- The first QA iteration found the prototype switcher obscuring the confirmation footer and mobile decision card. It was moved into the desktop sidebar and hidden below 820px; the mobile market constraint was compressed to two columns. `design-qa.md` now records `final result: passed`.
- This remains a fixed-data throwaway prototype and does not change report generation, canonical JSON/Markdown contracts, portfolio safety, AI authority, runtime completion, or trade authority. `feat-058` remains `in_progress` pending owner inspection and bounded runtime integration.

## 2026-07-24 - feat-058 decision-response and theme-temperature prototype refinement

- The owner approved a second prototype refinement: a morning draft can now be accepted, disputed, rejected, or deferred. Structured objections preserve the generated rule version and do not activate new opportunity alerts; batch acceptance changes only untouched plans.
- The Today route now exposes a labelled V2 alert-handoff preview. Accepted plans attach to the preview; an unaccepted morning draft falls back to the previous accepted baseline and only retains existing risk-invalidation monitoring. No five-minute poller or delivery runtime was implemented.
- Stock Lookup now separates the Shanghai Composite market-risk gate from the automatically selected board benchmark and includes both in the machine-testable IF condition. Review adds honest point-in-time backtest readiness fields that remain `待跑`/`样本不足` instead of inventing performance.
- Added a secondary `theme` route for AI-hardware temperature. It uses nine declared ETF proxies, a transparent cross-sectional median, 35/80 floor-ceiling orientation, and a rule contract that treats low temperature as a candidate observation zone requiring breadth, relative-strength, and Shanghai-risk confirmation.
- Browser verification passed at 1280px desktop and 390x844 mobile. All checked routes had `scrollWidth <= innerWidth`; structured objection save, accepted-plan alert attachment, theme navigation/chart, holdings, lookup, review, and backtest-detail entry worked, and browser diagnostics were empty.
- Updated the V1 specification, prototype README, product-state memory, current-state snapshot, feature evidence, and handoff. `feat-058` remains `in_progress`; this fixed-data prototype changes no canonical report contract, runtime alert authority, or trading authority.

## 2026-07-25 - feat-058 P0 runtime integration ready for owner acceptance

- Implemented only the delivery prompt's P0 scope. `decision-workspace/v1` is additive to the existing after-close JSON and carries effective date, stage, source health, market gate, real portfolio positions, zero-to-three changed plans, response state, local plan-version history, provenance, and an explicit unimplemented-monitor boundary.
- Replaced the report shell with a loopback-served red/white four-route workspace: Today, Portfolio Risk, Research, and Review. Market evidence is a drawer rather than another primary route. Today supports accept, dispute, reject, and defer; unaccepted plans never enter the monitor handoff.
- The portfolio importer remains approval-gated and local. Morning recheck only restages freshness from the same source report; it does not claim a live market refresh. Runtime state is tied to `source_generated_at`, so an older morning state cannot mask a newer after-close artifact.
- Quiet JSONL plan history writes only new content-addressed versions. Response records are version scoped and atomically persisted. Unknown portfolio fields remain unknown; source gaps render as `stale`, `missing`, or `blocked`; no fake data or trade authority was added.
- Final real artifact: `reports/20260725-000005-after-close.{json,md,html}`. It contains four real positions, six explicit data-health rows, zero simulated rows, three displayed plan changes, and four version-history entries.
- Verification passes 247/247 tests, compileall, project-memory validation, desktop viewports 1920/1440/1366, mobile 390x844, controlled table overflow, working response/drawer/navigation/morning-restage interactions, source-versus-implementation image comparisons, and a clean final browser console.
- `feat-058` remains `in_progress` only for owner acceptance. P1 research orchestration/history-center work and P2 five-minute monitoring/notifications were not started.

## 2026-07-25 - feat-058 strict V3 prototype alignment

- Treated `%USERPROFILE%\Downloads\InsightRadar-V3-交付包\InsightRadar-V3-delivery\InsightRadar-重构原型-v3.html` as the sole visual source and rebuilt the P0 runtime shell to match its blue-black palette, 228 px sidebar, four task routes, runtime strip, market gate, theme line, dominant-plan hierarchy, evidence rail, portfolio cockpit, lookup layout, review ledger, data drawer, and mobile bottom navigation.
- Preserved runtime truth boundaries: the prototype's sample scores, sample securities, fixed timestamps, and simulated technical chart were not copied. The current page uses four real positions, three real plan changes, six typed source-health entries, zero simulated rows, and an explicit P1 technical-chart/research-orchestration gap.
- Fixed initial hash deep links so `/#portfolio` selects the requested route without scrolling the topbar out of view. Added DOM-visible runtime error counting for browser verification and regression tests for the V3 shell, source route ids, and no-simulated-chart boundary.
- Fresh artifact: `reports/20260725-003439-after-close.{json,md,html}`. The loopback app serves it at `http://127.0.0.1:8765/`.
- Browser QA covered Today, Portfolio, Lookup, Review, the data drawer, plan disclosure, filter, research intent, tabs, deep links, focus restoration, and 1920x1080, 1440x900, 1366x768, and 390x844 layouts with no document-level horizontal overflow. Same-viewport reference/implementation comparisons are under `tmp/v3-strict-match/`; `design-qa.md` records `final result: passed`.
- P1 and P2 remain unstarted. `feat-058` remains `in_progress` for owner acceptance.

## 2026-07-25 - feat-058 final P0 state-consistency repair

- Kept the frozen four-route V3 structure and visual direction unchanged. The Today queue now equals the set of active plans that are both actionable and `pending`; it is no longer capped at three. The real artifact has four positions and four active plans, with three pending items because ????A already has a version-matched `deferred` response; pending ????D is present in Today.
- Blocked plans can no longer be accepted. The UI exposes `确认已知悉阻断`, dispute, defer, and old-plan rejection; the domain ledger and loopback API reject `accepted` against the server-resolved blocked status. Acknowledgement does not create an effective plan or monitor eligibility.
- Version rendering now distinguishes `首次生成`, true version/rule changes, and an execution-only state change. Matching version and rules render `计划内容未变，执行状态变为 blocked` instead of a false old-to-new diff.
- Fresh artifact: `reports/20260725-010125-after-close.{json,md,html}`. Full discovery passes 250/250 tests, compileall passes, and browser checks across Today, Portfolio, Lookup, and Review report zero captured runtime errors and zero console errors.
- No P1/P2 work, information-architecture change, new product feature, forced blocked override, or trade authority was added. `feat-058` remains `in_progress` until owner acceptance freezes the pilot version.

## 2026-07-25 - InsightRadar V3.0 Pilot scope frozen

- The owner accepted P0 and formally marked the product **InsightRadar V3.0 Pilot — Scope Frozen**.
- ADR-0010 freezes the Today, Portfolio, Lookup, and Review information architecture, the `Observe -> Explain -> Decide -> Verify` loop, and the rule/user/AI/trade responsibility boundary for ten consecutive real morning trials.
- During the trial, only data errors, plan mismatches, state-persistence failures, security issues, and core-flow blockers are admitted. Ordinary experience suggestions are logged without implementation. P1 research/backtest orchestration and P2 five-minute alerts remain unstarted.
- Updated the external review package with current frozen-state documentation, a production-rendered all-synthetic interactive HTML, four synthetic screenshots, current verification evidence, privacy notes, and a ten-run trial template. `PRODUCT_VERSION.md`, project memory, feature evidence, and handoff now record the frozen status.

## 2026-07-25 - Public V3 baseline prepared

- Froze the code-derived product baseline without changing runtime behavior: V3 keeps exactly four first-level tasks (`today`, `portfolio`, `lookup`, and `review`), while market evidence remains an upstream constraint/drawer rather than a fifth route.
- Added the baseline, frozen-version, V3.1 delta, architecture, decision-log, and data-boundary documents. V3.1 items are explicitly marked implemented, partial, not implemented, or pending confirmation; no V3.1 runtime work started.
- Completed a repository and 98-commit history audit for high-confidence secrets, account artifacts, private databases, real screenshots, logs, caches, and large files. No high-confidence secret was found. The legacy history contains personal author identity and local paths, so ADR-0011 requires a fresh sanitized public history while retaining the legacy history locally.
- Sanitized current documentation paths and historical account-linked examples, expanded `.gitignore`, and kept real portfolio data, account state, reports, runtime ledgers, caches, and generated artifacts outside the public candidate.
- Verification on Python 3.13.3: dependency install/check, compileall, project-memory validation, 250/250 tests, isolated sdist/wheel build, a real `after-close` run, and loopback HTTP/browser checks all pass. The fresh private artifact is `reports/20260725-160125-after-close.{json,md,html}` and remains untracked.
- The live `127.0.0.1:8765` service returns 200 for the workspace and importer, serves `decision-workspace/v1`, rejects an unauthenticated write with 403, switches across all four routes, and reports zero browser console errors.
- Ruff and Mypy are audit-only in this baseline because the repository has no committed lint/type configuration. Ruff reports 301 findings (including one undefined `json` name in `stock_assist/workflows/agent_roster.py`); Mypy reports 377 errors across 37 files. These are recorded as pre-existing debt and were not hidden by changing business code.
- `feat-058` remains `in_progress` for the ten-run frozen pilot. This baseline publication does not authorize P1, P2, automatic trading, or product redesign.

## 2026-07-28 - approved portfolio refresh and after-close null-contract repair

- Imported an owner-approved private broker snapshot through the existing preview/approval gate. The prior `portfolio.json` and `risk_watch_profile.json` were timestamp-backed up; beta classifications remain `unknown`, portfolio values remain private, and risk reconciliation remains visibly blocked.
- Ran the Core monitors serially and generated fresh risk-watch, market-pulse, market-levels, ai-capex-watch, and final after-close JSON/Markdown/HTML artifacts. The exact private artifact remains local and ignored.
- Reproduced a final-render blocker where an unavailable anchor-structure source produced `technology_definition: null` and `render_unified_decision_markdown()` attempted to iterate it. Added a focused regression test and normalized only that optional field to an empty iterable; no rule, risk budget, holding action, or trade authority changed.
- Focused unified-decision and after-close reliability tests pass. The generated result remains strictly blocked because beta/risk reconciliation and holding context are incomplete.
- Pilot observations retained for follow-up rather than hidden: one provider series appears to use an incompatible split/adjustment basis, and the Today headline could select a medium-priority item before a high-priority holding risk. Treat both as data/plan-mapping defects covered by synthetic minimal reproductions.

## 2026-07-30 - latest risk-card prototype implemented for owner review

- Created `codex/risk-card-workbench` and implemented the owner's latest prototype direction without promoting it into the frozen V3.0 baseline.
- Upgraded Today into a single-action command surface: real workflow stages, one primary pending or blocked plan, the four-layer authority chain, holding impact, evidence/risk context, and a compact remaining-plan queue.
- Upgraded Review into a decision-value workbench with core decision, exposure, and market modes plus 20/60/90/250-day controls. The current data contract truthfully renders decision value, drawdown change, execution deviation, account path, and baseline attribution as `unknown` or `blocked`.
- Preserved the frozen four routes and the existing Portfolio and Lookup implementations. No fifth route, automatic trading, prototype return value, simulated chart, or synthetic runtime capability was added.
- Fixed the evidence-strength computation to count matured T+20 decision episodes rather than summing overlapping T+1/T+5/T+20 signal windows.
- Fresh private verification artifacts were generated locally. Sanitized visual and responsive results are recorded in `design-qa.md`; raw captures remain outside the public repository.
- Owner visual review is the remaining acceptance step; `feat-058` stays `in_progress`, and the frozen V3.0 Pilot status is unchanged.

## 2026-07-30 - feat-058 P0 blocked-state and data-contract repair

- Reproduced the unusable real state: acknowledging all four blocked plan versions removed them from the pending queue, so Today appeared empty even though the blockers were unresolved.
- Added a separate `today_plans` attention lane and `blocked_waiting` runtime state. A blocked acknowledgement remains visible as `继续等待`, cannot create an effective plan, and cannot enter monitoring or trade authority.
- Replaced blanket blocker copying with structured per-plan mapping while retaining genuinely portfolio-wide risk-reconciliation constraints. High-priority holding risks now sort before medium-priority plans.
- Preserved nested authoritative `source_time` independently from report `generated_at`; stale market-pulse and market-level evidence now shows its real 2026-07-28 15:00 source time plus a repair action, owner, and next check.
- Added a price-basis guard and quarantined an incompatible historical threshold from Review instead of scoring it. The signal now exits tracked, matured, hit-rate, and average-effect aggregates; Review also disables its unavailable mode and horizon controls.
- A final private artifact confirmed that unresolved blocked plans remain visible, pending-response counts stay separate, strict readiness remains fail-closed, and quarantined history does not affect outcome aggregates.
- Verification passed: 42 focused tests, 260/260 full tests, compileall, project-memory validation, JSON validation, `git diff --check`, final desktop/mobile browser navigation and data-drawer checks, no document-level horizontal overflow, and zero browser warnings/errors. Source/runtime comparisons and the P0-P2 audit are in `design-qa.md`.
- The independent product reviewer returned REVISE when the first quarantine label still contaminated outcome aggregates. After the statistical exclusion and regression test were added, the same reviewer returned PASS with no blocking finding. Its remaining non-blocking suggestion is also covered: an explicit upstream quarantine without a reason now remains fail-closed.
- `feat-058` remains `in_progress` for owner re-review. No P1 research orchestration, P2 five-minute monitoring, fifth route, automatic trading, or public deployment was added.

## 2026-07-30 - feat-058 decision evidence and local refresh service repair

- Recorded the bounded P0 implementation plan in `docs/superpowers/plans/2026-07-30-risk-card-decision-service-p0.md` and committed it separately as `3a35549`; the initial technical-decision implementation was committed as `6aad17c`.
- Added a provider-independent holding decision module. Cost and account P&L are now `reference_only`; completed daily bars determine MA20/MA60, slope, prior-20-day structure, ATR14, volume ratio, technical state, board-limit reachability, and complete repair/risk/wait branches.
- Synthetic regression fixtures now prove that completed-bar structure drives repair/risk confirmation instead of cost or a fixed multiplier. Current weak-state UI says `降低仓位复核`; the repair action remains a separate conditional branch.
- Added a decision-evidence contract with stable evidence ids, supports/opposes, counter-evidence, gaps, authority, plan linkage, and a concise conclusion: market stance, technology style, dividend style, risk score, major market level, industry transmission, and style evidence. Decision evidence and source-health repair remain separate drawers.
- Portfolio import now atomically saves first and returns immediately with a background refresh id. A single-flight SQLite coordinator runs `market-levels -> risk-watch -> market-pulse -> style-rotation -> ai-capex-watch -> after-close`, persists step/error/restart state, and lets the UI poll or recover after reload. The workbench exposes stale-only and full refresh controls.
- Browser QA against the real loopback service verified the four frozen routes, evidence drawer, data-health drawer, stale-source refresh `0/2 -> 1/2 -> automatic reload`, and the separate importer page. The refresh reduced limited sources from two to one without freezing the page.
- Independent product re-review initially returned `REVISE` and identified four P0 gaps. The final implementation now computes blockers from `current_action`, quarantines undeclared >35% one-bar adjustment discontinuities, derives the top-level context gap from the same reliability predicate, and refuses refresh completion unless every step creates a new parseable artifact and final after-close creates a same-stem triplet bound to the saved `portfolio_version`.
- A fresh private artifact confirmed that stale-only refresh can complete as one `after-close` step and SQLite binds the exact triplet to its matching `portfolio_version`; quarantined data remains blocked rather than ready. `feat-058` remains `in_progress` for owner re-review and the ten-run Pilot; there is still no automatic trade authority, fifth route, cloud dependency, or P1/P2 expansion.
