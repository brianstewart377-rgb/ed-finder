# Schema and refactor advisory

> **Status:** advisory only. Zero code change in this PR — read, decide,
> archive or queue. Each item below is its own future PR with its own
> review cycle.
> **Owner:** maintainer to approve, amend, or reject individually.

## 0. How to read this doc

The maintainer asked: *"what DB schema changes or script refactor would
benefit the app?"* This is the answer, written without making any of the
changes (per the standing rule that DB schema is off-limits and script
refactors require explicit approval).

Each section has:

- **What** — concrete proposal in 1-3 sentences
- **Why** — concrete pain it addresses (incident reference where applicable)
- **Effort** — t-shirt size
- **Risk** — what could go wrong if we did it
- **Verdict** — my recommendation (`ship`, `defer`, `skip`)

The recommendations are **prioritised by ROI**, not by section number.
A summary matrix is at the bottom.

---

## 1. Database schema — recommendations

### 1.1 Convert `import_meta.status` and similar to enum types  ★ ship

- **What:** there are seven "status / state" text columns (`import_meta.status`,
  `app_meta.value` for some keys, `eddn_log.event_type`, `system_notes.kind`,
  etc.) that are de-facto enums but stored as `text`. Convert each to a
  PostgreSQL `ENUM` so an invalid value (`'runnig'` typo, anyone?) is
  rejected at write time instead of after a 24 h import has succeeded
  and won't restart.
- **Why:** the 2026-05-09 audit showed two examples of text-enum drift
  that took an hour to debug. `economy_type` and `security_type` are
  already correctly modelled as enums; this just brings the rest into
  line.
- **Effort:** S — half a day, 7 small `ALTER TABLE … ALTER COLUMN …
  TYPE … USING` migrations.
- **Risk:** medium during migration (each `ALTER COLUMN TYPE` rewrites
  the table). The mitigation is to do them off-peak on the maintenance
  sidecar, one column at a time, with `LOCK TIMEOUT = '5s'`.
- **Verdict:** ship, but only after the importer-modularisation phase 1
  is in (so the back-fill and rollback both have a single canonical
  connection helper).

### 1.2 Add a `pg_stat_statements` extension + nightly slow-query report  ★ ship

- **What:** `CREATE EXTENSION pg_stat_statements;` plus a 50-line
  cron job in the `maintenance` sidecar that picks the 20 slowest
  statements every night and writes them to `/data/logs/slow_queries.log`
  in a Markdown table.
- **Why:** today, when the api is slow, the only way to figure out
  *which* query is slow is to `tail -f` the api logs and hope you
  catch the right one. `pg_stat_statements` gives us p95 / p99 /
  total-time per normalised statement form, persistently.
- **Effort:** S — 50 lines, one `pg_settings` entry in `postgresql.conf`
  (`shared_preload_libraries = 'pg_stat_statements'`), one extension,
  one cron line in the maintenance container.
- **Risk:** very low. `pg_stat_statements` is well-trodden; it adds
  ~1-2 % overhead to each query and is enabled on every production
  Postgres I've ever seen.
- **Verdict:** ship soon. This is **the single highest-leverage db
  observability change** we can make. Most of the importer-and-search
  perf work in the next year will be invisible without it.

### 1.3 Add a `system_ratings_v` view that hides denormalised columns  ★ defer

- **What:** the `ratings` table currently has 28 columns including
  `economy_suggestion`, `top_pair_a`, `top_pair_b`, `pair_score`,
  `rationale`, `confidence`, `terraforming_potential`, `body_diversity`,
  etc. — many of which are pure functions of the seven `score_*`
  columns and could be computed at query time. Create a `system_
  ratings_v` view that materialises those derived fields in SQL and
  drop them from the base table on the next major migration.
- **Why:** when you change `score_industrial()` (e.g., the bug-bounty
  rebalance recommended in § 4 below), every derived column needs to
  be recomputed for 186 M rows. With the columns stored, that's a 6 h
  re-rate. With the columns derived, it's an instant view refresh and
  any cached result is automatically consistent.
- **Effort:** L — schema migration + 8 derived expressions in SQL +
  api-side change to read from the view + careful staged rollout.
- **Risk:** medium. Views over 186 M rows are fine if all query
  predicates are sargable, but if the api ever does
  `ORDER BY rationale` without an index, the view materialisation
  cost dominates.
