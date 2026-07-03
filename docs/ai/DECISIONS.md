# Accepted Decisions

This file is append-only. Record decisions that affect more than one stage, a later reconstruction, or a recovery workflow.

Use this format:

```md
## YYYY-MM-DD — Decision title

**Decision**
What was decided.

**Reason**
Why it was decided.

**Invariant**
What future work must preserve.

**Evidence / reference**
Branch, commit, issue, PR, test, or document.
```

---

## 2026-07-01 — Durable AI continuity protocol

**Decision**
AI-assisted work must be recoverable from the repository without relying on a live agent conversation.

**Reason**
A previous agent chat and an uncommitted laboratory worktree were lost. The loss showed that chat history and local uncommitted state are not durable project memory.

**Invariant**
Every substantive stage must have a named branch, exact base commit, durable current-stage record, explicit allowed-file list, evidence checklist, and a pushed checkpoint before an agent stops.

**Evidence / reference**
`docs/ai/README.md`, `docs/ai/CURRENT_STAGE.md`, and `docs/ai/RECOVERY.md` on branch `chore/ai-continuity-protocol`.

## 2026-07-01 — Chat handoff standard

**Decision**
When a chat becomes too large, the user may close it after updating and committing the stage handoff. A new agent chat must begin by reading the AI continuity files and inspecting Git state rather than relying on a manual recap.

**Reason**
A short, durable stage record is more reliable than a long chat summary and can be reviewed by any future agent.

**Invariant**
The new chat starts read-only. It may not edit, reset, stash, commit, merge, push, deploy, or delete files until it reports branch, commit, worktree status, and the active stage.

**Evidence / reference**
`docs/ai/CHAT_HANDOFF_TEMPLATE.md` and `docs/ai/RECOVERY.md`.

## 2026-07-01 — R1 Assessment Laboratory is a future clean reconstruction

**Decision**
The R1 Assessment Laboratory will not be reconstructed by guessing from lost chat state or by editing the current application branch opportunistically.

**Reason**
The earlier lab source tree and historical commit were not recoverable from the available checkout, local Git object database, remote branches, reflog, or searched workspace.

**Invariant**
Any future R1 lab work begins with a read-only inventory and written reconstruction contract, then uses a dedicated branch and narrow staged implementation.

**Evidence / reference**
`docs/ai/CURRENT_STAGE.md` and the 2026-07-01 recovery inspection.

## 2026-07-01 — R1 reconstruction semantics v1

**Decision**
Adopt the explicit Stage 2B assessment mapping and semantics in `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`.

**Reason**
The historic R1 implementation and fixture meanings were lost. The rebuilt evaluator needs complete, testable state coverage without falsely presenting assumptions as recovered historic fact.

**Invariant**
The mapping is a forward reconstruction contract: `compact_sufficient_case` is `supported`; incomplete and contradictory cases are `not_assessable`; `fake_flexibility_case` is `not_supported`; `remote_materials_carrier_case` is `conditionally_supported` without a carrier and `supported` with one. Assessment requires a discriminated role-or-question lens, has no universal score/rank/best/Plan Fit, and permits carrier effects only on logistics-sensitive outcomes.

**Evidence / reference**
`docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`; owner approval in the 2026-07-01 Stage 2A review.

## 2026-07-01 — Stage 3B lens selection is context-only

**Decision**
Stage 3B may show a Role/Question lens picker. The selected lens is visible, explicit assessment context and is passed to the accepted Stage 2B evaluator, but it does not alter fixture evaluation, requirement outcomes, conditions, or assessment state in Stage 3B.

**Reason**
The evaluator requires an exclusive lens, so the presentation layer must expose that context honestly. The accepted Stage 2B fixtures do not yet encode lens-specific semantics; presenting the selector as outcome-changing would falsely imply analysis that has not been reconstructed.

**Invariant**
The Stage 3B UI must display persistent plain language that lens selection is context-only in this slice. It must not use the selected lens to reinterpret results, offer lens-based recommendations, or add lens-specific fixtures or evaluator semantics without a later written contract.

**Evidence / reference**
Owner approval following the independent Stage 3A design review on 2026-07-01; `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`.

## 2026-07-01 — Stage 4B permits bounded provisional Plan Fit reconstruction

**Decision**
Plan Fit is now authorised only as a bounded, fixture-backed, pure-core forward reconstruction. It does not supersede assessment state. Stage 4B permits explicit selected strategies only and does not permit recommendation, score, rank, best result, or automatic strategy choice.

**Reason**
Stage 4A identified a narrow next slice for explicit strategy selection and provisional Plan Fit that can remain deterministic, local, and subordinate to the accepted Stage 2B assessment semantics without widening into planning UI or production behavior.

**Invariant**
Carrier remains limited to validated non-shared logistics dependencies. Lens remains context-only. The controlling reference for any later Stage 4B implementation is `docs/ai/R1_STAGE4_PLAN_FIT_CONTRACT_V1.md`.

**Evidence / reference**
`docs/ai/R1_STAGE4_PLAN_FIT_CONTRACT_V1.md`; owner approval to draft the Stage 4B contract on 2026-07-01.

## 2026-07-02 — Stage 4C permits DEV-only Plan Fit presentation

**Decision**
Stage 4C may present accepted Stage 4B Plan Fit output inside the existing DEV-only R1 Assessment Laboratory. Selected strategy is always explicit and local. Stage 4C must not infer strategy, alter Assessment or Plan Fit semantics, recommend a strategy, rank scenarios, score outcomes, or create product behavior.

**Reason**
Stage 4B established the accepted bounded pure-core Plan Fit output. A later Stage 4C slice may present that accepted output within the existing DEV-only lab without widening into production behavior or changing the underlying Stage 2B or Stage 4B semantics.

