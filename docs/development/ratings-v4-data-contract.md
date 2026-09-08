# Ratings V4 Data Contract

**Status:** proposed V4 data authority; review before implementation
**Depends on:** `ratings-v4-mechanics-evidence.md`, `ratings-v4-scoring-contract.md`, `ratings-v4-validation-fixtures.md`

## Purpose

This contract maps Ratings V4 mechanics onto the retained V3 canonical data model and defines the rebuildable derived relations needed by the scorer. It deliberately avoids reshaping canonical generation tables merely to suit Ratings V4.

## 1. Source-data rule

Canonical V3 generation data remains source truth. Ratings V4 consumes explicit canonical facts through an adapter and writes only derived data.

Every mechanics input is classified as:

- **AVAILABLE** — directly present in the current canonical V3 generation or normalized supporting relation;
- **DERIVABLE** — reproducibly computed from available canonical facts;
- **MISSING_SOURCE** — required by the accepted mechanics model but not currently retained;
- **UNKNOWN_CAPABLE** — schema supports the fact, but absence must not be interpreted as observed false without completeness/provenance.

No `MISSING_SOURCE` value may be fabricated by the scorer.

## 2. Current V3 source mapping

The current published canonical generation is resolved through `v3_meta.current_canonical_generation` and `v3_meta.canonical_generation.relation_schema`; application/scorer code must never hard-code a particular `v3_gen_*` schema name.

| V4 input | Current V3 source | Status | V4 treatment |
|---|---|---|---|
| system id/name | generation `systems.id64/name` | AVAILABLE | canonical identity |
| x/y/z | generation `systems.x_ly/y_ly/z_ly` | AVAILABLE | Finder/spatial only; not raw economy scoring |
| region | `systems.galaxy_region_id` + `v3_vocab.galaxy_region` | AVAILABLE | Finder/map; not raw economy scoring |
| body identity | generation `bodies.body_pk`, `system_id64`, source/frontier body ids | AVAILABLE | scorer candidate identity; preserve source identity/provenance |
| body type/classification | `bodies.body_type_id` + V3 vocab | AVAILABLE | native economy inheritance |
| stellar class | `bodies.spectral_class`, `luminosity_class`, `is_main_star` | AVAILABLE | Military / exotic-star inheritance classification |
| landable | `bodies.is_landable` | AVAILABLE, UNKNOWN_CAPABLE by source completeness | specialisation/buildability only where mechanics require it |
| tidal lock | `bodies.is_tidally_locked` | AVAILABLE, UNKNOWN_CAPABLE | Agriculture modifier only under active mechanics rule |
| terraforming state | `bodies.terraforming_state_id` + vocab | AVAILABLE, UNKNOWN_CAPABLE | Agriculture strong-link amplifier; never standalone inheritance |
| volcanism | `bodies.volcanism_type_id` + vocab | AVAILABLE, UNKNOWN_CAPABLE | Extraction strong-link amplifier; distinct from geological signals |
| atmosphere classification | `bodies.atmosphere_classification_id` | AVAILABLE | retained for later archetypes; not current raw seven unless a ruleset explicitly uses it |
| rings | generation ring relations / trusted ring facts | AVAILABLE, UNKNOWN_CAPABLE | Extraction modifier inheritance; missing evidence is unknown, not no-rings |
| biological signals | generation body signal/current relations where retained | AVAILABLE/DERIVABLE, UNKNOWN_CAPABLE | Agriculture modifier inheritance; High Tech/Tourism modifiers per ruleset |
| geological signals | generation body signal/current relations where retained | AVAILABLE/DERIVABLE, UNKNOWN_CAPABLE | Extraction + Industrial modifier inheritance; Tourism/High Tech modifiers per ruleset |
| system exotic-star presence | stellar bodies in generation | DERIVABLE | Tourism system modifier and High Tech/Tourism inheritance opportunities |
| main-sequence/Brown-Dwarf presence | stellar bodies in generation | DERIVABLE | Military inheritance opportunities |
| competing inherited economies at one body | body type + ring/bio/geo mechanics features | DERIVABLE | specialisation quality only |
| source freshness/provenance | generation source/lifecycle/completeness fields | AVAILABLE | evidence completeness/confidence |
| reserve level | not retained by current ED-Finder importer/canonical V3 shape | MISSING_SOURCE | must remain unknown until ingestion is added |
| distance from arrival | body/station orbital-distance facts where present | AVAILABLE | archetype/Finder practicality only, not raw economy scores |
| generic diversity/compactness | canonical facts | DERIVABLE | archetype/Finder only |

