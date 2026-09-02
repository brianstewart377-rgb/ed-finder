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

The first implementation uses GitHub Actions `workflow_dispatch` as the control surface because ChatGPT already has direct GitHub access. Workflows invoke a small allowlisted dispatcher and existing operator scripts.

Server connectivity must use already-authorized deployment/SSH credentials if they exist in GitHub Actions. This repository must not embed or create secrets in source control.

If the repository does not already have suitable Actions credentials, a workflow may be merged in an inert state and the remaining owner action is to add the required GitHub Actions secret/runner connection.

## Codex bridge

Codex task requests are intentionally asynchronous so a ChatGPT web or desktop turn never needs to stay open for the full Codex execution time.

The request path is:

`ChatGPT -> codex-task-requests -> Codex Dispatch -> workflow_dispatch -> GitHub-hosted prepare/source bundle -> self-hosted Codex -> sealed result -> GitHub-hosted trusted push`

A request is a single JSON file committed under `.github/codex-requests/` on the `codex-task-requests` branch. `.github/workflows/codex-dispatch.yml` validates that request on a GitHub-hosted runner, dispatches `.github/workflows/codex-laptop.yml` through `workflow_dispatch`, records a stable request identifier, and then exits. Its bounded job must never wait for the Codex worker to finish.

The long-running Codex execution remains on the self-hosted runner pool and has a stable request identifier in its workflow run name. The dispatcher prints `CODEX_DISPATCH_ACCEPTED=true` plus `CODEX_WORKER_RUN_ID=<id>` when the run becomes visible. If GitHub has accepted the dispatch but the worker run has not appeared within the short lookup window, the dispatcher prints `CODEX_WORKER_RUN_ID=pending` and still exits successfully.

ChatGPT clients should therefore report the dispatch acknowledgement/run ID immediately. A later turn may query the worker run for progress or results. A client-side timeout must not be treated as evidence that Codex failed unless the GitHub worker run itself failed or timed out.

The Codex execution job retains its 120-minute execution limit, repository state gates, investigation immutability check, and isolated implementation-branch behavior. Independent Codex jobs remain parallel because there is no global concurrency group.

### Credential-free source handoff

Repository source access is deliberately kept off the reused self-hosted Codex machine. A GitHub-hosted **prepare job** performs the authenticated read of `main` and, for existing-branch updates, the exact target branch. It captures the immutable main/base/expected-head SHAs, fetches complete history, and creates a self-contained Git bundle containing only the trusted source refs needed for the request. That source bundle is uploaded as a one-day Actions artifact.

The self-hosted **Codex job has no repository contents permission**. It downloads the source artifact, deletes and recreates its workspace, initializes a fresh local repository, imports the source bundle with hooks disabled, verifies the sealed SHAs, and deliberately configures **no network Git remote**. The canonical state gate is first run on the imported trusted `main`; implementation requests then select the exact immutable target/base, run the state gate again on that selected branch, and install that branch's pinned `tests/requirements-ci.txt` dependencies before Codex is invoked.

This means a persistent process, `.git` hook, Git configuration change, or ignored executable left behind by an earlier Codex run on the self-hosted machine never gets an opportunity to observe a GitHub repository token: no repository token is supplied to that host in the first place. The self-hosted job receives only Actions artifact-read authority needed for the source/result handoff.

### Codex review versus implementation authority

Hosted Codex PR review remains a reviewer path. It should not be treated as the authoritative repository write path because its hosted checkout may not expose a writable Git remote and its optional PR-writing helper is outside ED-Finder's control.

Repository writes are routed through three separate trust domains:

1. The GitHub-hosted **prepare job** validates mode and branch routing before Codex exists. It refuses `main`, `master`, `codex-task-requests`, `chatgpt-ops-requests`, and `chatgpt-ed-new-ops-requests`; captures the exact target/base SHA; fetches complete source history; seals main/target into the source bundle; and emits only validated branch/SHA metadata. Arbitrary task text is never written to `$GITHUB_OUTPUT`.
2. The self-hosted **Codex job** has Actions artifact-read authority but no repository contents authority. It reconstructs a fresh repository from the trusted source bundle with hooks disabled and no network remote, validates trusted main and the selected target state, installs target-specific pinned dependencies, then runs Codex without any repository credential. After Codex finishes, the wrapper commits locally, proves the candidate still descends from the immutable base, writes the candidate to a fixed sealed ref, and uploads a one-day self-contained result bundle. No routing or expected-head value produced by the Codex job is trusted by later jobs.
3. A separate **trusted push job runs on GitHub-hosted `ubuntu-latest`**, not on the self-hosted Codex runner pool. It receives routing and expected-head metadata only from the prepare job, never receives task text and never runs Codex. It downloads only the sealed result bundle, creates a fresh wrapper-owned Git directory and HOME, pins `https://github.com/${GITHUB_REPOSITORY}.git`, disables inherited system/global Git configuration and hooks, resets PATH to trusted system binaries, verifies candidate ancestry and workflow-file scope, and only then exposes a write credential.
4. Only the final Git-only step receives the scoped GitHub write token/PAT. Existing-branch updates use `--force-with-lease=<ref>:<expected-sha>` as a server-side compare-and-swap; new-branch creation uses an empty expected-ref lease. The ancestry proof means the lease is never authority to rewrite history.

This design protects both directions of the boundary: Codex cannot acquire a repository credential, and Codex-controlled output cannot change the target branch or expected remote SHA used by the trusted writer. The source and result bundles carry Git objects/refs, not Git configuration or hooks, so host-local Git state does not cross either trust boundary.

Updating an existing PR branch automatically updates that PR, so this path does not depend on a hosted `make_pr` helper. New implementation requests with no `target_branch` continue to create an isolated `codex/run-<run>-<attempt>` branch that ChatGPT can inspect and open as a PR through its GitHub connector.

For review-fix loops the preferred pattern is therefore:

`Codex review -> ChatGPT dispositions -> prepare immutable branch/SHA + source bundle -> credential-free self-hosted validation/Codex -> sealed result -> GitHub-hosted trusted push -> fresh CI/re-review`

This separation keeps reviewer independence while making repository writes deterministic and auditable.

### Codex implementation push credential

`CODEX_WORKER_GIT_TOKEN` should contain a fine-grained personal access token limited to this repository with `Contents: read/write` and `Workflows: read/write`. A broad classic token is not preferred. A GitHub App token is also suitable if generated at runtime with equivalent narrow authority.

An **existing PR branch update requires `CODEX_WORKER_GIT_TOKEN`**. The workflow does not fall back to the job `GITHUB_TOKEN` for that case because GitHub suppresses ordinary workflow events caused by `GITHUB_TOKEN`; using it to update an already-open PR could leave the new head without fresh CI, Semgrep, Review Lab, and other pull-request checks. The external PAT/App-style credential ensures the branch push behaves like an ordinary repository write and triggers fresh validation. Workflow-file changes also require the same token because the scoped `GITHUB_TOKEN` cannot modify `.github/workflows/*`.

For a brand-new isolated `codex/run-*` branch that does not modify workflow files, the trusted push job may still fall back to its scoped `GITHUB_TOKEN`. Opening the later PR is a separate action that establishes the normal pull-request validation cycle.

The privileged credential is intentionally not passed to the prepare source artifact, the self-hosted Codex job, the Codex CLI, the task prompt, the Codex working repository, the result sealing step, or either artifact. The trusted writer reconstructs and verifies the candidate using no push credential. Only its final Git-only step exposes the selected token through a temporary `GIT_ASKPASS` helper. The token is therefore not embedded in command arguments, artifacts, or any process/file system that Codex can influence.

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
