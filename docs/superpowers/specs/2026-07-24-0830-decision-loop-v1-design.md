# InsightRadar 08:30 Decision Loop V1

- Status: owner approved
- Date: 2026-07-24
- Decision owner: user
- Product scope: InsightRadar Core delivery and review loop
- Related active feature: `feat-058`
- Implementation authority: throwaway prototype refinement granted; runtime integration remains unapproved

## Decision Summary

This specification narrows the first useful product wedge without changing the
long-term product mission, North Star, or no-trade boundary.

InsightRadar remains a personal A-share investment decision-intelligence
system. Its durable loop remains:

`Observe -> Explain -> Decide -> Verify`

V1 proves that mission through one repeated job:

> At 08:30 China Standard Time, help the user remember, revalidate, and confirm
> no more than three conditional plans for the current portfolio in under three
> minutes.

The product is not a model gallery, a generic market-news dashboard, or an
automated trading system. A valid morning may contain zero new decisions.

## Why the Existing Product Feels Unhelpful

The current product has broad evidence coverage and strong failure boundaries,
but capability count has not translated into a short user task. The user still
has to:

- find the relevant facts across market, research, and holding views;
- remember the prior evening's plan after sleeping;
- translate overnight US and early Asian trading into A-share consequences;
- interpret technical indicators with inconsistent confirmation semantics;
- decide whether a new fact actually changes an existing plan;
- reconstruct later whether the strategy or the user's execution failed.

The current workbench and launchers remain useful foundations. V1 changes the
center of gravity from “show the market and all available evidence” to “preserve
and supervise a small number of confirmed plans.”

## Reference Patterns

Reference products are used for proven workflows, not feature imitation:

- Arkvol: learn from model-focused pages, long histories, and fast visual
  orientation; reject page-per-model sprawl and generic allocation language
  derived from a single sentiment indicator.
- TIKR: learn from a holdings-relevant event feed.
- Koyfin: learn from threshold alerts that retain a next-step note.
- iWencai: learn from direct stock-code and natural-language lookup.
- Choice: learn from the connected portfolio overview, monitoring, and analysis
  workflow.

InsightRadar's differentiator is not wider data coverage. It is a remembered,
evidence-linked, conditional plan for the user's actual A-share portfolio.

## Primary User and Deployment Boundary

V1 is a local, single-user product for a self-directed A-share investor.

V1 does not add:

- accounts, login, multi-tenancy, subscriptions, or cloud synchronization;
- automatic order execution;
- mobile clients;
- Redis, MySQL, or a distributed runtime;
- a five-minute intraday alert loop;
- AI authority over rules, risk budgets, or actions.

Stable data contracts and storage seams must permit later adapters, but V1 must
not pay the complexity cost of an unproven hosted product.

## Daily Loop

### After close: draft

The product generates a next-session draft from completed A-share data,
holdings, filings, research, risk state, and the most recent confirmed plan.
This draft is not a new commitment and must not silently replace the confirmed
plan.

### 08:30 CST: revalidate and confirm

The morning run incorporates:

- completed US trading, with emphasis on QQQ, SOX, rates, and relevant peers;
- the first approximately 30 minutes of Japan and Korea trading;
- overnight A-share filings, policy events, and material company news;
- updated rule states and data freshness;
- the prior confirmed plan as the comparison baseline.

Each retained plan receives exactly one morning change state:

- `unchanged`: new evidence does not alter the plan;
- `revised`: new evidence changes a condition, action, or confidence;
- `void`: the prior plan's assumptions or risk conditions no longer hold.

The user handles each morning plan with one explicit response:

- accept the generated plan;
- dispute a condition, level, market judgment, evidence state, or intended action;
- reject the generated plan;
- defer the decision.

The accepted version becomes the only new plan that later alerts and reviews may
reference. A dispute preserves both the generated version and the user's
structured objection; it does not silently activate the draft. Rejection and
deferral remain visible. Batch acceptance may affect only untouched plans and
must never overwrite an explicit dispute, rejection, or deferral.

If no new plan is accepted before the open, the product preserves the latest
accepted plan as a visibly stale or partially validated baseline. New
opportunity alerts stay disabled; an existing confirmed invalidation or risk
alert may remain eligible under the notification budget.

### During the session: V1 boundary

