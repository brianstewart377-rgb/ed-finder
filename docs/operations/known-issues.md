# Known Issues

## edfinder_api.state / state dual-import (pre-existing)

Discovered 2026-07-12 during Phase B integration test run.
tests/integration/conftest.py imports state via flat path;
apps/api/src/main.py sets pool via edfinder_api.state package
path. Python treats these as two separate module objects so
pool is None in integration tests. Does not affect production
(single import path). Fix in a separate stage before relying
on integration tests for endpoint verification.

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
