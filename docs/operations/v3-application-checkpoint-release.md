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

The repository now defines both the deployment boundary and a separate,
request-triggered prerequisite operator. The recorded Contabo authority
remains deliberately stopped until that operator has run and its sanitized
candidate has been reviewed and merged. Read-only inspection on 2026-09-06
proved no container runtime/Compose installation and no authorized checkpoint
database, HTTP origin, network/edge route, secret mount or receipt store. See
`deploy/v3-live-checkpoint/target-authority.json` for the exact sanitized facts
and blockers. Dispatching the application workflow while that authority is
stopped cannot pull an image or change a service.

## Prerequisite provisioning boundary

`.github/workflows/v3-live-checkpoint-provision.yml` is the only repository
operator for this checkpoint's missing host prerequisites. It is environment
gated, request triggered, pinned to the existing checkpoint SSH trust, and has
an exact `check|provision` operation allowlist. It sends a fixed source-free
bundle from trusted `main`; it never pulls Git or builds application images on
the host. `check` performs no persistent mutation. `provision` is bounded and
idempotent and must preserve the exact three active Codex runner units before
and after every stage.

The provisioner owns only non-production checkpoint prerequisites:

- Docker Engine, the Compose plugin, the PostgreSQL 18 client, a local-rootful
  Docker context and private Docker config;
- the persistent external `edfinder-v3-checkpoint-app` bridge;
- strict-mode API configuration and durable receipt paths;
- a separate persistent PostgreSQL 18 checkpoint service and volume, outside
  the application Compose project;
- the exact repository migration manifest, including manual fresh-database
  migrations, and the repository-owned synthetic Finder/Inspect fixture;
- an exact-host non-production edge route from
  `vmi3542235.contaboserver.net` to the loopback checkpoint origin, without any
  production DNS or route change; and
- either a proved anonymous pull of an allowlisted GHCR digest or the explicit
  `V3_LIVE_CHECKPOINT_GHCR_USERNAME` plus
  `V3_LIVE_CHECKPOINT_GHCR_TOKEN` environment-secret contract. A half-present
  credential pair or unproved anonymous access stops authority generation.

The existing five `V3_LIVE_CHECKPOINT_SSH_*`/host secrets remain the transport
boundary. For anonymous GHCR proof, configure the non-secret environment
variable `V3_LIVE_CHECKPOINT_GHCR_PROOF_IMAGE` to an existing allowlisted
`ghcr.io/brianstewart377-rgb/ed-finder/v3-(backend|web)@sha256:...` reference.
The variable may be empty only when the paired GHCR environment secrets are
present; secret-backed setup stores the login only in the private target
Docker config and the canonical deployment still proves each release digest
pull. PostgreSQL is first pulled as the official `postgres:18` contract and
its observed repository digest and image ID are recorded in the sanitized
receipt; an existing owned data source is never silently repointed to a newer
tag result.

Database and API credentials are generated once on the target, remain only in
strictly owned target-local files, and are never logged or uploaded. The
provisioner does not access a production host, DSN, dump or data source. It
does not create Redis/Valkey or NATS. The included fixture is a deliberately
small synthetic journey sample, not a complete public galaxy reconstruction;
it is sufficient only for first Finder-result and Inspect-detail live testing.

Every run uploads a sanitized provisioning receipt. A successful provision
also uploads a fresh schema-identity receipt and
`target-authority.candidate.json`. The workflow never edits, commits or pushes
the committed authority. Review the observed versions, ownership/modes,
network, database identity, GHCR proof and edge evidence, then make a separate
authority-only change if they are correct. The schema receipt remains subject
to the deploy boundary's 24-hour freshness limit, so rerun `provision`
idempotently if review/merge/deploy outlives that window.

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
unreviewed background database-writing workload. It also explicitly sets
`ADMIN_OPERATION_STARTUP_REAP_ENABLED=false`. That checkpoint-only opt-out
suppresses the FastAPI lifespan's stale `admin_job_runs` housekeeping update;
it does not make the API generally read-only. Ordinary deployments retain the
default enabled startup reap and all normal runtime semantics.

## Bootstrap and upgrade modes

Bootstrap checkpoint #1 intentionally has no prior V3 release or deployment
receipt. It requires the candidate release plus authoritative current database
migration identity and proves both allowlisted app containers are absent before
the first pull. A failed bootstrap restores that absence by stopping/removing
only `api` and `web`; persistent network, edge, database, cache, runners and
volumes are untouched. Its rollback identity is `predeploy_absence`.

Every subsequent upgrade requires all of the following before mutation:

- a distinct prior digest-only release manifest and adjacent checksum durably
  stored in the host receipt directory when that release was accepted;
- a durable accepted deployment receipt matching the prior manifest's source
  SHA, release run ID, both image digests and manifest checksum;
- an authoritative current database migration identity listed as compatible by
  both the candidate and rollback manifests.

Upgrade never reconstructs or re-downloads the rollback manifest from a source
checkout, a different SHA, or an expiring GitHub Actions artifact. It loads the
checksum-bound accepted manifest through the durable `current.json` receipt
chain, re-verifies its release-manifest schema, digest provenance and rollback
eligibility, and fails closed if any durable file, checksum or receipt binding
is missing, unsafe, corrupt or inconsistent. GitHub Actions authenticates only
the new candidate artifact; successful acceptance makes that exact candidate
the next durable rollback source.

