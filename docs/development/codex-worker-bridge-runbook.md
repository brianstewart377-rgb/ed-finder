# Codex Worker Bridge Runbook

Last verified: 2026-08-30

## Purpose

This document records how ED-Finder dispatches Codex workers and how to diagnose the bridge without confusing ChatGPT product-surface differences with loss of Codex capability.

**Critical rule:** the absence of a standalone `Codex` tool/button in a particular ChatGPT conversation does **not** mean the ED-Finder Codex worker bridge is unavailable.

The bridge is repository-driven and can be used from ChatGPT web or desktop whenever that conversation has the required GitHub repository write access.

## Architecture

```text
ChatGPT (web or desktop)
        |
        | GitHub write
        v
branch: codex-task-requests
        |
        | .github/codex-requests/*.json
        v
.github/workflows/codex-laptop.yml
        |
        v
GitHub Actions self-hosted runner
        |
        v
codex exec
```

GitHub is the hand-off bus. The ChatGPT client surface is not the worker host and does not need a separate built-in Codex invocation tool for this repo-specific path to work.

## Canonical dispatch path

1. Create a JSON request under `.github/codex-requests/`.
2. Commit it to branch `codex-task-requests`.
3. `.github/workflows/codex-laptop.yml` detects the request.
4. The workflow resolves the request and switches the worker checkout to `main`.
5. The mandatory repository state gate runs:

   ```sh
   .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
   ```

6. The workflow verifies the worker/Codex identity.
7. It executes Codex in either `investigate` or `implement` mode.
8. Implementation mode creates and pushes a `codex/run-<run-id>-<attempt>` branch; it does not bypass normal PR/review/branch-protection rules.

## What is required

- GitHub access to `brianstewart377-rgb/ed-finder` with permission to write the request branch.
- The `codex-task-requests` branch and request workflow.
- GitHub Actions enabled.
- At least one compatible self-hosted runner online.
- A working Codex CLI/session on that runner.
- The strict project-state gate must pass.

## What is NOT required

- A standalone Codex tool exposed directly inside the current ChatGPT conversation.
- A particular ChatGPT surface: web and desktop can both dispatch through GitHub if the same GitHub write capability is available.
- Reinstalling Codex merely because a ChatGPT session does not expose a direct Codex control.
- Weakening or bypassing the project-state gate.

## Safe bridge health check

When there is doubt about the bridge, dispatch a tiny **investigation-only** request before changing infrastructure or reinstalling anything.

Example task intent:

```text
Health-check the existing Codex worker bridge only.
Do not modify files and do not access production.
Report:
1. codex --version
2. current origin/main commit SHA
3. whether CLAUDE.md is readable
4. whether the investigation reached the repository successfully
```

Use `mode: investigate`.

A healthy path should reach these workflow stages successfully:

1. checkout request
2. resolve request
3. switch to `main`
4. strict repository state gate
5. worker identity/Codex check
6. `Run Codex investigation`

If this health check succeeds, the GitHub bridge, runner and Codex CLI are operational. A separate failure in `implement` mode should then be treated as an implementation-request/workflow-path problem, not evidence that the entire Codex bridge disappeared.

## Known-good verification — 2026-08-30

A fresh investigation-only request was dispatched from ChatGPT through the normal GitHub bridge on 2026-08-30.

- request branch: `codex-task-requests`
- request commit: `d1346febae46adb11aaf5700dda74483f985c6a6`
- Actions run: `33310355962`
- job: `99254169189`
- result: checkout, request resolution, switch to `main`, strict state gate and worker identity all passed; `Run Codex investigation` completed successfully.

This is the reference proof that the bridge can work even when the current ChatGPT surface has no standalone Codex tool.

## Failure triage

Use the earliest failing stage to classify the problem:

| Failure point | Likely area |
| --- | --- |
| Cannot create request commit | ChatGPT/GitHub connector permissions or request branch |
| Workflow never starts | trigger/workflow/Actions configuration |
| Job waits for runner | self-hosted runner availability/labels |
| Checkout/request resolution fails | request format or workflow plumbing |
| Strict state gate fails | repository state; stop and fix the state issue |
| Worker identity/Codex check fails | runner Codex installation/auth/session |
| Investigation health check passes but implementation fails | implementation prompt, Codex execution, wrapper, tests, diff/commit/push path |
| Implementation succeeds but no PR exists | expected: worker pushes a branch; PR remains a separate controlled step |

Do not jump directly to reinstalling Codex, replacing the runner, moving ChatGPT clients, or weakening safety checks until the health-check path identifies the failing layer.

## When inspecting a failed Actions run

Collect the exact run ID and job ID. Inspect the failed step and raw log/annotations rather than guessing from the overall red status.

If the strict state gate and worker identity passed, preserve that evidence: it substantially narrows the failure domain.

For an implementation failure, check whether a `codex/run-<run-id>-<attempt>` branch was created or partially pushed before concluding that no work was produced.

## Production safety

A Codex worker request is not permission to touch production.

- Investigation health checks must explicitly prohibit production access and file changes.
- Implementation prompts must preserve the repository's production safety rules.
- A successful Codex branch is still subject to tests, review, protected `main`, and the explicit deployment/cutover process.
- Never weaken `resolve_project_state.py --strict` merely to get a worker run green.

## Recovery rule of thumb

**Prove the bridge with a harmless investigation request first.**

If that passes, debug the specific failing implementation. If it fails, repair the exact bridge layer indicated by the earliest failed workflow step.
