# R1 Persistence / Storage Schema — Review 2

Date: 2026-08-31
Status: final pre-migration technical contract
Branch: `chatgpt-ed-new-ops-requests`

This document refines Review 1 into the exact storage contract to use when a later migration stage is explicitly authorised. It **does not create tables, alter schemas, run migrations, write production data, or authorise those actions by itself**.

## 1. Storage principle

R1 is not another galaxy-wide ratings database.

Persistent storage is split into three concerns:

1. **canonical galaxy truth** — remains in normalized V3;
2. **rebuildable Finder acceleration** — context-independent capability summaries only;
3. **durable player/project state** — saved plan revisions and immutable assessments when continuity/audit requires them.

Ordinary Finder searches, comparison contexts, auto-generated candidate plans, and ordinary search-result assessments remain ephemeral and create no SQL rows.

## 2. Logical schemas

When implementation is later authorised, use three R1 schemas rather than adding another flat set of `public.ratings_*` tables:

- `r1_meta` — immutable revision registries and capability-generation publication metadata;
- `r1_cache` — logical current Finder capability surface;
- `r1_plan` — durable user-selected plan revisions and assessment snapshots.

Canonical body identity remains under V3 (`v3_vocab` plus the next immutable V3 generation), not under an R1 schema.

## 3. Required upstream canonical correction

### 3.1 `v3_vocab.body_subtype`

The next canonical generation must gain an explicit normalized body-subtype vocabulary.

Logical contract:

```sql
body_subtype_id    <same integer-id convention as other v3_vocab tables> PRIMARY KEY
body_type_id       <same type as v3_vocab.body_type.body_type_id> NOT NULL
public_code        TEXT NOT NULL UNIQUE
display_name       TEXT NOT NULL
active             BOOLEAN NOT NULL DEFAULT TRUE
UNIQUE (body_subtype_id, body_type_id)
FOREIGN KEY (body_type_id) REFERENCES v3_vocab.body_type(body_type_id)
```

`public_code` is a stable canonical token. `display_name` is player-facing text and may change without changing identity.

Examples include HMC, metal-rich body, rocky body, rocky-ice body, icy body, Water World, Earth-like World, Ammonia World, gas-giant variants, Black Hole, Neutron Star, White Dwarf variants, and other exact source subtype identities.

### 3.2 Canonical generation `bodies.body_subtype_id`

The next immutable canonical body relation gains nullable `body_subtype_id`.

Hard rules:

- explicit source classification only;
- no subtype inference from atmosphere, composition, mass, temperature, or any R1 scoring/mechanics model;
- unmapped/absent classification remains NULL/Unknown;
- true Ammonia World requires the explicit Ammonia World subtype;
- atmosphere containing ammonia must never populate Ammonia World identity;
- a composite subtype/type consistency FK or equivalent canonical validation must prevent a planet subtype being attached to a star and vice versa.

Do not mutate the retained `v3_gen_phase4c_full_20260827_r5` generation in place.

Until a corrected canonical generation exists, EDSM or other explicit subtype data may be used only as a provenance-labelled bounded research overlay, never silently promoted to production canonical truth.

## 4. Revision metadata

### 4.1 `r1_meta.mechanics_revision`

One row identifies an immutable set of Elite mechanics rules used by R1.

Columns:

```text
mechanics_revision_id      TEXT PK
friendly_version           TEXT NOT NULL
game_patch                 TEXT NULL
rules_sha256               CHAR(64) NOT NULL UNIQUE
source_evidence_refs       JSONB NOT NULL DEFAULT []
effective_from             TIMESTAMPTZ NULL
effective_to               TIMESTAMPTZ NULL
status                     TEXT NOT NULL
created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
notes                      TEXT NULL
```

Allowed `status`:

- `experimental`
- `active`
- `retired`

A partial unique index permits at most one `active` mechanics revision.

