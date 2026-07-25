# After-Close Decision Workbench Design

- Status: written review
- Date: 2026-07-23
- Decision owner: user
- Product scope: InsightRadar Core delivery surface
- Implementation authority: not granted by this document

## Decision Summary

Replace the current long-form after-close HTML page with a market-first decision workbench. The workbench preserves one canonical JSON payload and one Markdown report while rendering five task-oriented interfaces inside a single portable HTML file:

1. `今日`
2. `持仓`
3. `市场`
4. `研究`
5. `复盘`

The first screen answers four questions in order:

1. What is today's market conclusion?
2. Which cross-market states changed?
3. What does that mean for the approved portfolio?
4. What conditional action applies to each holding tomorrow?

The product borrows the horizontal comparison pattern of a global-market matrix, but it does not copy an opaque 0–100 temperature model. The first version uses existing, explainable states, changes, trends, freshness, and authority labels.

## User Problem

The current after-close report is difficult to use because it combines a decision cockpit, market dashboard, research report, audit log, and provider diagnostics in one long page. This creates four failures:

- unrelated cards receive equal visual weight;
- the user must search for the next-session action;
- stale or conflicting facts can appear beside precise actions without a clear trust boundary;
- internal statuses and raw provider exceptions leak into the reading experience.

The redesign must support the user's actual reading sequence: understand the market environment first, then translate it into portfolio consequences and conditional actions.

## Product Goal

After the close, the user should be able to:

- understand the market regime within the first screen;
- identify abnormal cross-market changes without reading every card;
- see how the market state affects the portfolio;
- reach the per-holding action plan within 30 seconds;
- inspect evidence, methodology, gaps, and past outcomes only when needed.

## Non-Goals

This design does not:

- create or calibrate a new 0–100 market-temperature score;
- authorize automatic trading or deterministic orders;
- add cloud deployment, a new client, or a local web service;
- make Lab or Extension signals part of Core decision authority;
- add Hong Kong technology or China government-bond providers in the first implementation;
- hide missing, stale, or blocked inputs;
- remove the existing Markdown report or change JSON into a presentation-only format.

## Information Architecture

### Global shell

The HTML report uses a persistent application shell:

- desktop: left navigation and top data-status bar;
- mobile: bottom navigation and a compact status header;
- main content: one task-oriented interface at a time.

The global status bar shows independent timestamps and states for:

- portfolio snapshot;
- market-risk data;
- market-level data;
- research or filing data when used;
- strict decision-ready coverage.

A single generic “data as of” date is prohibited when the sources have different effective dates.

### 今日

The `今日` interface is the default route. It contains, in order:

1. **今日市场结论**
   - one conclusion sentence;
   - one short explanation;
   - current risk stance and budget authority.
2. **全球市场矩阵**
   - compact cross-market cards;
   - abnormal or unavailable cards receive priority;
   - no opaque temperature score.
3. **对持仓的直接含义**
   - one concise portfolio-impact statement;
   - explicit statement when the matrix does not change the plan.
4. **明日持仓动作**
   - one row per holding;
   - first action, trigger, blocker, and priority;
   - row click opens the holding action playbook.
5. **数据阻断与今日变化**
   - compact summaries only;
   - full evidence and errors stay in secondary interfaces.

On a desktop viewport of at least 1440×900, the market conclusion, complete matrix, and portfolio-impact statement must fit in the first viewport. The holding-action section must begin in that viewport or be reachable with one short scroll.

### 持仓

The `持仓` interface first compares all holdings, then provides a dedicated holding view.

The first screen of a holding view is the next-session action playbook:

- current action;
- upside scenario;
- flat scenario;
- downside scenario;
- trigger and invalidation;
- execution blocker;
- next review point.

Price charts and key levels are the second layer. Filings, research evidence, and thesis history are the third layer. Charts and research may explain an action but must not precede the action playbook.

### 市场

