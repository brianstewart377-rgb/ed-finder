# ED-Finder R1 — Finder Comparison Proof Stage
## Review 1 — Stage Definition

Date: 2026-08-31  
Status: **pre-code Review 1; implementation NOT yet authorised**  
Branch: `chatgpt-ed-new-ops-requests`  
Upstream contract: `docs/research/r1-ratings-vnext-contract-review-2-2026-08-31.md`

## 1. Stage objective

Prove, in an isolated fixture-backed implementation, that Finder search and R1 assessment can share one semantic comparison contract without introducing a universal system score.

The stage must demonstrate three search modes over the **same fixture candidate set**:

1. **Factual search only** — filters candidates but does not rank by hidden development quality.
2. **Extraction role comparison** — ranks candidates only for an explicit Extraction-oriented comparison context.
3. **`P-ER-01` Extraction / Refinery programme comparison** — evaluates each candidate against the same programme requirements, assessment-state rules and provisional fit policy.

The intended result is a deterministic proof of this pipeline:

```text
candidate facts
+ factual search filters
+ explicit comparison context
        ↓
canonical candidate evidence
        ↓
programme/role eligibility + requirements
        ↓
assessment state + conditions
        ↓
optional provisional fit for comparable candidates
        ↓
ranked result list
        ↓
open result carries the same comparison/template/evidence snapshot
```

This is a **semantic proof**, not production Finder integration.

## 2. Why this stage exists

Current Finder mixes several hidden scoring meanings:

- economy searches are mapped to paired archetype columns;
- multiple different economy intents share the same archetype score;
- no economy filter falls back to an overall-development score;
- the result ordering can fall back to legacy ratings;
- frontend presets combine factual filters with hidden minimum-development thresholds and force development ordering.

That violates the new contract because search can silently change the question being asked.

This stage proves a replacement interaction before touching live Finder/API code.

## 3. Explicit non-goals

This stage must NOT:

- modify `apps/api/src/local_search.py`;
- modify current search SQL or query plans;
- modify `apps/api/src/search_economies.py`;
- modify the production search request/response API;
- modify current frontend Finder/search UI;
- change routes or navigation;
- add migrations or tables;
- write to production or development databases;
- read legacy `ratings.score*`, `economy_suggestion` or archetype score outputs as R1 evidence;
- use `overall_development_potential`;
- implement galaxy-wide rerating;
- implement all programme templates or all economies;
- settle exact commodity-throughput mechanics;
- turn `domain/economy_state.py` composition-quality logic into R1 truth;
- treat the current `domain/placements.py` slot context as authoritative without an explicit fixture-provided capacity fact.

## 4. Source-boundary decision

The proof must be **fixture-backed and pure**.

It may read only local fixture/config data supplied to the evaluator. It must not access:

- PostgreSQL;
- Redis;
- network APIs;
- live Finder search;
- Raven;
- EDSM/Spansh;
- browser persistence;
- production rating/archetype tables.

This isolates semantic correctness from performance, SQL and data-coverage concerns.

## 5. Reuse vs reject from current repository

### Reuse conceptually

Existing repository code already contains useful structural ideas:

- `domain/colonisation_rules.py` separates `base_economies` and `modifier_economies`;
- `domain/placements.py` separates facility identity, placement and validation;
- R1 laboratory material already defines assessment state, conditions, evidence snapshots and carrier invariants.

### Do not inherit blindly

Current domain code also contains assumptions rejected by the forensic audit:

- `colonisation_rules.py` uses broad ammonia substring matching;
- it conflates geologicals and volcanism in its `has_geo` calculation;
- `economy_state.py` has subjective `IDEAL_PAIRS`, arbitrary composition-quality penalties and fixed percentage thresholds;
- `placements.py` expects slot inputs historically derived from topology/archetype outputs.

The proof must therefore use a new narrow R1 contract rather than importing those modules as authoritative mechanics.

## 6. First comparison contexts

Only three contexts are permitted in this stage.

### 6.1 `facts_only`

Purpose: prove an ordinary factual search remains useful without a hidden score.

Rules:

- apply factual filters;
- return matching candidates in deterministic factual sort order;
- no `plan_fit`;
- no `assessment_state` required beyond evidence completeness if the implementation chooses to expose it;
- no “best”, “recommended”, “development score” or implicit quality rank.

Default deterministic sort for the fixture proof:

1. distance ascending where distance is known;
2. system name lexical;
3. id64 ascending.

This sort is a proof convenience, not a product decision for final Finder.

### 6.2 `role_extraction_v1`

Purpose: prove a lightweight search comparison context can answer “which system is better for Extraction?” without silently converting that into Extraction/Refinery or a global archetype.

The role context may inspect only explicitly declared Extraction-relevant fixture dimensions. It must not infer a second economy automatically.