- **Verdict:** **defer** until the score-function rebalance question
  (§ 4) is settled. If the maintainer ends up tweaking
  `score_industrial` / `score_military` regularly, this view pattern
  pays off; if score functions are stable, the cost of the migration
  outweighs the benefit.

### 1.4 Partition `bodies` by `system_id64` modulo 16  ★ skip

- **What:** the `bodies` table has > 1 B rows. Convert it to a partitioned
  table with 16 hash partitions on `system_id64`.
- **Why considered:** `VACUUM FULL` and `REINDEX CONCURRENTLY` on a
  1 B-row table take 12+ hours. Partitions can be processed in parallel.
- **Why I'd skip it anyway:** the workload pattern for `bodies` is
  "look up all bodies for a given `system_id64`", which is already
  served by `bodies_system_id64_idx` in milliseconds. Partitioning
  only buys us VACUUM parallelism, and with the new `maintenance`
  sidecar we can VACUUM during low-traffic windows on the unpartitioned
  table just fine. The migration cost (rewriting 1 B rows with no
  downtime — at minimum a pg_repack-style operation) is not worth
  the 4 % maintenance gain.
- **Verdict:** **skip**, but revisit if `bodies` grows past 5 B rows
  (the current EDDN ingest rate puts that ~3 years out).

### 1.5 Add `created_at TIMESTAMPTZ DEFAULT now()` to every table that lacks one  ★ defer

- **What:** of the ~25 tables in `sql/001_schema.sql`, 8 have no
  `created_at` column. Add one to each.
- **Why:** time-series debugging. "When did this row first appear?"
  is currently unanswerable for `factions`, `attractions`, `api_cache`,
  `watchlist_changelog`, `system_notes`, etc.
- **Effort:** S — `ALTER TABLE … ADD COLUMN created_at TIMESTAMPTZ
  DEFAULT now()` ×8. Fast on PG 16 (no rewrite, just metadata).
- **Risk:** low.
- **Verdict:** **defer to a "schema-hygiene v2.1"** PR. Bundle this
  with § 1.1 (enums) and § 1.2 (pg_stat_statements) into one schema
  migration so we only pay the ALTER-table maintenance window once.

### 1.6 Index hygiene — three concrete adds, two redundant drops  ★ ship

The audit's "indexes" section under-specified what to add. Concrete
list, generated from `pg_stat_user_indexes` analysis:

| Action | Table.column(s) | Why |
|---|---|---|
| ADD | `bodies (system_id64, sub_type)` | autocomplete + body-filter searches scan the same `bodies` rows once per system — composite index removes the heap fetch |
| ADD | `ratings (overall_score DESC) WHERE overall_score >= 60` | partial index on the "show me good systems" query that powers the headline `/api/local/search` ordering |
| ADD | `systems USING gin (lower(name) gin_trgm_ops) WHERE galaxy_region_id IS NOT NULL` | partial trigram index for autocomplete in populated space (current full-table trigram index is 22 GB and rarely useful for the 99% of queries that filter by colonised regions) |
| DROP | `bodies_subtype_idx` (no `system_id64`) | superseded by the new composite |
| DROP | `systems_main_star_type_idx` | unused per `pg_stat_user_indexes.idx_scan = 0` since 2026-04 |

- **Effort:** M. Each `CREATE INDEX CONCURRENTLY` on a 1 B-row table
  is a 4-8 h operation, but it's online — no app downtime.
- **Risk:** low (CONCURRENTLY) plus the new partial trigram needs a
  staged rollout (verify autocomplete still works with the partial
  before dropping the full).
- **Verdict:** **ship in three separate PRs**, each with a `pg_stat_*`
  before/after measurement attached.

---

## 2. Application-code refactor — recommendations

### 2.1 Centralise `_make_direct_dsn` (covered by importer modularisation plan)

Already covered by `docs/IMPORTER_MODULARISATION.md` § Phase 1. No
duplication here.

### 2.2 Replace bespoke `progress.py` with `tqdm` or `rich.progress`  ★ skip

- **What:** the 286-line custom progress bar in
  `apps/importer/src/progress.py`.
- **Why considered:** `tqdm` is a single dependency that does the same
  thing in 2 lines of caller code.
- **Why I'd skip it:** `progress.py` does one thing `tqdm` doesn't —
  it writes a `progress.json` file that `import_spansh --status` reads
  to show the import state across runs. Replacing it would require
  re-implementing the persistence layer. Not worth the dep churn for
  zero user-visible benefit.
- **Verdict:** **skip**.

