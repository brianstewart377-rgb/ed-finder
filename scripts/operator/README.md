# Operator Scripts

Read `docs/operations/infrastructure-status.md` and `docs/operations/operator-command-contexts.md` before executing any operator script.

## Production rule

A script is a current production operator command only when a current V3 workflow or runbook explicitly identifies it, its target environment, and its safety boundary.

Do not promote a repository helper into a production command merely because it exists under `scripts/operator/`.

## Contabo live-checkpoint helper

- `install_v3_checkpoint_host_interface.py`: the one-time, idempotent
  non-production host privilege installer. The owner uses the single command
  in `docs/operations/v3-live-checkpoint-infrastructure.md`; it resolves
  protected `main` through GitHub and stages immutable-SHA source in a fresh
  root-owned `/run` directory. Never execute this file as root from a mutable
  runner checkout. The installer independently checks that exact head before
  and after installation. It
  atomically installs the root-owned fixed launcher and bootstrap. It first
  removes the checkpoint sudo rule from the active include path and validates
  the complete policy, then installs the helper pair and installs the
  single host-specific sudoers rule for `codex` last. It validates the rule and
  full policy with `visudo`, and exercises `sudo -n` through the launcher's
  `--check` path. A failed validation or self-test transactionally restores all
  three prior files and revalidates the complete sudo policy, with sudo
  authority revoked first and the prior sudoers rule restored last. The rule preserves only `GH_TOKEN` and grants only
  `/usr/local/sbin/edfinder-v3-checkpoint-launcher`, never Python, Bash,
  `runuser`, Docker, or general command authority.
- `actions/edfinder-v3-checkpoint-launcher` and `v3_checkpoint_bootstrap.py`:
  reviewed sources for the installed root-owned interface. Workflows invoke
  only the fixed installed launcher. A SHA-256 handshake binds the committed
  launcher and bootstrap sources, both installed helpers, and the sealed
  request; the root-owned launcher enforces it. A stale launcher or bootstrap
  stops before artifact access and requires a deliberate installer rerun.
  Before download, the bootstrap also resolves
  the artifact's GitHub-owned workflow-run association and requires the exact
  operation artifact name, canonical workflow/event/repository, active trusted
  `main` head, and matching source SHA. These files must not be executed as
  privileged worktree helpers during normal provisioning or deployment.
- `actions/v3-app-live-checkpoint-preflight.sh`: CPython 3.14 launcher for the
  fail-closed `v3_checkpoint_deploy.py` bootstrap/upgrade boundary. Contabo is
  explicitly non-production and uses separate environment credentials. The
  helper verifies digest manifests, target authority, the fixed `api`/`web`
  allowlist, the selected context's exact `unix:///var/run/docker.sock` endpoint,
  the local bridge network's exact app-only attachments and aliases, app absence
  or the checksum-bound durable prior receipt/manifest, and the live database
  identity plus current applied migration set before any pull or service change.
  Database verification is read-only and never reports or persists the
  credential-bearing `DATABASE_URL`; Compose receives only a private verified
  snapshot that is retained through rollback and then removed. Candidate and
  rollback starts receive bounded readiness polling before authoritative smoke
  checks. Upgrade
  rollback recreates from the already-verified prior digest images with
  `--pull never` and no registry request; receipts account for database reads
  independently from service mutation. The committed authority currently stops
  because the runtime, database/config, origin/edge and receipt facts are absent.
  It does not manage database, cache, NATS, edge, runner or volume resources.

## Current replacement-host helpers
- `actions/v3-app-status.sh`: fail-closed, read-only application status receipt
  for the current ED-Finder V3 origin and public edge. It checks the fixed V3
  container set, the loopback origin listener, the frontend index classification,
  `/api/health`, anonymous `/api/auth/session`, and the runtime OpenAPI OAuth
  route surface. It does not start an OAuth login, read environment/private-key
  files, access PostgreSQL directly, write files, or restart services. The
  public application health endpoint may itself perform its normal bounded DB
  liveness read.
- `actions/octopus-qdrant-healthcheck-repair.sh`: narrowly repairs the known
  Qdrant healthcheck for the current Octopus service, recreates only Qdrant,
  verifies the existing Postgres container is healthy without accessing it,
  and starts/verifies web without managing its dependencies. It does not read
  `.env`, access a database, or modify volumes.
- `actions/octopus-edge-status.sh`: fail-closed, read-only status receipt for
  the current Octopus edge on `ed-finder-prod` / `nb79a3d.mevnode.com`. It
  reports bounded listeners, relevant containers, internal health/version,
  sanitized nginx routing, DNS, public HTTP/HTTPS responses, and the served
  certificate. It does not read environment or private-key files, access a
  database, write files, or restart services.
- `recover_v3_runtime_contract.py`: read-only helper for the allowlisted
  `recover-v3-runtime-contract` operation. It identifies the retained runtime
  source root from container labels, rejects secret-like and unsafe paths, and
  streams a bounded checksummed source archive without database access or
  remote-host writes.

These helpers still require their own host/environment checks. Their presence here does not authorize a production action by itself.

## Other scripts in this directory

Staging, migration, research, or historical-phase scripts that remain in this directory are repository tooling unless a current V3 runbook explicitly promotes them into the production operator surface. Do not run them against production by inference.

In particular, the surviving Stage 19 staging tools are retained as historical/research tooling and evidence of the bounded staging contracts they implemented; their presence is **not** current V3 production authorization:

- `stage19anr_warehouse_derived_staging_rehearsal.py`
- `stage19ar_edsm_25_row_staging_pilot.py`
- `stage19as_au_edsm_100_row_controlled_expansion.py`
- `stage19av_expanded_source_run_staging_pilot.py`
- `stage19ba_bounded_production_staging_activation.py`
- `stage19bb_first_production_staging_activation.py`

The historical Stage 19BB execution evidence remains indexed by `docs/colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`. That closeout is evidence of the completed bounded historical run, not permission to repeat it against V3.

Historical shell wrappers that are no longer part of the active operator surface belong under `scripts/operator/archive/`, not back at the top level.

## Legacy migration data

A validated offsite database dump is retained only as a selective migration source. Use it through a purpose-built reviewed migration path; do not restore it wholesale as the production database and do not copy an older PostgreSQL physical data directory into PostgreSQL 18.

## Private material

Production artifacts and credentials are private operator material and should not be committed unless explicitly sanitized and reviewed. Current production secrets must come from the current V3 recovery/credential process.
