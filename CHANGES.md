# ED-Finder — V3 Development Change Log

This log records the **current V3 development era**, beginning with the infrastructure cutover on 2 September 2026. Entries are newest first.

It is a repository change record, not production/operator authority. For current truth, read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) for production, database, backup, and recovery boundaries;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) for programme stage and authorised next work;
- [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) for the locked V3 application target;
- [`CLAUDE.md`](CLAUDE.md) and [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) for engineering and command boundaries.

Pre-cutover history remains available in Git history and dated/archive documents. It is not repeated here where it could be mistaken for current operational guidance.

## 2026-11-01 — Cross-platform shared-package lint command

`pnpm shared:lint` now uses a Node launcher and ESLint's API, removing the POSIX
binary-shim path that failed on Windows. The existing shared config and both
source directories are unchanged; the repository root remains the flat-config
base. The command reports its linted file count (89 on this revision), and CI
keeps its existing invocation. Regression tests compare the exact file set with
the former CLI command and verify a temporary planner lint error fails the
launcher, including when started from an unrelated directory.

## 2026-11-01 — Public Ratings V4 smoke receipt after governed releases

Adds a standard-library CPython 3.14 check of public health, published generation
and ratings/explanations for Sol, Achenar and Alioth. Bounded read-only GETs
validate response fields, seven economy scores, confidence and generation
identity, and write a JSON receipt with build identity and per-request timing.
Failures exit non-zero. Local stub tests cover success, generation mismatch,
invalid scores, HTTP failures and timeouts without contacting production.

The production release runbook now requires the owner to run this check after
each accepted governed promotion, compare the served build with the accepted
SHA, and commit the actual receipt in the release record PR. Failed attempts
need an explicit disposition and a fresh run after a remedy. This closes the
2026-10-31 audit's missing repeatable smoke procedure; it does not claim a new
public verification or change deployment acceptance gates.

## 2026-11-01 — Roadmap opening status summary

Added “Where things stand (2026-11-01)” directly below the roadmap title,
linking current release, schema, purge, backup, product and next-work evidence.
It records the unrun A5 restore practice and open owner decisions, and makes
missing detailed redesign, S5c and ingestion-enablement records explicit. It
also records the live system-name search outage and its pending fix (PR #978),
and the body-filter and refresh-safe-anchor work in review. The F4 design's
section 9 now records the owner's 2026-11-01 answer to question 2 (future custom
weights are URL-only) and points question 3 at the enablement decision, leaving
only question 4 open. All existing roadmap content is unchanged. No opening-line
contract test exists, so no test was added or changed. `pnpm shared:test` still
uses the POSIX binary path and remains a Windows follow-up.

## 2026-11-01 — V2 API retirement inventory; profile-sync owner decision required

Added the [mounted-route inventory](docs/development/v3-v2-route-retirement.md)
for the V2 retirement sweep and Colony Planner S7, tracing database relations
against the V3 migration lineage and callers in `apps/web`. Retirement is
stopped under the task's caller guard: the handwritten profile-sync service
calls `GET` and `PUT /api/profile/sync/{sync_key}`, whose `profile_sync` table
is absent from V3. Both operations are recorded as **needs owner decision**;
the service is exported but is not currently instantiated by a page. This
change documents the candidates and exclusions without changing API behavior
or generated clients.

## 2026-11-01 — V3 system name autocomplete prefix index

Autocomplete now reads the published V3 Search generation through an explicit
schema-qualified query, escapes LIKE metacharacters literally, and sorts at
most 100 candidates into 10 suggestions. The route no longer scans canonical
`systems` or falls back to unindexed trigram matching; its cache follows the
published generation and unavailable publication returns the existing 503
problem response. API pool initialization sets no `search_path`; the new query
does not depend on DSN or role defaults.

Governed migration `023` adds the generation-scoped `text_pattern_ops` name
index, retaining the existing default-opclass index. Ledger/identity and target
transition registration, bounded index-build timeouts and application order
are documented in the schema-migration runbook. PostgreSQL 18 regression tests
cover literal prefixes, generation isolation and index plans with sequential
scans enabled. Production application remains a separate governed operation;
this change applies no migration and deploys no service.

## 2026-11-01 — Seventh F2d release `293bc72b` accepted in production: Finder archetype UI on