V1 may show conditions as pending, but it does not implement a continuous
five-minute alert loop. That loop belongs to V2.

The future authority split is already fixed:

- daily bars decide whether a plan is valid;
- 30-minute bars may confirm direction;
- five-minute bars may choose alert timing;
- a single five-minute signal cannot overturn a daily plan.

The prototype may show this V2 handoff as a labelled design preview. It must not
claim that five-minute polling, delivery, or runtime alerting is implemented.

### After close: review

The product automatically records whether each market condition triggered. The
user records actual behavior with one of:

- executed;
- partially executed;
- not executed;
- alert not seen.

Strategy quality and execution quality remain separate.

## Information Architecture

V1 has four first-level task routes:

1. `今日计划`
2. `我的持仓`
3. `个股查询`
4. `复盘`

Market, research, filings, global transmission, and technical indicators are
evidence inside these tasks. They are not first-level destinations.

The interaction pattern is deliberately mixed:

- task changes and stock strategy details use separate routes;
- short definitions use an `ⓘ` tooltip;
- compact supporting evidence uses a drawer;
- complete methodology, source records, and audit data use a dedicated detail
  route;
- the Today route must not become an indefinitely expanding accordion.

## Today Route

The Today route is action-first and shows at most three decision cards. Zero is
a valid count. Holdings with no material change are summarized as “continue the
confirmed plan; no action required.”

Each card shows, without expansion:

- security and current state;
- morning change state: unchanged, revised, or void;
- one primary action;
- one measurable `IF`;
- one explicit `THEN`;
- validity horizon;
- invalidation condition;
- current trigger progress;
- confirmation state.

Evidence, charts, gaps, and computation details are secondary.

## Conditional Strategy Contract

Every strategy uses this form:

```text
IF <observable and machine-testable condition>
THEN <one bounded action>
UNTIL <declared horizon or review time>
INVALID IF <observable invalidation>
```

Each stock has at most:

- one primary plan;
- one upside contingency;
- one downside contingency.

Waiting or range-bound behavior belongs in the primary plan. The renderer must
reject or visibly flag vague actions such as:

- 密切关注
- 适当操作
- 灵活处理
- 视情况而定

Permitted action families include:

- wait;
- set an alert;
- continue holding;
- prohibit adding exposure;
- reduce risk conditionally;
- enter further research;
- mark a thesis invalid.

Non-holding analysis cannot manufacture personalized quantities or account
actions.

## State Instead of a Magic Score

The stock strategy route does not lead with an opaque composite score. It uses
explainable states with visible promotion and demotion conditions:

- `avoid`
- `observe`
- `near_trigger`
- `condition_met`
- `thesis_invalid`

Existing calibrated or diagnostic scores may remain as evidence, with units,
sources, dates, and authority labels. They cannot replace the state or hide
conflicting inputs.

## Technical Evidence

### Default visible layer

The stock detail route always permits:

- daily candlesticks;
- volume;
- MA20 and MA60;
- current price distance from trigger and invalidation levels;
- one automatically selected primary benchmark.

### Conditional layer

The following appear only when they change a level, invalidation, or
confidence:

- MACD crossover or state;
- top or bottom divergence;
- Fibonacci retracement levels;
- other technical evidence with a documented rule.

Indicators do not vote. Conflicting indicators lower confidence or preserve the
current plan.

### Parameterized condition dictionary

Every term used by a plan has a machine-testable definition. The user can open
the definition through a tooltip or detail popover and may later edit supported
parameters.

Default examples:

- Intraday initial reclaim: three consecutive completed 15-minute closes above
  the level. Wicks may cross the level, but a 15-minute close may not.
- Daily reclaim: the completed daily close is above the level.
- Strong reclaim: a daily reclaim followed by a retest that does not close
  below the level on the declared confirmation timeframe.
- Volume confirmation: cumulative volume compared with the median cumulative
  volume at the same time over the prior 20 eligible sessions.
- Divergence: both price pivots, both indicator pivots, timeframe, and direction
  are shown.
- Fibonacci level: the selected start and end pivots and the pivot-selection
  rule are shown.

The interface shows progress such as `0/3`, `1/3`, or `3/3`. At 08:30, an
intraday condition remains pending and cannot be described as triggered.

## Benchmark Overlay

Charts normalize the selected start date to `100`; unlike price levels are not
plotted on one raw axis.

