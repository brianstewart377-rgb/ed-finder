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

## Current production state

The committed production target is authorized and has no recorded blockers.
The first governed promotion accepted release run `34527597963`, source
`b1616332c024e262a0aac03018943abbf619c087`, into the blue slot on 2026-09-10.
Public `/api/health` on 2026-09-13 still reported that exact build with
`database=connected`.

The retained PostgreSQL 18 database is
`edfinder_v3_phase4c_full_20260827_r5`, reached as
`edfinder-v3-phase4c-full-20260827_r5-postgres` by role `edfinder_v3`. Its
`v3_meta.schema_migration` ledger is the independent V3 lineage rather than the
V2 `sql/migration-manifest.txt` set. Migration 006 was applied and its exact
ledger hash verified before the Search worker launch reached its later
dependency failure in workflow run `34698167474`; read-only status run
`34698615774` then confirmed the migration's derived-product objects in use.

The reviewed transition advances that live lineage from 006 through the
additive migrations 008 and 009; 007 remains reserved. The target schema
identity is derived reproducibly by
`scripts/operator/v3_schema_identity.py` and pinned in
`deploy/v3-production/target-authority.json`. The active accepted release's
supplemental compatibility attestation is bound to its source SHA, release run,
manifest checksum and image digests, and covers every intermediate transition
identity. Schema migration is therefore a separate protected operation that
must complete before the application preflight and promotion.

## Live production state and the 2026-09-09 in-place promotion

Production was promoted in place on 2026-09-09T20:02Z, outside this workflow.
It serves `edfinder-v3-api:release-6a4fe0ef`
(`build_sha 6a4fe0ef1cb7b8fd03b4151dc8de4802fd3f4c99`) and
`edfinder-v3-production-web:release-1dc4d099`; the loopback origin and the
public edge report the same health body with `database=connected`. The
superseded containers were stopped and retained as
`edfinder-v3-api-pre-release-20260909T200206Z` and
`edfinder-v3-production-web-blue-pre-release-20260909T200231Z`. The public UI is
no longer the temporary replacement shell.

That record described what was running at the time; it was not an acceptance of
that promotion through the governed path. The governed path has since run and
accepted its first release, so the following paragraphs are retained as the
history of how the target was reconciled rather than as its current state.

## First accepted governed promotion (2026-09-10)

`bootstrap` promotion of release run `34527597963` was accepted from source
`b1616332c024e262a0aac03018943abbf619c087` in bootstrap mode, active slot
`blue`. Production now serves `edfinder-v3-api:release-…` and the matching web
slot from the same commit, with `edfinder-v3-production-api-blue` and
`edfinder-v3-production-web-blue` owning `127.0.0.1:58080` and `58081` free —
one active origin, exactly as the cutover model requires.

The receipt store holds the durable receipt, the byte-exact release manifest and
the advanced `current.json` pointer, so there is now a canonical immutable
release and a checksum-bound rollback target. The rollback kind for the first
promotion is `none-first-promotion`; every later promotion becomes
`prior-accepted-immutable-release`.

The legacy `edfinder-v3-api` and `edfinder-v3-proxy` were stopped by that cutover
and then retired on 2026-09-10. Their `docker inspect` records were archived into
the root-owned receipt store first, because their environments are the only
record of how the ungoverned 2026-09-09 stack ran and are not reproducible from
any committed revision — and are not safe to commit, since they carry live
configuration. The superseded 2026-09-09 pre-release containers are still
retained. The read-only inventory now completes with no failures at all, and its
required-container set no longer names the legacy pair: it requires the retained
database, the edge, Redis and NATS, plus a running owner of the active origin, so
the check survives blue/green rotation instead of pinning two container names.

Two facts had to be reconciled before that promotion could run:

1. **Topology.** The cutover model below keeps one active origin bind
   (`127.0.0.1:58080`) with the inactive slot on `127.0.0.1:58081`, and the
   deployer refuses an active bind that also presents a staging binding. The
   reviewed authority and its edge configuration now agree with that model:
   `edge_route_authority` is published in
   `deploy/v3-production/target-authority.json`, and
   `deploy/v3-production/public-auth-edge.nginx.conf` forwards the public
   application surface to the active origin instead of the staging port.
   The host is now reconciled: the reviewed edge configuration was applied to the
   deployed edge, which forwards the application surface to
   `127.0.0.1:58080`, and the staged web slot on `127.0.0.1:58081` was stopped,
   leaving the retained `edfinder-v3-proxy` as the sole active origin. That is
   exactly the pristine bootstrap state the deployer models, so the governed
   bootstrap cutover in step 6 can bind the verified candidate web slot to
   `127.0.0.1:58080` without repointing the edge.
