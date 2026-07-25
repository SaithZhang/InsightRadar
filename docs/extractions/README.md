# InsightRadar Extraction and Focus Plan

## Expansion Freeze

InsightRadar is temporarily feature-frozen outside the A-share core. The next product work must improve reliability, relevance, or calibration of the existing portfolio decision loop; it must not add a new market, client, model family, or automation surface.

## Core That Stays

- Portfolio holdings and thesis memory.
- `after-close` conditional actions and data-gap disclosure.
- A-share `market-pulse` and `market-levels` evidence.
- Filing, research, and industry evidence that maps to current holdings.
- Signal outcomes, benchmark-relative calibration, and product health governance.

## Extraction Queue

| Capability | Decision | Timing | Reason |
|---|---|---|---|
| Windows discipline reminder | Extracted as standalone personal app | Complete on 2026-07-14 at `D:\work\reminder` | Independent executable, config, scheduled task, release lifecycle, and no core runtime dependency |
| Crypto/RWA monitor | Freeze as optional extension | Revisit only if it becomes an independently used product | It is outside the A-share north star and currently has no reason to impose another repository lifecycle |
| X/Twitter collectors and influencer evidence | Freeze; keep behind an adapter boundary | Revisit after core event-to-holding mapping is stable | Collection is optional and should not be confused with the evidence/decision domain |
| Factor lab/pipeline | Keep in repo but park new work | Revisit after core reliability baseline and stable research payload contract | PIT exposure work is incomplete and the lab still shares data, universe, and report contracts with the core |

## Two-Phase Reminder Extraction

1. `feat-036` packaged source, config, docs, harness, hashes, cutover state, and rollback into a verified extraction bundle.
2. Standalone `dr-002` migrated the canonical repository to `D:\work\reminder`, published the executable, moved the Windows logon task, and verified the visible controls, speech, and restart cycle.
3. After explicit user confirmation, the C-drive intermediate copy and the original source/config/scripts/docs/export artifacts and satellite node were removed from InsightRadar.

The standalone project now owns runtime state and rollback. Historical extraction evidence remains in the feature/progress/ADR records rather than as duplicate source or generated bundles.

## Criteria for Any Future Extraction

Extract only when the capability has at least one of these: independent release/rollback lifecycle, separate security boundary, independent scaling/availability, runtime/dependency conflict, or a stable tested producer/consumer contract. File count alone is not a reason.
