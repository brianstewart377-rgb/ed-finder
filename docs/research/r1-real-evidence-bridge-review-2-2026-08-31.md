# ED-Finder R1 — Real Evidence Bridge
## Review 2 — Final Pre-Code Technical Contract

Date: 2026-08-31  
Status: **final pre-code Review 2; no code starts until owner acceptance**  
Branch: `chatgpt-ed-new-ops-requests`  
Review 1: `docs/research/r1-real-evidence-bridge-review-1-2026-08-31.md`

## 1. Stage objective

Implement a pure, read-only adapter that accepts dictionaries shaped like ED-Finder's current canonical `systems`, `bodies`, `body_rings`, and bounded evidence metadata, and projects them into explicit R1 canonical facts.

The stage proves that the fixture-only Finder comparison model can receive data shaped like the real repository without inheriting legacy scorer semantics or database-default ambiguity.

This stage does **not** wire ranking into live Finder.

## 2. Critical source semantics established by repository inspection

### 2.1 Canonical body schema

Current `bodies` contains, among other fields:

```text
id
system_id64
name
body_type
subtype
is_main_star
distance_from_star
is_tidal_lock
radius
gravity
surface_temp
atmosphere_type
volcanism
terraforming_state
is_terraformable
is_landable
is_water_world
is_earth_like
is_ammonia_world
bio_signal_count
geo_signal_count
spectral_class
updated_at
```

Several physically important values are nullable (`distance`, tidal state, radius, gravity, temperature, atmosphere, volcanism).

But several semantic flags/counts are stored as NOT NULL defaults:

```text
is_terraformable = false
is_landable = false
bio_signal_count = 0
geo_signal_count = 0
```

Those database values must not automatically become R1 confirmed negatives.

### 2.2 Importer asymmetry

Current Spansh import logic establishes:

- exact `Ammonia world` subtype as a positive canonical identity;
- Terraformable true from explicit Terraformable state or positive flag;
- landable stored through `bool(source flag or false)`;
- signal parsers return `0` when signal data is absent.

Therefore:

- positive Terraformable/Landable/signal values are useful positive evidence;
- false/zero can be source-confirmed **or** an importer default;
- R1 must preserve that ambiguity unless separate evidence confirms the negative.

### 2.3 Ring semantics are stronger

`body_rings` explicitly documents:

> Missing rows mean unknown ring state, not no rings.

Only `association_status='local_matched'` rows count as trusted positive ring association for a body.

Ambiguous/conflicting association rows must not become positive ring facts.

## 3. Final allowed implementation files

Only these files may be created/changed in this stage:

```text
apps/api/src/r1_evidence_bridge/__init__.py
apps/api/src/r1_evidence_bridge/types.py
apps/api/src/r1_evidence_bridge/body_projection.py
apps/api/src/r1_evidence_bridge/provenance.py
apps/api/src/r1_evidence_bridge/slot_prediction.py
apps/api/src/r1_evidence_bridge/candidate_projection.py
apps/api/src/r1_evidence_bridge/fixtures.py
tests/test_r1_evidence_bridge.py
docs/research/r1-real-evidence-bridge-completion-2026-08-31.md
```

Audit-only; must not change:

```text
sql/001_schema.sql
apps/importer/src/import_spansh.py
apps/api/src/evidence_store/models.py
apps/api/src/evidence_store/store.py
apps/api/src/evidence_store/source_catalog.py
apps/api/src/domain/colonisation_rules.py
apps/importer/src/build_ratings.py
apps/importer/src/build_topology.py
apps/importer/src/build_archetype_scores.py
apps/api/src/local_search.py
apps/api/src/search_economies.py
frontend/src/features/search/*
```

The existing `apps/api/src/r1_finder_compare/*` package is downstream/audit-only. It may be imported for the canonical dataclasses and compatibility assertions, but must not be modified.

## 4. Source-boundary contract

Pure projection code must not import:

- asyncpg/psycopg;
- FastAPI;
- Redis;
- network clients;
- importer modules;
- legacy rating/topology/archetype scoring modules;
- frontend code.

It may import standard library and the new `r1_finder_compare.types` dataclasses.

