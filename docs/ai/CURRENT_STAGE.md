# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Continuity protocol established. No product-code stage is currently authorised.**

## Current branch and baseline

- Continuity branch: `chore/ai-continuity-protocol`
- Base branch at creation: `work/r1-canonical-body-evidence`
- Base commit: `f9177b7c3e5dc4087144c416a8aed6cc57446df0`
- Purpose of this branch: add durable AI handoff and recovery records only.

## Active goal

Make future AI-assisted work recoverable when an agent chat is closed, crashes, or becomes too large.

## Allowed files for the continuity-protocol stage

- `docs/ai/README.md`
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/RECOVERY.md`
- `docs/ai/CHAT_HANDOFF_TEMPLATE.md`

No product source, tests, configuration, workflow, or deployment files are authorised in this stage.

## Known follow-on work

### R1 Assessment Laboratory reconstruction

- Status: **not started; no code authorised**.
- Reason: the previously reviewed R1 lab source tree and its historical commit are not present in the current local checkout, Git reflog, available remote branches, or searched workspace.
- Required first step: a read-only reconstruction-inventory and contract stage.
- Do not guess old fixture semantics, assessment rules, report text, or test behaviour from memory alone.
- Any reconstruction must use its own branch, explicit base SHA, accepted design contract, allowed-file list, and final evidence checklist.

## Required evidence before leaving any future implementation stage

Replace this checklist with stage-specific evidence, but keep the raw output or a durable CI link/reference:

- exact branch name and full current commit SHA;
- `git status --short`;
- `git diff --stat`, `git diff --name-status`, and `git diff --check`;
- tests required by the stage;
- typecheck/build where relevant;
- screenshots, artifacts, or preview checks where relevant;
- a clear list of remaining blockers or the next safe action.

## Last verified state

- Repository baseline inspected on 2026-07-01.
- Current application branch at that time: `work/r1-canonical-body-evidence`.
- Frontend root: `frontend-v2`.
- No `src/lab/r1-assessment-lab` directory exists in that checkout.
- The continuity protocol is being added on a separate documentation-only branch.

## Next safe action

Review and merge the continuity-protocol documentation branch. After merge, begin any new substantive task by copying the template in `CHAT_HANDOFF_TEMPLATE.md` into a fresh agent chat and updating this file with the new stage details.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
