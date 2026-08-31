# ED-Finder R1 / Ratings vNext — Technical Contract Review 2

Date: 2026-08-31  
Status: **Review 2 — final pre-code technical contract; no coding authorised by this document alone**  
Branch: `chatgpt-ed-new-ops-requests`  
Review 1: `docs/research/r1-ratings-vnext-contract-review-1-2026-08-31.md`  
Forensic base: `docs/research/v3-ratings-forensic-audit-checkpoint-2026-08-31-18.md`

## 1. Review-1 correction incorporated: Finder and Ratings must be one semantic system

A plan-relative rating model is only useful if Finder can still answer the ordinary player question:

> “I searched and got 50 systems back. Which of these is better for what I am trying to do?”

The answer is **not** to restore a universal Development/System score. The search itself establishes a comparison context, explicitly or by a tightly governed preset. Every candidate is then assessed against the **same role or programme contract**.

The required flow is:

```text
search filters
+ explicit/inferred comparison context
        ↓
canonical factual candidate filtering
        ↓
R1 role/programme assessment
        ↓
Supported / Conditional / Unsupported / Not assessable
        ↓
Plan/Role Fit only among comparable eligible candidates
        ↓
ranked Finder results
        ↓
open a result with the exact same context/evidence/auto-plan
        ↓
full detailed programme assessment / editable plan
```

Therefore search and detailed assessment must use **one canonical evidence engine, one mechanics contract, one template revision and one fit-policy revision**. There must not be a “search score” with different semantics from the detailed assessment.

## 2. Existing search behaviour that this contract is intended to replace

Current Finder has a semantic shortcut that must not be carried into R1:

- economy filters map to paired archetype columns;
- Agriculture -> `score_agriculture_terraforming`;
- Refinery and Industrial -> `score_refinery_industrial`;
- HighTech and Tourism -> `score_hitech_tourism`;
- Military -> `score_military_industrial`;
- Extraction -> `score_extraction_refinery`;
- no economy -> `overall_development_potential`;
- Finder currently uses `COALESCE(archetype_score, legacy_ratings_score)` and sorts descending for development ordering.

This means, for example, a user asking for High Tech is silently compared using a HighTech/Tourism archetype even if Tourism was not their intent. That is precisely the kind of hidden semantic inference R1 must remove.

Current frontend quick presets also combine factual filters with `minDevelopmentScore` and then force `sortBy = development`. R1 should keep the useful preset UX but replace the hidden universal/archetype score with an explicit comparison context.

## 3. Core type vocabulary

Use the accepted R1 vocabulary unless implementation inspection proves a naming collision.

```ts
type AssessmentState =
  | 'not_assessable'
  | 'not_supported'
  | 'conditionally_supported'
  | 'supported';

type CarrierMode =
  | 'no_carrier'
  | 'carrier_available'
  | 'compare_both';

type EvidenceDisposition =
  | 'sufficient'
  | 'partial'
  | 'missing'
  | 'ambiguous'
  | 'conflicting';

type FactAvailability =
  | 'known'
  | 'missing'
  | 'ambiguous'
  | 'conflicting'
  | 'not_applicable';

type FactPolarity =
  | 'positive'
  | 'negative'
  | 'value';
```

A negative fact is only valid when the source can genuinely assert absence/false. Missing evidence never becomes a negative fact.

## 4. Canonical evidence contract

### 4.1 Provenance

```ts
interface EvidenceProvenanceRef {
  source_kind: string;
  source_id: string;
  source_revision: string | null;
  payload_hash: string | null;
  observed_at: string | null;
  effective_from: string | null;
  effective_to: string | null;
  game_patch: string | null;
  evidence_class:
    | 'official_rule'
    | 'direct_observation'
    | 'imported_fact'
    | 'prediction'
    | 'manual_correction'
    | 'assumption';
}
```

`observed_at` is evidence metadata and is not permitted to make deterministic fixture output vary unless the fixture itself changes revision.

### 4.2 Fact record

