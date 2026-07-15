# Known Issues

## mv_archetype_rankings appears stale despite nightly refresh (2026-07-13)

Wiring survey reported the MV was last refreshed 2026-05-12.
However, scripts/nightly_update.sh already contains TWO conditional
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_archetype_rankings calls
(lines 244-248 after dirty rebuild, lines 281-285 after new-system
backfill). Before adding a third, diagnose why the existing two
haven't produced a fresher MV timestamp:
- Is the refresh silently erroring?
- Is either conditional block ever true in practice?
- Does the "last refreshed" timestamp we read reflect the refresh
  or the base data?

## Cluster rebuild: morning-after verification pending (2026-07-15)

The daily dirty-only cluster rebuild was re-enabled in d9c37e4 after
the discovery-query fix (cf993d1), index (039), column widening
(698f8f5), and orphan flag cleanup (cdff7f5). A supervised full
backlog clear completed successfully (7h 21m, 142,163 clusters,
exit 0).

Close when: tomorrow's nightly log shows step 4 completing without
errors, dirty count is small (delta-only, not millions), no smallint
overflow errors, and the orphan cleanup line reports a count.

Sunday full rebuild remains disabled (lines 324-327 of
nightly_update.sh) pending separate evaluation at scale.
