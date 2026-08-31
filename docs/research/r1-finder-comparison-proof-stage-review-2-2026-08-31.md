# ED-Finder R1 — Finder Comparison Proof Stage
## Review 2 — Final Pre-Code Technical Contract

Date: 2026-08-31  
Status: **final pre-code Review 2; coding may begin only inside this contract after owner acceptance**  
Branch: `chatgpt-ed-new-ops-requests`  
Review 1: `docs/research/r1-finder-comparison-proof-stage-review-1-2026-08-31.md`  
Upstream R1 contract: `docs/research/r1-ratings-vnext-contract-review-2-2026-08-31.md`

## 1. Stage objective

Build one isolated, fixture-backed proof that Finder-style candidate search and R1 assessment can use one semantic engine without introducing a universal score.

The proof must support exactly three comparison contexts over the same deterministic candidate list:

1. `facts_only`
2. `role_extraction_v1`
3. `programme_p_er_01_v1`

This stage does **not** touch the real Finder query path, production API, database, migrations, frontend search UI, legacy ratings or archetype outputs.

The stage proves only:

```text
candidate factual evidence
+ factual filters
+ explicit comparison context
        ↓
context-bound assessment
        ↓
assessment-state precedence
        ↓
optional provisional Plan Fit
        ↓
deterministic result ordering
        ↓
deterministic search-to-detail handoff
```

## 2. Final allowed-file list

Only the following implementation files may be created/changed in this stage:

```text
apps/api/src/r1_finder_compare/__init__.py
apps/api/src/r1_finder_compare/types.py
apps/api/src/r1_finder_compare/fixtures.py
apps/api/src/r1_finder_compare/evidence.py
apps/api/src/r1_finder_compare/programmes.py
apps/api/src/r1_finder_compare/evaluator.py
apps/api/src/r1_finder_compare/search_compare.py
tests/test_r1_finder_compare.py
docs/research/r1-finder-comparison-proof-completion-2026-08-31.md
```

The following are audit-only and must not change:

```text
apps/api/src/local_search.py
apps/api/src/search_economies.py
apps/api/src/domain/colonisation_rules.py
apps/api/src/domain/economy_state.py
apps/api/src/domain/placements.py
frontend/src/features/search/useSearch.ts
frontend/src/features/search/SearchForm.tsx
frontend/src/features/search/SearchFormControls.tsx
frontend/src/features/search/searchFormConfig.ts
```

Any need to edit an audit-only file is a scope break requiring a new pre-code review.

## 3. Source-boundary contract

The implementation must be pure and fixture-backed.

Forbidden imports/dependencies:

- PostgreSQL / psycopg / asyncpg;
- Redis;
- FastAPI route objects;
- network clients;
- `build_ratings`;
- `build_archetype_scores`;
- `build_topology`;
- `search_economies`;
- `local_search`;
- legacy ratings models/score helpers;
- archetype ranking helpers;
- current `domain/economy_state.py` scoring logic;
- current `domain/placements.py` slot truth;
- browser/frontend runtime dependencies.

Standard-library-only implementation is preferred for this proof.

## 4. Exact enums and IDs

```python
AssessmentState = Literal[
    'not_assessable',
    'not_supported',
    'conditionally_supported',
    'supported',
]

EvidenceDisposition = Literal[
    'sufficient',
    'partial',
    'missing',
    'ambiguous',
    'conflicting',
]

CarrierMode = Literal[
    'no_carrier',
    'carrier_available',
    'compare_both',
]

ComparisonContextId = Literal[
    'facts_only',
    'role_extraction_v1',
    'programme_p_er_01_v1',
]

CapacityState = Literal[
    'none',
    'viable',
    'sufficient',
    'resilient',
    'expandable',
]

LogisticsState = Literal[
    'compact',
    'moderate',
    'spread',
    'extreme',
]

PairStability = Literal[
    'robust',
    'fragile',
    'mixed',
    'unknown',
]

CarrierDependence = Literal[
    'carrier_independent',
    'carrier_helped',
    'carrier_dependent',
]
```

