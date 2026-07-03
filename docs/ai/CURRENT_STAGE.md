# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, after every merged change, and after any accepted decision or evidence run.

## Status

**D1a — Documentation Control Plane is accepted and merged. D0 — Documentation Estate and Code Boundary Register is now recorded in `docs/ai/D0_DOCUMENTATION_ESTATE_AND_CODE_BOUNDARY_REGISTER_V1.md`.**

## Branch and base

- Repository: `brianstewart377-rgb/ed-finder`
- Canonical base branch: `work/r1-canonical-body-evidence`
- Required canonical base SHA: `4d01e0213046825f640e245cc551512c7e9d90f1`
- Closeout branch: `docs/d1a-merge-closeout`

This closeout branch was created only after fetching `origin/work/r1-canonical-body-evidence` and verifying that it resolved to `4d01e0213046825f640e245cc551512c7e9d90f1`.

## D1a merge record

- PR: `#302 — docs: establish documentation control plane`
- PR base branch: `work/r1-canonical-body-evidence`
- PR base SHA before merge: `2302634a226ab79545bf27dfaf77cd6aff26a309`
- Reviewed head SHA: `2317012372742864b79b85f08f52361e1b5aee18`
- Merge commit SHA: `4d01e0213046825f640e245cc551512c7e9d90f1`
- Merge method: `merge commit`
- Merged at: `2026-07-03T16:23:05Z`

At closeout preflight, `origin/work/r1-canonical-body-evidence` resolved to the merge commit above.

## What D1a changed

- introduced `docs/DOCUMENTATION_INDEX.md` as a navigation layer subordinate to `CURRENT_STAGE.md`;
- separated current Stage 25 control, legacy stored ED-Finder ratings, DEV-only R1 Assessment Laboratory, future CPE System Assessment Engine, and CRE research truth;
- aligned AI recovery and handoff material with current control records and live GitHub/Git recovery;
- reconciled pre-merge acceptance with post-merge closeout;
- corrected stale Stage 25C wording without claiming Stage 25 is complete;
- updated the Reference Pack to lead with current control material before historical roadmaps.

## What D1a did not change

- no code, test, SQL, schema, API, runtime, deployment, CRE, CPE, or R1 semantic change;
- no document move, rename, archive, delete, or physical reorganisation;
- no changelog or versioning baseline;
- no database change, root `README.md` work, beta-version work, or implementation authority;
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

## Validation history

- PR `#302` was verified merged at `4d01e0213046825f640e245cc551512c7e9d90f1`.
- The reviewed head for that completed predecessor merge was `2317012372742864b79b85f08f52361e1b5aee18`.
- The changed-file scope for that predecessor merge remained the approved ten-file D1a documentation allowlist.
- This closeout branch was created from the fetched canonical base only after the worktree was verified clean.

## Remaining documentation debt

- D0 is now recorded in `docs/ai/D0_DOCUMENTATION_ESTATE_AND_CODE_BOUNDARY_REGISTER_V1.md` as a read-only documentation-estate and code-boundary register.
- D1b is the proposed, separately owner-authorised next documentation batch for root navigation and history/changelog cleanup. It is not started, accepted, merged, or authorised here.
- Stale historical-stage wording outside D1a requires later, separately authorised conservative cleanup batches.
- Archive, move, rename, deletion, root `README.md`, changelog, beta-version, and physical documentation reorganisation require separate explicit authorisation.

## Next safe action

D1b is the proposed next documentation batch: a separately owner-authorised,
docs-only root navigation and history/changelog cleanup. It must not archive,
delete, move, rename, refactor, implement any API or code boundary, or start
code, runtime, database, API, CRE, CPE, or R1 work without further explicit
authorisation.

## Closeout rule

This closeout records PR `#302`’s completed merge.

This closeout PR cannot record its own eventual merge SHA before it merges.

Its own eventual merge remains recoverable from live GitHub PR metadata.

Do not open another PR solely to record this closeout PR’s own merge SHA.

A later ordinary working-point update may record this closeout merge as historical evidence.

## Recovery instruction

If context is lost, start read-only. Read:

1. `docs/DOCUMENTATION_INDEX.md`;
2. this file;
3. `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`;
4. `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`;
5. `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md`;
6. `docs/ai/DECISIONS.md`;
7. the live GitHub and Git state.

Report the recovered branch, exact base, active scope, exclusions, validation state, merged-predecessor facts, and next safe action before making any write.