The `市场` interface answers why the market conclusion was reached. It contains:

- current risk state and budget constraint;
- expanded global-market matrix;
- A-share breadth and structure;
- market-level state;
- style rotation;
- macro transmission;
- methodology, freshness, and gaps.

Clicking a market card reveals:

- current state and change;
- 30-day trajectory;
- source and effective date;
- state inputs;
- affected holdings;
- counter-evidence;
- diagnostic or decision authority.

### 研究

The `研究` interface contains:

- official filings;
- supplier-realization and AI CapEx evidence;
- industry and peer evidence;
- research hypotheses;
- confirming and falsifying evidence;
- missing inputs and next review dates.

Research cards may link to holdings but may not duplicate the holding action playbook.

### 复盘

The `复盘` interface separates the prior plan from hindsight. It records:

- the plan issued before the session;
- whether its trigger occurred;
- whether the user acted, when known;
- 1/5/20-session outcome maturity;
- benchmark-relative outcome;
- data quality and unresolved gaps.

Pending samples remain visibly pending. The interface must not claim a stable edge from immature samples.

## Global-Market Matrix

### Display contract

Each card has one stable display contract:

- market or driver name;
- state label such as `升温`, `适中`, `降温`, or `不可用`;
- daily or latest completed-session change;
- 30-day sparkline;
- effective date;
- freshness state;
- authority label;
- optional portfolio-impact marker.

Cards must not show a numeric score unless that score already has a documented formula, test coverage, and calibration status.

### Grouping

Do not put unlike assets on one implied temperature scale. The matrix uses two semantic groups.

**Global technology and risk assets**

- A-share technology and growth structure;
- US technology;
- Korea;
- Japan when fresh data are available.

**Macro pressure**

- crude oil and energy shock;
- US 10-year yield or duration pressure.

Hong Kong technology and China government bonds are future candidates. They are not silently inferred from unrelated proxies. If a configured first-version series is unavailable, its card remains visible in an unavailable state with the reason and last valid date.

### Portfolio translation

The matrix is followed by one portfolio-translation sentence. It must say one of:

- the market state changes a portfolio action;
- the market state changes only observation priority;
- the market state does not change the current plan.

Diagnostic states such as macro transmission cannot authorize a trade or override a hard risk veto.

## Visual Hierarchy

- Neutral cards use restrained colors.
- Yellow and red are reserved for abnormal, stale, blocked, or risk states.
- Green is not a generic decoration; it means fresh, recovered, or explicitly favorable.
- Only the most important abnormal cards receive visual emphasis.
- Repeated badges, borders, headings, and explanatory text are reduced.
- Internal enum values are translated into plain Chinese.
- Raw exception strings are excluded from normal interfaces.

## Freshness and Failure States

Every displayed value is one of:

1. **Fresh**
   - rendered normally;
   - source date visible.
2. **Stale**
   - rendered with reduced emphasis;
   - explicit `已过期` label;
   - cannot upgrade risk or authorize new exposure.
3. **Unavailable**
   - grey placeholder remains in the expected position;
   - plain-language reason such as `数据源超时` or `尚未接入`;
   - no numeric fallback from an unrelated or older source.
4. **Blocked**
   - the value may exist, but a required decision input is incomplete;
   - the blocker is shown beside the affected action.

Provider details such as stack traces, URLs, and `HTTPSConnectionPool` messages belong only in an audit disclosure or backend log.

## Mobile Behavior

- Replace the left navigation with a five-item bottom navigation.
- Render the matrix as a horizontal card strip or a two-column grid; do not compress six cards into unreadable columns.
- Convert the holding action table into one compact action card per holding.
- Keep market conclusion, abnormal cards, and the first portfolio impact visible before long evidence.
- Do not expose desktop-only hover interactions; every detail must be reachable by tap.

## Rendering Architecture

The report remains a timestamp-aligned triplet:

- `reports/*-after-close.json`
- `reports/*-after-close.md`
- `reports/*-after-close.html`

The JSON payload remains the canonical client contract. Markdown remains the durable text renderer. HTML becomes a single-file application with hash routes:

- `#today`
- `#holdings`
- `#market`
- `#research`
- `#review`

All required data and assets are embedded in the HTML so the report works when opened directly from the local filesystem. The renderer must not depend on `fetch()` against a local file, a long-running local server, or a cloud service.

The HTML renderer should be decomposed into focused rendering units:

- app shell;
- global freshness bar;
- market conclusion;
- matrix group and card;
- portfolio-impact bridge;
- holding action table;
- holding action playbook;
- market-detail sections;
- research cards;
- review table;
- audit disclosure.

These units consume a normalized report view model derived from the existing after-close payload and its already-consumed upstream reports. Presentation units do not query providers directly.

## Data Flow

```text
risk-watch / market-levels / style-rotation / ai-capex-watch
                              |
                              v
                     after-close payload
                              |
                    normalized view model
                       /       |       \
                      v        v        v
                   JSON     Markdown   HTML workbench
```

The matrix reuses existing Core evidence:

- A-share breadth and growth structure from `risk-watch`;
- US technology, Korea, Japan, oil, and rate series when available from the existing risk and macro-transmission inputs;
- style state from `style-rotation`;
- decision authority and portfolio impact from `unified_decision`.

The first implementation does not create a separate provider-fetching workflow merely to fill visual cards.

## Compatibility

- Existing JSON fields remain valid.
- New optional view data must be additive and default safely when absent.
- Existing Markdown output remains available.
- Existing actions remain conditional.
- Structural action coverage and strict decision-ready coverage remain distinct.
- A stale market level or incomplete portfolio continues to block strict readiness.

## Acceptance Criteria

### Product behavior

- The default route is market-first `今日`.
- The first viewport contains the market conclusion, matrix, and portfolio translation.
- All current holdings have a visible conditional action row.
- A holding row opens the action playbook before charts or research.
- The five interfaces are navigable without reloading or a server.
- Market and research details do not duplicate the complete homepage content.

### Trust behavior

- Independent data dates are visible.
- Stale, unavailable, and blocked states are visually and semantically distinct.
- Missing data never becomes zero.
- No raw provider exception appears in the normal UI.
- No uncalibrated 0–100 global-temperature score appears.
- Diagnostic macro signals cannot authorize trades.

### Responsive behavior

- No horizontal page overflow at desktop or 390-pixel mobile width.
- Mobile navigation and holding cards are usable by touch.
- Matrix cards remain legible on mobile.
- The complete mobile experience does not rely on hover.

### Consistency

- JSON, Markdown, and HTML agree on holdings, actions, dates, risk state, and readiness.
- The HTML holding count must match the canonical payload.
- Portfolio action precision must not exceed decision readiness.
- Source dates in conclusions and cards must match the underlying source records.

## Verification Strategy

Implementation must include:

- unit tests for view-model normalization and state precedence;
- rendering tests for all five routes and empty or partial data;
- tests for fresh, stale, unavailable, and blocked matrix cards;
- tests that raw provider exceptions do not appear in normal UI;
- tests that no uncalibrated score is rendered;
- JSON/Markdown/HTML consistency assertions;
- desktop and 390-pixel browser checks for overflow and navigation;
- a fresh real `after-close` artifact;
- a 30-second usability check: identify market state, portfolio impact, and each holding's first action;
- project-memory and relevant Harness validation.

## Rollout Boundary

This redesign is one delivery-surface experiment. It should not run concurrently with an unrelated Core feature implementation. Before implementation, the active feature queue must explicitly authorize this work relative to `feat-056`.

The first release succeeds if it materially reduces reading time and removes trust conflicts without changing trade authority. New temperature scoring, new market-data providers, and richer charts require separate evidence and admission.