No DB loader is part of this implementation slice.

## 5. Exact raw input types

The adapter uses frozen row-shaped dataclasses so tests can model actual canonical rows without a DB.

```python
@dataclass(frozen=True)
class CanonicalSystemRow:
    id64: str
    name: str
    has_body_data: bool
    body_count: int
    updated_at: str | None

@dataclass(frozen=True)
class CanonicalBodyRow:
    id: str
    system_id64: str
    name: str
    body_type: str
    subtype: str | None
    distance_from_star: float | None
    is_tidal_lock: bool | None
    radius: float | None
    gravity: float | None
    surface_temp: float | None
    atmosphere_type: str | None
    volcanism: str | None
    terraforming_state: str | None
    is_terraformable: bool
    is_landable: bool
    bio_signal_count: int
    geo_signal_count: int
    updated_at: str | None

@dataclass(frozen=True)
class CanonicalRingRow:
    body_id: str | None
    source_body_id: str | None
    body_name: str | None
    ring_name: str | None
    source: str
    confidence: str
    association_status: str
    updated_at: str | None
```

## 6. Explicit confirmation hints

Because some canonical defaults erase source-presence information, the pure adapter accepts optional evidence hints separately from canonical rows.

```python
@dataclass(frozen=True)
class BodyEvidenceHints:
    body_id: str
    landable_negative_confirmed: bool = False
    terraformable_negative_confirmed: bool = False
    bio_signal_scan_complete: bool = False
    geo_signal_scan_complete: bool = False
    provenance_ids: tuple[str, ...] = ()
```

These hints represent explicit evidence metadata, not guessed defaults.

No hint means no extra negative knowledge.

## 7. Field availability type

```python
FactAvailability = Literal[
    'known',
    'unknown',
    'ambiguous',
    'conflicting',
    'not_applicable',
]

@dataclass(frozen=True)
class FactStatus:
    availability: FactAvailability
    provenance_ids: tuple[str, ...]
    reason: str
```

Projected evidence stores both the downstream `BodyFact` value (`None` where unknown) and field-level status/provenance.

## 8. Exact body projection rules

### Base identity

- `base_identity = subtype` when non-empty canonical subtype exists.
- no broad substring promotion to another identity;
- exact true Ammonia World iff normalized subtype equals `Ammonia world`;
- `is_ammonia_world=true` cannot override a contradictory gas-giant subtype in this bridge; contradiction makes true-Ammonia identity unavailable/conflicting rather than silently choosing one.

### Landable

- canonical `is_landable=true` -> known positive;
- canonical false + `landable_negative_confirmed=true` -> known negative;
- canonical false without confirmation -> Unknown.

### Terraformable

- `terraforming_state == 'Terraformable'` or positive flag -> known true;
- explicit non-empty non-Terraformable state or `terraformable_negative_confirmed=true` -> known false;
- false flag + no state/confirmation -> Unknown.

### Geological presence

- `geo_signal_count > 0` -> known true;
- `geo_signal_count == 0` + `geo_signal_scan_complete=true` -> known false;
- zero without scan-complete evidence -> Unknown.

Volcanism never sets geological presence.

### Biological presence

- `bio_signal_count > 0` -> known true;
- zero + `bio_signal_scan_complete=true` -> known false;
- zero without confirmation -> Unknown.

### Rings

For a body:

- one or more `local_matched` ring rows -> known true;
- any relevant `conflict` row without a resolved local match -> conflicting/None;
- relevant ambiguous/unresolved rows without local match -> ambiguous/None;
- no ring rows -> Unknown/None;
- never infer false from absence of rows.

### Volcanism

- null/empty -> Unknown;
- explicit `No volcanism` -> known absence represented by that canonical string or normalized none marker;
- any other explicit value -> known value.

### Atmosphere

- null/empty -> Unknown;
- exact `No atmosphere` -> known absence;
- any other explicit atmosphere string -> known value/presence.

### Tidal lock

- nullable canonical boolean maps directly when non-null;
- null -> Unknown.

### Radius / gravity / surface temperature / distance

- non-null finite numeric -> known value;
- null/non-finite -> Unknown.