**Invariant**
Lens remains context-only. Carrier behavior remains entirely provided by accepted Stage 2B and Stage 4B outputs. The controlling reference is `docs/ai/R1_STAGE4C_PLAN_FIT_LAB_PRESENTATION_CONTRACT_V1.md`.

**Evidence / reference**
`docs/ai/R1_STAGE4C_PLAN_FIT_LAB_PRESENTATION_CONTRACT_V1.md`; owner approval to draft the Stage 4C presentation contract on 2026-07-02.

## 2026-07-02 — Stage 5A defers unsupported control-fixture semantics

**Decision**
`wregoe_dual_dodec_control` and `plateau_30_vs_60_case` remain absent from the active R1 fixture registry. Their names alone do not authorise fixture data, Assessment behavior, Plan Fit behavior, tests, UI controls, or an interpretation of lost historical R1 semantics.

**Reason**
The reconstruction contract named both controls only as deferred. Independent review confirmed that the current repository contains no recoverable fixture payload, expected outcome, condition definition, test assertion, or specific proof role for either name beyond that deferral.

**Invariant**
A later forward-reconstruction fixture for either name requires an explicit written contract defining its proof question, deterministic payload, evidence and provenance, requirement evaluations, expected outputs, tests, file boundary, independent review, and separate owner authorisation. No later work may infer semantics from the fixture name, lost-worktree recollection, chat history alone, unrelated Wregoe/Dodec uses elsewhere in the repository, or a numerical comparison.

**Evidence / reference**
`docs/ai/R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`; Stage 5A reviewed head `36371887bf09dad420c86b6c6ca6faffb7cfa0cd`; PR `#290`, merged at `dad3a99f4571428fcb517a13785be297f57e875a`; owner acceptance on 2026-07-02.

## 2026-07-02 — Stage 5B adopts evidence-first capacity-sufficiency discipline

**Decision**
Adopt the Stage 5B evidence discipline as a forward-reconstruction boundary. No R1 conclusion may be stronger than its traceable evidence chain. A possible later capacity-sufficiency control may treat additional bodies as neutral only within a named programme and only where the additional bodies change no named requirement or constraint.

**Reason**
The project needs the galaxy database and other sources to test explicit model assertions rather than to emit opaque judgements. Without an evidence-chain rule, body count or an attractive narrative could be mistaken for capability. The owner provided the capacity-sufficiency intent as a forward-design boundary, not as recovered historical semantics.

**Invariant**
Every later claim must retain a traceable chain from source record through evidence fact and named requirement or constraint to a bounded consequence. Missing, contradictory, stale, incomplete, unsupported, or out-of-scope evidence limits the conclusion. Total body count is context, not an inherent score. The `30` and `60` labels are illustrative only; they are not universal thresholds. This decision does not authorise a fixture, external evidence collection, implementation, or deployment.

**Evidence / reference**
Owner-provided forward-design intent dated 2026-07-02, recorded as `owner_intent_capacity_sufficiency_plateau_2026-07-02` in `docs/ai/R1_STAGE5A_5B_ACCEPTANCE_CLOSEOUT_V1.md`; `docs/ai/R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`; Stage 5B reviewed head `b42d8cfa6d1ad453d6637ea7f24919d85950ec95`; PR `#291`, merged at `f1b1e5b42859a42b0e651ad957c01d5261bec754`; owner acceptance on 2026-07-02.

## 2026-07-03 — CPE / System Assessment Engine is the future assessment owner

**Decision**
Name and preserve **CPE / System Assessment Engine** as a first-class CPE pillar alongside **CPE / Colony Plan Construction**. The R1 Assessment Laboratory in `ed-finder` is the frozen DEV-only prototype and control-suite lineage for that future engine.

**Reason**
The R1 work evaluates candidate systems against an explicit programme, requirements, Carrier scenario, evidence status, and strategy context. That is player-specific planning and comparison work, not CRE research truth and not ed-finder presentation. A separate SRE repository would introduce a premature and duplicative source-of-truth boundary.

**Invariant**
CRE owns evidence, provenance, mechanics, observations, contradictions, confidence, planner-safe releases, and observed-state publications. CPE / System Assessment Engine owns programme-specific assessment, capacity-sufficiency, Carrier scenario evaluation, Plan Fit, and comparison-ready outputs. CPE / Colony Plan Construction owns player constraints, candidate plans, sequencing, alternatives, and validation steps. ed-finder presents but does not own research or planning truth. The R1 lab is reimplemented semantically in CPE only after an accepted contract and control migration; it is not copied as fixture truth.

**Evidence / reference**
Owner direction on 2026-07-03; `docs/ai/R1_STAGE6B_CRE_CPE_BOUNDARY_CONTRACT_V1.md`; `docs/ai/R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`; Programme A0 continuity audit.

## 2026-07-03 — Every merge must leave a durable recovery trail

**Decision**
Every merged change must leave the repository self-explanatory for a new chat or agent. `CURRENT_STAGE.md` is updated after every merge. The roadmap, continuity ledger, and decision register are updated when their respective subject matter changes.

**Reason**
Project knowledge was already vulnerable to chat slowdown, lost local worktree state, stale stage records, and overlapping closeout PRs. Recovery depends on durable repository records, not on a surviving conversation.

**Invariant**
A merge is not fully closed until its exact reviewed head, merge commit, scope, caveats, superseded items, and next safe action are recorded. New chats begin read-only from `CURRENT_STAGE.md`, the continuity protocol, roadmap, ledger, decisions, and live repository/PR state. No document may describe a merged stage as pending; status corrections must be treated as first-class maintenance.

**Evidence / reference**
Owner direction on 2026-07-03; `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`; Programme A0 finding F-13 and stale-record register.