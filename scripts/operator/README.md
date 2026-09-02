# Operator Scripts

## Infrastructure status

**The former Hetzner V2 production host was decommissioned on 2 September 2026.**

Do not treat this directory as a Hetzner command menu. It now contains a mixture of current replacement-host helpers and retained V2 operator/history material.

Read `docs/operations/infrastructure-status.md` and `docs/operations/operator-command-contexts.md` before executing any operator script.

## Current rule

A script is a current production operator command only when its own contract explicitly identifies the current V3/replacement environment and its safety boundary.

A script that requires the legacy Hetzner hostname `ed-finder`, old production IP, or former host paths is **retired**. Do not weaken or bypass its guard to make it run on the replacement host.

## Current replacement-host helpers

- `actions/octopus-qdrant-healthcheck-repair.sh`: narrowly repairs the known
  broken `wget` healthcheck in Octopus v1.0.122's Qdrant Compose service,
  accepts the exact repaired state on a resumable rerun, recreates only Qdrant,
  verifies the existing Postgres container is healthy without accessing it,
  and starts/verifies web without managing its dependencies. It does not read
  `.env`, access a database, or modify volumes.
- `actions/octopus-edge-status.sh`: fail-closed, read-only status receipt for
  Octopus v1.0.122 on short host `ed-finder-prod`. It reports the bounded edge listeners,
  relevant containers, internal health/version, sanitized nginx routing, DNS,
  public HTTP/HTTPS responses, and the certificate actually served for Octopus
  SNI. It does not read environment or private-key files, access a database,
  write files, or restart services.
- `recover_v3_runtime_contract.py`: read-only helper for the allowlisted ed-new
  `recover-v3-runtime-contract` operation. It identifies the retained Phase 4C
  R5 Compose source root from container labels, rejects secret-like and unsafe
  paths, and streams a bounded checksummed source archive without database
  access or remote-host writes.

These helpers still require their own host/environment checks. Their presence here does not authorize a production action by itself.

## Retired Hetzner/V2 operator material

The shared guard `require_hetzner_operator_env.sh` and workflows that depend on it describe the former Hetzner V2 environment. That environment no longer exists as an ED-Finder operator target.

Retained examples include:

- `require_hetzner_operator_env.sh`;
- `stage18j_run_station_type_dry_run.sh`;
- `stage19ba_bounded_production_staging_activation.py` where its contract assumes the former production-staging environment;
- `stage19bb_first_production_staging_activation.py` where its contract assumes the former production-staging environment;
- historical Stage 18J wrappers under `scripts/operator/archive/stage18j/`.

These files remain useful as implementation history, receipts, safety examples, and migration evidence. They are not current V3 deployment or production-operation instructions.

Do not:

- run them against the replacement host by changing expected hostnames or paths;
- recreate old V2 services solely to satisfy their guards;
- restore obsolete V2 credentials to make them executable;
- infer that `/opt/ed-finder` or `/var/lib/ed-finder/operator-artifacts` on a different machine is equivalent to the retired Hetzner environment.

## Historical evidence

Archived historical wrappers include:

- `scripts/operator/archive/stage18j/stage18j_run_compact_summary.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_review_packet.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_load_dry_run.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_approval_allowlist.sh`

The sanitized execution evidence for the completed bounded `100 -> 1,000 ->
10,000` Stage 19BB ladder is recorded in
`docs/colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`.

Historical documents should continue to say Hetzner where that is factually where the operation occurred. Historical accuracy is not current execution authority.

## Legacy data recovery

The old server is not required for V2 data recovery. The validated V2 PostgreSQL custom-format dump was synchronized offsite before decommission and is retained as the legacy migration vault.

Use that dump only through a purpose-built selective migration/recovery path. Do not restore it wholesale as the V3 operating database and do not copy the old PostgreSQL physical data directory into PostgreSQL 18.

## Private material

Production artifacts and credentials are private operator material and should not be committed unless explicitly sanitized and reviewed. Current V3 secrets must come from the current recovery/credential process, not from retired V2 runbooks.
