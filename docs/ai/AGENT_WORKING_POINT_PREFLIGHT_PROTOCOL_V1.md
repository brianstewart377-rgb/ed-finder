# Agent Working-Point Preflight Protocol v1

This protocol is mandatory for ChatGPT, Claude, Trae, Codex, and human contributors before they:

- issue an external-agent prompt;
- begin a new branch;
- review a PR;
- claim a task is current, complete, blocked, authorised, or next;
- rely on an older contract or stage record.

It governs preflight only. It does not select automation, CI enforcement, runtime behaviour, APIs, or implementation architecture.

## Target verification

Before acting, verify:

- exact repository;
- exact branch, PR, or commit;
- current live branch SHA;
- task status: `not started`, `active`, `merged`, `superseded`, `historic`, or `unknown`.

Do not infer target identity from a remembered branch name, an old chat, or a document title alone.

## Authority verification

Read the hierarchy in this order:

1. `docs/ai/CURRENT_STAGE.md`
2. `docs/DOCUMENTATION_INDEX.md`
3. the current named roadmap or active contract only after confirming it remains current
4. live GitHub PR and branch state
5. historical or frozen control records
6. chat memory

Quote the exact current `CURRENT_STAGE.md` status wording before acting.

If an older document conflicts with current control, treat that conflict as documentation drift, not as permission to proceed.

## Two-pass gate

### Pass 1

Run Pass 1 before drafting, editing, opening a branch, or preparing a reviewer prompt.

### Pass 2

Run Pass 2 immediately before:

- posting an external-agent prompt;
- opening a PR;
- accepting a review;
- merging.

The second pass must re-check:

- live GitHub state;
- current head and base;
- task duplication;
- whether a later merge superseded the intended work.

## Required proof block

Every Pass 1 and Pass 2 result must produce this proof block:

```text
Current branch:
Current HEAD:
Canonical branch:
Canonical HEAD:
Controlling document:
Exact current-status wording:
Relevant active contract:
Live PR or branch state:
Task relationship to the active control:
Decision: PROCEED or STOP
```

Do not proceed without a real proof block.

## Hard stop conditions

Stop when any of the following is true:

- base is stale or uncertain;
- an already merged or active equivalent task exists;
- an old contract is being used as current authorisation;
- current-control evidence is missing;
- live GitHub state and repository documentation disagree in a way that cannot be resolved conservatively.

When stopped, report the mismatch. Do not guess, infer, or continue on probability.

## No invented continuity

Do not infer current authority from:

- file names;
- commit subjects;
- prior chat summaries;
- remembered branch names;
- a static SHA copied from an old document.

Do not fabricate current head or base pins.

Do not send a reviewer prompt before a real writer result identifies an actual PR, base, head, and changed-file scope.

## External-agent prompt rule

Every external-agent prompt must:

- include a first-pass verification instruction;
- require a second live-state check immediately before the agent acts;
- target an existing PR and exact live head for review work;
- forbid the agent from recreating completed or merged work.

Prompt writers must not send an agent to review, amend, or recreate a task that live GitHub metadata already shows as merged, superseded, or materially duplicated.
