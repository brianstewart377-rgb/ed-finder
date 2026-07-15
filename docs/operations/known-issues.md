# Known Issues

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

## Resolved

### edfinder_api.state / state dual-import — closed 2026-07-15

Fixed in 4a66982. All flat "from state import" calls in tests
switched to package-qualified "from edfinder_api.state import".
Hardened with contract test
(`test_test_files_using_api_path_must_use_package_imports`).

### mv_archetype_rankings staleness — closed 2026-07-15

Root cause: MV refresh gated behind `if (( ARCH_SCORE_DIRTY > 0 ))`
and `if (( ARCH_SCORE_MISSING > 0 ))`. A failed refresh (Jul 14's
15s statement_timeout) had no retry path — the next night saw zero
dirty rows and skipped the block. Fixed in 54fc1e6 with a catch-up
refresh that fires whenever any archetype build ran, regardless of
post-build dirty count. One-off manual refresh completed (~6m30s,
10M rows, within 10min budget).
