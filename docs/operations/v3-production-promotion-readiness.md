# V3 PostgreSQL 18 Production Promotion

This runbook promotes the existing V3 rehearsal/test database. Do not restore
V2 into V3 and do not replace the candidate with a fresh rebuild. Repository
work prepares tooling; production commands and private receipts run only from
the current production operator host/shell. The readiness audit is read-only and is evidence, not
deployment authorization.

## Read-only audit

Use a read-only PostgreSQL role and keep the receipt in the private operator
artifact directory (never commit it). The command requires an explicit DSN,
forces a read-only transaction, applies finite timeouts, and redacts credentials.

```bash
python scripts/checks/production_candidate_readiness.py \
  --database-url "$DATABASE_URL" \
  --receipt-file /var/lib/ed-finder/operator-artifacts/v3-promotion/readiness-safe.json
```

The default safe profile uses catalog estimates for large base tables, retains
only index-supported exact backlog checks, and skips costly coverage joins. It
is deliberately **not** sufficient to return `ready`: it inventories the target
and identifies blockers within a bounded operator check. Schedule the explicit
`--full` profile separately when exact scans of the roughly 188M-system database
are acceptable. Full can deliberately require a larger finite timeout, for example:

```bash
python scripts/checks/production_candidate_readiness.py \
  --database-url "$DATABASE_URL" \
  --receipt-file /var/lib/ed-finder/operator-artifacts/v3-promotion/readiness-full.json \
  --full \
  --statement-timeout 2h
```

A skipped, timed-out, missing, or errored required check is never equivalent to
zero or ready.

## Mandatory target confirmation

The JSON receipt and human output identify the database using values reported by
PostgreSQL itself: `current_database()`, `current_user`, `inet_server_addr()`,
and `inet_server_port()`. A null server address is shown as a local-socket
connection rather than guessed from the DSN. Because the replacement host may
contain multiple PostgreSQL 18 instances, the operator must positively compare
these receipt fields with the approved candidate identity **before any write
phase starts**. A PG18 version result alone is not target confirmation. Stop if
any identity field is unexpected or ambiguous.

## Promotion gates and order

1. **Snapshot/backup:** create a fresh custom-format archive, checksum and
   metadata; require `pg_restore --list` success and a recorded disposable
   restore rehearsal exposing public tables and `schema_migrations`.
2. **Schema/migrations:** the audit gates on PostgreSQL major version 18; manifest and ledger
   checksums match exactly; pending automatic migrations, pending manual
   migrations, and checksum mismatches are all zero. Apply migrations only in a
   separately authorized write phase. `999_refresh_materialized_views.sql` is
   operational SQL, not a migration.
3. **Base/canonical data:** systems, bodies, stations and body_rings are present
   with plausible counts reconciled to import/source receipts. Body flag/count,
   duplicate identity, trusted-ring and association-status invariant drift is zero.
4. **Grid:** `grid_cell_id IS NULL = 0`, `macro_grid_id IS NULL = 0`, grid tables
   are nonempty, and referenced-cell orphan counts are zero.
5. **Ratings v3.4:** every `has_body_data=TRUE` system has one v3.4 rating;
   eligible unrated, wrong-version, eligible dirty, stale-clean and stale
   noneligible backlogs are zero under the strict/full invariant profile.
6. **Topology/economy synergy:** missing topology for rated systems is zero;
   report synergy rows and distinct-system coverage, with no missing builder-
   expected output. Do not require pairs where the builder legitimately emits none.
7. **Archetypes:** missing score rows versus ratings, missing traits versus scores,
   and `system_archetype_scores.dirty=TRUE` are zero.
8. **Regional analysis:** every intended coordinate-bearing candidate has a row;
   the missing-row backlog is zero and intentionally unpositioned systems remain explicit.
9. **Station-body links/backfills:** stations lacking a link row are zero after the
   full backfill; unresolved/inferred statuses remain valid and are reported.
   All confirmed-link drift buckets from `data_invariants.py` are zero.
10. **Full clusters:** a full build receipt exists, `cluster_summary` is nonempty,
    `app_meta.clusters_built=true`, and eligible `cluster_dirty` plus summary dirty
    backlogs are zero. Do not require one cluster per system.
11. **Materialized views/stats/cache:** every schema-supported map and archetype MV
    is present, populated/readable, and has its specifically named required UNIQUE
    index (catalog metadata must prove uniqueness, validity, and readiness); refresh/stats
    freshness is recorded and cache clear/warm behavior is explicitly decided.
    The gate contracts are `mv_map_regions` → `ux_mv_map_regions_cell`, the
    200/500/1000 LY heatmaps → `ux_mv_map_heatmap_200`,
    `ux_mv_map_heatmap_500`, and `ux_mv_map_heatmap_1000`,
    `mv_map_timeline_month` → `ux_mv_map_timeline`, and
    `mv_archetype_rankings` → `idx_archetype_rankings_pk`. If the candidate has
    only differently named migration-era indexes, readiness remains blocked;
    this audit does not create or rename them.
12. **Strict invariants/readiness receipt:** retain both safe and scheduled full
    JSON receipts plus checksums. All required backlogs/drift are exactly zero;
    no required metric is missing or skipped. Run the existing strict receipted
    invariants as the canonical body/ring/station/evidence contract check.
13. **Application deployment/cutover:** only after owner review. Deploy separately,
    verify deployed HEAD, health and representative Finder/archetype/map queries,
    and retain the snapshot reference for rollback.

Journal, evidence, observed/simulation, exploration, powerplay, routes and
Frontier account/auth tables are runtime/feature-populated inventory. Report
their presence, counts and useful status/freshness, but zero or partial history
is not a full-build promotion blocker. Schema unreadability or an applicable
integrity-contract failure still blocks.