## 9. Projected body evidence type

```python
@dataclass(frozen=True)
class ProjectedBodyEvidence:
    body: BodyFact
    field_status: tuple[tuple[str, FactStatus], ...]
    true_ammonia_world: bool | None
    raw_bio_signal_count: int
    raw_geo_signal_count: int
    provenance_ids: tuple[str, ...]
```

`field_status` is lexically sorted by field name for deterministic hashing.

Raw signal counts remain inspectable evidence; they do not become repeated body-local modifier credit.

## 10. System projection type

```python
BodyDataCompleteness = Literal['known_present', 'unknown', 'conflicting']

@dataclass(frozen=True)
class ProjectedSystemEvidence:
    system_id64: str
    system_name: str
    body_data_completeness: BodyDataCompleteness
    bodies: tuple[ProjectedBodyEvidence, ...]
    provenance_ids: tuple[str, ...]
    projection_revision: str
```

No-body behavior:

- zero requested/projected body rows is never treated as complete merely because `all([])` is true;
- `has_body_data=false` -> Unknown body completeness;
- `has_body_data=true` with zero rows -> conflicting/incomplete state, not a zero-body factual system;
- declared `body_count` and actual supplied rows may be compared for bounded completeness diagnostics, but a mismatch never fabricates missing rows.

## 11. Surface-slot prediction contract

```python
@dataclass(frozen=True)
class SlotPrediction:
    availability: Literal['known_prediction', 'unknown']
    slots: int | None
    model_id: str
    model_revision: str
    evidence_class: Literal['prediction']
    input_status: tuple[tuple[str, FactAvailability], ...]
    caveats: tuple[str, ...]
```

Model ID:

```text
surface_slots_nyatto_raven_family
```

Revision:

```text
community-validated-2026-08-31.1
```

Exact formula when every required input/modifier state is known:

```text
if not landable OR temp > 700 K OR gravity > 2.7g -> 0
base radius:
  <1500 -> 1
  <3750 -> 2
  <6000 -> 3
  >=6000 -> 4
+1 HMC
+1 Terraformable
+1 geologicals OR volcanism-present
+2 atmosphere-present
cap 7
```

Boundary semantics:

- exactly 700 K allowed;
- exactly 2.7 g allowed;
- exactly 1500 -> base 2;
- exactly 3750 -> base 3;
- exactly 6000 -> base 4.

Exact prediction requires known:

- landability;
- temperature;
- gravity;
- radius;
- terraformability;
- geological presence;
- volcanism presence/absence;
- atmosphere presence/absence.

If any required state is Unknown/ambiguous/conflicting, exact slot prediction is Unknown.

Caveat always records the two historical +1 residuals as model uncertainty; no correction rule is added.

## 12. Orbital capacity first-slice contract

Only one current orbital rule is promoted in this stage:

```text
canonical gas giant identity -> predicted orbital construction capacity = 1
```

Provenance class remains `prediction/mechanics-derived`, versioned to current post-Operations mechanics.

Other orbital body classes remain Unknown in this bridge slice rather than reusing the stale topology 3/5/etc. estimator.

## 13. CandidateEvidence projection boundary

This stage must not invent real-system pair stability or programme fit.

### Extraction evidence

Projection may set:

- `satisfied=True` if at least one known canonical Extraction source exists (HMC, Metal-Rich, known ring modifier, known geological modifier);
- `satisfied=False` only when source coverage is explicitly complete enough to establish none exist;
- otherwise `satisfied=None` / disposition missing or partial.

The numeric `support` field remains `None` in real-evidence projection. The proof-stage geometric policy is not promoted to real ranking calibration here.

### Refinery evidence

Same principle: known compatible canonical sources may establish positive presence; absence is not claimed without sufficient coverage. Numeric `support=None`.

### Pair stability

Default:

```text
pair_stability = 'unknown'
```

unless a future explicit pair/link evidence source is supplied. Canonical body inventory alone cannot prove a robust top-two ER economy pair.

Therefore real `P-ER-01` assessment from this bridge will normally remain Not assessable until a later link/economy-outcome bridge exists. This is intentional and preferable to inventing pair percentages.

