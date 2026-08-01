# InsightRadar 08:30 Action Brief Design QA

## Comparison Target

- Source visual truth: `.superpowers/brainstorm/0830-decision-loop-v1/selected-action-brief-blue-red.png`
- Implementation: `.superpowers/brainstorm/0830-decision-loop-v1/today-prototype.html?route=today&variant=A&scenario=3`
- Implementation screenshot: `.superpowers/brainstorm/0830-decision-loop-v1/audit-2026-07-24/06-today-blue-red.png`
- Full-view comparison: `.superpowers/brainstorm/0830-decision-loop-v1/audit-2026-07-24/12-design-qa-side-by-side.png`
- Focused comparison: `.superpowers/brainstorm/0830-decision-loop-v1/audit-2026-07-24/13-design-qa-focused.png`
- Baseline comparison state: Today route, variant A, three decisions, none confirmed
- CSS viewport: 1440 × 1024, device pixel ratio 1
- Source pixels: 1486 × 1059
- Implementation pixels: 1425 × 1013; the in-app browser capture excludes its scrollbar area
- Density normalization: both full images were rendered with `object-fit: contain` inside equal comparison frames; no source or implementation pixels were stretched. The focused comparison rendered both images at equal container width and clipped only below the primary decision region.

## Findings

- No actionable P0, P1, or P2 mismatch remains.
- The implementation preserves the selected blue-black surface system, warm-white hierarchy, restrained vermilion priority rail, amber waiting state, cool-blue freshness state, compact two-driver market constraint, one dominant decision, two compact decisions, and warm-white confirmation actions.
- The implementation intentionally keeps `UNTIL` visible beside `IF`, `THEN`, and `INVALID`, although the concept image omitted it from the primary rule row. This is required by the approved strategy contract and does not change the selected hierarchy.
- The concept's dashed right-side evidence-rail hint is implemented as working `查看全部市场`, `查看依据`, and drawer interactions instead of a permanently reserved empty rail. This preserves evidence-on-demand while using the available width for readable rules.
- The prototype-only variant/scenario control is parked inside the desktop sidebar and hidden below 820 px. It no longer obscures the primary confirmation footer.

## Required Fidelity Surfaces

- Fonts and typography: passed. The implementation uses the existing Inter / Segoe UI / Microsoft YaHei stack, preserves the source's large warm-white headings, compact uppercase metadata, tabular decision numbers, and readable 11–14 px supporting copy. No important label is clipped at the checked desktop or mobile widths.
- Spacing and layout rhythm: passed. The source's compact market band, decisive section break, dominant first decision, compact secondary rows, and final confirmation strip are reproduced. Desktop and 390 px layouts have no horizontal overflow.
- Colors and visual tokens: passed. Green-dominant surfaces were removed. Blue-black owns the brand surface; vermilion is restricted to highest priority, A-share positive movement, and invalidation; amber marks waiting or insufficient evidence; cool blue marks freshness, neutral confirmation, and A-share decline; warm white owns primary actions.
- Image quality and asset fidelity: passed. The selected reference contains no photographic or illustrative raster assets requiring recreation. The brand mark and chart remain code-native interface elements from the existing prototype; no source image asset was replaced with a placeholder.
- Copy and content: passed. Core Chinese copy, the three-plan limit, IF/THEN/UNTIL/INVALID contract, data freshness, evidence access, and no-trade boundary remain explicit.
- Interaction states: passed. Confirm-all, individual confirmation, all-market evidence drawer, holdings filtering, stock-code analysis, and review-detail drawer were exercised in the in-app browser.
- Accessibility: passed for this prototype gate. Semantic buttons, labelled inputs, visible focus styling, text-plus-color status labels, and high-contrast primary actions remain present. Automated screen-reader and text-zoom testing were not run.
- Responsiveness: passed. At CSS viewport 390 × 844, all four routes reported document scroll width 375 px with no horizontal overflow; the Today market drivers reflow to two columns and the prototype control is hidden so it cannot cover the decision card.

## Comparison History

1. Iteration 1 evidence: `05-today-blue-red-iteration1.png`
   - [P2] The fixed prototype switcher covered part of the primary confirmation footer at desktop and obscured the first decision at mobile.
   - Fix: moved the desktop switcher into the sidebar, hid it below 820 px, and compressed the mobile market constraint into a two-column driver grid.