```ts
interface CanonicalFact<T = unknown> {
  fact_id: string;
  entity_ref: string;
  fact_key: string;
  value: T | null;
  availability: FactAvailability;
  polarity: FactPolarity | null;
  provenance: EvidenceProvenanceRef[];
  ambiguity_flags: string[];
  conflict_flags: string[];
}
```

Arrays are explicit and deterministically ordered. `value = null` is not synonymous with false.

### 4.3 Body fact representation

Base identity and modifiers are independent. Do **not** create mutually exclusive replacement buckets such as `hmc_geo` or `rocky_mixed` as canonical truth.

Conceptual body evidence must be able to represent simultaneously:

```ts
interface BodyCapabilityFacts {
  body_ref: string;

  identity: CanonicalFact<string>; // exact controlled subtype
  body_type: CanonicalFact<string>;
  is_main_star: CanonicalFact<boolean>;

  landable: CanonicalFact<boolean>;
  terraformable: CanonicalFact<boolean>;
  rings_present: CanonicalFact<boolean>;
  geologicals_present: CanonicalFact<boolean>;
  biologicals_present: CanonicalFact<boolean>;
  volcanism: CanonicalFact<string>;
  atmosphere_type: CanonicalFact<string>;
  tidal_locked: CanonicalFact<boolean>;

  surface_temperature_k: CanonicalFact<number>;
  surface_gravity_g: CanonicalFact<number>;
  radius_km: CanonicalFact<number>;
  distance_from_arrival_ls: CanonicalFact<number>;
  reserve_level: CanonicalFact<string>;

  bio_signal_count: CanonicalFact<number>;
  geo_signal_count: CanonicalFact<number>;
}
```

The exact physical storage shape may differ later; this is the semantic contract.

### 4.4 Mandatory classifier invariants

1. HMC + geological remains HMC **and** geological.
2. Rocky + ring + geological + biological remains rocky **and** all three modifiers.
3. Terraformable survives classification for every applicable recognised subtype.
4. Volcanism is not inferred from geological signal count.
5. Signal count is separate from signal/body predicate presence.
6. True Ammonia World is exact canonical identity and never inferred from ammonia atmosphere/life text.
7. Directly contradictory mutually exclusive identity evidence withholds both affected derived claims.
8. No-body/zero-row evidence remains Unknown, never complete through an empty aggregate.

## 5. Derived feasibility contract

Derived mechanics are versioned outputs over canonical evidence, not score inputs by accident.

```ts
interface DerivedFact<T = unknown> {
  derived_fact_id: string;
  fact_key: string;
  value: T | null;
  availability: FactAvailability;
  model_revision: string;
  mechanics_revision: string;
  input_snapshot_id: string;
  provenance: EvidenceProvenanceRef[];
  uncertainty_flags: string[];
}
```

Required first families:

- surface construction capacity prediction;
- orbital capacity where current rules are known;
- body/locality grouping;
- distance/logistics bands;
- legal placement feasibility where rule coverage permits;
- link evidence/projection tied to actual body/node locality;
- economy-role/pair evidence only where source/model coverage permits it.

### 5.1 Surface-slot rule

Use the validated current hypothesis as a versioned prediction:

```text
0 if non-landable OR temperature > 700 K OR gravity > 2.7 g

base by radius:
<1500 km       -> 1
1500–<3750     -> 2
3750–<6000     -> 3
>=6000         -> 4

+1 HMC
+1 Terraformable
+1 Volcanism OR Geologicals
+2 atmosphere present
cap 7
```

Exact threshold equality fixtures are mandatory. The two historical `actual = predicted + 1` residuals remain uncertainty fixtures; no mystery correction constant is authorised.

Current-patch gas giants use one construction slot; the stale 3/5 model is prohibited.

## 6. Role vs programme comparison contexts

Search needs both lightweight role comparisons and explicit programme comparisons. They share the same evidence/feasibility engine.

```ts
type ComparisonKind =
  | 'role'
  | 'programme'
  | 'none';

type ComparisonContextSource =
  | 'explicit_user_selection'
  | 'named_preset'
  | 'strict_filter_inference'
  | 'none';

interface SearchComparisonContext {
  comparison_context_id: string;
  comparison_kind: ComparisonKind;
  source: ComparisonContextSource;

  role_id: string | null;
  template_id: string | null;
  template_revision: string | null;

  carrier_mode: CarrierMode;
  assessment_model_revision: string;
  fit_policy_revision: string | null;
  mechanics_revision: string;

  label: string;
  explanation: string;
}
```

