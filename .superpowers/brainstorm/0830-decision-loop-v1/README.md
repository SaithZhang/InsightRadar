# PROTOTYPE — 08:30 Decision Loop

Throwaway UI prototype. Do not promote this file directly into production.

Question:

> Which information structure lets the user understand and explicitly accept,
> dispute, reject, or defer zero to three morning plans in under three minutes,
> then move coherently through holdings, stock lookup, and outcome review?

Three structurally different variants share one route and fixed sanitized data:

- `A`: focus stack — one dominant decision plus compact secondary decisions.
- `B`: decision inbox — queue on the left, selected decision detail on the right.
- `C`: morning checklist — scan-first rows with inline decision controls.

All variants now share a compact market-constraint layer:

- one action-constraining conclusion before the decision count;
- six global temperature tiles with explicit freshness;
- direct indexes as the primary judgment and ETF baskets as confirmation;
- a detail drawer separating trend, breadth, sentiment, crowding, and liquidity;
- stale domestic QDII proxies are labelled and never presented as live overseas data.
- a holdings-relevant AI-hardware theme constraint links to a secondary detail
  route instead of expanding the Today page.

The selected `A` shell also contains three first-level task routes and one
secondary detail route:

- `holdings`: actual positions, readiness gaps, search, add, and import preview;
  the 5,299-stock market directory is explicitly separate from actual holdings.
- `lookup`: code search, K-line/MA20/MA60, MACD/divergence/Fibonacci context,
  a Shanghai Composite risk gate, board-specific benchmark overlays, and one
  rule-based scenario strategy.
- `review`: separate strategy quality from execution quality, retain the
  plan-trigger-execution ledger, expose T+1/T+5/T+20 evaluation windows, and
  show honest point-in-time backtest readiness instead of invented results.
- `theme`: secondary AI-hardware temperature detail with nine ETF proxies,
  a transparent cross-sectional median, 35/80 floor/ceiling lines, and an
  explicit rule that low temperature is observation rather than buy authority.

Today decisions are in-memory prototype states only. An accepted plan activates
the V2 alert handoff preview; a disputed, rejected, deferred, or unhandled plan
does not activate new opportunity alerts. Batch accept changes only untouched
plans and never overwrites an explicit response.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m http.server 8890 --bind 127.0.0.1 --directory .superpowers\brainstorm\0830-decision-loop-v1
```

Open:

```text
http://127.0.0.1:8890/today-prototype.html?variant=A&scenario=3
```

Use the left/mobile navigation to switch task routes. The URL keeps a `route`
parameter (`today`, `holdings`, `lookup`, `review`, or secondary `theme`). On the Today route, use
the floating prototype bar or the left/right arrow keys to switch variants and
zero/one/three-decision scenarios.

Evaluation:

1. Can the user say what requires action within ten seconds?
2. Can all visible plans receive an explicit response within three minutes?
3. Are the trigger, action, horizon, and invalidation understandable without
   opening evidence?
4. Does the first screen stay calm in the three-decision case?
5. Which details belong inline, in a drawer, or on a separate stock route?
6. Does the market layer constrain decisions without becoming an indicator wall?
7. Does each non-Today route have one obvious job and preserve the same decision
   vocabulary?
8. Does a plan dispute remain visible without silently activating or replacing
   the accepted alert baseline?
9. Does the theme-temperature page communicate floor/ceiling context without
   turning `<35` into an automatic “golden pit” trade?
