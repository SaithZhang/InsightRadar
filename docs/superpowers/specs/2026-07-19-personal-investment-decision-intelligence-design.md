# Personal Investment Decision Intelligence Design

> This English document is the canonical, normative specification and AI guidance source. The [Chinese human-review copy](2026-07-19-personal-investment-decision-intelligence-design.zh-CN.md) is non-normative; if the two differ, this English document controls.

- Status: approved
- Date: 2026-07-19
- Decision owner: user
- Product lead: primary Codex agent
- Durable decision: ADR-0009

## Decision Summary

InsightRadar is a personal A-share investment decision-intelligence system. It does not compete on the amount of data, the number of signals, or the number of agents. It wins by turning fragmented evidence into a small number of relevant, auditable, conditional decisions and alerts, then measuring what happened afterward.

The product remains portfolio-first. When the user has approved holdings, those holdings set relevance and priority. When no approved holdings exist, the product may offer a controlled candidate observation pool rather than becoming a generic stock-discovery feed.

The user-facing Chinese promise is:

> 聚合真正重要的信息，理解你的持仓，发现值得观察的机会，提前预警风险，让每次投资决策都有证据、有边界、能复盘。

Short positioning line:

> 从分散信息，到清晰决策。

## North Star

InsightRadar continuously collects portfolio, market, filing, policy, macro, international, industry, and capital-flow evidence. It identifies changes that materially affect the user's portfolio or market judgment and turns them into source-linked guidance and key alerts with explicit conditions, risk boundaries, uncertainty, and follow-through.

Two decision modes share the same evidence and verification contracts:

1. **Portfolio mode:** explain what changed for approved holdings, what conditional action is available, what invalidates it, and what must be watched next.
2. **Market-candidate mode:** when holdings are absent or sparse, surface zero to five observation candidates whose selection logic, trigger, invalidation, horizon, and risks are explicit. Zero candidates is a valid result.

All outputs preserve missing and stale data, avoid automatic trade execution, and enter an outcome-calibration loop after their horizons mature.

## Product Boundaries

InsightRadar is not:

- a raw financial-news feed;
- a creator-personality subscription or copied opinion stream;
- a generic stock screener that must always produce ideas;
- a deterministic buy/sell oracle;
- an automatic trading system;
- a feature marketplace driven by agent-generated wish lists.

News is evidence, not a conclusion. A candidate is an observation object, not an immediate buy instruction. A technical trigger cannot override missing portfolio data, an unresolved filing, or a hard risk veto.

## Core Product Capabilities

### 1. Information and Event Intelligence

The sensing layer covers:

- user-approved holdings, cost and risk context;
- A-share price, breadth, liquidity, style, index-futures basis, and market-regime evidence;
- CNInfo, exchange, and company announcements;
- fast-news sources such as Jin10 for discovery;
- macro policy, international markets, rates, currencies, commodities, and geopolitical events;
- industry, supply-chain, research, fund-flow, and institution/ETF evidence.

Fast news is a discovery source. Critical filings and policy claims require the highest available primary-source confirmation. The system records source, event time, as-of time, freshness, verification state, and unresolved gaps.

### 2. Relevance and Impact Mapping

Each material event follows one contract:

`discover -> verify -> classify -> map -> assess -> decide -> review`

The mapped record answers:

- What is new, and what is cumulative or previously known?
- Which market, sector, theme, holding, or candidate is affected?
- Is the likely horizon intraday, tactical, or thesis-level?
- What positive and negative transmission paths exist?
- What evidence would confirm or falsify the interpretation?
- Does the event change a plan, a risk budget, a candidate, or nothing?

For example, a fast-news item describing already-used state-capital support is not treated as equal-sized new money for the next session. It may raise the priority of state-support monitoring, central-SOE/technology/ETF mapping, and price/flow confirmation without independently authorizing more exposure.

### 3. Investment Guidance and Key Alerts

Guidance is conditional and conclusion-first. A decision-ready item includes:

- affected object and priority;
- factual evidence with source and as-of;
- base interpretation and credible counter-evidence;
- conditional action or observation;
- trigger and invalidation;
- risk boundary and time horizon;
- missing inputs and confidence/calibration state;
- next review point.