Owner-approved. Release run 41342325477 (source `293bc72b`) passed preflight
run 41342504519 and was accepted by promotion run 41342589203 at
2026-11-01T19:37:23Z to slot green: staging, active and public smoke 200, F2d
image contract, OpenAPI bounds, 422 rejections and behavioural probes passed;
no migration, no database writes, protected resources unchanged. It is the
first governed web image with the Finder archetype UI switched on (#974) and
also carries S3b (#972), F4e (#973) and #975. Operator-code and ranking
identities are unchanged. `deploy/v3-production/target-authority.json` records
it as the accepted release; `181f6fed` is the recorded rollback artifact and
`f667bb4d` stays the minimum schema-compatible image. Receipts are under
`docs/operations/evidence/2026-11-01-v3-production-*`.

## 2026-11-01 — Finder F4 archetype UI enabled for governed release builds

Owner enablement decision (F4 design question 3). Every gate in the F4 design is
met: both Finder products published (2026-10-23), slice 1c's representative-scale
proof (2026-10-31), F4c (#969) and F4e (#973). The governed release workflow's web
image now passes `VITE_FINDER_F4_ENABLED=1`; the Dockerfile default stays `0`, so
CI, Review Lab and local builds are unchanged. A contract test pins that only the
release web image opts in. Nothing is deployed by this change; the Finder UI
reaches production with the next owner-approved governed application release.

## 2026-11-01 — Finder F4e: per-archetype explanations

Behind the default-off `VITE_FINDER_F4_ENABLED` flag, Explore result cards lazily
load all eight archetype explanations from the F2d endpoint. Requests and cached
results are bound to the card's generation, archetype version and manifest hash;
a mismatch leaves the scores visible with an explanation-unavailable message.
The accessible disclosure operates independently of result selection, and tier
badges stay on one line in narrow result cards. Product coverage expands a real
fixture explanation, compares stored scores and tiers, and checks accessibility.

Browser and visual acceptance, the owner's enablement decision (F4 design
question 3), and the governed release still remain before the flag may be enabled.

## 2026-11-01 — Explore waits for a requested search

Fresh Explore visits now show “Systems” and an invitation to choose a system,
without requesting results or adding result markers. Choosing an anchor loads
nearby systems; clearing it removes the previous list. Galaxy layers and saved
systems remain available. Restored anchors and explicit Finder links still load
results, as do archetype rankings behind the existing default-off F4 flag.

## 2026-11-01 — Colony Planner S3b: surface slot predictions

The planner bodies route now returns surface slot predictions from the canonical
`validated-slot-v1` predictor, with version, status, missing required inputs and
an unavailable reason. It reuses S5b's published mechanics read and generation
guard: a missing or mismatched derived publication leaves prediction fields
null without rejecting the canonical bodies response. Radius is converted from
kilometres to metres; vocabulary names and signal counts retain unknown inputs.
Non-landable bodies, barycentres and belts have no surface prediction. Orbital
slots are never predicted. No migration or evaluate-route database access is
added.

The `/plan` surface totals show “predicted” or “entered by you”. Entered values,
including zero, take precedence and remain editable; clearing an override uses
the available prediction. Evaluation and free-slot selection use the same
effective totals, while saved plans keep only commander-entered overrides.

Both API clients are regenerated with `OPENAPI_INPUT=/tmp/edfinder-s3b-openapi.json
pnpm generate:api`, using the full application's `app.openapi()` export without
starting services. The second generation is byte-identical. Unit/component
coverage checks conversions, nulls, lineage guards and override/source behavior;
`tests/test_plan_bodies_postgres.py` extends the PostgreSQL 18 contract. The
retained Praea Euq WV-W b2-2 fixture includes all 24 landable bodies but lacks
their atmosphere inputs; it therefore tests unknown predictions. There is no
complete committed fixture for replaying the 2026-10-31 numeric answer key.

Validation: `apps/web` frozen install, `pnpm check` (no errors or warnings),
`pnpm test` (1,053 passed), `pnpm build`, targeted ESLint and
`ruff check apps/api tests` passed. The requested database-free Python suite
passed with 8,602 tests and 658 skips, after repairing this runner's local
CPython 3.14.7 library lookup; repetitive dependency deprecation warnings were
suppressed. All 16 planner PostgreSQL tests collect, but need execution by the
reviewer/CI on disposable PostgreSQL 18. Browser visual acceptance remains
required before promotion.

## 2026-11-01 — Surface the live Colony Planner on the home page and header

The home page now links to `/plan` with a Plan tool card describing colony
layouts, construction points, economies and Raven Colonial import. Only
Review & export remains labelled Coming later. The tool grid uses three
columns on desktop and stacks on tablet and phone widths. The product header
now shows Explore, Inspect and Plan, including the active-page state on `/plan`.
Component and browser coverage check the links, remaining upcoming item and
responsive layout.

## 2026-11-01 — Colony Planner: floating, tabbed facility picker

The facility picker opens beside the body's add button, or as a centred sheet
on narrow screens, with keyboard focus, Escape, Close and outside-click
dismissal. Both, Orbital and Surface tabs replace six-row pages with one
scrolling list grouped by facility type, with starports first and search scoped
to the selected tab. Rows show compact server-evaluated CP costs and rewards;
only visible choices request previews, with at most six pending requests and
cancellation when the plan, location or filters change. Primary Port, location
fit and the 300-site limit remain enforced.

## 2026-11-01 — Sixth F2d release `181f6fed` accepted in production

Owner-approved. Release run 41319999720 (source `181f6fed`) passed preflight
run 41320584087 and was accepted by promotion run 41320746913 at
2026-11-01T15:21:35Z to slot blue: staging, active and public smoke 200, F2d
image contract, OpenAPI bounds, 422 rejections and behavioural probes passed;
no migration, no database writes, protected resources unchanged. It carries
Colony Planner S5b (#967), the Raven layout import (#970) and Finder F4c behind
its default-off flag (#969). Operator-code and ranking identities are
unchanged. `deploy/v3-production/target-authority.json` records it as the
accepted release, attested for the installed through-022 set; `3fd8e719` is the
recorded rollback artifact and `f667bb4d` stays the minimum schema-compatible
image. Receipts are under `docs/operations/evidence/2026-11-01-v3-production-*`.

## 2026-11-01 — Colony Planner S4b part 2: Raven layout file import

The `/plan` page imports commander-exported Raven Colonial JSON files with
explicit replacement confirmation, Primary Port protection, safe numeric-id
validation and dismissible import notes. Sites retain their order, unavailable
bodies become Unplaced, and belt clusters share the belt's buildable location
and lowest-cluster slot counts. The deterministic mapper bounds sites and
preserves facility/location mismatches for evaluation.

The 112 build-type mappings come from **Copy of Colonization Construction v3
(By DaftMav).xlsx**, sheet **Lists**, rows **48–159**, as supplied by the owner.
No Raven source code was consulted or copied, and importing requires no Raven
server request, API change, dependency change or storage-format change.

## 2026-11-01 — Finder F4c: mode- and reference-safe saved surfaces

Behind the default-off `VITE_FINDER_F4_ENABLED` flag, Compare and Watchlist use
canonical archetype labels and API-supplied tiers. Saved snapshots retain overall
potential separately from the selected fit and its identity. Compare checks the
four semantic ranking/model provenance fields before comparing scores; matching
generations and build manifests are not required. Selected fits additionally
require the same archetype. Older saves remain readable without guessing their
mode or reference or rewriting browser storage.

Compare distance returns in enabled builds only for one shared reference, named
in the table and CSV. Every finite referenced distance, including zero, is valid;
unreferenced legacy distances cannot participate. Disabled builds retain their
existing behavior. F4e, browser and visual acceptance, the owner's enablement
decision (F4 design question 3), and the governed release remain required before
the flag may be enabled.

## 2026-11-01 — Purge tests: wider maintenance suppression and transient-writer evidence (round 3)

CI run 41281603191 (job 124774473183, Finder derived-data shard 1/3, on the
unrelated web-only PR #965) failed one test:
`test_active_vacuum_progress_refuses_phase_before_disabling_autovacuum[superuser]`.
Its first step, `_authorize`, was refused by migration `016`'s guard with
`competing writing transaction`, yet #964's post-refusal diagnostic found no
matching backend, so the competitor had already left.

An audit of every connection on that path (canonical fixture, `installed_purge`,
`_seed`, `_plan`, observers) found none that closes with an open transaction or
touches the test database. It did find that the fixture's maintenance
suppression covered only `v3_%` schemas and local `pg_catalog`, missing the
inherited `information_schema` heaps and any other non-shared heap. Changes,
all in tests:

- The suppression now covers every non-shared, non-temporary heap and its TOAST
  table. The four purge relations keep their unset `autovacuum_enabled` and
  high thresholds. A new PostgreSQL test pins this for both creator roles.
- `_authorize` waits (at most 10 seconds) for this database's automatic
  maintenance workers to leave before its single authorization attempt.
  Shared catalogs cannot be suppressed locally, and their workers can attach
  during seeding. Client writers are never waited for, cancelled or retried.
- `diagnose_competing_writers` keeps one administrator observer open across a
  purge call. It records the database's activity just before the call and up to
  20 samples within 200 ms after a refusal, so a backend that leaves within
  milliseconds is still named. Client SQL text is omitted, apart from two fixed
  test probes, and errors never include connection strings.

The original competitor is still not proven. If this recurs, the new notes
should name it. No SQL, migration or production code changed, and no
assertion was weakened, retried or skipped. Database-free tests: 45 passed.
The reviewer ran the targeted PostgreSQL tests locally (35 passed), and CI's
Finder shards run the full purge suites.

## 2026-11-01 — Fifth F2d release `3fd8e719` accepted in production

Owner-approved, after the post-purge Sunday full backup finished. Release run
41293253404 (source `3fd8e719`) passed preflight run 41293445849 and was
accepted by promotion run 41293577222 at 2026-11-01T09:33:27Z to slot green:
staging, active and public smoke 200, F2d image contract, OpenAPI bounds, 422
rejections and behavioural probes passed; no migration, no database writes,
protected resources unchanged. It carries the Colony Planner `/plan` page
through S5a, the 2026-10-31 audit fixes A1–A4 (#956, #957, #958, #962), the
Finder F4b work behind its default-off flag and the journal export pause. The
accepted F2d operator-code identity is now `8696feb8…`; ranking identity is
unchanged. `deploy/v3-production/target-authority.json` records it as the
accepted release, attested for the installed through-022 set; `1e748c9d` is the
recorded rollback artifact and `f667bb4d` stays the minimum schema-compatible
image. Receipts are under `docs/operations/evidence/2026-11-01-v3-production-*`.

## 2026-11-01 — Finder F4b: picker, ranked cards and browser contracts behind the default-off flag

F4b implements the archetype picker, selected-only minimum tier, ranked cards,
one-envelope paging, URL-owned selection and retained map markers, plus
state-carrying Explore/Inspect/watchlist round trips. Selected cards use the
owner's amended best-rival Clear fit / Close fit rule. Any keeps its no-floor
search; Compare distance remains suppressed in enabled builds pending F4c.

The protected Product E2E bundle and disposable Review Lab bundle alone opt in
to `VITE_FINDER_F4_ENABLED=1`. The web image accepts a validated `0`/`1` build
argument with a fail-closed default of `0`; workflow and release-image contracts
enforce these boundaries. Product E2E covers the three committed PostgreSQL
fixture rows, keyboard selection, paging, clean-session selection hydration,
Inspect return, history, axe and desktop/mobile screenshots. Review Lab adds
backend-owned ranking failure/empty modes and verifies selection survival,
normal Any recovery, failure tagging and the support-route matrix.

These are fixture-based implementation and validation changes. The prerequisite
migration/build/validation and step 9′ product-publication sequence completed
2026-10-23; slice 1c's representative-scale proof passed all 72 measurements on
2026-10-31. Before the flag may be enabled in any governed production or release
build, F4c, F4e, browser acceptance, visual approval, the owner enablement decision
and the separate governed application-release gate remain required. F4b does not
enable the flag in such a build or authorize a deployment.

## 2026-11-01 — CI runs the V3 journal flow tests; the stale export-limit test is fixed

`tests/integration/test_v3_journal_research_flow.py` and
`test_v3_journal_import_flow.py` never ran in CI: the integration job's
database has only the V2 schema, so both modules skipped. One test had been
failing unnoticed: `test_export_replay_limited_batch_matches_receipt` still
expected the old oldest-first export order. The export reads the newest rows
first, so a 5-row limit now gives 3 observations. The test now names them and
still proves that the limit applies before sanitization and that the replay
matches the receipt. A new CI job, "V3 journal flows (PG18+Redis)", applies
V3 migrations 001, 002, 005, 008 and 009 to an empty PostgreSQL 18 database,
runs both modules, and fails on any skip. Workflow contract tests pin the job.

## 2026-11-01 — Journal research export paused (owner decision D4)

`RESEARCH_EXPORT_PAUSED` in `apps/api/src/routers/v3_journal_research.py`
refuses new research exports and consent grants with HTTP 503 and reason
`research_export_paused`, after the existing authentication and origin checks.
Exports cannot yet carry colonisation events the CRE can use; resuming them
requires a reviewed code change. Withdrawal still supersedes lineage batches,
and all consent and export reads remain available. Database-free route tests
cover the refusals and withdrawal; PostgreSQL integration coverage preserves
the export-builder and consent flows with the pause explicitly disabled.


## 2026-10-31 — Finder: ranking rows carry their best rival archetype (F4b fit label)

Selected-archetype ranking rows now carry `rival_archetype` and `rival_score`,
computed from the wide row already fetched for each result. The rival is the
highest-scoring other archetype excluding Flexible, with ties resolved in
`ARCHETYPE_KEYS` order; picking Flexible compares against the other seven.
The generated API clients and application facade carry both optional fields.

F4 section 9 records the owner's amended label rule: Clear fit requires the
picked score to exceed the rival by at least three points; otherwise Close fit
names the rival and its score. Rendering that label remains F4b UI work.
Ranking membership, order, windows, counts, existing fields and identity are
unchanged, as are Any-mode queries and responses. Regression tests cover rival
selection, the final-SELECT-only SQL addition, fixture recomputation at every
floor and facade compatibility with servers that omit the new fields.

## 2026-10-31 — Finder: /api/archetypes/rankings accepts its documented min_score values

Production evidence reported on 2026-10-31: `GET
https://ed-finder.app/api/archetypes/rankings?archetype=paradise&limit=2`
returns 200, but adding `min_score=60`, `76` or `88` returns 422. For `76`,
the validation error is `{"type":"literal_error","loc":["query","min_score"],"msg":"Input should be 60, 76 or 88","input":"76"}`.
FastAPI 0.141 / Pydantic 2.13 does not coerce query strings to the integer
values in `Literal[60, 76, 88]`; only the omitted parameter's integer default
worked. The F4a rankings client sends `min_score` explicitly, so this would
fail every F4b rankings request. No live UI sends it yet: F4 remains behind its
default-off flag.

The handler now parses an integer before restricting it to the same three
indexed floors. The integer enum and default 60 in OpenAPI, helper validation,
ranking SQL/profile/identity, response fields and paging bounds are unchanged.
New database-free tests exercise the real FastAPI app's query parsing for
omitted, accepted and rejected floors, the OpenAPI schema, and the 10,000-row
window bound; the existing direct-helper tests could not expose this bug.
This takes effect in production only with the next governed application release.

## 2026-10-31 — Finder slice 1c: opt-in representative-scale ranking proof

Added `tests/test_archetype_rankings_scale_postgres.py` to prove bounded selected
ranking plans and the owner-accepted warm/cold latency budgets on a disposable
PostgreSQL 18 database with one million systems, for all eight archetypes at
each B/A/S floor. It is opt-in via `EDF_RANKINGS_SCALE_PROOF=1` because seeding
the corpus and restarting the server before all 72 cold measurements must not
run in the Finder lane on every PR. Each run prepares the route's SQL and
measures it with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE` under
`plan_cache_mode = force_generic_plan`, and fails unless `pg_prepared_statements`
shows that the run used a generic plan. Its JSON receipt records compact
warm-median plans, cold plan summaries, timings, each run's plan-cache counters,
identities and failures; a passing receipt is the representative-scale evidence
that unblocks F4b.

The proof was then run on a disposable PostgreSQL 18.4 server (2 CPUs, 7 GB
RAM, default memory settings). The first run measured the near-ceiling page
(offset 9950) over budget for all 24 archetype/floor pairs (705–1,098 ms warm
against 600 ms): the page joined all 10,000 window rows to `system_search`
before paging and the planner chose a sequential scan of the whole table. The
owner approved a query fix (#948).

Codex review of this proof then found that those first runs, and the
measurements quoted in the #948 entry below, passed the page's `LIMIT`/`OFFSET`
to `EXPLAIN` as bound values. PostgreSQL plans those as constants, so the runs
measured custom plans, not the generic plans the F4 design requires, even
though `force_generic_plan` was set. The harness was corrected to the
prepared-statement method above. With #948, it passed all 72 measurements, and
every one of the 432 timed runs used a generic plan (receipt
`docs/operations/evidence/2026-10-31-v3-finder-slice1c-rankings-scale-proof-receipt.json`,
buffer-cold):

| Query | Warm (budget) | Cold (budget) |
|---|---|---|
| First page | 3.5–6.9 ms (300 ms) | 9.2–22.4 ms (1,500 ms) |
| Near-ceiling page | 39.5–72.4 ms (600 ms) | 70.7–169.0 ms (2,500 ms) |
| Count | 37.0–65.6 ms (600 ms) | 62.8–138.1 ms (2,500 ms) |

## 2026-10-31 — Purge complete: body and vector relations done, step P COMPLETED

The governed purge of `ratings_v4_prod_p4` and `ratings_v4_prod_p4_opt1`
(ROADMAP step P) finished on the copy-and-drop route. Every run below was
approved by the owner in chat.

**`body_mechanics`:**
- **Copy:** run 41206570787 copied all 577,709,320 survivors (5,778 chunks in
  6,862.9 s), built the indexes in 517 s and froze the copy in 1,537 s.
- **Verify:** run 41218286633 verified it in 1,208 s.
- **Swap:** run 41220237129 swapped it in with a 0.114 s lock. It validated the
  `economy_opportunity` foreign key to the new table in 163.5 s and passed the
  Finder smoke.
- **Drop:** run 41220886721 dropped the retired table with a 5.4 s lock, taking
  free space from 433.1 GB to 643.3 GB.

**`system_rating_vector`:**
- **Copy:** run 41228458030 copied all 198,528,286 survivors, built the indexes
  in 321 s and froze the copy in 1,278 s.
- **Verify:** run 41239134283 verified it in 605 s.
- **Swap:** run 41240118438 swapped it in with a 0.145 s lock. It validated the
  foreign keys of all four children (`body_mechanics`, `system_archetype`,
  `system_search` and `v3_spatial.cluster_member`) in 124 s, recreated
  `v3_derived.system_economy_rating` unchanged and passed the Finder smoke. The
  database's temporary-file counter did not change during those checks; the
  1/100-scale planner model had allowed for about 30 GB for the
  `body_mechanics` check.
- **Drop:** run 41240648857 dropped the retired table with a 4.4 s lock, taking
  free space from 568.0 GB to 725.9 GB.

**`complete`:** run 41241201758 appended 019's `COMPLETED` (event 22040). The
purge state is `clear`, no relation is staged or retired, and the backup skip is
off. The canonical, derived and spatial pointers are unchanged. Both published
Finder products are unchanged: READY, 198,528,286 rows each, same manifests.

The dispatcher's swap, drop and `complete` steps for both relations were
replayed on PostgreSQL 18 in the production order before they ran
(`test_body_and_vector_swap_drop_and_complete_replay_through_the_dispatcher`).

The runbook's full backup after `COMPLETED` is the scheduled Sunday
2026-11-01 02:30 UTC full backup, which was still to run when this was
written.

## 2026-10-31 — Finder: deep selected-archetype pages read search details for the page only

The owner-approved query change keeps the selected archetype's partial-index
window unchanged at 10,000 rows, checks published Search membership using only
keys, and applies the existing order and page limit/offset before reading
`system_search` details. The final `picked` fetch is unchanged. Results, order,
response shape and ranking identity are unchanged; the count and Any-mode
queries are unchanged. This takes effect in production only at the next
governed application release.

The Finder F4 slice 1c PostgreSQL 18 proof used 1,000,000 systems, saturated
every window, and exercised all eight archetypes at the B/A/S floors under
`plan_cache_mode = force_generic_plan`. First pages passed 24/24 cases at
2–4 ms warm and 7–21 ms cold (budgets 300 / 1,500 ms); bounded counts passed
24/24 at 38–67 ms warm and 63–185 ms cold (600 / 2,500 ms). Near-ceiling pages
(`offset=9950`, `limit=50`) failed 24/24 at 705–1,098 ms warm against 600 ms,
also under production's planner settings (`effective_cache_size=128GB`,
`work_mem=32MB`). The old page joined 10,000 wide Search rows before paging,
choosing a hash join over a 1,000,000-row sequential scan (about 650 ms) and a
wide-row sort; the count's key-only join used primary-key index-only scans
(10,001 loops, about 45 ms). The 2026-10-23 publication probe covered only
offset-zero pages and counts. The revised query defers detail reads until
after pagination; PostgreSQL regression tests compare its complete output
with the old SQL and bound detail reads to the page size.

## 2026-10-31 — CRE rulebook v0.5.0 pinned: strong links with both port kinds

ED-Finder now reads CRE release `cre-knowledge-v0.5.0` (CRE commit `db7ee07`,
SHA-256 `03faf90c…1f53`, 29 rules), approved by the owner on 2026-10-31. New
`RB-0029` (`Confirmed`, CRE evidence `EV-0007`: the Dodec and the Large
Planetary Port on Wregoe ZN-X c28-28 A 5): on a body with both an orbital and a
planetary port, surface facilities link to the planetary port, which passes
their links on to the orbital port with its own strong link per economy;
orbital facilities link to the orbital port only. Contradiction `C-0014` records
that the guide's footnote 20 is contradicted. The parity test finds no new or
resolved difference.

## 2026-10-31 — CRE rulebook v0.4.0 pinned: economy rules settled in game

ED-Finder now reads CRE release `cre-knowledge-v0.4.0` (CRE commit `3ca81b6`,
SHA-256 `d2e64e8f…7976`, 28 rules), approved by the owner on 2026-10-31. It is
the first release with rules settled by in-game measurement (CRE evidence
`EV-0006`: colony port economy strengths from the owner's game journals and
Spansh station data).

- `RB-0012` (body economies and modifiers do not stack) is `Confirmed`.
- `RB-0013` gives volcanism's size: +0.4 to the port's own Extraction only.
- `RB-0016` (weak links 0.05) is `Confirmed`.
- New `RB-0028`: the strong-link modifier list also applies to a port's own
  economies. Each inherited economy starts at 1.0 and moves 0.4 per applicable
  condition, and a tidally locked planet in a binary pair counts as locked to
  its star.

Both copies (`docs/reference/colonisation/cre-rulebook/` and the planner's
runtime copy `apps/api/src/cpe/data/rulebook.json`), `pin.json` and
`assets/PROVENANCE.json` are updated. The parity test found no new or resolved
difference; one listed reason now cites the new status. The CRE tag itself
could not be pushed from the agent session; the pin is by commit, which the
rulebook README makes authoritative.

## 2026-10-31 — CI: Finder lane weights from CI and a session-independent EDDN freshness test

The Finder derived-data weights now come from CI run `41227989407` (PR #943,
head `8718e895`), replacing the local PostgreSQL 18 timings. Its three green
shards took 17.5 / 13.5 / 16.7 minutes, with 1,012.5 / 776.6 / 964.1 s of
test time: CI's relative module speeds differ from the local run. The refresh
uses all three `finder-derived-data-durations-*` artifacts, covering
228 + 311 + 328 = 867 distinct node ids with every shard exitstatus 0.
The new weights plan 918.2 / 917.7 / 917.7 s across the three shards.

The EDDN freshness test now imports the client in a fresh interpreter and
checks that its initial elapsed time is finite, nonnegative and below 60 s.
Previously it measured time since collection imported the module, so the full
backend unit suite failed after 140.36 s in Codex worker run `41223127055`
even though the module passed alone. The subprocess check tests process-start
freshness independently of session duration or test order.

## 2026-10-31 — CI: Finder derived-data lane in three time-balanced shards

The PostgreSQL 18 Finder derived-data lane now uses three shards balanced by
measured module seconds. Its former two-shard byte-size split took 35:32 /
15:18 on PR #936, making the lane the PR critical path. A local PostgreSQL 18
run measured `test_v3_governed_derived_purge.py` alone at 2,079.6 s of
3,608.7 s across 40 modules, so keeping every module whole could not balance
three shards. A pytest plugin collects every discovered module on every shard,
splits the dominant module at test level, keeps smaller modules whole, and
assigns each test exactly once with deterministic greedy balancing. The
45-minute pytest bound and disposable-database guardrails are unchanged.

Each shard uploads per-test phase durations. To refresh the weights, download
all three `finder-derived-data-durations-*` artifacts from one green run, run
`python scripts/ci/finder_derived_data_weights.py --measured "DATE: run evidence"
finder-derived-data-durations-{1,2,3}.json > scripts/ci/finder_derived_data_weights.json`,
and commit the new weights file. The refresh tool refuses incomplete, failed
or overlapping shard results; new modules use a byte-size fallback calibrated
by the measured modules until the next refresh.

## 2026-10-31 — Codex worker model pin moved to `gpt-6-astra` at `xhigh` effort

By owner decision, the Contabo Codex worker moves from `gpt-6.1-sol` at
`high` effort to `gpt-6-astra` at `xhigh` (extra high) effort "for now": most of
this week's Codex allowance is unused and it resets on Monday. Both execution
modes keep the single hard-pinned model contract (`--ignore-user-config
--strict-config --model … --config model_reasoning_effort=…`). Requests still
cannot choose a model or effort, and the governance test now rejects the old
`gpt-6.1-sol` and `high` literals. Whether to return to `gpt-6.1-sol` after the
reset is the owner's call.

## 2026-10-31 — Purge: opportunity relation done

`v3_derived.economy_opportunity` now holds only the 740,001,532 published
survivors. The first copy (runs 41140926027, 41155213939 and 41166416358)
reached 486.2 million rows at 2.92, 6.85 and 9.06 s per 100,000-row chunk
before the owner stopped it; `abandon-economy-opportunity` (run 41176670411)
dropped the staging copy and left the live table untouched. Migration 022 was
then applied (plan run 41180417409, apply run 41180459540) and the copy
restarted from `prepare`: every chunk read took about 0.23 s (runs
41181532586 and 41182249937; indexes built in 488 s, copy frozen in
2,256 s), and run 41194211040 verified it in 1,592 s, including the foreign
key to `body_mechanics`. `swap-economy-opportunity` (run 41198027388)
swapped it in with a 0.11 s lock, recalibrated `n_distinct` for
`system_id64` from fresh counts (75,539,150 systems over 740,001,532 rows,
−0.10208), confirmed the archetype builder's chunk read still plans as a
nested loop over `economy_opportunity_pkey` and passed the Finder smoke.
`drop-economy-opportunity` (run 41206256540) repeated the count, statistics
and plan check and the Finder smoke, then dropped the retired table, taking
free space from 260.9 GB to 526.4 GB; backups are no longer skipped until
`body_mechanics` prepares.

The dispatcher's swap and drop steps for this relation were replayed on
PostgreSQL 18 in the production order before they ran
(`test_opportunity_swap_and_drop_replay_through_the_dispatcher`). The
foreign-key checks still ahead on the route were also planned on a local
1/100-scale model with production's planner settings (`random_page_cost` 4,
`maintenance_work_mem` 2 GB): the opportunity → body checks and the body
copy's check against the live vector plan as merge anti-joins over the two
primary keys with no temporary files, and the body → vector check after the
vector swap as a hash anti-join writing about 30 GB of temporary files, under
its 32 GiB limit
(`docs/operations/evidence/2026-10-31-v3-purge-fk-validation-planner-model.json`).

## 2026-10-31 — Purge chunk reads start at their keyset (migration 022)

`copy-economy-opportunity` slowed from 2.92 s to 6.85 s per 100,000-row chunk
between its first two runs, the Search copy had shown the same slope, and the
`economy_opportunity` verification could never have fitted its 19,200 s
bound. 019's chunk read and 021's verification re-read bounded each chunk
with a row comparison led by `derived_generation_id` plus a separate equality
on it; the equality wins the btree scan's start position, so every chunk
walked all the survivor index entries before its low key. Migration
`022_v3_purge_keyset_start.sql` adds `v3_meta.purge_copy_keyset`, which bounds
the generation with `<=` so the row comparison starts the scan (same rows,
same plan shape; flat cost per chunk on PostgreSQL 18), and replaces
`purge_copy_chunk` and `purge_copy_verify` to use it. The purge authorized
on 2026-10-29 froze the through-021 migration ledger, so 016's
`purge_assert_request` also accepts the live ledger minus exactly 022's own
row; any other difference still refuses. Registered through-021 →
through-022 with `1e748c9d` attested for both endpoints. Not applied: the
governed apply refuses while a copy is staged, so the partial opportunities
copy is abandoned first (owner-approved) and copied again afterwards.

## 2026-10-30 — Purge verify gets a longer bound for the larger relations

The Search verify took 4,247 s (about 4.7 × its production-speed estimate)
and wrote about 19 GB of temporary files. Scaled by the one_percent
rehearsal's relative verify times, `economy_opportunity` would need about 3.7
hours and `body_mechanics` about 2.9, past the 7,200 s statement timeout and
probably the 32 GiB temp-file limit. By owner decision, verification alone now
runs under a 320-minute statement timeout and a 64 GiB temp-file limit; the
copy dispatch budget is 330 minutes and the purge job 360 minutes, GitHub's
ceiling for a hosted job. Every other phase keeps its 7,200 s and 32 GiB
bounds, and the workflow's admission check is per phase. The owner accepted
these changes to the pinned `v3_purge_copy.py` and `v3_purge_copy_dispatch.py`
(`amended_files`).

## 2026-10-30 — Purge: Search relation done

`v3_derived.system_search` now holds only the 198,528,286 published
survivors. Copy runs 41050714814 and 41070830382 copied the rows; run
41097049762 built the indexes (478 s) and froze the copy (1,382 s); run
41104549088 verified it (4,247 s); `swap-system-search` (run 41118398123)
swapped it in with a 0.1 s lock, validated foreign keys and passed the Finder
smoke; `drop-system-search` (run 41122363522) dropped the retired table, taking
free space from 200.6 GB to 375.7 GB, and backups are no longer skipped. The
read-only host inventories of the same day (`v3-host-storage-detail` run
41088164473, `v3-disk-inventory` run 41088246411) are committed with the
receipts. The other three relations have not started: the Search verify ran
about 4.7 × its production-speed estimate and wrote about 19 GB of temporary
files, which must be re-estimated for the larger relations first.

## 2026-10-30 — Purge watchdog rides out a checkpoint's WAL segment burst

After the space-check fix, `copy-system-search` built the Search indexes (8
minutes) and froze the copy (23 minutes) in run 41097049762. The verify,
carried to run 41102817187, was cancelled about a minute in by the long-phase
watchdog: a checkpoint was removing or recycling the WAL segments those two
steps had written, and the `pg_wal` size probe (`du`) failed three times in a
row, which the watchdog treats as a fault (`observe:wal_directory_bytes_unavailable`).
Nothing was lost; the verify only reads and resumes on the next dispatch.
`measure_wal` now keeps re-measuring every 0.5 s for up to 60 s after the three
immediate attempts before it fails closed. The owner accepted this third
change to a pinned file (`v3_generation_purge.py`, recorded in
`amended_files`). The file is in the F2d operator-code manifest, so F2d build
and status operations refuse until the next application release attests the
new identity; the purge does not use them.

## 2026-10-30 — Purge index-build space check stops counting the prebuilt Search index

`copy-system-search` copied all 198,528,286 Search survivors in two runs
(41050714814, 41070830382); the second then stopped, with nothing written for
the index build, at its free-space check: 221.8 GB free against 232.0 GB
required. The check reserved space for every live index, but the Search GiST
index on `position_ly` is created on the staging table at `prepare` and
filled by the row copy (17.5 GB already on disk), and the index build skips
it. The estimate now counts only the live indexes the build still creates
(about 206 GB required for Search); every other term of the check is
unchanged, and relations without a prebuilt index are unaffected. A
PostgreSQL 18 test proves the estimate before and after `prepare`. Read-only
host inventories (runs 41088164473, 41088246411) showed only about 11.6 GB
outside the database, so the shortfall could not be freed on the host. The
owner accepted this second change to the pinned `v3_purge_copy.py`; the
`amended_files` entry carries its new accepted digest.

## 2026-10-30 — Purge Search scan handles fully validated checks

The first `preflight-system-search` (run 41034514200) stopped read-only with
`bounded_command_failed`. Production validated all 18 Search checks on
2026-10-18; with none left NOT VALID, the survivor scan's aggregate still
returned one row and generated a statement selecting every survivor, which
failed (`SQLSTATE 2200M`). The rehearsal fixture kept the checks NOT VALID, so
the rehearsal never ran this case. `SEARCH_VIOLATIONS_SQL` now answers `{}`
without scanning when no NOT VALID check exists and is unchanged otherwise; a
PostgreSQL 18 test validates every check first and proves the old statement
fails there. The owner accepted this one change to a pinned file without a new
rehearsal: `ACCEPTED_REHEARSALS` records it under `amended_files`, and the
accepted rehearsal receipt (run 40704251158) is now committed as evidence. The
stopped preflight receipt is committed too.

## 2026-10-30 — Purge authorized; WAL archiving runs in the background

The governed purge's `plan` and `authorize` ran in production on 2026-10-29,
each owner-approved, from main `670ae640`. Plan run 40961557646 sealed
successfully, but its one-hour window lapsed before `authorize` started: run
40969595627 stopped with `plan_expired_or_future` before any database access.
Plan run 40969722614 sealed the identical reviewed plan and authorize run
40971335172 succeeded, opening purge ids `e3d03d58…` and `2110f899…` for
`ratings_v4_prod_p4` and `ratings_v4_prod_p4_opt1`. No payload rows were
deleted; the published generation and both Finder products are unchanged.
On 2026-10-30 the owner turned on background parallel WAL archiving from the
#919 runbook; the async log shows the forced segment pushed in 518 ms. The
runbook's `check` step now passes `--log-level-console=info`, because at the
default console level a successful check prints nothing. All four receipts and
the owner-run record are committed as evidence. The purge runbook now also
says to run that check before a relation's first `copy-R` whenever a scheduled
backup has run since the last one: the copy route's archive-lag query cannot
read the backup history file name a backup leaves in `pg_stat_archiver`.

## 2026-10-29 — Purge action runs from the host operator directory

The second protected `plan` (run 40946906378) reached the host and stopped
read-only with `worker_state_unknown`. It had already proved the installed
backup wrapper, the migration ledger, a clear purge state, both targets'
payload counts and 316 GB free. `workers()` reuses the lifecycle action, which
refuses any working directory but `/opt/ed-finder` (as the ops workflow runs
it), and the launcher ran the action from the unpacked bundle. The launcher
now proves the bundle's HEAD inside the bundle, then starts the action from
`/opt/ed-finder` with absolute artifact paths. Every purge path was already
absolute, so no pinned file changes and the accepted rehearsal stands. The
stopped receipt is committed as evidence.

## 2026-10-29 — Purge plan downloads the rehearsal receipt by exact name

The first protected `plan` (run 40939364894, rehearsal run 40704251158) stopped
in the GitHub-side artifact authentication, before any SSH or production read:
the rehearsal artifact was downloaded by name pattern, and a pattern that
matches a single artifact is extracted straight into the target path rather
than the per-attempt directory the authentication reads. The workflow now
resolves the attempt GitHub reports for the rehearsal run (a
`resolve-rehearsal-attempt` helper command: the same pinned run fetch and
provenance check as authentication, no `gh api`) and downloads exactly
`v3-derived-purge-rehearsal-<run>-<attempt>`
into that directory; authentication still re-fetches the run and reads only
that attempt. Its stopped receipt is committed as evidence. No purge or F2d
operator-code file changes; the pinned rehearsal still applies.

## 2026-10-29 — Runbook: background parallel WAL archiving before the purge

Production archived WAL one 16 MB segment at a time (`pgbackrest.conf` had only
`compress-level=3` for `archive-push`). The purge's long phases write 55–108 GB
of WAL per relation and the watchdog cancels at 2 × `max_wal_size` in `pg_wal`,
so archiving must keep up. `deploy/v3-production/backup/README.md` now records
the configuration facts and the owner steps to turn on `archive-async` with
`process-max=4` for `archive-push`, with a check, proof of an asynchronous
push and an undo; the purge runbook lists it as a precondition. The full-backup
duration notes are corrected to five to six hours.

## 2026-10-29 — Purge preconditions 3 and 4 met in production

The backup heartbeat is installed (ops run 40873385526: files and hashes
verified, timer enabled, a fresh first run exited 0, so pgBackRest shows a
backup within 36 hours; the first attempt, run 40869454484, stopped before
#915 fixed its run order). The owner applied `GRANT SET ON PARAMETER
temp_file_limit TO v3_derived_purge_executor` and verified it with
`has_parameter_privilege` (owner-run, recorded as evidence). Remaining before
the purge `plan`: the pre-copy full backup.

## 2026-10-29 — Backup heartbeat (dead-man's switch)

The new production host had no external alert, so failed or skipped backups
were silent (twelve nights in September; the purge precondition 3 asked for
one). `deploy/v3-production/backup/backup-heartbeat.sh` runs hourly from
`edfinder-v3-backup-heartbeat.timer`: it pings a healthchecks.io check only when
`pgbackrest info` shows a successful backup finished within 36 hours, pings
`/fail` when it can show otherwise, and sends nothing when it has no URL. The
allowlisted `v3-backup-heartbeat-install` operation installs the script and
units from trusted main with pinned hashes, refuses until the owner has
created the private URL file, enables the timer and records the first run.
The URL is a credential kept only on the host.

## 2026-10-29 — Fourth F2d release `1e748c9d` accepted in production

Owner-approved. Release run 40847515414 (source `1e748c9d`) passed preflight
run 40847736690 and was accepted by promotion run 40850450821 at
2026-10-29T09:33:33Z to slot blue: staging, active and public smoke 200,
F2d image contract, OpenAPI bounds, 422 rejections and behavioural probes
passed; no migration, no database writes, protected resources unchanged. It
carries the governed purge operator code (the accepted F2d operator-code
identity is now `feb0ed71…`) and app changes from PRs #892, #895, #896, #902,
#908 and #909. `deploy/v3-production/target-authority.json` now records it as
the accepted release; `a031c2da` is the recorded rollback artifact and
`f667bb4d` stays the minimum schema-compatible image. Receipts, including the
first preflight that stopped read-only before #911, are under
`docs/operations/evidence/`.

## 2026-10-29 — F2d rollback selection honours reviewed compatibility

The first preflight of the fourth F2d release (release run 40840492834, source
`6a97db48`; preflight run 40840746266) stopped read-only with
`f2d_rollback_artifact_schema_incompatible`. The rollback picker checked the
accepted release `a031c2da` only against its own sealed manifest, which names
the through-016 schema it was built for; migrations 019–021 were applied after
it, and the reviewed authority attests through-021 for it. `select_f2d_rollback`
now applies `validate_prior_runtime`'s rule: the recorded artifact that is
exactly the accepted release (source, run, manifest checksum, images) is
compatible when the trusted authority lists the current migration set, and it
must still be application-only rollback eligible. Every other mismatch still
refuses. A promotion that fails after cutover re-applies the same rule to the
artifact it selected, so recovery recreates that release instead of refusing it
(Codex review). Replayed against the real `a031c2da` manifest and authority, the
selection returns that artifact. No release image, migration or purge file
changes.

## 2026-10-28 — Purge rehearsal gate: judge verification at production speed

The one_percent rehearsal with 021 and #906 (run 40704251158) passed every
check, but the production gate refused it: `body_mechanics` and
`economy_opportunity` verification extrapolated to about 7,077 s and 8,900 s on
the rehearsal host, and the gate wants twice the longest phase within the
7,200 s statement cap. An owner-run benchmark of verification's work (row
text, md5, ordered aggregate; reads no table) took 5.56–5.63 s on production
and 17.77–18.48 s on the rehearsal host. Owner decision: no further rehearsal.
The gate now scales extrapolated verification by 0.31695 for receipts measured
in the benchmarked image (other long phases, the 2× allowance and every
statement timeout unchanged; the sealed receipt maths unchanged), and pins run
40704251158 as accepted authority while every file it rehearsed, except the
receipt module, is byte-for-byte unchanged. Its longest phase at production
speed is about 2,821 s. The benchmark is recorded under
`docs/operations/evidence/`.

## 2026-10-28 — Purge watchdog: re-measure pg_wal on a vanished segment; record what latched a cancel

The one_percent rehearsal with 021 (run 40654125745) copied, swapped and
dropped `system_search` (GiST filled during the copy), then stopped when the
watchdog cancelled `economy_opportunity`'s index build seconds after it started,
recorded only as `wal_archiver_failure`: every check that cannot complete is
recorded under that name. One such check is the `pg_wal` size probe, `du`,
which exits 1 when a checkpoint removes or recycles a segment while it walks
the directory (reproduced). `measure_wal` now re-measures up to three times and
still fails closed when the directory keeps failing, and the watchdog records
what latched its condition (`monitor_detail`, `observe:<code>` or
`backend:<code>`) in the copy receipt and the unit's journal. Operator code
only; the production watchdog uses the same probe, so this also guards the real
long phases.

## 2026-10-28 — Migration 021 applied to production

**Production (owner-approved, governed workflow).** Plan run 40654122650
reported `pending=[021]` with no writes; apply run 40654201809 applied
`021_v3_purge_long_phase_bounds.sql` and installed the through-021 schema
identity (`c54f861f…0679`). Capability only: three executor-only purge
functions (prepare, index build, verify) were replaced; no table, view, grant
or payload row changed, and no service changed. This clears the promotion block
that #904 introduced. The apply receipt and the one_percent rehearsal receipt
(run 40571954621) are committed under `docs/operations/evidence/`; CLAUDE.md,
ROADMAP, infrastructure status and the purge runbook record the apply.

## 2026-10-28 — One-percent purge rehearsal; migration 021 bounds the copy's long phases

**One-percent rehearsal (run 40571954621, Contabo, 2026-10-28).** The copy route
passed its own checks: every swap on its first attempt (lock held 0.34–0.68 s),
the worst Finder read stall 0.81 s, all nine crash scenarios, cleanup verified.
It cannot authorize production: three extrapolated long phases exceed the
reviewed 7,200 s envelope (`body_mechanics` verify about 11,400 s,
`economy_opportunity` verify about 16,000 s, `system_search` index build about
15,300 s). The Search preflight scan took 1.2 s (about 2 minutes at production
size), well inside the 2,760 s query transport, so deferred Codex finding
4384599563 stays deferred. Receipt:
`docs/operations/evidence/2026-10-28-v3-derived-purge-rehearsal-receipt-run-40571954621.json`.

**Migration 021 (registered, not applied).** Verification grew faster than the
tables (13.6 and 14.7 times the smoke run's time for 6.67 times the rows).
019's per-chunk re-read paired row comparisons led by `derived_generation_id`
with a separate `derived_generation_id = $1`, so each chunk's index scan ran on
to the end of the survivor generation; on PostgreSQL 18.4 one 100,000-row chunk
read 4,976 buffers in a 600,000-row table and 23,158 in a 3,600,000-row table.
`021_v3_purge_long_phase_bounds.sql` replaces `v3_meta.purge_copy_verify`,
re-reading each chunk the way the copy read it (low key, primary-key order,
`LIMIT` the ledgered rows; 2,670 buffers at both sizes). The Search index build
is dominated by the GiST index on `position_ly`; by owner choice (keep the copy
route, no longer time limit) 021 also replaces `purge_copy_prepare`, which now
creates the live GiST indexes on the empty staging table so the bounded chunk
inserts fill them, and `purge_copy_build_indexes`, which builds the rest and
leaves only such an exactly-matching GiST index alone. Checks, settings, owners
and grants are otherwise 019's. Registered after 020 in the manifest and the
production authority (through-020 → through-021, `a031c2da` attested for both
endpoints). Not applied: promotions are refused on the schema-identity checksum
and the purge controller refuses to plan until it is. The one_percent rehearsal
must be re-run with it.

## 2026-10-27 — CRE rulebook pinned, with a parity test

**Owner decision D1, first step.** The Colonisation Research Engine published
its first rulebook, `cre-knowledge-v0.3.0`: 27 rules with stable `RB-` IDs,
exact values, statuses (`Confirmed`, `Likely`, `Extracted`, `Disputed`) and
quotes checked against the guide's PDF pages and Frontier's notes. A copy is
pinned by release name, CRE commit and SHA-256 under `docs/reference/colonisation/cre-rulebook/`.
`tests/test_cre_rulebook_parity.py` compares ED-Finder's hard-coded tables with
it: construction-point escalation, link strengths and modifier size, body
economies and modifiers (Ratings V4 and the V2 planner), stacking, and the
Ratings V4 strong-link rules (by running `opportunities_from_facts` on probe
bodies). Every difference is listed with its reason; a new or resolved
difference fails the test. The costs fixed in #902 match `RB-0003`. Test and
reference data only: no score, constant or behaviour changed. The rulebook has a
provenance entry (`noncommercial_only`, Frontier-derived) and a notice.

## 2026-10-27 — Migration 020 applied to production

**Production (owner-approved, governed workflow).** Plan run 40551071635
reported `pending=[020]` with no writes; apply run 40551173291 applied
`020_v3_purge_swap_lock_order.sql` and installed the through-020 schema
identity (`55284f7d…1f00`). Capability only: three executor-only purge
functions changed their locking and one internal helper was added; no table,
view, grant or payload row changed. This clears the promotion block that #898
introduced. The receipt is committed under `docs/operations/evidence/`; CLAUDE.md,
ROADMAP, infrastructure status and the purge runbook record the apply.

## 2026-10-27 — Purge rehearsal: the restart crash scenario proves the archiver refusal, then resumes

Smoke rehearsal run 40495068589 (300,000 systems) completed the whole
copy-and-drop journey through `complete` and passed eight of the nine crash
scenarios. `copy_postgres_restart` stopped: after `docker restart --time 0` the
re-dispatched `copy-economy-opportunity` refused `wal_archive_lag_unknown`. A
crash restart discards `pg_stat_archiver`, so the action cannot measure archive
lag until the archiver reports a segment; the refusal is the action failing
closed, and the rehearsal container (no `archive_timeout`, no other WAL
traffic) never completes one on its own.

- The scenario now dispatches `copy-R` once after the restart and requires that
  it either succeeds or refuses with exactly `wal_archive_lag_unknown` (recorded
  as `restart_archive_refusal`; any other refusal fails the scenario), then
  completes one WAL segment as production's own traffic would, then resumes.
- The runbook records the production behaviour after a database restart.

## 2026-10-27 — Purge rehearsal: smoke at 300,000 systems; seed analyses before its receipt joins

The second smoke rehearsal (run 40484503505, with 020's lock order) swapped
`system_search` cleanly (one attempt, 0.44 s, the concurrent Finder read never
failed), then the real action refused the `economy_opportunity` swap with
`n_distinct_recalibration_plan_unverified`. At 100,000 systems the archetype
chunk read (one 1,000-system Ratings chunk joined to the opportunity table) is
genuinely cheaper as a hash join over the whole 372,744-row table, so the F7
proof that production's 746 M-row table plans a nested loop over
`economy_opportunity_pkey` cannot hold. Reproduced on PostgreSQL 18 with the
harness's own seed: hash join at 100,000 systems with default or production
planner settings, nested loop at 200,000 and 400,000. Every crash scenario also
swaps `economy_opportunity` at smoke proportions, so gate 10 could never pass.
The action's proof is unchanged.

- **Smoke scale** 100,000 → 300,000 systems (about 0.15%), keeping a margin
  above the crossover; crash fixtures follow. The workflow's smoke disk minimum
  becomes 150 GB (about 15 GB of fixture data on top of the action's ~135 GB
  admission).
- **Seed statistics.** The build-receipt join ran for more than 30 minutes at
  200,000 systems because the freshly inserted tables had no statistics; each
  receipt join now runs `ANALYZE` on its inputs first (136 s for the whole
  200,000-system seed, 268 s at 400,000).

## 2026-10-27 — Purge P: swap lock order (migration 020, registered, not applied)

The first smoke rehearsal of the copy route (run 40466831980, on Contabo,
disposable) stopped at its first swap with `finder_reader_failed`: the
concurrent Finder read of `v3_app.system_search` was cancelled by PostgreSQL as
a deadlock. Reproduced on PostgreSQL 18. Nothing ran against production.

- **Cause.** 019's swap locked the live table, then (inside the relocation) the
  dependent view; a reader locks the view first, then the tables it reads.
  019 also locked the view with `LOCK TABLE`, which on a view locks every
  relation the view reads, so `v3_meta.current_derived_generation`,
  `derived_generation` and `derived_product` were held `ACCESS EXCLUSIVE` and
  every Finder read waited for the whole swap.
- **Migration `020_v3_purge_swap_lock_order.sql`.** Adds the internal
  `v3_meta.purge_copy_lock_relocation`: the dependent view first, locked alone
  by a no-op owner change, then the outgoing, incoming and child tables, each
  `NOWAIT`. `purge_copy_swap` and `purge_copy_swap_back` call it in place of
  their `LOCK TABLE`; `purge_copy_relocate` no longer locks and refuses unless
  the locks are held. Nothing else in the three functions changes. A reader or
  autovacuum worker still holding a later relation fails the attempt at once
  with `55P03`, which the operator already retries. Installation changes no
  table, view, grant or row.
- **Registration.** Manifest entry after 019; production authority transition
  through-019 → through-020 (target checksum and set identity reproduced by
  `scripts/operator/v3_schema_identity.py`), with the accepted `a031c2da`
  release attested for both endpoints. Until 020 is applied, application
  promotions are refused on the schema-identity checksum and the purge
  controller refuses to plan.
- **Tests.** `tests/test_v3_purge_swap_lock_order.py`: Finder reads (the
  rehearsal's four plus the API's two-view joins in both orders) never fail
  during any of the four swaps or a swap-back; the swap's exclusive locks cover
  its view, tables and children and no `v3_meta` publication table; a reader
  holding a later relation fails an attempt in under a second with nothing
  changed; relocation refuses without the locks. Four of the five fail on 019
  alone.

## 2026-10-26 — Purge P (option B): review fixes and the copy-route rehearsal (PR #894)

Fixes for the five Codex findings on PR #894; nothing ran against production
and migrations 016/019 are unchanged.

- **Long-phase callback (4379797609).** `phase_backend` runs its identity and
  session set-up without the caller's watch callback, which now sees only a
  backend that has been set up and yielded; previously every long phase failed
  in its first callback. Proven end to end over a real psql backend on PG 18,
  including a stop request cancelling the phase (SQLSTATE 57014).
- **Copy-route rehearsal (4379797621).** `scripts/rehearsal/` runs preflight,
  copy, swap and drop per relation through the real action, measuring per
  relation copy rows/s, index-build, VACUUM FREEZE, verify and FK-validation
  time, the copy's free-space peak, WAL bytes per phase, the swap's lock hold,
  the worst concurrent Finder read stall and the temporary-file peak. Receipt
  schema `ed-finder/derived-purge-rehearsal/v3` (v1/v2 refused) seals the
  plan's `copy` block from the extrapolated copy peak. Nine crash scenarios
  replace the delete/rewrite ones. The seed records build and Search chunk
  receipts and production's planner statistics; the harness applies the whole
  manifest and the `temp_file_limit` grant. The rehearsal workflow keeps its
  runner and modes; its disk minima become 140/175 GB.
- **Workflow budget (4379797627).** `authenticate()` bounds the copy route's
  executed phases and a plan's sealed phase timeouts, not the legacy rewrite
  estimates (the committed receipt's 30,659,000 ms Search figure no longer
  refuses); the action bounds a recovered 016 rewrite `ANALYZE` itself.
- **Opportunity swap-back (4379797637).** One owner transaction restores the
  retired table's attribute options on the copy, then swaps back; the restore
  value is written to host state before every recalibration, which is now
  idempotent.
- **Resumable swap-back and swap (4379797650).** `staged`/`SWAPPED_BACK` with
  `NOT VALID` child FKs resumes in `swap-back-R`; a committed swap resumes in
  `swap-R`; `status` names both; a lost-response drop reports itself.
- Also: a competing copy backend refuses before any write; the WAL soft
  throttle measures WAL since the latest checkpoint REDO point; the copy
  watchdog's condition file is read from where the unit writes it.

## 2026-10-26 — Purge P (option B): copy-and-drop operator modes, fence and backup-wrapper reads

Operator side of the owner-accepted copy-and-drop purge
(`docs/development/v3-purge-copy-and-drop-design.md`); nothing ran against
production. Migration 019 is unchanged.

- **New protected-workflow modes** per relation (`preflight-R`, `copy-R`,
  `swap-R`, `swap-back-R`, `drop-R`, `abandon-R`) and a `complete` that reads
  019's `COMPLETED`, in `scripts/operator/lib/v3_purge_copy.py` (fixed SQL,
  reviewed per-phase `SET LOCAL statement_timeout`/`lock_timeout`, gate
  arithmetic, preflight evaluation, Finder smoke, `n_distinct` recalibration)
  and `scripts/operator/lib/v3_purge_copy_dispatch.py` (resumable copy state
  machine, per-chunk gate 2 and WAL/archiver throttle, long phases under the
  root-owned watchdog with progress polling, swap retry/backoff with the
  measured stall, F7/F12 checks). Both files join the purge script hash.
- **016's `delete-R`/`rewrite-R` disabled** (owner answer 6): removed from the
  workflow choices, refused before approval/SSH and by the action with
  `delete_rewrite_modes_disabled_by_copy_and_drop_design`; plan, authorize,
  status, `restore-services` and `abort-relation-R` stay.
- **Shared fence** (`v3_purge_state.py`, every mutator): refuses while
  `purge_copy_backup_skip()` is true or any relation is staged/swapped; an
  absent 019 ledger refuses except the schema apply whose authenticated pending
  suffix ends in 019 (`v3_production_migrate.py` `copy_bootstrap_allowed`).
- **Backup wrapper** reads `purge_copy_backup_skip()` after the 016 open-record
  read and SKIPs on exactly `t`; anything else exits non-zero. The installer
  refuses until 019 is applied. The committed wrapper's SHA-256 changed; re-run
  `v3-backup-wrapper-install` after merge (its receipt pins the new hash).
- **Watchdog** (`v3_purge_rewrite_monitor.py`) gains a copy mode (required free
  bytes per phase, WAL ceiling 2 × `max_wal_size`, owner-authenticated cancel).
- **Plan** seals a `copy` block (free space before each copy from the rehearsal
  peak proxy, reviewed bounds, a named `copy_rehearsal` hook). **Status** reports
  019's status, hours in each copy state and hours since the last successful
  backup.
- **Measured on PG 18.4 and recorded** (runbook, design §7a): function-level
  `SET statement_timeout` never bounds its own call; 019's function-level
  `lock_timeout='2s'` beats the caller's `SET LOCAL`, so the operator caps each
  swap attempt at 8 s instead; `temp_file_limit` needs
  `GRANT SET ON PARAMETER … TO v3_derived_purge_executor` (not in 019).
- Runbook `docs/operations/v3-governed-derived-purge.md`: copy route,
  preconditions (full backup before step 1 and after COMPLETED, backup
  heartbeat, the grant), the 24-hour staged/swapped rule, approvals ≈ 14–20.
- Tests: `tests/test_v3_purge_copy_operator.py` and
  `tests/test_v3_purge_copy_operator_pg18.py`; existing purge, fence, workflow
  and backup tests updated to the new contract.
## 2026-10-26 — Edge real-client address applied on production (owner-run)

The edge half of #896 is live: the reviewed `public-auth-edge.nginx.conf`
(sha256 `a1a26f42…a906`) replaced the verified-unchanged previous version
(`457d8ae3…373a`) after an in-container `nginx -t`, then a reload. The edge's
access log now records visitor addresses instead of Cloudflare's. The API half
(every rate limit keyed on the visitor) takes effect with the next release.
Recorded in `docs/operations/infrastructure-status.md`.

## 2026-10-26 — Rate limits key on the visitor, not the proxy hop (sweep S1)

Confirmed on production (owner-run, read-only): all 903 API requests in 24 h
came from the web slot's address `172.23.0.2`, so each rate limit was one
bucket for the whole site; and the public site is served by Cloudflare
(`server: cloudflare`, `cf-ray`), with Cloudflare addresses as the edge's
peers.

- **API** (`apps/api/src/config.py`): every limit now keys on
  `trusted_client_address`, the former OAuth-only helper. It accepts
  `X-Real-IP` only from a private, non-loopback peer (the web slot) and only
  when it parses as an IP; loopback and public callers key on themselves.
  `get_remote_address` is gone.
- **Edge** (`deploy/v3-production/public-auth-edge.nginx.conf`): `real_ip_header
  CF-Connecting-IP` with `set_real_ip_from` for exactly Cloudflare's published
  ranges (https://www.cloudflare.com/ips/, last updated 2023-09-28; checked
  2026-10-26), no recursion. A direct connection to the origin keeps its own
  address and cannot pick another visitor's key.

Checked locally with nginx 1.24: a spoofed `CF-Connecting-IP` from an
untrusted peer leaves `X-Real-IP` as the peer; from a trusted peer it becomes
the visitor. The API part takes effect with the next release; the edge part is
an owner-run host step after merge (copy the reviewed file over the edge's
mounted config, `nginx -t`, reload), recorded afterwards. Until the edge step,
limits key on the Cloudflare node address, which is already finer than one
site-wide bucket.
## 2026-10-26 — Sweep hardening: security headers, https share links, secret comparisons, ratings 503s

Findings S4, S6, S8 and S9 of the 2026-10-26 external repository sweep, each
confirmed against `main` and, for S6 and S8, on the live site (owner-run
read-only checks: no security headers; `og:url` advertised `http://`).

- **S8, web slot headers** (`apps/web/nginx/default.conf.template`): every
  response, including proxied API responses and errors (`always`), now carries
  `X-Frame-Options: SAMEORIGIN`, `Content-Security-Policy: frame-ancestors
  'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin` and a `Permissions-Policy` that denies
  camera, microphone, geolocation, payment and USB (the app uses none). HSTS is
  left to the TLS terminator; a full CSP comes later, report-only first.
- **S6, share links**: the web slot now forwards the edge's
  `X-Forwarded-Proto` (`map … $forwarded_proto`) instead of its own plain-http
  `$scheme`, and `_public_base` advertises `https` for every public host,
  honouring `http` only for local development hosts.
- **S9, secret comparisons**: the admin token, the OAuth `state` and the
  owner-claim token compare UTF-8 bytes through `deps.secrets_equal`, so
  non-ASCII client text is a mismatch, not a logged 500.
- **S4, ratings timeouts**: a statement or lock timeout on `/api/ratings/v4/*`
  is a retryable 503, as on the Finder routes (it was a generic 500).

Checked locally: `nginx -t` on the templated config, and a live nginx 1.24
run showing the headers on 200, 403 and 503 responses and the forwarded scheme
(`https` when the edge says so, `http` without it). Tests:
`tests/test_v3_sweep_hardening.py`; 210 passed across the auth, share, ratings
and release-contract suites. Not live until the next release.

## 2026-10-26 — Migration 019 applied to production; external review recorded

**Production (owner-approved, governed workflow).** Plan run 40338574785 reported
`pending=[019]` with no writes; apply run 40338736148 applied
`019_v3_purge_copy_and_drop.sql` and installed the through-019 schema identity.
Capability only: no payload row copied, swapped or deleted. This clears the
promotion block that #891's authority change introduced.

**Docs.** ROADMAP, CLAUDE.md and infrastructure status record the apply. The
operator-mode work now carries the 2026-10-26 external review's findings on
the copy-and-drop route (statement timeouts must be set per call by the
operator; long phases need the watchdog, gate 2 and resumability; the vector
swap's per-lock timeout must be short; `n_distinct` recalibrates at the
opportunity swap; a backup heartbeat must alert before step 1).
## 2026-10-25 — Inspect shows Ratings V4, ring hotspots and station economies

Web only. No API, migration or generated-client change: every field shown was
already served by a mounted, generation-pinned V3 route and dropped by the web
mapping.

- **Economy potential.** A new Inspect section (`SystemRatings.svelte`) reads
  `GET /api/ratings/v4/systems/{id}` and lists the seven Ratings V4 potentials,
  highest first, with confidence. Each row's "Why?" lazily reads
  `/explanation` and shows the contributing bodies (role, base, strong links,
  local score, weight), unknown evidence and specialisation
  (`RatingExplanation.svelte`). The explanation is keyed to the derived
  generation of the ratings on screen; a different publication is reported,
  never shown against older scores. A 404 reads "not in the published ratings
  yet"; other failures keep the rest of Inspect usable with a retry. Archetype
  grades are deliberately not shown: they belong to the gated Finder F4 design.
- **Ring hotspots.** The selected body's card lists each ring and belt with its
  type, reserve level and mining hotspots (`ring_signal_current`). It says "No
  hotspots" only when the source recorded an empty signal list, and "Hotspots
  not recorded" when it recorded none.
- **Stations.** A Stations section lists each station nearest first with its
  type, arrival distance, the body it is resolved to (`BODY_RESOLVED` only) and
  its catalogued economies, primary and secondary first. Shares show only when
  the catalogue has one; the Spansh import stores none. Fleet carriers, which
  can number dozens in a busy system and move at any time, sit behind a closed
  "N fleet carriers" toggle.
- **Phones.** Below 600px the ratings table drops its decorative meter, tightens
  its cells and keeps the "Explanation" header for screen readers only, so it
  fits from 375px; it scrolls inside its own box rather than the page below
  that.

Tests: facade normalisation and fail-closed validation, republish detection,
the ring/station mapping, display wording, and component behaviour (including
an open explanation not carrying over to the next system). The Inspect Product
E2E journey now waits for the ratings route, opens one explanation and saves
desktop and 375px screenshots of the section as visual evidence. The Review Lab
orrery pins the ratings route to its not-rated state.

## 2026-10-24 — Purge P (option B): migration 019 copy-and-drop capability registered

Capability only. Nothing was run against production, and 019 is **registered,
not applied**.

**`sql/v3/migrations/019_v3_purge_copy_and_drop.sql`** implements the
owner-accepted design `docs/development/v3-purge-copy-and-drop-design.md`:
schemas `v3_purge_staging` and `v3_retired`; an append-only copy
request/event ledger keyed to 016's `purge_id`; definer functions for prepare,
chunk copy (≤ 100,000 rows per transaction, keyset order, per-chunk SHA-256
digest), index build under canonical names, verify (counts, digests, chunk
receipts, FKs, catalog fingerprint), swap and swap-back (one transaction,
2 s lock timeout), FK validation, drop (`RESTRICT`), abandon and complete; a
catalog fingerprint; and read-only `purge_copy_status()` and
`purge_copy_backup_skip()`. Installation copies, swaps, drops and deletes no
payload row and changes no existing object. Prepare copies each column's
statistics target and `n_distinct` option (production's
`economy_opportunity.system_id64` carries both) and refuses before copying if
staging and live differ.

**Registration.** `sql/v3/migration-manifest.txt` registers 019 after 016.
`deploy/v3-production/target-authority.json` records the reviewed transition
from the installed through-016 identity (`d7efe689…c4e6`, set
`sha256:c274b55c…95fc`) to through-019 (`0f4a19ad…db65`, set
`sha256:70468da0…d88d`) and attests the accepted `a031c2da` release for both.
Because the authority now names the through-019 schema identity, application
promotions refuse until 019 is applied through the governed migration
workflow; that apply comes first.

**Tests.** `tests/test_v3_purge_copy_and_drop.py` (PG 18) covers the design's
§6 list; the lineage, migration-operation, deployment-authority, Search
operator and watchlist tests now pin the through-016 → through-019 transition.

**Still to do before purge P runs:** the operator modes and workflow, the
shared fence and backup-wrapper reading `purge_copy_backup_skip()`, the 1%
rehearsal, and a release carrying the new operator code.

## 2026-10-24 — Purge P: rehearsal result, owner decision, copy-and-drop design proposed

Docs and evidence only. No code, no migration and no workflow change; nothing
was run against production.

**Evidence.** Added
`docs/operations/evidence/2026-10-24-v3-derived-purge-rehearsal-receipt-run-40074011789.json`,
the 1% rehearsal receipt from run 40074011789.
- It was copied byte for byte, so its seal still verifies: `content_sha256`
  `94a522dd…73dd`, checked with
  `v3_purge_rehearsal_receipt.load_reviewed`.
- It was scanned for secrets before committing.

**`docs/ROADMAP.md`.** A new entry dated 2026-10-24 records:
- that the rehearsal passed;
- its production-scale projections: about 147 h of deletes, rewrite peaks of
  134.5–224.8 GB, and a 4.2 h Search outage that needs 267.8 GB free when about
  105 GB is available;
- that purge P as designed is impractical at production scale;
- the owner's decision: A now, B designed, C priced separately.

**`docs/development/v3-purge-copy-and-drop-design.md`** (proposed, not accepted)
describes option B:
- For each relation, copy only the published survivor rows into a table built
  from the live catalog. Build its indexes, verify counts, digests and the
  catalog, then swap it in with a short catalog-only transaction. Drop the old
  table only after verification.
- With about 105 GB free, nothing fits on the main volume. The first step needs
  267.8 GB free. A temporary tablespace on an added disk is the alternative, and
  it is priced in GB.

## 2026-10-23 — Purge rehearsal: no observer login starts while a delete runs

Rehearsal harness and tests only. No migration, no operator-code (F2d
identity) change, nothing run against production. Smoke rehearsal run
40032512857 stopped at `delete-economy-opportunity` with
`bounded_command_failed`. Most likely cause (the run's artifact could not be
read): during a measured delete the harness sampled
the batch ledger with a new `docker exec psql` observer login about every
0.3 s. 016's batch-start, batch, autovacuum-fence and relation-complete
functions refuse with `competing writing transaction` (SQLSTATE P0001) while
any other client backend of the database has a NULL `state`, and a starting
login has one. A refusal in a raw `_result` call (relation complete, fence)
surfaces as `bounded_command_failed`; inside a batch as
`purge_batch_write_outcome_unknown`. Reproduced locally at smoke scale with the
real harness (server log: `competing writing transaction` from
`purge_start_payload_batch`). Economy opportunity runs the most batches, so it
met the race first. The earlier one-percent stop at the same mode (run
39024371827, `purge_state_query_failed`) is consistent with it but not proven.

- `scripts/rehearsal/v3_derived_purge_rehearsal.py`: a measured delete opens
  one observer `psql` session before the action starts, samples the ledger
  through it, and closes it after the action exits. A dead or silent session
  stops sampling (`observer_session_failed`); it is never reopened mid-action.
  Rewrites still sample free space only.
- Tests: a delete action starts no database login while it runs (fails on the
  old per-sample logins); rewrites open none; the session is the observer
  role; a dead session refuses before the action starts.

## 2026-10-23 — Purge rehearsal re-measures the Search rewrite with published survivors (step P reopened gate 1)

Code, tests and docs only. No migration, nothing run against production, no
rehearsal dispatched. Since go-live the surviving generation
`ratings_v4_prod_p4_parallel_v1` holds about 198.5 million published
`system_search` and 198.5 million published `system_archetype` rows, but the
disposable 1% rehearsal fixture seeded none, so its `system_search`
`VACUUM FULL` peak (which admits the production rewrite) was unrepresentative.

- Fixture (`scripts/rehearsal/v3_derived_purge_seed.py`,
  `scripts/rehearsal/v3_derived_purge_rehearsal.py`): after the survivor's
  ratings base is published, the seed registers `system_search`
  (`v3-system-search-2`) and `system_archetype` (`v3-archetype-4`) products,
  writes one synthetic row per surviving system into each (guards,
  constraints and 011's partial ranking indexes active), marks them
  `READY`/`VERIFIED` and publishes both in one transaction through 015's
  `publish_derived_product`, which writes the audit rows. It then proves the
  products, audit rows and `v3_app` views. At `one_percent` that is 2,000,000
  survivor Search rows and 2,000,000 survivor archetype rows beside the
  unchanged targets (2,000,000 `opt1` Search rows and the existing ratings
  payload).
- Measurement: after `complete`, a survivor-only `VACUUM (FULL, ANALYZE)` of
  the disposable `system_search` separates the governed rewrite into survivor
  and target shares (`per_relation.system_search.survivor_target_split`), each
  extrapolated by the recorded proportion, with the 1.5× margin and 100 GB
  floor giving `required_free_bytes_before_rewrite`. The plan carries the
  larger of the governed and survivor-only peaks.
- Receipt validation (`scripts/operator/lib/v3_purge_rehearsal_receipt.py`):
  schema `ed-finder/derived-purge-rehearsal/v2`. It refuses `v1` receipts, a
  survivor population other than the expected one (zero included), a missing,
  forged or unbound split, and synthetic survivor rows narrower than production
  (about 440.7 bytes per row; the local PostgreSQL 18 smoke seed compacts to
  about 555). `gate_10_crash_rehearsal_passed` keeps its existing conditions,
  and the production workflow's rehearsal authentication (scale, crash gate,
  code identity) is unchanged.
- The rehearsal plan now runs the production survivor proof
  (`published_survivors(..., require_published=True)`) in
  `scripts/operator/lib/v3_generation_purge.py`, because its fixture now
  publishes both products.
- Docs: runbook "P2d rehearsal" and the survivor-proof note.
- F2d operator-manifest file changed: `scripts/operator/lib/v3_generation_purge.py`
  only (the harness, seed and receipt module are not in the manifest). The
  operator-code identity changes from
  `0f0a299176cdbb6d8e50c31f5a373b2f077311f0ec4e05411178d6664e25545e` to
  `ba5eb045687e2c74ece8f5b634851f43a755cba781334c2fbf3bb0af4438edb2`; it
  ships only through a new governed app release and attestation. The purge
  script identity and the rehearsal harness identity also change, so the
  `one_percent` rehearsal must be dispatched on the `main` that carries this
  change.

## 2026-10-23 — Governed purge (P) readiness: postmaster binding, rehearsal transport, archetype survivor proof

Code, tests and docs only. No migration (applied `016` is unchanged), nothing
run against production, no rehearsal started. After go-live (publish run
39933842811) the read-only purge `status` run 39962807193 succeeded, but `plan`
run 39963522021 stopped on `data_directory_unresolved`.

- Postmaster start binding (`scripts/operator/lib/v3_generation_purge.py`):
  `postmaster.pid` line 3 may now be at most 5 seconds **before**
  `floor(pg_postmaster_start_time())`, never after. Production read 1792438533
  from the file and 1792438534 from SQL. The PID, working-directory and PGDATA
  checks are unchanged; receipts record `postmaster_start_binding`.
- Rehearsal figures in the protected workflow
  (`.github/workflows/v3-production-derived-purge.yml`,
  `scripts/operator/v3_production_purge_workflow.py`): new `rehearsal_run_id`
  and `rehearsal_sha256` inputs, required for `plan` and refused otherwise. The
  successful `one_percent` rehearsal run's `rehearsal-receipt.json` is
  authenticated (run provenance, seal, SHA-256, crash gate, scale, code identity),
  staged and passed to the action's existing `--rehearsal-receipt` plan options.
  `authorize` (workflow before SSH, and the action) now refuses a plan without
  the reviewed one-percent binding, because authorization binds the plan to
  every later phase.
- Published archetype survivor proof (`v3_generation_purge.py`,
  `v3_purge_delete.py`, `v3_purge_rewrite_dispatch.py`): applied `016`'s
  `purge_snapshot()` covers only the four rewrite relations (so the published
  Search count is already frozen and rechecked). The plan now also freezes the
  exact `parallel_v1` `system_archetype` row count and both published product
  manifests (`reviewed_plan.published_survivors`; production requires both
  products published with rows equal to `expected_rows`), and authorize,
  verify, complete, every delete boundary and every rewrite (before any fence,
  after `VACUUM`, and in recovery of a committed rewrite) compare a fresh read
  with it. Drift is an integrity stop.
- The protected source bundle now also carries the three rehearsal harness
  files and the 2026-10-10 lifecycle receipt, which the remote plan's
  rehearsal-receipt validation reads.
- Docs: runbook (postmaster tolerance, rehearsal inputs, survivor proof, the
  stale "amended, unapplied 016" line), design §1.2, §1.3 and §4.3, and the
  rollout-state "As of 2026-10-04" line are marked superseded with current facts.
- F2d operator-code identity changes (purge files are in
  `deploy/v3-production/f2d-operator-code.txt`; the manifest is unchanged). The
  new identity ships only through a new governed app release and attestation.
  The rehearsal receipt binds the purge script identity, so the one-percent
  rehearsal must run on code carrying this change.

## 2026-10-24 — Record owner-run SSH and runner hardening (prod and Contabo)

Docs only. `docs/operations/infrastructure-status.md` records the owner-run host
changes of 2026-10-24: key-only SSH on `ed-finder-prod` and on Contabo (a
`00-hardening.conf` drop-in that outranks `50-cloud-init.conf`), and a
`needrestart` override so daily updates no longer restart the GitHub runners
mid-job (the cause of the cancelled 1% purge rehearsal run 40053756082),
and fail2ban's `sshd` jail on both hosts.

## 2026-10-23 — Owner decisions: the Finder screen

Docs only. `docs/ROADMAP.md` records the owner's 2026-10-23 decisions on the
Finder screen (own V2-style page, map on demand, best-first default, grade key,
colony-type picker with "Any type", Clear and descriptions, the V2 body-filter
groups) and on combining a colony type with body filters (anchored: after purge
P; galaxy-wide filter-first path: later), plus the 15 s API timeout risk near
the galactic core. No step order or gate changes beyond the recorded reversal
of F2d question 9 for anchored searches.

## 2026-10-23 — Finder published (go-live, step 9′)

Owner-approved `publish-finder-products` run 39933842811 published both Finder
products on `ratings_v4_prod_p4_parallel_v1` at 2026-10-23T09:45:08Z; all 80
plan-probe statements passed and the live verification served results with the
expected identities. Docs only:

- `docs/operations/evidence/2026-10-23-v3-finder-publication-receipt-run-39933842811.json`:
  the full, sealed publish receipt (its nested `content_sha256` seals verify).
- `docs/ROADMAP.md` and `CLAUDE.md`: status — the Finder is live; purge P is the
  next gated step.

## 2026-10-23 — Third F2d release (`a031c2da`) accepted in production

Owner-approved preflight (run 39925556950) and promotion (run 39925665010)
accepted release run 39921473982, source `a031c2da` (PRs #877 and #878), to
active slot green at 2026-10-23T08:35:49Z. App-only: no migration, no database
writes, protected resources unchanged; the `0dddc78d` backend is the recorded
rollback artifact and `f667bb4d` stays the minimum schema-compatible image.

- `deploy/v3-production/target-authority.json`: `observed_runtime` and
  `accepted_release_schema_compatibility` now bind the new release (images,
  manifest checksum, run ids; ranking and F2d operator-code identities
  unchanged; rollback targets gain the new backend).
- `docs/operations/evidence/2026-10-23-v3-production-promotion-receipt-run-39925665010.json`:
  the accepted promotion receipt.
- `docs/ROADMAP.md`, `docs/operations/v3-production-application-release.md`,
  `CLAUDE.md`: status lines. The ROADMAP entry also records why the first
  `publish-finder-products` attempt (run 39808363037) was refused with nothing
  committed (plan-probe statement 72 timed out on the 0dddc78d SQL).

## 2026-10-22 — Finder ranking SQL: generation-pinned windows that pass the F2d plan probe

API query SQL and tests only. No migration, no `deploy/` or `scripts/operator/`
change, no response-shape change; the F2d operator-code identity is unchanged
(`c26d23d0…6279`). It takes effect only through a new governed API release.

- Why: the owner-approved `publish-finder-products` run 39808363037 was refused
  with nothing committed. Plan-probe statement 72,
  `galaxy_wide_development_page_24`, hit the 60 s statement timeout under
  `force_generic_plan`: the galaxy window read `v3_app.system_archetype_summary`,
  whose generation arrives only through the view's join, so
  `system_archetype_summary_weighted` could not supply the ORDER BY and
  PostgreSQL sorted the whole ~198.5M-row generation. Statements 73–79 never ran.
- `apps/api/src/ranking/ranking_sql.py`: every fenced view read now also names
  the current generation as an InitPlan constant
  (`… = (SELECT derived_generation_id FROM v3_meta.current_derived_generation
  WHERE singleton)`); the views keep the full PUBLISHED/READY/published fence.
  The galaxy and picked windows are now index-ordered `Limit → Index Scan`.
  Shapes the frozen probe would also have refused are fixed: the picked page
  fetches the final row from `v3_derived.system_archetype picked` (a view's
  table never shows the alias `picked`) and sorts only the page rows; picked,
  galaxy and nearest-first counts take the sentinel over the same ordered
  window their page uses (parallel workers no longer overshoot it, and a
  literal 10,001 bound gives generic plans a known Limit); the nearest-first
  count orders by search columns so the archetype probe runs after the
  incremental sort; the score-ordered radius page walks candidates through the
  GiST index (`LIMIT NULLIF($n, $n)`, always LIMIT ALL).
- Results are unchanged: 464 old-vs-new comparisons (pages and counts, every
  filter kind, offsets to 9,990) on a 300,000-system, two-search-generation
  PostgreSQL 18 database returned identical rows in identical order.
- `tests/test_v3_finder_galaxy_window_plan_pg18.py` (Finder derived-data lane):
  seeds that shape, imports production-scale statistics with
  `pg_restore_relation_stats` (198.5M archetype rows, 397M search rows), and
  runs all 80 generated statements through the frozen `run_plan_probe` inside
  an uncommitted product-publication transaction. All 80 pass; the released
  statement 72 reproduces the whole-generation sort and fails. A third test
  records a frozen-probe boundary: if the one-page `v3_meta` tables are
  analyzed, PostgreSQL seq-scans them and `anchored_candidate_gist_only`
  refuses statements 78–79 whatever the ranking SQL.

## 2026-10-21 — V3 EDDN station-sighting worker and `v3_observe` proposal (code only)

Code and tests only. Nothing is deployed, scheduled or applied: no
`deploy/`, `scripts/operator/`, deploy workflow, `sql/v3/migration-manifest.txt`
or `sql/v3/migrations/` change, and the F2d operator-code identity is unchanged.

- `sql/v3/proposals/017_v3_observe_station_sightings.sql` (UNREGISTERED
  proposal): new `v3_observe` schema; append-only, change-only
  `station_sighting` history (market id, system id64, station name/type,
  economies JSONB, services, landing pads, optional Spansh body, source
  `spansh|eddn`, source/gateway/observed/first-seen times, state SHA-256; no
  uploader column), bounded by CHECK constraints; a `station_current` view per
  `(source, market_id)`; a source binding to two new `v3_source.source` rows
  with `INTERNAL_USE`, non-distributable rights policies; and the restricted
  NOLOGIN `v3_station_observer` role (SELECT/INSERT only).
- `apps/eddn_v3/`: a small CPython 3.14 worker (`psycopg` + `pyzmq`, own
  `pyproject.toml` and frozen `uv.lock`) that subscribes to the EDDN relay,
  keeps only `journal/1` `Docked` (no fleet carriers, no Legacy), validates and
  bounds every field, and writes a row only when a station's state hash
  changes — batched, parameterised, one transaction per batch, under
  `SET ROLE v3_station_observer`. `/metrics` and `/healthz` follow the #864
  liveness pattern; N consecutive failed flushes exit the process. The
  `uploaderID` header field is never read, stored or logged. The sighting
  model and `record_sightings` writer are source-agnostic for the later
  Spansh loader. A non-root Dockerfile is included but wired into nothing.
  This worker is the EDDN observation path only; it is not journal-import
  automation or canonical promotion.
- Tests: `tests/test_eddn_v3_worker.py` (unit lane) and
  `tests/test_eddn_v3_station_sightings_pg18.py` (Finder derived-data PG18
  lane, discovered by its `RATINGS_V4_VALIDATION_DATABASE_URL` reference).
  `tests/test_v3_python_runtime_validation.py` now accepts the second uv lock.
- Post-go-live, each with the owner's go: register as migration 017, add the
  worker to the production deploy authority, grant/verify the role on the
  application login, make the worker refuse to run during the governed purge,
  then the first run.
## 2026-10-21 — Spansh delta measurement (canonical-refresh study step S1)

Repository tooling only: no production access, no secrets, no database, no
migration, operator, deploy or F2d-frozen file. The F2d operator identity is
unchanged.

- `apps/importer/src/spansh_delta/`: a bounded-memory streaming parser for
  Spansh full-detail dumps (`galaxy_1day` / `_7days` / `_1month`, same schema
  as `galaxy.json.gz`). The default parser reads Spansh's one-system-per-line
  layout and falls back to `ijson` for any other layout; truncated or corrupt
  files fail closed and only an EOF read yields a receipt (size, SHA-256).
  Each system is mapped through the frozen `v3_spansh` adapter and COPY
  contract (imported, not edited) to the V3 canonical rows, provenance removed.
  A material-change classifier compares those rows with base canonical rows
  (`new` / `changed` / `unchanged`, with changed tables and columns), so
  faction, population and market churn that V3 does not store never admits a
  system. Two policies: `strict` (every stored column) and `stable` (ignores
  the orbital position at scan time); fleet carriers can be excluded.
- `scripts/dev/measure_spansh_delta.py`: streams one dump and writes JSON stats
  (systems, bodies, fixed stations and fleet carriers separately, canonical
  rows per table, bytes, update-time distributions, a timestamp touch proxy),
  plus a 40-byte-per-system digest index. Given the previous night's index or
  file it reports the overlap and how many repeat systems really changed.
- `.github/workflows/spansh-delta-measure.yml`: GitHub-hosted, `contents: read`,
  no secrets. On demand (`galaxy_1day`, `_7days` or `_1month`), plus a 04:17
  UTC nightly schedule that is skipped unless the repository variable
  `SPANSH_DELTA_NIGHTLY` is `enabled` (set only once decision D5, Spansh's
  terms for recurring downloads, is resolved); ETag-conditional download, stats artifact kept 30 days, the
  digest index carried night to night in the Actions cache.
- `docs/development/spansh-delta-measurement.md`: how to run it and read the
  stats; seven nights of results feed the delta-layer design (S3).
- `tests/test_spansh_delta.py`: uses the committed real fixture. Against the
  published 2026-08-24 base, 9 of 12 systems differ under `strict` but only 3
  under `stable` (real signal changes); the other 6 differ only in orbital
  position. `tests/test_ci_stall_detection.py` lists the new workflow.
## 2026-10-21 — Inspect, share preview and travel heatmap read V3 data

Inspect (`/inspect?system=<id64>` and the Explore system pop-up), the share
link preview (`/s/{id64}`, `/api/share/og/{id64}`) and the map's "Show my
travel heatmap" read V2 relations (`systems`, `ratings`,
`mv_archetype_rankings`, `exploration_visits`) that do not exist in V3
production, so on the live site they very probably failed. A new PG18 test
reproduces it: against the V3 production database shape, the legacy
`GET /api/system/{id64}` raises `UndefinedTableError`. This is a visual
change: Inspect needs visual validation before promotion.

- **Inspect** (`apps/web`): `getSystem` in the API facade now reads the
  generation-pinned V3 canonical routes `/api/v1/systems/{id}`, `/bodies`,
  `/rings` and `/stations` in parallel and maps them to a new V3-shaped
  `SystemDetail` (`systemDetailFromV3`). The four reads are fenced by the
  published generation identity (`/api/v1/generation`) read before and after
  them, so a read that straddles a publication (a 404 included) is retried
  once and then fails closed with a retryable 503 instead of mixing
  generations. Only ACTIVE bodies, rings and stations are shown; a system that
  is MISSING_CANDIDATE or RETIRED gets an explicit "Catalogue status" row. The page shows coordinates, the main
  star's catalogued class, body/station counts and the catalogue date, and
  states plainly that population, economy, security, allegiance, government
  and development fit are **not available yet** rather than leaving them
  blank. Body selection uses the unique Frontier BodyID (a body without one is
  counted but not selectable); the body card shows class, arrival distance,
  radius (km), rings, belts, landability and body signals. 404, and 422 for an
  id64 beyond the catalogue's signed 64-bit key, show "System not found". The
  3D system map takes V3 classes; star colouring uses a presentation phrase
  derived from the catalogued spectral class (marked `DERIVED`). The canonical
  URL and heading-focus behaviour are unchanged.
- **V3 body route** (`routers/v3.py`): `BodyV1` gains `is_main_star`,
  `spectral_class`, `luminosity_class`, `is_landable`, `lifecycle_state` and
  `signals` (from the generation's `body_signal_current`); `StationV1` gains
  `lifecycle_state`; every canonical read in the router is bounded at 5 s as a
  whole (connection acquisition included), so a saturated pool is a 503; the generation resolver is public as
  `current_canonical_generation`. Both TS clients regenerated.
- **Share preview** (`share_router.py`): the bot page and the PNG card read the
  published canonical generation through the same resolver (readonly pool;
  the generation resolution and the system read, connection acquisition
  included, are each bounded at 5 s). Unknown system → 404 (the bot page drops `og:image`);
  nothing published or a failed read → 503. The card shows only canonical
  facts (name, coordinates, catalogued body count): there is no V3 single
  score/rationale. The bot page pins its `og:image` to the generation it
  described (`?generation=<id>`, an immutable 7-day card; an unknown or purged
  generation is a 404); an unpinned card follows the current publication and
  is publicly cached for one hour. The Redis key is now `og:v3:{generation_id}:{id64}` through
  the same bounded `deps` helpers. Humans get a relative redirect to
  `/inspect?system=<id64>` (previously an absolute `/#system/<id64>` built
  from `X-Forwarded-Host`, which landed on the home page) with no database
  read. The OG absolute origin accepts only a plain `X-Forwarded-Host`
  hostname[:port] and an `http`/`https` proto (else `https://ed-finder.app`),
  and page text is escaped with `html.escape`.
- **Travel heatmap**: new `GET /api/v1/journal/travel-heatmap`
  (`getV3JournalTravelHeatmap`) in the V3 journal router — sign-in required
  (401), owner-scoped by the session account like the other journal routes,
  `Cache-Control: private, no-store`, 60/minute. It aggregates the account's
  `FSDJump`/`CarrierJump`/`Location` `StarPos` from
  `v3_private.journal_event` server-side (per system up close, per cubic cell
  further out, same thresholds as the V2 contract). Visits are jump arrivals;
  `Location` (deduplicated by position, not time) only proves presence, so a
  Location-only system counts as at least one visit. The route validates
  every coordinate and identity in SQL, and is bounded (1,000,000 travel
  events → explicit 503, 5 s timeout over connection acquisition and query,
  ≤ 20,000 points with `truncated`). No migration. The map's
  toggle uses it (query keyed by account; the private layer is hidden as soon
  as the query errors, e.g. an expired session) and shows honest states: sign-in
  prompt, account-check retry (a failed session check is not "signed out"),
  zoom hint, empty view, retryable error. The V2 `completion_state`
  is gone from the commander-history layer (V3 does not compute it).
- Tests: `tests/test_v3_inspect_share_travel_postgres.py` (fresh PG18 V3
  database, runs in the `finder-derived-data` lane); share unit tests and the
  V2-lane integration tests updated; Vitest and the map-review-lab Cypress
  mocks use V3 shapes; Product E2E adds a direct Inspect visit against the
  seeded V3 fixture that fails if `/api/system/*` is called.
- Follow-up (not in this change): the production release smoke checks still
  open only `/`, `/api/health`, `/api/v1/auth/session` and `/openapi.json`;
  one real `/inspect?system=…` page should be added there.

## 2026-10-21 — Mega Guide v2.3.0 reference text, mechanics and CRE/CPE audits, owner decision

Docs only; no `apps/`, workflow, script, operator, deploy or frozen-ruleset
change.

- `docs/reference/colonisation/sources/mega-guide-v2.3.0/`: the Elite
  Dangerous Colonization Mega Guide (CMDR Mechan with contributors), version
  2.3.0 with the 2.4.0 WIP revision row, committed as an unmodified
  `pdftotext -layout` extraction of the owner-supplied 121-page PDF, under the
  guide's CC BY-SA 4.0 licence. The README quotes the guide's attribution and
  Frontier non-endorsement notice, records the guide's caveat that the 4.2.2.0
  nerf is not incorporated, lists the SHA-256 of the PDF (not committed, 95 MB)
  and of the text, and states that images and image-only tables are absent and
  that Mega Guide page numbers in this repository are PDF page numbers.
  `.gitattributes` marks the text `-text` so its checksum stays stable.
- `docs/reference/colonisation/` README, `source-inventory.md` and
  `source-priority.md`: the Mega Guide is now recorded as committed, CC BY-SA
  4.0 with attribution, inspected version 2.3.0 (2.4.0 WIP) on 2026-10-21. The
  inventory row also notes that the "Colonization Mega Guide" URL listed in
  `docs/development/ratings-v4-mechanics-evidence.md` could not be retrieved,
  so whether it is CMDR Mechan's guide is unverified; that file is hash-pinned
  by the Ratings V4.0 freeze manifest and is left unchanged.
- `docs/development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md` and
  `docs/development/evidence/2026-10-21-cre-cpe-utilisation-audit.md`: the two
  read-only audits of 2026-10-21, committed as dated evidence (not execution
  authority) with local paths removed.
- `docs/ROADMAP.md`: owner decision 2026-10-21 — publish the Finder on the
  frozen Ratings V4.0 / `v3-archetype-4` rules as attested, and address the
  Mega Guide conflicts in a versioned Ratings V4.1 as the first post-go-live
  mechanics work. The same entry gives the CRE/CPE audit headline and records
  the owner's 2026-10-21 decisions on it (decided, not yet implemented): D1,
  the CRE becomes a versioned, machine-readable rulebook that ed-finder reads;
  D2, the CPE becomes a bounded module inside ed-finder with a boundary test;
  D3, the first Plan feature is a construction-point budget and port-order
  calculator, and until then `/plan` is to say plainly that planning is being
  rebuilt; D4, the journal research export is to be paused (the route is still
  mounted today). No step order or gate changes.
- `docs/development/cross-repo-workspace.md`: the planning-engine working rules
  now follow D2 (CPE as a bounded module in `ed-finder`).
- `assets/PROVENANCE.json`, `THIRD_PARTY_NOTICES.md`, `assets/README.md`: the
  guide text is registered with its rights chain (CC BY-SA 4.0, Frontier-derived,
  `noncommercial_only`) and SHA-256, so the CI asset-provenance guard fails on
  any drift; the manifest `audit_date` moves to 2026-10-21 for this one entry.

## 2026-10-21 — Journal: keep repeat dockings and read back station history

Manual journal import only; no migration, no scheduler/automation, no
canonical promotion, no research export (still paused), no web UI, no
workflow, operator or deploy change.

- `apps/api/src/edfinder_api/journal/store.py`: verified (commander-owned)
  imports now key `Docked` like `Scan` — the V3.0 semantic key
  (`SystemAddress`, `StationName`) plus `RecordHash` (journal line SHA-256)
  and `ObservedAt` (UTC event time), via the new `OBSERVATION_HISTORY_EVENTS`.
  A second docking at the same station is now kept instead of being dropped
  as a duplicate; replaying the same line stays idempotent. Unverified imports
  keep the plain key. Existing rows are not rewritten.
- New owner-scoped read route `GET /api/v1/journal/station-observations`
  (`listV3JournalStationObservations`): per station (MarketID), newest station
  first, the time-ordered Docked observations (system, station name/type,
  economy mix with proportions, services, government, allegiance, distance).
  Bounded (`limit` 1–100, `offset` ≤ 100,000, `max_observations` 1–200,
  optional digits-only `market_id`), parameterized, reads only
  `v3_private.journal_event`, and de-duplicates the legacy-key copy of a
  re-imported line by `source_record_hash`. Generated TS clients regenerated.
- `docs/colonisation-redesign/in-game-experiment-recording.md`: plain-language
  steps for recording a before/after colonisation test, how to read it back,
  how it feeds CRE (manually), and why the five colonisation journal events
  (verified against the v38 journal manual and the community journal schemas)
  are not kept yet: the event-type CHECK in migration `005` needs migration
  `017`, which follows after go-live.
- `docs/development/journal-commander-contributions.md` records the identity
  contract change; tests: store key unit tests, route contract/bounds tests,
  and a fresh-PG18 before/after, scoping, pagination and legacy-dedupe test.

## 2026-10-21 — Finder F4b prerequisites: owner answers and Product fixture-output contract

Docs and tests only; no `apps/api`, `apps/web`, workflow, operator or deploy
change.

- `docs/superpowers/specs/2026-10-10-v3-finder-f4-archetype-ui-design.md`:
  section 9 records the owner's 2026-10-21 answers. Question 1 — yes: F4b adds
  a **Clear fit** / **Close fit** classification label (driven by
  `archetype_confidence`) beside the Primary/Secondary line, in
  selected-archetype mode only, never inside the evidence badge; the “close”
  threshold is set later from published production data. Question 5 — yes:
  the slice 1c latency budgets are accepted unchanged, and a miss is reported
  with measured numbers rather than loosening them. Questions 2–4 stay open
  (not blocking F4b). Section 1 notes F4a (#870); sections 3, 5 and 7 point
  at the answers.
- `tests/test_seed_cypress_v3_generation.py`: the Product fixture-output
  contract F4a's section 7/8 assigns. It seeds the committed three-system
  corpus through the real Cypress seed, then pins every stored wide-row
  score/tier/fit-confidence/weighted key, the summary (primary, secondary,
  Best Colony Potential, best tier, classification confidence, completeness),
  the search evidence, every archetype's `min_score=60` page through
  `_archetype_rankings_v3`, the Flexible one-row pages at offsets 0/1/2, and
  Explore's Any request through `local_db_search_v3`. Flexible at B is
  confirmed as the only floor admitting all three, in the order V3 Lossless
  Reach (100/S) → Achenar (100/S) → HD 38179 (75/B). It runs in the Finder
  derived-data lane, which discovers the module by its
  `RATINGS_V4_VALIDATION_DATABASE_URL` reference.

## 2026-10-21 — Finder F4a: typed ranking foundation (default-off, no visible change)

PR F4a of `docs/superpowers/specs/2026-10-10-v3-finder-f4-archetype-ui-design.md`
(section 8). Code-only, fixture-validated, `apps/web` only. No rendered
component, picker, card or Product E2E opt-in is added; the build gate
`VITE_FINDER_F4_ENABLED` defaults to off everywhere and no build sets it.

- `apps/web/src/lib/config.ts`: central fail-closed feature config;
  Finder F4 is enabled only by the exact value `'1'`.
- `apps/web/src/lib/features/explore/archetypes.ts`: canonical eight-key V3
  archetype metadata, S/A/B minimum-tier → 88/76/60 floors (C/D rejected,
  B default), tier labels, and mode-specific Evidence/Fit confidence wording.
- `apps/web/src/lib/features/explore/ranking-state.ts`: pure
  `FinderRankingState` and URL codec (`archetype`, `min-tier`, `page_size`
  1–50, `offset`; weights reserved until slice 2), one exclusive 10,000
  offset ceiling applied from the URL before any request, and request
  selection whose rankings branch is unreachable while the gate is off.
- `apps/web/src/lib/api/client.ts`: `getArchetypeRankings` facade over the
  generated operation (`page_size` → wire `limit`); lossless page envelopes
  for both routes (`total_is_capped` for Any, API-owned `is_truncated` for
  selected); every row carries `score_kind`, selected archetype, distance
  reference, confidence/completeness and all seven `ranking_provenance`
  fields. A selected fit never enters generic `archetype_score`.
- `apps/web/src/lib/api/query.ts`: rankings query key; the Any key now also
  carries the committed anchor's `{ id64, name }`.
- Pin/compare snapshots persist the ranking identity; legacy snapshots decode
  unchanged and read as unknown mode with null provenance.
- Explore, in a default-off build, replace-strips F4 URL parameters
  (preserving `selected`, `system` and unrelated parameters) and keeps
  today's exact local-search request.
## 2026-10-21 — F3 slice 2b: `/api/search/galaxy` and `/api/search/cluster` on the V3 projections

The last two Finder routes still reading the legacy V2 relations are
repointed, following the slice-1/2 pattern (one REPEATABLE READ snapshot per
request, `local_search._current_derived_generation` as the generation pin and
migration-015 product gate — 404 without a PUBLISHED generation, 503 until
both Finder products are READY and published — request validation before any
database access, parameterized generation-pinned SQL, no legacy relation).

- **`POST /api/search/galaxy`** → `local_search.local_db_galaxy_search_v3`:
  on V3 the galaxy search *is* the galaxy-wide Any-mode window of the ranked
  search (`local_db_search_v3` with `galaxy_wide=true`): same bounded access
  path (top 10,000 by `weighted_potential`), same ranking profile, same
  `SearchResponse` envelope with the ranking-identity block and the
  sentinel-bounded total. Legacy request features with no V3 projection are
  rejected with 422 before the generation pin rather than silently dropped
  (slice-1 rule): a concrete `economy` (no per-economy potential projection;
  `economy="any"` ranks by best colony potential), `min_score > 0` (a hard
  filter on a galaxy-wide Any request, refused by the F2d bounded-access
  contract), an explicit `include_colonised=false`, and any undeclared field
  such as a legacy `galaxy_region_id`. **Flagged shape change:** the legacy
  route silently forced uncolonised-only results; `v3_app.system_search`
  carries no population column, so the V3 galaxy search ranks every system in
  the published generation. `GalaxySearchRequest` now declares the optional
  `include_colonised` field (forwarded to the validator, so `false` is a 422
  through the public route rather than silently dropped) and is
  `extra='forbid'`; both generated TypeScript clients are regenerated (one
  additive optional field). The route now declares
  `response_model=SearchResponse` (the envelope it actually returns, as
  `/api/local/search` does), so FastAPI validates it and the generated clients
  type the 200 body instead of `unknown`.
  `GALAXY_CACHE_VERSION` bumped `v4` → `v5`; the key is scoped to the ranking
  identity and the pinned generation like `/api/local/search`.
- **`POST /api/search/cluster`** → `local_search.local_db_cluster_search_v3`
  — **fail-closed, flagged data gap.** The legacy read over the V2
  `cluster_summary` macro-grid (per-anchor counts of economy-viable systems
  in a 500 LY bubble) plus `systems`/`ratings` slot detail is deleted. Its V3
  successor is the independent cluster product of migration 004
  (`v3_spatial.cluster_run` → `cluster` → `cluster_member`, decision doc §8),
  but no Finder cluster builder exists, no run has ever been published, and
  the per-economy viability summary the `ClusterResult` fields need is a
  builder-defined `cluster.summary` contract that has not been designed. The
  route validates the request (422 — including a partial `reference_coords`,
  which is no longer collapsed to "no anchor"), pins the published generation behind the
  Finder product gate, reads the Finder-owned (`owner_domain='finder'`)
  `cluster_run` state for that generation and answers 503 naming exactly what
  is missing (run states, or a published run with no read contract). It never
  fabricates clusters from a request-time galaxy scan (decision doc §12). The
  cluster route carries no cache any more. Request/response models unchanged.
  In production both routes already failed (the V2 relations do not exist in
  V3 prod); the difference is an intentional, named 503 instead of an
  `UndefinedTableError`.
- `apps/api/src/local_search.py`: `local_db_galaxy_search`,
  `local_db_cluster_search` and `_resolve_slot_matches` deleted; the legacy
  `local_db_search` and its SQL helpers are retained only as the
  route-unreachable legacy reference (its record builder serves
  `local_db_system`; the data-trust/population contract tests pin it). The F3
  section comment and the module header now describe this state; the "ONE
  search implementation" rule in `routers/search.py` is restated as per route.
- Tests: new `tests/test_search_slice2b_v3.py` (pure request-validation
  tables for both routes; PG18 fixture tests — galaxy ordering/identity/paging
  equals the local-search galaxy-wide window, 404 without a published
  generation, 503 until both products are published, cluster 503 naming the
  missing/unpublished/published-without-contract Finder run; whole-module AST
  string-literal guard for `routers/search.py`). `test_ranking_identity_and_
  no_legacy.py` extends its scoped guard to the new functions and routes, adds
  `cluster_summary` to the forbidden terms and the `routers/search.py` literal
  walk. Integration tests updated for the new read paths; `tests/test_cluster_
  region_scope.py` (legacy slot resolver) removed; cache-version pin updated.
## 2026-10-21 — API silent-failure follow-ups: status reason codes at the producer, alert rules for the #864 series

Closes the two items PR #864 deferred. No request/response schema changed
(`app.openapi()` is byte-identical to `main`); nothing under
`scripts/operator/`, `deploy/`, `.github/` or
`deploy/v3-production/f2d-operator-code.txt` was touched.

- **Bare Redis calls (item 4 follow-up):** re-verified on current `main` —
  `apps/api/src/routers/archetypes.py` has had no Redis layer since #862
  (every response is pinned to the generation resolved inside its own
  REPEATABLE READ snapshot) and `apps/api/src/local_search.py` never
  references a Redis client. The only direct client calls left in
  `apps/api/src/` are the timeout-guarded helpers in `deps.py` themselves.
  Nothing to route through `cache_get`/`cache_set`; no code change.
- **`local_db_status()` reason text (item 6 follow-up):** the producer in
  `apps/api/src/local_search.py` now classifies the swallowed exception **by
  type** (`helpers.status_failure_reason_code_for_exception`) into the same
  bounded set `routers/meta.py` introduced in #864 — `db_timeout`
  (`TimeoutError`, `asyncpg.QueryCanceledError`), `db_schema_missing`
  (undefined table/column/function/object, invalid schema), `db_unavailable`
  (`asyncpg.InterfaceError`, connection-class errors, too-many-connections,
  `ConnectionError`/`OSError`) or `db_error` — and returns only that code; the
  exception class and raw text go to the server log. The code set now lives in
  `apps/api/src/helpers.py` and `meta.py` imports it; `meta.status_failure_reason_code`
  passes a producer code through unchanged and keeps its text heuristics as
  defence in depth. The failure branch is still never cached.
- **Alert rules for the #864 series:** `config/prometheus_rules.yml` gains
  `EddnSimulationIngestFlushFailing` (flush-failure rate > 0 for 10 m, warning),
  `EddnSimulationIngestFlushBreakerNear` (consecutive failures > 0 and
  ≥ threshold − 1, warning — the positive guard matters at the allowed
  threshold of 1), `EddnSimulationIngestNoSuccessfulFlush` (no successful DB
  flush for 30 m while the ingest is enabled, has flushed at least once, and has
  *started* a non-empty flush since that success — so a healthy relay that
  simply carries no relevant events is not a failure; critical),
  `SseBridgeUnhealthy` (bridge state ≠ subscribed for 10 m, warning) and
  `SseBridgeReconnecting` (reconnect rate > 0 for 15 m, warning), in the file's
  existing style. To make the threshold and the enabled condition expressible
  in PromQL, `/api/metrics` exports two config gauges:
  `ed_finder_eddn_simulation_ingest_enabled` (0/1) and
  `ed_finder_eddn_simulation_ingest_max_consecutive_flush_failures` (the
  clamped breaker threshold), plus
  `ed_finder_eddn_simulation_ingest_last_flush_attempt_timestamp_seconds`
  (set in `eddn_client._flush_batch` when a non-empty batch starts flushing,
  before a hung write would block) so "attempted since the last success" is
  observable. **Scope note:** `config/prometheus_rules.yml` and the Grafana
  dashboard are mounted only by the root `docker-compose.yml` `monitoring`
  profile (repository/opt-in tooling); no current V3 production authority
  deploys a Prometheus/Grafana stack, and this entry does not create one —
  wiring monitoring into the governed V3 host is a separate owner decision. `config/grafana/dashboards/ed-finder.json` gains
  four matching panels (flush failures + consecutive/threshold, last-successful-flush
  age, bridge state with value mappings, reconnects/min). The rules file was
  validated with `promtool check rules` and a fire/no-fire `promtool test rules`
  scenario per alert using promtool 3.13.2 (the pinned Prometheus image version).
- Tests: `tests/test_local_db_status_reason_codes.py` (type classification,
  producer payload, log-only raw text, end-to-end route) and
  `tests/test_monitoring_flush_failure_alerts.py` (each rule's expression /
  `for` / severity, file order, the fresh-process and disabled guards, the two
  config gauges, dashboard panels and grid non-overlap, `promtool check rules`
  when a binary is on PATH); `tests/test_eddn_simulation_ingest_metrics.py`
  re-anchored to the new rule order.

## 2026-10-20 — Authority-document staleness sweep (docs only)

No code, test, workflow, script or operator change. Corrects current-authority
statements overtaken by this week's merges and operations:

- `CLAUDE.md` and `docs/ROADMAP.md` ("Programme status — 2026-09-26", the
  V2→V3 parity bullet): the Finder archetype UI (F4) was still described as
  gated on F2c/F3 backend work. F2c and F3 slice 1 merged in #777 and F3
  slice 2 in #862, so F4 no longer waits on backend work. F4's own gates from
  its design (fixture-based F4a/F4b behind a default-off flag; slice 1c scale
  proof before F4b is enabled; product publication at 9′ plus F4c/F4e before
  the flag is enabled in a governed build) are restated unchanged. The roadmap
  keeps the dated text and adds a supersession note in its usual form.
- `docs/development/v3-finder-delivery-plan.md`: dated 2026-10-20 status
  added after the 2026-09-26 one, which still said F3 was unfinished.
- `docs/operations/v3-production-application-release.md` (F3 cutover gate):
  records that #862 brought `/rerank`, `/system/{id64}` and `/simulate` behind
  the same product-publication gate.
- `docs/development/pull-request-acceptance-policy.md`: records that the
  self-hosted Octopus instance was switched to manual, final-candidate review
  (Auto Review off, spend limit set) on 2026-10-20 and that a review is
  requested with the PR comment `@octopus-review`; and that an Octopus `429`
  "no credits remaining" response is a service-unavailability (billing)
  failure under the reviewer-failure section, not a code finding.
- `docs/development/test-environment.md`: documents the #865
  `EDF_DB_TESTS_REQUIRED=1` behaviour of the three instrumented PostgreSQL CI
  lanes, and names the DB lanes and bare `pytest.skip` sites it does not cover.

## 2026-10-20 — Search build statistics repair recorded; builds running

Records the owner's 2026-10-20 `ANALYZE v3_derived.system_search` in
`docs/operations/v3-postgres-server-settings.md`: stale planner statistics
(last analysed 2026-09-21, before this generation's `system_search` rows
existed — the generation itself was created 2026-09-14 and published
2026-09-16) made the Search
build's per-chunk guard query scan the growing `system_search` table
(6.5 s/chunk, ~15-day projection); after the refresh the same query takes
5 ms and the build runs ~244 chunks/min. Also records that the 7′ capacity
gate passed (run 39328735287, 96 GB headroom) and the Search build started
(run 39328946864) on 2026-10-19, and notes the `ANALYZE` carry-forward for the
Archetype build.

## 2026-10-19 — F2d capacity-measurement evidence committed

The `V3 Finder capacity measurement` workflow (run 39322510090, disposable
PostgreSQL 18, 200,000 deterministic synthetic rows per measurement) produced
the last three step 7′ evidence files, committed under
`docs/operations/evidence/f2d/`: `calibration-fractions.json` (converted from
the complete-read receipt `2741e831…`), `archetype-footprint-receipt.json`
(308 fixed bytes per `system_archetype` row, seal `4b0eef55…`) and
`search-footprint-receipt.json` (83 bytes per row `010` delta, seal
`4ab125a1…`). Both footprint receipts are `capacity_gate_eligible` and carry
the attested operator-code identity `c26d23d0…`. The roadmap and rollout-state
ledger now point at the 7′ gate as the next step.

> **Current-horizon note (2026-09-05):** dated entries below describe their own
> repository checkpoint. In particular, the 2026-09-04 foundation entry predates
> active PR #601. At known PR head
> `190d26446a2487596299cbb6b497ffa5201fee0b`, that lane contains a real
> Explore/Finder → fresh Babylon results → canonical Inspect product slice.
> This note records active-PR state, not a claim that it has merged into `main`.
> Use the authority chain in [`README.md`](README.md) for current truth.

---

## 2026-10-19 — API silent-failure fixes (ingest liveness, SSE bridge, evidence errors, status cache)

Six places where the API swallowed a failure and reported itself healthy:

- **EDDN simulation ingest** (`apps/api/src/ingest/eddn_client.py`): a failed
  DB flush no longer advances the liveness timestamp (the July 2026 outage
  shape — the loop cycled, every flush failed, the stall alert never fired).
  Liveness advances on a successful flush, and on message receipt only while
  the write path is healthy. New `/api/metrics` series:
  `ed_finder_eddn_simulation_ingest_flush_failures_total`,
  `..._consecutive_flush_failures` and
  `..._last_successful_flush_timestamp_seconds`. After
  `EDDN_SIMULATION_INGEST_MAX_CONSECUTIVE_FLUSH_FAILURES` (default 5, bounded
  1..1000) consecutive failures the loop raises and reconnects; the breaker
  also applies to the exit-path flush (quiet-feed timeout) unless an
  exception is already propagating. The ingest
  remains the named runtime exception in `CLAUDE.md`; no journal-import
  automation was added.
- **EDDN→SSE bridge** (`apps/api/src/routers/events.py`, `main.py`,
  `deps.py`): the bridge now starts unconditionally and, when Redis was down
  at boot, retries the connection itself with capped exponential backoff
  (1 s → 60 s), installing the client on success so the cache recovers too.
  Boot and bridge share one bounded `deps.connect_redis()`. New gauge
  `ed_finder_sse_bridge_state` (0 not started, 1 connecting, 2 subscribed,
  3 retrying, 4 stopped) and counter `ed_finder_sse_bridge_reconnects_total`.
- **Warehouse planner evidence** (`warehouse_planner_evidence_provider.py`):
  only `UndefinedTableError`/`UndefinedColumnError` count as "missing
  evidence". Timeouts (`QueryCanceledError`), interface errors and other
  database errors — on any of the loader's direct calls (pool acquire, system
  lookup, counts/probes, bounded staging) as well as the helpers — raise
  `PlannerEvidenceQueryError`, which the route turns into
  HTTP 503 with a bounded detail (exception class + SQLSTATE only).
- **Share OG image** (`share_router.py`): the Redis read/write goes through
  `deps.cache_get`/`cache_set` (0.1 s cache I/O timeout) with the PNG
  base64-encoded; the cached payload is validated (PNG signature, size cap)
  before it is streamed. The bare Redis calls in `routers/archetypes.py` and
  `local_search.py` are deliberately left for a follow-up because another PR
  is editing those files.
- **V2 cluster rebuild** (`routers/admin.py`, `helpers.py`):
  `POST /api/admin/rebuild-clusters` answers 410 Gone with a
  `application/problem+json` body. The Docker Compose shell-out — which the V3
  API could never execute — is removed along with `subprocess`; admin auth and
  the rate limit stay on the route. 410 is the route's primary and only declared
  status (`response_model=RetiredRouteProblem`, `application/problem+json`),
  so the generated clients carry no 200 branch; both clients are regenerated.
- **`/api/local/status`** (`routers/meta.py`): a `{available: false}` payload
  is no longer cached for `ttl_status`, and the raw exception text is replaced
  by a fixed reason code (`db_timeout`, `db_schema_missing`, `db_unavailable`,
  `db_error`); the raw text stays in the server log.

Tests: `tests/test_eddn_simulation_ingest_flush_failures.py`,
`tests/test_sse_bridge_redis_recovery.py`,
`tests/test_warehouse_planner_evidence_query_errors.py`,
`tests/test_share_og_cache_bounded.py`,
`tests/test_meta_status_failure_branch.py`; the retired cluster-rebuild
contract test now pins the 410 and the absence of a Docker shell-out.

---
## 2026-10-19 — F3 slice 2: `/rerank`, `/system/{id64}`, `/simulate`, `/profiles` on the V3 projections

`apps/api/src/routers/archetypes.py` now reads only the published V3
`v3_app.system_search` / `v3_app.system_archetype` projections. The last four
legacy V2 routes were repointed the way slice 1 (#777) repointed
`/api/local/search` and `/api/archetypes/rankings`: one REPEATABLE READ
snapshot per request that resolves the published generation through
`local_search._current_derived_generation` (404 with no PUBLISHED generation;
503 until both Finder products are READY and published, migration 015's
product gate) and then reads the wide archetype row (migration 011) through a
new pure, parameterized builder in `apps/api/src/ranking/rerank.py`. Every
request shape is validated before any database access so a 422 is never
masked by that 503. The Redis cache layer, `mv_archetype_rankings`,
`system_archetype_scores`, `system_archetype_traits`, `systems`,
`system_slot_topology`, `economy_pair_synergy`, `body_scan_facts` and
`bodies` references are gone from the router; a static test walks every string
literal in the module to keep it that way.

Response and request shapes changed where the legacy fields had no V3
projection (flagged, not null-degraded, per the F2c/F3 design):

- `POST /api/archetypes/rerank` blends the eight V3 archetype fits.
  `ArchetypeRerankWeights` is one weight per V3 key (the legacy
  `purity`/`buildability`/`slots`/`expansion`/`logistics` dimensions are
  rejected); `archetype` takes the V3 keys; `reranked_score` is the blend of
  the stored `score x confidence x completeness` keys, normalised by the
  weight sum, ordered DESC then `system_id64`; rows carry `tier`,
  `original_score`, `confidence`, `completeness`, `primary_archetype`,
  `secondary_archetype` and no `rationale`; the envelope adds
  `missing_id64s` and the `ranking` identity block. An unknown `profile` is
  422, not a silent fallback.
- `GET /api/archetypes/system/{id64}` returns the wide row (all eight fits
  with stored tier/confidence/weighted key), the summary, the search evidence
  badge and a `facts` block; the V2-only `topology`, `economy_pairs`, `tags`,
  buildability/purity/contamination fields are retired. `id64` is
  path-bounded to a non-negative bigint. Explanations stay on the sibling
  `/system/{id64}/explanation` route.
- `POST /api/archetypes/simulate` scores the planned V3 archetype from its
  stored fit; `contamination_risk`/`purity_score`/`buildability_score` are
  retired and the `disclaimer` states that no V3 projection carries them.
- `GET /api/archetypes/profiles` is one single-archetype preset per V3 key plus
  `generalist`, derived from `ARCHETYPE_KEYS`.

The rerank blend is deliberately outside the hashed ranking-profile identity
(weights are per request), so `ranking_sha256` is unchanged and the deployed-
image attestation in `deploy/v3-production/target-authority.json` still
matches; a test pins that. Generated TypeScript clients
(`apps/web/src/lib/api/generated/`, `packages/api-client/src/generated/`) are
regenerated and `packages/api-client` `DEFAULT_WEIGHTS` moves to the V3 equal
blend. Tests: `tests/test_ranking_rerank.py` (pure),
`tests/test_archetype_slice2_v3.py` (PG18 fixture lane), the no-legacy guard
extended to the whole router, and the integration rerank tests now skip in the
V2-only lane via `v3_derived_ready`. Operator code and the ranking profile are
untouched.
## 2026-10-19 — DB lanes can no longer pass with zero tests run; known test flakes fixed

Test hygiene only; no application, migration or operator-script change (the
F2d operator identity `c26d23d0…d6279` is unchanged).

- **`EDF_DB_TESTS_REQUIRED=1`** (`tests/helpers/db_isolation.py`:
  `database_unavailable`, `import_db_module`). Every "the disposable database
  is not usable" exit in the database-backed tests — unreachable server, unsafe
  or unset target URL, missing destructive-reset opt-in, missing driver or
  `bash`/`psql` — now routes through one helper that skips by default and
  **fails** when the flag is set. The three CI jobs that provide PostgreSQL
  (`Importer and synchronous tooling`, `Backend integration (PG+Redis)`,
  `Finder derived-data tests (PostgreSQL 18)`) set the flag in their pytest
  step `env:`, so a DB lane that lost its database turns red instead of
  reporting a green run of skips. Converted sites: `tests/ratings_v4_pg_fixture.py`,
  `tests/integration/conftest.py` (probe failure and `clean_db` opt-in),
  `test_data_trust_runtime.py`, `test_migration_applier_runtime.py`,
  `test_migration_ledger_baseline_runtime.py`, the spatial lifecycle/publish/
  pyramid suites, `test_journal_commander_association.py`,
  `test_frontier_auth_v3_postgres.py`, the Stage 19 readiness/constraint suites,
  `test_ratings_v4_resume_upgrade.py`, `test_measure_search_footprint.py`,
  `test_v3_canonical_bootstrap.py`, and `confirmed_target_or_skip`. Skips about
  the *state* of a reachable database (V2-only schema, no published generation,
  missing seed rows) and the integration `Redis not available` skip are lane
  conditions, keep their specific reasons, and are not affected by the flag.
- **Flake fixes (tests only):** the deployment cancellation test's child now
  publishes its pid atomically (temp file + `os.replace`) and the test polls
  for digits rather than file existence; the purge-controller test's inert
  action holds 1.5 s so "still running once started" cannot lose a scheduler
  race; the backup test waits for the `tee`/process-substitution log writer to
  catch up with the captured stdout instead of a 1 s existence check; the
  review-lab process-registry test uses a 10 s grace so `running` is recorded
  after the child has actually exited; the EDDN metrics test starts the server
  on a probed ephemeral port with EADDRINUSE retry and waits for an accepted
  connection instead of `sleep(0.1)` (`METRICS_PORT=0` disables the server, so
  port 0 cannot be used directly).
## 2026-10-19 — Svelte web dead-code trim

Deletions only in `apps/web/`, no behaviour change. Removed the unreferenced
`OwnerAccessGate.svelte` and `SessionAdminTokenControl.svelte` components (no
`/admin` or `/operator` route exists), the `operatorHandoff` session store and
its `ed_operator_selected_source_run` persistence key, `queryKeys.operator`,
the SSE helper `src/lib/api/events.ts`, the optimiser request fingerprinting
(`optimiserRequestFingerprint`, `OptimiserQueryRequest`, `queryKeys.optimiser`)
and the `optimiserCandidates` facade function, the eager `profileSyncCommands`
singleton, and three zero-reference helpers (`loadGalaxyDensityContribution`,
`readSessionStorageValue`, `persistenceDiagnostics` plus its unused test seam).
Each deleted item had no importer outside its own unit test; those tests were
removed or trimmed with it, and the persistence contract test now lists only
`ed_admin_token` as a session key. The unused `bits-ui` dependency is dropped
from `apps/web/package.json` and `pnpm-lock.yaml`. `packages/api-client` is
still consumed (`core`, `id64`, `lossless-json` by the web facade; `types` by
`planner-core`) and is left in place.

## 2026-10-19 — Complete read receipt and coefficient decision committed

The step 6′ complete read (start run 39243944566, status run 39311585254)
scored every one of the 198,528,286 systems in under 8 h 10 min (started 11:21 UTC, found complete by the 19:31 UTC status check) with no failures;
its sealed receipt (Σ_all 0.5895 against the 4.0 bound) and the owner's sealed
`coefficient_decision: accepted` are committed under
`docs/operations/evidence/f2d/`. Both pass the capacity gate's own checks
against this source.

## 2026-10-19 — Production PostgreSQL server settings recorded

`docs/operations/v3-postgres-server-settings.md` records the owner-applied
statistics repair on `economy_opportunity.system_id64` and the move off
default memory/checkpoint settings (`effective_cache_size` 128 GB, `work_mem`
32 MB, `maintenance_work_mem` 2 GB, `max_wal_size` 32 GB, `checkpoint_timeout`
30 min, `wal_compression` zstd; no restart), with `shared_buffers` 32 GB and
`dynamic_shared_memory_type = mmap` planned for a restart after the complete
read.

## 2026-10-19 — Second F2d release accepted; sample probe passed after statistics refresh

Promotion run 39228589346 accepted release run 39223378017 (source `0dddc78d`,
PRs #854–#857) to active slot blue with no migrations or database writes;
the first F2d backend remains the minimum schema-compatible image and recorded
rollback artifact. The authority records the release with its attestation
(`f2d_operator_code_sha256` `c26d23d0…`), and the receipt is under
`docs/operations/evidence/`. The step 6′ sample probe (run 39186678592)
completed once the owner refreshed planner statistics on
`economy_opportunity.system_id64`; the owner accepted the coefficients. The
first full pgBackRest backup to the restored Storage Box completed on
2026-10-18 (label `20261018-152336F`, 1,252.9 GB).

## 2026-10-19 — Step 8′ builder hardening before the first production build

Audit of the two irreversible build actions ahead of their first production
run. Archetype validation (every chunk re-read and re-scored, hours at 198.5 M
systems) no longer runs as a bounded 7200 s foreground `--rm` container from
`finalize`: the detached worker validates after its last chunk and promotes
READY itself, exactly as the Search worker does, and `finalize` only requires
the worker's clean exit and the READY/VERIFIED product before `VACUUM
(ANALYZE)`; the duplicate per-chunk read is gone (the content seal is derived
from the rows already fetched) and `--validate` remains for operators. Both
builders now set `plan_cache_mode=force_custom_plan`, `lock_timeout` 30 s and
`statement_timeout` 30 min on connect; their failure receipts carry a bounded
`error_detail` and `sqlstate` with credential-bearing URIs and the live DSN
redacted (libpq errors can echo the password); a Search coverage mismatch
prints the ordinal and a bounded sample of uncovered id64s before failing. Both
actions: `fail()` also emits a stopped operation-result JSON line on stdout
(the workflow records stdout only), defined before the identity preflight so
those refusals print it too, `read_only` true for `-status`, with `db_writes_performed` null once a worker was
launched or VACUUM started by that invocation; a crashed worker's log is preserved under
the state root before `docker rm` and reported by `status`; a failed
`docker run -d` is guarded so it stops with a receipt (and the created
container's log) rather than exiting silently under `set -e`; the launch proof
window is ten minutes (a resume installs wheels and lists ~198k chunks first);
`start` requires the Storage Box rclone mount at `/mnt/ed-storagebox` in the
mount table (`wal_archive_target_unmounted` otherwise; an idle server with the
target unmounted shows no backlog and no failure), reads `pg_stat_archiver`,
`pg_ls_waldir()` and the archive_status
`.ready` backlog (a failed query stops with `wal_archiver_query_failed`; `archive_mode` off or
an empty `archive_command` stops with `wal_archiving_disabled`) and refuses `wal_archiver_unhealthy` when the archiver is
failing, or silent for 30 minutes while more than 50 unarchived segments wait
(never the recycled-segment count), since a build writes hundreds of GB of WAL
through pgBackRest archive-push; `status` reports the archiver. The Archetype
manifest records CPython major.minor only. Every changed file is in the F2d
operator-code manifest, so the accepted release must be rebuilt and promoted
with the new identity before the complete read, capacity gate or builds.

## 2026-10-18 — Calibration probe: generic-plan cancellation, stderr in receipt

Read-only probe run 39151827257 lost its SSH channel to the ~300 s idle
timeout (fixed in #853); the re-run 39155668281 then cancelled at the probe's
60 s statement timeout with `database error: QueryCanceled` and an empty raw
block. Reproduced on disposable PostgreSQL 18 with a 12 M-row copy: the shared
`OPPORTUNITY_READ_SQL` selects its branch with parameter NULL tests, and once
psycopg names the statement the generic plan is a parallel hash join over full
scans of both tables, while the custom plan is the chunk index plus the
opportunity primary key. `v3_archetype_calibration_probe` now forces custom
plans for the session, as `v3_archetype_calibration_complete` already did, and
`v3_system_archetype` does the same on connect because the build issues those
reads ~200,000 times. The probe action records the bounded tail of the
container's stderr in its receipt when the output is empty or invalid. Both
scripts are in the F2d operator-code manifest, so the accepted release must be
rebuilt and promoted with the new `f2d_operator_code_sha256`
(`7d3f346d…`) before the complete read, capacity gate or builds run.
## 2026-10-18 — Deploy and publish gate fixes for the second F2d promotion

Three gates audited ahead of the first re-promotion of an F2d release.
`validate_f2d_attestation` now requires the candidate backend to be one of its
own `rollback_targets`: the accepted authority later feeds
`validate_prior_runtime` for every migration apply without the running-image
exemption, so an attestation listing only the boundary image would block all
later migrations. The deploy workflow's attestation step now also computes
the operator-code identity over the checked-out candidate source and refuses
a mismatching `f2d_operator_code_sha256` (previously only shape-checked, so a
typo would pass promotion and refuse every later F2d action), and runs
`validate_f2d_boundary` before the SSH round trip. The publish and plan-probe
actions matched the active API image by `RepoDigests[0]`; repo digests are
unordered locally, so both now test membership of the attested backend as the
deployer does (both actions are in the F2d operator-code manifest). Tests
cover the second-release attestation shape, the workflow refusals and the
two-digest image case.
## 2026-10-18 — Complete read: resumable after a hard kill, retries, readable receipts

Pre-production audit of the step 6′′ complete read. `_atomic_json` named its
temporary `.<file>.tmp-<pid>` with O_EXCL; the worker is PID 1, so a hard kill
inside the write window would have refused every later resume. Temporaries now
use a per-write nonce and stale ones are cleared first. A chunk read that hits
the statement timeout or loses its connection is retried up to three times
(rollback, or reconnect with the session re-configured) before the run fails;
the default statement timeout for complete mode is 300 s; the session
configuration is committed so a rollback keeps it, and a failed reconnect
counts against the same per-chunk budget. `main()` writes a
sealed failure receipt for every exception with a bounded `error`, `sqlstate`
and the chunk in flight. The action's refusals print an
`operator-operation-result/v1` line on stdout, a stopped worker's logs are saved
before `docker rm` and their tail is in the status payload, the worker runs
under `--init`, and the proof-of-life window is ten minutes. The ops workflow
now routes each Finder action's stderr into its receipt artifact. Both scripts
are in the F2d operator-code manifest.

## 2026-10-18 — First F2d release accepted in production (step 5′)

Release run 39149556699 (source `f667bb4d`, including #851) passed preflight
run 39149910712 and was promoted by run 39149980927: receipt `status:
accepted`, active slot blue→green, no migrations or database writes, protected
resources unchanged. Staging, active and public smoke returned 200; the F2d
image contract, OpenAPI bounds, hard-filter 422 rejections and the 503
not-ready behavioural probes passed. `deploy/v3-production/target-authority.json`
now records this release in `observed_runtime` and as the accepted release
with its complete F2d attestation, so later candidates are judged by the
accepted-F2d product-state rule and keep its backend as the boundary image.
The bed755b9 promotion hold is removed. Both promotion receipts (accepted and
the earlier stopped attempt) are under `docs/operations/evidence/`. Tests that
assumed the pre-F2d accepted release or the unapplied migration transition now
assert the applied state; the transition mechanism tests rebuild the
historical attested set themselves. ROADMAP also records step 3 (all 18 Search
constraints validated) and the Storage Box restoration.

## 2026-10-18 — First F2d promotion stop fixed (OpenAPI bound type, search 422 order)

Production promotion run 39143010163 (release run 39140812920, source
`3415d5a3`) stopped on `f2d_openapi_contract_invalid:search.size` before any
cutover; the staged candidate was removed and the rollback verified, so the
live release was unchanged. FastAPI's OpenAPI model serves request-body
bounds as floats (`500.0`), while the gate accepted only JSON integers. The
gate now accepts an integral float equal to the exact expected bound (never a
bool). A local probe of the same release also showed the next gate,
`verify_f2d_rejections`, would stop: `POST /api/local/search` resolved the
published generation before validating the request, so an unpublished Finder
returned 503 where a disallowed hard filter must return 422. The route now runs
the DB-free `prepare_local_search_v3` validation first, matching the rankings
route. A new release must be built from the merged source before the next
promotion.

## 2026-10-18 — Finder migrations applied to production

Step 0 closed (read-only lifecycle status run 39113741990, every named worker
stopped or absent) and step 2 completed: governed plan run 39113784318 and apply
run 39113822236 applied `014`, `010`, `011`, `013`, `015` and `016` to the
production PostgreSQL 18 database, installing schema identity `d7efe689…`. The
apply receipt is retained under `docs/operations/evidence/`. The roadmap records
that the retired Storage Box leaves WAL archiving without a target and must be
resolved before the Finder builds.
## 2026-10-18 — Storage Box restoration runbook

`docs/operations/v3-storage-box-restoration.md` is the owner-run host procedure
that reconnects the retired offsite pgBackRest target to the unchanged design:
key-based rclone SFTP connection, `edfinder-storagebox.service` mount, a
same-container restart for the `rprivate` bind, `stanza-create`/`check` in the
new empty repository and the first full backup through the ledger-aware
wrapper. The wrapper's repository-health guard now also admits a full backup
(only) when a newly created stanza reports code 2 `no valid backups` with no
backups, so the first backup can be taken; every other state still refuses.
No production operation is included; the wrapper must be reinstalled through
the governed operation before the first backup.

## 2026-10-17 — Switch base-image pulls to the populated GHCR mirror

CI services, Docker builds, Review Lab and the disposable purge rehearsal now
pull base images from `ghcr.io/brianstewart377-rgb/ed-finder/mirror/` to avoid
anonymous upstream data limits. Tags and all digest pins are unchanged,
including the production API and web base images. The mirror's upstream source
list remains `.github/ci-image-mirror.txt`; contract tests reject executable
upstream references and unlisted mirror tags or digests. Current pull guidance
and image assertions follow the mirror. No production operation is included.

## 2026-10-17 — CI base-image mirror on ghcr.io

Anonymous pulls from `public.ecr.aws` now regularly fail CI with
`toomanyrequests: Data limit exceeded`. A new `CI base-image mirror` workflow
(manual and weekly) copies the listed base images (`.github/ci-image-mirror.txt`)
into `ghcr.io/brianstewart377-rgb/ed-finder/mirror/*` with every platform and
their manifest digests preserved and verified, then checks the packages pull
anonymously. A contract test keeps every executable `public.ecr.aws` reference
on the mirror list. Switching CI, Review Lab and image builds to the mirror is
a follow-up once the mirror is populated. No production operation is included.
## 2026-10-17 — Finder first, governed purge after go-live (owner decision)

The owner restored the build-first order: the 2026-10-11 pre-build purge
ordering is superseded, so the Finder products are built and published on
`parallel_v1` first (step 7′'s capacity gate still guards the builds) and the
governed purge of `ratings_v4_prod_p4`/`opt1` runs afterwards with its design
and gates unchanged. A host disk upgrade waits for NVMe availability.
`docs/ROADMAP.md`, `CLAUDE.md` and the capacity decision record carry the
amendment. Documentation only; no production operation is included.
## 2026-10-17 — Purge ledger state queries scale with batch history

The 1% disposable purge rehearsal stopped with `purge_state_query_failed`
during its third `delete-economy_opportunity` dispatch. Migration 016's
`purge_open_event` anti-joined every opening ledger event against every
closing event, so its cost grew with the square of the batch count, and the
operator state query let the planner call it once per batch event. The
never-applied 016 now resolves open events in one grouped last-closing pass
with identical results (randomised PG18 equivalence test), and the state
query materialises its scopes. Twenty thousand closed batches per relation
and request now resolve in about 0.13 s instead of about 30 s. The migration
checksum, manifest, target-authority migration-set identity and external
schema-identity checksum are re-pinned. No production operation is included.

## 2026-10-16 — Disposable governed purge rehearsal (P2d)

Added a manual Contabo self-hosted rehearsal workflow with a credential-free
PostgreSQL 18 container, unique disposable resources, disk admission checks,
scoped cleanup and 180-day evidence retention. The harness seeds lifecycle
receipt proportions, drives the real purge action through a production-refusing
disposable override, and records sealed measurements and crash-gate results.
Plan mode can consume a reviewed one-percent receipt by path and content SHA,
recomputing its production figures and refusing invalid seals or failed crash
gates. Smoke results cannot authorize production. Added workflow, harness,
override and receipt-consumption coverage and the P2d review runbook. No workflow
was dispatched or production system accessed; production artifact transport into
the protected plan workflow remains a separate gated integration.

## 2026-10-16 — Protected governed purge dispatch (P2c)

Added the manual, `v3-production`-protected derived-purge workflow with a closed
phase choice list, literal production-target confirmation, post-approval exact
`main` checks, both production/operator concurrency fences, pinned SSH trust,
authenticated sealed plan and exclusion-verification artifacts, and 180-day
receipts. Its controller waits for the remote action to exit and bounds delete
and rewrite timeouts; a trusted-main source bundle preserves the independent
rewrite monitor's source after controller loss. The ops workflow gains only
read-only purge plan/status choices. Added workflow contract coverage and the
dispatch/recovery runbook. The P2d disposable rehearsal and its sealed planning
figures remain required before destructive phases; no workflow was dispatched
and no production operation is included.

## 2026-10-16 — Purge physical rewrites and durable owner acknowledgement (P2b2b)

Added the four guarded rewrite dispatches, a backend-lifetime systemd watchdog,
filenode-based retry and interrupted-writer recovery, and recovered ANALYZE.
Amended unapplied migration 016 to durably record validated owner acknowledgement
on writer restoration, recutting its registered schema/target identities without
opening data-repair authority. Disposable PG18 catalog-worker races now use
fixture maintenance suppression and bounded waits. Added transaction, watchdog,
operator and PG18 recovery/completion coverage. No deployment, workflow dispatch
or production operation is authorized by this change; rehearsal figures remain
mandatory and come from P2d.

## 2026-10-15 — Bounded purge deletes and writer-fence recovery (P2b2a)

Extended the governed purge action with bounded, resumable delete dispatches,
per-batch disk/WAL/worker/controller checks, recorded-backend cancellation and
batch recovery through migration 016. Added exact-prior writer-fence restore,
signal cleanup ordering, acknowledged integrity-failure recovery and budgeted
autovacuum abort. The API stays running under the selected read-only fence.
The launcher requires CPython 3.14, source identity covers the backup wrapper,
and successful receipts derive WAL deltas through PostgreSQL. Physical rewrites
and their independent monitor remain P2b2b; workflow wiring and the disposable
1% rehearsal remain P2c/P2d. No production operation is included.

## 2026-10-15 — Purge plans and single-transaction phases (P2b1)

Added the governed purge action's closed mode allowlist, sealed read-only plan
and status receipts, authenticated authorization, zero-row dependency proof,
and completion gates through migration 016's functions. Shared preflight
checks pin the host/runtime/schema, workers, pointers, storage and WAL health,
backup wrapper, writer-fence authority and host lease. Single-transaction
phases wait boundedly for competing backend XIDs without changing 016's
production check. Added local operator contracts and disposable PostgreSQL 18
coverage. Delete/rewrite loops and recovery remain P2b2; protected workflow
wiring and rehearsal remain P2c/P2d. No production operation is included.

## 2026-10-15 — Purge entry fences and ledger-aware backups (P2a)

Added one read-only purge-ledger/host-lease admission check across production
mutators, with the exact authenticated-plan prefix exception only for schema
apply bootstrapping 016. The standalone pgBackRest wrapper skips live recorded
purge backends and fails closed on unavailable ledger evidence. A single new
trusted-main operator choice atomically installs and verifies that wrapper only
after 016, without changing timers or units. Added local contract tests and
PG18 ledger-query tests, plus the installation-order runbook. No production
operation, purge action/workflow, or rehearsal is included.

## 2026-10-15 — Governed derived purge capability registered (P1)

Migration `016` safely adopts a cluster-wide executor already installed by
another database only after checking its restricted role attributes, password
when readable, absence of memberships in other roles, and the non-superuser
creator's SET-only membership. Adoption also rejects every other incoming member
and any creator membership with ADMIN, INHERIT or no SET, including when the
creator is a superuser. Each database still installs its own grants and revokes.
PostgreSQL 18's implicit non-superuser creation ADMIN grant must be removed by an
authorized administrator before that role can be adopted in another database.
Rewrite cancellation authenticates a lock-waiting `VACUUM FULL` by its recorded
backend identity, bounded command and exact ungranted relation lock. Verified
rewrites reject repeated starts and new autovacuum fences. Service quiescence
allows one open record and restoration requires its exact container set; writer
and autovacuum fences preserve the recorded prior state across retries, and a
writer fence stays open until restoration is verified. Disposable PostgreSQL 18
regressions cover these recovery rules, reuse across databases and atomic
refusal of unsafe existing roles; fixture cleanup preserves shared roles.
The manifest and target schema identity are regenerated for these migration
bytes; this registration performs no production operation.

Migration `016` installs an append-only purge request/event ledger, fail-closed
bounded payload functions for only the two never-published rejected generations,
and the restricted executor role with autovacuum and application writer-fence
recovery support. It preserves manifests, products, receipts, publication
history and the published generation; installation performs no purge or rewrite.
The V3 manifest, target authority and every compatible transition prefix now
register `[014, 010, 011-rewritten, 013, 015, 016]`; the F2d release gate accepts
registration and still requires the exact applied ledger hashes. Lifecycle
status adds read-only role, writer-default and WAL/archive/slot facts for later
preflight evidence. Disposable PostgreSQL 18 tests cover the capability; operator
actions, protected workflow and crash rehearsal remain P2. Code only: no
production access, deployment or migration application.

## 2026-10-14 — Finder F2d release gate and identity attestation (PR4 D2b)

Adds the release-first Finder gate, grouped ranking/operator-code and rollback
attestation validation, post-promotion bounded-request probes, and a minimum
schema-compatible rollback boundary. The gate prefers recorded compatible
artifacts and permits the same operation's authenticated, checksum-bound
candidate as the first F2d rollback artifact after boundary and rollback-manifest
validation; preflight and promotion receipts retain its source and image identity.
Authenticated candidates defer image checks to promotion's candidate pull/verify
step; recorded rollback artifacts retain immediate verification. Publication's
bounded behavioural probes now require the exact READY-but-unpublished reason
for both 503s and receipt the parsed detail and verification result. The
publisher pins the active API DSN to the retained database and role, with the
host restricted to the pinned PostgreSQL container name or its inspected IPv4
address on the worker network, and independently checks the connected database
and user before any write (refusal code 79). The standalone plan probe also
refuses loaded checkout modules outside the operator-code manifest before
connecting. Regression tests cover all four review findings.
PR4b review round 3 fixes the deployed `picked` fetch-node recognition, applies
the KNN generation/tie allowance without the generic row cap, requires zero-heap
index-only windows for picked counts too, and measures bounding-box candidates
for the target generation before multiplying by the generation count. The
standalone probe now uses the publisher's pinned DSN binding and checks the
connected database and role before any probe statement (refusal code 24).
After commit, publication checks both live Finder endpoints for results and
the generation, attested ranking identity, and all three Archetype product
identities. A failed post-commit check records `published_unhealthy`, retains
the committed publication/write flags, and exits 80 without rollback.
Regression tests cover each of the six confirmed findings. These changes are
code only; no deployment or production access was performed.
PR4b review round 4 scopes `first-f2d-cutover-empty-finder-products` to the
currently accepted release lacking an F2d attestation group. Later upgrades use
`accepted-f2d-release-allowed-product-states`: keep the exact pinned generation,
allow BUILDING only unpublished and READY only VERIFIED (published or
unpublished), and refuse FAILED. Preflight and promotion receipts record the
rule and observed lifecycle, validation and publication states; post-promotion
bounded-request probes expect 200 after paired publication and the exact 503
reason during rollout. The choice uses accepted-release authority, independent
of optional dispatch attestation. F2d now authenticates the complete CPython
3.14 manylinux x86_64 Psycopg wheel graph through manifest-listed
`deploy/v3-production/f2d-wheels.txt`, hash-checked staging downloads and offline
installs in all six actions. The disposable capacity measurement uses the same
lock. Regression tests cover accepted later upgrades, first-cutover refusal,
failed products, rollout states, wheel hashes and every F2d install/download.
F2d operator operations now read their
attested identity from trusted-main's target authority. The gate requires all
six planned migrations and refuses explicitly while mandatory `016` remains
unregistered. The existing accepted-release values are unchanged. No deployment,
production access or production attestation was performed.

## 2026-10-14 — Finder F2d governed paired publication (PR4 D2a)

Adds the protected `publish-finder-products` operation, the deployment-lock-held
host action, and the paired publication transaction. The publisher checks bounded
view visibility, runs the deployed-image plan probe on its own connection before
commit, and waits for the host's repeated image-digest check. Sealed receipts
record preflights, maintenance, probe evidence and audit timestamps. The action
refuses until D2b supplies the accepted release's ranking and operator-code
attestation. No action was dispatched and no production system was accessed.

## 2026-10-14 — Codex worker model pin moved to `gpt-6.1-sol`

The Contabo Codex worker moves from `gpt-5.6-sol` to `gpt-6.1-sol`. The
2026-10-06 attempt (#784) was reverted because Codex then rejected
`gpt-6.1-sol` for ChatGPT-account sign-in. The worker's Codex CLI is now
0.162.1, and a live check on the worker, signed in with its ChatGPT account
and using the workflow's exact flags (`--ignore-user-config --strict-config
--model gpt-6.1-sol --config model_reasoning_effort="high"`), completed. The
owner chose 6.1 Sol over GPT-6 Astra to limit credit use. Effort stays
`high`; the single-model governance contract and its test keep the same shape
and now reject the old `gpt-5.6-sol` literal.

## 2026-10-13 — Finder F2d wide Archetype data layer

The governed read-only Archetype plan probe now generates all 80 ranking page
and count statements from the attested running API image, executes them with
production statistics under generic-plan settings, and seals complete
per-statement plan evidence. Its assertion module is connection-driven so the
later product publisher can run the same checks inside its own transaction;
the standalone action validates build maintenance receipts, product
publication, the image digest, and the densest current spatial window before
starting a bounded read-only worker. No action was dispatched and no production
system was accessed.

The governed Finder build slice now retargets Search to the current published
`ratings_v4_prod_p4_parallel_v1` generation and adds the wide Archetype build.
Both actions are identity- and migration-pinned, require the combined capacity
gate, bind registration to sealed manifest evidence, and finish only after
reviewed validation plus a receipted `VACUUM (ANALYZE)` of the physical product
table. The read-only lifecycle action now reports product publication
timestamps and the database publication-audit rows independently of publisher
receipts. No action was dispatched and no production system was accessed.

The combined Finder capacity gate is now wired as a synchronous, read-only
governed operation. Its trusted bundle is bound to the selected source SHA and
the explicitly supplied F2d operator-code attestation, and its sealed receipt
is retained for review before either product build can proceed.

The capacity-measurement slice adds fixed, shared F2d evidence paths and
canonical sealed-receipt loading; sealed, operator-identity-bound Archetype and
Search footprint receipts; and a manual GitHub-hosted PostgreSQL 18 measurement
workflow. Search is measured from three independent empty database states
(pre-010, post-010, and minimum-text fixed cost), while the Archetype receipt
records its measured text-free fixed cost for safe resume arithmetic. The
workflow only uploads evidence for review; it does not access or change
production.

The first governed-action slice pins the complete F2d operator surface to a
canonical content identity, adds matching fail-closed shell and Python identity
helpers, and allowlists a detached read-only complete calibration start/status
pair. The complete reader resumes only identity- and generation-bound chunk
checkpoints, scores every Ratings system through the shared model SQL and
`score_raw_system`, appends per-chunk tier counts to a digest-bound
`per-chunk.jsonl` log (the production generation has ~200,000 canonical chunks,
so the sealed receipt binds that log by length and SHA-256 rather than carrying
it), and seals the per-key totals, chunk-plan identity and expected product
manifest. A pure-standard-library converter verifies that receipt and
emits the measured 60/76/88 fractions consumed by the disposable footprint
measurement. No action was dispatched and no production system was accessed.

The additive `GET /api/archetypes/system/{id64}/explanation` route now
recomputes all eight archetype explanations on demand from the published
Ratings vector and opportunity inputs. It serves only an exact product/model
version and deployed-file hash match, holds identity and data reads in one
read-only repeatable-read snapshot, verifies every recomputed wide-row value,
and fails closed on identity or stored-score divergence. The legacy per-system
archetype route remains unchanged.

Migration `015` now permits independently validated Finder products to be
attached to the current published Ratings generation, while keeping product
rows and receipts insert-only and hiding READY products until a one-way,
audited publication timestamp is committed. Product publication and later
generation-pointer flips share a transaction lock; deferred table guards
enforce counterpart and unfinished-product rules even for direct DML. Search
and Archetype application views and API reads now require both products to be
READY and published, builders accept a PUBLISHED ratings base, and disposable
fixture seeds publish Search then Archetype in one transaction.

The unapplied migration `011` now stores one wide archetype row per system,
with integer-ppm confidences, exact integer weighted ranking keys, 24
tier-floor partial indexes, and application summary/detail views rather than a
physical summary table. The canonical scoring model now lives in
`shared_contracts`, carries a fail-closed semantic model digest, and is consumed
by a raw-input wide-row builder and exact validator. The governed migration
manifest and schema authority are recut for the rewritten `011`; this remains
registration only and does not claim production application.

The Finder ranking/API layer now reads that wide row through bounded 10,000-row
windows, literal B/A/S floors, cap-plus-one counts, and an anchored GiST KNN
nearest-first path. Picked and galaxy-wide hard-filter combinations fail
closed, filtered or score-sorted anchored searches are limited to 500 ly, and
both ranking envelopes carry the READY archetype product's complete identity.

The calibration probe now reads the canonical raw-vector and opportunity SQL,
scores only through the shared model entry point, and records model identities
and per-archetype tier histograms. The disposable footprint tool can apply and
measure the final `011` migration with all 26 indexes and histogram-shaped
builder rows, while fixture, Cypress, and Review Lab seeds validate one wide
row per system and keep product publication deferred to the follow-up PR.

## 2026-10-11 — Read-only production disk inventory action

The governed `v3-disk-inventory` action inventories PostgreSQL volume
directories, databases, WAL, temporary files and logs, large relations and
indexes, dead tuples, and derived-generation attribution, then summarizes
accounted and unaccounted usage. It is strictly read-only and performs no
reclamation; any purge or rewrite remains a separate reviewed design.

## 2026-10-10 — Finder rollout step 0 run; capacity decision A + B recorded

The read-only `v3-derived-lifecycle-status` inspection ran against production
(run 38079894267). Its receipt is recorded under `docs/operations/evidence/`.
The data volume has about 292 GB free against roughly 1.4 TB for the fresh
Finder generation as designed. The owner chose to rewrite the unapplied
migration `011` as one wide archetype row per system (measured ≈65 GB) and to
attach both Finder products to the already-published generation behind an
explicit product-publication gate (`015`), deferring any purge; the ROADMAP's
steps 4–9 are replaced accordingly. The paused `opt1` ratings worker was killed
by the owner; step 0 closes when the confirming receipt is recorded.

## 2026-10-10 — CI pulls from ECR Public are sequential with retry

ECR Public's anonymous quota is one pull per second, so parallel pulls can fail
with `toomanyrequests`. Review Lab and the image-parity jobs now pull images
sequentially with three attempts and a three-second backoff. Review Lab bounds
each attempt to 60 seconds, while image parity bounds each attempt to 120
seconds; no image or digest changed.

## 2026-10-10 — CI failure causes surfaced as GitHub annotations

Failed pytest tests now emit `::error` annotations with the file, line, test ID,
and assertion text when running under GitHub Actions. The Review Lab job summary
now shows the failure code, failure summary, and failed phases and emits them as
annotations; nothing about test selection, assertions, or gates changed.

## 2026-10-10 — CI image builds avoid anonymous Docker Hub pulls

The API and web Dockerfiles now use the public ECR Docker Library mirror for
their digest-pinned Python, Node and nginx base images, preserving every
immutable digest. Compose validation and container-image parity use the Docker
daemon's built-in BuildKit driver, avoiding the default Docker Hub BuildKit
helper pull. The production release workflow and deploy contracts are
unchanged. The EDDN, importer, and maintenance Python base images now also come
from `public.ecr.aws/docker/library` with unchanged tags, and the
runtime-authority test now requires the mirror prefix.

## 2026-10-09 — CI Docker Official Images moved to ECR Public

CI workflows and the disposable Review Lab contract now pull the same pinned
Docker Official Image tags and digests through `public.ecr.aws/docker/library`.
This avoids anonymous Docker Hub pull limits on shared GitHub-hosted runner IP
addresses without changing the selected PostgreSQL, Redis, or nginx images.
Contract validation now rejects bare Docker Hub library references in those
surfaces while leaving legacy, local, and production Compose contracts
unchanged.

## 2026-10-09 — Finder migrations 010/011/013 registered after 014; 010 rewritten for bounded application

Migration `010_v3_system_search_body_type_counts.sql` now adds its 18 columns
without inline checks and declares the checks as `NOT VALID`, avoiding a
full-table validation scan during the bounded migration apply while continuing
to enforce them for subsequent writes. The V3 production manifest and authority
now register `010`, `011`, and `013` after `014`. This is registration only:
none of those migrations was applied, and the governed plan/apply and separate
constraint-validation operations remain outstanding.

## 2026-10-09 — Reviewed production-promotion hold in version-drift monitor

The production version-drift monitor now understands an explicit, reviewed,
time-bounded hold pinned to the live `bed755b9` release while the F3 Finder
products remain unpublished. The hold expires on 2026-11-09 and must be renewed
or removed through review; manual dispatch can ignore it to expose raw drift.
Web/API agreement, SHA validity, and the expected-SHA deployment gate remain
fail-closed.

## 2026-10-10 — Finder rollout step 6: read-only archetype calibration probe + governed action

The bounded, read-only probe samples published Ratings V4 vectors and reports per-archetype score distributions, primary and secondary counts, tier histograms, and mining/manufacturing/megacomplex separation. The governed operator action verifies the published current generation, runs the probe with fixed resource limits, and retains its JSON receipt as calibration evidence. It has not been run, and the resulting coefficient decision must be recorded before the `system_archetype` product is registered and built.

## 2026-10-10 — Finder rollout step 3: governed system_search constraint validation action

The action runs all 18 deferred `system_search` check validations in a detached runner and provides a separate read-only status operation. It changes only catalog validation flags, with no row data changes and no publication. It has not been run.

## 2026-10-10 — Finder rollout step 0: read-only derived lifecycle status action

The action reports the four worker states, the migration ledger, and the canonical, derived, and spatial pointers and lifecycle states. Its footprint evidence reports measured live relation and index sizes, database size, host disk headroom, and a `measured_footprint_attribution` section with proportional chunk-receipt system-count attribution per generation as inputs to the disk decision. These measurements do not replace the required disposable PostgreSQL 18 sample measurement and full-scale extrapolation of the post-`010` `system_search` row width or the `system_archetype` and `system_archetype_summary` relations and indexes. It is strictly read-only, using READ ONLY transactions and reading identity names only. Running it is a governed operator operation that has not yet happened.

## 2026-10-08 — Codex worker model pin reverted to `gpt-5.6-sol`

The 2026-10-06 bump to `gpt-6.1-sol` (#784) is reverted. The Contabo Codex
worker authenticates with a ChatGPT account, and the Codex API rejects
`gpt-6.1-sol` for that auth mode (`400 invalid_request_error: The
'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT
account`). The first run after #784 (Codex Laptop run 37820866840) failed at
`Run Codex implementation` with that error. The pin returns to `gpt-5.6-sol`,
used by every successful run since #593; effort stays `high` and the
single-model governance contract and test are unchanged in shape.

## 2026-09-05 — Codex worker reasoning-cost adjustment

### Fixed high-effort model contract

The self-hosted Linux Codex worker now pins both investigation and implementation runs to `model_reasoning_effort="high"` instead of `max` to reduce Contabo credit consumption. The official model ID remains the literal `gpt-5.6-sol`, and each pre-execution attestation reports the fixed `model=gpt-5.6-sol` and `reasoning_effort=high` values.

Exact governance tests now require the same `high` setting in both Codex CLI invocations and both pre-execution attestations, while rejecting the former `max` configuration.

### Trust and authority boundaries unchanged

This is a worker resource-setting change only. Strict configuration validation, ignored ambient user configuration, sandbox mode, least-privilege job permissions, immutable branch/base selection, repeated state gates, credential separation, result sealing, trusted compare-and-swap push, fresh CI/re-review requirements, the production/operator workflows, and deployment authority are unchanged.

---

## 2026-09-04 — Issue #577 hard replacement tranche

- Made `apps/web/` the sole browser-application destination; React is temporary source evidence only, and this branch remains unmerged until replacement parity is complete.
- Made Cypress the sole active browser framework for Review Lab, Chrome/Firefox, axe accessibility, and deterministic screenshot evidence. Playwright survives only in static historical provenance.
- Preserved the Python Review Lab evaluator as the acceptance and browser-summary schema owner; Cypress is only its browser driver.
- This tranche does not authorize production deployment, database work, OAuth activation, a Babylon runtime, or later Stage 27 work.
- Marked root Compose, its PostgreSQL 16 maintenance image, and restore/rehearsal helpers as legacy local/CI tooling, never PostgreSQL 18 V3 production or backup authority.

## 2026-09-04 — V3 application stack lock and implementation foundation

### One deliberate application baseline

ED-Finder locked the V3 application architecture rather than carrying each V2-era choice forward independently.

The new browser-application target is:

- Svelte 5 and SvelteKit 2;
- TypeScript 6;
- Vite 8 / Rolldown;
- Node.js 24 LTS and pnpm 11;
- Tailwind CSS 4, Bits UI v2, and Lucide Svelte;
- TanStack Svelte Query for server state;
- Hey API + Fetch for generated FastAPI clients;
- Cypress as the sole active protected browser/E2E authority;
- static SvelteKit output served through the same-origin V3 web boundary.

The backend/data direction remains FastAPI, Pydantic 2, PostgreSQL 18, reviewed SQL migrations, and an eventual CPython 3.14 + `uv` baseline. Valkey is the locked cache/pub-sub direction; NATS is not part of the new baseline without a newly justified responsibility.

The spatial target is a Babylon.js 9-class workbench behind the existing renderer-neutral Stage 27 contracts. The stack decision does **not** authorise Babylon implementation, a renderer cutover, or a later Stage 27 slice.

### New `apps/web` implementation lane

A parallel V3 application foundation now lives under [`apps/web/`](apps/web/). It establishes:

- a static SvelteKit SPA shell and route skeleton;
- Node 24 / pnpm 11 frozen dependency management;
- Tailwind 4, Bits UI, Lucide, and TanStack Svelte Query foundations;
- Hey API generation from an explicitly supplied FastAPI OpenAPI source;
- bootstrap health/session client calls through the generated SDK;
- ESLint 10, Prettier 3, Svelte checks, Vitest/Testing Library, and Cypress smoke coverage;
- CI checks for generation drift, type/check, lint, format, unit tests, build, and browser smoke;
- explicit same-origin route ownership: `/api/*`, exact `/openapi.json`, and numeric `/s/{id64}` remain FastAPI-owned while other application/static routes belong to SvelteKit.

The existing [`frontend/`](frontend/) React/R3F tree is temporary source evidence only during the hard replacement, not an active runnable or validation lane.

### Scope deliberately not claimed

This foundation is **not**:

- a production deployment or public cutover;
- Finder, Inspect, Colony Planner, Review, Admin/Ops, or map feature parity;
- a Babylon renderer implementation;
- a React/R3F retirement;
- a Playwright removal;
- a Redis-to-Valkey or NATS removal;
- a Python 3.14 / `uv` backend migration;
- a database migration, restore, or production OAuth activation.

Those remain separate reviewed slices with their own acceptance and rollback boundaries.

### API and test transition rules

While both frontend lanes exist, both generated API clients must come from the same authoritative FastAPI `/openapi.json` document. The repository drift check regenerates both and fails if checked-in output differs.

Cypress is the only active browser authority. Review Lab, accessibility, visual, and Chrome/Firefox responsibilities are Cypress-owned; Playwright remains only as wording inside clearly historical evidence.

### Root documentation re-baseline

The root [`README.md`](README.md) now acts as the complete V3 entrypoint. It distinguishes:

- infrastructure cutover from application completion;
- the new Svelte lane from the retained React reference;
- programme authority from technology selection;
- SvelteKit routes from FastAPI-owned routes;
- production V3 authority from root legacy/self-host Compose;
- selective legacy-data migration from wholesale database recovery;
- Cypress direction from still-load-bearing Playwright evidence;
- inert/historical Hetzner references from executable production authority.

---

## 2026-09-02 — V3 infrastructure cutover and V2/Hetzner severance

### What the cutover established

The cutover established the replacement V3 **infrastructure authority**:

- PostgreSQL 18 is the production database generation;
- the V3 backup/PITR design and current infrastructure status document define the recovery boundary;
- Frontier identity and replacement-host trust/configuration belong to the V3 environment;
- GitHub and reviewed V3 workflows/runbooks are the application and infrastructure source authority;
- old Hetzner/V2 release, SSH, hosted-review, and server-maintenance procedures no longer authorise production work.

This was an infrastructure boundary, **not a claim that the complete application had already been rebuilt, released, or proven at the public edge**. Current live application state must be established from current status/provenance evidence, not from this historical entry.

### Operational severance

The repository retired or removed the former V2 execution path:

- the old main deployment entrypoint became an inert fail-closed tombstone;
- obsolete Windows release and direct-SSH wrappers were deleted;
- the Hetzner operator workflow and hosted-review deployment lane were removed;
- retired database/recovery runbooks were converted to explicit non-executable historical material;
- current V3 operator actions remained narrow and did not acquire an implied deploy, migration, or database-restore operation;
- environment examples were sanitised so retired Storage Box and V2 secret/config values were not presented as V3 authority.

Some historical identifiers, archived stage records, and local/self-host tooling remain intentionally. The decommission goal is **zero live V2 path and zero ambiguous authority**, not deletion of every historical mention.

### Data migration boundary

Public and reconstructable galaxy data should be reimported or rebuilt through current data paths. Redis/cache state and NATS/JetStream transport state are not canonical domain truth.

A validated PostgreSQL custom-format dump is retained offsite solely as a selective source for genuinely irreplaceable/private/manual/history data:

| Field | Value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Recorded offsite sync | `2026-08-23T05:32:41Z` |

The dump is not the operating database, not a PostgreSQL 18 physical backup, and not a general disaster-recovery shortcut. Never attach or copy an older PostgreSQL physical data directory into PostgreSQL 18. Any extraction must identify the exact irreplaceable data, use reviewed migration tooling, verify the target, and validate the selected result.

### Recovery remains fail-closed

A retained dump, source archive, status action, local Compose restore helper, or old incident note is not automatically a production recovery procedure.

When a current V3 runbook does not authorise the required production database restore/PITR action, stop rather than adapting a retired V2 PostgreSQL/Compose sequence. Recovery authority must identify the V3 target, data source, safety checks, compatibility boundary, validation, and rollback/abort conditions explicitly.