Mechanics revision contains rules such as construction-slot mechanics and link behavior. It must not contain player-preference fit weights.

### 4.2 `r1_meta.model_revision`

One row identifies the immutable R1 assessment software/config bundle.

Columns:

```text
model_revision_id           TEXT PK
friendly_version            TEXT NOT NULL
code_commit_sha             CHAR(40) NOT NULL
model_sha256                CHAR(64) NOT NULL UNIQUE
canonical_contract_revision TEXT NOT NULL
capability_revision         TEXT NOT NULL
candidate_generator_revision TEXT NOT NULL
fit_policy_revision         TEXT NULL
status                      TEXT NOT NULL
created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
effective_from              TIMESTAMPTZ NULL
effective_to                TIMESTAMPTZ NULL
notes                       TEXT NULL
```

Allowed `status`:

- `experimental`
- `shadow`
- `active`
- `retired`

At most one row may be `active`.

Important: `capability_revision` is a component identity, not a galaxy score version. Changing fit policy alone does **not** invalidate/rebuild capability generations if capability semantics are unchanged.

### 4.3 `r1_meta.programme_revision`

Columns:

```text
programme_id          TEXT NOT NULL
programme_revision    TEXT NOT NULL
programme_name        TEXT NOT NULL
definition_sha256     CHAR(64) NOT NULL
definition_json       JSONB NOT NULL
status                TEXT NOT NULL
created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
effective_from        TIMESTAMPTZ NULL
effective_to          TIMESTAMPTZ NULL
PRIMARY KEY (programme_id, programme_revision)
UNIQUE (programme_id, definition_sha256)
```

Allowed `status`:

- `draft`
- `shadow`
- `active`
- `retired`

A programme row describes explicit player intent/requirements/coexistence/allocation rules. It is not a universal scoring profile.

## 5. Finder capability generations

### 5.1 Why generation-based rather than update-in-place

The galaxy contains approximately 198M normalized systems. The capability cache must therefore be built as an immutable generation and atomically published, not updated row-by-row in place.

Changing any of these invalidates a capability generation:

- canonical generation;
- `capability_revision`;
- mechanics revision where mechanics affect a cached derived fact (for example surface construction slots).

Changing only:

- programme definitions;
- candidate-plan generator;
- fit policy;

does not require rebuilding the context-independent capability cache.

### 5.2 `r1_meta.capability_generation`

Columns:

```text
capability_generation_id BIGINT PK generated by identity
generation_key           TEXT NOT NULL UNIQUE
relation_schema          TEXT NOT NULL UNIQUE
canonical_generation_id  BIGINT NOT NULL
capability_revision      TEXT NOT NULL
mechanics_revision_id    TEXT NOT NULL FK -> r1_meta.mechanics_revision
builder_code_sha         CHAR(40) NOT NULL
builder_config_sha256    CHAR(64) NOT NULL
lifecycle_state          TEXT NOT NULL
row_count                BIGINT NULL
validation_receipt       JSONB NULL
build_started_at         TIMESTAMPTZ NOT NULL DEFAULT now()
validated_at             TIMESTAMPTZ NULL
published_at             TIMESTAMPTZ NULL
retired_at               TIMESTAMPTZ NULL
failed_at                TIMESTAMPTZ NULL
failure_reason           TEXT NULL
```

Allowed lifecycle:

- `building`
- `validated`
- `published`
- `retired`
- `failed`

`canonical_generation_id` must bind to `v3_meta.canonical_generation` when the migration is implemented.

### 5.3 `r1_meta.current_capability_generation`

Singleton publication pointer:

```text
singleton                 BOOLEAN PK CHECK (singleton)
capability_generation_id  BIGINT NOT NULL FK -> r1_meta.capability_generation
publication_sequence      BIGINT NOT NULL
published_at              TIMESTAMPTZ NOT NULL
```

### 5.4 Physical capability relation

Each build gets its own immutable generation schema, for example:

