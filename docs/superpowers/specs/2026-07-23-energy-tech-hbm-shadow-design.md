# Energy, Technology, and HBM Shadow-Intelligence Design

> This English document is the canonical, normative specification and AI guidance source. The [Chinese human-review copy](2026-07-23-energy-tech-hbm-shadow-design.zh-CN.md) is non-normative; if the two differ, this English document controls.

- Status: user-approved design direction; implementation not authorized
- Date: 2026-07-23
- Decision owner: user
- Product lead: primary Codex agent
- Queue effect: none; `feat-056` remains next and sole queued Harness experiment
- Execution preference: single agent by default; multi-agent work requires an explicit request and independently separable tasks with a measured speed advantage

## Decision Summary

InsightRadar may add the NGA observation as two independent, read-only shadow layers:

1. a macro-transmission layer that asks whether an energy supply shock is becoming a rates and technology-duration shock; and
2. an HBM profit-allocation layer that asks where AI demand is becoming contracted volume, pricing power, and realized margin.

The layers must not be collapsed into one composite score. Crude oil rising by itself is not a technology sell signal, and an HBM long-term agreement by itself is not proof that supplier profit will rise. The first layer belongs beside `risk-watch` as diagnostic evidence; the second belongs inside `ai-capex-watch` as industry-thesis evidence. Neither receives trade authority or risk-budget authority during shadow operation.

This design records a candidate product direction only. It does not register or activate a feature, change `CURRENT_STATE.md`, modify the active queue, or authorize implementation.

## Product Question

The observed narrative is plausible:

`war or supply disruption -> crude-oil shock -> inflation and rate pressure -> lower valuation/capital-spending tolerance for long-duration technology -> relative weakness in technology and energy-importing Korea`

A second narrative concerns industry profit allocation:

`AI demand -> HBM qualification and long-term agreements -> volume visibility and pricing power -> memory/packaging constraints and DRAM opportunity cost -> realized supplier margin`

Both narratives are useful only if the product separates:

- event discovery from primary-source confirmation;
- contemporaneous co-movement from causality;
- absolute return from benchmark-relative return;
- one current episode from a stable historical relationship;
- demand visibility from profit realization;
- diagnostic evidence from decision authority.

## Exploratory Evidence Baseline

The 2026-07-23 research snapshot is exploratory evidence, not a production backtest. Market-specific latest-close dates may differ because of calendars and time zones.

### Current episode

From 2026-06-30 to the latest available close in the snapshot:

| Asset or index | Return |
|---|---:|
| Brent crude | +31.84% |
| WTI crude | +27.14% |
| PetroChina A | +25.58% |
| CNOOC A | +24.10% |
| XLE | +11.47% |
| QQQ | -4.22% |
| Philadelphia Semiconductor Index | -12.89% |
| KOSPI | -17.01% |
| Samsung Electronics | -19.54% |
| A-share semiconductor ETF proxy | -26.81% |
| SK Hynix | -27.96% |

The US 10-year yield moved from 4.418% to 4.657%, an increase of 23.9 basis points. This episode is consistent with the proposed transmission path, but consistency does not establish that crude oil caused the entire technology drawdown.

### Longer-history checks

Using weekly observations from 2016 onward, raw Brent correlations with QQQ, SOX, and KOSPI were respectively `+0.150`, `+0.129`, and `+0.161`. Benchmark-relative correlations were weaker or negative: QQQ minus S&P 500 `-0.107`, SOX minus S&P 500 `+0.002`, and KOSPI minus S&P 500 `-0.039`.

In the 2026 slice, benchmark-relative correlations became more negative: QQQ `-0.113`, SOX `-0.349`, and KOSPI `-0.334`, based on only 30 weekly observations. This supports a current-regime diagnostic but is too small and unstable for a timeless scoring rule.

An oil-only event definition of a five-day crude gain of at least 8% produced 33 historical events. Average 20-trading-day forward absolute returns were positive for QQQ `+1.61%`, SOX `+3.12%`, and KOSPI `+2.35%`. Oil rising alone therefore failed as a reliable technology-risk signal.

A stricter triple-confirmation sample—oil shock, rising yields, and technology relative weakness—produced only nine events. Average 20-day absolute returns were QQQ `-1.24%`, SOX `-0.33%`, and KOSPI `-0.31%`, while benchmark-relative outcomes were not stably negative. This is directional evidence with insufficient sample size, not an accepted factor.

### Evidence conclusion

The observation is useful as a conditional regime detector:

- the current episode fits it strongly;
- the long-history unconditional relationship does not;
- oil-only triggers are contradicted by forward-return evidence;
- joint confirmation is more plausible but statistically underpowered;
- production use must remain shadow-only until point-in-time, cross-regime, out-of-sample evidence accumulates.

## Accepted Architecture

The implementation, if separately authorized later, remains inside the modular monolith and introduces typed observation contracts rather than a new service.