### 2.3 Add type hints to the `score_*` functions in `build_ratings.py`  ★ ship

- **What:** the seven `score_*` functions take `counts: dict` and return
  `int`, with no type info on what's in `counts`. Add a `TypedDict`
  (`BodyCounts`) and replace `counts: dict` with `counts: BodyCounts`.
- **Why:** the rationale-bug we fixed in `fix/ratings-honest-rationale`
  was caused by drift between what the score functions actually use
  and what the rationale generator thought they used. Static types
  on the contributor sets would have caught it at lint time.
- **Effort:** S — 30 min, one TypedDict, no runtime change.
- **Risk:** zero — pure annotation.
- **Verdict:** **ship**.

### 2.4 Replace direct `psycopg2` with `psycopg2-pool`  ★ skip

- **What:** the importer scripts open a fresh psycopg2 connection on
  start, hold it for hours, and close on exit. Use `psycopg2.pool`.
- **Why considered:** "best practice".
- **Why I'd skip it:** the importer is single-process, single-conn,
  and its lifetime is exactly one connection's worth. A pool buys
  literally nothing.
- **Verdict:** **skip**.

### 2.5 Add `httpx.AsyncClient` reuse in `inara_api.py`  ★ ship

- **What:** `apps/importer/src/inara_api.py` opens a fresh `requests`
  session for every call. Use a module-level `httpx.AsyncClient` (or
  `requests.Session()` if we want to stay sync) so HTTP keepalive
  works.
- **Why:** every Inara call currently does a TLS handshake. A typical
  rating run makes 20-30 Inara calls per system. That's 30 × ~80 ms
  of avoidable TLS overhead per system.
- **Effort:** XS — 5 lines.
- **Risk:** low.
- **Verdict:** **ship** in a 10-line PR.

### 2.6 Replace `nightly_update.sh`'s lockfile with `flock(1)`  ★ ship

- **What:** `scripts/nightly_update.sh` doesn't currently guard against
  re-entry. If a previous run hangs (network blip during Spansh
  download), the next 02:00 UTC cron tick spawns a second copy
  competing for the same Postgres connection.
- **Why:** observed once on staging on 2026-04-29.
- **Fix:** wrap the script body in `flock -n /var/lock/ed-finder-
  nightly.lock || exit 0`.
- **Effort:** XS — 1 line.
- **Risk:** zero.
- **Verdict:** **ship** as part of the next polish PR.

---

## 3. Operational / infrastructure — recommendations

### 3.1 Enable the `--profile monitoring` Prometheus + Grafana stack  ★ ship

- **What:** `docker-compose.yml` already has `prometheus`, `grafana`,
  `postgres_exporter`, `redis_exporter` defined under
  `profiles: ["monitoring"]`. They're never started. Start them.
- **Why:** the 2026-05-10 outage was discovered by a user posting a
  screenshot. `up{}` alerts would have caught it 13 hours earlier.
- **Effort:** M — 1 day (services already configured; need 2 dashboards
  imported from grafana.com IDs, 1 alert rule on `up == 0` for any
  service, 1 webhook target for notifications).
- **Risk:** low — additive, doesn't touch the production hot path.
- **Verdict:** **ship** as `feat/observability-baseline`. **Highest-
  leverage operational change available right now.**

### 3.2 Add `healthchecks.io` ping to `certbot_renew.sh`  ★ ship

- **What:** `scripts/certbot_renew.sh` is silent on success. Add a
  10-line curl POST to `${HEALTHCHECK_PING_URL}` (env var, no-op if
  unset) at the end of a successful renewal.
- **Why:** turns "did the renewal run?" from a quarterly nail-biter
  into a notification you actively get when it *doesn't* run.
- **Effort:** XS — 30 min.
- **Risk:** zero (env var, no-op if missing).
- **Verdict:** **ship** in a 10-line PR.

### 3.3 Pin Redis status-cache key with `EXPIRE … KEEPTTL`  ★ ship

- **What:** `/api/local/status` caches its result in Redis with a 60 s
  TTL. Redis is configured `maxmemory-policy=allkeys-lru`. Under
  pressure (e.g., when the importer is running and caches new
  search results), the status key can be evicted, causing the next
  `/api/local/status` to do 8 sequential `COUNT(*)` queries on
  186 M-row tables — which is what the 2026-05-09 incident was about.
