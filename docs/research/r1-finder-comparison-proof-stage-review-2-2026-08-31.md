# ED-Finder R1 — Finder Comparison Proof Stage
## Review 2 — Final Pre-Code Technical Contract

Date: 2026-08-31  
Status: **final pre-code Review 2; coding may begin only inside this contract after owner acceptance**  
Branch: `chatgpt-ed-new-ops-requests`  
Review 1: `docs/research/r1-finder-comparison-proof-stage-review-1-2026-08-31.md`  
Upstream R1 contract: `docs/research/r1-ratings-vnext-contract-review-2-2026-08-31.md`

## 0. Product-redesign principle: V2 is evidence, not the target

Owner decision recorded 2026-08-31: ED-Finder should not be rebuilt by mechanically migrating V2 features. V2 is a source of observed player workflows, useful interaction patterns, operational lessons, failure cases, data-contract history, and regression controls. It is **not** the feature-parity checklist, information architecture, scoring ontology, or UI blueprint for R1.

For every inherited V2 feature or concept, the redesign must ask:

1. What player job was this feature actually trying to solve?
2. What have we learned since V2 about Elite colonisation mechanics, data quality, provenance, uncertainty, allocation and player workflow?
3. Does the feature still deserve to exist in the same form?
4. Should it be simplified, split, merged into another workflow, reframed around evidence, or removed entirely?
5. If retained, can it use the new canonical evidence/assessment contract rather than preserve legacy scoring assumptions?

**Feature parity is therefore not an acceptance criterion.** Losing a V2 control or screen is acceptable when its player job is better served by the reimagined R1 workflow. Conversely, a useful V2 idea may be retained when it survives the new evidence/mechanics review.

The first Finder-comparison proof remains deliberately isolated because it is testing the new semantic foundation, not preserving current Finder behaviour.

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

PairStability = Literal[
    'robust',
    'fragile',
    'mixed',
    'unknown',
]