### Lane A: macro transmission

The lane produces a `macro_transmission` observation with three independent state objects:

- `energy_supply_shock`;
- `duration_pressure`;
- `korea_import_stress`.

Each state records:

- state value: `unavailable`, `observe`, `confirmed`, or `invalidated`;
- observation time, market-session date, fetch time, and timezone;
- source URLs and primary-source verification status;
- current values and five-/20-trading-day changes;
- triggered and blocked rule IDs;
- benchmark-relative confirmation;
- historical event count and calibration status;
- counter-evidence, unresolved gaps, and next review condition;
- authority fixed to `diagnostic_only`.

Candidate inputs are:

- Brent and WTI returns over fixed trading-day windows;
- crude term structure or physical-market evidence only when a reliable point-in-time source exists;
- US 10-year yield change;
- QQQ versus S&P 500 and SOX versus S&P 500;
- KOSPI versus SOX and KOSPI versus S&P 500;
- KRW or another Korea import-cost channel only after source reliability is validated;
- verified geopolitical, supply, sanctions, inventory, production, or ceasefire evidence.

`risk-watch` may render this lane as a diagnostic shadow section and archive it for later replay. It may not add its result to an existing risk family, change a light color, change a risk budget, or override `RISK_VETO` during shadow operation. `after-close` may cite it only as an explanatory condition or a monitoring priority.

### Lane B: HBM profit allocation

The lane produces an `hbm_profit_allocation` observation with:

- `volume_visibility`;
- `pricing_power`;
- `margin_realization`;
- `capex_budget_competition`;
- overall confidence, source coverage, and explicit gaps.

Candidate evidence includes:

- disclosed contract or nomination window;
- fixed, indexed, or renegotiable price mechanism when disclosed;
- HBM generation and customer qualification milestones;
- shipment, mix, capacity, yield, packaging, and substrate constraints;
- conventional DRAM opportunity cost and capacity allocation;
- supplier revenue, gross margin, operating cash flow, inventory, and receivables;
- customer concentration and cancellation or requalification conditions;
- official hyperscaler CapEx and network-transmission evidence already owned by `ai-capex-watch`.

Contract announcements improve volume visibility only. Pricing power remains unknown without price or mix evidence. Margin realization remains unknown until shipment, yield, cost, and financial evidence agree. HBM strength may reallocate profit within the AI chain even when total AI CapEx remains healthy, so the lane must show winners, bottlenecks, and offsets rather than output one sector-wide bullish label.

`ai-capex-watch` owns this lane. It may change industry-thesis confidence after its existing official-evidence gates, but it cannot override `risk-watch`, create orders, or upgrade portfolio exposure by itself.

### Jin10 boundary

The future `feat-055` event-intelligence layer may discover war, ceasefire, sanctions, supply disruption, producer-policy, and HBM contract clues. Jin10 remains a discovery and reconciliation source:

- material claims require primary-source confirmation where available;
- a digest links or recovers child events without duplicating them;
- provider importance and red-highlight fields remain `unknown` unless exposed structurally;
- a headline cannot authorize a state transition that requires market or financial confirmation;
- no new Jin10 runtime work begins under this design.

## State Logic

### Macro state machine

1. **Oil rises without corroboration:** set `energy_supply_shock=observe` or retain an explicit demand/unknown alternative. Do not infer technology risk.
2. **Supply evidence and oil shock agree:** `energy_supply_shock=confirmed`; retain its expected duration and invalidation condition.
3. **Oil shock, yield pressure, and technology relative weakness agree:** `duration_pressure=confirmed`. Without all required fields, remain `observe` or `unavailable`.
4. **KOSPI relative weakness plus verified import-cost or energy-supply evidence:** `korea_import_stress=confirmed`. KOSPI weakness alone is insufficient.
5. **Ceasefire or supply normalization:** it may invalidate `energy_supply_shock` after price/supply confirmation. It does not automatically repair technology or KOSPI; repair requires separate relative-price confirmation.
6. **Contradictory evidence:** preserve both paths, block confirmation, and record the next observation that can resolve the conflict.

Initial thresholds are research hypotheses, not product constants. They must be versioned, replayed, and promoted only through the calibration gates below.

### HBM state machine

1. A reported agreement without a primary contract, company filing, or investor-relations confirmation remains `discovered`.
2. A confirmed contract or qualification milestone may set `volume_visibility=positive`.
3. `pricing_power=positive` requires disclosed price/mix evidence or consistent realized financial evidence; contract duration alone is insufficient.
4. `margin_realization=positive` requires shipment or revenue realization plus yield/cost/margin evidence. Inventory or receivables deterioration remains visible counter-evidence.
5. Capacity competition that constrains ordinary DRAM, packaging, networking, or customer budgets sets `capex_budget_competition=observe` until measurable effects appear.
6. Missing fields remain `unknown`; they are never converted to zero or neutral.

