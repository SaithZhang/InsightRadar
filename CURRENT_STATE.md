# InsightRadar Current State

This is the bounded startup snapshot. Read it after `PROJECT_MEMORY.md`; load chronological history only when a referenced feature or decision requires it. Keep this file under 120 lines and 16 KB.

<!-- current-state-manifest
{
  "schema_version": "insight-radar-current-state/v1",
  "updated_at": "2026-07-30",
  "next_feature_id": "feat-058",
  "product_charter": "docs/product-charter.md",
  "architecture_source": "configs/architecture.json",
  "decision_index": "docs/memory/decision-log.md"
}
-->

## North Star

InsightRadar is an independent AI risk officer for personal A-share decisions. It identifies the few facts that may justify changing a position, separates fact/inference/rumor/sentiment/unknown, preserves counter-evidence and freshness, and never executes a trade.

The proof goal remains local Core value through real trials, controlled replay, benchmark-relative outcomes, drawdown/payoff, and regime stability. Immature results do not establish an edge.

## Current Product Shape

- Product version: **InsightRadar V3.0 Pilot — Scope Frozen**. P0 is owner-accepted; the active phase is ten consecutive real morning decision trials under ADR-0010.
- Canonical workspace: `D:\work\InsightRadar`. All new code, local data, reports, harness state, and Codex project context belong here.
- Public release: prepare a fresh sanitized GitHub baseline under ADR-0011; legacy history and private runtime data remain local.
- Core: portfolio decisions, A-share market radar, research/filing evidence, and the outcome-calibration loop.
- Lab: factor research, universe lineage, neutralization, and model promotion gates. Lab output cannot enter core decisions without a validated champion.
- Satellite: no in-repository satellite is active; the former Windows reminder now has independent ownership at `D:\work\reminder`.
- Optional extension: crypto/RWA monitoring and public-viewpoint collectors. They must not set the A-share core roadmap.
- Governance: project memory, product map, architecture topology, feature state, verification, and evolution backlog.

The canonical boundary and extraction rules are in `docs/product-charter.md`. The live command graph is in `configs/architecture.json`; `docs/architecture.html` is generated from it.

## Verified Baseline