2. Post-fix evidence: `06-today-blue-red.png` and `mobile-10-today-blue-red-final.png`
   - The primary footer is fully visible at desktop.
   - The mobile decision heading and first card enter the initial scroll sequence without an overlapping prototype control.
   - No actionable P0/P1/P2 finding remains.

## Verification Evidence

- Desktop screenshots: `06-today-blue-red.png`, `07-holdings-blue-red.png`, `08-lookup-blue-red.png`, `09-review-blue-red.png`
- Mobile screenshots: `mobile-10-today-blue-red-final.png` plus the other `mobile-*blue-red.png` route captures
- Desktop horizontal overflow: none on all four routes
- Mobile horizontal overflow: none on all four routes
- Browser diagnostic logs: empty
- Primary interactions tested: confirm-all, evidence drawer, holdings search/filter, stock lookup update, review detail drawer

## Follow-up Polish

- [P3] Replace the prototype glyph navigation with one coherent production icon family when this throwaway prototype becomes a maintained client.
- [P3] Consider a user-selectable light theme only after the dark default completes the ten-session pilot.

final result: passed

# 2026-07-30 P0 Blocked-State Repair

## Source and Runtime Evidence

- Today source: private local prototype reference, retained outside the public repository.
- Today runtime and side-by-side comparison were captured privately at 1280 x 720.
- Review source: private local prototype reference, retained outside the public repository.
- Review runtime and side-by-side comparison were captured privately at 1440 x 1024.
- Mobile runtime was captured privately from the 390 x 844 CSS viewport.
- Runtime artifact: private local report triplet generated from the current portfolio.

## Findings and Fixes

1. [P0] A blocked plan disappeared from Today after the user acknowledged the blocker, producing a false `0`.
   - Fixed by separating pending responses from unresolved blocked attention. Today now retains every blocked plan, labels the runtime `blocked_waiting`, disables execution-like controls, and makes `继续等待` the compliant primary branch.
2. [P0] Global reliability messages were copied onto every plan, so an unrelated local holding gap could block the wrong plan.
   - Fixed by mapping structured blockers to the matching holding while preserving true portfolio-wide risk reconciliation constraints.
3. [P0] Nested source timestamps were discarded, which could turn stale evidence into a false missing state or make report-generation time look like market time.
   - Fixed by carrying authoritative `source_time` separately from `generated_at`; the data drawer now shows source time, repair action, owner, and next check.
4. [P0] A historical plan threshold used an incompatible price basis and remained eligible for review and outcome aggregation.
   - Fixed by quarantining implausible fresh-history/current-price basis mismatches. Review visibly marks the affected version `口径异常，已隔离` and excludes the bad signal from tracked, matured, hit-rate, and average-effect aggregates.
5. [P1] Review mode and horizon controls appeared interactive despite the decision-value series being unavailable.
   - Fixed by rendering all seven controls disabled with explicit unavailable labels.
6. [P2] The first repaired blocked card was too tall, and the narrow stage rail exposed a browser scrollbar.
   - Fixed by compressing acknowledged-version detail into one status note and hiding the mobile rail scrollbar while preserving horizontal navigation.

## Fidelity and Functional Gate

- Hierarchy: passed. The runtime preserves the reference's four-task shell, staged decision rail, dominant first action, causal chain, holding impact strip, evidence-on-demand, and review ledger.
- Truthfulness: passed. Synthetic executable actions and positive review curves were not copied. The real state remains `blocked`, `stale`, or `unknown`, with no automatic trade authority.
- Typography, spacing, colors, borders, and density: passed. The blue-black tokens, warm-white hierarchy, coral blocker rail, amber waiting state, and compact cards match the latest prototype language.
- Responsive layout: passed. Desktop and mobile document width has no horizontal overflow. The mobile bottom navigation works and the stage rail remains contained.
- Core interactions: passed. Four-route navigation, data-status open/close, Portfolio attention count, disabled Review controls, and mobile navigation were exercised against the final real artifact.
- Runtime diagnostics: passed. Browser warning/error log was empty.
- Automated verification: passed. Focused 42-test gate and full 260-test suite passed; compileall, project-memory validation, JSON validation, and `git diff --check` passed.
- Independent product audit: passed after one revise cycle. The reviewer first caught that a quarantined signal still affected outcome aggregates; the final implementation closes that gap and the reviewer returned PASS. Its non-blocking fail-closed test suggestion for an explicit quarantine without a reason was also added.
- Remaining P0/P1/P2 visual or interaction findings in the agreed repair scope: none.

