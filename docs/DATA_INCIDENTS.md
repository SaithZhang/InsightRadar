# Data Incident Loop

This is the proportional local workflow for reproducible data defects. It does
not change the four-route product contract or authorize trading.

## Task Size

| Class | Boundary | Required verification and records |
|---|---|---|
| S | One local behavior, no data contract, product state, or module-boundary change | Add one focused regression and run only the targeted test. Do not refresh architecture, `feature_list.json`, `progress.md`, `session-handoff.md`, or `CURRENT_STATE.md`. |
| M | One vertical data path or an internal adapter/contract change, without adding a product module or route | Run the offline reproduction, adjacent module tests, focused static checks, and `compileall`. Add a short incident/progress record only when it improves restartability. Do not regenerate architecture or full handoff/state files. |
| L | Product behavior/state, first-level route, provider/workflow topology, separately deployed boundary, release, or recurring automation changes | Use the full Harness loop, exact feature state, relevant real workflow, full regression proportionate to risk, architecture regeneration/validation when topology changed, and handoff/current-state updates when their source-of-truth facts changed. |

Escalate by the boundary actually crossed, not by the number of files touched.
Only a product-state or topological module-boundary change triggers the full
governance-material refresh.

## DI-001: AmazingData Daily Price Basis

- Classification: M. It formalizes the existing AmazingData adapter boundary
  for the after-close holding path; it does not add a provider, workflow, route,
  deployment, or product capability.
- Symptom: an unadjusted daily series contains a corporate-action-sized close
  discontinuity. Without a declared price basis, downstream rules can only
  guess whether the series is safe for moving averages and technical levels.
- Fixture:
  `tests/fixtures/amazingdata_daily_unadjusted_split.json` is synthetic and
  redacted. It preserves the provider's dict/DataFrame columns and a load-bearing
  price discontinuity, with no account, credential, holding, or real symbol.
- Contract: `ProviderResult[T]` carries provider, schema version, source/fetch
  time, trade date, status, gaps/errors, price basis, and canonical data.
- Invariants: timestamps are sorted and deduplicated; OHLC is numeric, positive,
  and internally valid; the latest trade date is checked against the requested
  date; an unadjusted close discontinuity above 35% is quarantined.
- Fail-closed behavior: quarantined series may explain the data gap but cannot
  supply moving averages, support, resistance, volatility, or position actions.

Offline reproduction and verification command (no credentials or network):

```powershell
.venv\Scripts\python.exe -m unittest tests.test_daily_kline_contract -v
```
