# R1 Stage 5A — Control-Fixture Discovery Record v1

**Status:** Drafted for independent review on 2026-07-02.

This is a documentation-only discovery record. It does not claim to recover lost historical fixture semantics and it does not authorise any implementation.

## 1. Purpose and boundary

Stage 5A investigates two names explicitly reserved by the R1 reconstruction contract:

- `wregoe_dual_dodec_control`
- `plateau_30_vs_60_case`

The only question in scope is whether the current repository contains enough deterministic, reviewable evidence to assign either name a precise proof role in a later DEV-only R1 stage.

Stage 5A does not add or change:

- application code;
- R1 fixture data;
- Stage 2B assessment semantics;
- Stage 4B Plan Fit semantics;
- the DEV lab UI;
- normal routes, navigation, providers, stores, APIs, network, persistence, production assets, configuration, deployment, scoring, ranking, recommendation, planning, or exports.

## 2. Sources inspected

This discovery is based only on the current canonical repository at the Stage 4C closeout baseline.

1. `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`
   - It explicitly names both controls and says neither is part of Stage 2B unless a later written contract gives it a specific proof role.
2. `frontend-v2/src/lab/r1-assessment-lab/core/fixtures.ts`
   - The active fixture registry contains five fixture IDs only:
     - `compact_sufficient_case`
     - `incomplete_evidence_case`
     - `contradictory_allocation_case`
     - `fake_flexibility_case`
     - `remote_materials_carrier_case`
3. `frontend-v2/src/lab/r1-assessment-lab/core/types.ts`
   - It defines the minimum current fixture shape: `fixtureId`, `fixtureRevision`, immutable fixture evidence with fixture provenance, and requirement evaluations.
4. Repository-wide source search for both reserved names.
   - No current source, test, or document reference beyond the Stage 2B reconstruction contract was found.

## 3. Evidence finding

Neither reserved name has a recoverable current fixture payload.

For each name, the repository lacks all of the following:

- a fixture revision;
- evidence facts and fixture provenance;
- requirement evaluation rows;
- exact expected Assessment state or carrier-mode behavior;
- structured conditions and evidence links;
- a defined proof question;
- a stated relation to an accepted invariant;
- a test assertion;
- an accepted Stage 4B Plan Fit interaction, if any.

The names themselves are not sufficient evidence from which to infer those missing semantics.

## 4. Per-control outcome

### 4.1 `wregoe_dual_dodec_control`

**Finding:** Not admitted to the active R1 fixture registry.

**Reason:** The current repository contains only the name in a deferral note. It contains no deterministic payload, expected output, or proof role. The name must not be used to infer system-specific, station-specific, material, market, logistics, or planning semantics.

**Stage 5A result:** No fixture, test, UI option, Assessment behavior, or Plan Fit behavior is authorised for this name.

### 4.2 `plateau_30_vs_60_case`

**Finding:** Not admitted to the active R1 fixture registry.

**Reason:** The current repository contains only the name in a deferral note. It contains no deterministic payload, expected output, threshold definition, capacity interpretation, or proof role. The name must not be used to infer a numerical rule, comparison rule, threshold, ranking, recommendation, or planning outcome.

**Stage 5A result:** No fixture, test, UI option, Assessment behavior, or Plan Fit behavior is authorised for this name.

## 5. Non-inference rule

A later R1 stage must not create semantics for either reserved name from:

- the wording of the name;
- lost-worktree recollection;
- chat history alone;
- assumptions about Wregoe, Dodecs, capacity, or colonisation mechanics;
- an apparent numerical comparison;
- an inferred best, preferred, recommended, or ranked result.

A future fixture can be a forward reconstruction only after its proof role and payload are explicitly approved. It must never be presented as recovered historical behaviour unless source evidence exists and is recorded separately.

## 6. Re-admission gate for any later fixture

Before either reserved name may enter code, a separate written contract must define, for that one fixture:

1. the exact fixture ID and fixture revision;
2. a narrow proof question that is not a score, rank, recommendation, winner, or production feature;
3. a complete deterministic `FixtureAssessmentScenario` payload compatible with the then-current accepted types;
4. fixture-owned evidence facts, each with availability and fixture provenance;
5. exactly one requirement-evaluation row for every requirement in the selected template, including evidence ID lists and base outcomes;
6. exact expected Assessment result(s), carrier-mode behavior, conditions, ordering, and proof assertions;
7. whether the fixture has any Stage 4B Plan Fit role; absence is the default unless explicitly specified;
8. the exact test additions and their expected assertions;
9. a narrow file allowlist and explicit exclusions;
10. an independent read-only review and separate owner authorisation before implementation.

No current Stage 5A finding supplies items 1–9 for either name.

## 7. Stage 5A conclusion

The current evidence is insufficient to assign a responsible proof role to either deferred control. Both remain intentionally absent from the active R1 fixture registry.

This is a successful discovery result: it preserves the existing deterministic boundary by refusing to invent semantics. It does not block future forward reconstruction, but it does require a new, explicit, evidence-backed contract before either name can be introduced.

## 8. Next safe action

Obtain an independent read-only review of this discovery record and the corresponding `CURRENT_STAGE.md` update. Do not create an implementation branch, modify fixtures, tests, R1 core, the DEV lab UI, the normal app, or deployment configuration until the owner accepts the reviewed Stage 5A conclusion and separately authorises any later stage.
