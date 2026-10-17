# Operator Command Contexts

## Purpose

This document separates ED-Finder command contexts so repository work, local development, and current V3 production operations are not confused.

## Current environments

| Environment | Typical context | Purpose |
|---|---|---|
| Codex / repo environment | A checked-out repository or GitHub branch/PR | Code, docs, tests, validation, commits, and PRs. |
| DAVE2 / local development | Developer checkout and disposable local services | Local development and non-production validation. |
| V3 production | Current replacement-host runbooks and workflows only | Production services, backup/recovery, identity, and operator actions. |

## Codex / repo environment

Use Codex/repository tooling for:

- editing code and documentation;
- writing and running repository tests;
- local/static validation;
- opening and updating PRs;
- documenting operator procedures without executing production commands.

Git history and removed operational artifacts are not current execution authority.

## DAVE2 / local development

DAVE2/local development is useful for local builds, disposable services, and non-production experiments. It is not proof that a production command is safe.

Do not substitute a local Docker stack or local PostgreSQL instance for production when validating production procedures.

## V3 production

Production commands must come from a current runbook or workflow that explicitly identifies the replacement environment and its safety boundary.

Before any production action:

1. identify the target host/environment explicitly;
2. verify the procedure is part of the current V3 operator surface;
3. verify the intended host identity before executing destructive or stateful commands;
4. preserve current backup, credential, and least-privilege boundaries;
5. stop if the requested procedure exists only in Git history or an archived artifact.

## Legacy migration data

A validated offsite database dump is retained only as a selective migration source. Use it through a purpose-built, allowlisted migration/recovery process. Do not restore it wholesale as production and do not copy an older PostgreSQL physical data directory into PostgreSQL 18.

## Secret handling

Never paste real DSNs, passwords, secrets, private keys, recovery codes, or credential-bearing URLs into chat or Git.

Production credentials must be managed through the current V3 recovery/secret process.

## How to recognise the right prompt

Use Codex/repository tooling when the prompt asks for repo edits, docs, tests, validation, commits, or PRs.

Use DAVE2/local development for non-production application work.

Use current V3 operator procedures only when the prompt explicitly concerns production and the relevant current runbook/workflow has been identified.

If a requested production action is not present in the current V3 operator surface, stop rather than adapting an obsolete procedure.

## Operator scripts

`scripts/operator/` is a mixed repository-tooling directory, not a blanket production-operator namespace.

The only current replacement-host helpers presently identified by the V3 control plane are:

- `scripts/operator/actions/v3-app-status.sh`;
- `scripts/operator/actions/octopus-edge-status.sh`;
- `scripts/operator/actions/octopus-qdrant-healthcheck-repair.sh`;
- `scripts/operator/recover_v3_runtime_contract.py`;
- `scripts/operator/actions/v3-host-cleanup.sh` through the bounded operation below.

### Fixed production host clean-up

The owner authorized removal of four unused host directories following the
2026-10-17 `v3-disk-inventory` receipt from run `39018450185`. Implementation
base: current `origin/main` at `24d0c4d9127928b886d68f81da7eb200593ee9dc`
(includes #832). The fixed targets are:

- `/data/v3/source-artifacts/spansh/2026-08-24T205426Z`;
- `/root/edfinder-v3-benchmark`;
- `/root/.bun`;
- `/root/.codex`.

The only operator entry point is a manual dispatch of
[ChatGPT ed-new Ops](../../.github/workflows/chatgpt-ed-new-ops.yml) on `main`,
selecting `v3-host-cleanup`. Request-file pushes and dispatches on other refs
are refused for this operation. Trusted `main` supplies both the action and
`deploy/v3-production/target-authority.json`; no input, environment variable,
or argument selects a deletion path. The workflow retains pinned SSH trust,
uses the existing root/passwordless-sudo handoff, and holds the workflow's
`chatgpt-ed-new-ops` concurrency group, with cancellation disabled, including
during the attached SSH run. The governed derived purge job holds that same
group. The action also takes the purge's host lease at
`/run/lock/edfinder-v3-derived-purge.lock` before validation and holds it through
receipt printing. Clean-up and purge exclude each other through both this
non-blocking host lease and the workflow group, including if the runner or SSH
dies while the remote action continues. A held lease refuses every path with
`purge_host_lease_held`.

The action verifies `ed-finder-prod` / `nb79a3d.mevnode.com` against committed
target authority and runs for at most 1800 seconds. In the order above, it skips
absent paths and refuses unsafe paths: symlinks or symlinked parents, a changed
realpath, mount points or overlapping bind-mount sources, another filesystem,
non-root ownership, Docker volume or Docker-state containment, PostgreSQL data or a nested `PG_VERSION`. The Spansh
directory additionally requires no process to hold an open file beneath it.
It measures each accepted directory with `du -sx -B1`, removes only that exact
directory with `rm -rf --one-file-system --`, and verifies absence. A refusal
skips that directory and makes the final status `stopped`; other allowlisted
paths are still checked. Parents are never removal targets.

Every run attempts upload of `v3-host-cleanup-receipt` for 180 days and emits a
compact `Host clean-up` notice containing each path's outcome, estimated bytes
removed, and filesystem space reclaimed, including stopped runs. The JSON
receipt records per-path `bytes_removed_estimate` from `du -sx -B1` before
deletion (or null if unmeasured), and `filesystem_bytes_reclaimed` as root
filesystem available bytes after minus before (or null if either observation is
unavailable). The estimate can exceed space reclaimed because hard links or
open files retain blocks; the filesystem delta can also reflect other host
activity. A later refusal can retain the pre-deletion estimate, so always read
it alongside the outcome. The receipt also records root filesystem usage
before/after and whether any filesystem removal occurred. Database writes and
service changes remain false.
Review the notice and receipt before any retry; an already-removed path becomes
`already_absent`. This code change does not execute the clean-up.

The production application promotion surface is separately and exclusively
identified by `docs/operations/v3-production-application-release.md` and
`.github/workflows/v3-production-application-deploy.yml`. Its
`v3-production-inventory` operation is read-only and may use an already-present
host Python 3 standard-library runtime. Its preflight/promotion helper is not a
general operator command: the committed target authority is stopped and it may
run only from the exact protected workflow after all external facts are
reviewed. It never selects the root Compose or the Contabo authority.

`scripts/operator/actions/v3-app-live-checkpoint-preflight.sh` is separate from
that production surface. It targets the non-production Contabo live-checkpoint
boundary and launches the reviewed bootstrap/upgrade validator. The committed
target authority currently stops before pulls or service mutation because the
container runtime, database/config, origin/edge and receipt authorities are
absent. When those facts are separately reviewed, the same boundary may mutate
only its fixed `api` and `web` application allowlist; it never manages
PostgreSQL, Redis/Valkey, NATS, edge, runners or volumes.

Other scripts in that directory, including surviving Stage 19 staging/research tools, are **not** current V3 production authority merely because they are checked in. Read `scripts/operator/README.md` and require an explicitly current V3 workflow/runbook before executing any operator script against production.

## Final recommendation

Keep repository work, local/non-production development, and current V3 production operations clearly separated. Production work requires explicit current authority and a verified target environment.
