# Project Continuity and Merge Closeout Protocol v1

**Status:** Drafted for independent review.

**Purpose:** Ensure that a new chat, reviewer, or implementation agent can recover the current project state from the repositories without relying on a long conversation, a remembered plan, or an uncommitted workspace.

## 1. Governing rule

> A merged change is not fully closed until its durable recovery records are updated.

`CURRENT_STAGE.md` is mandatory after every merge. The roadmap, continuity ledger, and decision register are updated when their respective subject matter changes.

## 2. Mandatory records

| Record | Update requirement | Purpose |
|---|---|---|
| `docs/ai/CURRENT_STAGE.md` | **Every merge** | Exact working point, status, caveats, active phase, and next safe action. |
| `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md` | When a phase advances, blocks, changes dependency, or completes | Strategic programme state. |
| `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md` | When an artefact’s ownership, lifecycle label, control status, or migration treatment changes | R1/CPE/CRE continuity and anti-burial record. |
| `docs/ai/DECISIONS.md` | When the owner accepts a durable rule or boundary that future work must obey | Append-only decision record. |
| Relevant contract or acceptance record | When its own stage/status changes | Preserve exact contract/acceptance provenance. |

## 3. Merge-closeout checklist

For every merge:

1. Verify the live merged PR state.
2. Record the PR number, title, exact reviewed head SHA, merge commit SHA, merge method where known, and merge date/time.
3. State in plain language what changed.
4. State in plain language what did **not** change.
5. Record caveats, unresolved questions, stale documents, superseded PRs, and any external dependency.
6. Update `CURRENT_STAGE.md`.
7. Update the roadmap only when programme phase status or dependency changed.
8. Update the Continuity Ledger only when ownership, lifecycle classification, control admission, or migration treatment changed.
9. Append to `DECISIONS.md` only when a durable owner decision changed future constraints.
10. Set one explicit next safe action.
11. Do not start that next action without separate scope/owner authorisation.

## 4. Status vocabulary

Use these labels consistently:

- **Drafted** — exists on a branch or PR; not yet independently accepted.
- **Reviewed** — independent review completed; owner acceptance may still be pending.
- **Accepted, awaiting merge** — owner approved exact reviewed head; merge has not yet completed.
- **Accepted and merged** — live branch contains the accepted merge.
- **Deferred pending evidence** — no implementation or conclusion may be inferred yet.
- **Blocked** — a named missing input, contradiction, review issue, or decision prevents progress.
- **Historic reference only** — retained for provenance but cannot influence current decisions.
- **Stale documentation debt** — can still mislead live work and must be scheduled for correction.

No document may say a merged item is pending review or merge. No document may call a draft item accepted. When a factual status error is discovered, correct it through a narrow documentation-only change rather than letting it propagate.

## 5. New-chat recovery protocol

A new chat or agent begins read-only.

1. Read `CURRENT_STAGE.md`.
2. Read this protocol.
3. Read the applicable roadmap and continuity ledger.
4. Read `DECISIONS.md`.
5. Inspect the live repository branch, exact commit, worktree/PR state, and current review threads.
6. Report:
   - repository and branch;
   - exact commit;
   - active phase;
   - what is confirmed versus pending;
   - open PR/review status;
   - next safe action;
   - any discrepancy between durable records and live GitHub state.
7. Do not write, merge, push, close, deploy, reset, stash, or delete until the owner approves the recovered state.

## 6. Cross-repository rule

When work spans `ed-finder`, CRE, and CPE, record a separate immutable pin for each repository. A review must not silently follow moving `main` or a moving working branch.

Each cross-repository handoff records:

- repository URL;
- branch;
- full commit SHA;
- whether the branch resolved to that SHA at review time;
- which repository supplies research truth, planning assessment, plan construction, or presentation;
- any uncertainty about PR/SHA linkage or merge method.

## 7. Documentation boundaries

This protocol does not authorise code, tests, fixture changes, data migration, external research, database access, architecture selection, deployment, or implementation. It governs continuity only.

## 8. Review and merge rule

Every substantial PR receives an independent read-only review before owner merge authorisation. The owner authorises a merge against an exact live head SHA. Before merging, re-fetch the live PR metadata, changed files, reviews, threads, and head SHA. If the head moved or an actionable thread exists, pause and re-review.

## 9. Completion test

A merge closeout is complete only when someone opening a new chat can answer, from the repository:

```text
What exists?
Who owns it?
What changed?
What remains uncertain?
What is allowed next?
```
