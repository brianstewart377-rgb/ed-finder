# System Assessment Continuity Ledger v1

**Status:** Drafted for independent review as a documentation-only continuity record.

**Purpose:** Preserve the R1 Assessment Laboratory lineage while establishing the future home of programme-specific system assessment in **CPE / System Assessment Engine**. This ledger does not authorise implementation, migration, fixture changes, evidence collection, scoring, ranking, or architecture selection.

## 1. Current truth in one page

```text
CRE
  Research truth: evidence, mechanics, provenance, observations, contradictions,
  confidence, planner-safe releases, observed-state publications
        ↓ pinned release and snapshot
CPE / System Assessment Engine
  Programme-specific candidate-system assessment, capacity sufficiency,
  Carrier scenarios, Plan Fit, comparison-ready outputs
        ↓ assessment result
CPE / Colony Plan Construction
  Player constraints, protected assets, layouts, sequence, alternatives,
  validation gates, plan outputs
        ↓
ed-finder
  Presentation, exploration, comparison display, DEV-only R1 laboratory
```

The R1 Assessment Laboratory is **not discarded**. It remains the frozen DEV-only prototype and control-suite lineage until a future CPE implementation passes equivalent accepted controls.

## 2. Lifecycle vocabulary and tie-break

Every material item has one primary label:

- **Accepted prototype semantic** — accepted R1 behaviour that a future CPE implementation must preserve.
- **Accepted future design rule** — accepted forward constraint that is not yet executable behaviour.
- **Pending evidence** — cannot be admitted without an evidence inventory or validation.
- **Deferred control** — reserved named control without an admitted payload or proof role.
- **Historic reference only** — retained only for provenance or comparison; cannot affect a live decision.
- **Stale documentation debt** — can still mislead a live decision, handoff, review, or implementation action.
- **Future CPE implementation target** — an accepted semantic destination, not currently implemented in CPE.

**Tie-break:** use `Stale documentation debt` rather than `Historic reference only` whenever an item can still mislead live work.

## 3. Accepted R1 semantics to preserve

| Semantic | Primary label | Future treatment |
|---|---|---|
| Four assessment states: `not_assessable`, `not_supported`, `conditionally_supported`, `supported` | Accepted prototype semantic | Reimplement in CPE from an accepted contract and controls. |
| Resolution order: unknown or contradictory evidence dominates; mandatory unmet follows; conditional outcomes follow; otherwise supported | Accepted prototype semantic | Preserve verbatim. |
| Missing/contradictory evidence cannot be rescued by Carrier, strategy, or later logic | Accepted prototype semantic | Preserve verbatim. |
| Exclusive role-or-question lens, context-only in the current prototype | Accepted prototype semantic | Preserve unless a later contract supplies real lens-specific evidence. |
| Carrier can affect only carrier-sensitive, non-shared logistics requirements | Accepted prototype semantic | Preserve verbatim. |
| Carrier comparison order is `no_carrier`, then `carrier_available` | Accepted prototype semantic | Preserve verbatim. |
| Plan Fit is secondary and consumes accepted assessment output | Accepted prototype semantic | Preserve verbatim. |
| Plan Fit states: `no_plan_fit`, `blocked_plan_fit`, `provisional_plan_fit`; no `supported_plan_fit` | Accepted prototype semantic | Preserve until a later explicit contract changes it. |
| Explicit fixed strategies only; no inferred strategy, recommendation, ranking, or winner | Accepted prototype semantic | Preserve verbatim. |
| Determinism, immutability, sorted trace/provenance, local fixture-backed DEV-only operation | Accepted prototype semantic | Preserve as migration controls. |
| No universal score, rank, best-system result, or automatic selection | Accepted prototype semantic | Preserve until evidence-backed comparison design is separately accepted. |

## 4. Fixture-only boundary

The following are fixture-only forward reconstruction material, not game truth:

- all evidence payloads, fact keys, values, conditions, and outcomes in the five R1 fixtures;
- the four-requirement template and its mandatory/carrier/shared flags;
- the two fixed strategy records;
- any interpretation of a fixture result as a real Elite Dangerous mechanic or real candidate-system assessment.

A future CPE implementation may preserve the **behavioural control** of a fixture without copying its evidence payload as research truth.

## 5. Deferred controls

| Item | Current status | Primary label | Admission gate |
|---|---|---|---|
| `plateau_30_vs_60_case` | Documentation-only capacity-sufficiency intent. No fixture, test, UI, payload, threshold, or expected result. | Pending evidence | CRE-backed evidence inventory; narrow proof question; complete requirement rows; expected output; independent review; owner authorisation. |
| `wregoe_dual_dodec_control` | Documentation-only deferred control name. No fixture, test, UI, payload, or expected result. | Deferred control | Same gate as above. No inference from the name, memory, unrelated Wregoe/Dodec references, or numerical comparison. |

