# ADR-0007: Keep Viewpoint Discipline Contracts Evidence-Bound

- Status: accepted
- Date: 2026-07-16

## Context

The tracked NGA thread `tid=46906089` proposes a useful discipline framework for holding a volatile technology theme: separate industry trend from trading structure, pre-commit portfolio drawdown responses, distinguish core and trading sleeves, and judge a theme with core-stock, chain-rotation, and style-switch evidence. The thresholds and conclusions remain author/user viewpoints, however, and the public page could not be independently fetched during this review. Current market data also showed that several static “near the 20-day line” statements had already drifted materially.

## Decision

Store reusable viewpoint frameworks with explicit source and verification status, and keep them separate from market facts and product defaults.

- A viewpoint framework may define diagnostic axes, candidate thresholds, invalidation gates, and execution rules.
- Every framework must retain `source_url`, `source_type`, `verification_status`, and review date.
- User-provided or page-unverified content may inform a report checklist, but cannot enter public sentiment percentages or substitute for filings, financial statements, cash-flow evidence, or current market data.
- Author thresholds such as 6%-8%, 10%-12%, 15%, or MA20 are candidates. They become actionable only after binding to the user's risk budget, portfolio sleeve, and observable trigger.
- “The technology mainline ended” is not an executable invalidation rule. Reports must decompose it into industry evidence, trading structure, core-stock trend, chain rotation, and sustained style-switch observations.
- Reports must surface conflicts between a framework and current evidence. They must not preserve an author prior by calling every unbroken move a washout or by ignoring a triggered rule.
- External viewpoints have no action authority. They may open a research question, but cannot directly trigger a trade, replace the original thesis after entry, or cancel an already defined reduction rule.
- “Earnings will be good” must be decomposed into official disclosure, performance versus expectations, and price response. A positive narrative with repeated price invalidation is not confirmation.
- Monthly-profit giveback bands may be proposed as user-approved candidates, but remain inactive until the user chooses the reference high-water mark and thresholds.

## Consequences

- `configs/nga_monitor.json` can carry a tracked author's decision framework inside the separately labelled influencer profile.
- The Codex-native NGA automation adds a compact strategy-contract and falsification check when relevant.
- The framework remains an optional Extension input and cannot become a hidden dependency of Core portfolio actions.
- Future promotion into Core requires independent data adapters, user-specific risk configuration, replay/outcome evidence, and an explicit feature decision.

## Revisit Trigger

Revisit after enough framework statements have verifiable timestamps and matured outcomes to calibrate whether any candidate threshold improves drawdown or expectancy for the user's actual portfolio.