### 6.1 Role context

A role context answers a narrow discovery question such as:

> “Which of these systems is a better candidate for supporting Extraction?”

It does **not** silently invent a second economy or full build programme.

A role context can have hard feasibility requirements and an explicit capacity/support definition, but it must not pretend to be a completed multi-node plan.

### 6.2 Programme context

A programme context evaluates an explicit plan/template such as:

- Extraction / Refinery specialist;
- Industrial / High Tech specialist;
- Wregoe-style dual-hub materials programme;
- flexible platform with a defined simultaneous independent-route count.

Programme context includes allocation/coexistence requirements.

### 6.3 No context

When `comparison_kind = none`:

- there is no Plan Fit or Role Fit;
- no universal score is substituted;
- `development` must not remain a hidden default ranking semantic;
- results may be sorted by factual/user-chosen criteria such as distance, population, name, counts, or other explicit factual fields;
- UI should invite the user to choose **Compare for:** rather than inventing what “better” means.

## 7. Search-context resolution rules

Resolution is deterministic and visible.

1. **Explicit Compare-for selection wins.**
2. **Named preset may carry an explicit comparison profile.** The preset label must show the intended role/programme.
3. **Strict filter inference is allowed only when an exact approved mapping exists.**
4. A single economy filter must never silently map to a pair merely because a legacy/v4 archetype happens to pair it with another economy.
5. Arbitrary body sliders are factual filters, not automatic intent inference.
6. Conflicting filters do not rewrite the comparison context. They constrain the candidate set and may make candidates unsupported.
7. Exobiology/exploration presets are outside colonisation Plan Fit unless an explicit cross-domain contract is designed later.
8. Every result must expose the resolved comparison context label/id so the player can see what the ranking means.

## 8. Mapping current Finder presets into the new model

The current preset UI is worth retaining, but each colonisation preset must be redefined as filters **plus** a comparison context.

Working migration table:

| Current preset | R1 treatment |
|---|---|
| Farm Colony | Requires an accepted Agriculture/civilian role or programme profile before cutover. Do not simply reuse `agriculture_terraforming`. |
| Refinery | Candidate for `P-ER-01` only if the preset explicitly says Extraction/Refinery. Otherwise define a Refinery role profile. |
| Tourism Hub | Requires a Tourism/civilian role/programme profile. Do not silently pair with High Tech. |
| High-Tech R&D | Requires a High-Tech role profile or an explicitly labelled Industrial/High-Tech programme. |
| Military | Requires an accepted Military role/programme contract; generic landables/exotics cannot stand in for it. |
| Exobiology | Keep as an exploration/exobiology search context; do not route through colonisation Plan Fit. |

Production search must not be cut over until every currently exposed colonisation preset/economy filter has an honest mapping or is visibly factual-only.

## 9. Programme/template contract

Reuse the accepted R1 Programme Template Canvas.

```ts
interface ProgrammeTemplate {
  programme_id: string;
  template_id: string;
  revision: string;
  label: string;
  intent: string;
  target_outcome: string;
  nodes: ProgrammeNodeDefinition[];
  requirements: ProgrammeRequirement[];
  coexistence_rules: CoexistenceRule[];
  capacity_ladder: CapacityLadder;
  known_exclusions: string[];
}
```

Each requirement binds abstract evidence roles, not fixture IDs.

```ts
interface ProgrammeRequirement {
  requirement_id: string;
  label: string;
  kind: 'eligibility' | 'capacity' | 'economy' | 'locality' | 'logistics' | 'constraint' | 'evidence';
  mandatory: boolean;
  shared_constraint: boolean;
  carrier_sensitive: boolean;
  evidence_roles: string[];
}
```

## 10. Search candidate auto-plan contract

The search list cannot ask the player to manually place every node before producing a useful ordering. Therefore standard programme comparisons use a **deterministic bounded candidate-plan generator**.