The first contract should be deliberately minimal:

- canonical HMC identity;
- canonical Metal-Rich identity;
- ring evidence;
- geological presence as a composable modifier;
- physical capacity evidence where material;
- locality/distance evidence;
- evidence disposition.

No fixed production weighting is accepted in Review 1. Review 2 must define the provisional strategy used in the fixture proof and mark every coefficient as product/laboratory policy rather than Elite mechanics.

### 6.3 `programme_p_er_01_v1`

Purpose: prove programme-relative search ranking and detail handoff using the accepted `P-ER-01` concept.

Target outcome:

> Extraction and Refinery are the intended top-two pair in either order.

Hard requirement families:

- candidate placeability/capacity;
- source evidence for both intended economy sides;
- target-pair viability evidence;
- no double allocation;
- declared locality/link assumptions;
- logistics under selected carrier mode;
- evidence sufficiency.

Baseline top-two membership alone must not be promoted to a robust Supported pair if the declared perturbation/pair-stability evidence is unavailable. In that case the result is conditional/not-assessable according to the exact Review-2 state rules.

## 7. Candidate fixture set

The stage should use a deliberately small candidate-list fixture rather than one fixture per evaluator call.

Minimum candidate systems:

1. **compact Extraction specialist**
   - strong canonical HMC/Metal-Rich evidence;
   - usable capacity;
   - compact logistics;
   - intended positive control.
2. **Extraction-rich but remote**
   - more raw material bodies than the compact specialist;
   - materially worse distance/logistics;
   - proves raw abundance does not automatically win.
3. **geo-HMC composability control**
   - HMC with geologicals;
   - must retain HMC identity and geological modifier;
   - must never become worse merely because the modifier exists.
4. **Refinery-heavy but weak Extraction**
   - useful for `P-ER-01` contrast;
   - may rank well for neither Extraction-only nor full pair depending on evidence.
5. **incomplete evidence candidate**
   - promising inventory but material unknown/conflicting capacity/economy evidence;
   - cannot appear as ordinary Supported winner.
6. **surplus-volume plateau pair**
   - two candidates with equivalent programme-sufficient allocated support but one has many irrelevant extra bodies;
   - fixed-programme fit must plateau.

Named real-galaxy fixtures can be added later. This first proof may use deterministic paper fixtures because its purpose is contract behaviour, not live data calibration.

## 8. Search request contract for the proof

Review 2 must lock exact field names, but Review 1 requires this conceptual shape:

```ts
interface R1FixtureSearchRequest {
  factual_filters: FactualSearchFilters;
  comparison_context:
    | { kind: 'facts_only' }
    | { kind: 'role'; role_id: 'role_extraction_v1'; revision: string }
    | {
        kind: 'programme';
        programme_id: 'P-ER-01';
        template_revision: string;
        carrier_mode: 'no_carrier' | 'carrier_available' | 'compare_both';
      };
  strategy_id?: string;
}
```

Rules:

- `strategy_id` is invalid for `facts_only`;
- role/programme search can return assessment state without a strategy;
- provisional numeric fit/order is only allowed when an eligible strategy is explicitly selected;
- no request may contain `overall_score`, `development_score`, `archetype`, `economy_suggestion` or legacy rating fields.

## 9. Result-list contract

Every returned candidate must preserve factual identity plus context-bound assessment.

Conceptual shape:

```ts
interface R1FixtureSearchResult {
  system_id64: string;
  system_name: string;
  distance_ly: number | null;
  factual_summary: CandidateFactualSummary;
  comparison_context_id: string;
  assessment_state?: AssessmentState;
  conditions: AssessmentCondition[];
  evidence_status?: EvidenceStatus;
  reserve?: ReserveCapacity;
  logistics?: LogisticsState;
  complexity?: ComplexityState;
  carrier_dependence?: CarrierDependence;
  plan_fit?: number;
  evidence_snapshot_id: string;
  candidate_plan_id?: string;
}
```

`plan_fit` must be absent unless the selected comparison context + strategy are eligible to produce it.

## 10. Ordering semantics

### Facts-only

Deterministic factual ordering only.

### Role/programme with no fit strategy selected

Group by assessment state:

1. `supported`
2. `conditionally_supported`
3. `not_supported`
4. `not_assessable`

Within each state use deterministic factual ordering. This demonstrates that hard semantic gates precede any score.

### Role/programme with fit strategy selected

Ordering:

1. assessment-state precedence above;
2. within `supported`, provisional fit descending;
3. within `conditionally_supported`, provisional fit may be shown but must remain in the conditional group;
4. unsupported/not-assessable candidates have no plan fit and use deterministic factual ordering;
5. stable tie-break: distance, name, id64.

A Conditional 97 can never outrank a Supported 85 in default search ordering.

