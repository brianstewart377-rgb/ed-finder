# CRE / EDRE Journal Observation Export — sanitization authority

This document is the committed arbitration source for the sanitized journal
observation export (`ed-finder-cre-journal-observation-export` v1.0.0). It is
the authority referenced by
`apps/api/src/edfinder_api/journal/sanitize.py`. If the sanitizer and this
document disagree, this document wins and the sanitizer must be corrected.

## A1-A14 allowlist mapping

`sanitize_observation` emits only the fields below. Any field not listed is
never copied into the output (fail-closed).

| ID | Output field | Source / rule |
|----|--------------|---------------|
| A1 | `observation_id` | `uuid5` of `event_type:canonical_key_json` |
| A2 | `observation_type` | journal `event_type` |
| A3 | `observed_week` | ISO-8601 week bucket of `event_timestamp` (never exact timestamp) |
| A4 | `source_event_sha256` | `source_record_hash` as lowercase hex |
| A5 | `evidence_quality` | always `OBSERVED_PERSONAL` |
| A6 | `system_id64` | decimal string from event key `SystemAddress` (omitted for `SellOrganicData`) |
| A7 | `system_name` | payload `SystemName` -> `StarSystem` -> `System` (omitted for `SellOrganicData`) |
| A8 | `body_id` | decimal string from event key `BodyID` (when present) |
| A9 | `body_name` | payload `BodyName`, else string form of payload `Body` (when present) |
| A10 | `body_environment` | normalized `Scan`/`FSSBodySignals`/`SAASignalsFound` facts (see unit conversions) |
| A11 | `signals` / `genuses` | projected signal/genus blocks (see below) |
| A12 | `codex_region` / `codex_entry_id` | `CodexEntry` only |
| A13 | `genus` / `species` / `variant` | `ScanOrganic` only |
| A14 | `sale` | `SellOrganicData` only (see below) |

Optional trailing fields: `game_version`, `game_build` when present in the
payload.

## Exported and excluded event types

Exported set:

```text
Scan, FSSBodySignals, SAASignalsFound, SAAScanComplete, CodexEntry,
ScanOrganic, SellOrganicData, FSSDiscoveryScan, FSSAllBodiesFound
```

Every other allowlisted journal event type is excluded (travel/identity/credit
events return `None`), including: `FSDJump`, `CarrierJump`, `Location`,
`Touchdown`, `Liftoff`, `ApproachBody`, `LeaveBody`, `Disembark`, `Embark`,
`Screenshot`, `Docked`, `Fileheader`, `LoadGame`, `Commander`, `Died`,
`Resurrect`, `SellExplorationData`, `MultiSellExplorationData`, `FSDTarget`,
`NavRoute`, `NavRouteClear`.

## Hard exclusions

Latitude/Longitude, credits (`Value`/`Bonus`/`TotalValue`), `MarketID`,
commander name/FID, and localised display names are never emitted, even when
present in the event key or payload.

## Arbitrated unit conversions

| Output | Journal source | Conversion |
|--------|----------------|------------|
| `radius_km` | `Radius` (metres) | `/ 1000`, rounded to 4 decimal places |
| `surface_gravity_g` | `SurfaceGravity` (m/s²) | `/ 9.80665`, rounded to 6 decimal places |

## Signals projection

`signals` entries are projected to `{ "Type": str, "Count": int }` only.
Journal extras such as `Type_Localised` are dropped. `genuses` is a separate
optional string array of canonical genus tokens from `SAASignalsFound.Genuses`.
JSON `null` values are never emitted.

## Sale object

For `SellOrganicData`, `sale` is `{ "count": int, "items": [...] }` where
`count` is the number of `BioData` items (the journal carries a list, not
per-item counts). Each item carries `genus`/`species` plus `variant` when
present. `MarketID`, credits, and localised names are excluded.