The product automatically selects one primary benchmark:

- large-cap Shanghai/Shenzhen main-board security: CSI 300;
- medium or small main-board security: CSI 500 or CSI 1000;
- ChiNext security: ChiNext Index;
- STAR Market `688` security: STAR 50.

Every A-share strategy also carries a Shanghai Composite market-risk gate.
This gate is separate from the stock's primary performance benchmark: it may
permit, constrain, or veto a promotion in action state, but the interface must
show the relevant completed-bar condition instead of treating the index level
as a vague macro opinion.

The user may optionally add auxiliary benchmarks such as QQQ or SOX. Auxiliary
US benchmarks provide risk and industry context; they do not become the primary
performance benchmark for every A-share security.

## Theme Temperature Detail

Theme temperature is a secondary evidence route, not a fifth first-level task.
The Today route may show one compact holdings-relevant constraint and link to a
detail page; Stock Lookup may show the mapped sub-sector; Review owns historical
rule validation.

The first prototype theme is A-share AI hardware, represented by one declared
ETF proxy per sub-sector across semiconductors, chips, AI, communications,
compute leasing, ChiNext growth, and commercial aerospace. Similar ETFs must
not be double-counted without an explicit basket rule.

Floor and ceiling lines are useful orientation aids, but values such as `35`
and `80` remain unbacktested parameters. A value below the floor is labelled
`低位候选`, not automatic `黄金坑` or buy authority. Promotion requires the
declared combination of low position, stabilization/breadth, relative-strength
improvement, and a non-vetoing Shanghai Composite risk gate.

Until the source calculation is fully specified, the product must not claim to
reproduce a reference product's greed algorithm. Structured rule data and AI
explanation share one evidence fingerprint; inconsistent or stale prose blocks
the explanation rather than overriding current values.

## Universe, Watchlist, and Holdings

Three concepts remain distinct:

- security universe: searchable A-share master covering the current market;
- watchlist: user-selected securities that receive research and event context;
- holdings: approved current positions eligible for personalized morning plans.

The stock lookup route accepts a code or name and returns a generic conditional
strategy. It offers:

- add to watchlist;
- mark as a holding;
- import or complete position context;
- open chart and evidence;
- prepare a next-session observation plan.

Holding intake supports manual addition, paste, and common broker file formats.
Every import remains preview-first and approval-gated. Missing fields stay
unknown. A security with no approved position context cannot be presented as a
decision-ready holding.

## Overnight Relevance Mapping

The Today route does not reproduce a generic US market summary. International
evidence enters the first screen only when it:

- maps to an approved holding;
- maps to a relevant industry or supply chain;
- changes the portfolio risk budget;
- changes a trigger, invalidation, or confidence;
- voids a previously confirmed plan.

The product must state the mapping chain, for example:

```text
SOX change -> semiconductor risk appetite -> affected A-share holding
US yield change -> duration pressure -> high-valuation growth exposure
peer guidance -> supplier thesis -> holding plan unchanged/revised/void
```

Unmapped international news belongs in the evidence layer.

## Rule and AI Authority

### Rule authority

Rules own:

- indicator calculation;
- trigger and invalidation evaluation;
- timeframe authority;
- state transitions;
- risk-budget constraints;
- notification deduplication;
- review and outcome calculations.

### AI authority

An inexpensive AI/NLP model may:

- extract facts from filings, news, and transcripts;
- map unstructured events to holdings, sectors, or themes;
- summarize supporting and opposing evidence;
- explain structured rule results in plain Chinese;
- flag a case not covered by the current condition dictionary.

AI may not:

- calculate authoritative indicators;
- overwrite a rule state;
- change a risk budget;
- turn unclassified evidence into an action;
- create or execute an order.

An uncovered case renders:

> 检测到未分类事件；原计划暂不改变，需要人工确认。

A later version may run AI in shadow mode and compare its proposed changes with
outcomes before any authority is reconsidered.

## AI Reuse and Storage Seam

Page refreshes, fixed timers, and ordinary price ticks do not trigger AI.

AI reuse is keyed by:

- normalized evidence fingerprint;
- rule version;
- prompt version;
- model identity;
- affected security and declared horizon.

A new AI call is permitted only when:

- a material filing, event, transcript, or news item is new or revised;
- a meaningful rule-state transition requires a new explanation;
- the prompt, rule, or model version changes;
- the user explicitly requests reanalysis.

