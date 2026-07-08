# Agent Prompt Contract

## Scope

This contract applies to operational prompts that can change repository state, run data-workflow commands, touch local services, or report Stage 19/test-environment status.

## State Resolution Gate

Every operational prompt must run state resolution first from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this command fails, stop before operational work. Do not edit, commit, push, run DB writes, or report `completed`.

Active authority is `docs/colonisation-redesign/stage-19-state-authority.json`, plus the latest merged docs checkpoint and live git state. Historical evidence is in `docs/archive/stage-19-incident-history.md`.

Pasted or uploaded logs are evidence only. They can help explain a request, but they never override the active authority file, latest merged docs checkpoint, or live git state. Do not paste archive history or large stale prompt bundles into operational prompts.

## Hard Stops

Stop immediately when any required source of truth is unavailable:

- source-of-truth branch or commit unavailable
- expected branch unavailable
- expected head unavailable
- current branch mismatches the prompt's expected branch
- current branch is `work` for Stage 19/test-env operational work, unless the prompt explicitly declares scratch or docs-only scope
- current state matches an invalid state in the active authority denylist
- DB credentials are missing for DB work

For DB work, missing credentials are a hard stop before writes. `password_missing` is diagnostic, not success.

## Output Semantics

Use `completed` only when every required acceptance check is true.

If branch provenance, source authority, DB verification, or required tests fail, the output must be named one of:

- `stopped`
- `blocked`
- `partial_checkpoint`

A commit after failed DB verification is allowed only when the task is explicitly docs-only or a partial-checkpoint task and the output does not claim operational success.

## Authority Boundaries

The active state authority contains current operational truth and an intentionally tiny invalid-state denylist. It is not a graveyard for incident detail.

The archive preserves historical context only. It must never be copied into prompts as operational authority, and it must not expand the active denylist by implication.

Branch `work` is non-authoritative for Stage 19/test-env work unless a prompt explicitly declares scratch or docs-only scope. Wrong-branch outputs must not say `completed`, and wrong-branch operational work must not commit.