```text
r1_cap_<generation_key>.system_capability
```

The production contract exposed to Finder is:

```text
r1_cache.system_capability_current
```

implemented as a view targeting exactly one validated physical generation. Publication changes the singleton metadata pointer and current view in one transaction.

Do not retain every 198M-row capability generation forever. Retain the current generation and immediate previous successful generation through the rollback window; retain generation metadata/receipts indefinitely.

## 6. Exact first capability row contract

The physical capability relation contains **one row per canonical system**. It contains only context-independent, rebuildable facts/derived mechanics useful for candidate narrowing.

It must not contain Plan Fit, programme outcome, economy recommendation, pair resilience, universal system score, or suggested plan.

### 6.1 Identity/inventory

```text
system_id64                     BIGINT PRIMARY KEY
source_body_count               INTEGER NULL
loaded_body_count               INTEGER NOT NULL
body_inventory_state            SMALLINT NOT NULL
```

`body_inventory_state` codes:

- `0` Unknown
- `1` Complete
- `2` Partial
- `3` Conflicting

Do not convert incomplete/conflicting inventory into zero counts masquerading as known negatives.

### 6.2 Explicit identity counts

All counts are non-negative integers. Initial hot identity columns:

```text
star_count
planet_count
hmc_count
metal_rich_body_count
rocky_body_count
rocky_ice_body_count
icy_body_count
water_world_count
earth_like_world_count
ammonia_world_count
gas_giant_count
neutron_star_count
black_hole_count
white_dwarf_count
body_subtype_unknown_count
```

These are exact subtype identities. Modifiers never replace these counts.

A body may contribute simultaneously to `hmc_count` and modifier counts such as geological/terraformable/ringed.

### 6.3 Modifier/presence counts

```text
landable_count
landable_unknown_count
terraformable_count
terraforming_unknown_count
ringed_body_count
geological_body_count
geological_unknown_count
biological_body_count
biological_unknown_count
volcanism_present_count
volcanism_unknown_count
atmosphere_present_count
atmosphere_unknown_count
tidally_locked_count
tidal_lock_unknown_count
signals_incomplete_body_count
genera_incomplete_body_count
distance_unknown_body_count
```

Rules:

- a positive geological signal and HMC identity coexist;
- geological presence does not imply volcanism;
- signal count does not multiply the body predicate;
- absence of a signal is a known negative only where source signal completeness supports that conclusion;
- missing ring evidence is never silently turned into `ringed=false`.

### 6.4 Ring/reserve facts

```text
ring_count
rocky_ring_count
icy_ring_count
metal_rich_ring_count
metallic_ring_count
reserve_depleted_ring_count
reserve_low_ring_count
reserve_common_ring_count
reserve_major_ring_count
reserve_pristine_ring_count
reserve_unknown_ring_count
```

Reserve Unknown must remain separate from every known reserve class.

### 6.5 Versioned physical capacity

```text
surface_buildable_body_count
surface_slot_known_body_count
surface_slot_unknown_body_count
surface_slot_total_known
surface_slot_max_known
gas_giant_orbital_slot_total_known
```

No generic `orbital_slot_total` is allowed until the current mechanic is known for all body families being aggregated.

`surface_slot_total_known` is meaningful only alongside `surface_slot_unknown_body_count`; the UI/API must not present it as an exact system total if Unknown bodies remain.

### 6.6 Cheap factual distance summaries

Nullable `DOUBLE PRECISION` columns:

```text
nearest_landable_distance_ls
nearest_hmc_distance_ls
nearest_metal_rich_distance_ls
nearest_ringed_body_distance_ls
nearest_water_world_distance_ls
nearest_earth_like_world_distance_ls
nearest_ammonia_world_distance_ls
nearest_terraformable_distance_ls
furthest_known_body_distance_ls
```

These are factual summaries used only for filtering/candidate narrowing. Final logistics is calculated from the concrete plan/allocation and must not be copied from these fields.

