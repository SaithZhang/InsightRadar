# ADR-0009: Make Personal Investment Decision Intelligence the Product North Star

- Status: accepted
- Date: 2026-07-19

## Context

InsightRadar already used the `Observe -> Explain -> Decide -> Verify` loop and prioritized current holdings. The user clarified that the durable product should also aggregate material policy, macro, international, filing, fast-news, industry, and capital-flow evidence; provide investment guidance and key alerts; and offer a small candidate set when no holdings are supplied.

The expansion creates a product risk: a multi-agent system can generate features and content faster than it can prove usefulness. A time-of-day report definition would also confuse a delivery format with the durable product mission.

Public product review found complementary patterns rather than one product to clone. Meet Kevin demonstrates a concise Alpha Report habit; Klarion emphasizes portfolio-relevant risk explanations; AlphaSense emphasizes evidence aggregation and monitoring agents; Koyfin and TradingView demonstrate explicit alerts and replayable triggers.

## Decision

Adopt **personal A-share investment decision intelligence** as the durable North Star.

- Turn fragmented portfolio and market evidence into relevant, auditable, conditional guidance and key alerts.
- Keep approved holdings as the primary relevance anchor.
- When holdings are absent or sparse, allow a controlled pool of zero to five observation candidates with transparent rationale, trigger, invalidation, horizon, and risk. Never fill a quota.
- Treat `Alpha Report` and any scheduled or event-driven variants as delivery surfaces, not as the product mission.
- Treat fast news as discovery evidence. Critical claims require primary-source confirmation and an explicit new-versus-cumulative assessment before they affect guidance.
- Keep missing/stale data, uncertainty, conflicts, and calibration state visible. Do not execute trades.
- Measure decision-ready holding coverage, alert usefulness, candidate/outcome quality, source reliability, and mature benchmark-relative results rather than feature, report, candidate, or agent counts.
- Operate multi-agent work through one lead and bounded temporary roles. Agents manage an evidence-backed problem backlog; one product experiment may be active and at most two may be queued.

The approved detailed design is `docs/superpowers/specs/2026-07-19-personal-investment-decision-intelligence-design.md`.

## Consequences

- Product work that does not improve information relevance, decision readiness, key-alert quality, or outcome calibration stays outside Core.
- Candidate discovery is a fallback decision mode, not a generic screener or recommendation feed.
- Time-of-day report variants may evolve without changing the North Star.
- Meet Kevin and Klarion join the maintained competitor benchmark, but no competitor feature is copied without one verifiable InsightRadar behavior and an outcome/kill criterion.
- The current modular-monolith rings, no-trade boundary, local-first value gate, and active implementation feature remain unchanged until a separately reviewed implementation plan reprioritizes them.