Strategy ID for this stage only:

```text
balanced_geometric_v1
```

This is explicitly a **product/laboratory comparison policy**, not an Elite mechanic.

## 5. Canonical body/evidence shape for the fixture proof

The implementation must not collapse identity and modifiers into replacement buckets.

```python
@dataclass(frozen=True)
class BodyFact:
    body_id: str
    name: str
    base_identity: str
    distance_ls: float | None
    is_landable: bool | None
    is_terraformable: bool | None
    has_rings: bool | None
    has_geologicals: bool | None
    has_biologicals: bool | None
    has_volcanism: bool | None
    atmosphere_present: bool | None
    tidal_locked: bool | None
    surface_temperature_k: float | None
    surface_gravity_g: float | None
    radius_km: float | None
```

Required invariants:

- HMC + geological remains HMC **and** geological.
- Rocky + ring + geological remains Rocky **and** ringed **and** geological.
- `has_geologicals` and `has_volcanism` are independent fields.
- raw signal counts are deliberately absent from the scoring contract in this proof.
- true Ammonia World / ammonia-life handling is not needed for ER scoring, but no loose substring classifier may be introduced.

Evidence wrapper:

```python
@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    disposition: EvidenceDisposition
    source_kind: str
    source_id: str
    source_revision: str | None
    evidence_class: str

@dataclass(frozen=True)
class CandidateEvidence:
    evidence: tuple[EvidenceRef, ...]
    material_evidence_ids: tuple[str, ...]
```

All tuples must be stored and serialised in deterministic lexical order.

## 6. Candidate fixture shape

```python
@dataclass(frozen=True)
class CandidateSystem:
    system_id64: str
    name: str
    distance_ly: float | None
    bodies: tuple[BodyFact, ...]
    evidence: CandidateEvidence

    extraction_capacity: CapacityState
    refinery_capacity: CapacityState
    placement_capacity: CapacityState

    pair_stability: PairStability
    pair_stability_evidence: EvidenceDisposition

    logistics_no_carrier: LogisticsState
    logistics_with_carrier: LogisticsState
    carrier_dependence: CarrierDependence

    allocation_conflict: bool
    allocation_notes: tuple[str, ...]

    reserve_capacity: CapacityState
```

`extraction_capacity`, `refinery_capacity`, `placement_capacity`, `pair_stability`, logistics and allocation facts are fixture-declared derived facts for this semantic proof. The stage is **not** authorised to invent production mechanics to calculate them from the body rows.

Body rows exist to prove composable identity/modifier handling and factual summaries.

## 7. Exact fixture candidate list

The fixture registry must contain exactly these seven IDs in this stage:

```text
compact_er_specialist
remote_extraction_abundance
geo_hmc_composable
refinery_heavy_weak_extraction
incomplete_evidence_candidate
plateau_sufficient_base
plateau_surplus_twin
```

### 7.1 `compact_er_specialist`

Purpose: primary positive control.

Facts:

- distance: 42 ly;
- bodies: 3 HMC, 1 Metal-Rich, 2 Rocky; one HMC has geologicals;
- all material evidence sufficient;
- Extraction capacity: `resilient`;
- Refinery capacity: `sufficient`;
- placement capacity: `sufficient`;
- pair stability: `robust`, evidence sufficient;
- no-carrier logistics: `compact`;
- carrier logistics: `compact`;
- carrier dependence: `carrier_independent`;
- no allocation conflict;
- reserve: `resilient`.

Expected:

- Extraction role: `supported`;
- P-ER-01: `supported`.

### 7.2 `remote_extraction_abundance`

Purpose: prove raw abundance does not automatically beat practical support.

Facts:

- distance: 118 ly;
- bodies: 8 HMC, 3 Metal-Rich, 3 Rocky;
- all material evidence sufficient;
- Extraction capacity: `expandable`;
- Refinery capacity: `resilient`;
- placement capacity: `sufficient`;
- pair stability: `robust`, evidence sufficient;
- no-carrier logistics: `extreme`;
- carrier logistics: `moderate`;
- carrier dependence: `carrier_helped`;
- no allocation conflict;
- reserve: `expandable`.