### 6.7 Capability row constraints

- every count >= 0;
- `loaded_body_count <= source_body_count` when source count is known and the inventory state is not conflicting;
- every identity/modifier count <= loaded body count where logically applicable;
- `surface_slot_known_body_count + surface_slot_unknown_body_count <= loaded_body_count`;
- `surface_slot_max_known` is NULL when no surface-slot prediction is known;
- a nearest-distance field is NULL when the corresponding positive body count is zero or Unknown;
- no capability row stores a system-level pair resilience field.

Use INTEGER for counts in the initial implementation rather than SMALLINT. Storage is larger, but this avoids embedding an unnecessary hard body-count ceiling into the semantic contract. Physical compression/encoding can be revisited after measured size tests.

## 7. Capability indexes and Finder query strategy

Mandatory initial indexes per physical capability generation:

1. primary B-tree on `system_id64`;
2. partial B-tree `(water_world_count DESC, nearest_water_world_distance_ls, system_id64)` where `water_world_count > 0`;
3. partial B-tree `(earth_like_world_count DESC, nearest_earth_like_world_distance_ls, system_id64)` where `earth_like_world_count > 0`;
4. partial B-tree `(ammonia_world_count DESC, nearest_ammonia_world_distance_ls, system_id64)` where `ammonia_world_count > 0`;
5. partial B-tree `(black_hole_count DESC, system_id64)` where `black_hole_count > 0`;
6. partial B-tree `(neutron_star_count DESC, system_id64)` where `neutron_star_count > 0`.

Do **not** create an index for every capability slider by default.

Normal localized Finder flow should lead with the canonical systems spatial/distance index and then join capability rows by `system_id64`. HMC/rings/geological/slot secondary indexes are added only when EXPLAIN/benchmark evidence demonstrates a need. Adding such an index is a performance-only change and cannot alter search semantics.

No index is permitted whose sole purpose is global ordering by a universal score, because no such column exists.

## 8. Capability build / publish / rollback contract

A future builder must:

1. bind to one immutable published canonical generation;
2. bind to one capability revision and mechanics revision;
3. build a new physical relation without altering the current one;
4. create mandatory indexes;
5. ANALYZE the completed relation;
6. run golden/control checks and bounded distribution checks;
7. verify deterministic rebuild output for sampled systems;
8. verify no Unknown was converted into False/zero incorrectly;
9. verify exact Ammonia identity and HMC+modifier composability;
10. validate row count/inventory reconciliation;
11. mark generation `validated`;
12. publish pointer + `r1_cache.system_capability_current` atomically;
13. leave previous successful generation intact for rollback;
14. permit rollback by pointer/view switch only, with no galaxy rewrite.

Never COALESCE a missing R1 capability row to legacy ratings/v4 output.

## 9. Durable plan model — immutable revisions

Review 1's mutable saved-plan shape is refined here: a saved plan is a stable project header plus immutable plan revisions.

### 9.1 `r1_plan.saved_plan`

Columns:

```text
plan_id                    UUID PK
owner_account_id           <exact same DB type as v3_identity.account.account_id> NOT NULL
system_id64                BIGINT NOT NULL
plan_name                  TEXT NULL
plan_state                 TEXT NOT NULL
current_revision_number    INTEGER NOT NULL
created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
archived_at                TIMESTAMPTZ NULL
```

Allowed state:

- `draft`
- `selected`
- `build_pack`
- `archived`

The implementation migration must use the exact underlying `v3_identity.account.account_id` type discovered from catalog; do not guess/cast it through TEXT.

Persistent saved plans are private to an authenticated account in the first release. Public/shared/community plans require a separate future design; do not add sharing flags now.

Index:

```text
(owner_account_id, updated_at DESC)
```

### 9.2 `r1_plan.plan_revision`

Every meaningful generated/saved/user-edited plan state is immutable.

Columns:

```text
plan_revision_id                 UUID PK
plan_id                          UUID NOT NULL FK -> saved_plan ON DELETE CASCADE
revision_number                  INTEGER NOT NULL
previous_plan_revision_id        UUID NULL FK -> plan_revision
programme_id                     TEXT NOT NULL
programme_revision               TEXT NOT NULL
carrier_mode                     TEXT NOT NULL
created_from_model_revision_id   TEXT NULL
created_from_mechanics_revision_id TEXT NULL
created_from_canonical_generation_id BIGINT NULL
created_from_evidence_snapshot_sha256 CHAR(64) NULL
candidate_plan_sha256            CHAR(64) NOT NULL
change_kind                      TEXT NOT NULL
created_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (plan_id, revision_number)
UNIQUE (plan_id, candidate_plan_sha256)
FK (programme_id, programme_revision) -> r1_meta.programme_revision
```

Allowed `carrier_mode`:

- `no_carrier`
- `carrier_available`

`compare_both` is a search/assessment request mode, not a single saved plan state; saving one scenario produces a concrete carrier mode.

Allowed `change_kind` initial set:

- `finder_generated`
- `user_edit`
- `programme_change`
- `rebase`

User edits create a new revision; they never mutate old nodes/allocations that an assessment or Build Pack may reference.

## 10. Persistent body reference contract

Generation-local `body_pk` is not sufficient as the only durable plan reference.

A plan-node host-body reference must preserve both:

1. stable/source identity usable for rebasing to a future canonical generation; and
2. the exact generation-local body identity used by the original assessment.

### 10.1 `r1_plan.plan_node`

Columns:

```text
plan_node_id                 UUID PK
plan_revision_id             UUID NOT NULL FK -> plan_revision ON DELETE CASCADE
node_key                     TEXT NOT NULL
node_kind                    TEXT NOT NULL
parent_plan_node_id          UUID NULL FK -> plan_node
facility_type_code           TEXT NOT NULL
intended_role_code           TEXT NULL
locality_key                 TEXT NULL
host_body_pk_snapshot        BIGINT NULL
host_body_source_id64        BIGINT NULL
host_body_frontier_id        INTEGER NULL
host_body_name_snapshot      TEXT NULL
ordinal                      INTEGER NOT NULL
metadata_json                JSONB NOT NULL DEFAULT {}
UNIQUE (plan_revision_id, node_key)
UNIQUE (plan_revision_id, ordinal)
```

At least one host-body identity field is required for node kinds that are body-local.

`host_body_pk_snapshot` is for forensic continuity only; reassessment against a newer canonical generation resolves stable identity rather than assuming that PK survived the generation change.

Initial `node_kind` vocabulary remains application-owned/versioned by the programme contract; core locality/body fields are typed and may not be hidden only inside JSON.

## 11. Allocation contract

### 11.1 `r1_plan.plan_allocation`

Columns:

```text
allocation_id             UUID PK
plan_revision_id          UUID NOT NULL FK -> plan_revision ON DELETE CASCADE
requirement_id            TEXT NOT NULL
resource_kind             TEXT NOT NULL
resource_key              TEXT NOT NULL
plan_node_id              UUID NULL FK -> plan_node
allocation_mode           TEXT NOT NULL
allocation_quantity       NUMERIC NULL
evidence_refs_json        JSONB NOT NULL DEFAULT []
ordinal                   INTEGER NOT NULL
UNIQUE (plan_revision_id, requirement_id, resource_kind, resource_key, plan_node_id)
UNIQUE (plan_revision_id, ordinal)
```

Allowed `allocation_mode`:

- `exclusive`
- `shared`
- `capacity`

Mandatory partial unique constraint:

```text
UNIQUE (plan_revision_id, resource_kind, resource_key)
WHERE allocation_mode = 'exclusive'
```

This prevents the same exclusive scarce resource being credited twice.