V1 stores JSON records. Callers use one deep Module interface:

```text
get_or_analyze(symbol, evidence, rule_state)
-> cached | recomputed | skipped
```

The Module hides fingerprinting, cache lookup, model invocation, validation,
and persistence. Future Redis or MySQL adapters must satisfy the same interface;
the decision engine and renderer must not depend on storage technology.

Every saved explanation records source identifiers, source times, generated
time, versions, validation state, and whether the result came from cache.

## Failure and Degradation

Failure is local to the authority that needs the missing input:

- missing US evidence preserves the prior plan and blocks a confidence upgrade;
- missing Japan or Korea data removes that confirmation but does not erase the
  holding plan;
- missing technical data preserves existing levels but blocks claims about the
  unavailable indicator;
- missing position quantity or weight permits a direction and condition but not
  a personalized quantity;
- an unknown beta class blocks risk reconciliation but does not erase the
  holding or its non-quantity plan;
- only an unconfirmed security identity, invalid portfolio record, or missing
  critical price state blocks the affected holding card.

The product always preserves the latest confirmed plan. It may label that plan
stale, partially validated, or blocked; it may not silently replace it with
empty output.

## Notifications

V1 sends at most one ordinary notification per day:

- at 08:30, report the count of unchanged, revised, and void plans;
- clicking opens the Today route;
- failure to confirm does not cause another ordinary push;
- UI badges may retain an unconfirmed state without notification.

Only a future material state transition, such as a confirmed invalidation, may
bypass the ordinary notification budget. Identical security-condition states
deduplicate, and simultaneous events aggregate into one message.

## Review and Outcome Contract

Every plan declares its evaluation horizon before the outcome is known:

- intraday execution: same-session review;
- short horizon: one to three sessions;
- swing horizon: five to twenty sessions;
- medium-term thesis: until its declared invalidation or review date.

Outcome review records:

- whether the condition triggered;
- whether and how the user acted;
- favorable and adverse excursion when available;
- absolute result;
- primary-benchmark-relative result;
- data completeness;
- pending versus mature status.

The product must not label a plan successful or failed before its horizon
matures. A short sample cannot establish a stable edge.

The Review route also exposes backtest readiness and, once admissible, the
point-in-time replay result. It must show the rule/parameter version, sample
count, test interval, primary benchmark, T+1/T+5/T+20 relative outcomes,
favorable/adverse excursion, payoff/expectancy, drawdown, regime splits, and
sample-out results. Before no-lookahead and coverage gates pass, these fields
remain `待跑` or `样本不足`; the prototype must not invent performance numbers.

## Ten-Session V1 Acceptance

V1 enters a ten-trading-session owner pilot only after functional verification.
The pilot passes only if:

- the morning plan is available by 08:35 on at least nine eligible sessions;
- the user can confirm the plan in under three minutes;
- zero to three cards appear, with no forced filler decision;
- every displayed strategy has a machine-testable IF, bounded THEN, horizon, and
  invalidation;
- unchanged evidence does not create a new decision or repeat an AI call;
- data-source failures degrade only affected authority;
- one ordinary daily notification is not exceeded;
- prior confirmed plans remain recoverable and auditable;
- the user voluntarily opens the product on at least seven of ten eligible
  sessions;
- the user can distinguish strategy quality from execution quality during
  review.

Returns and win rate are recorded but do not decide this short pilot. The pilot
tests usefulness, reliability, recall, and decision-loop completion.

## Migration from the Current Workbench

The current `feat-058` workbench, timestamp-aligned JSON/Markdown/HTML triplet,
loopback portfolio importer, and Windows launchers remain foundations.

Migration must:

- preserve canonical JSON and Markdown artifacts;
- preserve preview/approval portfolio safety;
- preserve source dates, gaps, and no-trade authority;
- replace the current market-first default with the 08:30 Today task;
- move market and research views into contextual evidence routes;
- add stock lookup without treating the universe as holdings;
- add plan confirmation and review records before adding continuous alerts;
- retain the old renderer as a rollback path until the new flow passes the
  ten-session pilot.

No existing implementation is declared complete by this specification. The
current manual desktop/mobile acceptance remains separate, and V1 runtime work
requires its own bounded implementation plan and verification.
