# V3 production application release

## Authority and execution boundary

This is the production-in-place application promotion authority for the exact
target `ed-finder-prod` / `nb79a3d.mevnode.com`. The only executable workflow is
`.github/workflows/v3-production-application-deploy.yml`; it is manual-only,
must run from the exact current `main`, and uses protected production
environments plus pinned SSH host trust.

Creating or reviewing this authority does **not** authorize executing it during
a pull request or implementation task. No command in this runbook was executed
against production while it was implemented. Do not use the Contabo checkpoint,
the root `docker-compose.yml`, a host checkout, or a legacy deployment script as
production authority.

The generic `.github/workflows/v3-application-release.yml` remains the immutable
off-host build authority. It produces digest-only backend and Svelte web images,
an exact `build_sha`, a checksummed migration set, explicit schema compatibility,
and application-only rollback eligibility. Production consumes that artifact;
it never builds, resolves dependencies, installs packages, or runs `git pull`.

## Current fail-closed state

The committed `deploy/v3-production/target-authority.json` is intentionally
`stopped`. Read-only host-status run `34202433965` proves the named production
containers, retained PostgreSQL 18 container, Redis, NATS, edge, and temporary
UI shell. It does not prove the application network, secret-file path and mode,
local Docker context, receipt store, live migration ledger identity, or the
exact edge-to-loopback cutover topology.

Run only the workflow's default `inventory` operation first. It uses the
already-present host `python3` standard library and performs only bounded
runtime, Docker, listener, HTTP, and `BEGIN READ ONLY` ledger inspection. The
machine-readable receipt must identify the bounded executable path,
implementation, and version of the default `python3` used to run inventory,
and separately state whether `python3.14` exists, its bounded executable path
and version when present, and whether it is exactly CPython 3.14. This
inspection is evidence for
`production_promotion_cpython314_runtime_unproved`; it does not install or
provision a runtime.

The same receipt must inspect Docker context `default` and expose only its
context name and Docker endpoint/host. It must not emit Docker configuration or
credentials. Review that fact as evidence for
`production_local_docker_context_authority_missing`. Where the already-bounded
Docker port inventory makes it possible, the receipt must also identify the
container owners of loopback ports `58080` and `58081`, including an explicit
unowned result, as evidence for the unchanged-edge/cutover topology review.

The receipt excludes container environments, env-file contents, DSNs,
passwords, tokens, private keys, and Docker credential/configuration content.
Review the sanitized receipt in a separate PR and replace every `null`
authority plus every blocker only with exact reviewed facts. Inventory never
edits `target-authority.json`, fills a blocker, or changes its committed
`stopped` status automatically. Changing the target to `authorized` without
those facts is invalid.

Read-only inventory may use the reported already-present default host `python3`
standard-library runtime. Authority and preflight prefer a bounded, validated
exact CPython 3.14 and may fall back only to a bounded, validated CPython 3.9 or
newer host `python3`. An unsupported runtime emits an operation-accurate stopped
receipt and performs no installation. Actual production mutation retains the
repository's exact CPython 3.14 execution contract and stops with
`python314_required_for_production_mutation` if that runtime is absent. This
runbook does not authorize installing it; runtime provisioning, if genuinely
needed for promotion, requires separate review and is not a status-tool repair.

No current production migration authority exists in this repository. If the
fresh complete `public.schema_migrations` filename/checksum ledger cannot be
mapped to a reviewed `ed-finder/v3-production-schema-identity/v1` file, or the
candidate release does not explicitly list that identity as compatible,
preflight emits `production_migration_authority_absent_or_schema_incompatible`.
It must not invoke `apply_migrations.sh`, baseline a ledger, run SQL migrations,
or perform application-data writes. A schema delta requires a separate reviewed
production migration authority; this release path never creates one.

## Persistent application topology

`deploy/v3-production/compose.yml` is a separate project named
`edfinder-v3-production`. It owns only blue/green API and web application slots.
It contains no database, volume, Redis/Valkey, NATS, edge, proxy, Octopus, lab,
bench, or unrelated service. The external application network and API secret
file must be exact reviewed authorities.