## 3. Reserve-level source decision

Reserve level is a real mechanics input for Extraction, Industrial and Refinery, but current ED-Finder code does not ingest or retain it.

Elite scan/journal data exposes `ReserveLevel` for ring-bearing bodies/ring systems using game values such as `PristineResources`, `MajorResources`, `CommonResources`, `LowResources`, and `DepletedResources`. Spansh is the preferred bulk-ingestion source because ED-Finder already uses whole-galaxy Spansh body data and it preserves scan-derived body/ring facts.

### Important semantic correction

Do **not** add a guessed scalar `systems.reserve_level` merely because old code referred to one.

Reserve evidence belongs to the body/ring fact domain. V4 derives any economy-level/system summary from retained reserve observations with explicit provenance.

Target canonical enrichment should retain, at minimum:

```text
body/ring reserve fact
- system_id64
- body identity / ring identity where available
- reserve_level enum/code
- source_id / source_run_id
- observed/source-updated timestamp
- coverage/completeness state
```

If a future authoritative source proves reserve level is genuinely system-wide rather than ring/body scoped for the relevant mechanic, that can be represented as another source fact without changing the V4 derived schema.

Until enrichment is populated, reserve-dependent score families remain partially incomplete rather than assuming `Common`, `None`, or any neutral value.

## 4. Derived mechanics feature relation

V4 should materialize normalized mechanics features so the scorer does not repeatedly reinterpret raw canonical rows.

Conceptually:

```text
v3_derived.system_mechanics_feature
- derived_generation_id UUID
- system_id64 BIGINT
- subject_kind SYSTEM|BODY|RING
- body_pk BIGINT NULL
- subject_key TEXT
- feature_type TEXT
- feature_value_text TEXT NULL
- feature_value_numeric DOUBLE PRECISION NULL
- known_state KNOWN_PRESENT|KNOWN_ABSENT|UNKNOWN
- source_confidence DOUBLE PRECISION
- source_freshness_at TIMESTAMPTZ NULL
- rule_input_version TEXT
- provenance JSONB
PRIMARY KEY (derived_generation_id, system_id64, subject_kind, subject_key, feature_type)
```

Examples of `feature_type`:

- `BODY_CLASS_ELW`
- `BODY_CLASS_WATER_WORLD`
- `BODY_CLASS_AMMONIA`
- `BODY_CLASS_HMC`
- `BODY_CLASS_METAL_RICH`
- `BODY_CLASS_ROCKY`
- `BODY_CLASS_ROCKY_ICE`
- `BODY_CLASS_ICY`
- `BODY_CLASS_GAS_GIANT`
- `STAR_MAIN_SEQUENCE`
- `STAR_BROWN_DWARF`
- `STAR_NEUTRON`
- `STAR_WHITE_DWARF`
- `STAR_BLACK_HOLE`
- `RING_PRESENT`
- `BIOLOGICAL_PRESENT`
- `GEOLOGICAL_PRESENT`
- `VOLCANISM_PRESENT`
- `TERRAFORMABLE`
- `TIDALLY_LOCKED`
- `RESERVE_LEVEL`

This table is derived and rebuildable. It does not replace canonical normalized facts.

## 5. Local economy opportunity relation

The scoring contract evaluates candidate local opportunities before system roll-up.

```text
v3_derived.economy_opportunity
- derived_generation_id UUID
- system_id64 BIGINT
- economy_id SMALLINT / economy_code TEXT
- candidate_kind SYSTEM|BODY
- body_pk BIGINT NULL
- mechanics_version TEXT
- scorer_version TEXT
- eligibility_class NATIVE|MODIFIER|NATIVE_AND_MODIFIER
- local_opportunity_score SMALLINT
- local_specialisation_quality SMALLINT NULL CHECK 0..100
- local_specialisation_quality_min SMALLINT CHECK 0..100
- local_specialisation_quality_max SMALLINT CHECK 0..100
- evidence_completeness DOUBLE PRECISION
- confidence DOUBLE PRECISION
- competing_economies TEXT[] / normalized child relation
- explanation JSONB
- computed_at TIMESTAMPTZ
PRIMARY KEY (derived_generation_id, system_id64, economy, candidate_kind, candidate identity)
```

