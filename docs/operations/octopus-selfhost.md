# Fresh Octopus 1.0.122 self-host preparation

Status: preparation and validation only. This runbook does not authorise a
server write, container start, migration, public route, TLS/DNS/firewall change,
GitHub App change, webhook delivery, provider credential entry, or legacy
destruction. It leaves every ED-Finder/V3 service, port, database, migration
ledger, current nginx route, and `/opt/octopus/ui.htpasswd` mount untouched.

## Fixed architecture and data decision

This is a fresh installation of official release `v1.0.122` (tag commit
`55583ac832472ad8b535f1f678f9c11837f7cfdb`) using application image
`ghcr.io/octopusreview/octopus-selfhost:1.0.122`; `latest` is forbidden. It has
its own Compose project (`octopus-selfhost`), PostgreSQL 17, Qdrant 1.17.0,
internal backend network, web-only outbound network, and version-named volumes. No legacy Octopus PostgreSQL,
Qdrant, sessions, index, cache, settings, or repository state is migrated. That
loss is intentional; existing GitHub review comments remain on GitHub.

Only the web service is host-published, at `127.0.0.1:43300`. PostgreSQL and
Qdrant have no host ports. A later edge slice may attach the web container to a
shared proxy network, but this package does not declare or activate that
attachment. It does not change the current ports 80/443 or the legacy route.

Preparation generates independent URL-safe hexadecimal values for the database
password, `BETTER_AUTH_SECRET`, 32-byte `OCTOPUS_DATA_KEY`, and temporary admin
password. They exist only in root-owned mode-0600 `/opt/octopus/octopus.env`.
The operator supplies `OCTOPUS_ADMIN_EMAIL`. Repository tools never print the
temporary password. Octopus marks the seeded administrator for a mandatory first password change.
Never source this file as shell code; Compose parses it.
Do not put it in logs, argv, Actions, receipts, backups, or the repository.

Provider and GitHub App credentials are absent until private health succeeds.
Initial intended settings are Claude review model `claude-sonnet-4-6` and
OpenAI embedding model `text-embedding-3-large` (3072 dimensions). Configure
provider keys interactively or through root-only host secrets later. Self-hosting
removes Octopus SaaS/community quotas, but does **not** remove Anthropic/OpenAI
billing, spend controls, or provider rate limits. Ollama is explicitly deferred;
changing embedding models requires reconstruction because vectors are not
compatible.

## Preparation commands (only when separately authorised)

First run read-only preflight. It reports expected hostname, kernel/architecture,
CPU/RAM/disk, Docker/Compose versions, listeners on 43300/43332/43333/43334 and
80/443, networks, `/opt/octopus` presence, and only public-edge container names,
network names, and bind-mount sources. It never inspects container environment
or database content.

```sh
bash scripts/operator/octopus_selfhost.sh preflight
sudo bash scripts/operator/octopus_selfhost.sh prepare \
  --target-root / \
  --admin-email 'operator@example.invalid' \
  --confirm 'PREPARE FRESH OCTOPUS ON ED-FINDER-PROD'
sudo bash scripts/operator/octopus_selfhost.sh validate \
  --deployment-dir /opt/octopus
```

Replace the synthetic address. Preparation refuses any existing destination,
including unmanaged content, and makes no attempt to merge or overwrite it.
Before container work, archive the directory for rollback or remove it only
after manually confirming it is the newly generated, unused managed package.
The script itself performs no cleanup of an installed destination.

## Later private installation sequence

Each numbered phase needs separate operator authorisation. Keep port 43300
loopback-only throughout.

Every Compose invocation must use this exact prefix so interpolation reads the
root-only host file (never `source` it):

```sh
cd /opt/octopus
docker compose --project-name octopus-selfhost --env-file octopus.env -f compose.yaml ...
```

1. Record preflight and `docker compose config` output without environment
   values. Pull the three pinned images with the prefix above plus `pull`. Do
   not use `latest`.
2. Start only `postgres` and `qdrant`, wait for both health checks, and confirm
   there are no host listeners on 43332/43333/43334. The suffix is
   `up -d postgres qdrant`; do not start `web` yet.
