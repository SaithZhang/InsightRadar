# InsightRadar Current State

This is the bounded startup snapshot. Read it after `PROJECT_MEMORY.md`; load chronological history only when a referenced feature or decision requires it. Keep this file under 120 lines and 16 KB.

<!-- current-state-manifest
{
  "schema_version": "insight-radar-current-state/v1",
  "updated_at": "2026-08-01",
  "next_feature_id": "IR-002",
  "product_charter": "docs/product-charter.md",
  "architecture_source": "configs/architecture.json",
  "decision_index": "docs/memory/decision-log.md"
}
-->

## North Star

InsightRadar is an A-share premarket/intraday risk-and-opportunity radar over holdings and candidate-thesis memory. It protects account-level profit, detects catalyst failure, gates re-entry, confirms relative strength, separates fact/inference/rumor/sentiment/unknown, and never executes a trade.

The proof goal remains local Core value through real trials, controlled replay, benchmark-relative outcomes, drawdown/payoff, and regime stability. Immature results do not establish an edge.

## Current Product Shape

- Version: **InsightRadar V3.1 — Incremental Development** under ADR-0015. V3.0 is historical; its incomplete ten-run pilot is not reported as passed.
- Direction: **Intraday Core pivot under ADR-0012**. Four routes and the rule/user/AI/trade boundary remain V3.1 guardrails.
- Routes: `today` 今日工作台, `portfolio` 组合风险, `lookup` 标的研究, and `review` 复盘账本. Today is a conclusion layer, not a fifth route.
- Canonical workspace: `D:\work\InsightRadar`. All new code, local data, reports, harness state, and Codex project context belong here.
- Public release: prepare a fresh sanitized GitHub baseline under ADR-0011; legacy history and private runtime data remain local.
- Core: portfolio decisions, A-share market radar, research/filing evidence, and the outcome-calibration loop.
- Lab: factor research, universe lineage, neutralization, and model promotion gates. Lab output cannot enter core decisions without a validated champion.
- Satellite: no in-repository satellite is active; the former Windows reminder now has independent ownership at `D:\work\reminder`.
- Optional extension: crypto/RWA monitoring and public-viewpoint collectors. They must not set the A-share core roadmap.
- Governance: project memory, product map, architecture topology, feature state, verification, and evolution backlog.

The canonical boundary and extraction rules are in `docs/product-charter.md`. The live command graph is in `configs/architecture.json`; `docs/architecture.html` is generated from it.

## Verified Baseline

- `IR-001` passed: 36,060 private minute bars, 25 auction snapshots, 255 no-lookahead snapshots, and 15 transitions reproduced the bounded case. Private results beat full hold on profit protection; account values stay local and improvement versus actual remains unknown.
- `IR-002` P0 is weekend-usable but still uncalibrated: the page opens before bounded provider work; explicit domestic/foreign/local routes, real exchange/runtime/display dates, latest-completed historical review, a pre-registered restart-safe scheduler, and a terminable sub-60-second refresh are live. Runtime v2 remains `shadow_only`; per-component freshness and unknowns fail closed. Confirmed executions and real re-entry-failure observations retain per-sell lineage under single-flight ledger writes. No notification or trade authority is admitted.

