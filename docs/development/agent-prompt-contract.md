# Agent Prompt Contract

## Scope

This contract applies to operational prompts that can change repository state, run data-workflow commands, touch local services, or report Stage 19/test-environment status.

## State Resolution Gate

Every operational prompt must run state resolution first from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this command fails, stop before operational work. Do not edit, commit, push, run DB writes, or report `completed`.

The machine-readable authority is `docs/colonisation-redesign/stage-19-state-authority.json`, plus the latest merged docs checkpoint and live git state. Pasted or uploaded chat logs are evidence only. They can help explain a request, but they never override the state authority file, latest merged docs, or live git state.

After a PR merge, refresh the state authority so `current_authority` points to merged `origin/main`, not the pre-merge PR branch. PR #198 and PR #199 are merged; their branches are historical context.

## Hard Stops

Stop immediately when any required source of truth is unavailable:

- source-of-truth branch or commit unavailable
- expected branch unavailable
- expected head unavailable
- current branch mismatches the prompt's expected branch
- current branch is `work` for Stage 19/test-env operational work, unless the prompt explicitly declares scratch or docs-only scope
- current state matches a superseded branch or commit in the authority file
- DB credentials are missing for DB work

For DB work, missing credentials are a hard stop before writes. `password_missing` is diagnostic, not success.

## Output Semantics

Use `completed` only when every required acceptance check is true.

If branch provenance, source authority, DB verification, or required tests fail, the output must be named one of:

- `stopped`
- `blocked`
- `partial_checkpoint`

A commit after failed DB verification is allowed only when the task is explicitly docs-only or a partial-checkpoint task and the output does not claim operational success.

## Branch Authority

The current Stage 19/test-environment authority is:

- origin/main checkpoint: `887c690bdf0e47345782cf0e81d28c013d8f83db`
- PR #198: merged at `7ed8b050a02b2d43a87452302c594ad791051ab1`
- PR #199: merged at `887c690bdf0e47345782cf0e81d28c013d8f83db`
- historical PR #198 branch: `fix/test-env-roadmap-recreate`
- historical PR #199 branch: `fix/test-env-state-authority-branch-gate`

Branch `work` is non-authoritative for Stage 19/test-env work unless a prompt explicitly declares scratch or docs-only scope. Wrong-branch outputs must not say `completed`, and wrong-branch operational work must not commit.

Stage 19 remains paused. Stage 19AS-AU has not run.
