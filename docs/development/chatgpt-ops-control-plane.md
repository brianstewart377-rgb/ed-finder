# ChatGPT Operations Control Plane

## Purpose

Provide a small, auditable operations interface that lets ChatGPT manage routine ED-Finder operational tasks without requiring the owner to relay commands between ChatGPT and a shell session.

This is deliberately **not** an unrestricted remote shell. It exposes named, fail-closed operations that wrap existing guarded scripts and runbooks.

## Current operation set

The legacy Hetzner lane allows:

- `production-status`
- `db-readonly-health`
- `latest-artifacts`
- `latest-artifact-summary`
- `octopus-qdrant-healthcheck-repair`

The ed-new lane allows:

- `host-status`
- `octopus-edge-status`
- `recover-v3-runtime-contract`
- `octopus-qdrant-healthcheck-repair`

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

The production operations paths use a two-stage GitHub Actions control surface.
A request workflow runs without an operator environment or operator secrets,
validates one bounded request, and dispatches a separate privileged executor at
`ref: main`. Only the executor may select an operator environment and invoke the
existing allowlisted operator scripts.

The connector-friendly request paths are:

- `.github/ops-requests/*.json` on `chatgpt-ops-requests` for the legacy
  Hetzner lane, validated by `chatgpt-ops-dispatch.yml`;
- `.github/ed-new-ops-requests/*.json` on
  `chatgpt-ed-new-ops-requests` for the ed-new lane, validated by
  `chatgpt-ed-new-ops-dispatch.yml`.

Each push must introduce exactly one changed JSON request in the applicable
directory and no other changed path. The dispatcher evaluates the complete push
range, including multi-commit pushes and branch creation, rejects unsupported
keys or operations, and sends only validated scalar inputs to the executor. A
workflow file modified on either writable request branch therefore cannot gain
an operator environment or consume operator secrets: the privileged workflow
definition and implementation are both loaded from trusted `main`.

The privileged `chatgpt-ops.yml` and `chatgpt-ed-new-ops.yml` executors retain
their manual `workflow_dispatch` choices for the Actions UI. They have no push
trigger. Branch-backed requests reach those same executor definitions through
an explicit dispatch to trusted `main`.

Each dispatch carries request ID, file, and commit metadata for correlation and
receipts. Executors use workflow run IDs as a durable FIFO gate before the
environment-bearing job. This preserves production serialization without a
fixed Actions concurrency group that could replace a pending middle request.

Server connectivity must use already-authorized deployment/SSH credentials if
they exist in GitHub Actions. This repository change must not embed or create
secrets in source control. The legacy executor uses exactly the
`hetzner-operator` environment; the ed-new executor uses exactly the
`ed-new-operator` environment. Request workflows use neither environment.

If the repository does not already have suitable Actions credentials, the workflow may be merged in an inert state and the one remaining owner action is to add the required GitHub Actions secret/runner connection.

## Codex bridge

Codex task requests are intentionally asynchronous so a ChatGPT web or desktop turn never needs to stay open for the full Codex execution time.

The request path is:

`ChatGPT -> codex-task-requests -> Codex Dispatch -> workflow_dispatch -> Codex Worker -> self-hosted runner -> codex exec`

A request is a single JSON file committed under `.github/codex-requests/` on the `codex-task-requests` branch. `.github/workflows/codex-dispatch.yml` validates that request on a GitHub-hosted runner, dispatches `.github/workflows/codex-laptop.yml` through `workflow_dispatch`, records a stable request identifier, and then exits. Its bounded job must never wait for the Codex worker to finish.

The long-running self-hosted job is a separate workflow run. Its run name includes the stable request identifier, and the dispatcher prints `CODEX_DISPATCH_ACCEPTED=true` plus `CODEX_WORKER_RUN_ID=<id>` when the worker run becomes visible. If GitHub has accepted the dispatch but the worker run has not appeared within the short lookup window, the dispatcher prints `CODEX_WORKER_RUN_ID=pending` and still exits successfully.

ChatGPT clients should therefore report the dispatch acknowledgement/run ID immediately. A later turn may query the worker run for progress or results. A client-side timeout must not be treated as evidence that Codex failed unless the GitHub worker run itself failed or timed out.

The Codex Worker retains its 120-minute execution limit, serial `codex-worker` concurrency group, repository state gate, investigation immutability check, and isolated implementation-branch behavior.

### Codex implementation push credential

Ordinary Codex implementation branches may be pushed with the workflow's normal `GITHUB_TOKEN`. GitHub refuses that token when a commit creates or modifies files under `.github/workflows/`, so workflow-file changes require the repository secret `CODEX_WORKER_GIT_TOKEN`.

`CODEX_WORKER_GIT_TOKEN` should contain a fine-grained personal access token limited to this repository with `Contents: read/write` and `Workflows: read/write`. A broad classic token is not preferred. A GitHub App can be adopted later, but the workflow would need to generate a fresh installation token at runtime rather than storing a short-lived installation token as this repository secret.

The privileged credential is intentionally not passed to `actions/checkout`, the Codex CLI, the task prompt, or the Codex execution environment. Codex finishes first using the ordinary worker environment. The wrapper then inspects the resulting commit and exposes `CODEX_WORKER_GIT_TOKEN` only to the final branch-push step. Authentication is provided through a temporary `GIT_ASKPASS` helper so the token is not embedded in command arguments, remote URLs, or repository configuration.

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
