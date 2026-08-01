# InsightRadar Product Charter

## Product Mission

InsightRadar is an **A股盘前/盘中风险与机会雷达，叠加持仓与候选逻辑记忆**. It filters fragmented portfolio and market evidence, distinguishes facts, inferences, rumors, sentiment, and unknowns, and turns the small number of position-relevant changes into auditable, conditional guidance through a repeatable decision loop:

`Observe -> Explain -> Decide -> Verify`

The product promise is not “more signals.” It is to identify the small number of facts that may justify changing a position, while keeping counter-evidence, freshness, gaps, human confirmation, and later outcomes reviewable.

The user-facing architecture still has exactly four first-level route ids, now labelled `今日雷达` (`today`), `持仓风险` (`portfolio`), `机会发现` (`lookup`), and `复盘验证` (`review`). Market evidence remains an upstream constraint and detail drawer, not a fifth task. The owner-authorized intraday pivot in ADR-0012 supersedes ADR-0010 only where the earlier pilot deferred point-in-time intraday monitoring; the four-route and human-trade-authority freeze remains intact.

## Primary User and Wedge

The primary user is a self-directed A-share investor. The initial wedge remains an approved current portfolio plus a bounded 20-30-theme opportunity universe, not a generic full-market stock-discovery feed:

- What changed that matters to my holdings?
- Which evidence is fresh, trustworthy, or missing?
- What conditional action and invalidation line should I prepare?
- Did prior guidance help after its horizon matured?

When holdings are absent or sparse, the same evidence and risk contracts may produce zero to five transparent observation candidates. Each candidate needs a rationale, horizon, trigger, invalidation, and later outcome review; zero candidates is a valid result.

## Product Loop

| Stage | Product responsibility | Current surfaces |
|---|---|---|
| Observe | Archive point-in-time holdings, auction/minute structure, theme breadth, filings, research, events, and public viewpoints | `intraday-poll`, `market-pulse`, `market-levels`, `research-monitor`, CNInfo/AmazingData adapters |
| Explain | Rank relevance, preserve source links, expose conflicts and data gaps | Insight payloads and JSON/Markdown/HTML reports |
| Decide | At 09:25/09:35/10:00 protect account profit, detect catalyst failure, gate re-entry, and surface confirmed opportunity structure | `intraday-poll`; `after-close` remains remembered-plan preparation and audit |
| Verify | Replay minute-visible evidence and compare counterfactual risk paths before calibration | `intraday-replay`, `signal_outcomes`, and `evolve` |

## Decision Modes and Delivery

- **Portfolio mode:** rank evidence by its effect on approved holdings and produce conditional actions, invalidations, and key alerts.
- **Market-candidate mode:** use the current market/risk state to surface a bounded observation pool when holdings do not provide enough decision context.
- **Alpha Report family:** deliver the same contract through scheduled briefs, event-driven alerts, dashboards, archives, or interactive answers. Time-of-day variants are delivery choices, not the North Star.

Fast-news and international-market inputs first enter an event contract: discover, verify, distinguish new from cumulative facts, map affected holdings/sectors/themes, assess horizon and counter-evidence, then decide whether the item changes a plan, a risk budget, a candidate, or nothing. Critical filings still prioritize primary sources.

## Product Rings

Keep one Git repository and a modular monolith while the product loop is still changing. Separate lifecycle inside the repo before separating deployment or ownership.

| Ring | Included capabilities | Boundary |
|---|---|---|
| Core | Portfolio Intelligence, A-share Market Radar, filing/research evidence, outcome calibration | Must improve the Observe-Explain-Decide-Verify loop and meet production data-gap rules |
| Lab | Factor lab, factor pipeline, PIT universe, neutralization experiments | May publish diagnostics; cannot affect core actions without validated promotion gates |
| Satellite | No current in-repository capability | The former Windows reminder is independently owned at `D:\work\reminder`; a future satellite must meet the extraction criteria below |
| Extension | Crypto/RWA monitor, X/Twitter collectors, optional future brokers | Off by default or loosely coupled; failure cannot break the A-share core |
| Governance | Project memory, ADRs, architecture, feature state, validation, evolution | Version-controlled and required for continuity across sessions and machines |

Do not split into multiple repositories or services merely because file count grows. Extract a component only when at least one of these is true:

