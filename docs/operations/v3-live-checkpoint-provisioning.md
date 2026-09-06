# V3 Live-Checkpoint Infrastructure Provisioning

## Boundary

This runbook describes the reviewed operator for provisioning the first V3
live-checkpoint host. The target is exactly Contabo
`vmi3542235` / `vmi3542235.contaboserver.net` on `x86_64`. It is
**NON-PRODUCTION**. Running this operator is not a release, application deploy,
production promotion, or grant of deployment target authority.

The committed [`target-authority.json`](../../deploy/v3-live-checkpoint/target-authority.json)
remains unchanged and stopped. A successful run emits a sanitized candidate
for a separate reviewed follow-up commit; that review is the only place target
authority may change.

## Control plane and request

Use **V3 live-checkpoint infrastructure provisioning**. It is a manual and
allowlisted request-file workflow with the dedicated `v3-live-checkpoint`
GitHub environment and only `V3_LIVE_CHECKPOINT_*` SSH secrets. Pinned
known-host verification is mandatory. It does not use the production
`ED_NEW_OPERATOR_*` boundary.

The only operation is `provision-infrastructure`. A request commit may change
exactly one JSON file below
`.github/v3-live-checkpoint-provision-requests/` on the dedicated request
branch. The request cannot select a host, remote path, command, release, or
credential. Optional backend and web values are accepted only as the two exact
canonical GHCR repositories at digest-pinned references and are used solely
for an anonymous pull proof.

The workflow checks out the implementation independently from trusted `main`,
builds a temporary allowlisted bundle, and streams it over SSH. The bundle
contains only the provisioner, canonical migration/seed helpers, SQL,
migration identity, and checkpoint Compose contract. It is removed after the
run. There is no persistent source checkout, `git pull`, application build, or
dependency resolution/build from repository source on the target.

## Fail-closed target gate

Before the first target mutation, the provisioner requires all of:

- short hostname `vmi3542235`;
- FQDN `vmi3542235.contaboserver.net`;
- machine architecture `x86_64` and package architecture `amd64`;
- an allowlisted supported Ubuntu release; and
- exactly these three active runner units, with no additional active
  `actions.runner.*` service:
  - `actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker.service`
  - `actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-2.service`
  - `actions.runner.brianstewart377-rgb-ed-finder.contabo-codex-worker-3.service`

The three services are never started, stopped, restarted, enabled, disabled,
or reconfigured. Package handling runs `needrestart` in list-only mode, and
their exact active set plus stable main PIDs/activation timestamps are checked
again after provisioning.
First-run foreign checkpoint paths, a container runtime/state, PostgreSQL
listener, or HTTP listener stop ownership instead of being adopted. A
root-owned marker permits a partial run to resume and makes repeat runs
idempotent.

## Owned persistent resources

The operator installs Docker Engine and Compose from Docker's signed Ubuntu
repository, plus `psql` and PostgreSQL 18 from the PostgreSQL Apt repository.
It then owns only:

- local rootful Docker context `edfinder-v3-checkpoint` at
  `unix:///var/run/docker.sock`, with operator-owned mode-`0700` config;
- empty/preserved external local bridge `edfinder-v3-checkpoint-app` at
  `172.30.54.0/24`, accepting attachments only from the fixed checkpoint
  `api` and `web` container names;
- native persistent database `edfinder_v3_checkpoint`, owned by the dedicated
  local/DB role `edfinder_checkpoint_db`;
- a generated read-only application DB role, password, and generated API
  admin token in `/etc/ed-finder/v3-checkpoint/api.env`, owner-only mode
  `0600`;
- `/var/lib/edfinder-v3-checkpoint/receipts` and the local Docker config,
  owner-only mode `0700`;
- loopback application origin `http://127.0.0.1:18080`; and
- an nginx HTTP-only route for exact Host
  `vmi3542235.contaboserver.net`, rejecting other hostnames and proxying only
  to that loopback origin.

The route does not configure DNS or TLS and never mentions or changes the
production hostname. Docker's external-network creation is infrastructure
only: the provisioner does not run Compose or create/start an application
container.

Provisioning and application deployment share the receipt-directory operation
lock, so a later idempotent provisioning refresh cannot overlap a deployment.

No Redis, Valkey, NATS, EDDN worker, OAuth activation, production database,
backup, restore, derived-data bootstrap, or V2 data source is part of this
operator.

## Fresh preview database and identity proof

The database is created only inside the provisioner's independently owned
namespace. It never copies production data. On first bootstrap the dedicated
owner runs canonical `scripts/seed_check.sh`, which invokes
`scripts/apply_migrations.sh --include-manual`, applies
`sql/seed_preview.sql`, checks the preview counts and rating coverage, and
refreshes the map/archetype materialized views. This is the repository's
existing Finder/search/detail/map preview dataset.

After grants are reduced to the application read role, the provisioner repeats
the seed acceptance checks in a transaction-read-only session. It also compares
the complete live `schema_migrations` ledger with the migration entries
generated by canonical `v3_release_manifest.migration_set()` from the trusted
bundle. Only that bounded read-only proof can produce the fresh sanitized
`ed-finder/v3-live-checkpoint-schema-identity/v2` receipt. The receipt contains
no DSN, username, or password and its SHA-256 is recorded in the authority
candidate.

Credentials are generated once on target, retained on an idempotent rerun,
never printed, and never uploaded. Command output is redirected to a private
temporary log that is deleted before return.

## GHCR authority and artifacts

No registry credential is accepted by this workflow. If both optional
digest-pinned image references are supplied, Docker uses a temporary empty
configuration to attempt actual anonymous pulls. The candidate records
anonymous/public pull authority only when both succeed. Missing or failed
proof emits the sanitized blocker
`explicit_secret_backed_ghcr_pull_authority_required`; a later design must
name an explicit secret-backed authority rather than inventing credentials.

The only uploaded files are:

- `provisioning-receipt.json`; and
- `target-authority-candidate.json`.

Review the receipt, schema identity, exact runner preservation, package/runtime
facts, path owners/modes, route, and GHCR result. Do not treat the candidate as
active authority and do not copy it mechanically over the committed authority.
If a run stops after mutation begins, inspect the sanitized failure receipt and
rerun the same operator; do not delete persistent database, network, receipts,
or Docker state to simulate a clean run.
