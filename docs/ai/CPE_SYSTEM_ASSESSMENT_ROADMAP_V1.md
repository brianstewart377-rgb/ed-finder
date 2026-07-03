# CPE System Assessment Roadmap v1

**Status:** Drafted for independent review. Documentation-only programme roadmap.

**Purpose:** Turn the accepted R1 Assessment Laboratory lineage into a durable, evidence-first future capability without burying it in generic planning work, duplicating CRE research truth, or prematurely creating a separate SRE repository.

## 1. Target operating model

```text
CRE
  Evidence, mechanics, provenance, observations, contradictions, uncertainty,
  planner-safe knowledge releases, observed-state snapshots
        ↓
CPE / System Assessment Engine
  Candidate-system assessment against an explicit programme, requirements,
  Carrier scenario, and pinned CRE inputs
        ↓
CPE / Colony Plan Construction
  Player-specific layouts, protected assets, sequence, alternatives,
  trade-offs, validation gates
        ↓
ed-finder
  Presentation, exploration, comparison display
```

## 2. Named CPE pillars

### CPE / System Assessment Engine

Evaluates a candidate system against an explicit colony programme. It owns:

- programme templates and named requirements;
- requirement evaluation;
- assessment states and evidence/condition trace;
- capacity-sufficiency and plateau controls;
- Carrier scenarios;
- Plan Fit for explicit strategies;
- candidate-system comparison within compatible programme/scenario context;
- comparison-ready, caveated outputs.

It does **not** own raw research evidence, source provenance, mechanics, confidence/contradiction resolution, player-plan construction, or presentation.

### CPE / Colony Plan Construction

Turns an assessed system and player intent into candidate plans. It owns:

- objectives, preferences, risk tolerance, protected assets, and prohibited actions;
- candidate layouts, facility choices, sequencing, alternatives, and trade-offs;
- expected effects and validation gates;
- plan-specific outputs.

It consumes System Assessment; it must not silently recreate its requirement logic or CRE research truth.

## 3. R1 continuity rule

The R1 Assessment Laboratory in `ed-finder` remains a **frozen DEV-only prototype and CPE control-suite lineage**.

Future CPE work must:

- preserve accepted R1 semantics;
- reimplement them against equivalent controls;
- keep the R1 lab unchanged as reference until the CPE controls pass;
- never copy fixture payloads into CPE as real-world facts;
- never infer semantics for deferred controls from their names, chat history, or unrelated repository references.

## 4. Hard rules

1. Assessment state is primary; Plan Fit is secondary and explicit-strategy-gated.
2. Missing, contradictory, stale, incomplete, unsupported, or out-of-scope evidence must remain visible. It cannot silently become positive.
3. Carrier effects are limited to accepted carrier-sensitive, non-shared logistics requirements.
4. No universal score, rank, winner, recommendation, or automatic selection is introduced before requirement-level assessment and controls justify it.
5. No candidate-system comparison begins with raw total body count.
6. Extra bodies are neutral only when every mandatory requirement is met and they change no named requirement or constraint.
7. `plateau_30_vs_60_case` and `wregoe_dual_dodec_control` remain out of code until a CRE-backed evidence inventory and later admission contract exist.
8. CPE consumes pinned CRE publications. It must not recreate CRE evidence truth or access CRE private storage.
9. No merge is complete until the continuity records are updated under the merge-closeout protocol.

## 5. Programme roadmap

| Phase | Status at this roadmap baseline | Deliverable | Gate before next phase |
|---|---|---|---|
| **Cleanup 0** — Stage/status hygiene | Drafted | Correct Stage 6C working point; record reviewed head and merge commit; resolve superseded bookkeeping when authorised | Independent review and owner merge authorisation |
| **Cleanup 1** — R1 freeze and designation | Drafted | Declare R1 lab the frozen DEV-only prototype/control lineage | Recorded in current stage, ledger, and decisions |
| **Cleanup 2** — Continuity Ledger | Drafted | One ownership/lifecycle/migration inventory | Independent review and owner merge authorisation |
| **Cleanup 3** — System Assessment Roadmap | Drafted | This strategic programme record | Independent review and owner merge authorisation |
| **Cleanup 4** — CPE documentation foundation | Drafted separately | Correct CPE README and establish its two pillars | Independent review and owner merge authorisation |
| **Cleanup 5** — Merge closeout protocol | Drafted | Durable recovery rule for all future merges | Independent review and owner merge authorisation |
| **A0** — Continuity audit | Owner-accepted | Read-only R1→CPE audit, with repository pins and lifecycle findings | Complete; informs cleanups |
| **A1** — CPE documentation foundation | Not started | CPE top-level documentation, first-system-assessment scope, ownership clarity | Cleanup package merged |
| **A2** — First CPE System Assessment contract | Not started | Documentation-only logical Assessment Request/Result contract with every field owned | A1 accepted; no implementation authority |
| **A3** — Bounded assessment core | Not started | Narrow CPE implementation of accepted R1 assessment semantics against synthetic labelled controls | A2 accepted; separate implementation authorisation |
| **A4** — Capacity-sufficiency evidence inventory | Not started | CRE-backed read-only inventory for below-sufficiency, compact-sufficient, neutral-surplus, additive-surplus cases | Separate authorisation; inventory may conclude insufficient evidence |
| **A5** — Deferred control admission | Not started | Evidence-backed contract and tests for 30-v-60 and/or Wregoe control only after A4 | A4 reviewed; owner authorisation |
| **A6** — Plan Fit and comparison | Not started | Mature CPE Plan Fit and comparable candidate-system outputs | Assessment core and controls accepted |
| **B** — Colony Plan Construction | Not started | Candidate layouts, sequencing, alternatives, protected-asset and validation handling | System Assessment produces trusted results |
| **C** — ed-finder graduation | Not started | Presentation of stable CPE outputs beyond DEV-only laboratory | CPE outputs and contracts stable |