```ts
interface CandidatePlanRef {
  candidate_plan_id: string;
  template_id: string;
  template_revision: string;
  generator_revision: string;
  allocation_refs: string[];
  evidence_snapshot_id: string;
}
```

Rules:

1. Candidate generation uses only canonical/derived evidence permitted by the template.
2. It is deterministic and order-stable; no randomness.
3. It generates a bounded set of credible allocations, not every combinatorial possibility.
4. Each scarce body/slot/facility/link allocation is exclusive unless the mechanic/template explicitly permits sharing.
5. The same evidence/allocation may not be credited twice merely to manufacture flexibility.
6. The selected search-result fit is the fit of a concrete `CandidatePlanRef`, not a generic system score.
7. Opening the system from Finder starts from **the exact candidate plan/evidence snapshot that produced the result**.
8. If the user edits the plan, a new assessment is produced and the UI clearly shows it is no longer the unchanged Finder candidate.

This is the primary semantic bridge between “Finder list ranking” and detailed planning.

## 11. Assessment and search-result contracts

### 11.1 Requirement result

```ts
interface RequirementAssessment {
  requirement_id: string;
  outcome: 'met' | 'unmet' | 'conditional' | 'unknown' | 'contradictory';
  matched_evidence_ids: string[];
  missing_evidence_ids: string[];
  contradictory_evidence_ids: string[];
  allocation_refs: string[];
  carrier_logistics_affected: boolean;
}
```

### 11.2 Condition

```ts
interface AssessmentCondition {
  condition_id: string;
  severity: 'blocker' | 'requirement' | 'warning';
  action: string;
  reason: string;
  evidence_refs: string[];
  requirement_refs: string[];
  allocation_refs: string[];
  affected_dimensions: string[];
}
```

Stable order: blocker -> requirement -> warning -> lexical `condition_id`.

### 11.3 Scenario assessment

```ts
interface ScenarioAssessment {
  carrier_mode: Exclude<CarrierMode, 'compare_both'>;
  assessment_state: AssessmentState;
  conditions: AssessmentCondition[];
  requirement_results: RequirementAssessment[];
  evidence_snapshot_id: string;
  reserve_capacity: 'tight' | 'sufficient' | 'resilient' | 'expandable' | 'unknown';
  logistics: 'compact' | 'moderate' | 'spread' | 'extreme' | 'unknown';
  complexity: 'low' | 'moderate' | 'high' | 'unknown';
  evidence_status: EvidenceDisposition;
  carrier_dependence: 'carrier_independent' | 'carrier_helped' | 'carrier_dependent' | 'unknown';
}
```

### 11.4 Comparable fit result

The numeric helper is deliberately separated from the state/evidence result.

```ts
interface ComparableFitResult {
  fit_policy_revision: string;
  fit_value: number; // integer 0–100 if the accepted model retains this scale
  provisional: boolean;
  trace: FitTrace;
}
```

Rules:

- no fit result for `not_assessable` or `not_supported`;
- `conditionally_supported` may have `provisional = true` only when the accepted policy allows it;
- conditional candidates are never promoted above Supported candidates merely because their provisional number is larger;
- a fit strategy/policy cannot change assessment state, evidence, allocations or conditions.

### 11.5 Finder candidate result

```ts
interface SearchCandidateAssessment {
  system_id64: string;
  comparison_context_id: string;
  candidate_plan: CandidatePlanRef | null;
  scenario: ScenarioAssessment;
  fit: ComparableFitResult | null;
  model_revision: string;
  mechanics_revision: string;
}
```

## 12. Finder ordering semantics

Default comparison ordering for a selected comparison context:

```text
Supported
  ↓
Conditionally supported
  ↓
Not assessable / Not supported shown outside the comparable ranked set
```

Within the Supported group:

1. accepted `fit_value` descending;
2. deterministic stable tie break only (e.g. system ID/name), unless the user explicitly chooses another factual secondary sort.

Within Conditional:

1. provisional fit descending if the policy permits a provisional fit;
2. otherwise deterministic stable ordering.