final result: passed

# 2026-07-30 Risk-card Workbench Prototype Match

## Visual Truth and Runtime State

- Visual authority:
  - Today: private local prototype reference (1280x720).
  - Review: private local prototype reference (1487x1058), normalized to 1440x1024 for the comparison.
- Runtime authority: private local report triplet generated from the current portfolio and source-health state.
- Runtime state rendered in the comparison used a private portfolio; only the UI state categories and interaction results are documented publicly.
- The prototype's positive performance numbers and simulated decision-value curve were not copied. Missing account-path, drawdown, execution, and no-action-baseline evidence remains visibly `unknown` or `blocked`.

## Comparison Evidence

- Today desktop implementation and source/runtime comparison were captured privately at 1280 x 720.
- Review desktop implementation and source/runtime comparison were captured privately at 1440 x 1024.
- Today and Review mobile implementations were captured privately at 390 x 844.
- The raw runtime captures were 1921x1080, 2161x1536, and 586x1266 because Windows rendered the requested CSS viewports at 1.5x device scale. They were normalized to 1280x720, 1440x1024, and 390x844 before comparison.
- Focused crops were not needed: the complete action-command hierarchy fits in the Today desktop viewport, while the Review comparison contains the complete summary, mode controls, evidence legend, and blocked chart state at readable scale.

## Iteration History

1. Iteration 1
   - [P2] The primary Today card was too tall because all response options were exposed at once.
   - Fix: kept the authority-safe response prominent and moved the remaining responses into a collapsed secondary control.
2. Iteration 2
   - [P1] Evidence strength incorrectly summed T+1, T+5, and T+20 signal windows, overstating independent decision-value samples.
   - Fix: evidence strength now counts only matured T+20 decision episodes and renders `样本不足 0/20` for the current run.
   - [P2] Review repeated its title and exposed English status labels.
   - Fix: removed the duplicate heading and translated the visible runtime states.
3. Final comparison
   - No unresolved P0, P1, or P2 visual or interaction findings.
   - The five production contract stages replace the prototype's six simulated intraday replay stages because intraday monitoring is not implemented.
   - The blocked Review canvas intentionally replaces the prototype chart until continuous plan, account, point-in-time proxy, and no-action-baseline evidence exists.
   - Text labels retain the reference hierarchy without adding external icon assets to the self-contained report.

## Verification Evidence

- Desktop viewports: 1280x720 for Today and 1440x1024 for Review.
- Mobile viewport: 390x844 for Today and Review.
- Root horizontal overflow: none. The desktop stage rail remains fully visible; the narrow mobile stage rail is an intentionally contained horizontal scroller.
- Browser diagnostic logs: zero runtime errors in the final clean session.
- Primary interactions tested: all four frozen routes, market-data drawer open/close, Review mode switching, Review window switching, and mobile bottom navigation.
- Automated checks cover the single-action hierarchy, blocked/unknown Review contract, removal of prototype values, and matured T+20 evidence counting.

final result: passed

# InsightRadar V3 Strict Runtime Match

## Comparison Target

- Sole visual source: `%USERPROFILE%\Downloads\InsightRadar-V3-交付包\InsightRadar-V3-delivery\InsightRadar-重构原型-v3.html`.
- Source screenshots: `InsightRadar-v3-today.png`, `InsightRadar-v3-portfolio.png`, `InsightRadar-v3-research.png`, `InsightRadar-v3-review.png`, `InsightRadar-v3-data-drawer.png`, and `InsightRadar-v3-mobile.png` from the same delivery folder.
- Runtime implementation: `http://127.0.0.1:8765/`, generated from `reports/20260725-003439-after-close.json`.
- Final Today comparison: `tmp/v3-strict-match/final-compare-today-1440x900.jpg`.
- Cross-route comparison: `tmp/v3-strict-match/compare-all-desktop.jpg`.
- Corrected Portfolio comparison: `tmp/v3-strict-match/compare-portfolio.jpg`.
- Mobile viewport evidence: `tmp/v3-strict-match/implementation-mobile-390x844.jpg`.
- Desktop comparison viewport: 1440 x 900. Source and implementation occupy equal 1440 x 900 frames without crop or aspect-ratio distortion.
- Mobile viewport: 390 x 844. The browser's full-page capture is unreliable under viewport emulation, so the visible viewport, measured DOM geometry, and horizontal-overflow metrics are the acceptance evidence.