## Point-in-Time and Data Contract

Every replay must use only information known by the evaluation timestamp:

- event publication time and later primary-source confirmation time are separate;
- exchange calendars, completed closes, holidays, and time zones are market-specific;
- revised macro or company values retain vintage or filing timestamps where available;
- forward outcomes are evaluation labels only and never enter features;
- event windows are de-overlapped or clustered so one war episode is not counted as many independent observations;
- benchmarks and return conventions are declared before results are computed;
- survivorship-prone constituent series are avoided or explicitly labeled.

Provider failure, missing history, stale closes, calendar mismatch, or incomplete pagination must create explicit gaps and reduce coverage. No fallback may silently change the definition of a series.

## Report Contract

Any future implementation preserves existing JSON, Markdown, and HTML outputs.

The `risk-watch` shadow section answers in concise Chinese:

- whether an energy supply shock is observed or confirmed;
- whether yields and technology relative prices corroborate it;
- whether Korea shows additional import-cost stress;
- what contradicts the interpretation;
- what would confirm, invalidate, or end the state;
- whether the item changes only monitoring priority—which is always the answer during shadow mode.

The `ai-capex-watch` HBM section answers:

- what agreement or qualification evidence is new;
- whether it changes volume visibility, pricing, or realized margin;
- where the bottleneck and profit pool may move;
- which supplier financial fields confirm or contradict realization;
- what remains unknown;
- whether the industry thesis changes while the portfolio risk budget remains unchanged.

The first screen must not imply precision through a single combined gauge. Independent states, evidence age, coverage, and calibration labels remain visible.

## Calibration and Promotion Gates

Shadow observations are archived daily but excluded from production scoring. Promotion requires all of the following:

1. point-in-time replay from at least 2016 across supply-shock, demand-led, easing, tightening, and calm regimes;
2. at least 60 de-overlapped independent macro events, or an equivalently justified cross-regime sample, plus a held-out out-of-sample period;
3. declared absolute and benchmark-relative horizons, drawdown, hit rate, false-positive rate, and confidence intervals;
4. stability checks across plausible thresholds rather than selection of one best in-sample threshold;
5. explicit comparison of oil-only, oil-plus-rates, and triple-confirmation rules;
6. market-calendar, timezone, stale-data, source-conflict, and no-lookahead tests;
7. event deduplication and digest-reconciliation tests;
8. HBM evidence replay across at least two reporting quarters after contract or qualification milestones, including shipment, margin, cash-flow, inventory, and receivables realization;
9. proof that the shadow improves warning precision, explanation quality, or manual research time without materially increasing alert noise;
10. separate user approval before any score, light-color, risk-budget, candidate, or alert-authority change.

If the evidence remains regime-specific, the layer stays diagnostic. If it fails to improve product decisions, it is merged into background research or parked.

## Test and Artifact Acceptance

A later implementation is not complete until:

- typed-state unit tests cover every confirmation, invalidation, missing-data, and contradictory-evidence branch;
- deterministic fixtures prove that oil-only cannot confirm duration pressure;
- no-lookahead replay reproduces event counts and outcome metrics;
- source timestamps and URLs survive JSON, Markdown, and HTML rendering;
- existing `risk-watch`, `ai-capex-watch`, `after-close`, project-memory, and architecture tests pass;
- fresh CLI runs produce inspectable JSON, Markdown, and HTML artifacts;
- architecture metadata and generated documentation are refreshed if topology is materially changed;
- feature evidence records the exact commands, artifacts, sample sizes, and residual gaps.

## Alternatives Considered

### One composite oil-versus-technology score

Rejected. It overfits the current episode, hides conflicting transmission paths, and falsely turns correlation into trade authority.

### Two bounded shadow layers

Accepted. It preserves the separate owners of macro risk and industry profit allocation, supports replay, and makes unknowns and counter-evidence visible.

### Manual checklist only

Useful during research but insufficient as the final product. It does not create typed, timestamped, replayable evidence or outcome calibration.

## Non-Goals

- automatic trading, position sizing, or an oil-to-technology rotation instruction;
- claiming that crude oil caused a specific technology drawdown;
- forecasting war start or end from prices alone;
- inferring HBM contract price, customer, margin, or allocation when undisclosed;
- replacing official filings, investor relations, exchanges, or macro primary sources;
- adding a new service, cloud dependency, generic news terminal, or provider-specific UI;
- changing the current feature queue or starting `feat-044`, `feat-055`, or a new feature implicitly;
- using multi-agent execution merely because the design spans multiple markets.

## Implementation Authorization Boundary

User approval of this design means the product direction and boundaries are accepted. It does not authorize code changes. After the user reviews the written specification, implementation requires a separate plan, explicit queue or priority decision, and the repository's normal one-feature-at-a-time verification loop.