Candidate startup explicitly disables EDDN simulation ingest and startup
`admin_job_runs` reaping so staging cannot initiate background or housekeeping
writes. Redis and NATS are not removed or replaced. The current public-auth/TLS
edge is never recreated.

Promotion uses these gates in order:

1. Authenticate a successful manual canonical release run from exact `main`;
   verify its adjacent basename-only checksum, digest images, and OCI revision.
2. Recheck exact host/FQDN/architecture, the local rootful Docker context,
   Compose checksum/service/volume allowlist, secret-file metadata, receipt
   store, live CPU/memory/disk headroom, external network, and protected
   running container identities.
3. Under the production deployment lock, query the complete ledger in a bounded
   read-only transaction and require exact compatibility before any pull.
4. Require exactly one `127.0.0.1` Docker binding for the active origin and no
   staging binding; wildcard, IPv6, alternate-address, duplicate, and extra
   mappings stop the operation. Freeze the authorized secret file to a private
   mode-0600 snapshot, use ephemeral GHCR credentials, pull only the two digest
   images, and start the inactive app slot on `127.0.0.1:58081`.
5. Require bounded Svelte, health/build/database, OpenAPI, and anonymous-session
   smoke success. Recheck every protected container before cutover.
6. Stop only the prior app origin, bind the verified candidate web slot to
   `127.0.0.1:58080`, leave `edfinder-v3-public-auth-edge` untouched, and require
   both loopback and public HTTPS smoke success. Only after that verification,
   stop the stale legacy API on bootstrap or retire the prior managed slot on
   an upgrade.
7. Persist a sanitized immutable receipt, byte-exact manifest and checksums, then
   atomically advance `current.json`. Remove the secret snapshot and registry
   credentials on every exit.

Cancellation is a controlled deployment failure. The remote transport forwards
one termination signal and waits while the deployer terminates and reaps its
active bounded subprocess, performs any required application rollback, writes a
durable failure receipt, and removes ephemeral credentials.

The first promotion cannot describe stale `edfinder-v3-api:phase4c-r5` as an
accepted immutable rollback. Before cutover it can remove only its inactive
candidate. If the first verified port swap fails, it may abort the cutover by
restarting both stale legacy application services; the receipt labels this as
a cutover abort, not an accepted-release rollback. Every later upgrade may roll
back only to the checksum-bound prior accepted production manifest/receipt,
only when the fresh live schema identity is still explicitly compatible, and
with `--pull never`. There is no database rollback in this path.

## Owner sequence after blockers are reviewed away

1. Dispatch `inventory` and review the sanitized receipt without changing the
   host. Require the default inventory Python executable,
   implementation/version, the separate exact-CPython-3.14 executable and
   availability result, Docker `default` context name and endpoint/host, and
   bounded ownership of loopback ports `58080` and `58081`; missing or
   malformed facts keep the corresponding blockers in place.
2. Land a separate reviewed PR that supplies exact non-secret target and schema
   authority. Required secrets live only in the protected
   `v3-production-readonly` / `v3-production` environments as
   `V3_PRODUCTION_HOST`, `V3_PRODUCTION_PORT`, `V3_PRODUCTION_USER`,
   `V3_PRODUCTION_SSH_KEY`, and `V3_PRODUCTION_SSH_KNOWN_HOSTS`.
3. Build a candidate through `V3 application immutable release`, with the
   observed production migration identity explicitly reviewed as compatible.
4. Dispatch `preflight` with the exact release run ID and literal confirmation
   `ed-finder-prod/nb79a3d.mevnode.com`. Review the stopped/passed receipt.
5. Only after owner approval, dispatch `promote` with the same inputs and the
   correct `bootstrap` or `upgrade` mode.

If any fact differs, stop. Do not repair infrastructure, alter the database,
recreate the edge, or adapt a legacy/root Compose command from this runbook.
