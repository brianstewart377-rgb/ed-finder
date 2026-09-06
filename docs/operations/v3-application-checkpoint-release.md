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

For an owner checkpoint:

1. Merge the exact accepted head to `main` and manually dispatch **V3
   application immutable release** with that 40-character SHA. For a reviewed
   `backward-compatible` release, supply any additional compatible migration-set
   identities as lowercase `sha256:` identities, one per line; other modes
   reject that input, and `exact` always records only the source migration
   identity.
2. Review the sealed manifest, compatibility evidence, application-only
   rollback eligibility and basename-only SHA-256 checksum. Both image
   references must be digest pinned.
3. Dispatch **V3 application live-checkpoint deploy** in `bootstrap` mode for
   checkpoint #1, or `upgrade` afterward. Upgrade selects only the release
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

## Request-triggered dispatch

ChatGPT may invoke the same two canonical `workflow_dispatch` entry points
without the GitHub UI by adding exactly one new JSON file in one commit under
`.github/v3-checkpoint-requests/` on the dedicated
`chatgpt-v3-checkpoint-requests` branch. The branch must first be seeded from
current `main`, must accept only fast-forward request commits, and must be
protected from force pushes and non-request changes. Request filenames use
only lowercase letters, digits, dots, underscores and hyphens.

An immutable release request is:

```json
{
  "operation": "v3-application-immutable-release",
  "inputs": {
    "source_sha": "0123456789abcdef0123456789abcdef01234567",
    "schema_compatibility": "exact",
    "compatibility_evidence": "review-record:checkpoint-42",
    "reviewed_compatible_migration_sets": "",
    "rollback_eligible": true
  }
}
```

A live-checkpoint deploy request is:

```json
{
  "operation": "v3-application-live-checkpoint-deploy",
  "inputs": {
    "deployment_mode": "bootstrap",
    "release_run_id": "1234567890"
  }
}
```

Every key shown is required and no other key is accepted. `release_run_id`
remains a quoted positive decimal string. For `exact`, leave reviewed migration
sets empty. For `backward-compatible`, list any additional reviewed lowercase
`sha256:<64 hex>` migration identities one per line. `unknown` and
`incompatible` requests must use empty evidence and reviewed-set strings and
must set `rollback_eligible` to `false`. Never put secrets, DSNs,
credential-bearing URLs or host details in a request.

The dispatcher always calls the allowlisted target workflow at `ref: main`
with the workflow `GITHUB_TOKEN`; it logs only sanitized request and returned
run correlation. A successful dispatcher run means GitHub accepted that one
canonical run, not that release or deployment succeeded. Inspect the correlated
target run and its artifacts. Rerunning a dispatcher creates another canonical
run. The target workflows retain all current-main, provenance, environment,
schema, receipt and target-authority gates. In particular, the currently
stopped target authority still prevents host mutation.