`not_assessable` and `not_supported` do not receive fake zero scores. They remain categorically different outcomes.

The UI may offer explicit sorts such as Nearest, Population, Name, Reserve Capacity, Logistics, or factual body count. Choosing one is a user preference and must be labelled as such.

## 13. Search execution layers

This contract deliberately separates semantics from eventual performance implementation.

### Layer 0 — factual prefilter

SQL/database filtering may cheaply narrow systems using canonical facts:

- distance/region;
- colonised/uninhabited state;
- star/body predicates/count ranges;
- permit state;
- other explicit factual filters.

A filter is not a score.

### Layer 1 — standard comparison assessment

For common role/programme contexts, production may later use versioned precomputed candidate assessments or another indexed representation **only if they are materialisations of the same R1 evaluator contract**.

No hidden COALESCE fallback to legacy/v4 score is permitted.

### Layer 2 — bounded detailed assessment

Opening a result performs/loads the full evidence/plan trace for the same candidate context and plan. User edits produce a new plan assessment.

### Performance rule

The physical storage/index design is deferred to a dedicated scale stage. Semantic shortcuts are not allowed merely because a universal scalar is easier to index.

## 14. Staleness/version gating

A comparable Finder result is valid only when its revisions are compatible with the active context:

- template revision;
- mechanics revision;
- classifier/evidence model revision;
- candidate generator revision where applicable;
- fit policy revision;
- evidence snapshot/data freshness requirements declared by the template.

A stale/unverifiable candidate must not be silently ranked as current. Depending on the failure it becomes either:

- not assessable;
- conditional with explicit stale-evidence condition;
- excluded from the current comparable result set.

There is no legacy score fallback.

## 15. First programme/role slice

Do not attempt every economy at once in the first implementation proof.

### Required first vertical slice

1. **Extraction role context** — answers a single-role search without inventing Refinery.
2. **`P-ER-01` Extraction / Refinery programme** — explicit pair/programme search and detailed handoff.
3. Existing factual-only/no-context search mode.

Why this slice:

- HR 1188 provides a genuine Extraction specialist positive control;
- HIP 70564 provides generic-volume saturation pressure;
- remote-material cases exercise logistics/distance;
- HMC + geological composability exercises the new evidence representation;
- it demonstrates both role search and programme search without prematurely creating ten profiles.

### Follow-up profiles required before production replacement

Production cutover of the existing economy/preset UX requires accepted role/programme mappings for Agriculture, Refinery, Industrial, HighTech, Military, Tourism and Extraction plus explicit handling for exploration/exobiology search.

## 16. Golden/control expectations for the first slice

No exact numeric fit targets are authorised yet.

### HR 1188

- must remain a positive Extraction-role candidate;
- HMC identity must not be lost when geological evidence is present;
- result must not depend on legacy Extraction 100.

### HIP 70564

- raw body abundance alone must not guarantee top Extraction/ER fit;
- surplus beyond programme sufficiency must plateau rather than increase forever.

### Blu Thua SU-W c2-5 / Praea Euq PS-U c2-3

- remote resources remain factual resources;
- logistics/practicality must distinguish them from equivalent compact evidence;
- carrier mode may alter logistics, not body evidence or physical capacity.

### Brambai DL-Y g32 / Eorgh Prou AA-A h24

- ammonia-life gas giant and true Ammonia World remain distinct even when the first slice does not use them directly; retain as classifier regression tests.

### Incomplete/contradictory controls

- missing/conflicting material evidence cannot become a low score;
- it must remain an explicit categorical state/condition.

## 17. Exact invariant test list for implementation

Before any implementation stage is accepted, automated tests must prove:

1. geological HMC retains HMC identity;
2. multi-modifier rocky retains all applicable modifiers;
3. Terraformable survives recognised-body classification;
4. geological signal count does not multiply body-local modifier strength;
5. volcanism and geologicals remain distinct;
6. true Ammonia and ammonia-life gas giant remain distinct;
7. no-body evidence remains Unknown;
8. surface-slot threshold boundaries are exact;
9. atmosphere bonus is independent/composable;
10. current gas-giant one-slot rule is protected;
11. factual filters do not mutate comparison context;
12. single-economy Extraction filter does not silently become ER unless the user/preset selected ER;
13. no comparison context produces no fit/universal development ranking;
14. explicit comparison context is returned on every ranked result;
15. same candidate plan/evidence snapshot is handed from Finder into detail assessment;
16. changing fit policy cannot change state/evidence/allocation;
17. unsupported/not-assessable results receive no numeric zero score;
18. conditional provisional fit cannot outrank a Supported candidate due only to numeric value;
19. surplus capacity plateaus for a fixed programme;
20. carrier changes logistics only except for requirements explicitly marked carrier-sensitive;
21. duplicate scarce evidence/allocation cannot be credited twice;
22. stale revision cannot fall back to legacy/v4 score;
23. result ordering and trace serialization are deterministic.

## 18. Search UI contract

The eventual Finder UI should make the comparison meaning visible without turning search into a planning form.

Minimum controls:

```text
Compare for: [selected role/programme]
```

Examples:

```text
Extraction
Extraction / Refinery specialist
Industrial / High Tech
Flexible home system
No comparison — factual search
```

Result cards for a comparison context show, compactly:

- assessment state;
- Plan/Role Fit where eligible;
- reserve/capacity;
- logistics;
- evidence indicator;
- one or two decisive conditions/warnings;
- label such as `Ranked for: Extraction / Refinery specialist`.

A conditional 94 must not visually outrank a supported 90.

Opening the card shows the exact candidate plan/evidence trace used by the list result.

No context -> cards show factual comparative dimensions and an invitation to choose `Compare for`.

## 19. Calibration contract

The fit-policy decision remains separate from this technical contract.

The accepted laboratory must compare the existing candidate families:

- constrained additive;
- balanced non-compensatory;
- bottleneck-capped;
- optionally Pareto/frontier presentation if useful.

For each candidate policy report:

- assessment-state/eligibility rates before scoring;
- fit distribution among comparable candidates only;
- 80+/90+/95+/100 shares if 0–100 retained;
- maximum ties;
- plateau behaviour;
- named control traces;
- rank inversions;
- sensitivity to logistics/carrier;
- double-allocation failures;
- explanation trace.

The production Finder and detailed view must use the **same accepted fit policy revision** for the same context.

## 20. Implementation stage boundary

This Review 2 defines semantics only.

The first code stage, once explicitly authorised, should remain isolated/read-only and should implement the smallest vertical proof:

```text
canonical composable body facts
→ Extraction role assessment
→ P-ER-01 candidate-plan generation/allocation
→ search-candidate result contract
→ detail handoff trace
→ fixture tests
```

It must not:

- alter production Finder ranking;
- change public API contracts;
- create/apply migrations;
- write production/V3 data;
- rebuild legacy ratings or archetypes;
- deploy;
- merge automatically;
- broaden to all programme types as a side effect.

Exact allowed repository files must be established from the target implementation branch at code-start review. Legacy/v4 scorer files are audit/reference-only unless explicitly authorised for isolation tests.

## 21. Review-2 acceptance decision requested

This contract is ready for explicit owner acceptance if the following are correct:

1. Finder should still rank systems, but only under a visible selected/inferred role/programme context.
2. Search-result ranking and detailed assessment must use the same evidence, mechanics and fit semantics.
3. Single-economy search must not silently invent a paired economy.
4. Standard programme search may auto-generate a deterministic candidate plan so the user does not have to manually plan every returned system.
5. Opening a ranked result must carry forward the exact candidate plan/evidence snapshot that produced its ranking.
6. Generic factual search with no comparison context has no hidden universal Development Score.
7. Supported candidates always outrank Conditional candidates by state; numeric fit cannot erase evidence/condition status.
8. Role/programme fit is the rating that dovetails with Finder; it is not a context-free system value.
9. First implementation proof is Extraction role + P-ER-01 + factual no-context search, fixture-backed/read-only, before any production cutover.

If accepted, the next action is to prepare the **first code-stage implementation brief/allowed-file list** from the current repository state. Coding should still require explicit authorization under the standing two-review rule.