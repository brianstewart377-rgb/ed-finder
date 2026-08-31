# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 14

Date: 2026-08-31
Scope: research only. No production writes, V3 database writes, scoring-code changes, or migrations.

This is a continuation of checkpoint 13, completing the next Raven slot call-path item rather than stopping after locating the formula.

## Raven slot predictor call path is now proven

PR #25 (`Predict surface slots when they are unknown`) changed `src/views/SystemView2/BodyCard.tsx` to import `predictSurfaceSlots()` and use it only when the stored surface-slot value is unknown/negative.

Current `main` still contains the same logic:

```ts
const bodySlots = sysView.state.sysMap.slots[bod.num] ?? [-1, -1];
...
max={bodySlots[1] < 0 ? predictSurfaceSlots(bod) : bodySlots[1]}
isPredicted={bodySlots[1] < 0}
```

Source:
https://github.com/njthomson/RavenColonialWeb/blob/main/src/views/SystemView2/BodyCard.tsx

So `src/slot-prediction.ts` is specifically a **fallback for unknown surface slots**, not a replacement for Raven's stored/observed slot values.

This resolves an important ambiguity from checkpoint 13.

## Stored slot values arrive in Raven's loaded system object

`SystemView2.loadData()` fetches the system through Raven's `api.systemV2.getSys(...)`, builds the system model, and `useLoadedData()` sets:

```ts
bodySlots: newSys.slots,
originalBodySlots: JSON.stringify(newSys.slots),
```

The body card reads `sysMap.slots`, which is built from that loaded `Sys` object. In other words the UI's preference order is effectively:

1. use Raven system's stored slot count when it exists;
2. if surface slots are unknown (`< 0`), calculate the local `predictSurfaceSlots()` fallback;
3. visibly mark the fallback as predicted.

Sources:
https://github.com/njthomson/RavenColonialWeb/blob/main/src/views/SystemView2/SystemView2.tsx
https://github.com/njthomson/RavenColonialWeb/blob/main/src/views/SystemView2/BodyCard.tsx

## Consequence for our Raven-vs-workbook experiment

A casual Raven UI lookup can accidentally compare our workbook prediction with a **stored observed/manual Raven value**, not Raven's formula. That would be a category error.

The threshold corpus therefore needs three separate columns:

- `raven_stored_slots`;
- `raven_fallback_predicted_slots` (computed from `slot-prediction.ts`);
- `workbook_predicted_slots`.

And ideally a fourth independent current observation:

- `architect_observed_slots_current_patch`.

Without this split, a statement such as "Raven agrees with the workbook" is ambiguous and cannot be used as algorithm validation.

## Evidence/confidence distinction for CRE

Raven itself already encodes a useful provenance distinction in UI state: stored slot count vs locally predicted count (`isPredicted`). ED-Finder/CRE should preserve at least the same semantic split and go further by storing source/date/patch state.

Suggested conceptual states for future design, not an implementation request in this research pass:

- `observed_current`;
- `observed_historical`;
- `reported_by_tool`;
- `predicted_formula`;
- `manual_override`;
- `unknown`.

A numeric `slot_count` without this state is insufficient for forensic validation.

## Adversarial challenge

This call-path proof does **not** prove how every Raven stored value was obtained. The `newSys.slots` object may include values imported from user/System Map/Architect observations, manual edits, older Raven imports, or other server-side sources. That provenance still needs tracing if Raven stored values are to be used as gold labels.

Therefore:

- Raven fallback formula: provenance is now clear (PR #25/community thread, November 2025);
- Raven stored value: provenance remains per-record/unknown unless separately documented;
- Raven UI output: must not be treated as one homogeneous evidence type.

**Falsification test:** trace a freshly imported never-edited system from API response through `newSys.slots`, then compare with a manual Raven slot edit and a system whose ground slot remains unknown. Confirm the three states survive reload distinctly.

## Next queue — continue

1. Recover/materialize the original slot-analysis workbook and extract its exact high-accuracy formula.
2. Build the discriminating Raven-fallback vs workbook vs current-Architect threshold corpus.
3. Trace the source/provenance of Raven `newSys.slots` stored values and determine whether source/date metadata exists server-side.
4. Continue post-Operations terraformable-Agriculture controlled fixture work.
5. Quantify unknown-resource-level -> Pristine bias in Raven economies.
6. Continue commodity top-two/rank-three golden markets and EDDN archive history work.
7. Continue post-July-2026 orbital-slot corpus.
8. Run the read-only V3 sensitivity analysis for signal-count/fake-slot replacement.