- `feat-054` passed after ultimate independent read-only review at `d115e2e` returned PASS with no findings. The bootstrap now provides bounded governance, exact read-only agent contracts, executable manifests, PUBLIC-only traces, goal-bound checkpoints, fail-closed public privacy, and deterministic smoke evidence. This proves structural contracts only, not model-performance benefit or trade authority.
- `feat-053` passed: the guarded Iwencai completed-close IF/IH/IC/IM adapter aligns spot/contract dates, selects active positive-open-interest contracts, exposes basis and positioning, and falls back serially. It never invents a four-minute change or grants decision authority.
- `feat-036` passed and ownership transferred: the Windows reminder is independently built and running from `D:\work\reminder`; Task Scheduler points there, the main-repo source/export artifacts were retired, and historical logs were migrated.
- `feat-041` passed: `risk-watch` produces a read-only cross-market/portfolio budget with no-lookahead replay, multi-family confirmation, red re-entry lock, Korea circuit-breaker gating, and 16:20 workday automation. The verified replay first confirmed yellow on 05-19, orange on 06-03, and red on 06-09.
- `feat-042` passed: `risk-watch` now exposes an Iwencai A-share turnover-concentration snapshot and generalized volatility-normalized shock gates for S&P 500, QQQ, SOX, Nikkei, and cross-region US/Asia concurrence. Concentration remains diagnostic until at least 20 archived daily samples support percentile calibration; community narrative telemetry remains observation-only.
- `feat-043` passed: `ai-capex-watch` separates hyperscaler CapEx, optical-network transmission, and supplier realization; sparse or missing evidence stays explicit and cannot override `risk-watch` or authorize trades.
- `feat-047` passed: `after-close` consumes risk, state-team ETF, and AI-capex evidence into one fail-closed next-session plan; missing or stale gates cannot authorize added exposure.
- `feat-048/050` passed: the next-session guide consumes market levels and unbacktested gauges; the bear-bull score is a persisted close-finalized state machine with rule/veto ledger, hysteresis, daily ±1 cap, and fail-closed market-level authority.
- `feat-051` passed: loopback portfolio import is preview/approval gated, null-preserving, atomic, reversible, and serially refreshed; incomplete weight/beta blocks risk reconciliation, while missing current risk context separately blocks strict decision readiness.
- `feat-052` passed: fixed style proxies use 5/20/60-session strength, breadth, approximate turnover, persistence, conflicts, and coverage; insufficient persistence/earnings evidence cannot authorize a style switch.
- `feat-037` passed: fresh post-migration Core workflows now run from `D:\work\InsightRadar`. After-close exposes structural versus strict decision-ready coverage; market-pulse degrades to a bounded explicit-gap report outside live session instead of hanging; market-level synthesis tolerates timeframes without a qualifying support zone.
- `feat-057` passed: `risk-watch` now exposes independent energy, duration, and Korea macro-transmission states with no-lookahead calibration and `diagnostic_only` authority. The real 2026-07-23 run retained 5/7 macro series after Yahoo SP500/QQQ timeouts, so event count is 0 and calibration is insufficient; the causal thesis is not confirmed and no risk/trade output changes.
- No factor champion exists. Current factor rankings are diagnostic only and cannot influence `after-close` actions.
- Current holdings come from an owner-approved private broker snapshot. Position details and aggregate exposure remain local. The 2026-08-01 deterministic beta refresh produced ready 120-session evidence for 4/4 holdings and reconciled the risk profile. Current risk context is ready for 1/4 holdings and strict readiness is 1/4; historical entry context is 0/4 and remains a Review limitation rather than a current-plan blocker.

## Next Feature

- `IR-002` remains the sole active experiment. P0 truth/authority/scheduling defects are fixed; next evidence is multiple real 09:25/09:35/10:00 shadows, verified external point-time mapping, timing/false-escalation/missed-protection measurement, and notification admission. No notifications are authorized.
- `feat-058` remains outside the sole active experiment slot, but the owner explicitly resumed its bounded Today Workbench replacement on 2026-08-01. The after-close/weekend three-column entry, data health, evidence chain, and version-scoped rule responses remain secondary to IR-002 live calibration and do not authorize notifications or trades.
- `feat-056` remains pending and the sole queued Harness experiment; no pilot or benchmark run has started.
- `feat-057` is complete but remains an unpromoted diagnostic layer until adequate independent events, held-out outcomes, stable thresholds, primary-source event evidence, and reliable source coverage exist.
- `feat-044` and `feat-055` remain pending outside the Harness queue and are not authorized to jump ahead of the Harness program without explicit reprioritization.
- `feat-044` — add automatic official-IR change discovery and bind 中际 gross margin, operating cash flow, inventory, receivables, and disclosed 800G/1.6T realization into the existing supplier gate.
- `feat-040` remains pending user acceptance and is parked after the 2026-07-18 Core risk-watch reprioritization.
- `feat-038` passed as an explicitly reprioritized, read-only NGA Extension; its failure cannot block Core workflows.
- `feat-039` passed as the optional NGA daily semantic layer: evidence is deterministic; the default after-close automation now uses its own Codex model and makes no external AI API call, while the opt-in gateway path remains parked for later tuning.
- `feat-040` now also carries an evidence-bound strategy-contract layer for the tracked technology-mainline thread: user-provided thresholds stay labelled and cannot override current market data, filings, financial evidence, or user-specific risk settings. Acceptance is still pending.

## Known Gaps