3. Obtain the official Octopus repository at exact tag `v1.0.122`, verify HEAD
   is `55583ac832472ad8b535f1f678f9c11837f7cfdb`, and retain its `bun.lock`.
   Run `bun install --frozen-lockfile` and `bunx prisma migrate deploy` from
   `packages/db` inside `oven/bun:1.3.4`, attached only to
   `octopus-selfhost-backend`. Supply the internal database URL through a
   temporary mode-0600 Docker `--env-file`, not argv; delete that temporary
   file afterward. The exact tag supplies schema/migrations and lockfile, the
   container pins Bun, and the lockfile pins Prisma. The runtime image cannot
   migrate because it intentionally contains neither Prisma nor migrations.
   Do not install or invoke an unpinned host Bun/Prisma toolchain.
4. Start `web` with the same prefix plus `up -d web`. From the host, require
   `GET http://127.0.0.1:43300/api/health`
   to return HTTP 200 with `status: ok`, and `/api/version` to report exactly
   `1.0.122`. The health endpoint proves PostgreSQL but not Qdrant, so also keep
   Qdrant's Compose health green. No edge/App work may begin without this proof.
5. Restart all three services and repeat health/version checks. Create a marker
   record through the private UI only if authorised, restart again, and prove
   PostgreSQL persistence. Index a disposable test repository, restart, and
   prove or deliberately rebuild its Qdrant index.
6. Sign in privately as the supplied admin, immediately change the temporary
   password, set Claude `claude-sonnet-4-6`, add the Anthropic key, set OpenAI
   `text-embedding-3-large`, add the OpenAI key, and verify spend/rate controls.
   These are user-interactive steps and are not automated here.

Do not use a curl-pipe-shell installer. Do not apply ED-Finder migrations or
connect this stack to an ED-Finder/V3 database or migration ledger.

## Backup and restore

PostgreSQL is authoritative and must be backed up before upgrades and on an
operator schedule. Run `pg_dump --format=custom --no-owner --no-acl` from the
pinned PostgreSQL 17 container, stream stdout directly into a newly created
mode-0600 host backup file, then checksum it. Do not put the password in argv;
`docker compose exec -T postgres pg_dump -U octopus -d octopus` uses the
container's existing environment. Test restore only into a new isolated
PostgreSQL 17 volume/project: create the empty database, stream the custom dump
to `pg_restore --clean --if-exists --no-owner --no-acl`, then run matching-tag
migrations and private health/version checks. Never restore over the live
volume, and never reuse an ED-Finder volume.

Qdrant is intentionally not backed up initially. It is derived and rebuildable
by re-indexing repositories after a PostgreSQL restore. Record the affected
repositories, clear only the fresh Octopus Qdrant volume under separate
authorisation, re-index, and verify collection health. Revisit snapshots only
if rebuild time becomes operationally unacceptable.

## GitHub App and cutover (future slice only)

Recommend a **new GitHub App**. It gives the fresh instance distinct credentials,
webhook secret, endpoint, and an auditable rollback boundary. Reusing the old
App reduces installation work but risks ambiguous delivery, credential coupling,
and accidental routing to both instances. The official self-host App Manifest
flow requires a public HTTPS callback, so it cannot occur during private install.

In the later authorised edge slice, establish TLS/edge health first. Create the
new App interactively, validate its least-privilege permissions and installation,
then disable delivery on the old webhook immediately before enabling delivery
to the new path: there must never be two simultaneous active webhook paths.
Open or synchronize a test PR and require one successful review of the exact PR head SHA.
Verify both inline comments and the top-level review, the new App
identity, and absence of duplicate delivery before calling cutover successful.

Keep the old instance and its volumes intact during a documented rollback
window of at least seven days. Rollback disables the new webhook/App delivery
and re-enables the old single path. Only after the window and owner approval:
disable the legacy GitHub webhook/App, stop the old instance, observe another
explicitly recorded rollback interval, and handle destruction plus credential
revocation as a separate authorised change. This repository slice implements
none of those actions, nor DNS/public edge changes or blocked-PR recovery.

## Primary upstream references

- [release v1.0.122](https://github.com/octopusreview/octopus/releases/tag/v1.0.122)
- [official self-host compose](https://github.com/octopusreview/octopus/blob/v1.0.122/docker-compose.selfhost.yml)
- [official environment contract](https://github.com/octopusreview/octopus/blob/v1.0.122/.env.example)
- [official self-host documentation](https://github.com/octopusreview/octopus/blob/v1.0.122/apps/web/app/%28landing%29/docs/self-hosting/page.tsx)
