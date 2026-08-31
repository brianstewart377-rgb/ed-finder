# ED-Finder R1 — Real Evidence Bridge
## Review 1 — Stage Definition

Date: 2026-08-31  
Status: **pre-code Review 1; no implementation authorised yet**  
Branch: `chatgpt-ed-new-ops-requests`  
Previous completed stage: `docs/research/r1-finder-comparison-proof-completion-2026-08-31.md`

## 1. Stage objective

Bridge real ED-Finder canonical system/body evidence into the new R1 `CandidateEvidence` contract without wiring R1 ranking into production Finder yet.

The stage exists to prove that the semantic model that passed the fixture-only Finder comparison proof can consume realistic ED-Finder evidence while preserving:

- composable body identity + modifiers;
- Unknown vs false/absent;
- source/provenance boundaries;
- direct facts vs derived predictions;
- current-patch slot semantics;
- deterministic evidence snapshots;
- the same assessment semantics already proven by `r1_finder_compare`.

The desired bounded flow is:

```text
canonical system/body/ring projection
+ evidence-store provenance/freshness where appropriate
        ↓
R1 canonical body facts
        ↓
R1 derived feasibility facts
        ↓
CandidateEvidence
        ↓
existing isolated Finder comparison evaluator
```

This is a data/evidence bridge stage, not a new scoring stage.

## 2. Product-redesign principle remains binding

V2 is evidence and history, not the target architecture.

This bridge must not attempt to recreate old ratings columns, body-count aggregates, or legacy search semantics merely because those fields already exist. Existing data may be reused only where its meaning survives the new evidence/mechanics review.

Feature parity remains explicitly out of scope.

## 3. Existing evidence architecture we can reuse carefully

The repo already has an Evidence Store with generic records carrying:

- evidence key;
- source name and origin;
- subject type/id;
- evidence type;
- lifecycle/freshness status;
- confidence label;
- observed/collected/expiry timestamps;
- generic `value` and `provenance` objects.

This is useful provenance plumbing but it is not automatically the canonical R1 body model.

The Evidence Store source catalog explicitly distinguishes:

- `canonical_app_data` — lifecycle-managed evidence promotions from already-ingested canonical tables;
- Spansh/EDDN canonical/source-of-truth feeds;
- EDSM and other secondary evidence sources;
- future first-party Frontier Journal observations.

Therefore the bridge must project explicit facts into R1 rather than passing arbitrary evidence `value` blobs directly into assessment.

## 4. Important current Evidence Store limitation

The current canonical-promotion path in `evidence_store/store.py` allows these promoted evidence types:

```text
body_completeness
station_set
colonisation_status
ring_composition
```

It does **not** establish first-class R1 facts for every environmental property required by the new model, such as:

- surface temperature;
- gravity;
- atmosphere;
- volcanism;
- terraformability;
- tidal lock;
- exact canonical body identity;
- per-body geological/biological presence.

So this stage must not assume that "the Evidence Store has the system" means "R1 has complete body evidence".

## 5. Source hierarchy for this bridge

For the first bridge proof, use this precedence conceptually:

### A. Canonical app body/system/ring projection

Use explicitly projected canonical fields from the already-ingested ED-Finder system/body/ring data model.

These form the baseline factual representation where field semantics are known.

### B. Evidence Store lifecycle/provenance

Use Evidence Store records to enrich:

- source identity;
- freshness/lifecycle;
- promoted completeness/ring evidence;
- explicit observation/import provenance.

Do not use a generic confidence label as a substitute for field-level availability/truth.

### C. Direct observation / journal evidence

Not implemented in this stage, but the adapter contract must leave room for later first-party observations to coexist with imported facts without silently rewriting mechanics.

## 6. Canonical fact projection rules to lock

The bridge must produce `BodyFact`-equivalent facts with independent/composable properties.

### Exact identity

Base identity remains a single canonical body identity, e.g.:

```text
High metal content world
Rocky body
Metal-rich body
Water world
Ammonia world
```

Do not create replacement pseudo-types such as `hmc_geo` or `rocky_mixed`.

### Modifiers remain independent

Keep separate fields for:

- rings;
- geological presence;
- biological presence;
- terraformability;
- volcanism;
- atmosphere;
- tidal lock;
- landability;
- temperature;
- gravity;
- radius;
- distance.

### Geologicals vs volcanism

These remain distinct. One must never be inferred solely from the other.

### Ammonia identity

Only exact canonical `Ammonia world` identity counts as a true Ammonia World.

A gas giant with ammonia-based life remains a gas giant with that characteristic and must not populate the true-Ammonia identity.

### Signals

Raw signal count may be retained as evidence metadata, but body-local mechanic predicates use presence unless an accepted mechanic explicitly requires count.

### Unknown

Missing/null/untrusted values remain Unknown. Do not coerce to false, zero, no-atmosphere, no-volcanism, Pristine, or any other default.

## 7. Physical-feasibility projection

This stage should project bounded feasibility facts only when their required inputs are known.

### Surface slots

Use the validated versioned community/Raven-family surface-slot prediction as the current prediction model where inputs are sufficient:

- landable;
- temperature <= 700 K;
- gravity <= 2.7 g;
- radius bands 1500 / 3750 / 6000 km;
- HMC +1;
- terraformable +1;
- geologicals OR volcanism +1;
- atmosphere +2;
- cap 7.

Prediction provenance must identify the model/revision and remain distinct from an observed Architect slot count.

If a material required input is Unknown, predicted surface capacity is Unknown rather than guessed.

Keep the two historical +1 residuals as documented model uncertainty; do not add hidden correction constants.

### Orbital slots

