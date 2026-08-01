# InsightRadar Harness

This document adapts Harness Engineering to InsightRadar. The canonical checkout and active project context use `InsightRadar`; the internal Python package remains `stock_assist`, and legacy CLI aliases remain compatible. Keep it light: use the full loop for multi-file workflow changes, data-source changes, report generation changes, and recurring automation changes. For small copy or config edits, read AGENTS.md, make the edit, and run the narrowest relevant check.

## Operating Loop

1. Orient
   - Read AGENTS.md.
   - Read `PROJECT_MEMORY.md` and `CURRENT_STATE.md`, then load only the topic matching the task.
   - Check `git status --short --branch` and recent `git log --oneline -10`.
   - Query the exact feature in `feature_list.json`, its matching recent history, and the relevant contract in this file. Do not load append-only history wholesale.
2. Plan
   - Define the smallest useful increment.
   - Name the affected workflow, data source, report, or automation.
   - Write concrete pass/fail checks before editing.
3. Execute
   - Read target files before editing.
   - Keep changes scoped to one logical concern.
   - Prefer additive behavior over replacing working paths.
4. Verify
   - Run `.\.venv\Scripts\python -m compileall stock_assist`.
   - For report changes, run `.\.venv\Scripts\python -m stock_assist.cli after-close`.
   - For AmazingData changes, run SDK checks serially, never in parallel on the same account.
   - For HTML report changes, verify the expected `.json` payload when a workflow has one, plus `.md` and `.html` under `reports/`.
5. Review
   - Re-read modified files.
   - Check generated output for user-facing Chinese readability, source links, and explicit data gaps.
   - Run the smallest relevant workflow again if review finds a behavioral issue.
6. Handoff
   - Update `feature_list.json` status only; do not delete feature descriptions.
   - If a durable project fact or design decision changed, update its memory topic before changing the index pointer.
   - Refresh `CURRENT_STATE.md` when the verified baseline, next feature, blockers, or product direction changed.
   - Summarize generated report paths and commands run.

## Project Memory Contract

Done means:

- `PROJECT_MEMORY.md` remains a bounded routing index, not a transcript dump.
- `CURRENT_STATE.md` remains a bounded startup snapshot under 120 lines and 16 KB, with a valid pending or in-progress `next_feature_id`.
- Detailed project facts live in `docs/memory/*.md` and link to canonical code/config/state files.
- Product scope and Core/Lab/Satellite/Extension boundaries live in `docs/product-charter.md`; durable changes require an ADR.
- `progress.md` and `session-handoff.md` remain chronological evidence loaded by feature id/date/tail, not always-on context.
- Every indexed topic and source exists.
- Generated memory-sensitive assets are not older than their source configuration.
- Every `ProductCommand` is represented in `configs/architecture.json` and the topology is regenerated after graph changes.

Minimum checks:

- `.venv\Scripts\python scripts\validate_project_memory.py`
- `.venv\Scripts\python -m stock_assist.cli architecture-view` when architecture sources change
- `node "$env:USERPROFILE\.codex\skills\harness-creator\scripts\validate-harness.mjs" --target D:\work\InsightRadar`

### Product Continuity

Done means:

- New sessions can recover product direction, verified baseline, blockers, and next work from bounded startup files without reading full history.
- Every capability is classified as Core, Lab, Satellite, Extension, or Governance in `docs/product-charter.md`.
- Optional extensions cannot become an implicit dependency of the A-share core.
- A repository/service split occurs only for an independent lifecycle, security boundary, scaling need, runtime conflict, or stable payload contract.
- Product-level success is measured by decision-ready holding coverage and outcome calibration, not raw feature count.
- During an expansion freeze, the next feature must improve the Core loop; parked Lab/Extension work cannot become active without an ADR or explicit user reprioritization.
- A satellite extraction is complete only after the standalone repository owns its external runtime state and rollback has been verified; an export ZIP alone is not cutover.

Minimum checks:

- `.venv\Scripts\python scripts\validate_project_memory.py`
- `.venv\Scripts\python -m json.tool feature_list.json`
- `node "$env:USERPROFILE\.codex\skills\harness-creator\scripts\validate-harness.mjs" --target D:\work\InsightRadar`

## Sprint Contracts

### Product Foundation

Done means:

- User-facing surfaces call the product `InsightRadar`.
- CLI help exposes product modules and keeps `insight-radar`, `shenyan-radar`, and `stock-assist` compatible.
- `stock_assist/product.py` remains the source of truth for module boundaries, CLI workflow ownership, and data/config classification.
- `product-map` generates a fresh Markdown product map under `reports/`.
- README and handoff docs distinguish product config, private runtime data, templates/schemas, and generated output.

