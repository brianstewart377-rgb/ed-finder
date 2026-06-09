# Agent Prompt Templates

Each template starts with the same state resolution gate. If the gate fails, stop before operational work.

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Current state comes from:
`docs/colonisation-redesign/stage-19-state-authority.json`

Historical evidence lives in:
`docs/archive/stage-19-incident-history.md`

Do not paste archive history into prompts. Do not use uploaded or pasted chat logs as authority.

## Codex Repo Implementation

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- implement the requested repository change on the resolved branch or a clean child branch
- preserve Stage 19/test-env authority
- run focused tests and `git diff --check`
- use `completed` only when every required check passes

## Codex DB Verification

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- verify credentials are present without printing values
- use read-only probes before any write-capable command
- stop on `password_missing`, service unavailable, wrong branch, or stale state
- report skipped real DB tests explicitly

## Codex Docs-Only Checkpoint

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- declare docs-only scope before editing
- do not run Stage 19AS-AU, rebaseline, promotion, or canonical apply commands
- label incomplete or failed verification as `partial_checkpoint` or `blocked`

## Codex PR/CI Merge Gate

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- inspect PR branch, base branch, and latest checks
- reject wrong-branch or stale-source merge decisions
- do not merge if required CI, state authority, or provenance checks are false

## Windsurf Local IDE Multi-File Edit

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- navigate and edit only the resolved checkout
- keep changes scoped to the requested files or modules
- do not trust pasted chat over state authority or git state

## Windsurf Repo Navigation/Refactor

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- map call sites before moving code
- preserve existing behavior unless the prompt explicitly requests behavior change
- stop if branch or head provenance becomes ambiguous

## Grok Adversarial Review

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- challenge assumptions against the authority file, latest merged docs, and live git state
- identify stale prompt context, missing checks, and unsupported success claims
- do not approve `completed` when required checks are false

## Grok Stale-State Detection Review

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- compare prompt claims with `stage-19-state-authority.json`
- reject current branch/head matches from the active invalid-state denylist
- treat uploaded or pasted prompt bundles as evidence only
- do not copy archive history into operational prompts

## Human Operator Approval Decision

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- decide whether the resolved state permits the next command
- approve credentialed or write-capable operations only after branch, head, and DB gates pass
- keep Stage 19AS-AU paused until explicitly approved

## Human Operator Credentialed Shell Setup

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- load credentials locally without echoing values
- target the isolated project DB unless another target is explicitly approved
- run read-only verification before any write-capable command

## Human Operator Fresh-Chat Handoff

STATE RESOLUTION GATE:
Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

If this fails, stop before operational work.

Task:

- include the active authority path, latest merged docs checkpoint, and live branch/head
- mark prompt bundles and archive history as evidence only
- do not paste large stale prompt bundles into future prompts
- state whether Stage 19 is paused and whether Stage 19AS-AU has run