- `feat-054` passed after ultimate independent read-only review at `d115e2e` returned PASS with no findings. The bootstrap now provides bounded governance, exact read-only agent contracts, executable manifests, PUBLIC-only traces, goal-bound checkpoints, fail-closed public privacy, and deterministic smoke evidence. This proves structural contracts only, not model-performance benefit or trade authority.
- `feat-053` passed: the guarded Iwencai completed-close IF/IH/IC/IM adapter aligns spot/contract dates, selects active positive-open-interest contracts, exposes basis and positioning, and falls back serially. It never invents a four-minute change or grants decision authority.
- `feat-036` passed and ownership transferred: the Windows reminder is independently built and running from `D:\work\reminder`; Task Scheduler points there, the main-repo source/export artifacts were retired, and historical logs were migrated.
- `feat-041` passed: `risk-watch` produces a read-only cross-market/portfolio budget with no-lookahead replay, multi-family confirmation, red re-entry lock, Korea circuit-breaker gating, and 16:20 workday automation. The verified replay first confirmed yellow on 05-19, orange on 06-03, and red on 06-09.
- `feat-042` passed: `risk-watch` now exposes an Iwencai A-share turnover-concentration snapshot and generalized volatility-normalized shock gates for S&P 500, QQQ, SOX, Nikkei, and cross-region US/Asia concurrence. Concentration remains diagnostic until at least 20 archived daily samples support percentile calibration; community narrative telemetry remains observation-only.
- `feat-043` passed: `ai-capex-watch` separates hyperscaler CapEx, optical-network transmission, and supplier realization; sparse or missing evidence stays explicit and cannot override `risk-watch` or authorize trades.
- `feat-045` passed: four CSI 300 ETF share histories are compared with dated Huijin disclosures. The 2026-07-17 lower bound is 1606.59亿 units exited from the disclosed ETFs, without claiming cash selling, redemption destinations, or full rescue-book coverage.
- `feat-046` passed: the proxy adds 1/5/20-observation changes and preserves the current +17.88% five-observation rebound inside a -33.38% twenty-observation contraction; it cannot identify the seller or authorize a style trade.
- `feat-047` passed: `after-close` consumes risk, state-team ETF, and AI-capex evidence into one fail-closed next-session plan; missing or stale gates cannot authorize added exposure.
- `feat-048` passed: the same guide now consumes `market-levels`, shows diagnostic bear-bull/fear-greed/crowding gauges, exposes the current support/confirmation/resistance ladder and a four-stage intraday watchlist, and provides a local-only broker TSV importer that converts to canonical `portfolio.json` only after a user-approved save. The 2026-07-17 snapshot reads 2.0/10 bear-bull, 28/100 fear-greed, and 52/100 crowding; all remain unbacktested diagnostics rather than trade signals. The active 16:20 automation now runs `market-levels` before `after-close` and reports these fields first.
- `feat-049` passed: `risk-watch` now queries the complete 同花顺问财 A-share cross-section against a fixed 2024-09-24 anchor, requires listing-date eligibility plus provider-adjusted interval returns and visible coverage, and sends below-anchor breadth, equal-weight/median-stock equivalent points, and a 3900-stock claim audit into the unified after-close cockpit. The verified 2026-07-17 snapshot covers 5299/5299 eligible stocks: 925 (17.46%) are below the anchor, so the same-mouth claim that 3900 are lower is not supported; median-stock equivalent Shanghai is 3845.54 and the arithmetic equal-weight equivalent is 5060.68 versus the official 3764.15. The 78/100 anchor-width gauge describes cumulative position since 9·24 and is explicitly separated from the current red short-cycle risk state.
- `feat-050` passed: the 2.0/10 bear-bull gauge is now a persisted close-finalized state machine with separate formal/candidate scores, auditable rule/veto ledger, same-day deduplication, daily ±1 cap, hysteresis, two-bar support-failure confirmation, and exact pre-open/intraday/midday/close authority. Market-level states now constrain stance and risk budget instead of remaining decorative; the 2026-07-17 close stays at 2.0 with a red-risk budget-upgrade veto.
- `feat-051` passed: the token-protected loopback importer supports preview/approval, null-preserving diff, explicit beta, fail-closed reconciliation, backup, atomic save, rollback, and serial refresh. The approved 2026-07-22 three-holding snapshot remains blocked until weights, beta classes, and context are complete.
- `feat-052` passed: `style-rotation` now compares fixed technology-growth, large-financial, and high-dividend ETF proxies with CSI 300 across 5/20/60 sessions, breadth, moving-average participation, approximate turnover, persistence, conflicts, and source coverage. The 2026-07-17 result is `信号冲突`: large financials lead, technology weakens, but confirmation persists only three sessions and turnover/earnings evidence is insufficient, so no style switch or budget change is authorized.
- `feat-037` passed: fresh post-migration Core workflows now run from `D:\work\InsightRadar`. After-close exposes structural versus strict decision-ready coverage; market-pulse degrades to a bounded explicit-gap report outside live session instead of hanging; market-level synthesis tolerates timeframes without a qualifying support zone.
- `feat-057` passed: `risk-watch` now exposes independent energy, duration, and Korea macro-transmission states with no-lookahead calibration and `diagnostic_only` authority. The real 2026-07-23 run retained 5/7 macro series after Yahoo SP500/QQQ timeouts, so event count is 0 and calibration is insufficient; the causal thesis is not confirmed and no risk/trade output changes.
- No factor champion exists. Current factor rankings are diagnostic only and cannot influence `after-close` actions.
- Current holdings come from an owner-approved private broker snapshot. Position details and aggregate exposure remain local; beta classifications and incomplete context remain unknown, risk reconciliation is blocked, and strict readiness remains fail-closed.

## Next Feature

- `feat-058` is the sole active experiment for the ten-run Pilot. The decision-service repair now derives cost-invariant repair/risk/wait branches from completed daily bars, quarantines undeclared adjustment discontinuities, links evidence to plans, and saves imports before an idempotent SQLite-backed serial refresh. Completion requires new artifacts plus a same-stem triplet bound to `portfolio_version`. Private runtime evidence and loopback interaction QA passed; owner re-review is pending and P1/P2 remain unstarted.
- `feat-056` remains pending and the sole queued Harness experiment; no pilot or benchmark run has started.
- `feat-057` is complete but remains an unpromoted diagnostic layer until adequate independent events, held-out outcomes, stable thresholds, primary-source event evidence, and reliable source coverage exist.
- `feat-044` and `feat-055` remain pending outside the Harness queue and are not authorized to jump ahead of the Harness program without explicit reprioritization.
- `feat-044` — add automatic official-IR change discovery and bind 中际 gross margin, operating cash flow, inventory, receivables, and disclosed 800G/1.6T realization into the existing supplier gate.
- `feat-040` remains pending user acceptance and is parked after the 2026-07-18 Core risk-watch reprioritization.
- `feat-038` passed as an explicitly reprioritized, read-only NGA Extension; its failure cannot block Core workflows.
- `feat-039` passed as the optional NGA daily semantic layer: evidence is deterministic; the default after-close automation now uses its own Codex model and makes no external AI API call, while the opt-in gateway path remains parked for later tuning.
- `feat-040` now also carries an evidence-bound strategy-contract layer for the tracked technology-mainline thread: user-provided thresholds stay labelled and cannot override current market data, filings, financial evidence, or user-specific risk settings. Acceptance is still pending.