Before candidate mutation, an upgrade pulls and verifies the accepted prior
digest images as well as the candidate images. If candidate readiness or smoke
then fails, only `api` and `web` may be recreated at those already-verified
prior digests. The rollback Compose operation uses `--pull never` and performs
no registry pull, so recovery does not depend on registry availability.
Database rollback/recovery and migrations are outside this path.

## Deployment sequence and receipt

For an owner checkpoint after prerequisite authority is merged:

1. Merge the exact accepted head to `main` and request **V3 application
   checkpoint dispatcher** operation `release` with that 40-character SHA.
   The dispatcher invokes the canonical **V3 application immutable release**
   workflow and does not implement release logic itself. For a reviewed
   `backward-compatible` release, supply any additional compatible migration-set
   identities as lowercase `sha256:` identities, one per line; other modes
   reject that input, and `exact` always records only the source migration
   identity.
2. Review the sealed manifest, compatibility evidence, application-only
   rollback eligibility and basename-only SHA-256 checksum. Both image
   references must be digest pinned.
3. Request the dispatcher operation `deploy` with the exact successful release
   run ID and `bootstrap` mode for checkpoint #1, or `upgrade` afterward. The
   dispatcher invokes canonical **V3 application live-checkpoint deploy**;
   that environment-gated workflow remains the execution boundary. Upgrade
   selects only the release
   authenticated by the host's durable accepted-receipt/manifest chain; there
   is no operator-supplied rollback artifact or rollback run ID.
4. The target boundary validates all target/external facts, Compose checksum,
   allowlisted project resources and app absence/prior receipt before an image
   pull or service change. The selected Docker context must be inspectable and
   resolve exactly to the authorized local rootful daemon at
   `unix:///var/run/docker.sock`; SSH, TCP, alternate Unix sockets and malformed
   or unverifiable context results stop before any pull or Compose mutation. It
   obtains the non-secret database identity from the `DATABASE_URL` in the
   authorized external API env file without logging or persisting the URL, then
   uses a read-only database session to verify that identity and the complete
   applied `schema_migrations` set against the authoritative schema receipt.
   Under the deployment lock it freezes the securely opened env-file bytes into
   a private read-only snapshot, verifies the database through that snapshot,
   and revalidates the retained source identity before mutation. Candidate and
   rollback Compose operations use only that same snapshot; they never reread
   the external env file after schema verification. Repointed or edited env
   files, stale receipts, migration drift and unverifiable database identity
   stop before service mutation. Preflight also parses the Docker network
   topology and rejects a non-local bridge, unexpected attachments or aliases,
   and malformed or drifting network evidence before pulls and again before an
   application recreate.
5. It pulls and verifies the exact digest images and OCI build-SHA labels, then
   recreates only `api web` with `--no-deps`.
6. After each candidate or upgrade-rollback Compose apply, it polls bounded
   `/api/health` readiness for at most 120 seconds with a two-second interval.
   Only after readiness succeeds does it run the authoritative bounded,
   no-redirect smoke suite against `/`, `/api/health`, `/openapi.json` and
   `/api/auth/session`. Health must report `database=connected` and the expected
   `build_sha`; OpenAPI must expose the health and session paths; the session
   must be anonymous. A transient startup delay therefore cannot trigger an
   immediate false rollback, while readiness failure remains bounded.
7. Only after all smokes pass does it persist an immutable sanitized receipt
   and checksum together with the byte-exact accepted release manifest and its
   checksum, then atomically advance the `current.json` pointer that binds both
   durable files. The workflow uploads the same receipt output even for a
   stopped preflight.

An accepted receipt contains the authenticated release run ID, source SHA,
exact image digests, candidate manifest checksum, non-production target identity, current migration identity,
exact changed app resources, smoke outcomes and rollback identity. It never
contains DSNs, environment-file contents, passwords, tokens, private keys or
credential-bearing URLs.

Database access and service mutation are accounted independently. The
pre-mutation live schema verification and an upgrade's prior-release health
smoke are database reads even when a later pull, image verification or apply
fails; failure receipts record that access without claiming a database
mutation. The checkpoint path performs no migrations, and the startup reap
opt-out keeps candidate and rollback startup from updating `admin_job_runs`.

The external schema authority is the
`ed-finder/v3-live-checkpoint-schema-identity/v2` receipt named by target
authority. It contains the approved `database_source_authority`, a non-secret
`database_identity` (`database_name`, literal `server_address`, and
`server_port`), the canonical `migration_set_identity`, the complete
release-format `migration_set_entries`, and `captured_at`. The receipt must be
no more than 24 hours old (with at most five minutes of clock skew), and its
checksum remains pinned in target authority. The host must provide `psql` on
the fixed operator `PATH`; preflight verifies the client before any pull and
then uses it only for the bounded read-only identity/ledger query.

The workflow job ceiling is 75 minutes. Individual operator commands retain
their 120-second limit, and candidate/rollback readiness windows retain their
120-second limit; the larger job ceiling covers the full valid worst-case host
validation, candidate and prior-image pull/inspection, apply, readiness, smoke,
rollback and receipt/SSH overhead rather than pre-empting the deployer's own
bounded recovery path.

## Committed authority before checkpoint #1

The committed authority intentionally continues to record the original exact
blockers. Provisioning is now executable, but generated observations do not
become deployment authority merely because a workflow succeeded. Production
must not be used and production data must not be copied. Until the sanitized
candidate is reviewed and merged, the application deploy continues to stop
locally before artifact access or SSH.
