# V3 Application Checkpoint Release

## Scope and present state

This is the owner-facing release foundation for the Svelte V3 application. It
does not authorize or perform a production deployment, service restart,
migration, database read/write, DNS change, or secret inspection.

The executable part today is the manual **V3 application immutable release**
workflow. It builds the current FastAPI application and static SvelteKit shell
off-host, publishes digest-addressed OCI images, and seals a machine-readable
manifest. The separate **V3 application deploy preflight** verifies a candidate
and prior rollback manifest through the existing `ed-new-operator` environment
and `ED_NEW_OPERATOR_*` SSH trust boundary. It then stops deliberately without
pulling an image or changing a service.

That stopped state is required. Current repository/runtime evidence does not
establish a reviewed V3 production Compose authority, application-service
allowlist, network/edge wiring, mounted secret/config authority, current
PostgreSQL migration identity receipt, receipt store, or an accepted immutable
rollback release. The stale `edfinder-v3-api:phase4c-r5` runtime has a mutable
tag and reports `build_sha=unknown`; it is not eligible rollback evidence.

## Checkpoint cadence

Use this sequence for every owner-test checkpoint:

1. Make the intended PR head exact and green under the full acceptance policy,
   including required review disposition.
2. Merge that exact reviewed head to `main`.
3. Manually dispatch **V3 application immutable release** with the full
   40-character SHA now at the head of `main`.
4. Review the uploaded manifest and its checksum. The workflow builds both
   images from that one SHA and records only `repository@sha256:...` references.
5. Select the candidate release run and a distinct, previously accepted,
   receipt-backed rollback release. Explicitly dispatch the environment-gated
   deploy path.
6. After a future reviewed topology slice makes deployment executable, require
   successful origin and public smoke for the Svelte root/application route,
   `/api/health` (including the exact `build_sha`), exact `/openapi.json`, and
   anonymous `/api/auth/session`. Confirm the Frontier route surface before
   attempting login.
7. Retain the deployment receipt, candidate and rollback manifests, route
   results, image digests, migration-set identity and compatibility decision.
8. Only then hand the checkpoint to the owner for live testing.

Normal PR, merge and `main` push events do not invoke either release or deploy.
Both workflows accept only an explicit manual dispatch. Building a release is
not permission to deploy it.

## Release manifest contract

`scripts/release/v3_release_manifest.py` computes the schema identity from the
ordered `sql/migration-manifest.txt` entries and the SHA-256 of every referenced
SQL file. A manifest records:

- the exact Git SHA and derived release ID;
- allowlisted backend and web image repositories with immutable SHA-256
  digests;
- the migration manifest checksum, per-file checksums and aggregate migration
  identity;
- an explicit compatibility status, compatible migration identities and a
  non-secret reviewed evidence identifier;
- explicit application-only rollback eligibility and rationale.

Unknown or incompatible schema status cannot be rollback eligible. Actual
application rollback additionally requires an authoritative receipt for the
current database migration identity and an exact match in the old release's
compatibility set. A manifest never carries DSNs, passwords, tokens, private
keys, secret values or credential-bearing URLs.

The release workflow uses Node 24/pnpm 11 with the committed frozen web lock and
CPython 3.14/uv with the committed API lock. Static SvelteKit output is copied
into nginx; no source checkout, build tool or dependency resolution is needed
on the target host. nginx delegates only `/api` and `/api/*`, exact
`/openapi.json`, and exact numeric `/s/{id64}` to the API. All other routes stay
with the Svelte static application fallback.

## Why deployment still fails closed

The host preflight emits a machine-readable stopped receipt listing the facts
still required. Review and land all of these as a separate topology authority
before adding any mutation command:

- V3 Compose project/config path and how the deployment bundle is installed
  without a production source checkout;
- exact app-owned service keys/container names and recreate allowlist;
- explicit preservation targets for PostgreSQL 18, Redis, NATS and retained
  edge services;
- host CPU platform, Docker networks/aliases, API upstream, loopback port and
  retained TLS-edge wiring;
- approved GHCR pull/authentication authority;
- non-secret configuration plus external secret-file/mount authority per
  service, including ownership/mode and required data/log/receipt mounts;
- approved read-only source for a current `schema_migrations` identity receipt;
- durable manifest/deploy-receipt/rollback-history storage and update rules;
- accepted prior digest release plus deploy receipt proved compatible with the
  current database;
- exact origin/public smoke authority and ordering.

Do not fill these gaps from the root legacy/local Compose file, old host source,
historical workflows, or observed container names. The current status helper
also expects a frontend inside the stale API image, so it remains diagnosis
evidence rather than the final smoke authority for the separate nginx web image.

## Rollback boundary

Rollback is always explicit and receipt-backed. It may recreate only the
eventually reviewed V3 application services and must preserve PostgreSQL 18.
If the prior manifest is missing, tag-only, reports unknown compatibility, or
does not list the current database migration identity as compatible,
application-only rollback stops.

This foundation does not implement database rollback/recovery or run
migrations. A schema-incompatible release requires a separately reviewed and
rehearsed database procedure; no one-click application rollback may imply that
such a procedure exists.