1. It has an independent release and rollback lifecycle.
2. It needs a materially different security or secret boundary.
3. It needs independent scaling or availability.
4. Its dependency/runtime conflicts with the core.
5. A stable, tested payload contract already separates producer and consumer.

The Windows reminder qualified and has completed extraction into its own repository and Windows lifecycle. Factor work qualifies as a lab namespace, not yet a service. Crypto monitoring is an optional extension and should not expand the A-share core.

## Sustainable Objective

The durable objective is “A-share decision intelligence,” not a clone feature list. HyperInsight is useful as a positioning reference because its official product description emphasizes decision-first intelligence, fund-flow/whale behavior, denoised feeds, and a personal analyst while explicitly avoiding trade execution. InsightRadar should translate that shape into A-share-native evidence:

- On-chain flows -> holdings, exchange disclosures, capital/sector flows, order-book and liquidity evidence.
- Crypto intel feeds -> CNInfo filings, research changes, macro events, and A-share public viewpoints.
- Whale consensus -> institution/sector/ETF flow and position-concentration evidence when reliable.
- Personal analyst -> portfolio-aware, conditional plans with remembered thesis and risk rules.

Reference reviewed 2026-07-14: https://axipher.com/ and https://apps.apple.com/us/app/hyperinsight-trading-prophetx/id6744803078

## North-Star and Guardrail Metrics

Primary north-star metric:

- **Decision-ready holding coverage**: percentage of current holdings with fresh relevant data, source-linked evidence, an explicit conditional plan, risk/invalidation conditions, and disclosed gaps.

Supporting metrics:

- Event-to-insight latency for portfolio-relevant filings and high-priority market changes.
- Alert precision, missed-material-event rate, and the share of alerts that change an existing plan, risk state, holding, or candidate.
- Candidate promotion and matured benchmark-relative outcomes; candidate volume is not a success metric.
- Matured signal quality with sample count, benchmark-relative return, hit rate, and MFE/MAE; immature samples remain pending.
- Source reliability and freshness by provider, including fallback frequency and unresolved gaps.
- User actionability: proportion of surfaced alerts that map to a holding, watchlist thesis, or explicit risk rule.
- Continuity health: memory validation, architecture coverage, and current-state freshness all pass before a feature is marked done.

Local Core value standard:

- Cloud reach, container count, and client count are not product-success metrics while the decision loop is unproven.
- Evaluate whether guidance can support durable compounding only through sufficient matured samples, benchmark-relative expectancy after realistic costs, drawdown and loss-tail behavior, payoff ratio, MFE/MAE, and stability across market regimes.
- Hit rate remains visible but is never sufficient by itself. Replay and backtests must control point-in-time inputs, look-ahead bias, survivor bias, revisions, and out-of-sample evaluation before influencing product claims or promotion gates.
- Historical evidence must be followed by paper/live shadow evidence; InsightRadar never guarantees returns.

Guardrails:

- Never turn missing data into a confident conclusion.
- Never merge fact, inference, rumor, sentiment, and unknown into one unlabelled claim.
- Never hide counter-evidence, source time, freshness, or a material data gap.
- Never weaken validation gates to force a factor champion.
- Never make automatic trade execution a hidden side effect.
- Never force a candidate quota or promote fast news directly into an action without verification and relevance mapping.
- Never let lab, extension, or governance work crowd out the core portfolio loop without an explicit product decision.
- Never present prototype, synthetic, or fixed review data as a live product capability.
- Never make named-person copy trading or influencer identity a formal product dependency.

The approved product and multi-agent operating design is `docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md`; ADR-0009 records the durable choice.

## Roadmap Order

1. Prove IR-001 offline with immutable minute archives, no-lookahead snapshots, four deterministic rule modules, and explicit counterfactuals.
2. Shadow the same contract at 09:25/09:35/10:00 on live sessions; measure alert timing, provider gaps, false escalation, missed profit protection, and re-entry discipline.
3. Replace scenario external mapping with a verified point-in-time external feed and add notification only for substantive state changes.
4. Mature outcome samples and calibrate thresholds without granting automatic trade authority.
5. Resume parked research/Lab or delivery expansion only after the intraday Core proves value.

The active freeze and extraction queue are maintained in `docs/extractions/README.md`.

Architecture changes that alter these rings or roadmap order require an ADR and a refresh of `CURRENT_STATE.md` plus `configs/architecture.json`.