Minimum checks:

- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m stock_assist.cli product-map`
- `.\.venv\Scripts\insight-radar.exe --help`
- `.\.venv\Scripts\python -m json.tool feature_list.json`

### After-Close Report

Done means:

- Markdown report is still generated.
- JSON payload is generated with the same timestamp as the Markdown and HTML reports.
- `reports/*-after-close.json` is the Portfolio Intelligence contract for future native clients; Markdown and HTML remain renderers.
- HTML report is generated with the same timestamp when expected.
- The after-close HTML preserves the four frozen first-level tasks with `today`, `portfolio`, `lookup`, and `review` routes; market and evidence context stay inside those tasks instead of becoming a fifth route.
- Holding technical plans treat broker cost as `reference_only`. For identical OHLCV, cost changes cannot alter the technical state or levels. Plans use moving-average plus price-structure evidence, expose available volatility/volume evidence, and provide repair, risk-reduction review, and continue-waiting branches with persistence and invalidation. A greater-than-35% single-bar discontinuity with an undeclared adjustment basis is quarantined; its MA/support/resistance cannot enter decision evidence as ready.
- Decision evidence uses stable ids and states the claim, change, supported/opposed conclusion, plan impact, counter-evidence, gaps, source time, freshness, and linked plan. Decision evidence and source health use separate drawers.
- `today` is the conclusion and action entry layer. In `after_close` and `weekend` phases it renders three columns: deterministic account/market changes, one unified priority list for position and verified-opportunity attention, and rule decisions with fail-closed response controls. It does not duplicate the full Portfolio, Lookup, or Review detail surfaces.
- `today` account P&L, intraday peak, giveback, attribution, ordering, data-quality state, and monitor eligibility come from typed structured data plus deterministic rules. Natural-language templates and future AI extraction cannot calculate or override them.
- The four route ids remain `today`, `portfolio`, `lookup`, and `review`; their first-level labels are 今日工作台、组合风险、标的研究、复盘账本. No risk-command or market-summary fifth route is allowed.
- Matrix cards use explicit states, changes, bounded trajectories, dates, freshness, and diagnostic authority; no uncalibrated 0-100 temperature score is allowed.
- A holding action playbook appears before price charts or research evidence.
- Stale, unavailable, and blocked states remain distinct; raw provider exceptions stay out of normal routes.
- Direct `file://` use, 1440x900 desktop, and 390px mobile must pass route, overflow, and console checks.
- Long evidence is routed to the evidence drawer, `lookup`, and `review` so the first screen remains a decision surface rather than a wall of text.
- Missing data remains explicit in freshness badges, unavailable matrix cards, holding blockers, and the market audit disclosure.
- JSON exposes separate structural-action and strict decision-ready coverage. Strict readiness requires a dated current holding snapshot, complete position fields, review context, evaluated market data, and all conditional action branches.
- Placeholder text such as `暂无` is not counted as a real gap, while absent broker fields remain explicit and must render as `未提供` rather than numeric zero.
- Manual broker holdings can be previewed through the loopback-only `portfolio-import` service. The parser must prefer `当前持仓` over `股票余额`, show validation plus old/new diffs, and require explicit approval before atomically replacing canonical `data/portfolio.json`; static reports must never silently overwrite holdings, write browser downloads, or transmit the table.
- Portfolio import must preserve missing shares/cost/price/P&L/weight as null and never infer beta class from a ticker, name, or industry. After the approved snapshot is atomically saved, `portfolio-beta` deterministically calculates simple daily-return beta against `000300.SH` over 120 sessions with at least 60 valid observations. It records beta, R², benchmark, window, observations, as-of, source, data quality, and fit quality; stale, insufficient, failed, or non-finite evidence stays `unknown` and keeps risk reconciliation blocked. A successful import returns HTTP 202 with a durable local refresh id, then runs `portfolio-beta`, `market-levels`, `risk-watch`, `market-pulse`, `style-rotation`, `ai-capex-watch`, and `after-close` sequentially in one background task. Duplicate clicks reuse the active task, page reload restores its status, exact workflow failures remain visible, and the saved portfolio plus last-good report are preserved. Because `portfolio-beta` updates the canonical evidence, the refresh coordinator rebinds final artifact validation to the new `portfolio_version`. A step is successful only after a new parseable artifact exists; final completion additionally requires a same-stem JSON/Markdown/HTML triplet whose embedded `portfolio_version` matches the saved snapshot. It never places an order.
- Holdings actions are conditional, not deterministic orders.
- Percentage trims are advisory targets until shares and availability are known. Executable quantities use 100-share board-lot flooring, never exceed the requested or available quantity, and show zero plus a manual-choice blocker when a small position cannot satisfy the percentage target in one board lot.
- Holding guidance must be execution-oriented: include position action, upside trigger, downside trigger, flat-market handling, and next-day priority. Avoid vague internal wording such as "trend did not give a strong signal".
- JSON exposes `unified_decision` built from the latest `risk-watch`, `market-pulse`, `market-levels`, `style-rotation`, and `ai-capex-watch` payloads. It includes `plan_date`, `stance`, `first_action`, `risk_budget`, diagnostic market-regime scores, support/confirmation/resistance zones, an intraday watchlist, four opening/upside/flat/downside scenarios, blocked actions, unlock conditions, source freshness, and decision-specific gaps.
- `unified_decision.market_regime` is a persisted close-finalized score state machine with formal/candidate scores, bounded daily delta, auditable rule ledger, evidence source/as-of, triggered and blocked rule ids, hysteresis/deduplication state, calibration status, and finalization time. Pre-open, intraday, and midday observations may update candidates only; the close window alone finalizes the formal score. Red risk or hard-risk vetoes block budget upgrades.
- `unified_decision.market_levels` exposes the current value, support/confirmation/resistance/repair bounds, relation and signed distance. `market_level_impact` must materially constrain stance or risk budget through explicit `support_testing`, `support_failed`, `repair_confirmed`, or `breakout_confirmed` states instead of rendering decorative levels.
- The portfolio-risk evidence panels retain detailed regime, level, breadth, freshness, source, and audit evidence without crowding the `today` decision surface. Bear-bull, fear-greed, crowding, and fixed-anchor cumulative width must show units/as-of dates and remain labelled diagnostic/unbacktested until calibrated; a low score is not a bottom signal.
- The unified decision also exposes `market_structure` from risk-watch: a declared 2024-09-24 anchor, listing-date eligible denominator, provider-adjusted interval returns, coverage, below-anchor count/share, equal-weight and median-stock equivalent points, and a 3900-stock claim audit. The first screen must distinguish cumulative anchor width from current short-term risk.
- Equivalent points are never described as official index levels. Missing or sub-threshold cross-section coverage fails the stock-count claim closed and cannot alter actions.
- A red/orange risk budget or a missing risk report fails closed on adding exposure; missing broker fields remain `NA` and cannot remove the holding from dashboard counts.
- State-team and industry evidence may constrain or preserve confidence, but cannot override the risk budget, identify the current ETF seller, or independently authorize a style-rotation trade.
- Fresh A-share filings prioritize CNInfo before AmazingData structured confirmation.
- Generated links remain clickable in HTML.

Minimum checks:

- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m unittest -v tests.test_today_workbench tests.test_decision_workspace tests.test_after_close_workbench`
- `.\.venv\Scripts\python -m stock_assist.cli after-close`
- Inspect the newest `reports/*-after-close.json`, `reports/*-after-close.md`, and `reports/*-after-close.html`.
- Inspect the JSON payload for `schema_version`, `summary_cards`, `components`, `sections`, `actions`, `unified_decision`, `unified_decision.market_regime.score_ledger`, `unified_decision.market_level_impact`, `unified_decision.style_rotation`, `unified_decision.holding_execution_plans`, `unified_decision.market_structure`, `reliability`, and `data_gaps`.
- For dashboard layout changes, run a browser/Playwright check for key visual blocks and no horizontal overflow. If local `file://` navigation is policy-blocked, record that gap and fall back to static DOM/CSS/interaction-contract assertions without routing through another browser surface.

### Data Sources

Done means:

- `.env` secrets are not printed or committed.
- `data/portfolio.manual.tsv` is private runtime data; commit only `data/portfolio.manual.example.tsv`.
- AmazingData cache writes to a project-local path.
- Non-positive daily close values are excluded from latest close and moving-average calculations.
- Same-evening filings can be found by querying CNInfo through tomorrow.

Minimum checks:

- `.\.venv\Scripts\python -m stock_assist.data_sources.xysz doctor --code 000001.SZ`
- For filing work, verify a known filing symbol such as `002240.SZ` against CNInfo.

### AI CapEx Watch

Done means:

- `ai-capex-watch` generates JSON, Markdown, and HTML with one timestamp and clickable official-source links.
- Only evidence dated on or before the scoring date, within the configured freshness window, and labelled `official` can affect scores.
- The report separates hyperscaler CapEx momentum, optical-network transmission, and supplier financial realization; missing transmission links remain explicit gaps.
- Sparse evidence is shrunk toward neutral, and different CapEx definitions/fiscal periods are not summed into a false comparable total.
- Conclusions change industry-thesis confidence only. They cannot override `risk-watch` budgets, external-view firewalls, or trigger trades.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_ai_capex_watch -v`
- `.\.venv\Scripts\python -m stock_assist.cli ai-capex-watch --as-of YYYY-MM-DD`
- Inspect the generated payload for `metrics`, `companies`, `optical_evidence`, `supplier_checks`, `actions`, and `data_gaps`.

### Macro Transmission Shadow

Done means:

- `risk-watch` JSON exposes separate `energy_supply_shock`, `duration_pressure`, and `korea_import_stress` state objects with `authority=diagnostic_only`.
- Oil-only evidence remains `observe`. Duration confirmation requires an oil threshold, verified primary-source supply evidence, a yield rise, QQQ relative weakness, and SOX relative weakness.
- Korea confirmation requires verified energy/import evidence plus KOSPI relative weakness; an energy invalidation does not silently manufacture a technology or Korea repair signal.
- Replay exposes the independent event count and 5/20-session absolute and S&P-relative outcomes for QQQ, SOX, and KOSPI, including unavailable forward observations.
- Fewer than 60 independent episodes, or a missing held-out sample, cannot promote the layer above diagnostic-only.
- Macro state cannot change the risk score, risk budget, actions, alerts, strict decision readiness, or any trading authority.
- JSON, Markdown, and HTML preserve source URLs, source as-of dates, calibration status, counter-evidence, and explicit data gaps.

Minimum checks:

- `.\.venv\Scripts\python -m unittest discover -s tests -p test_macro_transmission.py -v`
- `.\.venv\Scripts\python -m unittest discover -s tests -p test_macro_transmission_workflow.py -v`
- `.\.venv\Scripts\python -m stock_assist.cli risk-watch --as-of YYYY-MM-DD --replay-start YYYY-MM-DD`
- Inspect the generated triplet for `macro_transmission.authority`, the three independent state objects, calibration event count, source links, counter-evidence, and data gaps.

### A-Share Market Pulse

Done means:

- `market-pulse` generates JSON payload, Markdown, and HTML with the same timestamp.
- `reports/*-market-pulse.json` is the product contract for future iOS, Android, Windows, and Web App clients; Markdown and HTML are renderers of that payload.
- Galaxy AmazingData `query_snapshot` is the priority source for intraday index and ETF snapshots.
- Public Eastmoney intraday data is only a fallback; source/fallback details belong in `data/market_pulse_sources.jsonl`, not normal report cards.
- Outside the A-share live session, the realtime AmazingData SDK is skipped instead of being allowed to block indefinitely; bounded public fallback failures must still produce a report and explicit gaps.
- The report keeps a PPT-style, conclusion-first card layout: direction, score, strongest/weakest style, index temperature, ETF support proxy, futures basis, state-team ETF proxy, and data gaps.
- Futures basis first uses a bounded Iwencai OpenAPI completed-close adapter that resolves one shared spot date, discovers active IF/IH/IC/IM contracts from actual provider rows, rejects expired zero-open-interest contracts, and records volume/open interest/available daily open-interest change. During the live session, a stale Iwencai close is rejected and the existing serial AmazingData snapshot adapter remains the realtime fallback.
- Completed-close basis has no fabricated four-minute change and stays diagnostic-only; provider/date/field failures remain explicit gaps, credentials never enter payloads, and source details stay in the backend audit log.
- The state-team proxy uses AmazingData ETF total-share history plus dated public annual-report holdings for four CSI 300 ETFs. It reports `max(disclosed Huijin units - current ETF total units, 0)` as a hard lower bound, compares current totals with 2023-03/08/10 baselines, and retains source URLs in every row.
- The same proxy reports aggregate and per-product changes over the latest 1/5/20 observations, the resulting change in the provable lower bound, and mixed structures such as short-term replenishment inside a still-contracting 20-observation window.
- ETF lower-bound exits must not be described as cash net selling, direct underlying-stock selling, or complete coverage of the 2015 rescue book; in-kind redemptions, position transfers, direct stock holdings, and the unfinished 2026 interim-report check remain visible boundaries.
- The active workday monitor compares prior `market-pulse` artifacts and only escalates a state-team note when the share date, cumulative lower bound, short/medium structure, or disclosed holding changes; unchanged dates stay concise.
- Futures volume/open interest are visible when the verified Iwencai adapter provides them. Long/short seat structure, basis historical percentile, intraday state-team ETF activity, breadth, limit-up/limit-down, industry rotation, subscription/redemption, and ETF premium/discount must remain explicit gaps until real adapters are verified.
- Browser QA checks desktop and about 390px mobile width for overflow before marking HTML changes done.

Minimum checks:

- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m json.tool configs\a_share_pulse.json`
- `.\.venv\Scripts\python -m stock_assist.cli market-pulse`
- Inspect newest `reports/*-market-pulse.json` for `schema_version`, `components`, `summary_cards`, `futures_basis`, `basis_actions`, `state_team_etf_proxy`, `state_team_etfs`, and `data_gaps`.
- Inspect newest `reports/*-market-pulse.md` and `reports/*-market-pulse.html` for clean product copy and data gaps.
- Inspect `data/market_pulse_sources.jsonl` for traceable source/audit entries.

### Evolution Backlog

Done means:

- `evolve` scans business reports, not its own previous evolution reports.
- Existing project capabilities reduce obsolete backlog items instead of repeating stale gaps.
- New backlog items are concrete enough to implement in the next small sprint.

Minimum checks:

- `.\.venv\Scripts\python -m stock_assist.cli evolve`
- Inspect the newest `reports/*-evolution.md`.

### Agent Harness Bootstrap (`feat-054`)

Done means:

- Product governance permits at most one active and two queued experiments; only the human owner or lead after explicit approval changes experiment state.
- `evolve` reads the complete feature catalog, exposes experiment capacity, and never starts, completes, or reprioritizes work.
- The roster has exactly one human owner, one default lead, and four self-targeting project-scoped runtime identities. The four matching task-agent TOML contracts are read-only, non-recursive, and subordinate to lead-only workspace writes; `agents` fails closed on roster or contract drift.
- Versioned task, trace, privacy, failure, and checkpoint contracts use Python 3.10 standard-library code and do not depend on a model or network call. Manifest starting-state references, identifiers, containers, numbers, and file reads are bounded and reproducible.
- Traces contain structured events and artifact references, never secrets or hidden chain-of-thought. Shared public validation scans normalized keys and every bounded string. Deterministic path-token parsing rejects Windows drive, UNC/device, and POSIX absolute tokens even when immediately preceded by Chinese text, while preserving bounded relative runtime-artifact references and ordinary spaced slash prose. V1 uses structural fail-closed validation rather than semantic negation or conjunction parsing: manifest free text (`title` and `goal`) rejects every configured English or Chinese trade-action/authority lexeme, including negated prose and hyphen compounds. English matching tokenizes bounded complete words and checks an explicit inflection set rather than broad prefixes, so `buyer`, `sellers`, `traded`, `ordering`, US/UK authorization forms, and plurals reject while unrelated near-words such as `traditional`, `orderly`, and `inventory` remain valid. Safety and no-trade assertions belong only in approved structured acceptance checks and the fixed Harness boundary. Every public or sanitized string rejects normalized sensitive assignments followed by `=` or `:`, credentials, holdings/positions/shares, broker exports or accounts, account identifiers, cost basis, personal risk, portfolio/risk profiles, raw conversations, and reasoning phrases without echoing input. PUBLIC project input references use an allowlist: only `.codex/agents/`, `configs/`, `docs/`, `stock_assist/`, and `tests/`, plus exact root files `AGENTS.md`, `PROJECT_MEMORY.md`, `CURRENT_STATE.md`, `feature_list.json`, `progress.md`, and `session-handoff.md`; `data/`, `reports/`, portfolio, broker, risk-profile, and other roots are rejected. PRIVATE manifests retain generic bounded relative references.
- Manifest, trace, and checkpoint readers use a single bounded file handle. V1 defines no transformation-record event, so public trace writers and validators accept only `PUBLIC`; `SANITIZED` fails closed until a later schema can verify the transformation, and private manifests remain local. Trace writers enforce the shared 64-event limit before append, with public validation retaining the same cap as defense in depth. Checkpoint save and load use that same source of truth and accept only sequence `0..64`, so impossible trace/checkpoint continuity cannot be persisted or restored. Checkpoint restore also verifies task identity and goal hash; corrupt JSON or goal drift fails visibly.
- `harness-smoke` validates its declared governance, feature-catalog, roster, and TOML inputs, then enforces step/tool/elapsed budgets, the exact artifact set, and every declared v1 `file_exists` or `text_contains` acceptance check before recording `run_completed: pass` or publishing a fresh ignored run. V1 rejects `exit_code` because this in-process smoke has no separately observed subprocess result. Its Markdown report states model call `none`, trade authority `none`, checkpoint continuity `PASS`, and public trace validation `PASS`.
- Production investment workflows remain unchanged. This bootstrap cannot authorize trades or claim that Context, Memory, checkpointing, or Multi-Agent improves performance before the benchmark phase.

Minimum checks:

- `.\.venv\Scripts\python -m unittest -v tests.test_product_governance tests.test_evolution tests.test_agent_contracts tests.test_agent_roster tests.test_harness_manifest tests.test_harness_trace tests.test_harness_checkpoint tests.test_harness_integration`
- `.\.venv\Scripts\python scripts\validate_agent_contracts.py`
- `.\.venv\Scripts\python -m stock_assist.cli agents`
- `.\.venv\Scripts\python -m stock_assist.cli evolve`
- `.\.venv\Scripts\python -m stock_assist.cli harness-smoke`
- Inspect the newest agents, evolution, and harness-smoke Markdown reports plus the referenced trace/checkpoint artifacts.
- `.\.venv\Scripts\python scripts\validate_project_memory.py`
- `node "$env:USERPROFILE\.codex\skills\harness-creator\scripts\validate-harness.mjs" --target D:\work\InsightRadar`

### Market Levels

Done means:

- `market-levels` generates matching JSON, Markdown, and HTML artifacts.
- Monthly, weekly, daily, 60-minute, 15-minute, and aggregated 3-minute structures are attempted independently; one failed timeframe does not erase the rest.
- Synthesis ignores otherwise valid timeframes that have no qualifying support zone; sparse support evidence must not crash the whole report.
- Chan-theory output is labeled as a deterministic approximation built from fractals, alternating strokes, overlap centers, and MACD divergence candidates.
- A highlighted level requires at least two distinct evidence families; rolling lows at several windows count as one family.
- Output states hold, invalidation, and reclaim conditions instead of deterministic trade orders.
- Unclosed bars and source limitations are explicit data notes or gaps.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_market_levels`
- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m json.tool configs\market_levels.json`
- `.\.venv\Scripts\python -m stock_assist.cli market-levels`
- Inspect the newest `reports/*-market-levels.json`, `.md`, and `.html`; verify responsive HTML without horizontal overflow.

### Portfolio Import and Risk Reconciliation

Done means:

- `portfolio-import --file <broker.tsv>` produces a read-only preview with parsing errors, null-preserving canonical holdings, old/new diffs, an explicit pending-beta state, and reconciliation blockers. The import UI has no manual beta selector.
- `--approve` is required for state changes. Approved writes use temporary files, timestamped backups, and atomic replacement. A failed save restores the prior file; a later background-refresh failure preserves the newly approved portfolio and the last-good report while exposing the failed step.
- The service binds only to `127.0.0.1`, uses an unguessable session token, never accepts a browser-selected destination path, and never executes a trade.
- Imported risk exposure is not silently synchronized from guessed tickers or zero broker weights. Incomplete weights or beta evidence with status other than `ready` leaves reconciliation blocked and strict decision-ready coverage at zero. Low R² remains visible as fit quality and is not presented as strong explanatory evidence.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_portfolio_import -v`
- `.\.venv\Scripts\python -m unittest tests.test_portfolio_beta -v`
- `.\.venv\Scripts\python -m stock_assist.cli portfolio-beta`
- `.\.venv\Scripts\python -m stock_assist.cli portfolio-import --file data\portfolio.manual.tsv`
- Inspect preview validation, null fields, diff, pending beta, reconciliation, and `requires_approval`; inspect the newest `portfolio-beta` JSON/Markdown/HTML evidence and do not pass `--approve` without the user's explicit authorization.

### Style Rotation Monitor

Done means:

- `style-rotation` generates matching JSON, Markdown, and HTML artifacts from fixed transparent technology-growth, large-financial, high-dividend, and CSI 300 benchmark proxies.
- The payload reports 5/20/60-session benchmark-relative returns, breadth, MA20/MA60 participation, turnover/fund proxies, persistence, source coverage, positive and negative evidence, conflicts, and missing earnings confirmation.
- One indicator cannot confirm rotation. Sustained confirmation requires relative strength plus breadth plus turnover/fund evidence and at least five persistent sessions without a horizon conflict.
- ETF `close * volume` is labelled an approximate turnover proxy, never official amount, ETF-share creation/redemption, or state-team activity. The diagnostic cannot independently authorize a trade or override the risk budget.
- `after-close` consumes the latest payload and shows whether technology is weaker than financial/high-dividend while preserving short-horizon seesaw uncertainty.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_style_rotation -v`
- `.\.venv\Scripts\python -m json.tool configs\style_rotation.json`
- `.\.venv\Scripts\python -m stock_assist.cli style-rotation`
- Inspect the newest JSON/Markdown/HTML for all horizons, evidence conflicts, coverage, calibration, and no-trade authority.

### Event Intelligence (`feat-055`)

Done means:

- The product owns a standard MCP client lifecycle and does not depend on the user-scoped Codex MCP configuration.
- Jin10 machine parsing uses `structuredContent`; text `content` is never a silent structured-data fallback.
- List pagination uses `cursor`, `data.next_cursor`, and `data.has_more`, with visible incomplete-coverage state on failure.
- Normalized events preserve provider identity, source URL, published/fetched time, timezone, verification state, and unresolved gaps.
- Classification distinguishes incremental execution, recent/historical cumulative amounts, future commitments, targets/capacity, and unknown semantics.
- Search/list/summary duplicates produce one event and no duplicate alert; generic “国家队” sports or industry uses do not classify as market support.
- Weekend, pre-open, midday, after-close, and evening digest items are reconciliation containers: their child items link to existing atomic events or recover genuinely missed discoveries without inflating event/alert counts.
- Provider importance and red-highlight state require structured source fields with provenance. Under the current `content/time/title/url` contract they remain unknown and produce a visible data gap rather than a visual/textual guess.
- Critical policy, filing, company, and state-capital claims retain primary-source confirmation state. Jin10 alone cannot authorize a trade or override the risk budget.
- Relevance is approved-holdings first; empty holdings may map to market/index/style/sector without forcing a candidate.
- Missing token, MCP business/protocol errors, quota exhaustion, timeout, stale data, malformed structured output, pagination inconsistency, and source conflicts fail visibly and within bounded time.
- Bearer tokens and Authorization values remain outside Git and are redacted from reports, logs, audits, fixtures, and exceptions.
- JSON and every enabled human/alert rendering agree on what is new, what is cumulative, relevance, impact, confirmation, invalidation, horizon, and gaps.

Minimum checks when implementation starts:

- Focused MCP transport, normalization, deduplication, classification, verification, relevance, failure, and secret-redaction tests.
- Full unit regression and compileall.
- Real shadow-mode artifact inspection, including the 2026-07-19 China Reform Holdings and China Chengtong semantics and a “国家队” false-positive corpus.
- Digest reconciliation coverage using “周日重要消息汇总”, including missing-child recovery, duplicate suppression, and unknown provider-red state.
- `.\.venv\Scripts\python -m json.tool feature_list.json`
- `.\.venv\Scripts\python scripts\validate_project_memory.py`
- `node "$env:USERPROFILE\.codex\skills\harness-creator\scripts\validate-harness.mjs" --target D:\work\InsightRadar`

### Factor Lab

Done means:

- `factor-lab` generates matching JSON, Markdown, and HTML artifacts from one result.
- The universe type is explicit; a custom pilot universe is never described as the official CSI 1000 universe.
- Features are point-in-time, labels are future benchmark-relative returns, and every forecast uses a horizon-sized training embargo.
- Validation reports RankIC, turnover, costs, drawdown, sample count, current weights, and data gaps; it does not turn a small backtest into a buy order.
- Non-positive closes and extreme one-day data errors are excluded before factor calculation.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_factor_lab`
- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m json.tool configs\factor_lab.json`
- `.\.venv\Scripts\python -m stock_assist.cli factor-lab`
- Inspect the newest `reports/*-factor-lab.json`, `.md`, and `.html` for sample counts, explicit universe type, and data gaps.

### Personal Factor Pipeline

Done means:

- One completed daily run upserts observations, matures only labels whose full horizon exists, trains a versioned challenger, and records a registry entry.
- The same data/config rerun is idempotent: no duplicate observation keys or model-registry versions.
- A failed challenger cannot create or overwrite `champion.json`; rankings without a champion are labeled diagnostic only.
- Model JSON records data hash, feature names, training/validation dates, weights, gates, VIF, condition number, and promotion reason.
- Runtime data stays under ignored `data/factor_pipeline`; config, runner, installer, tests, and schemas stay trackable.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_factor_pipeline`
- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m json.tool configs\factor_pipeline.json`
- `.\.venv\Scripts\python -m stock_assist.cli factor-pipeline`
- Rerun once and confirm `new_rows=0`, the registry version is not duplicated, and a failed challenger leaves no champion.

### Point-in-Time Factor Universe

Done means:

- `factor-universe-sync` serially fetches and atomically persists CSI 1000 in/out intervals plus matching JSON, Markdown, and HTML audit artifacts.
- Membership uses half-open intervals: inclusion date is active and removal date is inactive.
- Rolling factors are calculated from the historical code union before the daily membership filter is applied.
- Observation keys, training hashes, and model metadata include universe lineage; the legacy custom pilot remains isolated.
- Supplier revisions and missing index-weight/free-float data are explicit gaps.

Minimum checks:

- `.\.venv\Scripts\python -m unittest tests.test_universe tests.test_factor_lab tests.test_factor_pipeline`
- `.\.venv\Scripts\python -m compileall stock_assist`
- `.\.venv\Scripts\python -m stock_assist.cli factor-universe-sync`
- Inspect the newest `reports/*-factor-universe.json`, `.md`, `.html` and confirm the private CSV has exactly 1,000 open CSI 1000 intervals.
- Run `factor-pipeline` twice and confirm the second run has `new_rows=0`, lineage fields are present, and a failed challenger leaves no champion.

## Project-Specific Guardrails

- Use CNInfo first for fresh performance forecasts and critical filings.
- Treat AmazingData as structured confirmation for same-evening filings.
- Do not parallelize AmazingData login or query commands on the same account.
- Preserve the current Markdown report when adding richer report formats.
- Keep trading language conditional and evidence-based.
- Call out missing holdings, watchlists, credentials, or network conditions directly.
- Use concise, scan-friendly Chinese for trading reports.

## Handoff Template

Use this shape at the end of non-trivial work:

```text
Changed:
- <files/features>

Verified:
- <commands and generated report paths>

Current state:
- <what works now>

Next:
- <highest-value next sprint>
```
# Intraday Radar Contract (IR-001)

- `intraday-replay` must consume only locally archived observations whose `source_time` is no later than the evaluated timestamp.
- `IntradaySnapshot`, `ThemeSnapshot`, and `IntradayAlert` keep missing fields as null and preserve both source and fetch lineage.
- Account risk, catalyst failure, opportunity radar, and re-entry guard remain deterministic and cannot execute trades.
- IR-001 must compare full hold, 30/50/70% open reductions, giveback/VWAP reductions, unconditional/structural re-entry, and no same-day re-entry.
- Real account case data and minute archives remain ignored; tracked tests use synthetic fixtures.

## Live Intraday Shadow Contract (IR-002 P0)

- Minute and quote archives are append-only, content-addressed observations. Every row keeps `trade_date`, `source_time`, `fetched_at`, provider, and a stable `observation_id`; a provider correction creates another observation and never replaces the first bytes.
- Live account peaks advance only with a declared `source_time`. A later peak or correction cannot rewrite an earlier snapshot or alert; non-advancing supplier observations stay archived with a visible gap.
- `intraday-runtime/v2` separates `trade_date`, `data_status`, `freshness_status`, and `decision_authority`. Only a same-trade-date runtime inside the freshness window overlays the active workspace; older/stale state is historical/expired.
- IR-002 is fixed at `shadow_only` until real-session calibration passes. Shadow output contains no reduction/addition sizing or position-action copy even when data is available.
- User-confirmed executions append to the private execution ledger and retain symbol, side, quantity, available quantity, `sold_at`, `sale_price`, and source. Missing quantities remain missing rather than zero.
- A second-reentry override is a separate append-only confirmation event that must reference a real first `buy` execution and a later new-low observation. It never creates a synthetic fill or grants automatic execution authority.
- Re-entry is blocked immediately after a confirmed reduction until at least five minutes without a new low, a higher low, VWAP or rebound-high recovery, and breadth recovery. A failed first re-entry followed by another low locks the second attempt until explicit user confirmation.
- Every buy references one existing sell execution; symbol/theme/time lineage must match and concurrent cumulative buys cannot exceed that sell quantity. Execution, failure, and override validation+append share a cross-process single-flight lock. Multiple reductions retain distinct guards.
- The double-click entry starts the loopback page before network work, acquires the checkpoint scheduler lock before the initial refresh, and runs provider work in a terminable child with a 57-second hard boundary. Shutdown wakes and joins the scheduler; restart removes only locks whose recorded owner process is dead.
- A-share session dates come from the AmazingData calendar, a real local archive date, or a bounded real K-line probe in that order. A non-trading day mounts the latest completed session as `historical_review`; it never pretends that the calendar date is live.
- Network routes are provider-scoped: domestic HTTP clients bypass environment proxies, foreign Yahoo clients inherit the system proxy, and loopback/Futu remain local-only. Diagnostics expose route policy but redact proxy endpoints/credentials; application-level direct mode does not claim to bypass OS TUN/VPN.
- Checkpoint states are explicit `scheduled/running/succeeded/partial/failed/missed`; failed runs are not completed and retry at most twice. Runtime/UI expose source time, fetch time, next check, missed checks, data/freshness, authority, and explicit activated/escalated/resolved/invalidation events.

Minimum checks:

- `.venv\Scripts\python -m unittest tests.test_intraday_reliability tests.test_intraday_radar tests.test_one_click_launcher -v`
- `.venv\Scripts\python -m unittest discover -s tests -v`
- `.venv\Scripts\python -m compileall stock_assist`
- `.venv\Scripts\python -m stock_assist.cli architecture-view`
- `.venv\Scripts\python scripts\validate_project_memory.py`