## 11. Search-to-detail continuity proof

For the top returned programme candidate, the proof must expose a deterministic handoff payload containing:

- comparison context/programme ID + revision;
- carrier mode;
- strategy revision if selected;
- evidence snapshot ID;
- generated candidate-plan ID;
- requirement/allocation trace IDs.

Opening/re-evaluating that candidate from the handoff must reproduce the same base assessment state, conditions, evidence snapshot and allocation truth.

Detailed editing is out of scope. The only proof required is that search did not rank using a different model than detail assessment.

## 12. Provisional allowed-file set

Review 2 must confirm the exact list after final repository inspection. The expected implementation should be isolated under a new package/test area.

### New implementation files only

Proposed:

```text
apps/api/src/r1_finder_compare/__init__.py
apps/api/src/r1_finder_compare/types.py
apps/api/src/r1_finder_compare/fixtures.py
apps/api/src/r1_finder_compare/evidence.py
apps/api/src/r1_finder_compare/programmes.py
apps/api/src/r1_finder_compare/evaluator.py
apps/api/src/r1_finder_compare/search_compare.py
apps/api/tests/test_r1_finder_compare.py
```

If the repository test convention requires a different exact test root, Review 2 may adjust the test path but must not expand functional scope.

### Documentation allowed

```text
docs/research/r1-finder-comparison-proof-stage-review-1-2026-08-31.md
docs/research/r1-finder-comparison-proof-stage-review-2-2026-08-31.md
docs/research/r1-finder-comparison-proof-completion-2026-08-31.md
```

### Audit-only source files — must not be modified in this stage

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

Any need to modify an audit-only file is a scope break requiring a new review before code.

## 13. Required proof tests

Review 2 must turn these into exact test names/assertions.

At minimum:

1. facts-only result contains no plan fit or hidden comparison score;
2. Extraction role does not silently become ER pair assessment;
3. programme `P-ER-01` uses the same base evidence/evaluator as detail handoff;
4. supported results precede conditional regardless of numeric fit;
5. conditional high fit does not outrank supported lower fit;
6. unsupported/not-assessable candidates never receive fit;
7. geo-HMC retains HMC identity and geo modifier;
8. geological presence cannot reduce an otherwise identical Extraction capability merely through classification replacement;
9. true Ammonia vs ammonia-life does not appear in this programme's evidence accidentally;
10. signal count cannot multiply body-local modifier credit;
11. surplus-volume plateau candidate gets equal fixed-programme fit once both plans are fully sufficient;
12. remote raw abundance loses to compact sufficient candidate when the selected provisional strategy says logistics is material;
13. unknown/conflicting material evidence produces correct state and structured conditions;
14. same scarce evidence/allocation cannot be used twice;
15. carrier mode changes only carrier-sensitive logistics requirements;
16. same frozen evidence yields same evidence snapshot across strategies;
17. search-to-detail handoff reproduces assessment state/conditions/allocation trace;
18. all output ordering deterministic across repeated runs;
19. no imports from `build_ratings`, `build_archetype_scores`, ratings/archetype API helpers, DB or network modules;
20. no production files changed.

## 14. Acceptance evidence required after implementation

The completion packet must contain:

- base and head SHA;
- exact changed-file list;
- full focused test output;
- import/source-boundary scan;
- deterministic repeated-run proof;
- compact table showing all candidate systems under all three contexts;
- one case showing factual order differs from Extraction role order;
- one case showing Extraction role order differs from `P-ER-01` programme order;
- one conditional-high-fit vs supported-lower-fit ordering proof;
- search-to-detail handoff equality proof;
- explicit confirmation of no DB/network/persistence/migration/production-search changes.

## 15. Review-1 decision points carried to Review 2

Review 2 must resolve, not guess:

1. exact pure-domain type names and enums;
2. exact provisional Extraction role dimensions;
3. exact `P-ER-01` first-slice requirements that can be honestly evaluated from fixtures;
4. state precedence for direct allocation contradiction vs contradictory evidence;
5. exact fit-strategy choice for this proof — preferably one simple strategy, not A/B/C all at once;
6. whether the programme proof should support `compare_both` carrier mode in the first slice or only single carrier scenarios;
7. exact package/test paths matching current repo conventions;
8. whether candidate-plan generation is merely trace allocation or a separate object in this stage.

## 16. Review 1 acceptance gate

Proceed to Review 2 only if this scope is accepted:

- first prove comparison semantics on fixtures;
- do not touch live Finder yet;
- support facts-only, Extraction-role, and `P-ER-01` only;
- one semantic evaluator/trace must feed both result ranking and detail handoff;
- assessment state precedes numeric fit;
- legacy/v4 scores are excluded;
- new isolated files only;
- no DB, network, persistence, migration or production UI/API changes.
