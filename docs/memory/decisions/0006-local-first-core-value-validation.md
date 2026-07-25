# ADR-0006: Validate Core Investment Value Locally Before Cloud Delivery

- Status: accepted
- Date: 2026-07-14

## Context

InsightRadar can eventually benefit from Linux portability, Docker packaging, and cloud deployment, but those investments add infrastructure, operating, security, and observability cost before the product has proved its central value. The immediate product question is not whether the system can be hosted broadly. It is whether its portfolio-aware guidance can improve decision quality and support durable compounding after costs and risk, with evidence that survives replay, backtest, and later real outcomes.

The current baseline is not sufficient for that claim. `feat-037` is still pending, strict same-day decision-ready holding coverage was 0/3 in the latest audit, only six signals have matured at the one-session horizon, and no five-session or twenty-session sample has matured. Win rate alone would also be an unsafe optimization target because it can hide poor payoff asymmetry, drawdown, regime concentration, look-ahead bias, or overfitting.

## Decision

Keep InsightRadar local-first and defer cloud deployment, production Docker work, and platform migration until the Core decision loop has credible reliability and outcome evidence.

- Continue from the canonical local Windows checkout at `D:\work\InsightRadar`.
- Finish the workspace closeout prerequisite and `feat-037` before adding capabilities or portability work.
- After the reliability baseline, prioritize outcome maturation, replay/backtest quality, benchmark-relative attribution, and calibration over new clients, infrastructure, or deployment reach.
- Treat WSL, Docker, macOS ARM, and cloud as deferred delivery options, not the active roadmap. Revisit them only when portability materially improves Core validation or when the value gates below pass.
- Keep Iwencai available for manual evaluation under ADR-0005, but do not let provider migration distract from the local Core evidence loop.
- Preserve conditional guidance and explicit uncertainty. The product must not claim guaranteed returns or stable compounding from immature or in-sample evidence.

## Value Gates

Before prioritizing cloud or broad product delivery, require reviewable evidence for:

1. Reliable fresh-data and decision-ready holding coverage across normal trading days, with provider failures and fallbacks measured.
2. Sufficient matured samples at the stated one-, five-, and twenty-session horizons; every result must display sample size.
3. Benchmark-relative return and expectancy after realistic transaction-cost assumptions, not win rate alone.
4. Drawdown, MFE/MAE, payoff ratio, and loss-tail behavior that are compatible with the intended risk budget.
5. Stability across market regimes, holdings, sectors, and time splits rather than performance concentrated in one period.
6. Replay/backtest controls for point-in-time inputs, look-ahead bias, survivor bias, data revisions, and out-of-sample evaluation.
7. A documented path from historical evidence to paper/live shadow evidence before any claim that the system supports durable compounding.

These gates are product-learning requirements, not promises of future investment performance.

## Consequences

- Near-term engineering cost stays focused on the decision loop rather than infrastructure that would amplify fixed and operating cost.
- Windows and PowerShell friction is accepted temporarily because the current data path is proven there; portability remains a later optimization.
- Backtest hit rate remains visible but cannot become the sole promotion metric or a reason to loosen validation gates.
- New features, new clients, automated execution, Docker productionization, and cloud deployment remain parked until an explicit evidence review changes the priority.

## Revisit Trigger

Revisit this decision after `feat-037` passes and the outcome ledger contains enough mature, benchmark-relative evidence to evaluate the Value Gates. Any move to cloud production or platform migration requires a new priority decision with estimated operating cost, failure boundaries, and a rollback plan.