## 6. A0 findings that govern all later work

The owner-accepted Programme A0 audit established:

- all three repositories were reviewed at fixed pins;
- accepted R1 prototype semantics are real and must be preserved;
- the five current fixtures and two current strategies are fixture-only forward reconstruction material, not game truth;
- `plateau_30_vs_60_case` and `wregoe_dual_dodec_control` have no admitted payload, expected result, test, UI, or active behaviour;
- Stage 6B establishes the cross-repository ownership model;
- CPE README ownership wording required correction;
- Stage records require explicit, durable closeout to prevent stale recovery state.

## 7. First CPE System Assessment contract shape

This is a logical target only. It is not an executable schema or implementation authorisation.

### Assessment Request

- pinned CRE Knowledge Release;
- pinned CRE Observed Colony-State Snapshot;
- named programme/template/revision;
- finite named requirements and constraints;
- explicit Carrier scenario;
- explicit assessment lens or question where applicable;
- declared player constraints and scope limits;
- treatment choice for unknown, contradictory, stale, or withheld CRE inputs.

### Assessment Result

- input pins and contract identity;
- assessment state;
- per-requirement outcomes;
- evidence/provenance and caveat trace;
- conditions, missing/contradictory/withheld limitations, and validation gates;
- Carrier scenario comparison where applicable;
- capacity-sufficiency finding;
- Plan Fit state only when an explicit compatible strategy is supplied;
- bounded comparison-ready result without pretending to be a universal score.

The required order is:

```text
CRE evidence and named requirements
        ↓
Assessment state
        ↓
Plan Fit for explicit strategy
        ↓
Later comparison or rating display
```

## 8. Capacity-sufficiency and the 30-v-60 control

The future control suite must prove four distinct cases:

1. **Below sufficiency:** at least one mandatory requirement is unmet or unknown.
2. **Compact sufficient baseline:** every mandatory requirement is met with fewer relevant bodies.
3. **Neutral surplus:** more total bodies, but no additional body changes a named requirement or constraint.
4. **Additive surplus:** extra bodies genuinely add required coverage, relevant capacity, qualifying body/slot capability, logistics improvement, or constraint resolution.

Only the fourth case can improve an assessment because of the extra bodies. The 30/60 labels are illustrative; no global threshold is implied.

## 9. Why there is no separate SRE repository

A separate SRE repository is not justified now because it would:

- duplicate CPE programme inputs or Plan Fit logic;
- create a second source-of-truth boundary before the CPE contract exists;
- force runtime/storage/package/API choices that Stage 6B explicitly leaves open;
- risk copying R1 fixture material as if it were research truth;
- multiply continuity and merge-closeout debt.

The System Assessment Engine is a protected, first-class CPE domain. It may be extracted later only after stable contracts, independent consumers, control maturity, and a clear no-duplication case exist.

## 10. Agent roles and review discipline

| Role | Responsibility |
|---|---|
| Owner | Decides objectives, accepts audits, authorises implementation and merges. |
| Independent auditor/reviewer | Read-only audit, contract review, control challenge, and scope verification. |
| ChatGPT | Programme governance, cross-repository boundary guard, contract/continuity drafting, review coordination. |
| Trae or focused implementation agent | One bounded implementation story on one branch after contract and owner authorisation. |

Rules:

- one writer per branch;
- one bounded objective per PR;
- an independent reviewer checks every non-trivial change;
- no merge without exact-head owner authorisation;
- no external evidence or live-game conclusion without explicit scope;
- no CPE conclusion stronger than its weakest critical CRE dependency.

## 11. Current next safe action

Independently review the documentation-only cleanup package and the separate CPE documentation-foundation change. After explicit owner merge authorisation, begin **A1 CPE documentation foundation**. Do not start A2/A3/A4 work early.