## Findings and Resolution

1. [P0] The earlier P0 runtime used a red/white shell and a different information hierarchy.
   - Resolved by replacing the shell with the V3 blue-black tokens, 228 px sidebar, 1340 px content stage, reference topbar, runtime strip, four-column market gate, theme line, dominant plan plus compact queue, and evidence-on-demand side rail.
2. [P0] Hash deep links initially let the browser scroll the active route under the topbar.
   - Resolved by consuming the initial hash, selecting the route, and removing the fragment without a page reload. `/#portfolio` still opens Portfolio, but the page starts at scroll position zero.
3. [P1] A filtered Portfolio state remained active during the first screenshot pass.
   - Resolved by clearing the visible filter, verifying all four real rows are visible, and replacing the comparison evidence.
4. [P1] The prototype contains fixed market values and a simulated technical chart that do not exist in the P0 runtime.
   - Intentionally not copied. The runtime renders current local market/data states and a labelled `技术图表尚未接入此 P0 页面` boundary instead of fake prices, scores, or chart lines.
5. [P2] The source uses the route id `lookup`, while the first runtime iteration used `research`.
   - Resolved by matching the source route id and navigation contract without changing the internal research-task data model.

## Fidelity and Functional Gate

- Visual system: passed. Palette, typography, radii, borders, shadows, spacing, responsive rules, and primary/secondary hierarchy match the supplied V3 HTML.
- Content truthfulness: passed. Four real positions, three changed plans, six explicit source-health rows, zero simulated rows, and all unknown/stale/missing/blocked states remain visible.
- Main routes: passed. Today, Portfolio, Lookup, and Review navigate without reload and update title/navigation state.
- Core interactions: passed. Plan evidence disclosure, data drawer open/close with focus restoration, portfolio filter, research-intent form, research tabs, and deep-link selection work.
- Runtime diagnostics: passed. The final freshly generated report exposes `data-runtime-error-count="0"` after load.
- Responsiveness: passed. Root horizontal overflow is zero at 1920 x 1080, 1440 x 900, 1366 x 768, and 390 x 844. Mobile sidebar is replaced by the four-task bottom navigation; wide tables remain inside controlled scrollers.
- Scope boundary: passed. P1 research orchestration/history center and P2 five-minute monitoring/notification delivery were not implemented or visually misrepresented.

final result: passed

## Approved Refinement Verification

- The owner-approved response model adds accept, dispute, reject, and defer
  without changing the selected action-brief hierarchy. A structured objection
  was saved in the browser, remained visibly disputed, and did not attach to
  the alert preview.
- Accepting a separate plan changed the V2 handoff to `已挂接 1 份接受计划`.
  The panel remains explicitly labelled as a design preview; no polling or
  notification runtime is claimed.
- Stock Lookup now shows the Shanghai Composite risk gate separately from the
  STAR/ChiNext/CSI primary benchmark. Review shows backtest readiness with
  `待跑` and `样本不足`, not invented returns.
- The new secondary AI-hardware route renders a canvas trend, nine ETF proxies,
  and 35/80 floor-ceiling lines. It states that the unified value is a prototype
  cross-sectional median and that low temperature is not buy authority.
- Fresh browser checks used 1280 px desktop and 390 × 844 mobile. Today,
  Holdings, Lookup, Review, and Theme all reported `scrollWidth <= innerWidth`;
  browser diagnostic logs were empty.

refinement result: passed

# InsightRadar V3 P0 Runtime Design QA

## Comparison Target

- Source visual truth: `%USERPROFILE%\Downloads\InsightRadar-V3-交付包.zip`, Today and mobile reference screenshots extracted for comparison.
- Implementation: `http://127.0.0.1:8765/#today`, generated from `reports/20260725-000005-after-close.json`.
- Desktop implementation screenshot: `tmp/v3-p0-qa/implementation-today-1440x900-final.png`.
- Desktop full-view comparison: `tmp/v3-p0-qa/compare-today-reference-vs-p0-final.png`.
- Mobile implementation screenshot: `tmp/v3-p0-qa/implementation-today-390x844-final-fresh.png`.
- Mobile full-view comparison: `tmp/v3-p0-qa/compare-mobile-reference-vs-p0-final.png`.
- Baseline state: real after-close stage, three changed plans, no plan accepted.
- Desktop CSS viewport: 1440 x 900. Source crop: 1440 x 900 from a 1440 x 1233 source. Browser capture: 1425 x 891, normalized into a 1440 x 900 comparison frame without changing aspect ratio.
- Mobile CSS viewport: 390 x 844. Source crop: 390 x 844 from a 390 x 3571 source. Browser capture: 375 x 812 at device pixel ratio 1.5, normalized into a 390 x 844 comparison frame without changing aspect ratio.

