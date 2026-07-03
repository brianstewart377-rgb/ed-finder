# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, after every merged change, and after any accepted decision or evidence run.

## Status

**D1a — Documentation Control Plane is drafted for independent review on branch `docs/d1a-documentation-control-plane` and live draft PR `#302 — docs: establish documentation control plane`. It is based on `work/r1-canonical-body-evidence` at exact base `2302634a226ab79545bf27dfaf77cd6aff26a309`, with current draft head `fab0bad11e47c27996518da118168deb853424c1`. This stage creates a practical documentation entry point, separates current product control from historic and future assessment records, corrects stale Stage 25 wording, and aligns recovery/handoff documents to the current reading order. It is not accepted or merged.**

## Branch and base

- Repository: `brianstewart377-rgb/ed-finder`
- Base branch: `work/r1-canonical-body-evidence`
- Required base SHA: `2302634a226ab79545bf27dfaf77cd6aff26a309`
- PR: `#302 — docs: establish documentation control plane`
- Branch: `docs/d1a-documentation-control-plane`
- Head: `fab0bad11e47c27996518da118168deb853424c1`

This branch/head pair is the recovery point for the current draft only. Any later review, acceptance, or merge work must re-fetch live GitHub PR metadata and live Git state rather than trust stale document text alone.

## Scope

- create `docs/DOCUMENTATION_INDEX.md` as the practical documentation entry point;
- update `docs/ai/README.md` to index the current control documents, roadmap, ledger, merge-closeout protocol, Stage 6 closeout, R1 contracts, recovery material, and decisions;
- update `docs/ai/PROJECT_CONTEXT.md`, `docs/ai/RECOVERY.md`, `docs/ai/CHAT_HANDOFF_TEMPLATE.md`, and `docs/ai/ACCEPTANCE_PROTOCOL.md` to match the current documentation control plane and reading order;
- correct stale Stage 25 wording in `docs/colonisation-redesign/README.md` and `docs/colonisation-redesign/stage-25-roadmap.md` using live merged PR status;
- update `docs/reference/colonisation/README.md` to point readers first to the Documentation Index and current control documents.

## Explicit exclusions

- no code, test, SQL, schema, API, runtime, deployment, CRE, CPE, or R1 semantic change;
- no document move, rename, archive, delete, or physical reorganisation;
- no changelog or versioning baseline;
- no merge, rebase, force-push, review request, PR comment, deployment, or automation authority;
- no claim that Stage 25 is complete.

## Control boundaries preserved

- Legacy ED-Finder ratings remain the stored `0–100` product ratings documented in `docs/colonisation-redesign/rating-system-current-contract.md`.
- The R1 Assessment Laboratory remains DEV-only, fixture-backed, deterministic, local, and separate from the public product.
- CRE remains the authority for evidence, provenance, mechanics, contradictions, confidence, and planner-safe releases.
- CPE remains the future authority for programme-specific assessment and player-specific plan construction.
- The future CPE System Assessment Engine must not be described as a universal score or universal rank.

## Live merged GitHub state checked for Stage 25 wording

- PR `#262` — `Add Stage 25C product shell and navigation hierarchy` — merged.
- PR `#263` — `Fix Review Lab mobile planner contract` — merged.
- PR `#269` — `[codex] stage 25d-a finder save, inspect, and plan start` — merged.
- PR `#271` — `[codex] Stage 25D-A.2 planner clarity and draft lifecycle` — merged.

These merged facts correct stale wording that still described Stage 25C Slice 1 as pending review. They do not justify calling Stage 25 complete.

## Validation

- Base branch resolution to exact required SHA was verified before editing.
- The worktree was clean before editing.
- `git diff --check` passed on the D1a docs-only diff.
- `git status --short` showed only the ten allowlisted documentation files before commit.

## Remaining documentation debt

- D0 cross-repository Documentation Estate Audit and Spring-Clean Register remains outstanding.
- Conservative follow-on batches are still required for stale historical-stage wording outside the D1a allowlist.
- Any future archive, move, rename, deletion, root `README.md`, changelog, beta-version baseline, or physical documentation reorganisation work requires separate explicit authorisation.

## Next safe action

Await independent review on live draft PR `#302` at exact head `fab0bad11e47c27996518da118168deb853424c1`. After independent review, the next safe action is owner acceptance only after a final live GitHub-state check against the exact reviewed head. Acceptance does not merge; merge remains a separate exact-head owner-authorised decision. Do not mark this stage accepted or merged, and do not widen scope beyond the listed documentation files.

## Recovery instruction

If context is lost, start read-only. Read:

1. `docs/DOCUMENTATION_INDEX.md`;
2. this file;
3. `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`;
4. `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`;
5. `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md`;
6. `docs/ai/DECISIONS.md`;
7. the live GitHub and Git state.

Report the recovered branch, exact base, exact HEAD, active scope, exclusions, validation state, PR state, and next safe action before making any write.
