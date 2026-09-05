# Operator Scripts

Read `docs/operations/infrastructure-status.md` and `docs/operations/operator-command-contexts.md` before executing any operator script.

## Production rule

A script is a current production operator command only when a current V3 workflow or runbook explicitly identifies it, its target environment, and its safety boundary.

Do not promote a repository helper into a production command merely because it exists under `scripts/operator/`.

## Current replacement-host helpers

- `actions/v3-app-deploy-preflight.sh`: fail-closed, read-only checkpoint
  deployment preflight. The environment-gated workflow invokes it only after
  verifying digest release and rollback manifests. It verifies the fixed V3
  host identity, emits every unresolved topology/secret/schema/rollback fact,
  and always stops without reading secrets, accessing the database, pulling
  images, writing files, or changing services.
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
