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

`ChatGPT -> codex-task-requests -> Codex Dispatch -> workflow_dispatch -> prepare -> Codex Worker -> sealed result -> ephemeral trusted push`

A request is a single JSON file committed under `.github/codex-requests/` on the `codex-task-requests` branch. `.github/workflows/codex-dispatch.yml` validates that request on a GitHub-hosted runner, dispatches `.github/workflows/codex-laptop.yml` through `workflow_dispatch`, records a stable request identifier, and then exits. Its bounded job must never wait for the Codex worker to finish.

The long-running Codex execution remains on the self-hosted runner pool and has a stable request identifier in its workflow run name. The dispatcher prints `CODEX_DISPATCH_ACCEPTED=true` plus `CODEX_WORKER_RUN_ID=<id>` when the run becomes visible. If GitHub has accepted the dispatch but the worker run has not appeared within the short lookup window, the dispatcher prints `CODEX_WORKER_RUN_ID=pending` and still exits successfully.

ChatGPT clients should therefore report the dispatch acknowledgement/run ID immediately. A later turn may query the worker run for progress or results. A client-side timeout must not be treated as evidence that Codex failed unless the GitHub worker run itself failed or timed out.

The Codex execution job retains its 120-minute execution limit, repository state gates, investigation immutability check, and isolated implementation-branch behavior. Independent Codex jobs remain parallel because there is no global concurrency group.

The job selects Python 3.12 through the same pinned setup action used by CI and first runs the strict repository state gate on trusted `origin/main` before installing any dependencies. For an implementation request it then selects the immutable target/base SHA, completes the Git history needed for a self-contained result bundle, checks out that exact base, and runs the strict state gate **again on the selected implementation branch**. A target branch that the canonical resolver classifies as unsafe is therefore rejected before Codex is invoked. Only after the selected target passes does the job install that target's pinned `tests/requirements-ci.txt` authority, so the Codex/test environment matches the branch actually being updated rather than stale `main` requirements. It exports `VIRTUAL_ENV`, prepends `.venv/bin` only for the unprivileged Codex/test steps, and verifies the environment with `python -m pip check`, `python -m pytest --version`, and `python -m ruff --version`.

### Codex review versus implementation authority

Hosted Codex PR review remains a reviewer path. It should not be treated as the authoritative repository write path because its hosted checkout may not expose a writable Git remote and its optional PR-writing helper is outside ED-Finder's control.

Repository writes are routed through three separate trust domains:

1. A small GitHub-hosted **prepare job** validates mode and branch routing before Codex exists. It refuses `main`, `master`, `codex-task-requests`, `chatgpt-ops-requests`, and `chatgpt-ed-new-ops-requests`; captures the exact target/base SHA; and emits only validated branch/SHA metadata. Arbitrary task text is never written to `$GITHUB_OUTPUT`.
2. The **Codex job** runs on the self-hosted Codex runner pool with `contents: read` only. It first gates trusted `main`, then fetches complete history for the immutable selected base, rechecks that the prepared SHA has not moved, checks out the exact target, runs the mandatory state gate again on that target, and only then installs the target's pinned test dependencies. Codex runs without any push credential. After Codex finishes, the wrapper commits the result without credentials, proves it still descends from the immutable base, refuses to create a result while the repository remains shallow, writes the candidate to a fixed sealed ref, and uploads a one-day self-contained Git bundle through a pinned artifact action. No routing or expected-head value produced by the Codex job is trusted by later jobs.
3. A separate **trusted push job runs on GitHub-hosted `ubuntu-latest`**, not on the self-hosted Codex runner pool. This is a host-level trust boundary as well as a job-level one: a detached process or persistent same-user modification left by `codex exec` on a self-hosted worker cannot observe the later credentialed push. The push job receives routing and expected-head metadata only from the prepare job, never receives task text and never runs Codex. It downloads only the sealed bundle, creates a fresh wrapper-owned Git directory and HOME, pins `https://github.com/${GITHUB_REPOSITORY}.git`, disables inherited system/global Git configuration and hooks, resets PATH to trusted system binaries, verifies the bundle is descended from the immutable base, and determines whether the change touches workflow files before any push credential is exposed.
4. Only the final Git-only step receives the scoped GitHub write token/PAT. Existing-branch updates use `--force-with-lease=<ref>:<expected-sha>` as a server-side compare-and-swap; new-branch creation uses an empty expected-ref lease. The ancestry proof means the lease is never authority to rewrite history.

This design protects both directions of the boundary: Codex cannot acquire the write credential, and Codex-controlled output cannot change the target branch or the expected remote SHA used by the trusted writer. Completing the source history before sealing ensures the fresh trusted repository can reconstruct the candidate from the bundle without relying on hidden shallow-clone prerequisites. Moving the writer to a GitHub-hosted ephemeral machine additionally prevents self-hosted runner persistence from bridging the credential boundary.

Updating an existing PR branch automatically updates that PR, so this path does not depend on a hosted `make_pr` helper. New implementation requests with no `target_branch` continue to create an isolated `codex/run-<run>-<attempt>` branch that ChatGPT can inspect and open as a PR through its GitHub connector.

For review-fix loops the preferred pattern is therefore:

`Codex review -> ChatGPT dispositions -> prepare immutable branch/SHA -> gate exact target -> install target dependencies -> self-hosted Codex -> complete sealed artifact -> GitHub-hosted trusted push -> fresh CI/re-review`

This separation keeps reviewer independence while making repository writes deterministic and auditable.

### Codex implementation push credential

`CODEX_WORKER_GIT_TOKEN` should contain a fine-grained personal access token limited to this repository with `Contents: read/write` and `Workflows: read/write`. A broad classic token is not preferred. A GitHub App token is also suitable if generated at runtime with equivalent narrow authority.

An **existing PR branch update requires `CODEX_WORKER_GIT_TOKEN`**. The workflow does not fall back to the job `GITHUB_TOKEN` for that case because GitHub suppresses ordinary workflow events caused by `GITHUB_TOKEN`; using it to update an already-open PR could leave the new head without fresh CI, Semgrep, Review Lab, and other pull-request checks. The external PAT/App-style credential ensures the branch push behaves like an ordinary repository write and triggers fresh validation. Workflow-file changes also require the same token because the scoped `GITHUB_TOKEN` cannot modify `.github/workflows/*`.

For a brand-new isolated `codex/run-*` branch that does not modify workflow files, the trusted push job may still fall back to its scoped `GITHUB_TOKEN`. Opening the later PR is a separate action that establishes the normal pull-request validation cycle.

The privileged credential is intentionally not passed to `actions/checkout`, the Codex CLI, the task prompt, the Codex execution environment, the sealing step, the artifact upload/download, or the reconstruction step. The trusted writer first reconstructs and verifies the candidate using no push credential. Only its final Git-only step exposes the selected token through a temporary `GIT_ASKPASS` helper. The token is therefore not embedded in command arguments, remote URLs, repository configuration, artifacts, or any process/file system that Codex can influence.

If an existing PR update or workflow-file change is requested while `CODEX_WORKER_GIT_TOKEN` is absent, the trusted push job fails closed before attempting the push and reports the missing credential explicitly.

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