`30` and `60` are illustrative labels only. Extra bodies are neutral only after every named mandatory requirement is met and the surplus changes no named requirement or constraint.

## 6. Ownership map

| Asset or responsibility | Current location | Future authority | Boundary treatment |
|---|---|---|---|
| Raw evidence, sources, observations, claims, mechanics, experiments, contradictions, unknowns, confidence, caveats | CRE | CRE | CPE consumes published planner-safe input; never rewrites it as fact. |
| CRE knowledge releases and observed colony-state snapshots | CRE | CRE | Pinned CPE inputs. |
| R1 assessment states, trace rules, Carrier constraints, Plan Fit semantics | `ed-finder` R1 lab | CPE / System Assessment Engine | Migrate semantically, never by fixture-copy. |
| Capacity-sufficiency/plateau rule | Stage 5 documentation | CPE / System Assessment Engine | Remains future design until evidence-backed control admission. |
| Candidate-system comparison inside a named programme and scenario | Not yet implemented | CPE / System Assessment Engine | Do not reduce to a universal score. |
| Player objectives, protected assets, constraints, layouts, sequence, alternatives, validation | CRE drafts and future CPE | CPE / Colony Plan Construction | CPE owns plan-specific context and outputs. |
| DEV lab UI, future comparison display, search/exploration presentation | `ed-finder` | ed-finder | Presentation only. |

## 7. Keep / defer / migrate / historic-only register

| Item | Required treatment | Primary label |
|---|---|---|
| `frontend-v2/src/lab/r1-assessment-lab/**` | Keep frozen as prototype/control lineage; migrate semantics later | Future CPE implementation target |
| R1 evaluation and Plan Fit tests | Keep as mandatory migration controls | Accepted prototype semantic |
| `R1_RECONSTRUCTION_CONTRACT_V1.md` | Keep as assessment reconstruction authority | Accepted prototype semantic |
| `R1_STAGE4_PLAN_FIT_CONTRACT_V1.md` and Stage 4C presentation contract | Keep as Plan Fit authority | Accepted prototype semantic |
| `R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md` | Keep as capacity-sufficiency evidence discipline | Accepted future design rule |
| `plateau_30_vs_60_case` | Defer | Pending evidence |
| `wregoe_dual_dodec_control` | Defer | Deferred control |
| Stage 6B and 6C contracts | Keep as cross-repository governance authority | Accepted future design rule |
| Stage 5 acceptance records and Stage 6A audit report | Retain for provenance | Historic reference only |
| CPE README old ownership wording | Corrected in separate documentation PR | Stale documentation debt until merged |
| Stage 6C current-stage unmerged wording | Corrected by this documentation cleanup | Stale documentation debt until merged |
| PR #293 | Superseded by #294; close only with explicit owner authorisation | Stale documentation debt until closed |
| CRE summary-index mismatch from Stage 6A | CRE-side follow-up; not changed here | Stale documentation debt |

## 8. Known collision and traceability cautions

### `Dodec` collision

The live station-type feature and related source references using `Dodec` are unrelated to `wregoe_dual_dodec_control`. No future work may infer deferred-control semantics by grepping the token alone.

### PR traceability

PRs #297 and #298 are linked to their commits by the accepted project records because their commits do not embed the PR number in the commit subject. Future closeouts must explicitly record PR number, reviewed head, merge commit, and merge method to keep recovery auditable.

### Confirmed Stage 2/3 foundation

Live GitHub metadata independently confirmed the early R1 lineage:

| PR | Result | Merge commit |
|---|---|---|
| #280 — Stage 2B pure R1 assessment core | Merged | `220c870f89a5af7f98adb88578373dbc3a681a9c` |
| #281 — Stage 3A lens context | Merged | `b6529e70ddbdcc26d46ce742eea793273138c635` |
| #282 — Stage 3B DEV-only R1 assessment lab | Merged | `98b4bacf1d799e7937b449210046659b3e96615b` |
| #283 — Stage 3B merge record correction | Merged | `83f4e4bc9829c173979fce5aa0bda734174ca55a` |

## 9. Minimum pre-code documentation package

Before any CPE code work, the project needs only:

1. this Continuity Ledger;
2. the CPE System Assessment Roadmap;
3. the Project Continuity and Merge Closeout Protocol;
4. an accurate `CURRENT_STAGE.md` working point;
5. CPE README ownership correction;
6. a later CPE documentation contract defining the first System Assessment request/result shapes.

Explicitly excluded: new SRE repository, database, API, shared package, runtime/storage/transport decision, scoring formula, external evidence collection, R1 code change, CPE scaffolding, CRE source change, or deployment.

## 10. Next safe action

Review this ledger alongside `CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`, `PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`, and the separate CPE documentation PR. After independent review and separate owner merge authorisation, begin the CPE documentation foundation—not implementation.
