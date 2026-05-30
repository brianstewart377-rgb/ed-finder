# Body And Ring Enrichment Dry-Run Architecture

This note defines the next enrichment stage before any new production write path
exists. It is a dry-run contract for improving body metadata, ring coverage,
mining signals, colonisation planning, exploration value, and body-level
recommendations.

## Scope

This stage may inspect local database rows and offline source payloads. It must
not call live EDSM or other live APIs, mutate production data, or add a new
apply mode. The output is a JSON report that a later guarded implementation can
validate before writes are considered.

Existing ring write helpers in the importer are not expanded by this stage. The
next implementation should prefer dry-run-only planning first, then add guarded
writes only after the report shape and safety counters are stable.

## Existing Model

`bodies` is the local body catalogue. The relevant columns are:

- Identity: `id`, `system_id64`, `name`.
- Classification: `body_type`, `subtype`, `is_main_star`, `spectral_class`,
  `luminosity`, `is_scoopable`.
- Orbital and physical metadata: `distance_from_star`, `orbital_period`,
  `semi_major_axis`, `radius`, `mass`, `gravity`, `surface_temp`,
  `surface_pressure`.
- Planet metadata: `atmosphere_type`, `atmosphere_composition`, `volcanism`,
  `materials`, `terraforming_state`, `is_terraformable`, `is_landable`,
  `is_water_world`, `is_earth_like`, `is_ammonia_world`.
- Signals and value: `bio_signal_count`, `geo_signal_count`,
  `estimated_mapping_value`, `estimated_scan_value`.

`body_rings` is the trusted ring fact table. A row stores local identity
(`system_id64`, `body_id`), optional source identity (`source_body_id`,
`body_name`), ring attributes (`ring_name`, `ring_type`, `ring_class`,
`mass_mt`, `inner_radius`, `outer_radius`), provenance (`source`,
`confidence`), and `association_status`. Consumers count only rows with
`association_status = 'local_matched'` joined to local `bodies.id`.

`body_scan_facts` stores normalised per-body journal facts keyed by
`(system_address, body_id)`, where `body_id` is the source or journal body id,
not necessarily ED-Finder `bodies.id`. It includes physical fields, class,
terraform state, atmosphere, volcanism, orbital fields, parent hierarchy,
bio/geo signal counts, `is_landable`, `is_terraformable`, tri-state
`is_ringed`, `data_sources`, and numeric `confidence`.

Body hierarchy is currently handled by `apps/api/src/body_sorting.py`.
`natural_body_sort_key_string()` is exposed on API body payloads as
`body_sort_key`, and system detail responses sort bodies in natural Elite body
order rather than distance order.

Exploration value is already stored at body level via
`estimated_scan_value` and `estimated_mapping_value`. System detail responses
sum those fields into `exploration_value.total_scan_value`,
`total_mapping_value`, and `combined_value`.

## Existing Code Paths

Spansh import currently populates `bodies` and can write `body_rings` from
explicit source ring arrays. It does not treat missing or empty Spansh ring
arrays as no-ring proof.

EDDN `Journal/Scan` normalisation writes `body_scan_facts`. Explicit ring arrays
set source scan evidence to `is_ringed = true`; explicit empty `Rings` arrays
set trusted no-ring evidence to `is_ringed = false`; missing `Rings` remains
`NULL`.

EDDN ring rows are only promoted to trusted `body_rings` rows when the source
ring payload resolves to exactly one local body. EDDN `BodyID` belongs in
`source_body_id`, not `body_rings.body_id`.

API consumers already preserve the trust boundary: a source-only
`body_scan_facts.is_ringed = true` remains `is_ringed = null` and
`ring_state = 'unknown'` until a trusted local `body_rings` row is present.
Source-only `false` from trusted EDDN scan facts can be exposed as
`not_ringed`.

## Dry-Run Report Shape

The scaffolded helper in `apps/importer/src/body_ring_enrichment_plan.py`
defines this versioned JSON shape:

```json
{
  "schema_version": "body_ring_enrichment_dry_run/v1",
  "dry_run": true,
  "source": "spansh_dump",
  "safety_rules": ["..."],
  "systems": [
    {"id64": 42, "name": "Example"}
  ],
  "body_updates_planned": [
    {
      "system_id64": 42,
      "body_id": 7,
      "body_name": "Example 4",
      "field": "estimated_mapping_value",
      "current": null,
      "planned": 12345,
      "source": "spansh_dump",
      "confidence": "source_body_payload",
      "reason": "populate_missing_value"
    }
  ],
  "ring_rows_planned": [
    {
      "system_id64": 42,
      "body_id": 7,
      "source_body_id": null,
      "body_name": "Example 4",
      "ring_name": "Example 4 A Ring",
      "ring_type": "Metal Rich",
      "ring_class": "eRingClass_MetalRich",
      "mass_mt": null,
      "inner_radius": null,
      "outer_radius": null,
      "source": "spansh_dump",
      "confidence": "source_ring_payload",
      "association_status": "local_matched"
    }
  ],
  "scan_fact_updates_planned": [
    {
      "system_address": 42,
      "body_id": 3,
      "body_name": "Example 5",
      "is_ringed": false,
      "data_sources": ["eddn_scan"],
      "confidence": 0.95,
      "reason": "trusted_empty_rings_array"
    }
  ],
  "skipped": [
    {"system_id64": 42, "body_name": "Example 6", "reason": "body_not_matched_exactly"}
  ],
  "conflicts": [
    {"system_id64": 42, "type": "body_id_name_mismatch"}
  ],
  "fetch_errors": [],
  "dirty_system_ids_planned": [42],
  "summary": {
    "systems": 1,
    "body_updates_planned": 1,
    "ring_rows_planned": 1,
    "trusted_ring_rows_planned": 1,
    "confirmed_ringed_bodies_planned": 1,
    "scan_fact_updates_planned": 1,
    "explicit_no_ring_scan_facts_planned": 1,
    "source_only_ring_true_retained_unknown": 0,
    "skipped": 1,
    "conflicts": 1,
    "fetch_errors": 0,
    "dirty_systems_planned": 1
  }
}
```

`scan_fact_updates_planned` is report-only in this stage. A later apply path
must prove that a row uses source/journal body identity before writing
`body_scan_facts`.

## Safety Rules

Body identity matching:

- Match inside a known `system_id64`.
- Prefer exact local body id only for sources where the id is known to be
  ED-Finder `bodies.id`, then require the name to agree.
- For EDDN, keep Journal `BodyID` as `source_body_id`; never write it as
  `body_rings.body_id`.
- Name-only matches must be exact after conservative normalisation and must
  resolve to exactly one local body.
- Ambiguous, missing, or mismatched identity becomes `conflicts` or `skipped`,
  never a guessed write.

Ring row idempotency:

- Planned trusted ring rows use the existing identity key:
  `(system_id64, body_id, ring_name, source)`.
- Rows missing any key component are skipped.
- Duplicate rows in one batch are counted and skipped before any future apply
  path.
- Existing ring rows may be enriched with missing attributes from equal or
  stronger provenance, but weaker data must not erase populated fields.

Conflict handling:

- Body id/name mismatch, multiple local matches, missing ring identity,
  belt-source evidence, and source payload contradictions must be visible in
  `conflicts` or `skipped`.
- Risky conflicts block a future apply phase. Dry-run reports should remain
  useful even when conflicts exist.

Source provenance:

- Every planned body update, ring row, or scan fact update carries `source` or
  `data_sources` plus `confidence`.
- Provenance labels must be source-specific, for example `spansh_dump`,
  `eddn_scan`, or a later guarded EDSM label.

No blind overwrites:

- Populate missing values first.
- Do not replace trusted values with weaker source values.
- Do not downgrade `is_ringed = true` confirmed by trusted `body_rings`.
- Do not convert missing ring rows into no-ring evidence.

Ring state promotion:

- Trusted local `body_rings` rows are required before consumer ring state can be
  confirmed as ringed.
- Source-only `body_scan_facts.is_ringed = true` remains unknown.
- Source-only `body_scan_facts.is_ringed = false` from trusted EDDN scan facts
  may represent explicit no-rings.
- Missing scan facts and missing ring rows remain unknown.

## Small Implementation Plan

1. Keep this pass dry-run only: design doc, pure report helpers, and unit tests.
2. Add a local/offline planner that consumes existing local `bodies`,
   `body_rings`, `body_scan_facts`, and an offline source payload. It should
   emit the versioned report above and write nothing.
3. Extend body update planning field by field, starting with missing
   `estimated_mapping_value`, `estimated_scan_value`, signals, and obvious
   physical metadata. Each field should have a source confidence rule and a
   no-overwrite rule.
4. Reuse or extract the existing ring planner so `build_ring_plan` and the new
   dry-run report share identity matching and ring-row normalisation.
5. Add a guard-level validator that refuses any report where source-only
   `is_ringed = true` is counted as confirmed ringed without a trusted
   `body_rings` row.
6. Only after dry-run counters are stable, design a separate apply phase with
   bounded scope, explicit flags, final dry-run validation, and dirty marking.

## Suggested Next Stage

Build a dry-run CLI mode that reads a small offline Spansh sample or local test
fixture, fetches matching local bodies from a non-production database, and emits
`body_ring_enrichment_dry_run/v1`. It should still have no live API calls and no
write flags. Acceptance should be focused unit tests plus a fixture-based
end-to-end dry-run test that asserts JSON counters, skipped rows, conflicts, and
the source-only ring truth boundary.