Expected:

- Extraction role/no carrier: `supported` but lower Plan Fit than compact specialist;
- Extraction role/carrier: `supported`, logistics improves;
- P-ER-01/no carrier: `supported` but lower Plan Fit than compact specialist;
- reserve may exceed compact specialist without forcing higher fixed-programme fit.

### 7.3 `geo_hmc_composable`

Purpose: monotonicity/composability regression.

Facts:

- distance: 55 ly;
- bodies: 3 HMC, all three geological;
- all material evidence sufficient;
- Extraction capacity: `sufficient`;
- Refinery capacity: `viable`;
- placement capacity: `sufficient`;
- pair stability: `fragile`, evidence sufficient;
- logistics: `compact` in both carrier modes;
- carrier dependence: `carrier_independent`;
- no allocation conflict;
- reserve: `sufficient`.

Expected:

- Extraction role: `supported`;
- P-ER-01: `conditionally_supported` because pair is fragile;
- all three bodies retain HMC identity and geological modifier.

### 7.4 `refinery_heavy_weak_extraction`

Purpose: role/programme ordering divergence.

Facts:

- distance: 36 ly;
- bodies: 7 Rocky, 1 HMC;
- material evidence sufficient;
- Extraction capacity: `viable`;
- Refinery capacity: `expandable`;
- placement capacity: `sufficient`;
- pair stability: `mixed`, evidence sufficient;
- logistics: `compact`;
- carrier dependence: `carrier_independent`;
- no allocation conflict;
- reserve: `resilient`.

Expected:

- Extraction role: `conditionally_supported` (`viable` only);
- P-ER-01: `not_supported` because target pair is mixed and Extraction side is insufficient for full programme support.

### 7.5 `incomplete_evidence_candidate`

Purpose: material unknown/conflict gate.

Facts:

- distance: 28 ly;
- bodies: 5 HMC, 2 Rocky;
- at least one material capacity evidence record `missing`;
- pair stability: `unknown`, pair evidence `missing`;
- capacities may look promising but are not trusted;
- logistics: `compact`;
- no allocation conflict.

Expected:

- Extraction role: `not_assessable`;
- P-ER-01: `not_assessable`;
- no Plan Fit.

### 7.6 `plateau_sufficient_base`

Purpose: first half of surplus plateau test.

Facts:

- distance: 70 ly;
- exactly enough declared ER capability for full support;
- Extraction capacity: `sufficient`;
- Refinery capacity: `sufficient`;
- placement capacity: `sufficient`;
- pair stability: `robust`, evidence sufficient;
- logistics: `moderate`;
- carrier dependence: `carrier_independent`;
- no allocation conflict;
- reserve: `sufficient`.

Expected P-ER-01: `supported`.

### 7.7 `plateau_surplus_twin`

Purpose: prove irrelevant surplus does not increase fixed-programme Plan Fit.

Facts must match `plateau_sufficient_base` for every fit-driving field, but include at least 30 additional irrelevant bodies and reserve `expandable`.

Expected:

- same P-ER-01 assessment state;
- **exact same P-ER-01 Plan Fit** under `balanced_geometric_v1`;
- better reserve allowed and displayed separately.

## 8. Factual filters contract

This proof only needs these filters:

```python
@dataclass(frozen=True)
class FactualSearchFilters:
    max_distance_ly: float | None = None
    min_hmc: int | None = None
    min_metal_rich: int | None = None
    require_geological_body: bool = False
```

Filters operate only on factual body identity/modifier counts and candidate distance.

They do not alter assessment semantics or fit.

## 9. Comparison-context request shape

```python
@dataclass(frozen=True)
class SearchComparisonRequest:
    factual_filters: FactualSearchFilters
    comparison_context_id: ComparisonContextId
    carrier_mode: CarrierMode = 'no_carrier'
    strategy_id: str | None = None
```

Validation rules:

- `facts_only` requires `strategy_id is None`;
- `facts_only` ignores carrier mode for ordering/output;
- role/programme contexts may run without a strategy and then return state-grouped factual ordering only;
- only `balanced_geometric_v1` is accepted as a strategy in this stage;
- unknown context/strategy IDs raise `ValueError` at the pure-domain boundary;
- `compare_both` yields two scenario assessments per candidate in fixed order: `no_carrier`, then `carrier_available`.

## 10. Requirement/state rules — Extraction role

`role_extraction_v1` means:

> Compare systems for credible pre-build Extraction support only. Do not infer Refinery or any other second economy.

Material requirements:

1. material evidence is assessable;
2. Extraction capacity is at least `viable`;
3. placement capacity is at least `viable`;
4. logistics state is known.

State rules, applied in this order:

### `not_assessable`

If any material evidence disposition is `missing`, `ambiguous` or `conflicting` for a required claim.

### `not_supported`

If Extraction capacity = `none` or placement capacity = `none`.

### `conditionally_supported`

If either Extraction capacity or placement capacity = `viable` but not `sufficient`.

### `supported`

If Extraction and placement are each `sufficient`, `resilient` or `expandable` and material evidence is sufficient/partial without a blocking unresolved claim.

`partial` evidence may remain Supported only when no material hard claim depends on the partial field; otherwise it emits a condition and becomes Conditional.

## 11. Requirement/state rules — P-ER-01

`programme_p_er_01_v1` target:

> Extraction and Refinery are the intended top-two programme pair in either order.

Material requirements:

1. evidence assessable;
2. Extraction capacity at least `sufficient`;
3. Refinery capacity at least `sufficient`;
4. placement capacity at least `sufficient`;
5. no allocation conflict;
6. pair stability evidence assessable;
7. pair stability not `mixed`;
8. logistics known.

State rules in this order:

### `not_assessable`

- material evidence missing/ambiguous/conflicting; or
- pair stability = `unknown`; or
- pair-stability evidence missing/ambiguous/conflicting.

### `not_supported`

- allocation conflict; or
- Extraction capacity `none`/`viable`; or
- Refinery capacity `none`/`viable`; or
- placement capacity `none`/`viable`; or
- pair stability = `mixed`.

### `conditionally_supported`

- pair stability = `fragile`; or
- a carrier-sensitive logistics condition is required for the selected scenario; or
- another explicit non-blocking material condition remains.

### `supported`

- Extraction/Refinery/placement are each at least `sufficient`;
- pair stability = `robust`;
- no allocation conflict;
- no unresolved material condition.

No guessed percentage buffer may be calculated.

## 12. Capacity scoring policy for provisional Plan Fit

This is product/lab policy only.

For fixed-plan fit, surplus above `sufficient` does **not** keep increasing the capability dimension.

```python
CAPACITY_FIT = {
    'none': 0,
    'viable': 70,
    'sufficient': 100,
    'resilient': 100,
    'expandable': 100,
}
```

Reserve state remains separately visible, so `resilient`/`expandable` still matter to the player without distorting fixed-plan fit.

Logistics mapping for this proof:

```python
LOGISTICS_FIT = {
    'compact': 100,
    'moderate': 85,
    'spread': 65,
    'extreme': 40,
}
```

These values are **not Elite mechanics** and must be labelled in trace metadata as `product_policy`.

## 13. Pair stability fit policy

For P-ER-01 only:

```python
PAIR_FIT = {
    'robust': 100,
    'fragile': 70,
}
```

`mixed` and `unknown` are ineligible for Plan Fit because their assessment states are `not_supported` / `not_assessable`.

Again, this is product/lab policy, not a mechanic percentage.

## 14. Provisional fit formula

Strategy `balanced_geometric_v1` uses an unweighted geometric mean so one weak dimension cannot be fully hidden by abundance elsewhere.

### Extraction role

Dimensions:

```text
Extraction capacity fit
Placement capacity fit
Logistics fit
```

Formula:

```python
plan_fit = round((extraction_fit * placement_fit * logistics_fit) ** (1 / 3))
```