- IR-001 external-mapping returns are explicit acceptance-case inputs, not verified external price observations. Live `catalyst_failure` remains unavailable until a point-in-time external mapping source is wired.
- Actual 2026-07-31 broker executions are unavailable, so `improvement_vs_actual` remains `unknown`; no proxy strategy is labelled as actual behavior.
- The live poller has no open-session IR-002 calibration sample yet. The 2026-08-01 Saturday smoke resolved the real 2026-07-31 session, loaded 90/90 archived symbols, and exposed historical-only authority; this proves weekend usability, not live timing, profitability, or notification admission.
- The workbench can append user-confirmed sell/re-entry evidence and gate re-entry, but no real execution has been supplied; absence remains unknown rather than “no sale”.

- Codex config and the weekday brief target `D:\work\InsightRadar`. The old `%USERPROFILE%\Documents\stock-assist` root remains empty but process-locked; do not force-delete it.
- The project `.venv` and AmazingData connectivity are restored. The latest private report has four structural actions and one strictly ready holding. Automatic beta/risk reconciliation is complete for 4/4 holdings; three holdings still lack usable current risk context or retain independent blockers. Historical entry context is incomplete for 4/4 and limits Review only. One provider series is separately quarantined until its adjustment basis is reconciled.
- The weekend `market-pulse` now contains eight dated IF/IH/IC/IM 2608/2609 close-basis rows, while Eastmoney index/ETF snapshots still closed connections and realtime AmazingData remains session-gated. Derivative context is valid through 2026-07-17, but the report is still a partial after-close diagnostic, not live direction.
- The four-ETF state-team proxy is current through 2026-07-17, but 2015-era CSF/Huijin direct stock holdings and ETF in-kind redemption destinations remain unverified; a full direct-holding check must wait for the 2026 interim-report disclosure set.
- Galaxy/AmazingData is not a universal ARM macOS/Linux runtime. Iwencai is now a guarded local Core source for fixed-anchor breadth and completed-close futures basis under ADR-0008, but cross-platform execution, multi-day reconciliation, latency/quota measurement, and supply-chain gates remain open; do not describe it as cloud/universal production readiness.
- Point-in-time industry/free-float exposure coverage and neutralization are incomplete.
- Signal-outcome samples are still maturing; product-quality claims require visible sample counts and benchmark-relative results. One historical plan is quarantined from Review because its 20-day threshold and the current broker price use incompatible bases.
- Cloud deployment, production Docker work, WSL/macOS migration, and new clients are deferred by ADR-0006 until Core reliability and outcome-value gates pass. The canonical product continues locally on Windows; portability remains a later option rather than the active roadmap.
- Portfolio attribution and event-to-position alerting remain roadmap work.
- A-share turnover concentration currently has only as-of snapshots, not a mature daily percentile history. Futu community feeds provide timestamped text but no interaction fields; long-horizon narrative/FOMO ratios must accumulate point-in-time samples before they can influence Core risk scores.
- The market-regime state machine is transparent and persisted but still `diagnostic_unbacktested`; rule thresholds are not calibrated against forward returns, drawdown, or regime persistence. Crowding has fewer than 20 archived daily observations and is not a historical percentile. The current portfolio file is approved and beta risk reconciliation is complete through deterministic price evidence; missing or conflicting current risk context remains an independent plan blocker, while unknown historical entry context is a Review gap. The service never guesses beta from ticker codes.
- Style-rotation history currently comes from public ETF K-lines. Turnover is an explicit `close * volume` approximation, earnings confirmation is unavailable, and only three persistence sessions exist; the current financial lead/technology weakness remains a conflict diagnosis rather than a confirmed lasting switch.
- The 9·24 anchor-width result is a single-provider, single-anchor diagnostic. It has full current query coverage and adjusted interval returns, but it is not a survivorship-free rolling history or an official-index contribution decomposition; arithmetic equal-weight output is skew-sensitive, so the median-stock equivalent remains visible beside it.
- `ai-capex-watch` currently uses timestamped, manually curated official-IR evidence. It does not yet discover new earnings releases automatically; 800G/1.6T official demand and 中际毛利率、经营现金流、库存应收与1.6T收入 remain open transmission gaps. Direct `file://` browser QA is also blocked by the local browser URL policy.
- `progress.md` and `session-handoff.md` are append-only history and already large; query their tail or matching feature section instead of reading them in full.

## Version Discipline and Parked Expansion

- V3.1 advances one admitted increment at a time; `IR-002` is active. V3.2 and parallel redesign remain unauthorized.
- Preserve the four-route information architecture, modular monolith, local-only runtime, and human authority boundary. ADR-0012 authorizes intraday Core behavior inside those routes; it does not authorize a fifth page, cloud deployment, or automatic execution.
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
