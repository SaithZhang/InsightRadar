# InsightRadar Product Baseline

Status: **Frozen baseline**

Baseline date: **2026-07-25**

Runtime version: **InsightRadar V3.0 Pilot — Scope Frozen**

## Product Definition

InsightRadar is an independent AI risk officer for individual investors and capital providers. It continuously filters market information; separates facts, inferences, rumors, sentiment, and unknowns; combines real portfolio state, account drawdown, industry fundamentals, market risk, and verifiable action evidence; and produces traceable, reviewable risk levels and conditional action guidance at material risk or opportunity points.

Short definition:

> InsightRadar is not designed to help users know more. It is designed to identify the small number of facts that may justify changing a position.

The current implementation is local-first, single-user, A-share focused, and human-confirmed. It never executes a trade.

## Primary Users

- A self-directed investor who needs portfolio-first risk guidance rather than another information feed.
- A capital provider who needs decisions, evidence, uncertainty, and outcomes to remain auditable.
- A researcher or operator who must distinguish product capability from prototype, diagnostic, and missing data.

## Non-Negotiable Principles

1. V3 is the working baseline and must not be redesigned from scratch.
2. V3.1 may only make incremental changes after the frozen pilot review.
3. Preserve the four first-level tasks: `今日计划`, `组合风险`, `标的研究`, and `复盘账本`.
4. Do not add a fifth first-level menu. `今日计划` may later be renamed or widened to `风险与计划` only as an approved V3.1 delta.
5. Portfolio risk is the product center. Security research is an evidence and explanation layer.
6. Risk views prioritize peak drawdown, risk actions, underlying factor exposure, and re-entry conditions.
7. Every material claim must be classified as `fact`, `inference`, `rumor`, `sentiment`, or `unknown`.
8. Counter-evidence, source provenance, as-of time, freshness, and missing fields remain visible.
9. Risk signals must enter a point-in-time ledger that is not rewritten after the outcome is known.
10. Review must record false positives, missed upside, premature exits, and re-entry—not only successful warnings.
11. The system never trades automatically. Every position action requires explicit human confirmation.
12. The formal product must not depend on named-person copy trading or influencer identity.
13. Action evidence should come from verifiable account execution, ETF or margin data, filings, buybacks or reductions, orders, and industry data.
14. Simulated or synthetic data must be labelled and must never be presented as a live product capability.
15. Commercialization, public stock-picking, and automated execution are outside the near-term scope.

## Evidence Classification

| Class | Meaning | Product treatment |
|---|---|---|
| `fact` | Source-linked observation with a known as-of time | May enter deterministic rules when freshness and coverage pass |
| `inference` | Reproducible interpretation derived from facts | Must expose assumptions, invalidation, and counter-evidence |
| `rumor` | Unverified claim or secondary retelling | Discovery only; cannot authorize a position action |
| `sentiment` | Opinion, narrative, or crowd behavior | Diagnostic only until independently calibrated |
| `unknown` | Missing, stale, blocked, conflicting, or unavailable state | Remains visible; never converted to zero or a confident conclusion |

## Current Product Loop

`Observe -> Explain -> Decide -> Verify`

- **Observe:** local portfolio data, A-share structure, market levels, filings, research, and risk evidence.
- **Explain:** relevance, provenance, freshness, counter-evidence, and explicit gaps.
- **Decide:** conditional plans with triggers, invalidation, and risk constraints.
- **Verify:** versioned plan responses and T+1/T+5/T+20 outcome maturation.

The four task routes are the user-facing expression of this loop. The older internal module registry—Portfolio Intelligence, Research Intelligence, Market Radar, and Product Ops—is an engineering classification, not a second navigation system.

## Authority Boundary

- Rules may calculate deterministic state from declared inputs.
- AI may summarize or explain non-structured evidence, but cannot overwrite rule output or manufacture missing data.
- Users accept, dispute, reject, defer, or acknowledge blocked plans.
- Only a user can execute a trade outside InsightRadar.

## Sources of Truth

- Frozen runtime and routes: `stock_assist/after_close_workbench_html.py`
- Workspace and immutable version semantics: `stock_assist/decision_workspace.py`
- Loopback service: `stock_assist/portfolio_import_server.py`
- Canonical after-close payload: `stock_assist/workflows/after_close.py`
- Upstream plan synthesis: `stock_assist/unified_decision.py`
- Product rings and commands: `stock_assist/product.py`
- Durable freeze decision: `docs/memory/decisions/0010-v3-pilot-scope-frozen.md`
