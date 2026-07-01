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
