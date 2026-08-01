# Today Workbench Design QA

Prior design-QA history is preserved at `docs/qa/2026-07-30-design-qa-history.md`.

## Comparison target

- Source visual truth: `D:\work\InsightRadar\docs\product-prototypes\postclose-2026-07-31\screenshot-1440x900.png`
- Rendered implementation: `http://127.0.0.1:8766/#today`
- Final implementation screenshot: `D:\work\InsightRadar\reports\20260801-191128-today-workbench-final2-1440x900.png`
- State: weekend review of the latest completed trading session, real local structured data, blocked rule examples, no AI, no trade authority
- CSS viewport: 1440 x 900, device scale factor 1
- Pixel dimensions: source 1440 x 900; browser capture 1425 x 891 because the in-app browser excludes its scrollbar/reserved edge from the PNG
- Density normalization: none required. Both captures are 1x; the 15 x 9 capture-edge difference was treated as browser chrome rather than product layout.

## Full-view comparison evidence

The source and final implementation captures were emitted together at the same desktop state and inspected as one comparison input. The implementation preserves the source's blue-black high-density finance surface, three equal-priority columns, red/amber/blue semantic states, bordered cards, restrained radii, large account P&L, compact labels, and progressive evidence disclosure.

The existing InsightRadar sidebar and local refresh controls remain visible by design. They reduce the three-column content width compared with the standalone prototype, but preserve the product's established four-route navigation and runtime controls. Real blocked data and real rule counts replace the prototype's fixed examples; this is a truth-boundary difference, not design drift.

## Focused-region evidence

A separate crop was not needed: both full captures were inspected at original resolution and the dense card copy, numeric hierarchy, buttons, badges, borders, and disclosure affordances remained legible. Browser DOM checks additionally verified the exact route labels, active panel, details controls, decision controls, and parameterized holding link.

## Required fidelity surfaces

- Fonts and typography: existing project font stack retained; heading, numeric, label, and body weights reproduce the prototype hierarchy without adding a new typeface. No observed clipping or unintended truncation.
- Spacing and layout rhythm: desktop uses three columns; 1024 x 768 and 390 x 844 collapse to one column with no horizontal overflow. Card spacing and section rhythm remain consistent with the source and existing shell.
- Colors and tokens: reused the project's background, line, danger, warning, blue, muted, and text variables. No new brand palette or decorative gradient was introduced.
- Image and asset fidelity: the source has no content imagery requiring replacement. The existing text/IR brand treatment remains unchanged; there are no placeholder images, emoji icons, or synthetic charts.
- Copy and content: headings follow 发生了什么 / 最需要关注 / 我需要决定什么. Real data, explicit unknowns, blocked states, evidence, counter-evidence, and the honest empty-opportunity state replace prototype-only claims.

## Interaction and accessibility evidence

- Native `details/summary` disclosure expanded successfully.
- Position attention opened Portfolio with `symbol` and `plan_id`; the holdings table filtered to the matching row.
- Portfolio, Lookup, Review, and Today routes all activated without a fifth route.
- Desktop, tablet, and mobile had zero horizontal overflow; the four mobile route buttons were visible.
- Page console warning/error log was empty.
- Response controls expose live regions and explicit status text. Browser QA did not mutate the real local response ledger; persistence, disabled state, blocked acceptance rejection, and stale-version modification behavior are covered by the passing response/state tests.

## Comparison history

### Iteration 1

- Finding: [P2] A fresh `#today` load could allow the hash to target the route panel and restore an offset scroll position, hiding the top header.
- Evidence: `D:\work\InsightRadar\reports\20260801-191128-today-workbench-1440x900.png`; observed `scrollY=108.67`.
- Fix: renamed route-panel DOM ids to `route-today`, `route-portfolio`, `route-lookup`, and `route-review` while preserving public hash route ids.

### Iteration 2

- Post-fix evidence: `D:\work\InsightRadar\reports\20260801-191128-today-workbench-final2-1440x900.png`; fresh-tab `scrollY=0`, top bar visible, active route `today`, and no horizontal overflow.
- Responsive evidence: `D:\work\InsightRadar\reports\20260801-191128-today-workbench-1024x768.png` and `D:\work\InsightRadar\reports\20260801-191128-today-workbench-390x844.png`.
- Remaining P0/P1/P2 findings: none.

## Follow-up polish

- P3: the current local refresh interruption toast overlaps the lower-right card edge while visible. This is a transient existing runtime notification and does not block the core task.

final result: passed