### P-ER-01

Dimensions:

```text
Extraction capacity fit
Refinery capacity fit
Placement capacity fit
Pair stability fit
Logistics fit
```

Formula:

```python
plan_fit = round(
    (extraction_fit * refinery_fit * placement_fit * pair_fit * logistics_fit) ** (1 / 5)
)
```

Rules:

- `plan_fit` is absent for `not_supported` and `not_assessable`;
- `plan_fit` may be present for `conditionally_supported`, but state precedence always wins ordering;
- only state-eligible fit-driving dimensions participate;
- evidence disposition is a gate/condition, not a numeric bonus;
- raw body count never appears directly in the formula;
- reserve never appears directly in the formula;
- all dimension values and policy mappings appear in the trace.

## 15. Carrier rules

Carrier mode changes only logistics-sensitive outputs.

For `no_carrier`, use `logistics_no_carrier`.

For `carrier_available`, use `logistics_with_carrier`.

Carrier mode must not change:

- body facts;
- evidence records;
- evidence snapshot ID;
- Extraction/Refinery/placement capacity;
- pair stability;
- allocation conflict;
- reserve;
- composable identity/modifier facts.

A carrier can therefore raise/lower Plan Fit only through the logistics dimension and may remove/add a logistics condition where the fixture contract allows it.

## 16. Evidence snapshot

Canonical evidence snapshot input:

```text
candidate system ID
candidate fixture revision
sorted body facts
sorted evidence records
fit-independent derived facts:
  extraction_capacity
  refinery_capacity
  placement_capacity
  pair_stability
  allocation_conflict
  reserve_capacity
```

Carrier mode and strategy ID are deliberately **excluded**.

Digest:

```text
sha256:<lowercase hex>
```

The same candidate must have the same evidence snapshot across:

- facts-only;
- Extraction role;
- P-ER-01;
- no-carrier / carrier-available;
- with/without strategy.

## 17. Search result shape

```python
@dataclass(frozen=True)
class SearchCandidateResult:
    system_id64: str
    system_name: str
    distance_ly: float | None
    comparison_context_id: ComparisonContextId
    carrier_mode: str | None
    evidence_snapshot_id: str

    assessment_state: AssessmentState | None
    conditions: tuple[str, ...]
    evidence_disposition: EvidenceDisposition | None

    reserve_capacity: CapacityState | None
    logistics: LogisticsState | None
    carrier_dependence: CarrierDependence | None

    plan_fit: int | None
    candidate_plan_id: str | None
    trace: tuple[tuple[str, str], ...]
```

For `facts_only`:

- `assessment_state = None`;
- `plan_fit = None`;
- `candidate_plan_id = None`;
- conditions empty;
- output remains factual.

## 18. Candidate plan / handoff ID

For programme context only, create deterministic candidate-plan ID from:

```text
programme context ID
programme revision
system ID64
evidence snapshot ID
carrier scenario
```

Format:

```text
r1plan:<first-24-hex-of-sha256>
```

The handoff must preserve:

- context/programme ID and revision;
- candidate plan ID;
- evidence snapshot ID;
- carrier scenario;
- base assessment state;
- conditions;
- deterministic allocation/evidence trace.

Re-evaluating the handoff must reproduce those fields exactly.

## 19. Ordering contract

State precedence rank:

```python
STATE_ORDER = {
    'supported': 0,
    'conditionally_supported': 1,
    'not_supported': 2,
    'not_assessable': 3,
}
```

### `facts_only`

Sort key:

```text
distance known before unknown
distance ascending
name casefold lexical
id64 lexical
```

### Role/programme without strategy

Sort key:

```text
assessment state precedence
distance known before unknown
distance ascending
name
id64
```

### Role/programme with `balanced_geometric_v1`

Sort key:

```text
assessment state precedence
plan_fit descending within supported/conditional groups only
distance known before unknown
distance ascending
name
id64
```

A Conditional 100 can never outrank a Supported 1.

Unsupported/not-assessable results have `plan_fit=None`.

## 20. Exact test list