Shared/capacity allocation ceilings are mechanics/programme semantics and remain evaluator-enforced because allowable sharing varies by resource; do not encode one global sharing ratio into SQL.

## 12. Immutable assessment snapshots

### 12.1 `r1_plan.plan_assessment`

Production persistence is allowed only for assessments tied to durable player workflow:

- saved/selected plan;
- Build Pack snapshot;
- later observed Plan Audit.

Ordinary Finder result assessments remain ephemeral. Golden/calibration research outputs should normally remain deterministic repo/CI artifacts rather than production DB rows.

Columns:

```text
assessment_id                 UUID PK
plan_revision_id              UUID NOT NULL FK -> plan_revision ON DELETE CASCADE
assessment_kind               TEXT NOT NULL
system_id64                   BIGINT NOT NULL
programme_id                  TEXT NOT NULL
programme_revision            TEXT NOT NULL
model_revision_id             TEXT NOT NULL FK -> r1_meta.model_revision
mechanics_revision_id         TEXT NOT NULL FK -> r1_meta.mechanics_revision
canonical_generation_id       BIGINT NOT NULL
evidence_snapshot_sha256      CHAR(64) NOT NULL
candidate_plan_sha256         CHAR(64) NOT NULL
carrier_mode                  TEXT NOT NULL
assessment_state              TEXT NOT NULL
evidence_disposition          TEXT NOT NULL
reserve_capacity              TEXT NULL
logistics_state               TEXT NULL
plan_pair_resilience          TEXT NULL
plan_fit                      SMALLINT NULL
fit_policy_revision           TEXT NULL
result_sha256                 CHAR(64) NOT NULL
trace_json                    JSONB NOT NULL
created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (result_sha256)
FK (programme_id, programme_revision) -> r1_meta.programme_revision
```

Allowed `assessment_kind` initial production set:

- `saved_plan`
- `build_pack`
- `plan_audit`

Allowed `assessment_state`:

- `not_assessable`
- `not_supported`
- `conditionally_supported`
- `supported`

Allowed `evidence_disposition`:

- `sufficient`
- `partial`
- `missing`
- `ambiguous`
- `conflicting`

Allowed `plan_pair_resilience`:

- NULL when the programme does not define a pair outcome;
- `robust`
- `fragile`
- `mixed`
- `unknown`

`plan_fit` constraints:

- NULL for `not_assessable` and `not_supported`;
- 0..100 when present;
- Conditional fit may be present only if the accepted fit-policy revision permits it;
- no SQL ordering rule allows Conditional to outrank Supported solely by `plan_fit`.

Indexes:

```text
(plan_revision_id, created_at DESC)
(system_id64, programme_id, programme_revision, created_at DESC)
(assessment_kind, created_at DESC)
```

Do not create a global Plan Fit leaderboard index.

`trace_json` is the byte/deterministically canonicalizable full evaluator output, including requirement traces, conditions, evidence refs, allocations, dimensions, and strategy trace. `result_sha256` is computed from that deterministic result contract.

## 13. `r1_assessment_condition` decision

Do **not** create a separate condition table in the first persistence migration.

Conditions remain inside immutable `plan_assessment.trace_json` because:

- Finder assessments are not persisted;
- saved-plan assessment counts are small;
- the UI receives the whole trace together;
- relational condition analytics are not yet a proven requirement.

If later product/analytics work genuinely needs cross-assessment condition queries, add a derived/index table then. Do not prematurely normalize every trace node.

## 14. Existing Evidence Store boundary

Reuse `evidence_records` for imported/manual/observational evidence that does not belong in immutable canonical V3. Reuse source-run/provenance machinery where applicable.

Do not use generic Evidence Store JSON rows as substitutes for:

- explicit canonical body subtype;
- the 198M-row typed capability cache;
- saved plan/node/allocation relational identity;
- immutable assessment revision binding.

No R1 table duplicates the normalized V3 source/run/provenance hierarchy.

## 15. Persistence matrix

