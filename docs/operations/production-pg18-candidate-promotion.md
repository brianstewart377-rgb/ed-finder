# Existing PostgreSQL 18 Production-Candidate Promotion

## Purpose and boundary

This runbook is for assessing and, in a later separately approved operation,
promoting the **existing PostgreSQL 18 rehearsal/test database** to production.
It is not a database rebuild. Do not create an empty database, restore V2 into
V3, reset the candidate, run migrations, start a rebuild, change DNS, or cut
over application traffic while following the audit portion of this runbook.

The readiness audit is evidence, not cutover approval. Keep its JSON receipt
with the snapshot identity and the candidate database identity that it
describes. Never paste or store a `DATABASE_URL`, password, or other credential
in the receipt.

## One-time full-build order

The production bootstrap has this dependency order. Do not skip ahead because
a downstream command happens to run successfully:

1. **Snapshot/backup.** Freeze an identifiable recovery point for the PG18
   candidate and prove the backup can be listed and restored using
   [postgres-backup-and-restore.md](./postgres-backup-and-restore.md). Record
   backup identifier, start/end UTC, database identity, and verification result.
2. **Schema and migration audit.** Run the production-candidate readiness audit
   read-only. The PostgreSQL server must report major version 18. Every entry in
   `sql/migration-manifest.txt` must agree with the migration ledger: no pending
   automatic or manual migration and no checksum mismatch. An unexpected or
   unreadable ledger is a stop condition, not permission to apply migrations.
3. **Base-data validation/import gaps.** Validate `systems`, `bodies`,
   `stations`, and `body_rings` when present. Reconcile counts and source
   coverage against the accepted rehearsal baseline. Investigate missing joins,
   rejected-row spikes, and implausible count decreases before scheduling any
   bounded gap import.
4. **Grid.** Fully populate both `grid_cell_id` and `macro_grid_id` wherever the
   canonical contract requires them. Completion means zero eligible null or
   invalid assignments, not merely that a nightly batch made progress.
5. **Ratings v3.4.** Fully build ratings with current `rating_version = 3.4`.
   Completion means every eligible canonical system has its required rating,
   no stale/non-3.4 eligible row remains, and `rating_dirty` has no unresolved
   eligible work.
6. **Topology and economy-pair synergy.** Complete the topology dataset first,
   then economy-pair synergy. Require full eligible coverage and zero required
   backlog/dirty rows for each before continuing.
7. **Archetypes.** Complete archetype scores and traits. Every eligible system
   must have the required current score/trait representation, and archetype
   dirty work must be zero.
8. **Regional analysis.** Fully populate the required regional-analysis
   products for every eligible system/region, with no required backlog.
9. **Station/body links and canonical backfills.** Complete station-to-body
   links and every other canonical backfill identified by the audit. Each
   backfill needs an explicit eligible denominator and must reach that
   denominator; unexplained orphans are blockers.
10. **Full clusters.** Build `cluster_summary` only after its dependencies are
    complete. Require complete eligible cluster coverage and an empty
    `cluster_dirty` backlog.
11. **Materialized views and maintenance refresh.** Refresh every required
    serving materialized view after the underlying full builds, then perform
    the documented database maintenance. Record view presence, row counts,
    refresh completion/time, and maintenance result.
12. **Strict invariant audit.** Run the strict data-invariant suite against the
    candidate. Every required invariant must pass; skipped, unavailable, or
    partially checked invariants are promotion blockers.
13. **Application smoke/release gate.** With writes and public traffic still
    controlled, verify API startup, representative search/detail/map/planning
    reads, database compatibility, and rollback readiness. Cutover needs a
    separate owner-approved release procedure and receipt.

Nightly jobs use deliberately bounded backfills so routine maintenance cannot
monopolise the database. A bounded nightly run, a decreasing backlog, or one
successful batch is **not** completion evidence for this one-time production
bootstrap. Use explicit full-build commands only in a later reviewed operator
plan, and measure every dataset against its eligible denominator.

## Readiness receipt and interpretation

The preferred replacement-host control plane is the existing **ChatGPT ed-new
Ops** workflow's narrowly allowlisted `production-candidate-readiness`
operation. It requires the `ED_NEW_CANDIDATE_DATABASE_URL` environment secret,
transmits it over SSH standard input rather than a command argument, runs
`scripts/operator/audit_production_candidate.py --json-output <private-temp>`
from `/opt/ed-finder`,
checks that the output is valid JSON and does not contain the URL, and retains
the receipt as a 30-day Actions artifact. Exit status `1` means audited but not
ready; `2` means the audit failed closed. Both block the workflow. This
operation performs reads only and does not run a migration or backfill.

For a reviewed direct operator-shell run, export `DATABASE_URL` from the
operator's protected secret source without printing it, then run:

```sh
python3 scripts/operator/audit_production_candidate.py \
  --json-output /path/to/private/production-candidate-readiness.json
```

Unset `DATABASE_URL` after the command. Do not put it on the command line, in
shell history, or in an artifact. The audit must be read-only and fail closed.
Preserve its human-readable summary or JSON receipt with the snapshot evidence;
publish the JSON only after confirming it is credential-free.

Classify audit results in two groups:

- **Must be fully built:** grid and macro-grid assignment, ratings v3.4 and
  rating dirty state, topology, economy-pair synergy, archetype scores/traits
  and dirty state, regional analysis, station/body links, cluster summary and
  cluster dirty state, plus required serving materialized views. Missing
  objects, incomplete eligible coverage, stale versions, or non-zero required
  backlogs block promotion.
- **Runtime/feature populated:** later journal, evidence, exploration,
  powerplay, route, frontier-account, and similar feature tables. The audit
  records whether each exists and its row count; zero or partial population is
  not by itself a bootstrap failure unless a separate product release gate has
  declared that feature required.

Optional missing tables/views must be explicit in the receipt rather than
causing the audit to crash. Conversely, “optional” means optional to inspect,
not permission to ignore a missing object listed above as must be fully built.

## Measurable promotion gate

The candidate can enter a separate cutover review only when all of these are
recorded together:

- a verified, restorable pre-promotion snapshot/backup;
- PostgreSQL major version 18 and the expected database identity/size;
- zero pending manifest entries (automatic and manual), zero ledger checksum
  mismatches, and no unexpected migration-ledger state;
- accepted base-table counts and source/join coverage with every discrepancy
  resolved or explicitly accepted;
- 100% eligible coverage for every must-be-fully-built dataset, current ratings
  version 3.4, and zero required dirty/backlog rows;
- every required materialized view present and refreshed after the last full
  dependency build;
- a fully passing strict invariant audit with no required check skipped;
- passing read-only application smoke tests and a documented rollback target.

Any unknown denominator, missing receipt, checksum mismatch, partial full
build, stale materialized view, failed/skipped invariant, or incomplete
external-database deployment configuration is a promotion blocker. Stop and
plan the exact population or remediation operation; do not turn the audit into
an implicit migration or repair lane.