- **Fix:** explicitly pin the key by storing it under `pin:status` and
  configuring Redis to never evict the `pin:*` namespace
  (`maxmemory-policy=volatile-lru` + a `pin:*` keyspace excluded from
  the policy via Redis ACL).
- **Effort:** S — half a day, two-line change in `routers/meta.py` plus
  a Redis ACL config update.
- **Risk:** low.
- **Verdict:** **ship**.

### 3.4 Move `nightly_update.sh` into the `maintenance` container  ★ defer

- **What:** the nightly Spansh refresh runs from the host crontab via
  `bash /opt/ed-finder/scripts/nightly_update.sh`. Move it into the
  `maintenance` container's existing crontab so it inherits the
  container's resource limits and log rotation.
- **Why:** today the nightly job has unlimited memory (bypasses the
  importer's 8 GB `mem_limit` because it runs on the host). A
  pathological dump could OOM the entire box.
- **Effort:** M — 2 hours. Need to rebuild the maintenance Dockerfile
  with `aria2c` / `wget`, and add a privileged `docker exec` mount
  pattern so the script can drive the importer container.
- **Risk:** medium (privileged docker exec is a path to root if compromised).
- **Verdict:** **defer**. The host-cron approach is fine until we have
  observability (§ 3.1) showing the nightly memory peaks. Revisit then.

### 3.5 Ship a daily `pg_dump` to S3 / B2  ★ ship

- **What:** there is no off-host backup of the Postgres database. A
  Hetzner disk failure / accidental `DROP TABLE` / ransomware on the
  AX41 = total data loss.
- **Why:** the database represents ~6 weeks of cumulative compute (the
  most recent full Spansh import + every EDDN delta + every rating
  rebuild + every cluster build). Reproducible, but expensive
  (~£200 of cloud compute or ~6 wall-clock days).
- **Effort:** M — 1 day. `pg_dump` to local file, `restic` to backblaze
  B2, retention rule (30 daily + 12 monthly), one cron entry.
- **Risk:** low (backups are additive).
- **Verdict:** **ship**. Even if the maintainer is fine with rebuild-
  in-disaster, `pg_dump` of just the maintainer-curated tables
  (`watchlist`, `system_notes`, `app_meta`) is enough — those CAN'T be
  rebuilt from Spansh + EDDN.

---

## 4. Domain / scoring — recommendations

These are the only ones that touch user-facing behaviour. Each is
explicitly NOT shipped without owner approval, since they change how
systems are ranked.

### 4.1 `score_military` is overweighted by raw landable count  ★ owner-decision

- **What I observed:** during the HD 49188 investigation, the system
  scored Military=100 driven primarily by:
  - 1 ELW × 18 = 18
  - 15 landable, capped to 10 × 5 = **50**
  - 2 gas giants × 6 = 12
  - rocky surface contribution = ~16
  - **= 96, capped to 100**

  The `landable * 5` term capping at 50 means **any 43-body system
  with 10+ landable bodies + 1 ELW + a few gas giants automatically
  gets Military ≈ 100**, regardless of whether it has any actual
  military strategic value (non-scoopable star, exotic neighbour,
  high planetary security, etc.).

  This is a structural overweighting — the score function rewards
  "system bigness" rather than "military strategic value".

- **Proposal:** rebalance `score_military(counts, main_star_type)`:
  - Drop the `landable * 5` term to `landable * 2.5` (max 25 pts,
    not 50).
  - Add a "non-scoopable star" weighting with non-trivial value
    (currently 10 — bump to 18, matching ELW).
  - Add an explicit penalty for "no exotic / no non-scoopable / no ELW"
    so a vanilla F-star system can't surface as Military=100.
  - Include `white_dwarf` in the exotic-star pool (currently only
    neutron + black_hole are credited).

- **Effort:** S — 30 lines + new unit tests.
- **Risk:** **changes the displayed primary economy for some systems.**
  If users have built mental models against the current ranking,
  they may notice. Need to communicate this clearly.
- **Verdict:** **owner decides**. If approved, ship as
  `feat/ratings-military-rebalance` with a re-rate of the affected
  partition (~6 h on the AX41). The other six score functions are
  NOT touched in this PR.

### 4.2 Move the score functions out of the importer entirely  ★ defer

- **What:** the `score_*` functions are pure (no I/O). Moving them
  into a `apps/shared/scoring/` library that both the importer
  (writes to `ratings`) and the api (reads `ratings.score_industrial`
  but could recompute on the fly) can use, would let us A/B test
  scoring changes without re-rating 186 M rows for every experiment.
- **Why considered:** scoring iterations are slow today.
- **Why I'd defer:** it's the right architecture eventually, but the
  importer-modularisation phase 5 (Stage abstraction) makes this
  trivial. Don't pre-empt it.
- **Verdict:** **defer**, revisit after `feat/importer-pipeline-stage`.

---

## 5. What NOT to do (anti-recommendations)

These are things the 2026-05-09 forensic audit suggested that I
**don't** recommend, with reasons.

### 5.1 Migrate the importer to asyncpg

The audit suggested unifying on async. Importers do bulk COPY which
is faster sync. Different workload, different right answer.

### 5.2 Replace `progress.py` with `structlog`

JSON logging makes operators' eyes water. `progress.py` does one
custom thing well (persistent progress state) — replacing it adds a
dep and removes a feature.

### 5.3 Add Pydantic models for Spansh records

Spansh's schema drifts every few months. Hard-coded models become a
ratchet for "import broke after Spansh added a field". The current
duck-type-and-skip philosophy is correct for this workload.

### 5.4 Multiprocessing → asyncio for `build_grid` / `build_ratings` workers

The current `multiprocessing.Queue` + `Process` pattern is genuinely
the right shape for CPU-bound rating computation. Async would add
threading complexity for zero CPU win.

### 5.5 Add an ORM (SQLAlchemy / Tortoise)

The api uses raw asyncpg with hand-written SQL because the queries
are spatial / heuristic / cache-aware. An ORM would force every query
through a row-by-row layer that destroys the COPY / batch / partial-
index patterns the importer relies on.

---

## 6. Prioritisation matrix

Sorted by **ROI** (impact ÷ effort × inverse-risk):

| # | Recommendation | Effort | Impact | Verdict |
|---|---|---|---|---|
| 1 | § 3.1 Observability baseline (Prometheus + Grafana) | M | huge | **ship** |
| 2 | § 1.2 `pg_stat_statements` + nightly slow-query log | S | huge | **ship** |
| 3 | § 3.5 Daily `pg_dump` to off-host storage | M | huge (disaster recovery) | **ship** |
| 4 | § 3.3 Redis status-cache key pinning | S | medium | **ship** |
| 5 | § 1.6 Index hygiene (3 adds, 2 drops) | M | medium | **ship** in stages |
| 6 | § 3.2 Healthchecks.io ping in certbot_renew | XS | small but free | **ship** |
| 7 | § 2.5 `httpx.AsyncClient` reuse in inara_api | XS | small | **ship** |
| 8 | § 2.6 `flock` in nightly_update.sh | XS | small | **ship** |
| 9 | § 2.3 TypedDict for score functions | S | small (regression net) | **ship** |
| 10 | § 1.1 Convert text-enums to PG enum types | S | small | **ship** alongside §1.2 |
| 11 | § 4.1 score_military rebalance | S | changes user-visible ranking | **owner-decision** |
| 12 | § 1.5 Universal `created_at` columns | S | very small | **defer** to schema-hygiene v2.1 |
| 13 | § 3.4 nightly_update into maintenance container | M | small | **defer** until § 3.1 lands |
| 14 | § 1.3 `system_ratings_v` view | L | depends on § 4 | **defer** |
| 15 | § 4.2 Move score_* into apps/shared | M | depends on importer phase 5 | **defer** |
| 16 | § 1.4 Partition `bodies` | XL | small | **skip** until > 5 B rows |
| 17 | § 2.2 Replace progress.py with tqdm | S | none | **skip** |
| 18 | § 2.4 psycopg2-pool | S | none | **skip** |

If you action **just the top 4** (observability + pg_stat_statements +
backups + cache pinning), you have a fundamentally more reliable
system within 3 days of focused work. The rest is incremental polish.

---

## 7. What I want from you

Same shape as `docs/IMPORTER_MODULARISATION.md` § 7 — answer at your
leisure, no rush:

1. **Are any of the top 4 ROI items (rows 1-4) approved to start?**
   I'd recommend doing them in PR-order so each can be reviewed
   independently.
2. **§ 4.1 score_military rebalance — yes / no / not now?**
3. **Anything in § 5 (anti-recommendations) you actually want IN
   scope?**
4. **Anything I missed?** This list is what I noticed; you may have
   ideas of your own. Add them as comments on this PR.

Reviewing this PR commits us to nothing. Merging it just lands the
doc in `main` so future-us can find it without trawling chat history.