Alerts are promoted only when they affect an approved holding, invalidate a candidate, change the market/risk state, or materially change a previously issued plan. Everything else stays in background evidence. Silence is preferable to low-value alert volume.

### 4. Candidate Observation Pool

Candidate generation is subordinate to market state and portfolio risk. The default output is zero to five candidates, never a quota that must be filled.

Each candidate requires:

- a transparent market/industry/company rationale;
- source-backed evidence and freshness;
- a declared observation horizon;
- an entry/attention trigger rather than an unconditional call;
- invalidation and principal risks;
- liquidity and execution constraints when available;
- later benchmark-relative outcome review.

Candidates do not become portfolio actions until the user adopts them or an explicit future workflow promotes them through a reviewed gate.

### 5. Outcome Calibration

Every material guidance item, alert, and promoted candidate is eligible for later review. Matured evidence records sample count, benchmark-relative return, hit/miss under the declared direction, MFE/MAE, drawdown and loss-tail behavior, payoff ratio, regime, data quality, and whether the user acted.

Immature samples remain pending. No report may describe a stable edge or compounding ability from small or unrepresentative samples.

## Alpha Report as a Delivery Family

`Alpha Report` is the main user-facing delivery family, not the North Star itself. Its contract can be rendered as a scheduled brief, event-driven alert, dashboard, archive, or interactive answer without changing the product mission.

The delivery family should preserve:

- a conclusion-first summary;
- portfolio relevance before generic market detail;
- important international, policy, filing, and market-structure changes;
- a small number of conditional actions or candidates;
- key risks, invalidations, and explicit data gaps;
- links to evidence and later outcome history.

Time-of-day variants may exist operationally, but the product is defined by decision quality rather than by pre-market, intraday, or after-close labels.

## Logical Architecture

The design keeps the existing modular monolith and Core/Lab/Extension rings. It adds no service split and no automatic execution path.

| Logical unit | Responsibility | Output contract |
|---|---|---|
| Evidence collectors | Fetch portfolio, market, filing, fast-news, macro, international, and research inputs | Timestamped evidence with provenance and freshness |
| Event normalizer | Deduplicate, classify, distinguish new versus cumulative facts | Typed event record with verification state |
| Relevance mapper | Map events to holdings, sectors, themes, candidates, and market regime | Affected objects, horizon, impact paths, confidence |
| Decision engine | Apply portfolio state, market state, risk vetoes, triggers, and invalidation | Conditional guidance, alerts, candidate pool |
| Alpha delivery | Render conclusion-first views and notification payloads | JSON plus human-readable report surfaces |
| Outcome ledger | Mature horizons and compare with benchmarks | Auditable calibration and product metrics |
| Product governance | Admit, reject, merge, or retire product experiments | Problem backlog, acceptance evidence, kill decisions |

Interfaces remain typed and source-linked. Provider failures degrade to explicit gaps; they do not silently substitute fabricated values or model guesses.

## Failure and Uncertainty Handling

- Missing or stale risk inputs fail closed on new exposure.
- Missing holdings fields remain unknown and block strict decision readiness.
- Conflicting sources remain visible; primary sources take precedence for critical filings.
- Fast-news text cannot create an action until verification and relevance mapping finish.
- Provider timeouts are bounded and recorded with fallback state.
- Low-confidence or low-relevance events remain background evidence.
- Candidate generation may return an empty pool.
- Agent disagreement is resolved by the lead agent against the evidence contract, then by the user for material product or investment-policy choices.

## Product Metrics

Primary metric:

- **Decision-ready holding coverage:** the share of approved holdings with fresh relevant evidence, conditional guidance, risk/invalidation conditions, and disclosed gaps.

Supporting metrics:

- alert precision, missed-material-event rate, and event-to-insight latency;
- proportion of alerts mapped to a holding, adopted thesis, candidate, or explicit risk rule;
- candidate promotion rate and matured benchmark-relative outcomes;
- source freshness, reliability, fallback rate, and unresolved gaps;
- user usefulness/acceptance and time saved;
- outcome sample count, MFE/MAE, drawdown, payoff ratio, regime stability, and realistic costs.

Feature count, report count, candidate count, agent count, and raw win rate are not success metrics.

## Product Admission Gate

A new Core feature must have all of the following:

1. repeated real-user pain or one high-severity failure;
2. a named part of the Observe-Explain-Decide-Verify loop;
3. a baseline and a measurable outcome;
4. the smallest useful experiment;
5. explicit data and safety boundaries;
6. a kill/merge criterion and review date.

Only one product experiment may be active at a time, with at most two queued. Agents maintain a problem backlog, not an autonomous feature wish list.

## Multi-Agent Operating Model

Roles are stable templates; agents are temporary workstations. The current operating pattern uses one lead plus up to three task agents when parallel work is justified.

| Role | Responsibility | Authority boundary |
|---|---|---|
| User / board / lead practitioner | Set the North Star, provide real corrections, approve material scope and release | Final product and investment-policy authority |
| Lead agent / CEO-CPO | Synthesize evidence, own the problem backlog, choose one experiment, integrate results | Cannot admit a feature without the product gate |
| Evidence and portfolio analyst | Analyze usage traces, holdings, outcomes, data gaps, and repeated failures | Cannot create implementation scope independently |
| Market and benchmark analyst | Compare market products, events, workflows, and A-share-native evidence | Read-only discovery and gap analysis |
| Product critic / kill agent | Challenge value, complexity, duplication, and false confidence | Defaults to reject, merge, simplify, or park |
| Architect / builder | Implement an approved, bounded design | Cannot expand the approved acceptance criteria |
| Independent evaluator | Test contracts, artifacts, replay, regressions, and outcome claims | Must remain separate from the implementation verdict |
| Operations verifier | Check freshness, observability, recovery, and rollback | Cannot change product direction |

Read-heavy exploration, test triage, and review may run in parallel. Repository writes are serialized by ownership. The lead agent keeps the full context; specialists receive bounded role-specific evidence to reduce cost, overlap, and role leakage.

The operating loop is:

`real use/correction -> structured trace -> problem cluster -> gated brief -> user approval -> bounded build -> independent verification -> shadow use -> keep/merge/delete`

## Competitive References

InsightRadar combines useful workflow patterns without cloning any one product:

- **Meet Kevin Alpha Report:** fixed daily habit, overnight-world context, fresh research, lines to watch, and an archive. Borrow the concise delivery rhythm, not creator authority or generic trade calls.
- **Klarion:** portfolio-aware explanations, market-move alerts, exposure mapping, and historical context. Borrow the requirement to answer why an event matters to this user.
- **AlphaSense:** unified, auditable research plus scheduled monitoring agents. Borrow proactive evidence collection and source-linked synthesis.
- **Koyfin:** portfolio/watchlist alerts for news, filings, price, valuation, and technical conditions. Borrow explicit user-relevant trigger management.
- **TradingView:** separation between historical strategy calculation and live alert execution. Borrow replayable trigger semantics and evaluation boundaries.

InsightRadar's differentiation is A-share-native evidence, user-approved holdings, explicit market/risk state, conditional guidance, fail-closed data gaps, and a persistent outcome loop.

## Alternatives Considered

### Report-first creator product

Rejected as the North Star. It can create a strong daily habit but depends on one personality and provides weak portfolio personalization and calibration.

### Information-terminal product

Rejected as the North Star. It maximizes breadth but risks becoming another dashboard that leaves the decision burden with the user.

### Autonomous stock-picking system

Rejected. It encourages forced candidates, hides uncertainty, and conflicts with the no-execution and evidence-bound product contract.

### Portfolio-first decision intelligence with controlled candidate fallback

Accepted. It retains a sharp initial wedge, supports the no-holdings case, and makes relevance, risk, and later verification first-class product behavior.

## Verification Strategy

Implementation plans derived from this design must verify:

- schema and source-provenance contracts for normalized events;
- relevance mapping against approved holdings and empty-portfolio cases;
- critical-source precedence and cumulative-versus-incremental event tests;
- alert promotion, deduplication, staleness, and silence behavior;
- zero-candidate and bounded-candidate cases;
- no automatic trade side effects;
- JSON/Markdown/HTML consistency for affected report surfaces;
- replay without look-ahead, with visible sample counts and pending horizons;
- real artifact generation, data-gap disclosure, and project-memory validation.

This design authorizes planning. It does not itself activate a new implementation feature or change the current `feat-044` code backlog item.