## Known Gaps

- Codex config and the weekday brief target `D:\work\InsightRadar`. The old `%USERPROFILE%\Documents\stock-assist` root remains empty but process-locked; do not force-delete it.
- The project `.venv` and AmazingData connectivity are restored. The latest private report has structural actions but no strictly ready holding; complete explicit beta/risk reconciliation and all stale or missing holding contexts before any blocked plan can gain authority. One provider series is separately quarantined until its adjustment basis is reconciled.
- The weekend `market-pulse` now contains eight dated IF/IH/IC/IM 2608/2609 close-basis rows, while Eastmoney index/ETF snapshots still closed connections and realtime AmazingData remains session-gated. Derivative context is valid through 2026-07-17, but the report is still a partial after-close diagnostic, not live direction.
- The four-ETF state-team proxy is current through 2026-07-17, but 2015-era CSF/Huijin direct stock holdings and ETF in-kind redemption destinations remain unverified; a full direct-holding check must wait for the 2026 interim-report disclosure set.
- Galaxy/AmazingData is not a universal ARM macOS/Linux runtime. Iwencai is now a guarded local Core source for fixed-anchor breadth and completed-close futures basis under ADR-0008, but cross-platform execution, multi-day reconciliation, latency/quota measurement, and supply-chain gates remain open; do not describe it as cloud/universal production readiness.
- Point-in-time industry/free-float exposure coverage and neutralization are incomplete.
- Signal-outcome samples are still maturing; product-quality claims require visible sample counts and benchmark-relative results. One historical plan is quarantined from Review because its 20-day threshold and the current broker price use incompatible bases.
- Cloud deployment, production Docker work, WSL/macOS migration, and new clients are deferred by ADR-0006 until Core reliability and outcome-value gates pass. The canonical product continues locally on Windows; portability remains a later option rather than the active roadmap.
- Portfolio attribution and event-to-position alerting remain roadmap work.
- A-share turnover concentration currently has only as-of snapshots, not a mature daily percentile history. Futu community feeds provide timestamped text but no interaction fields; long-horizon narrative/FOMO ratios must accumulate point-in-time samples before they can influence Core risk scores.
- The market-regime state machine is transparent and persisted but still `diagnostic_unbacktested`; rule thresholds are not calibrated against forward returns, drawdown, or regime persistence. Crowding has fewer than 20 archived daily observations and is not a historical percentile. The current portfolio file is approved, but risk reconciliation remains blocked until beta classifications and missing holding context are explicitly completed; the service never infers these from ticker codes.
- Style-rotation history currently comes from public ETF K-lines. Turnover is an explicit `close * volume` approximation, earnings confirmation is unavailable, and only three persistence sessions exist; the current financial lead/technology weakness remains a conflict diagnosis rather than a confirmed lasting switch.
- The 9·24 anchor-width result is a single-provider, single-anchor diagnostic. It has full current query coverage and adjusted interval returns, but it is not a survivorship-free rolling history or an official-index contribution decomposition; arithmetic equal-weight output is skew-sensitive, so the median-stock equivalent remains visible beside it.
- `ai-capex-watch` currently uses timestamped, manually curated official-IR evidence. It does not yet discover new earnings releases automatically; 800G/1.6T official demand and 中际毛利率、经营现金流、库存应收与1.6T收入 remain open transmission gaps. Direct `file://` browser QA is also blocked by the local browser URL policy.
- `progress.md` and `session-handoff.md` are append-only history and already large; query their tail or matching feature section instead of reading them in full.

## Expansion Freeze

- InsightRadar V3.0 Pilot: freeze the four-page information architecture, core loop, and responsibility boundary for ten real morning trials; see ADR-0010.
- Windows reminder: extraction and external cutover complete; it is no longer an InsightRadar repository component.
- Factor Lab: keep available but park new development.
- Crypto/RWA and X/Twitter collectors remain frozen as optional Extensions. The completed NGA monitor and daily digest remain isolated and cannot become Core dependencies.
- New mobile/web clients, model families, markets, and automated execution remain out of scope.
- Cloud deployment and production containerization remain parked; prioritize official supplier evidence and mature outcomes before replay-threshold recalibration, attribution, or delivery expansion.

## Restart Protocol

1. Read `AGENTS.md`, `PROJECT_MEMORY.md`, and this file.
2. Load only the memory topic and harness contract matching the task.
3. Query the exact feature entry and matching recent history by feature id.
4. Check `git status --short --branch` and recent commits.
5. Work on one feature, run its verification, then refresh this snapshot if current direction or next work changed.
