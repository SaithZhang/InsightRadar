# InsightRadar Current State

This is the bounded startup snapshot. Read it after `PROJECT_MEMORY.md`; load chronological history only when a referenced feature or decision requires it. Keep this file under 120 lines and 16 KB.

<!-- current-state-manifest
{
  "schema_version": "insight-radar-current-state/v1",
  "updated_at": "2026-08-08",
  "next_feature_id": "feat-058",
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

- `feat-059` is on `main`: four read-only MCP tools expose Eastmoney-primary/Tencent whole-series-fallback tape and trade review with explicit provenance, no-lookahead, no cross-source row merge, and no trade authority.
- `IR-001` passed: 36,060 private minute bars, 25 auction snapshots, 255 no-lookahead snapshots, and 15 transitions reproduced the bounded case. Private results beat full hold on profit protection; account values stay local and improvement versus actual remains unknown.
- `IR-002` P0 is weekend-usable but still uncalibrated: the page opens before bounded provider work; explicit domestic/foreign/local routes, real exchange/runtime/display dates, latest-completed historical review, a pre-registered restart-safe scheduler, and a terminable sub-60-second refresh are live. Runtime v2 remains `shadow_only`; per-component freshness and unknowns fail closed. Confirmed executions and real re-entry-failure observations retain per-sell lineage under single-flight ledger writes. No notification or trade authority is admitted.

- Older passed Core and governance increments remain recorded in `feature_list.json` and scoped memory topics; this bounded snapshot does not duplicate their full evidence.
- `feat-048/050` passed: the next-session guide consumes market levels and unbacktested gauges; the bear-bull score is a persisted close-finalized state machine with rule/veto ledger, hysteresis, daily ±1 cap, and fail-closed market-level authority.
- `feat-051` passed: loopback portfolio import is preview/approval gated, null-preserving, atomic, reversible, and serially refreshed; incomplete weight/beta blocks risk reconciliation. ADR-0016 supersedes the old consent gate: missing/stale management context now generates a deterministic proposal and does not block base analysis.
- `feat-058` repair closure is locally verified: ProviderResult lineage reaches the decision workspace; every blocked plan links to structured repair issues; the Portfolio route exposes field/source/time/current-known-value/repair authority; version-bound system retries regenerate after-close and preserve blocked on failure. Daily-series price-basis/mapping faults may use a separately recorded, ignored Tencent forward-adjusted whole-series fallback; rows are never stitched across providers and the primary quarantine remains visible in provenance. Broker field gaps still route through the approved importer, and no user action can clear provider quarantine.
- `feat-052` passed: fixed style proxies use 5/20/60-session strength, breadth, approximate turnover, persistence, conflicts, and coverage; insufficient persistence/earnings evidence cannot authorize a style switch.
- `feat-037` passed: fresh post-migration Core workflows now run from `D:\work\InsightRadar`. After-close exposes structural versus strict decision-ready coverage; market-pulse degrades to a bounded explicit-gap report outside live session instead of hanging; market-level synthesis tolerates timeframes without a qualifying support zone.
- `feat-057` passed: `risk-watch` now exposes independent energy, duration, and Korea macro-transmission states with no-lookahead calibration and `diagnostic_only` authority. The real 2026-07-23 run retained 5/7 macro series after Yahoo SP500/QQQ timeouts, so event count is 0 and calibration is insufficient; the causal thesis is not confirmed and no risk/trade output changes.
- No factor champion exists. Current factor rankings are diagnostic only and cannot influence `after-close` actions.
- Current holdings come from an owner-approved private broker snapshot. Position details and aggregate exposure remain local. The deterministic beta refresh reconciled the private risk profile. A private 2026-08-02 runtime acceptance confirmed that management proposals and independent price-data quarantine now coexist without committing symbols, account values, or report artifacts; historical entry context remains a Review limitation.

## Next Feature

- `feat-058` is the owner-selected active V3.1 increment and is ready for final owner acceptance. The blocked-to-repair vertical chain is implemented and verified; stop here and do not start P1/P2 or another product increment.
- `feat-059` remains available on `main`; local MCP does not imply ChatGPT Web reachability and no remote tunnel/deployment is admitted by this closure.
- `IR-002` P0 remains intact but its live calibration is parked for this bounded increment. When resumed, next evidence is multiple real 09:25/09:35/10:00 shadows, verified external point-time mapping, timing/false-escalation/missed-protection measurement, and notification admission. No notifications are authorized.
- `feat-056` remains pending and the sole queued Harness experiment; no pilot or benchmark run has started.
- `feat-057` is complete but remains an unpromoted diagnostic layer until adequate independent events, held-out outcomes, stable thresholds, primary-source event evidence, and reliable source coverage exist.
- `feat-044` and `feat-055` remain pending outside the Harness queue and are not authorized to jump ahead of the Harness program without explicit reprioritization.
- `feat-044` — add automatic official-IR change discovery and bind 中际 gross margin, operating cash flow, inventory, receivables, and disclosed 800G/1.6T realization into the existing supplier gate.
- `feat-040` remains pending user acceptance and is parked after the 2026-07-18 Core risk-watch reprioritization.
- `feat-038` passed as an explicitly reprioritized, read-only NGA Extension; its failure cannot block Core workflows.
- `feat-039` passed as the optional NGA daily semantic layer: evidence is deterministic; the default after-close automation now uses its own Codex model and makes no external AI API call, while the opt-in gateway path remains parked for later tuning.
- `feat-040` now also carries an evidence-bound strategy-contract layer for the tracked technology-mainline thread: user-provided thresholds stay labelled and cannot override current market data, filings, financial evidence, or user-specific risk settings. Acceptance is still pending.

## Known Gaps

- The local MCP server supports stdio and loopback Streamable HTTP only. ChatGPT Web cannot call localhost directly; Secure MCP Tunnel or a separately reviewed authenticated remote HTTPS deployment remains outside `feat-059`.
- Eastmoney/Tencent application endpoints are non-official and have no SLA. The current evidence layer supports only a bounded recent minute window and fixed benchmark registry; sector-relative strength and old-history backfill remain explicit gaps.
- IR-001 external-mapping returns are explicit acceptance-case inputs, not verified external price observations. Live `catalyst_failure` remains unavailable until a point-in-time external mapping source is wired.
- Actual 2026-07-31 broker executions are unavailable, so `improvement_vs_actual` remains `unknown`; no proxy strategy is labelled as actual behavior.
- The live poller has no open-session IR-002 calibration sample yet. The 2026-08-01 Saturday smoke resolved the real 2026-07-31 session, loaded 90/90 archived symbols, and exposed historical-only authority; this proves weekend usability, not live timing, profitability, or notification admission.
- The workbench can append user-confirmed sell/re-entry evidence and gate re-entry, but no real execution has been supplied; absence remains unknown rather than “no sale”.

- Codex config and the weekday brief target `D:\work\InsightRadar`. The old `%USERPROFILE%\Documents\stock-assist` root remains empty but process-locked; do not force-delete it.
- The project `.venv` and AmazingData connectivity are restored. Private beta/risk reconciliation is complete; historical entry context limits Review only. The bounded repair flow first demonstrated fail-closed retention, then repaired the quarantined daily series through a typed Tencent forward-adjusted whole-series fallback and refreshed all stale decision sources. The final private report has zero repair issues, zero blocked plans, and all current holding decisions ready; pending management proposals affect personalization only. Exact portfolio counts and values remain local.
- The weekend `market-pulse` now contains eight dated IF/IH/IC/IM 2608/2609 close-basis rows, while Eastmoney index/ETF snapshots still closed connections and realtime AmazingData remains session-gated. Derivative context is valid through 2026-07-17, but the report is still a partial after-close diagnostic, not live direction.
- The four-ETF state-team proxy is current through 2026-07-17, but 2015-era CSF/Huijin direct stock holdings and ETF in-kind redemption destinations remain unverified; a full direct-holding check must wait for the 2026 interim-report disclosure set.
- Galaxy/AmazingData is not a universal ARM macOS/Linux runtime. Iwencai is now a guarded local Core source for fixed-anchor breadth and completed-close futures basis under ADR-0008, but cross-platform execution, multi-day reconciliation, latency/quota measurement, and supply-chain gates remain open; do not describe it as cloud/universal production readiness.
- Point-in-time industry/free-float exposure coverage and neutralization are incomplete.
- Signal-outcome samples are still maturing; product-quality claims require visible sample counts and benchmark-relative results. One historical plan is quarantined from Review because its 20-day threshold and the current broker price use incompatible bases.
- Cloud deployment, production Docker work, WSL/macOS migration, and new clients are deferred by ADR-0006 until Core reliability and outcome-value gates pass. The canonical product continues locally on Windows; portability remains a later option rather than the active roadmap.
- Portfolio attribution and event-to-position alerting remain roadmap work.
- A-share turnover concentration currently has only as-of snapshots, not a mature daily percentile history. Futu community feeds provide timestamped text but no interaction fields; long-horizon narrative/FOMO ratios must accumulate point-in-time samples before they can influence Core risk scores.
- The market-regime state machine is transparent and persisted but still `diagnostic_unbacktested`; rule thresholds are not calibrated against forward returns, drawdown, or regime persistence. Crowding has fewer than 20 archived daily observations and is not a historical percentile. Missing or conflicting management context is now a pending personalization state rather than a data blocker; invalid account/market evidence remains fail closed. Unknown historical entry context is a Review gap. The service never guesses beta from ticker codes.
- Style-rotation history currently comes from public ETF K-lines. Turnover is an explicit `close * volume` approximation, earnings confirmation is unavailable, and only three persistence sessions exist; the current financial lead/technology weakness remains a conflict diagnosis rather than a confirmed lasting switch.
- The 9·24 anchor-width result is a single-provider, single-anchor diagnostic. It has full current query coverage and adjusted interval returns, but it is not a survivorship-free rolling history or an official-index contribution decomposition; arithmetic equal-weight output is skew-sensitive, so the median-stock equivalent remains visible beside it.
- `ai-capex-watch` currently uses timestamped, manually curated official-IR evidence. It does not yet discover new earnings releases automatically; 800G/1.6T official demand and 中际毛利率、经营现金流、库存应收与1.6T收入 remain open transmission gaps. Direct `file://` browser QA is also blocked by the local browser URL policy.
- `progress.md` and `session-handoff.md` are append-only history and already large; query their tail or matching feature section instead of reading them in full.

## Version Discipline and Parked Expansion

- V3.1 advances one admitted increment at a time; the owner explicitly returned to the `feat-058` repair closure on 2026-08-08. It is ready for acceptance, `IR-002` calibration is parked without losing state, and no later increment is admitted. V3.2 and parallel redesign remain unauthorized.
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
