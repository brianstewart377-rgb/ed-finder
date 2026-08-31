# ChatGPT Operations Control Plane

## Purpose

Provide a small, auditable operations interface that lets ChatGPT manage routine ED-Finder operational tasks without requiring the owner to relay commands between ChatGPT and a shell session.

This is deliberately **not** an unrestricted remote shell. It exposes named, fail-closed operations that wrap existing guarded scripts and runbooks.

## Initial operation set

- `production-status`
- `backup-status`
- `pgbackrest-check`
- `api-smoke`
- `collect-logs`
- `restart-api`
- `restart-worker`
- `deploy-commit`
- `run-governed-migrations`

Destructive operations such as deleting volumes, pruning Docker data, dropping databases, reinitializing PostgreSQL, or rerunning Phase 4C are intentionally excluded.

## Safety model

Every mutating operation must:

1. run the canonical repository/project state gate first where applicable;
2. verify the expected target host and deployment identity;
3. call an existing guarded operator script or a purpose-built wrapper rather than ad-hoc shell commands;
4. fail closed when required inputs or safety checks are missing;
5. emit a machine-readable receipt;
6. never print credentials, tokens, passwords, or private keys.

The retained r5 production candidate remains protected by the existing `RETENTION_HOLD` and cleanup guards. No control-plane operation may bypass those protections.

## Delivery model

The first implementation should use GitHub Actions `workflow_dispatch` as the control surface because ChatGPT already has direct GitHub access. Workflows should invoke a small allowlisted dispatcher and existing operator scripts.

Server connectivity must use already-authorized deployment/SSH credentials if they exist in GitHub Actions. This repository change must not embed or create secrets in source control.

If the repository does not already have suitable Actions credentials, the workflow may be merged in an inert state and the one remaining owner action is to add the required GitHub Actions secret/runner connection.

## Codex bridge

Codex task requests are intentionally asynchronous so a ChatGPT web or desktop turn never needs to stay open for the full Codex execution time.

The request path is:

`ChatGPT -> codex-task-requests -> Codex Dispatch -> workflow_dispatch -> Codex Worker -> self-hosted runner -> codex exec`

A request is a single JSON file committed under `.github/codex-requests/` on the `codex-task-requests` branch. `.github/workflows/codex-dispatch.yml` validates that request on a GitHub-hosted runner, dispatches `.github/workflows/codex-laptop.yml` through `workflow_dispatch`, records a stable request identifier, and then exits. Its bounded job must never wait for the Codex worker to finish.

The long-running self-hosted job is a separate workflow run. Its run name includes the stable request identifier, and the dispatcher prints `CODEX_DISPATCH_ACCEPTED=true` plus `CODEX_WORKER_RUN_ID=<id>` when the worker run becomes visible. If GitHub has accepted the dispatch but the worker run has not appeared within the short lookup window, the dispatcher prints `CODEX_WORKER_RUN_ID=pending` and still exits successfully.

ChatGPT clients should therefore report the dispatch acknowledgement/run ID immediately. A later turn may query the worker run for progress or results. A client-side timeout must not be treated as evidence that Codex failed unless the GitHub worker run itself failed or timed out.

The Codex Worker retains its 120-minute execution limit, repository state gate,
investigation immutability check, and isolated implementation-branch behavior.
It has no workflow-level concurrency group: the three dedicated workers
(`contabo-codex-worker`, `contabo-codex-worker-2`, and
`contabo-codex-worker-3`) form a bounded parallel pool, while each runner still
executes at most one job at a time.

### Codex implementation push credential

Ordinary Codex implementation branches may be pushed with the workflow's normal `GITHUB_TOKEN`. GitHub refuses that token when a commit creates or modifies files under `.github/workflows/`, so workflow-file changes require the repository secret `CODEX_WORKER_GIT_TOKEN`.

`CODEX_WORKER_GIT_TOKEN` should contain a fine-grained personal access token limited to this repository with `Contents: read/write` and `Workflows: read/write`. A broad classic token is not preferred. A GitHub App can be adopted later, but the workflow would need to generate a fresh installation token at runtime rather than storing a short-lived installation token as this repository secret.

The privileged credential is intentionally not passed to `actions/checkout`,
the Codex CLI, the task prompt, the Codex execution environment, ordinary
implementation pushes, or push-payload preparation. After Codex exits, the
self-hosted job creates a credential-free full-index binary patch artifact. A separate
GitHub-hosted job reconstructs the commit, detects workflow changes fail-closed,
and performs the push. A workflow-changing branch alone enters the PAT-backed
push step; an ordinary branch enters a separate `GITHUB_TOKEN` step.

The GitHub-hosted job applies the patch to a fresh checkout of canonical `main`,
creates a wrapper-owned commit, disables system/global config,
credential helpers, replacement objects, terminal prompts, and hooks, and
pushes to the canonical HTTPS URL derived from `GITHUB_REPOSITORY`.
Authentication uses a temporary `GIT_ASKPASS` helper. The credential-bearing
process therefore never runs on the danger-full-access host, and
Codex-controlled repository remotes, includes, helpers, hooks, background
processes, and host tooling cannot observe the selected token.

Codex prompts are streamed on stdin. Unattended invocations use the CLI's
`--ignore-user-config`, `--ignore-rules`, and `--ephemeral` modes: authentication
continues to use the runner's Codex home, but interactive user MCP servers,
hooks, plugins, rules, and session persistence are not inherited. Before either
Codex invocation, the workflow also requires the runner name to match one of the
three dedicated pool hosts above.

If a Codex implementation changes `.github/workflows/*` while `CODEX_WORKER_GIT_TOKEN` is absent, the worker fails closed before attempting the push and reports the missing secret explicitly. Implementations that do not change workflow files continue to fall back to the normal `GITHUB_TOKEN`.

## Receipts

Every run should record at least:

- operation name;
- requested commit/ref where relevant;
- start/end UTC;
- target host identity;
- exit status;
- bounded stdout/stderr with secret redaction;
- resulting deployment/database generation identity where relevant.

Receipts should be retained as Actions artifacts and/or in the existing operations receipt format.

## Permission boundary

The control plane is intended to let ChatGPT execute routine operational tasks directly through GitHub. Production cutover, destructive storage/database actions, and other explicitly high-risk operations remain separate owner-authorized procedures unless a later authority decision adds narrowly-scoped actions for them.