| Object | Normal Finder | Open result | Save/select plan | Build Pack | Later audit |
|---|---:|---:|---:|---:|---:|
| Search comparison context | ephemeral | ephemeral | copied into plan semantics | referenced | referenced |
| Candidate plan | ephemeral | ephemeral | persisted as plan revision | persisted | persisted |
| Candidate assessment | ephemeral | ephemeral | persisted when saving if required | persisted | persisted |
| Canonical body facts | read only | read only | referenced by snapshot/identity | referenced | compared |
| Capability cache | read only | read only | not copied | not copied | not copied |

A normal Finder search must remain zero-write.

## 16. Retention / privacy

- model/mechanics/programme/capability-generation metadata: retain indefinitely; rows are tiny and needed for provenance;
- capability physical data: current + immediate previous successful generation through rollback; older physical data may be dropped after acceptance while metadata/receipts remain;
- saved plan/revisions/nodes/allocations/assessments: retained until account/user deletion policy removes them or the user explicitly deletes the project;
- deleting a saved plan cascades its private revisions/nodes/allocations/assessments;
- no public/shared plan semantics in initial schema;
- research EDSM overlays are artifacts, not persistent production R1 plan/capability rows.

## 17. Tables deliberately not created

Still prohibited:

- `r1_ratings`
- `r1_economy_scores`
- `r1_system_value`
- per-system/per-programme Plan Fit materialization
- system-level pair resilience
- R1 copy of every body
- persistent ordinary search/candidate rows
- persistent comparison-context history
- condition table in initial migration
- any legacy/v4 fallback bridge table.

## 18. Migration stage order once separately authorised

A future schema implementation stage must be split so the high-risk galaxy cache cannot accidentally arrive with user-state tables unreviewed:

1. create only `r1_meta` registries/schemas;
2. add canonical body-subtype correction to the **next V3 generation contract**, not retained generation;
3. create `r1_cache` logical surface and capability-generation machinery with an empty/unpublished state;
4. create `r1_plan` saved-plan/revision/node/allocation/assessment tables;
5. run schema/constraint tests only;
6. no capability backfill yet;
7. separately review/authorise the first capability build;
8. build shadow capability generation;
9. validate on real golden/control systems and broad samples;
10. separately authorise publication into Finder.

No migration step changes current Finder ranking or removes legacy tables.

## 19. Review-2 acceptance invariants

Before any migration is authorised, the schema contract must satisfy all of these:

1. body subtype is canonical upstream, not an R1 inference table;
2. Ammonia atmosphere cannot become Ammonia World identity;
3. HMC + geo + bio + ring + TF remain composable facts;
4. Unknown remains representable in capability summaries;
5. capability rows contain no purpose-specific score/outcome;
6. fit-policy changes alone do not force a 198M-row capability rebuild;
7. capability generations are immutable and atomically published/rollbackable;
8. normal Finder is zero-write;
9. unsaved candidate plans are ephemeral;
10. saved plan edits create immutable revisions;
11. durable plan body references do not trust generation-local `body_pk` alone;
12. exclusive allocations cannot be double-credited;
13. pair resilience belongs only to a concrete plan assessment;
14. Unsupported/Not Assessable cannot receive fake numeric zero Plan Fit;
15. assessment result is bound to programme/model/mechanics/canonical generation/evidence snapshot/candidate plan;
16. conditions can remain inside deterministic trace initially;
17. user plan state is private by default;
18. no legacy/v4 fallback enters the R1 schema;
19. no tables are created until a separate migration-stage authorisation.

## 20. Decision after Review 2

If this Review 2 is accepted, the next schema action is **not** an immediate galaxy backfill.

The next authorised code/migration slice should create only the structural metadata/plan/cache-shell schema and tests, leaving the capability cache unpublished and empty. The first 198M-system capability build remains a separately reviewed and explicitly authorised operation after the canonical subtype source is solved.