`tests/test_r1_finder_compare.py` must contain at least these named tests:

```text
test_facts_only_has_no_assessment_or_plan_fit
test_facts_only_uses_deterministic_factual_order
test_extraction_role_does_not_infer_refinery_pair
test_p_er_01_uses_explicit_pair_contract
test_supported_precedes_conditional_even_when_conditional_fit_is_higher
test_unsupported_and_not_assessable_have_no_plan_fit
test_geo_hmc_preserves_hmc_identity_and_geological_modifier
test_geological_modifier_never_replaces_hmc_identity
test_raw_body_surplus_does_not_raise_fixed_programme_fit
test_plateau_twins_have_identical_p_er_01_fit
test_plateau_surplus_twin_can_have_better_reserve_without_better_fit
test_remote_abundance_loses_to_compact_support_without_carrier
test_carrier_changes_only_logistics_sensitive_outputs
test_carrier_does_not_change_evidence_snapshot
test_incomplete_material_evidence_is_not_assessable
test_mixed_pair_is_not_supported_for_p_er_01
test_fragile_pair_is_conditional_for_p_er_01
test_allocation_conflict_is_not_supported
test_evidence_snapshot_is_context_and_strategy_invariant
test_programme_handoff_reproduces_state_conditions_and_snapshot
test_result_order_is_byte_stable_across_repeated_runs
test_no_forbidden_runtime_imports
test_fixture_registry_contains_exact_expected_candidates
```

## 21. Required cross-context ordering demonstrations

The completion report must show at least three compact tables:

1. **facts_only** — factual distance order;
2. **role_extraction_v1** — Extraction-specific ordering;
3. **programme_p_er_01_v1** — ER programme ordering.

At least one candidate pair must reverse order between facts-only and Extraction-role comparison.

At least one candidate pair must change state/order between Extraction role and P-ER-01, specifically `geo_hmc_composable` and/or `refinery_heavy_weak_extraction`.

## 22. Deterministic report helper

The package may expose one pure helper that returns serialisable dictionaries for completion evidence.

It must not write files itself.

Canonical ordering:

- candidate list as sorted result order;
- condition strings lexical;
- trace entries lexical by key;
- body facts by `body_id`;
- evidence by `evidence_id`.

No timestamps, random UUIDs, locale formatting or environment paths in deterministic output.

## 23. What the implementation must explicitly NOT prove

The stage does not prove:

- these fit mappings are final product weights;
- these paper fixtures calibrate real-galaxy score distributions;
- exact Economy proportions/link strengths;
- commodity self-sufficiency;
- exact orbital slot rules galaxy-wide;
- production data coverage;
- Finder SQL performance;
- UI design;
- all economy/programme templates.

It proves only that the **search/rating semantic architecture works** without a universal score and without hidden intent changes.

## 24. Completion evidence required before any live Finder integration stage

After coding, freeze the code and produce `docs/research/r1-finder-comparison-proof-completion-2026-08-31.md` containing:

- branch/base/head SHA;
- changed-file list;
- focused pytest command and full summary;
- forbidden-import/source-boundary scan;
- deterministic repeated-run proof;
- all three context tables;
- plateau proof;
- geo-HMC composability proof;
- carrier invariance proof;
- conditional-vs-supported ordering proof;
- search-to-detail handoff equality proof;
- explicit confirmation:
  - no production Finder/API changes;
  - no DB writes;
  - no migrations;
  - no network/persistence;
  - no legacy/v4 score imports;
  - no merge/deploy.

Then perform a read-only evidence review before deciding whether a separate live Finder integration stage is justified.

## 25. Coding authorization boundary

Once this Review 2 is explicitly accepted by the owner, coding is authorised **only** for the allowed-file list in section 2 and only to satisfy this contract.

Pause before code if implementation discovers:

- a required edit to an audit-only/production file;
- a contradiction in these state rules;
- a fixture requirement that needs a new Elite mechanic assumption;
- a repository/build blocker that changes scope.

Otherwise implement without additional permission loops, then freeze and return the completion evidence packet for read-only review.