Do not reuse the stale generic topology estimator as authoritative current capacity.

At minimum, current-patch gas giant capacity must respect the one-construction-slot rule.

Rare/unverified orbital edges may remain Unknown in this stage.

## 8. Evidence-disposition mapping

The adapter must calculate R1 availability/disposition from explicit facts, not from old Ratings confidence.

Conceptual mapping:

- `sufficient` — all material fields for the bounded claim are explicitly available and non-conflicting;
- `partial` — useful facts exist but a non-blocking field is missing;
- `missing` — required evidence absent;
- `ambiguous` — source semantics do not establish one interpretation;
- `conflicting` — direct source facts disagree materially.

Freshness is a separate provenance/lifecycle attribute. Fresh-but-incomplete is still incomplete.

## 9. Bounded real/golden systems for bridge validation

Review 2 should define a small snapshot corpus from existing known controls rather than attempting a galaxy-wide integration immediately.

Preferred semantic coverage:

- **HR 1188** — genuine HMC/Metal-Rich Extraction positive;
- **Brambai DL-Y g32** — ammonia-life gas giant vs true-Ammonia regression;
- **Eorgh Prou AA-A h24** — true Ammonia World positive;
- **Blu Thua SU-W c2-5** — remote-material distance/logistics stress;
- **HIP 294** — Water-World + stale/provenance control;
- **one no/partial-body-data control** — must remain Unknown rather than zero.

If exact raw snapshots for any named control are not safely available, Review 2 may substitute a deterministic captured canonical projection with the same regression role. Do not fabricate a real-system observation.

## 10. Core output of the bridge

The adapter should return two clearly separated artifacts:

### Canonical projected system evidence

Contains normalized body facts plus provenance/availability metadata.

### R1 CandidateEvidence

Contains only the bounded assessment-ready projection required by the existing comparison proof.

This separation matters so future programmes can reuse canonical facts without inheriting Extraction/ER-specific assumptions.

## 11. No hidden scorer reuse

The bridge must not read or reuse as R1 evidence:

- legacy `ratings.score*` values;
- `economy_suggestion`;
- v4/archetype scores;
- `overall_development_potential`;
- topology `ground_synergy` / `orbital_synergy` as physical capacity;
- topology `strong_link_potential` as observed link evidence;
- topology `weak_link_stability` as a mechanic fact;
- stale estimated gas-giant 3/5 orbital slots.

Existing fields may be inspected for regression comparison only.

## 12. Read-only implementation boundary

The implementation stage should remain shadow/read-only.

No:

- migration;
- DB write;
- Evidence Store mutation;
- Ratings/archetype rebuild;
- production Finder ordering change;
- frontend search change;
- public API contract change;
- deployment.

The pure projection core should accept pre-fetched row/record dictionaries so the semantic adapter can be tested independently from DB access.

A separate read-only loader may be permitted in Review 2 if needed for bounded snapshot extraction, but it must not become part of the pure projection logic.

## 13. Expected implementation surfaces

Review 2 should determine exact paths after repository inspection, but the preferred architecture is a new isolated adapter package rather than modifying legacy classifiers.

Conceptually:

```text
apps/api/src/r1_evidence_bridge/
    types.py
    body_projection.py
    provenance.py
    slot_prediction.py
    candidate_projection.py
```

Tests should live in the normal root `tests/` convention.

The existing `r1_finder_compare` proof package should be consumed as the downstream contract rather than duplicated.

## 14. Audit-only existing surfaces

At minimum these should remain read-only in the first bridge implementation unless Review 2 explicitly narrows a justified change:

```text
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

## 15. Required bridge invariants

Review 2 must turn these into exact tests:

1. geo-HMC remains HMC + geological;
2. ring+geo rocky remains rocky + ring + geo;
3. terraformable survives identity classification;
4. geologicals and volcanism remain independently representable;
5. true Ammonia World is exact-identity only;
6. ammonia-life gas giant never becomes true Ammonia World;
7. raw signal count does not multiply body-local modifier semantics;
8. missing fields remain Unknown;
9. no-body data remains Unknown, not zero/complete;
10. surface-slot prediction returns Unknown when a required field is unavailable;
11. surface-slot exact thresholds are regression-tested;
12. gas giant current-patch one-slot rule is protected;
13. prediction provenance is not labelled observation;
14. evidence freshness cannot convert missing evidence into sufficient evidence;
15. identical normalized source evidence yields deterministic snapshot IDs;
16. downstream `r1_finder_compare` receives the same `CandidateEvidence` contract it already tests.

## 16. Review 1 acceptance criteria

This stage definition is accepted if:

- the next bridge is understood as evidence projection, not scoring redesign;
- canonical body facts are explicit/composable;
- Evidence Store is provenance/lifecycle plumbing rather than an automatic truth blob;
- current known mechanics corrections are preserved;
- Unknown remains first-class;
- the implementation remains shadow/read-only;
- the existing Finder comparison proof remains the downstream semantic contract;
- Review 2 will define exact source row contracts, adapter types, golden snapshots, tests, and allowed files before coding.

## 17. Review 2 requested output

The next pre-code review must define:

- exact raw/canonical input row schema accepted by the adapter;
- exact projected body/system evidence types;
- field-by-field source/availability mapping;
- exact ring-source handling;
- exact surface-slot prediction type/provenance contract;
- bounded orbital-capacity contract for the first slice;
- exact no-body/partial-body behavior;
- golden snapshot IDs/roles;
- exact downstream CandidateEvidence mapping for Extraction and P-ER-01;
- deterministic hashing/ordering rules;
- exact allowed file list;
- exact automated tests;
- explicit no-write/no-production-wiring confirmation.