2. **Runtime.** Production mutation requires an exact CPython 3.14 on the host,
   and that reviewed provisioning change is now complete. `uv` 0.12.12 is
   installed at `/usr/local/bin/uv` from the checksum-verified upstream release
   tarball, and it installed CPython 3.14.7 into
   `/opt/python/cpython-3.14.7-linux-x86_64-gnu`. `/usr/local/bin/python3.14` is a
   symlink to that pinned build, so the launcher's `command -v python3.14` lookup
   resolves on the safe path instead of depending on a user-specific
   `~/.local/bin`. The launcher's own exactness test passes, and inventory run
   `34517318462` records `python3_14` as `exists=true`, `version=3.14.7`,
   `is_exact_cpython_3_14=true`, which is the reviewed evidence that clears
   `production_promotion_cpython314_runtime_unproved`. The host's default
   `python3` is still 3.13.5 and still runs the read-only inventory. To reverse
   the change, remove the symlink, `/opt/python` and `/usr/local/bin/uv`.

The runtime identity drift is recorded in
`deploy/v3-production/target-authority.json`: the running api container keeps
the legacy name `edfinder-v3-api` rather than the Compose slot name
`edfinder-v3-production-api-blue`.

All three designated paths now exist at exactly the reviewed owner/mode: the api
env snapshot at `/etc/ed-finder/v3-production/api.env` (uid `0`, mode `0600`), the
reviewed schema identity at `/etc/ed-finder/v3-production/schema-identity.json`
(uid `0`, mode `0600`), and the durable receipt store at
`/var/lib/ed-finder/v3-production/receipts` (uid `0`, mode `0700`). The target
authority pins all three, and inventory run `34517318462` records stat-only
existence/owner/mode evidence for each without reading contents. Authoring the
api env snapshot was a secret-handling step: it supplies the real production API
configuration, and no automation here reads container environments to synthesise
it.

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
credentials. The context must resolve exactly to the local rootful
`unix:///var/run/docker.sock` endpoint, and every Docker inventory command is
explicitly pinned to it. An unexpected endpoint stops before any container,
network, port, or ledger evidence is queried. Review that fact as evidence for
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

Workflow-driven preflight remains application- and data-read-only, but it is
not host-filesystem-write-free: the workflow creates a private temporary
operation directory, extracts the sealed bundle into it, and removes it on
exit. Preflight receipts therefore report `filesystem_writes_performed=true`
with scope `ephemeral-operation-bundle-only`, while database writes,
application-data writes, migrations, image pulls, service changes, edge
recreation, and protected-resource changes remain `false`. A transport failure
that cannot prove whether remote extraction began reports that filesystem fact
as unknown/may-have-occurred rather than falsely reporting `false`.

Schema changes use the separate manual-only
`.github/workflows/v3-production-schema-migration.yml` authority documented in
`v3-production-schema-migration.md`. Application promotion still never runs SQL
migrations. Its preflight reads the complete `v3_meta.schema_migration` ledger
and requires the installed identity plus candidate release to match it exactly.

The accepted 2026-09-10 release originally recorded the three-row V3 identity.
The database later advanced additively through migration 006 while the same
immutable release remained healthy, leaving its historical receipt correctly
unchanged but insufficient as proof for a later rollback. The target authority
therefore carries a supplemental compatibility attestation bound to that exact
release run, manifest checksum, source SHA and image digests. It lists the
reviewed identities through 006, 008 and 009. The deployer always verifies the
immutable manifest against its originally recorded schema first; it consults
the supplemental attestation only for a later schema identity, and refuses any
binding mismatch. This preserves the original receipt and manifest rather than
rewriting production history.

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
   atomically advance `current.json`. If any later persistence step fails,
   atomically restore the prior pointer (or its prior absence) before candidate
   artifacts are removed. Remove the secret snapshot and registry credentials
   on every exit.

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

## Owner sequence

1. Merge the exact reviewed schema-transition authority into `main`.
2. Dispatch the protected migration `plan` with literal confirmation
   `ed-finder-prod/nb79a3d.mevnode.com` and review the receipt. It must report
   the live prefix through 006 with only 008 and 009 pending.
3. Separately approve and dispatch `apply`, supplying the successful reviewed
   plan run ID. The workflow authenticates that run and its exact-head receipt
   before reaching the host. Require the apply receipt to report both migrations
   applied, no service changes, and the installed target identity matching the
   final live ledger.
4. Build exact current `main` through `V3 application immutable release` with
   `schema_compatibility=backward-compatible`, reviewed compatible migration set
   `sha256:78e8da38e961a62f13c9ca87059d6cf23e66e2091d22afef07d4a12c7f48d02e`,
   non-secret review evidence, and `rollback_eligible=true`.
5. Dispatch application `preflight` in `upgrade` mode with that exact release
   run ID and the same literal target confirmation. Review the passed receipt.
6. Separately approve and dispatch `promote` with the identical run ID and
   `upgrade` mode, then verify public health and the served build SHA.

If any fact differs, stop. Do not recreate the edge or adapt a legacy/root
Compose command from this runbook.
