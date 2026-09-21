# Galaxy Impact implementation and validation

Date: 2026-09-21. Branch: `feat/galaxy-contributions-scoreboard`.

## Investigation and result

The former panel displayed sharing-review receipts, including raw system/body
identifiers. Those receipts carry physical measurements, not personal body-type
totals. The private journal store retains Scan classifications under an explicit
verified commander, so the new own-account endpoint aggregates those records
directly. Existing account-wide projections also include non-Scan and unassigned
events, making them unsuitable for this scoreboard.

`GET /api/v1/journal/galaxy-impact` returns seven counts from currently verified
owned commanders' READY imports. It deduplicates exact system/body identities,
retains known classifications through sparse scans and fails closed on ownership,
malformed identity, input overflow and execution timeout. No catalogue tables are
read. The response is private/no-store and never contains entity identifiers.

The accessible Svelte 5 scoreboard uses the generated facade and Svelte Query,
with distinct loaded/empty/loading/error states, account-scoped caching,
cancellation and refresh after committed imports, including interrupted imports.
Sharing remains optional; withdrawal controls are retained in a secondary
disclosure with readable labels. Both OpenAPI clients were regenerated locally
from FastAPI without starting its application lifespan or connecting to a DB.

## Review decisions

See the [design spec](../superpowers/specs/2026-09-21-galaxy-impact-scoreboard-design.md)
for the full contract and owner-review decisions. In particular:

- **Systems discovered** means distinct systems represented in imported scans;
  the visible explanation disclaims first-discovery credit.
- **Recorded** avoids implying that private imports have been published.
- Totals combine currently verified owned commanders linked to the account,
  deduplicating overlapping bodies. Bodies include stars; terraformable candidates
  can overlap notable planet categories.
- Nine journal gas giant classes count; water giants remain separate.
- Missing terraforming values preserve prior knowledge; explicit empty/null values
  clear candidate status. An authoritative star classification cannot retain
  terraformable planet credit.

## Validation

Environment: CPython 3.14.4, asyncpg 0.31.0, Psycopg 3.3.4, PostgreSQL 18.6,
Node 24.15.0 and pnpm 11.25.0. API dependencies came from the frozen
`apps/api/uv.lock`; web dependencies used the unchanged frozen pnpm lockfile.

All DB work used a newly created loopback-only PostgreSQL 18 container with tmpfs
storage and synthetic data. The new feature fixture creates and drops its own
randomly named database, guarded by the repository's disposable-target checks.
No production database, main-branch mutation or push was used.

| Check | Result |
| --- | --- |
| New API HTTP and real importer/PostgreSQL tests | 35 passed |
| Existing journal sharing/PostgreSQL regression suite | 11 passed |
| Focused scoreboard, journal panel and facade Vitest tests | 27 passed |
| `pnpm check` | 0 errors, 0 warnings |
| `pnpm test --pool=threads --maxWorkers=2` | 39 files, 325 tests passed |
| Broad repository CI unit selection | 2,938 passed, 233 failed, 79 skipped, 86 deselected |
| Ruff on changed Python files | Passed |
| `git diff --check` | Passed |

TDD evidence: the backend tests first failed for the absent route/module; six
scoreboard tests failed against the old panel and the facade test failed for the
absent method. A separate star/terraformability regression failed before its fix.
The real DB suite also proves timeout behavior using a held table lock and proves
input overflow returns no partial totals.

The default Vitest fork workers timed out before any tests started on this
Windows host. The complete suite passed using thread workers; project test
configuration was not changed. Existing SlowAPI deprecation warnings remain.
Cypress acceptance assertions were updated for the new labels/counts, but the
browser acceptance suite was not run in this task.

The broad repository selection is **not green** on this Windows checkout. Its
failures are outside the changed feature: Linux-only `fcntl` imports, unavailable
WSL `/bin/bash`, Windows symlink/executable-bit/path assumptions, CRLF checkout
asset/migration hash mismatches, and a metric-freshness assertion exceeded during
the long test collection. Normalizing the affected checked asset/migration bytes
to LF reproduces their recorded checksums; no source changes were needed. The
metric-freshness test passed when rerun alone. No journal, account UI or generated-facade boundary test
failed in that run. These unrelated operational-test failures were not changed
as part of the scoreboard. Full local output is retained in the ignored
`.venv/galaxy-impact-baseline-pytest.log`.

The broad command, started before implementation, was:

```powershell
.venv/Scripts/python.exe -B -m pytest --ignore=tests/integration --ignore=tests/test_deploy_main_invariants_gate.py -m "unit or not (integration or db or operator or e2e or slow)" -q -p no:cacheprovider
```

The disposable PostgreSQL container was removed after validation; the local
Python environment and ignored logs remain available for review.

To rerun the new backend tests, set `PYTHONPATH=apps/api/src;.` and
`CORS_ORIGINS=http://testserver`, point `GALAXY_IMPACT_TEST_DATABASE_URL` at an
explicitly disposable local PostgreSQL 18 server with database-creation rights,
and set `EDFINDER_GALAXY_IMPACT_TEST_DATABASE=yes`. Then run:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_journal_galaxy_impact.py tests/test_journal_galaxy_impact_postgres.py -q
```
