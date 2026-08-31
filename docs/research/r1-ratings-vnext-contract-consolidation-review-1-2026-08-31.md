# ED-Finder R1 / Ratings vNext — Contract Consolidation Review 1

Date: 2026-08-31  
Status: **Review 1 — stage definition only; no coding authorised**  
Branch: `chatgpt-ed-new-ops-requests`  
Base checkpoint: `docs/research/v3-ratings-forensic-audit-checkpoint-2026-08-31-18.md`

## 1. Stage goal

Consolidate the completed Ratings/CRE forensic findings into the already accepted R1 product direction so the next implementation stage has one coherent contract.

The goal is **not** to invent another universal scoring engine. It is to define the canonical evidence and plan-relative assessment architecture that can replace legacy/v4 recommendation semantics safely.

The intended flow is:

```text
canonical/composable evidence
→ physical feasibility and locality facts
→ explicit programme/template requirements
→ allocation/coexistence evaluation
→ assessment state + conditions
→ optional provisional Plan Fit for that selected plan only
```

A system has no single context-free value. Assessment is always relative to an explicit development question, route, pair or programme.

## 2. Source-of-truth hierarchy

This stage must reconcile, rather than overwrite, the following sources:

1. **R1 New-Chat Handoff and Current-State Record (1 July 2026)** — authoritative product/safety direction:
   - no universal Overall/System/Development Score;
   - no Suggested Economy machine;
   - explicit plan-relative assessment;
   - two pre-code review rounds for every substantive stage;
   - final read-only evidence review before merge/deploy.
2. **R1 Assessment Laboratory v0/v0.3 contract** — accepted laboratory semantics:
   - `assessment_state` before Plan Fit;
   - structured conditions;
   - allocation truth must not change with fit strategy;
   - no network/persistence/production scoring coupling.
3. **R1 scoring/programme brainstorming ledger** — programme-template and allocation principles:
   - hard requirements before formulae;
   - no double-use of scarce evidence/allocation;
   - capacity plateaus after a fixed programme is fully supported;
   - carrier changes logistics only.
4. **Ratings/CRE forensic checkpoints 17–18** — current implementation failures and mechanics constraints:
   - composable body facts are collapsed into replacement buckets;
   - Terraformable/tidal/environmental facts are lost or not fetched;
   - legacy/v4 generic-body leakage and saturation;
   - physical slot estimates are stale and are not equivalent to programme feasibility;
   - immutable model/source provenance is required.
5. **CRE** — first source for accepted mechanics/evidence. External research is used only where CRE is genuinely missing, contradictory or patch-stale.

If any implementation proposal conflicts with items 1–3, the R1 product contract wins unless that contract is explicitly amended before code.

## 3. Explicit non-goals

This stage does **not** authorise:

- a universal Overall Score, System Value, Development Score or default best-system ranking;
- Suggested Economy or automatic economy recommendation without an explicit selected programme;
- reuse of legacy `ratings.score_*`, `economy_suggestion`, v4/archetype scores, ranks, caps or recommendation outputs as R1 evidence;
- a galaxy-wide rerate;
- production database writes or migrations;
- public Finder/System Detail wiring;
- a new planner/project tracker;
- live construction tracking;
- Raven-derived mechanics as authoritative truth;
- arbitrary weights or thresholds presented as Elite mechanics;
- guessing Unknown evidence as False, zero, Pristine or any other convenient default.

## 4. Architectural boundary to lock

R1 should have four deliberately separate layers.

### Layer A — Canonical evidence facts

Store what is known about each entity without scoring it.

Body identity and body modifiers must be independent/composable facts. For example:

```text
base identity: High Metal Content world
landable: true
terraformable: true
geologicals: present
volcanism: present / type-known
rings: absent
atmosphere: known-present
surface temperature: known
surface gravity: known
tidal lock: false
distance from arrival: known
```

A geological HMC must remain an HMC **and** geological. A ringed+geological rocky body remains rocky **and** ringed **and** geological. No replacement bucket may erase the base identity or another modifier.

Every material fact needs explicit availability/provenance state. At minimum the design must distinguish:

- known positive/value;
- known negative/absent where the source supports a negative assertion;
- unknown/missing;
- ambiguous;
- conflicting;
- not applicable.

Direct contradictions must withhold the affected derived claim rather than silently choosing whichever field is convenient.

### Layer B — Derived mechanics/feasibility facts

Derive bounded factual/provisional capabilities from Layer A, with explicit model provenance.

Examples:

- predicted surface construction capacity using the validated surface-slot family, including documented residual uncertainty;
- current-patch gas-giant orbital capacity;
- body/locality groupings;
- distance/logistics bands;
- candidate placement feasibility;
- strong/weak-link evidence or bounded projection tied to actual local-body placement;
- top-two/pair evidence only where the declared source/model can support it.

These are **not** programme scores. A slot prediction is not “slot efficiency”; body abundance is not “strong-link potential”; a body-count prior must never be labelled as an observed link mechanic.

### Layer C — Programme/template allocation

Assessment must consume an explicit programme template defining:

- player intent;
- target outcome/pair/route;
- named nodes/hubs;
- hard requirements;
- allocatable scarce inputs;
- coexistence rules;
- capacity ladder;
- carrier/logistics assumption;
- evidence requirements;
- known exclusions.

Assets may not be credited twice unless the mechanics contract explicitly permits shared use. Simultaneous programmes must prove coexistence after allocation, not simply sum generic counts.

### Layer D — Assessment result

Before any numerical fit, return:

- `assessment_state`: `not_assessable | not_supported | conditionally_supported | supported`;
- structured conditions;
- requirement-level outcomes and evidence bindings;
- reserve/capacity state;
- logistics state;
- complexity state;
- evidence status;
- carrier dependence.

Only after those facts/state are frozen may a laboratory or later approved product surface calculate **Plan Fit for the selected programme**. Fit strategy must not alter evidence, allocation, conditions or assessment state.

No Plan Fit is emitted when the selected strategy is ineligible under the contract.

## 5. Canonical feature families required by the forensic findings

Review 2 must define precise types/field names, but the following families are mandatory.

### Identity

- internal body identity and stable game/source identities;
- canonical body type/subtype;
- exact true Ammonia World identity kept distinct from gas giant with ammonia-based life;
- star identity plus main/secondary status without caller-dependent fabrication.

### Independent body/environment modifiers

- landability;
- terraformability;
- ring presence/evidence;
- geological presence;
- biological/organic presence;
- volcanism separately from geologicals;
- atmosphere presence/type;
- tidal locking;
- surface temperature;
- surface gravity;
- radius;
- distance from arrival;
- reserve/resource state when genuinely known.

Signal **presence/local predicate** must be distinguishable from raw signal count. A body with ten geological signals must not automatically act like ten independent economy/link modifiers.

### Provenance/temporal state

Every derived recommendation-significant fact must be bindable to:

- source kind/id;
- source record/payload revision or hash where available;
- observed/fetched timestamp;
- game/mechanics patch/effective period where known;
- classifier/model revision;
- source commit/model hash for derived outputs;
- direct observation vs imported fact vs prediction vs manual correction vs assumption.

A friendly label such as `3.4` is insufficient formula identity.

## 6. Mechanics-vs-product-preference boundary

Review 2 must explicitly label every rule/term as one of:

1. **Canonical/observed fact** — e.g. body subtype, observed ring evidence, actual distance.
2. **Mechanics rule** — versioned accepted Elite rule, with evidence strength and patch scope.
3. **Prediction/inference** — e.g. predicted surface slots where Frontier does not directly expose current count.
4. **Programme requirement** — a statement about what a selected plan needs.
5. **Product preference/heuristic** — convenience/ranking strategy chosen by ED-Finder, never presented as Elite truth.

No rule may silently jump categories.

## 7. Physical feasibility and slot contract

The validated surface-slot family should enter R1 as a **versioned feasibility prediction**, not as an overall value component.

The design must preserve:

- eligibility checks including temperature/gravity;
- radius bands;
- independent HMC / Terraformable / atmosphere / volcanism-or-geo modifiers;
- cap semantics;
- exact boundary fixtures;
- the two historical +1 residuals as documented uncertainty rather than hidden correction constants.

