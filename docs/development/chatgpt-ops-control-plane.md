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

### Disposable execution boundary (host prerequisite)

The self-hosted Codex runner executes arbitrary model-authored code. A job cannot make itself trustworthy from the inside: workflow steps run *after* the environment already exists, so they cannot reliably terminate root/other-UID helpers or containers left by a previous run, and an in-job "kill every same-user process" sweep would also destroy sibling runner listeners and unrelated services. Isolation must therefore come from **trusted host infrastructure**, not from repository code.

The Codex runner **must** be provisioned as a single-use, disposable boundary: an ephemeral runner registered with `--ephemeral` on a fresh VM or container that is destroyed after exactly one job. It **must** carry a dedicated `codex-ephemeral` runner label (the `codex` job requires `runs-on: [self-hosted, Linux, X64, codex-ephemeral]`) so that only disposable workers — never an ordinary reused self-hosted runner sharing the generic labels — are eligible for the job. The host owner attests disposability by setting `CODEX_WORKER_EPHEMERAL_BOUNDARY=1` in the runner **service** environment (for example the runner's `.env` file). The worker's first step reads that marker from the runner process environment — never from a workflow `${{ }}` expression — and fails closed if it is absent.

This marker is host-owned and cannot be forged by repository or Codex-authored code: a job step can only influence its own job's later steps (via `$GITHUB_ENV`), never the runner service process that a *subsequent* job inherits its environment from, and a genuinely disposable runner has no subsequent job to compromise. Do **not** set this marker (or apply the `codex-ephemeral` label) on a reused/long-lived runner; doing so would falsely assert single-use disposability and defeat the boundary.

This host-owned boundary — not any in-job process quarantine — is what prevents one Codex invocation's processes, containers, on-disk `HOME` state, caches, or planted executables from surviving into or modifying the next.

**Deferred to the Temporal worker architecture (accepted residual).** Fully isolating the Codex *login* credential from untrusted target-branch code is **not** solved here and is deliberately owned by the forthcoming Temporal-orchestrated worker. For an existing-branch update the target branch's own code runs in the same GitHub Actions job/identity that later invokes Codex — the state validator, the pinned-dependency install, and the resulting virtualenv are all unreviewed target code. Because they share the job identity, they can reach the login through same-job channels that repository YAML cannot fully close (a hard-coded absolute-path read, injecting `BASH_ENV`/`$GITHUB_ENV`/`$GITHUB_PATH` into the later credentialed step, or `PATH`-shadowing the `codex` binary via a poisoned `.venv/bin`). The robust fix is to run untrusted target execution under a **separate identity or sandbox** from the credential — a property of the durable Temporal worker, not this bridge. Until then the mitigations above stand: the disposable single-use runner bounds any leak to one throwaway job's login, and the host owner should run Codex under a dedicated/rotatable credential. This is an accepted, owner-dispositioned residual, carried forward as a requirement of the Temporal worker spec; it is not a blocker to the bounded worker primitive this workflow provides.

**Codex credential isolation.** The Codex CLI login (normally `~/.codex`) is a credential that any code running as the runner user can read by absolute path. The worker keeps `HOME` isolated for the whole job and records the login location as a **step output** of the reconstruct step, which GitHub injects only into steps that reference it — here, the two sandboxed `codex exec` steps, each of which sets `CODEX_HOME` from it and fails closed if the login is absent. The path is deliberately **not** written to `$GITHUB_ENV`, which would broadcast it to every later step in the job. As a result the untrusted target-branch code that runs before the sandbox — the state validator and the pinned-dependency install for an existing-branch update — does not receive the credential location in its environment or through the default `~/.codex` lookup. This does not stop that pre-sandbox code from reading the login file by a hard-coded absolute path, which is a host-identity property that repository YAML cannot enforce. The host owner **should** therefore run Codex under a dedicated identity, or provision a per-job / rotatable credential, so that untrusted in-job code cannot read a durable login; the disposable single-use boundary bounds the blast radius of any residual read to that one throwaway job's credential.

### Credential-free source handoff

Repository source access is deliberately kept off the reused self-hosted Codex machine. A GitHub-hosted **prepare job** performs the authenticated read of `main` and, for existing-branch updates, the exact target branch. It captures the immutable main/base/expected-head SHAs, fetches complete history, and creates a self-contained Git bundle containing only the trusted source refs needed for the request. That source bundle is uploaded as a one-day Actions artifact.

The self-hosted **Codex job has no repository contents permission**. It first requires a host-owned disposable-boundary attestation (see above), then downloads the source artifact, deletes and recreates its workspace, initializes a fresh local repository, imports the source bundle, verifies the sealed SHAs, and deliberately configures **no network Git remote**. Before its first Git invocation it records where the runner's Codex login lives and then isolates `HOME`/`XDG_CONFIG_HOME` to a per-run temporary directory, additionally neutralizing system/global Git configuration and the system attributes file through Git's own environment variables (`GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`, `GIT_ATTR_NOSYSTEM`), disabling hooks with per-command `core.hooksPath=/dev/null`, and neutralizing the default global attributes file with `core.attributesFile=/dev/null` on the working-tree checkouts. This prevents a persistent `~/.gitconfig`, global `core.attributesFile`/`gitattributes`, smudge filter, or hook configuration left by an earlier Codex run from affecting the workspace while the trusted bundle is materialized. Codex authentication is preserved without exposing it to that pre-sandbox surface: the recorded login location is handed to the `codex exec` steps alone via `CODEX_HOME` (see **Codex credential isolation** above), and those steps fail closed if the login is absent.

The pinned `actions/setup-python` step on the self-hosted job is also given an explicitly empty `token` input instead of accepting its GitHub.com default. The self-hosted job therefore does not hand the repository-scoped job token to that action. Its only GitHub-side authority is the Actions artifact capability required to receive the source bundle and upload the sealed result; repository source and write credentials remain confined to GitHub-hosted trust domains.

The canonical state gate is first run on the imported trusted `main`; implementation requests then select the exact immutable target/base, run the state gate again on that selected branch, and install that branch's pinned `tests/requirements-ci.txt` dependencies before Codex is invoked. For an existing-branch update this selected-branch validator and dependency install are unreviewed target code; they run with the isolated `HOME` and without `CODEX_HOME`, so they cannot obtain the Codex login through the environment or the default lookup path.

This means a persistent process, `.git` hook, Git configuration change, ignored executable, global attribute/filter, or setup-action token default left behind by an earlier Codex run on the self-hosted machine never gets an opportunity to observe a GitHub repository credential: no repository credential is supplied to that host in the first place, inherited Git execution configuration is ignored, and setup-python receives no token.

### Codex review versus implementation authority

Hosted Codex PR review remains a reviewer path. It should not be treated as the authoritative repository write path because its hosted checkout may not expose a writable Git remote and its optional PR-writing helper is outside ED-Finder's control.

Repository writes are routed through three separate trust domains:

1. The GitHub-hosted **prepare job** validates mode and branch routing before Codex exists. It refuses `main`, `master`, `codex-task-requests`, `chatgpt-ops-requests`, and `chatgpt-ed-new-ops-requests`; captures the exact target/base SHA; fetches complete source history; seals main/target into the source bundle; and emits only validated branch/SHA metadata. Arbitrary task text is never written to `$GITHUB_OUTPUT`.
2. The self-hosted **Codex job** has Actions artifact-read authority but no repository contents authority. It reconstructs a fresh repository from the trusted source bundle under isolated Git/HOME configuration with hooks disabled and no network remote, validates trusted main and the selected target state, installs target-specific pinned dependencies, then runs Codex without any repository credential. After Codex finishes, the wrapper commits locally, proves the candidate still descends from the immutable base, writes the candidate to a fixed sealed ref, and uploads a one-day self-contained result bundle. No routing or expected-head value produced by the Codex job is trusted by later jobs.
3. A separate **trusted push job runs on GitHub-hosted `ubuntu-latest`**, not on the self-hosted Codex runner pool. It receives routing and expected-head metadata only from the prepare job, never receives task text and never runs Codex. It downloads only the sealed result bundle, creates a fresh wrapper-owned Git directory and HOME, pins `https://github.com/${GITHUB_REPOSITORY}.git`, disables inherited system/global Git configuration and hooks, resets PATH to trusted system binaries, verifies candidate ancestry and workflow-file scope, and only then exposes a write credential.
4. Only the final Git-only step receives the scoped GitHub write token/PAT. Existing-branch updates use `--force-with-lease=<ref>:<expected-sha>` as a server-side compare-and-swap; new-branch creation uses an empty expected-ref lease. The ancestry proof means the lease is never authority to rewrite history.

This design protects both directions of the boundary: Codex cannot acquire a repository credential, and Codex-controlled output cannot change the target branch or expected remote SHA used by the trusted writer. The source and result bundles carry Git objects/refs, not host Git config or hooks, so host-local Git state does not cross either trust boundary.

Updating an existing PR branch automatically updates that PR, so this path does not depend on a hosted `make_pr` helper. New implementation requests with no `target_branch` continue to create an isolated `codex/run-<run>-<attempt>` branch that ChatGPT can inspect and open as a PR through its GitHub connector.

For review-fix loops the preferred pattern is therefore:

`Codex review -> ChatGPT dispositions -> prepare immutable branch/SHA + source bundle -> credential-free self-hosted validation/Codex -> sealed result -> GitHub-hosted trusted push -> fresh CI/re-review`

This separation keeps reviewer independence while making repository writes deterministic and auditable.

### Codex implementation push credential

`CODEX_WORKER_GIT_TOKEN` should contain a fine-grained personal access token limited to this repository with `Contents: read/write`. It does **not** need `Workflows` authority: the trusted push job rejects any candidate that changes `.github/workflows/**`, so the normal path never writes workflow files. A broad classic token is not preferred. A GitHub App token is also suitable if generated at runtime with equivalent narrow authority.

An **existing PR branch update requires `CODEX_WORKER_GIT_TOKEN`**. The workflow does not fall back to the job `GITHUB_TOKEN` for that case because GitHub suppresses ordinary workflow events caused by `GITHUB_TOKEN`; using it to update an already-open PR could leave the new head without fresh CI, Semgrep, Review Lab, and other pull-request checks. The external PAT/App-style credential ensures the branch push behaves like an ordinary repository write and triggers fresh validation. **Workflow-file changes are not supported by this path at all**: the trusted push job fails closed if the Codex candidate modifies anything under `.github/workflows/`, because normal implementation output must never be able to alter control-plane authority and then have a stronger credential publish it. A privileged workflow-change path, if ever wanted, is a separate owner-approved trusted operation and is intentionally not built here.

For a brand-new isolated `codex/run-*` branch that does not modify workflow files, the trusted push job may still fall back to its scoped `GITHUB_TOKEN`. Opening the later PR is a separate action that establishes the normal pull-request validation cycle.

The privileged credential is intentionally not passed to the prepare source artifact, the self-hosted Codex job, the Codex CLI, the task prompt, the Codex working repository, the result sealing step, or either artifact. The trusted writer reconstructs and verifies the candidate using no push credential. Only its final Git-only step exposes the selected token through a temporary `GIT_ASKPASS` helper. The token is therefore not embedded in command arguments, artifacts, or any process/file system that Codex can influence.

If an existing PR update is requested while `CODEX_WORKER_GIT_TOKEN` is absent, the trusted push job fails closed before attempting the push and reports the missing credential explicitly. A candidate that modifies `.github/workflows/**` is rejected regardless of which credential is present.

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