## Findings

- No actionable P0, P1, or P2 visual defect remains for the P0 acceptance surface.
- The runtime preserves the reference information hierarchy: navigation, decision chain, market gate, theme strip, one dominant plan, compact secondary plans, risk/evidence rail, portfolio risk, and evidence-on-demand.
- The red/white palette is intentional and follows the owner's explicit A-share color selection; it is the only material departure from the reference's blue-black palette.
- Research and Review intentionally remain truthful read-only P0 surfaces. They do not simulate the P1 research orchestrator, backtest ledger, or history center.
- The P2 monitor handoff is visibly blocked and labelled unimplemented; it is not a visual placeholder for a working service.

## Required Fidelity Surfaces

- Typography and hierarchy: passed. Plan priority, IF/THEN/UNTIL/INVALID clauses, data states, and primary response actions remain readable at all checked widths.
- Layout rhythm: passed. Root document horizontal overflow is absent at 1920x1080, 1440x900, 1366x768, and 390x844.
- Portfolio tables: passed. Desktop stays within the page; mobile overflow is isolated to a controlled table scroller rather than the document.
- Interaction states: passed. Route navigation, plan response actions, market evidence drawer, Escape close, backdrop close, and morning freshness restage work.
- Accessibility gate: passed for P0. Interactive controls have semantic elements, visible focus styling, text-plus-color states, and mobile response targets of at least 44 px. Automated screen-reader and 200% text-zoom testing were not run.
- Asset fidelity: passed. The source requires no photographic or illustrative assets; no fake image, inline SVG, emoji icon, or placeholder art was introduced.
- Data truthfulness: passed. The checked workspace uses real local artifacts, reports zero simulated sources, and exposes missing/stale/blocked inputs instead of filling them.

## Comparison History

1. Iteration 1
   - [P2] Rendering all three plans fully expanded made the Today route unnecessarily dense (`scrollHeight` 1621).
   - Fix: retained the first plan as the full decision surface and collapsed the remaining changed plans into compact rule summaries (`scrollHeight` 1349).
2. Iteration 2
   - [P2] Mobile plan-response controls measured about 37 px high.
   - Fix: raised the minimum interactive height to 44 px.
3. Functional QA
   - [P0] Morning recheck logged a console error because `event.currentTarget` was read after an awaited request.
   - Fix: captured the button before the await; the final clean browser session reports no console diagnostics.
4. Data-health QA
   - [P1] A source marked `current` without `source_time/as_of` could display an unhelpful generic gap.
   - Fix: the contract now marks it `missing` and explains that the declared current state lacks a source timestamp.
5. Runtime-state QA
   - [P1] A saved morning state could have overlaid a newer after-close report sharing the same effective market date.
   - Fix: runtime state must also match the immutable `source_generated_at`.

## Verification Evidence

- Viewports: 1920x1080, 1440x900, 1366x768, 390x844.
- Root horizontal overflow: none at all four viewports.
- Browser diagnostic logs: empty in the final clean session.
- Real/simulated status: six source-health rows, zero simulated.
- Primary interactions tested: accept/dispute/reject/defer controls, market drawer open/close, morning restage, Portfolio/Research/Review routing.
- Focused comparison was not separately required after the desktop and mobile full-view comparisons resolved every P0-P2 issue; the dominant decision region is visible in both full-view comparison inputs.

final result: passed

# Latest Acceptance Authority

The `InsightRadar V3 Strict Runtime Match` section supersedes the earlier
red/white P0 comparison. The supplied V3 HTML is the current visual authority;
the final runtime uses its blue-black system and truthful local data.

final result: passed

# Latest Repair Acceptance Authority

The `2026-07-30 P0 Blocked-State Repair` section is the latest acceptance
evidence. It preserves the V3 blue-black visual authority while replacing
prototype-only executable and performance states with the current truthful
blocked, stale, quarantined, and unknown runtime states.

final result: passed
