# Fresh Octopus 1.0.122 deployment

## Scope and isolation

This bundle creates a fresh, repository-owned Octopus installation on the new
ED-Finder host. It is not a migration. Do not read, copy, export, mount, or
otherwise depend on the old `/opt/octopus` PostgreSQL or Qdrant data. Historical
GitHub comments remain on GitHub; old Octopus accounts, indexes, settings, and
usage history are intentionally discarded.

The target is `/opt/octopus`, Compose project
`edfinder_octopus_fresh_10122`, network
`edfinder-octopus-fresh-10122-network`, and two equally specific volumes. The
only published port is `127.0.0.1:43300`; PostgreSQL and Qdrant have no host
ports. This stack does not join the V3, ED-Finder, `review-edge`, or default
networks. Approximately 971 GB free was reported by the owner, but the operator
must recheck capacity without inspecting any database before preparing.

This slice does not wire an operator dispatcher or public edge. Existing nginx
Octopus co-tenant assumptions do not apply to this isolated bundle. DNS, TLS,
reverse proxy for `octopus.ed-finder.app`, GitHub App changes, and retirement of
the old host are separate, reviewed integration steps.

## Secrets and first boot

Copy `deploy/octopus/` to a trusted checkout on the new host and run commands as
an operator allowed to create only this named project. `prepare` installs the
bundle and a pinned upstream checkout. It creates `/opt/octopus/.env` from the
placeholder template with mode `0600`; replace every marker before migration.
Keep the directory `0700`, never print `.env`, and restrict backup/receipt
access. Never use the upstream example password `octopus`.

Provision strong, externally generated values for the database password and
URL, `BETTER_AUTH_SECRET`, `OCTOPUS_DATA_KEY`, all GitHub App credentials,
webhook/state secrets, and initial admin email/password. Values must never be
committed. Use fresh auth and data-encryption secrets because no encrypted old
database is restored. Restoring old encrypted records later would require the
old `OCTOPUS_DATA_KEY`; that is explicitly outside this fresh-install decision.
Percent-encode the database password in `OCTOPUS_DATABASE_URL` and make it
correspond exactly to `OCTOPUS_POSTGRES_PASSWORD`.

## Deterministic sequence

Run from the repository bundle directory:

```bash
sudo ./octopusctl.sh preflight
sudo ./octopusctl.sh prepare
sudoedit /opt/octopus/.env
sudo chmod 0600 /opt/octopus/.env
sudo /opt/octopus/octopusctl.sh migrate
sudo /opt/octopus/octopusctl.sh start
sudo /opt/octopus/octopusctl.sh health
```

Every mutation is bounded to the exact names above. Preflight refuses an
existing target, matching container, volume, network, or listening port. Later
steps verify Compose ownership labels and the pinned clean source checkout.
There is no prune, wildcard deletion, volume deletion, or `down -v` path.

The migration step starts only the new PostgreSQL and Qdrant, waits for
`pg_isready` and Qdrant `/readyz`, and runs `prisma migrate deploy` from the
exact upstream v1.0.122 checkout (`55583ac...`) in the digest-pinned Bun 1.3.4
container. The runtime image is never assumed to contain migrations. The
checkout, frozen lockfile, migration output, and source commit form the receipt.

Acceptance requires all containers healthy, PostgreSQL ready, Qdrant ready,
`GET /api/health` returning healthy, and `GET /api/version` reporting version
`1.0.122` with `selfHosted: true`. Preserve the generated API, container-health,
exact image ID/digest, source, and migration receipts under
`/opt/octopus/receipts/`.

## Bootstrap and provider-credit correctness

`ENABLE_REVIEW_WORKERS=false` is the committed/default state. Log in with the
new initial admin, rotate that access if appropriate, then configure and verify
the GitHub App, repository selection, provider, model, and webhook while workers
remain off.

A process-level provider key alone is insufficient: Octopus applies its
internal credit gate unless the organization owns a key for the provider of the
selected model. In the Octopus UI, save an **organization-level Anthropic BYOK
key** for the default Claude review path. Also save an **organization-level
OpenAI BYOK key** for default `text-embedding-3-large` indexing, or deliberately
configure and validate an alternative local embedding provider before indexing.
Never put provider keys in this repository.

Before worker activation, prove the configuration-only checks with workers off:

- health, version, login, GitHub App installation, repository selection, and
  signature-verified webhook delivery are correct;
- the selected review model resolves to Anthropic and the organization UI shows
  its Anthropic key as configured and valid;
- indexing uses the organization's OpenAI key for `text-embedding-3-large`, or
  the approved local embedding alternative is active;
- routine GitHub webhook delivery remains disabled so no ordinary review can be
  queued during bootstrap.

The old Octopus worker and webhook delivery must be stopped or disabled before
the new worker is activated, otherwise both installations may review the same
event. After the checks and owner confirmation, the auditable activation is:

```bash
sudo OCTOPUS_OLD_WORKER_STOPPED=yes /opt/octopus/octopusctl.sh activate
```

Activation requires the prior health receipt and changes only
`ENABLE_REVIEW_WORKERS=false` to `true`, recreating only the new web container.
With routine delivery still disabled, send exactly one controlled exact-HEAD
test event. Confirm its usage/transaction UI classifies the provider call as
BYOK with no platform-credit debit, its comments attach to that exact commit,
and no duplicate review is emitted. Do not enable routine webhook delivery
until that checklist passes. Destroy the old server only after at least one
controlled exact-HEAD test review succeeds on the new instance and the separate
public-edge cutover is accepted.

## Rollback

```bash
sudo /opt/octopus/octopusctl.sh stop
```

This stops only project `edfinder_octopus_fresh_10122` and retains both fresh
volumes, its network, receipts, and source checkout. It does not remove or
restart any V3/ED-Finder resource. Diagnosis or deletion requires a separate
reviewed procedure; do not improvise cleanup commands.

The later integration PR needs owner-provisioned provider, GitHub App, and admin
secrets. If Octopus cannot review the PR intended to restore Octopus itself, the
owner must explicitly authorize the Octopus-unavailable reviewer waiver; it is
not implied by this bundle.
