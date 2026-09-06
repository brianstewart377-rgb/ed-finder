# V3 Application Live-Checkpoint Release

## Boundary and current state

This is the owner-facing release and deployment boundary for the Svelte V3
application. **Contabo is not production.** Evidence from Contabo must not be presented as production
deployment or health evidence, and nothing here grants
production promotion, routing, credential, database-mutation or migration
authority.

The immutable release workflow builds the FastAPI and static SvelteKit images
off-host from one exact `main` SHA. Normal V3 backend unit, integration,
coverage, OpenAPI, Product E2E API, Review Lab backend, release image and the
every-PR container parity lane validate on exact CPython 3.14. The real FastAPI lifespan
is exercised against disposable PostgreSQL 18. Repository tooling,
retained frontend tooling, and the Codex worker bootstrap also validate on
exact CPython 3.14. The API continues to own asyncpg; synchronous tooling uses pinned Psycopg 3.

The environment-gated deployment workflow authenticates release artifacts
against a successful manual run of the canonical release workflow on `main`,
checks the adjacent manifest checksum, and accepts only the allowlisted GHCR
repositories at `repository@sha256:...`. It never runs `git pull`, a build,
package installation, migrations or dependency resolution on the target.

The repository now defines the deployment boundary, but the recorded Contabo
authority remains deliberately stopped. Read-only inspection on 2026-09-06
proved no container runtime/Compose installation and no authorized checkpoint
database, HTTP origin, network/edge route, secret mount or receipt store. See
`deploy/v3-live-checkpoint/target-authority.json` for the exact sanitized facts
and blockers. Dispatching the workflow while that authority is stopped cannot
pull an image or change a service.

## Persistent topology contract

The checkpoint is persistent infrastructure, not a rebuild-every-run stack.
The fixed Compose project is `edfinder-v3-checkpoint`; its mutation allowlist is
exactly the `api` and `web` services/containers plus their already-provisioned
application network. The Compose bundle contains no PostgreSQL, Redis/Valkey,
NATS, edge/proxy, runner service or named volume.

Deployment and rollback may use only explicit `api web` service arguments with
`--no-deps`. They must never use Compose `down`, `--remove-orphans`, volume
removal, project-wide recreation, or start/stop/recreate PostgreSQL,
Redis/Valkey, NATS, edge/proxy, runner or unrelated resources. The edge route,
database, secret/config paths, application network and receipt directory must
already exist under separate reviewed authority.

The two app services are capped at 2.00 CPUs and 2 GiB combined: API at 1.50
CPU/1536 MiB and web at 0.50 CPU/512 MiB. That ceiling is derived from the
observed 8 logical CPUs and 23 GiB RAM, leaving 75% of CPU and more than 90% of
nominal RAM outside the checkpoint for the OS and exactly three Codex runners.
It is a conservative isolation ceiling, not workload sizing proof. The deploy
preflight stops if the host falls below the audited total baseline or cannot
currently satisfy the two app services' combined 2 GiB memory ceiling.

Redis/cache is optional for core Finder and Inspect correctness. The API
already degrades to no cache when Redis is unavailable and uses in-memory rate
limits, so the checkpoint baseline intentionally has no cache service. NATS is not a V3 checkpoint baseline dependency.
Checkpoint configuration also disables
the live EDDN simulation ingest so a first UI/API checkpoint cannot begin an
unreviewed background database-writing workload.

## Bootstrap and upgrade modes

Bootstrap checkpoint #1 intentionally has no prior V3 release or deployment
receipt. It requires the candidate release plus authoritative current database
migration identity and proves both allowlisted app containers are absent before
the first pull. A failed bootstrap restores that absence by stopping/removing
only `api` and `web`; persistent network, edge, database, cache, runners and
volumes are untouched. Its rollback identity is `predeploy_absence`.

Every subsequent upgrade requires all of the following before mutation:

- a distinct prior digest-only release manifest;
- its checksum and successful canonical release-run provenance;
- a durable accepted deployment receipt matching its source SHA, both image
  digests and manifest checksum;
- an authoritative current database migration identity listed as compatible by
  both the candidate and rollback manifests.

If an upgrade smoke fails, only `api` and `web` may be recreated at the accepted
prior digests. Database rollback/recovery and migrations are outside this path.

## Deployment sequence and receipt

For an owner checkpoint:

1. Merge the exact accepted head to `main` and manually dispatch **V3
   application immutable release** with that 40-character SHA.
2. Review the sealed manifest, compatibility evidence, application-only
   rollback eligibility and basename-only SHA-256 checksum. Both image
   references must be digest pinned.
3. Dispatch **V3 application live-checkpoint deploy** in `bootstrap` mode for
   checkpoint #1, or `upgrade` with the accepted rollback run ID afterward.
4. The target boundary validates all target/external facts, schema identity,
   Compose checksum, allowlisted project resources and app absence/prior receipt
   before an image pull or service change.
5. It pulls and verifies the exact digest images and OCI build-SHA labels, then
   recreates only `api web` with `--no-deps`.
6. It makes bounded, no-redirect origin requests to `/`, `/api/health`,
   `/openapi.json` and `/api/auth/session`. Health must report
   `database=connected` and the candidate `build_sha`; OpenAPI must expose the
   health and session paths; the session must be anonymous.
7. Only after all smokes pass does it persist an immutable sanitized receipt
   and checksum, then atomically advance the checksum-bound `current.json`
   pointer. The workflow uploads the same output even for a stopped preflight.

An accepted receipt contains the authenticated release run ID, source SHA,
exact image digests, candidate manifest checksum, non-production target identity, current migration identity,
exact changed app resources, smoke outcomes and rollback identity. It never
contains DSNs, environment-file contents, passwords, tokens, private keys or
credential-bearing URLs.

## Exact blockers before checkpoint #1

No authorized checkpoint `DATABASE_URL` or data source exists in current
repository/host evidence. Production must not be used and production data must
not be copied. An operator must provide a separately approved persistent
non-production data source, external API secret/config file, and current schema
identity receipt.

The other current blockers are container-runtime/Compose installation
authority, the origin loopback port/listener, persistent app network and edge
route, target GHCR pull authentication, and a durable deployment receipt
directory. These are explicit external authority requirements; no port, path,
network, data source or edge wiring may be inferred from legacy Compose files,
production, or observed runner names.
