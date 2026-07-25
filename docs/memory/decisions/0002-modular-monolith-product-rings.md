# ADR-0002: Modular Monolith with Product Rings

- Status: accepted
- Date: 2026-07-14

## Context

InsightRadar now includes portfolio decisions, research ingestion, market radar, factor experiments, a native Windows reminder, crypto monitoring, and governance tools. Premature repository or service splitting would add contracts and operations before the product loop is stable, while leaving everything undifferentiated risks roadmap sprawl.

## Decision

Keep one repository and a modular monolith, but classify capabilities as Core, Lab, Satellite, Extension, or Governance in `docs/product-charter.md`.

- Core owns the A-share Observe-Explain-Decide-Verify loop.
- Lab output is diagnostic until explicit promotion gates pass.
- Satellites may deploy independently through stable payload/config contracts.
- Extensions cannot make the A-share core unavailable or set its roadmap implicitly.
- Governance is required for continuity but is not a user-facing signal source.

Extract a repository or service only for independent lifecycle, security, scaling, runtime-conflict, or stable-contract reasons.

## Alternatives Rejected

- Immediate microservices: operational cost without demonstrated scaling or ownership need.
- One undifferentiated feature bucket: allows optional experiments to crowd out the core product promise.
- Separate factor or crypto products now: neither has a proven independent user loop in this checkout.

## Consequences

- The Windows reminder was later extracted under ADR-0003 after its independent lifecycle and rollback boundary were verified; Satellite remains a valid category even when no current in-repository node uses it.
- Factor workflows are treated as a lab and cannot feed production decisions without a champion.
- Crypto/X capabilities remain optional extensions.
- Future boundary changes require an ADR and topology/current-state refresh.