This relation is useful for Inspect/explanations and for validating why the system-level score moved after a ruleset change.

## 6. System economy rating relation

Semantic authority is one row per system/economy, not one enormous historical-style ratings row.

```text
v3_derived.system_economy_rating
- derived_generation_id UUID
- system_id64 BIGINT
- economy_id SMALLINT / economy_code TEXT
- mechanics_version TEXT
- scorer_version TEXT
- potential_score SMALLINT CHECK 0..100
- specialisation_quality SMALLINT NULL CHECK 0..100
- specialisation_quality_min SMALLINT CHECK 0..100
- specialisation_quality_max SMALLINT CHECK 0..100
- evidence_completeness DOUBLE PRECISION CHECK 0..1
- confidence DOUBLE PRECISION CHECK 0..1
- best_candidate_kind SYSTEM|BODY
- best_candidate_body_pk BIGINT NULL
- best_specialisation_candidate_kind SYSTEM|BODY NULL
- best_specialisation_candidate_body_pk BIGINT NULL
- contributor_count INTEGER
- constraint_count INTEGER
- explanation JSONB
- computed_at TIMESTAMPTZ
PRIMARY KEY (derived_generation_id, system_id64, economy)
```

For hot Finder queries a separate wide projection may expose seven potential/specialisation columns, but it is only a performance projection. The normalized row-per-economy relation remains semantic authority.

Specialisation bounds represent unresolved mandatory constraints, conditional on
known inheritance/modifier evidence. The quality is null when the bounds differ;
an exact zero remains distinct from unknown. Store constraint rule IDs, states,
confidence, provenance and per-candidate intrinsic/constrained quality in the
explanation payload. The specialisation candidate is independent of the raw
potential candidate and is nullable for unresolved/zero specialisation. These
are proposed derived-data fields, not a production migration; see the candidate-3
contract in `ratings-v4-specialisation-constraints.md`.

## 7. Contributor relation

Explanation details should be queryable and testable without treating prose rationale as data authority.

```text
v3_derived.economy_rating_contributor
- derived_generation_id
- system_id64
- economy
- candidate_kind
- body_pk NULL
- rule_id
- mechanic_class NATIVE_INHERITANCE|MODIFIER_INHERITANCE|STRONG_LINK_POSITIVE|STRONG_LINK_NEGATIVE|SPECIALISATION_CONSTRAINT
- feature_type
- contribution_numeric
- evidence_grade
- provenance JSONB
PRIMARY KEY (... rule/candidate identity ...)
```

UI rationale is generated from these records.

## 8. Archetype boundary

Archetypes consume V4 ratings plus non-economy dimensions such as buildability, accessibility, body diversity, compactness, economy synergy and strategic/domain features.

Those dimensions must not be copied back into raw economy potential.

`v3_derived.system_archetype` remains separately versioned as defined by the spatial/derived-data decision.

## 9. Stable application boundary

FastAPI reads stable published-generation relations such as:

```text
v3_app.system_economy_rating
v3_app.system_economy_opportunity
v3_app.system_archetype
v3_app.system_search
```

The stable boundary resolves `v3_meta.current_derived_generation` explicitly. No generation schema names or `search_path` assumptions leak into application routes.

## 10. Implementation order

1. Add/verify reserve-level source ingestion with provenance; do not block synthetic V4 fixture development on live population.
2. Implement canonical-to-mechanics feature adapter against current V3 generation relations.
3. Implement deterministic V4 scorer against synthetic fixtures.
4. Persist mechanics features/opportunities/ratings into a disposable test derived generation.
5. Run coefficient/ordering validation, including V3.4 side-by-side regression evidence.
6. Freeze V4.0 coefficient/ruleset manifest.
7. Only then create the reviewed production derived-data bootstrap/migration authority.

## Acceptance rules

- No scorer input is silently defaulted from unknown to false/neutral.
- Reserve absence before enrichment lowers completeness; it does not fabricate reserve state.
- Geologicals and volcanism remain separate features.
- ELW inherited Military remains visible but receives no unsupported raw strategic bonus.
- Any coefficient-only V4.x change requires derived rebuild, not schema migration.
- Any mechanics-rule change updates version/provenance and triggers rebuild, not canonical mutation.