ReserveCapacity = Literal[
    'tight',
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
```

## 5. Canonical candidate/evidence shape

Each fixture candidate must expose canonical, composable facts. Identity and modifiers are independent.

```python
@dataclass(frozen=True)
class BodyFact:
    body_id: str
    base_identity: str
    distance_ls: float | None
    is_landable: bool | None
    is_terraformable: bool | None
    has_rings: bool | None
    has_geologicals: bool | None
    has_biologicals: bool | None
    volcanism: str | None
    atmosphere: str | None
    surface_temperature_k: float | None
    gravity_g: float | None
    radius_km: float | None
```

Fixture evidence must never encode a geological HMC as a replacement pseudo-body type. It remains `High metal content world` plus `has_geologicals=True`.

```python
@dataclass(frozen=True)
class CandidateEvidence:
    system_id64: str
    system_name: str
    distance_ly: float | None
    bodies: tuple[BodyFact, ...]
    physical_capacity: CapacityEvidence
    extraction_evidence: RequirementEvidence
    refinery_evidence: RequirementEvidence
    pair_stability: PairStability
    logistics_no_carrier: LogisticsState | None
    logistics_carrier: LogisticsState | None
    evidence_disposition: EvidenceDisposition
    ambiguity_flags: tuple[str, ...]
    conflict_flags: tuple[str, ...]
    provenance_ids: tuple[str, ...]
```

All tuples are stored/sorted deterministically. `None` means unknown/not supplied, never false by implication.

## 6. Fixture candidates

Use exactly these seven fixture IDs:

```text
compact_extraction_specialist
remote_extraction_abundance
geo_hmc_composable
refinery_heavy_weak_extraction
incomplete_material_evidence
plateau_sufficient_30
plateau_surplus_60
```

Their semantic roles are fixed:

### compact_extraction_specialist

- canonical HMC + Metal-Rich positive evidence;
- enough explicitly provided capacity;
- compact logistics;
- strong Extraction evidence;
- sufficient Refinery evidence;
- robust ER pair;
- `supported` for role Extraction and P-ER-01.

### remote_extraction_abundance

- greater raw Extraction-relevant body abundance than compact specialist;
- spread/extreme logistics under no-carrier;
- sufficient evidence, not missing evidence;
- supported for Extraction if the role has no hard logistics failure, but lower fit than compact specialist under the provisional strategy;
- P-ER-01 may be conditional under no-carrier if the fixture declares logistics dependency, and supported under carrier if all other requirements are met.

### geo_hmc_composable

- includes at least one HMC with geologicals;
- must retain HMC identity and geological modifier simultaneously;
- otherwise comparable to a clean-HMC control dimension;
- adding geological evidence cannot reduce the Extraction capability dimension.

### refinery_heavy_weak_extraction

- good Refinery evidence;
- insufficient Extraction evidence;
- `not_supported` for P-ER-01;
- must not become an ER candidate merely because Refinery is strong.

### incomplete_material_evidence

- promising body inventory;
- material capacity/pair evidence missing or conflicting;
- `not_assessable` for P-ER-01;
- no Plan Fit.

### plateau_sufficient_30 / plateau_surplus_60

- same allocated, programme-sufficient ER plan;
- surplus fixture has materially more irrelevant/unused bodies and higher reserve state;
- identical P-ER-01 Plan Fit;
- different reserve capacity allowed/required.

## 7. P-ER-01 exact requirement contract

Target: unordered top-two `{Extraction, Refinery}`.

Requirement IDs:

```text
ER-PLACE-01    candidate placement/capacity is known and sufficient
ER-EXT-01      Extraction-side evidence is sufficient
ER-REF-01      Refinery-side evidence is sufficient
ER-PAIR-01     pair stability is known and acceptable
ER-ALLOC-01    required scarce capacity/evidence has a non-overlapping allocation
ER-LOG-01      selected carrier scenario satisfies declared logistics requirement
ER-EVID-01     material evidence is not missing/ambiguous/conflicting
```

State rules, evaluated in this order:

1. `not_assessable` when any material requirement cannot be evaluated because required evidence is missing, ambiguous or conflicting.
2. `not_supported` when evidence is sufficient to evaluate but a hard requirement fails, including insufficient Extraction/Refinery, impossible capacity, invalid/double allocation or `pair_stability='mixed'`.
3. `conditionally_supported` when all hard feasibility requirements pass but a material declared condition remains, including `pair_stability='fragile'` or carrier-dependent logistics under the no-carrier scenario where the fixture explicitly permits conditional support.
4. `supported` only when every material requirement is met and `pair_stability='robust'`.

`pair_stability='unknown'` is `not_assessable`, not a guessed fragile/robust state.

No numeric percentage margin is invented for pair stability in this stage.

## 8. Extraction role exact contract

`role_extraction_v1` is not an implicit ER pair.

It evaluates only:

```text
EX-EVID-01     material Extraction evidence is assessable
EX-SOURCE-01   at least one canonical Extraction source exists
EX-CAP-01      relevant physical capacity is known enough for the role claim
EX-LOG-01      logistics/practicality is classified for comparison
```

Canonical Extraction sources in fixture semantics:

- HMC identity;
- Metal-Rich identity;
- ring modifier on a compatible body;
- geological presence as a composable Extraction-positive modifier.

No Refinery requirement exists in this role context. Pair stability is ignored.

## 9. Provisional fit policy

Use one strategy only in this proof:

```text
strategy_id = bounded_geometric_v1
strategy_revision = finder-proof-2026-08-31.1
```

This is **ED-Finder laboratory policy, not Elite mechanics**.

### Extraction role dimensions

Each eligible candidate supplies bounded `0..1` dimensions:

- `source_support`
- `usable_capacity`
- `logistics_practicality`
- `evidence_quality`

### P-ER-01 dimensions

Each eligible candidate supplies bounded `0..1` dimensions:

- `extraction_support`
- `refinery_support`
- `allocated_capacity`
- `pair_resilience`
- `logistics_practicality`
- `evidence_quality`

Every dimension is capped at `1.0` when the fixture has reached declared sufficiency. Extra unused bodies/capacity cannot raise that dimension above `1.0`.

Plan Fit:

```python
plan_fit = round(100 * product(dimensions) ** (1 / len(dimensions)))
```

The geometric mean is chosen only because it is transparent and non-compensatory enough for the proof. It is not accepted as the final production fit model.

Unsupported/not-assessable results do not receive dimensions or Plan Fit.

Conditional results may receive a provisional Plan Fit for comparison inside the conditional group only.

## 10. Reserve semantics

Reserve is separate from Plan Fit.

For P-ER-01 fixture allocation:

```text
tight       = programme feasible with no meaningful unused compatible capacity
sufficient  = programme fully supported with a small explicit reserve
resilient   = programme supported with meaningful compatible spare capacity
expandable  = programme supported with enough independent spare capacity for a declared additional future route/node
```

The plateau fixtures must prove that `resilient`/`expandable` may improve while fixed P-ER-01 Plan Fit remains unchanged.

## 11. Search request/result types

```python
@dataclass(frozen=True)
class FactualFilters:
    max_distance_ly: float | None = None
    require_hmc: bool = False
    require_metal_rich: bool = False
    require_rings: bool = False

@dataclass(frozen=True)
class FixtureSearchRequest:
    factual_filters: FactualFilters
    comparison_context_id: ComparisonContextId
    carrier_mode: CarrierMode = 'no_carrier'
    strategy_id: str | None = None
```

Rules:

- `facts_only` rejects/non-uses `strategy_id`;
- role/programme may run without strategy to show state groups only;
- only exact `bounded_geometric_v1` is accepted as strategy in this proof.

Result must include:

```python
@dataclass(frozen=True)
class SearchCandidateResult:
    system_id64: str
    system_name: str
    distance_ly: float | None
    comparison_context_id: ComparisonContextId
    assessment_state: AssessmentState | None
    conditions: tuple[AssessmentCondition, ...]
    reserve_capacity: ReserveCapacity | None
    logistics: LogisticsState | None
    evidence_disposition: EvidenceDisposition
    plan_fit: int | None
    evidence_snapshot_id: str
    candidate_plan_id: str | None
```

For `facts_only`, `assessment_state`, reserve and Plan Fit are `None`.

## 12. Evidence snapshot and deterministic IDs

Evidence snapshot canonical payload includes only frozen candidate evidence:

```text
fixture_id
fixture_revision
normalized candidate facts
normalized requirement evidence
normalized provenance IDs
ambiguity/conflict flags
```

It excludes:

- comparison context;
- carrier mode;
- strategy;
- conditions/prose;
- Plan Fit;
- run time.

Digest:

```text
sha256:<lowercase hex>
```

`candidate_plan_id` for P-ER-01 is separately hashed from:

```text
system_id64
programme id + revision
carrier scenario
stable allocation trace
```

Strategy does not change candidate-plan identity because strategy is not allowed to change allocation truth.

## 13. Ordering contract

State precedence:

```text
supported
conditionally_supported
not_supported
not_assessable
```

### facts_only

Sort:

1. known distance ascending; unknown distance last;
2. system name lexical;
3. id64 lexical.

### role/programme without strategy

1. state precedence;
2. factual sort above.

### role/programme with strategy

1. state precedence;
2. for supported/conditional groups only: Plan Fit descending;
3. factual tie-break.

A Conditional `97` is always below a Supported `85`.

## 14. Carrier invariants

Carrier mode may affect only declared logistics-sensitive requirement outcomes and logistics dimension/state.

It must not change:

- body facts;
- physical capacity facts;
- Extraction/Refinery source evidence;
- pair stability;
- evidence disposition/provenance;
- evidence snapshot ID;
- non-logistics allocation truth.

`compare_both` returns exactly two scenario results in order:

```text
no_carrier
carrier_available
```

## 15. Search-to-detail handoff

For any P-ER-01 result, provide:

```python
@dataclass(frozen=True)
class CandidateHandoff:
    system_id64: str
    comparison_context_id: str
    programme_id: str
    template_revision: str
    carrier_mode: str
    evidence_snapshot_id: str
    candidate_plan_id: str
    allocation_trace_ids: tuple[str, ...]
    requirement_trace_ids: tuple[str, ...]
```

Re-evaluating from this handoff must reproduce byte-equivalent canonical base assessment fields:

- assessment state;
- conditions;
- reserve;
- logistics;
- evidence disposition;
- evidence snapshot;
- allocation trace;
- requirement trace.

Plan Fit is allowed to be omitted/recomputed separately and must not be part of the base-equivalence assertion.

## 16. Exact test names

Create exactly one new test file:

```text
tests/test_r1_finder_compare.py
```

Required tests:

```text
test_facts_only_has_no_assessment_or_hidden_fit
test_extraction_role_does_not_require_refinery_or_pair_stability
test_geo_hmc_preserves_hmc_identity_and_geo_modifier
test_geo_modifier_cannot_reduce_extraction_dimension
test_per_body_signal_presence_not_signal_count_drives_modifier
test_p_er_01_supported_requires_robust_pair
test_p_er_01_fragile_pair_is_conditional
test_p_er_01_mixed_pair_is_not_supported
test_p_er_01_unknown_pair_is_not_assessable
test_refinery_strength_cannot_rescue_missing_extraction_requirement
test_missing_material_evidence_is_not_assessable_and_has_no_fit
test_unsupported_and_not_assessable_have_no_plan_fit
test_supported_candidate_precedes_higher_fit_conditional_candidate
test_remote_abundance_does_not_beat_compact_sufficient_under_proof_policy
test_surplus_plateau_has_equal_fixed_programme_fit
test_surplus_plateau_can_have_better_reserve_without_fit_increase
test_allocation_cannot_consume_same_scarce_capacity_twice
test_carrier_changes_only_logistics_sensitive_fields
test_compare_both_order_is_stable
test_evidence_snapshot_is_strategy_and_carrier_invariant
test_programme_candidate_plan_id_is_strategy_invariant
test_search_handoff_reproduces_base_assessment
test_factual_role_and_programme_orders_are_intentionally_different
test_results_are_deterministic_across_repeated_runs
test_source_boundary_forbids_db_network_legacy_and_archetype_imports
```

## 17. Completion checks

Implementation completion must report:

```text
python -m pytest tests/test_r1_finder_compare.py -q
```

plus a source-boundary scan over `apps/api/src/r1_finder_compare` proving absence of forbidden imports/strings.

The completion document must include:

- exact base/head SHA;
- exact changed-file list;
- complete focused test output;
- deterministic repeated-run equality result;
- table of all seven candidates in all three comparison contexts;
- conditional-high-fit vs supported-lower-fit example;
- 30/60 plateau result;
- carrier compare-both result;
- search-to-detail equality result;
- explicit no-production-change statement.

## 18. Final coding boundary

Coding is authorised **only after owner acceptance of this Review 2**, and only for the files in section 2.

No migration, DB write, API route, Finder UI, local search SQL, ratings rebuild, archetype rebuild, production deployment or merge is part of this stage.