### Physical capacity

`CapacityEvidence` may expose known predicted slot facts, but `sufficient` remains `None` unless an explicit programme/role capacity requirement is supplied by a later layer.

This bridge does not decide how many slots P-ER-01 requires.

## 14. Downstream compatibility assertion

The adapter must be able to create a structurally valid `r1_finder_compare.types.CandidateEvidence`.

The downstream evaluator may be invoked **without fit strategy** only to prove state/Unknown propagation.

No test in this stage may claim that the real bridge has calibrated Extraction or P-ER Plan Fit.

## 15. Deterministic fixture corpus

Use schema-semantic projection fixtures, not fabricated claims about live systems.

Exact fixture IDs:

```text
canonical_geo_hmc
canonical_ringed_rocky
canonical_ammonia_world
canonical_ammonia_life_gas_giant
canonical_default_false_unknowns
canonical_no_body_data
canonical_surface_slot_boundaries
canonical_gas_giant_orbital
```

These are synthetic canonical-row fixtures shaped exactly like the current schema/importer semantics. They are not labelled as observed real systems.

Named real-galaxy golden systems remain a later read-only snapshot validation step.

## 16. Exact automated tests

One new test file:

```text
tests/test_r1_evidence_bridge.py
```

Required tests:

```text
test_geo_hmc_projects_composable_identity_and_modifier
test_ringed_geo_rocky_keeps_identity_ring_and_geo_separate
test_terraformable_true_survives_projection
test_terraformable_false_without_source_confirmation_is_unknown
test_landable_false_without_source_confirmation_is_unknown
test_zero_geo_without_complete_scan_is_unknown
test_zero_geo_with_complete_scan_is_known_negative
test_zero_bio_without_complete_scan_is_unknown
test_volcanism_does_not_imply_geologicals
test_true_ammonia_world_requires_exact_identity
test_ammonia_life_gas_giant_is_not_true_ammonia_world
test_conflicting_ammonia_flag_and_subtype_withholds_true_identity
test_local_matched_ring_row_is_known_positive
test_missing_ring_rows_are_unknown_not_false
test_conflicting_ring_row_is_conflicting
test_no_body_data_is_unknown_not_zero_complete
test_has_body_data_true_with_zero_rows_is_conflicting
test_surface_slot_unknown_if_required_input_unknown
test_surface_slot_threshold_700_k_is_allowed
test_surface_slot_threshold_2_7_g_is_allowed
test_surface_slot_radius_boundaries_1500_3750_6000
test_surface_slot_modifiers_are_independent_and_cap_at_7
test_surface_slot_geo_and_volcanism_together_add_only_one
test_surface_slot_prediction_is_labelled_prediction_not_observation
test_gas_giant_orbital_capacity_is_one
test_non_gas_giant_orbital_capacity_remains_unknown_in_first_slice
test_candidate_projection_does_not_invent_pair_stability
test_candidate_projection_does_not_invent_numeric_support
test_downstream_candidate_evidence_shape_is_compatible
test_downstream_p_er_remains_not_assessable_when_pair_unknown
test_projection_is_deterministic
test_source_boundary_has_no_db_network_or_legacy_scorer_imports
```

## 17. Completion evidence

Completion report must include:

- exact base/head SHA;
- exact changed-file list;
- focused pytest output;
- source-boundary scan;
- table showing every field projection for the eight schema-semantic fixtures;
- exact surface-slot boundary outputs;
- gas-giant orbital result;
- ammonia regression outputs;
- default-false/zero ambiguity outputs;
- deterministic snapshot/hash result;
- downstream CandidateEvidence compatibility result;
- explicit demonstration that P-ER remains Not assessable with unknown pair evidence;
- explicit no DB/write/search/UI/deploy statement.

## 18. Final stage boundary

No migration, DB write, Evidence Store mutation, live Finder order change, frontend change, API contract change, ratings/archetype rebuild, deployment or merge is authorised.

After this bridge passes, the next design stage may define a bounded read-only real-system snapshot loader and/or the missing link/economy-outcome evidence needed to make real programme comparison assessable.