Orbital capacity must be separately versioned. Current-patch gas giants must not inherit the stale 3/5-slot model.

Programme capacity must then allocate actual/predicted slots to named nodes. Raw total slots alone do not prove a programme is buildable.

## 8. Locality/link contract

The redesign must stop converting system-wide body counts into link mechanics.

Any strong/weak-link claim used to support a programme must identify, at minimum:

- source node/facility if known/planned;
- target/local body or node;
- relationship locality;
- whether the link is observed, mechanics-derived, preview-derived or predicted;
- evidence/provenance;
- unresolved uncertainty.

Environmental modifiers that affect strong-link performance must not be relabelled as generic weak-link stability.

Where exact link magnitude/tie semantics remain unresolved, the programme result must expose a condition or Unknown rather than inventing a universal percentage buffer.

## 9. Candidate programme scope for the next technical contract

Do not create ten context-free archetypes again.

Review 2 should start with a deliberately small programme set already present in R1 work:

- `P-ER-01` — single-hub Extraction / Refinery specialist;
- `P-IHT-01` — single-hub Industrial / High Tech specialist;
- `P-WRG-01` — dual-hub Wregoe-style ER + IHT programme;
- `P-FLEX-01` — flexible platform with several independently credible future routes and explicit simultaneous-hub capacity.

The first implementation slice may be smaller than this list if Review 2 demonstrates a safer vertical slice.

## 10. Golden/control acceptance matrix

The technical contract must bind named controls to expected **behaviour**, not target scores.

### Existing R1 laboratory controls

- `wregoe_dual_dodec_control` — simultaneous differentiated allocation works; no generic average substitutes for allocation.
- `compact_sufficient_case` — compact sufficient evidence should be supportable without demanding pointless surplus.
- `plateau_30_vs_60_case` — doubling surplus bodies after programme sufficiency must not automatically improve the result.
- `remote_materials_carrier_case` — carrier changes logistics only; does not invent capacity/evidence/coexistence.
- `fake_flexibility_case` — the same body/slot/evidence cannot be credited twice to manufacture flexibility.
- `incomplete_evidence_case` — material unknown/conflict remains non-assessable/conditional as specified.
- `contradictory_allocation_case` — rich inventory cannot overcome mutually incompatible allocation.

### Forensic/golden regression controls

- Plaa Eurk ZR-M c7-2 — civilian ELW evidence must not become a Military specialist recommendation by generic leakage.
- Blu Thua SU-W c2-5 — remote material abundance must not be treated as equivalent to compact usable support.
- Blu Thua JS-J d9-1 — civilian ELW/WW/Terraformable-positive control.
- HIP 101924 — legitimate materials plus extreme-distance stress case.
- HIP 294 — stale/provenance and nearby-WW control.
- HR 1188 — genuine Extraction-specialist positive control.
- Brambai DL-Y g32 — ammonia-life gas giant must not count as true Ammonia World.
- Eorgh Prou AA-A h24 — true Ammonia World positive regression.
- HIP 70564 — generic-cap/surplus-volume saturation control.
- Praea Euq PS-U c2-3 — distributed/remote material stacking control.
- Wolf 359 / Lalande 21185 / UV Ceti / Yin Sector CL-Y d127 — sparse/low-evidence controls.

No fixture receives a required numerical Plan Fit in Review 1. Expected states/conditions/requirement outcomes are specified in Review 2 only where evidence is strong enough.

## 11. Mandatory invariant tests before any production design can be trusted

Review 2 must turn these into exact automated tests:

1. **Composable HMC:** adding geological evidence never removes HMC identity.
2. **Composable rocky:** rings/geo/bio can coexist without replacing rocky identity or each other.
3. **Terraformable preservation:** Terraformable survives classification for every recognised applicable planet type.
4. **Unknown preservation:** missing/no-body data never becomes zero/false/complete through empty aggregation.
5. **Ammonia identity:** true Ammonia World and ammonia-life gas giant remain distinct; contradiction withholds both claims.
6. **Signal locality:** signal count does not multiply a body-local modifier unless an accepted mechanic explicitly requires count.
7. **Tidal semantics:** tidal state is preserved independently and is not transformed into generic weak-link stability.
8. **Surface-slot boundaries:** below/at/above every radius/temp/gravity threshold plus modifier fixtures.
9. **Gas-giant capacity:** current-patch one-slot rule is regression protected.
10. **No double allocation:** scarce capacity/evidence cannot support two incompatible nodes simultaneously.
11. **Plateau:** irrelevant surplus after full fixed-programme support does not endlessly improve Plan Fit.
12. **Carrier isolation:** carrier assumption changes logistics only unless the programme contract explicitly makes another requirement carrier-sensitive.
13. **Strategy invariance:** changing fit strategy cannot alter evidence, allocation, conditions or assessment state.
14. **Version gating:** stale/unverifiable model outputs cannot silently become current recommendations.
15. **Determinism:** same canonical evidence + programme revision + strategy revision produces byte-stable trace/result ordering.

## 12. Calibration/distribution requirements

Any later Plan Fit model must be evaluated as a programme-relative helper, not a mechanics score.

For every candidate fit strategy report:

- eligibility/support-state rates before scoring;
- score distribution only among eligible comparable cases;
- share at 80+/90+/95+/100 if a 0–100 laboratory fit remains;
- maximum tie count;
- plateau behaviour;
- double-counting audit;
- carrier sensitivity;
- named-control traces;
- rank/order inversions between candidate strategies;
- contribution/decision trace sufficient to explain every material outcome.

A visually pleasant distribution is not an acceptance criterion by itself.

## 13. Repository/implementation surface — Review 1 expectation

No source code should change in this stage.

A subsequent approved implementation is expected to prefer a **new isolated R1 evidence/assessment path** rather than patching `build_ratings.py` or `build_archetype_scores.py` into correctness.

Legacy/v4 code may be read for migration/compatibility tests but its score outputs must not become R1 inputs.

Review 2 must identify exact repository paths after inspecting the current target branch/repository state. Do not assume the July local-only laboratory branch is remotely available or merged.

## 14. Risks to carry into Review 2

### Product-risk

- accidentally reintroducing universal ranking through a renamed “development potential” field;
- presenting programme fit as game truth rather than ED-Finder decision support;
- over-expanding the first programme catalogue.

### Data-risk

- source projections that cannot prove negative evidence;
- environmental fields present in schema but incompletely populated;
- stale/patch-mismatched observations;
- entity identity conflicts.

### Mechanics-risk

- unresolved exact link magnitudes/ties;
- deferred commodity guarantees;
- rare orbital-slot edge cases;
- surface-slot residuals.

These must reduce confidence or produce conditions where material; they must not be papered over with defaults.

### Engineering-risk

- accidental coupling to production `ratings`/archetype outputs;
- migration/public API scope expansion before semantics are proven;
- non-deterministic evidence ordering/provenance;
- hidden double allocation.

## 15. Review 1 acceptance criteria

Review 1 is accepted only if the reviewer agrees that:

1. Ratings vNext is an R1 **plan-relative assessment redesign**, not a replacement universal score.
2. Canonical body identity + modifiers are composable independent facts.
3. Unknown/ambiguous/conflicting states are first-class and cannot become zero/false by default.
4. Physical capacity, economy/link mechanics, programme allocation and product fit are separate layers.
5. Legacy/v4 score outputs are excluded as R1 evidence.
6. The existing R1 laboratory semantics and golden controls remain authoritative constraints.
7. The next step is a precise Review 2 technical contract, still with **no code**.

## 16. Review 2 requested output

The next pre-code review must return:

- precise domain types and field names;
- fact/evidence/provenance schemas;
- composable classifier rules;
- exact first programme/template contract(s);
- requirement-to-evidence binding shape;
- allocation model and deterministic ordering rules;
- surface/orbital feasibility interfaces;
- locality/link evidence interfaces;
- assessment-state precedence;
- Plan Fit eligibility boundary and strategy isolation;
- exact fixture expectations/tests;
- source-boundary/isolation rules;
- exact proposed changed-file list;
- explicit migration/API/network/persistence/deployment statement.

**No coding is authorised by this document.**