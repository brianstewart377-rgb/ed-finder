# ED-Finder R1 — Operator Real-System Snapshot
## Review 2C — Host PostgreSQL Inventory Amendment

Date: 2026-08-31  
Status: bounded metadata-only connection discovery amendment.

## Triggering evidence

The retained-PG18 target used by the existing `ed-new-db-discover-audit` workflow is a valid ED-Finder database for `systems + ratings`, but the R1 snapshot run proved it does not contain the canonical `bodies` table required for body-level evidence projection.

The R1 snapshot safety tests passed (18/18) before host access. No R1 system/body canonical SELECT was executed because discovery failed closed.

## Goal

Locate the full ED-Finder body database on the already-authorised operator host without reading gameplay rows.

## Discovery scope

Enumerate Docker containers on the operator host and consider only containers whose image or name indicates PostgreSQL (`postgres`). For each **running** PostgreSQL container:

1. inspect its container environment only to obtain its local PostgreSQL bootstrap user/password;
2. list connectable databases using `pg_database`;
3. for each database run only a metadata query using `to_regclass` to report whether these tables exist:
   - `public.systems`
   - `public.bodies`
   - `public.body_rings`
   - `public.ratings`
   - `public.stations`
4. record database size for diagnostics only;
5. never query rows from any of those gameplay tables during discovery.

Discovery output/logging may include only:

- container name;
- container image;
- running/stopped state;
- database name;
- database size;
- table-presence booleans;
- whether PostgreSQL has a published host port or Docker-network IP.

It must never print PostgreSQL passwords, full DSNs, container environment contents, or table data.

## Selection rule

A candidate for the R1 body snapshot must have at least:

- `systems=true`
- `bodies=true`

Preference order if more than one candidate appears:

1. fail closed and report the matrix;
2. do **not** automatically choose between multiple body databases until their identities are reviewed.

If exactly one candidate exists, its connection metadata may be retained in a runner-temporary secret file for the subsequent SSH tunnel step. Password/DSN stay masked and are never uploaded.

`body_rings` remains optional: missing source means ring facts remain Unknown.

## Container boundary

The inventory step may inspect multiple PostgreSQL containers, unlike Review 2A's fixed retained container. It does not execute arbitrary commands in non-PostgreSQL application containers and does not change container state.

No `docker start`, `docker stop`, `docker exec` writes, schema changes or application actions are permitted.

## Snapshot boundary unchanged

Only after an unambiguous systems+bodies database is found may the existing immutable R1 snapshot runner execute:

- max 20 exact named/id64 selectors;
- PostgreSQL session explicitly read-only;
- `SHOW transaction_read_only = on` required;
- static parameterized SELECT/SHOW only;
- no DB writes, migrations, ranking rebuild, Finder changes or Plan Fit.

## Failure behavior

- zero systems+bodies databases -> fail closed with safe table matrix;
- more than one -> fail closed with safe table matrix;
- authentication/discovery error -> fail closed;
- no running PostgreSQL container -> fail closed.

This amendment exists solely to find the correct body-data database so the already-reviewed snapshot can run.
