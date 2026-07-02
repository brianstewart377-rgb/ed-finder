# R1 Stage 5B — Evidence Discipline Contract v1

**Status:** Drafted for independent review on 2026-07-02.

This is a documentation-only forward-design contract. It establishes the evidence standard for a possible later R1 capacity-sufficiency investigation. It does not claim to recover historical R1 behavior and it does not authorize any fixture, code, UI, production behavior, external lookup, or implementation.

## 1. Governing rule

No R1 assessment, Plan Fit result, comparison statement, or later forward-reconstruction conclusion may be stronger than the traceable evidence chain supporting it.

A valid conclusion has this shape:

```text
source record
→ normalized evidence fact
→ named programme requirement or constraint
→ requirement outcome
→ bounded Assessment or Plan Fit consequence
```

Every arrow must be inspectable. A missing, contradictory, stale, out-of-scope, or unsupported arrow limits the conclusion accordingly.

## 2. Scope

This contract governs only the evidence discipline for a potential future capacity-sufficiency plateau control, provisionally associated with the deferred name `plateau_30_vs_60_case`.

The owner-provided forward-design intent is:

> Once a system meets every explicit requirement for a defined extraction/refining programme, additional bodies that do not satisfy an otherwise unmet requirement or resolve an otherwise present constraint are neutral. Raw total body count must not create a linear score, rank, recommendation, preference, or automatic conclusion.

This is forward-design intent. It is not evidence of lost historical R1 semantics and must never be labelled as such.

The values `30` and `60` are illustrative labels only. They are not universal thresholds, general Elite Dangerous facts, or requirements in themselves.

## 3. Exact non-goals

Stage 5B does not add or change:

- any R1 fixture, requirement, condition, template, Assessment result, or Plan Fit result;
- any R1 core, test, DEV-lab UI, route, navigation item, provider, store, API, persistence behavior, network request, or production asset;
- a universal body-count threshold;
- a score, rank, best-system result, recommendation, preference, winner, or automatic selection;
- live-data dependence at runtime;
- a claim that any historical R1 fixture meaning has been recovered;
- an implementation stage, deployment, or system scouting result.

## 4. Source classes and labelling

Every evidence fact used in a later R1 contract must identify its source class and provenance. The permitted classes are:

### 4.1 Repository evidence

A fact recorded in the canonical repository.

Required provenance:

- repository path;
- exact commit SHA or immutable ref;
- relevant line, object, or record identifier;
- retrieval date;
- scope of what the source does and does not establish.

Repository evidence may establish accepted project contracts, current fixture content, existing types, accepted test behavior, or durable decisions. It cannot establish lost behavior that is absent from the repository.

### 4.2 External observed evidence

A fact from a public, attributable source about a real system or game state.

Required provenance:

- source name and stable reference;
- canonical system identifier;
- retrieval date and time;
- data field or display location used;
- whether the fact is direct, inferred, incomplete, stale, or conflicting;
- any material caveat about source coverage or update timing.

External observed evidence may support a forward reconstruction input. It must not be used as a live runtime dependency for the DEV-only lab.

### 4.3 Owner-provided forward-design intent

A requirement, boundary, definition, or objective explicitly supplied by the owner.

Required provenance:

- date of owner statement;
- concise statement of the accepted intent;
- distinction between a design decision and an observed game fact;
- the later contract or decision record that adopts it.

Owner intent may authorise a future forward reconstruction. It does not establish historic R1 semantics or convert an unknown external fact into a known fact.

### 4.4 Fixture representation

A deterministic, local evidence representation admitted by a later written contract.

Required provenance:

- fixture ID and revision;
- the precise source facts or owner-approved design inputs represented;
- explicit transformation or normalization rules;
- an exact mapping from source evidence IDs to fixture evidence IDs;
- an explicit statement of what was intentionally omitted.

A fixture is a bounded representation, not an independent source of truth.

### 4.5 Derived evidence fact

A transparent conclusion computed from one or more prior evidence facts.

Required provenance:

- derived fact ID;
- ordered dependency IDs;
- deterministic derivation rule;
- resulting value;
- scope and limitations;
- explanation of why the derivation does not create a score, rank, preference, or recommendation.

A derived fact must never hide a qualitative judgement behind a raw count or aggregate.

## 5. Evidence status rules

Each fact must be treated as one of:

- **known:** directly established within the stated source scope;
- **missing:** required evidence was not supplied or could not be verified;
- **contradictory:** credible sources or records conflict;
- **not applicable:** the named requirement does not apply in this programme context;
- **derived:** transparently computed from identified known facts, with its derivation recorded.

Rules:

1. Missing evidence is not a positive fact.
2. Contradictory evidence is not averaged, guessed away, or silently treated as sufficient.
3. An incomplete or stale source must not be represented as complete current knowledge.
4. A source outside the stated programme scope must not satisfy a requirement merely because it is favorable in another scope.
5. A claim may be no broader than the least-supported evidence fact or derivation in its chain.

## 6. Programme-first comparison rule

No system comparison may begin with total body count.

Before comparing candidate systems, the relevant programme/template must define a finite requirement table. For every requirement, the table must specify:

- requirement ID and neutral label;
- kind: eligibility, capacity, logistics, or constraint;
- whether it is mandatory;
- the exact capability or constraint being assessed;
- the admissible evidence fields;
- the success condition;
- the treatment of missing or contradictory evidence;
- whether carrier mode could affect it under the accepted R1 boundaries;
- the exact reason extra bodies could or could not change it.

Total body count may be recorded as context. It cannot be a proxy for capability, capacity, quality, or desirability unless a later contract explicitly defines a bounded requirement that uses a count and supplies its evidence basis.

## 7. Capacity-sufficiency plateau rule

A later control may test a plateau only after the programme requirements in Section 6 are explicit.

For two candidate systems, a larger total body count is neutral only when all of the following are evidenced:

1. The smaller candidate meets every mandatory programme requirement.
2. The larger candidate also meets every mandatory programme requirement.
3. Each additional body or group of bodies in the larger candidate does not:
   - satisfy a requirement unmet by the smaller candidate;
   - add a distinct required material or output coverage;
   - add a qualifying body type, slot, capacity, or validated logistics capability relevant to a named requirement;
   - resolve a shared or non-shared constraint present in the smaller candidate;
   - change an accepted carrier-sensitive logistics outcome;
   - introduce a separately defined required capability.
4. The comparison does not hide any non-count distinction that changes a named requirement or constraint.

When all four conditions hold, raw surplus body count must not by itself change the resulting requirement outcomes, Assessment state, conditions, Plan Fit state, or Plan Fit reasons.

The converse is equally important: a larger system may differ materially when its extra bodies change a named requirement or constraint. This contract does not declare large systems neutral by default.

## 8. Required evidence inventory before a later fixture contract

Before any fixture implementation is proposed, a read-only evidence inventory must provide four categories of candidate evidence:

1. **Below-sufficiency candidate:** at least one named mandatory requirement remains unmet or unknown.
2. **Sufficient baseline candidate:** every named mandatory requirement is evidenced as met with a comparatively lower relevant-body count.
3. **Neutral-surplus candidate:** materially more total bodies than the baseline, with evidence that the additional bodies alter no named requirement or constraint.
4. **Additive-surplus candidate:** more bodies and evidence that the additional bodies do add a named capability or resolve a named constraint.

For each candidate, the inventory must record:

- total body count where known, clearly labelled as context;
- counts of bodies relevant to each named requirement;
- body types, slots, material/output coverage, and logistics facts used by each requirement;
- source records and retrieval times;
- direct versus inferred facts;
- missing and contradictory information;
- a per-extra-body or per-extra-group explanation of whether it changes any named requirement or constraint.

The inventory may conclude that the available evidence is insufficient. That is a valid result and must not be resolved by assumption.

## 9. Deterministic fixture admission rules

A later fixture may be proposed only after the evidence inventory is reviewed and an owner-approved written contract supplies:

1. an exact fixture ID and revision;
2. one narrow proof question;
3. the selected template and every requirement evaluation row;
4. complete fixture-owned evidence facts with provenance;
5. exact expected Assessment scenario results and ordered conditions;
6. a statement of any permitted carrier effect;
7. a statement of whether Plan Fit is relevant; absence is the default;
8. exact tests proving the plateau and additive-surplus contrasts;
9. a narrow file allowlist and explicit non-goals;
10. an independent read-only review and separate owner authorisation before implementation.

No fixture may be admitted merely because it has a familiar name, a compelling narrative, a larger number, or a plausible-looking data set.

## 10. Presentation boundary

Any later DEV-only presentation must render the evidence chain without turning it into an opaque total.

It may show neutral, traceable information such as source scope, evidence IDs, requirement IDs, availability, conditions, and caveats. It must not introduce scoring, ranking, recommendation, best-system claims, traffic-light shorthand, or automatic selection.

## 11. Stage 5B deliverable and next safe action

The immediate Stage 5B deliverable is this reviewed evidence-discipline contract only.

After owner acceptance, the next safe action would be a separately authorised, read-only evidence inventory under Section 8. That inventory would gather and assess evidence; it would not alter R1 code or create a fixture.
