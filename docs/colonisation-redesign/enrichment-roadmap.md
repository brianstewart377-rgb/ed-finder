# EDSM station enrichment — production roadmap & runbook

> **Audience:** anyone running the guarded EDSM station enrichment on the
> Hetzner production host (or a staging clone), or extending the importer/guard
> code in this repo.
>
> **Scope:** the apply path that writes verified `stations.station_type`,
> `stations.distance_from_star`, `stations.body_name`, and confirmed
> `station_body_links` rows from EDSM. Ring enrichment lives in the same
> importer entrypoint but follows a separate Spansh-first contract.

This file is the source of truth for how we run station enrichment safely at
scale. If a procedural step in this document conflicts with what you see in
the code, the code wins — please update this doc in the same PR.

---

## 1. Components

| Path | Role |
|---|---|
| `apps/importer/src/enrich_system_data.py` | Importer entrypoint. Implements the dry-run / metadata-apply / confirmed-link-apply contract per system. Emits a single JSON report on stdout, progress on stderr, and writes the database via `apps/importer/src/edsm_station_enrichment_probe.py`. |
| `apps/importer/src/edsm_station_enrichment_probe.py` | The actual EDSM HTTP client + change planner. Owns identity matching, conflict classification, the trust-and-hold rules for `distance_from_star`, and the rate-limit retry loop. |
| `scripts/station_enrichment_guard.py` | Production wrapper. Runs the importer in a docker-compose `importer` service, validates each phase JSON, gates apply behind safety analysis, writes per-batch artifacts, and maintains the resumable all-records checkpoint. **Never** call the importer directly in production — use the guard. |
| `scripts/run_station_enrichment_guarded.sh` | One-line shell shim around the guard so cron/Hetzner systemd timers can invoke it without remembering the python path. |
| `scripts/station_enrichment_status.py` | Read-only status helper. Inspects the latest run output dir and the checkpoint without touching EDSM or the database. |
| `tests/test_edsm_station_enrichment_probe.py` | Importer-level unit tests (no live EDSM). |
| `tests/test_station_enrichment_guard.py` | Guard-level unit tests with fake command runners (no docker, no live EDSM). |
| `tests/test_station_enrichment_status.py` | Status helper unit tests. |

---

## 2. Safety invariants the guard upholds

These are **hard contracts**. If any of them looks wrong in a live run, stop
the run and report it before re-running.

1. **Single source of truth.** Trusted writes always carry
   `source = "edsm_system_api"` and
   `confidence = "exact_station_identity"`. Anything weaker is a bug.
2. **Identity gate.** A station must match by EDSM id/marketId AND name before
   any column is updated.
3. **Trust-and-hold for `distance_from_star`.** Once a station's distance is
   already at trusted EDSM/exact provenance we **never** replan a distance
   update, even when the live EDSM value drifts. Orbital stations show
   natural `distanceToArrival` jitter between EDSM refreshes; replanning would
   re-touch the column on every nightly run. Population (NULL → value) and
   replacement of untrusted legacy distances still happen.
4. **Permanent station types only.** `Unknown` may be promoted to a known
   permanent type (Orbis, Coriolis, Asteroid Base, …). Carriers and other
   transient stations are ignored — never written.
5. **Risky conflicts block apply.** `id_name_mismatch`,
   `known_station_type_mismatch`, `station_economy_mismatch` and any
   `*_unsafe` write-safety marker abort the apply phase. The guard refuses to
   continue.
6. **Final dry-run validates writes.** When the guard applied any metadata or
   confirmed-link write it reruns a final dry-run and asserts that
   `metadata_updates_planned == 0` and `confirmed_link_updates_planned == 0`.
   No-op batches skip this re-fetch (see §4).
7. **Success-only checkpointing.** Only systems that returned a non-failed
   station report are appended to the resumable checkpoint. Systems that
   tripped a fetch / rate-limit error are deliberately left off the
   checkpoint so a later batch retries them.

---

## 3. Resumable checkpoint contract

Long `--all-records` runs are batched (default `--batch-size 2000`). Each
batch is a full guarded sequence (`initial dry-run → metadata applies →
confirmed-link apply → final dry-run`) restricted to the next batch of
systems that are not yet on the checkpoint.

### Default checkpoint path

If `--checkpoint-file` is **not** provided, the guard uses

```
/tmp/edfinder-station-enrichment/all-records-station-enrichment-checkpoint.json
```

This path is stable across runs by design: a second invocation resumes from
the first one's checkpoint instead of starting from scratch. The guard prints
the resolved checkpoint path at run start so the operator can verify it. To
override this for staged production runs, pass `--checkpoint-file
/path/to/your-state.json`.

### What goes into the checkpoint

```json
{
  "processed_system_id64s": [<sorted, deduplicated successful ids>],
  "last_system_id64": <max of the above>
}
```

The guard **only** appends to `processed_system_id64s` when the batch's
guarded sequence finishes cleanly **and** the system did not appear under
`stations.systems_fetch_failed` / `stations.fetch_errors`. Failed systems are
left for the next batch.

### Failure handling

* If a batch contains some failed systems and some successful ones, the
  successful ones are checkpointed and the run continues with the next batch.
  The failed system ids will reappear in the next batch's eligible set
  because they are still missing trusted provenance.
* If **every** system in a batch fails (typical EDSM outage / rate-limit
  storm), the guard logs a clear "all-records aborted" message and exits.
  The checkpoint stays exactly as it was so the next run resumes from the
  same point. **Do not** delete the checkpoint to "force a retry"; that would
  redo every previously-processed system.

---

## 4. No-op batch handling

If the initial dry-run for a batch reports zero metadata updates and zero
confirmed-link updates, the guard treats the batch as a clean no-op:

* No metadata apply runs.
* No confirmed-link apply runs.
* **No final dry-run is re-fetched.** A second EDSM round-trip on a clean
  batch costs rate-limit budget and risks reintroducing spurious live deltas
  (notably `distanceToArrival` jitter for orbiting stations).
* The batch's successful system ids are still checkpointed.

When a metadata or confirmed-link apply *did* run in the batch, the final
dry-run re-fetch is unconditional and its zero-plan assertion is the
acceptance test for the writes.

---

## 5. EDSM rate-limit handling

The probe enforces a layered defence:

1. **Per-request retry budget** — `--edsm-retries` (default 3) attempts per
   endpoint. Non-429 errors use the exponential `--edsm-retry-backoff-seconds`
   ladder.
2. **Retry-After floor** — when EDSM returns a 429 with a Retry-After header
   we honour it but clamp it to `EDSM_MIN_RETRY_AFTER_SECONDS` (default
   **5 seconds**). EDSM occasionally answers with very short Retry-Afters
   (1–2 s); obeying them literally guarantees another 429 on the next call.
3. **Configured backoff floor** — when no Retry-After header is present the
   probe falls back to `--edsm-429-backoff-seconds` ×
   `--edsm-429-backoff-multiplier^attempt`, then clamps the result up to the
   same 5 s floor.
4. **Repeated-429 escalation** — the guard mirrors importer stderr live and
   counts consecutive rate-limit log lines per phase. After 3 in a row it
   prints a one-shot warning recommending a higher
   `--edsm-429-backoff-seconds` / `--edsm-request-delay-seconds`, or aborting
   and resuming later. The checkpoint is preserved either way.

If you see the warning more than once per run, **abort and let EDSM cool
down** rather than turning up the dials further; we are part of a wider EDSM
load-shedding window in that case.

---

## 6. Observability

While a run is in flight the guard now streams importer stderr live to its
own stderr, line-by-line, so the operator can watch per-system progress in
real time. Each batch persists:

* `01_initial_dryrun.json[.stderr.txt]`
* `02_metadata_apply_*.json[.stderr.txt]` (if any apply ran)
* `03_after_metadata_*_dryrun.json[.stderr.txt]`
* `04_confirmed_links_apply.json[.stderr.txt]` (if any apply ran)
* `final_dryrun.json[.stderr.txt]` (skipped on no-op batches)

The guard prints a compact summary line per phase with the counters spec
asked for:

```
initial dry-run: systems_processed=N metadata_updates=M confirmed_links=L
                 conflicts=C skipped=S fetch_errors=F systems_fetch_failed=K
                 suppressed_station_writes=W ignored_transient_non_slot=I
                 dirty_marked/planned=D/P file=...
```

To inspect run state from a separate shell (or to feed into nagios/an
operator dashboard) use `scripts/station_enrichment_status.py`:

```sh
# Default: stable all-records checkpoint, default output root.
python3 scripts/station_enrichment_status.py

# Ask whether a specific system has already reached the checkpoint.
python3 scripts/station_enrichment_status.py --system-id64 9472415114065

# Machine-readable for cron/email.
python3 scripts/station_enrichment_status.py --json
```

---

## 7. Hetzner production runbook

Run from the host as the deploy user, with the docker-compose `import`
profile already provisioned (the guard executes
`docker compose --profile import run --rm -T importer ...` for every phase).

### 7.1 Smoke check (always do this first)

```sh
cd /opt/ed-finder
# Process at most 2 systems, never apply. Confirms the importer + guard pipeline
# and the EDSM connectivity path without touching the database.
python3 scripts/station_enrichment_guard.py --limit 2 --dry-run-only
```

Expect: a fresh dir under `/tmp/edfinder-station-enrichment/`, an
`01_initial_dryrun.json`, a `final_dryrun.json` if any apply ran (it won't,
because of `--dry-run-only`), and a one-line summary per phase. No errors on
stderr.

### 7.2 Bounded apply

```sh
cd /opt/ed-finder
# Apply on a small slice. If anything goes wrong only N stations are touched.
python3 scripts/station_enrichment_guard.py --limit 100 --yes
```

Inspect:
* Last `final_dryrun.json` should have `metadata_updates_planned == 0` and
  `confirmed_link_updates_planned == 0`.
* `summary.stations.fetch_errors` and `summary.stations.systems_fetch_failed`
  are 0 on a healthy run.

### 7.3 Resumable all-records run

```sh
cd /opt/ed-finder
nohup python3 scripts/station_enrichment_guard.py \
    --all-records \
    --batch-size 2000 \
    --max-batches 50 \
    > /var/log/edfinder/station-enrichment.$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
```

Notes:
* No `--checkpoint-file` is needed: the guard uses the stable default at
  `/tmp/edfinder-station-enrichment/all-records-station-enrichment-checkpoint.json`.
  If you want the checkpoint to survive `/tmp` cleanup across reboots, point
  at a path under `/var/lib/edfinder/state/` instead.
* `--max-batches` keeps any single shell session bounded; re-running with the
  same default checkpoint resumes where the previous session stopped.
* Use `tail -f` on the log file (or
  `python3 scripts/station_enrichment_status.py --json --output-root
  /tmp/edfinder-station-enrichment`) for live progress.

### 7.4 Healthy-day rate-limit knobs

For a quiet EDSM window the defaults are appropriate. When EDSM is hot you
can either:

```sh
# Slow the request cadence and increase the no-Retry-After backoff.
python3 scripts/station_enrichment_guard.py --all-records \
    --edsm-request-delay-seconds 1.5 \
    --edsm-429-backoff-seconds 120
```

…or pause the run, wait, and restart — the checkpoint is preserved either
way.

### 7.5 What to do on the warnings the guard prints

| Guard message | Operator action |
|---|---|
| `[guard] EDSM 429 observed N times in this phase; consider raising --edsm-429-backoff-seconds…` | If first time in a run: keep going, the backoff floor will absorb it. If repeated: abort, raise the delays, restart later. |
| `all-records batch X: skipping checkpoint append for systems_fetch_failed=N` | Expected when EDSM blips. Those systems will be retried in the next batch. |
| `all-records aborted: every system in this batch hit a fetch/rate-limit error` | EDSM is degraded. Stop the run, investigate, retry later. The checkpoint stays accurate. |
| `Guard failed: ... blocked by safety gate` | Safety net tripped. Inspect the most recent `*_dryrun.json` for `conflicts` and `metadata_updates_planned`. **Do not** force-apply by editing the JSON. |

### 7.6 Recovery from a partial / interrupted run

The guard never deletes the checkpoint. If you `Ctrl+C` mid-batch the
already-completed batches are recorded; the in-flight batch is lost (its JSON
files remain on disk for inspection but no rows from it were checkpointed
unless they were applied successfully before the interruption). Re-run with
the same arguments and the next batch resumes from the next un-processed
system id64.

---

## 8. Body/Ring Enrichment Input Strategy

Body/ring enrichment should be planned around explicit input modes. The
planner must remain pure: it receives local body/ring rows and external
source rows, then returns a `body_ring_enrichment_dry_run/v1` report. The
planner must not perform network access and must not write to the database.

### 8.1 Input modes

| Input mode | Best use | Limits / cautions |
|---|---|---|
| JSON fixtures / offline samples | Unit tests, deterministic examples, trust-classification edge cases, and CI. | Fixtures are not enough to prove SQL joins, schema compatibility, null/enum behaviour under real database adapters, or production-scale performance. |
| Non-production DB | Integration testing against the real schema, joins, null handling, enum handling, and migrations. | Safer than production, but slower and more complex than fixtures. It should still use offline source data, not live enrichment APIs. |
| Existing local production tables | Production dry-runs using the real local source of truth. Required for galaxy-scale validation because it exercises the actual body/ring population and current trust state. | Must remain read-only in this warehouse path. Use only for dry-run reads and report generation. |
| Offline snapshots / staging data | Preferred external source for large-scale enrichment and repeatable validation. | Needs a parser/normaliser and versioned snapshot handling, but gives stable inputs, batchability, and rerunnable reports. |
| Live APIs | Small manual diagnostics only, if ever needed outside this planner contract. | Avoid for large all-record enrichment: rate limits, latency, upstream volatility, and poor repeatability make them unsuitable for deterministic galaxy-scale planning. |

### 8.2 Scalable architecture

The long-term architecture should be:

```text
external snapshot/file
-> source parser/normaliser
-> staging model or in-memory source rows
-> read-only local DB fetch
-> pure planner
-> versioned dry-run report
-> separately designed write path only if explicitly approved later
```

For production scale, the preferred path is existing local tables plus
offline source snapshots plus checkpointed batching. That lets us validate
the real galaxy-sized local dataset without coupling the dry-run to live API
availability or upstream drift.

For development and testing, the robust path is JSON fixtures plus
non-production DB integration tests plus production read-only dry-runs.
Fixtures keep planner behaviour deterministic; the non-production DB proves
schema and join compatibility; production read-only dry-runs prove scale and
real-data classification without modifying rows.

### 8.3 Staged implementation

1. **Stage A: JSON fixture CLI mode.** Accept fixture files and emit
   `body_ring_enrichment_dry_run/v1` with no database or network dependency.
2. **Stage B: read-only non-production DB mode.** Fetch local rows from a
   staging/test database and combine them with offline source rows to prove
   joins, migrations, null handling, and enum handling.
3. **Stage C: production read-only dry-run.** Read existing local production
   tables and offline snapshots only, use checkpointed batching for scale, and
   write versioned reports without touching production data.
4. **Stage D: future write-path design review.** Keep this out of the current
   warehouse implementation. Any canonical writes need a separate proposal,
   safety review, and test plan after dry-run reports are boring and
   predictable.

### 8.4 Body/ring trust model

The body/ring planner must preserve the current trust distinction:

* Source-only `body_scan_facts.is_ringed = True` remains unknown until it is
  resolved to trusted local `body_rings` rows.
* Source-only `False` may represent explicit trusted no-rings according to the
  existing tests.
* Trusted local-matched `body_rings` rows are required before promoting a body
  to confirmed ringed state.

## 8.5 Offline enrichment warehouse foundation

The first warehouse foundation is documented in
`docs/colonisation-redesign/enrichment-staging-architecture.md` and implemented
by:

| Path | Role |
|---|---|
| `sql/026_enrichment_staging_foundation.sql` | Additive source-run, raw-record, normalised staging, and derived dry-run intelligence tables. |
| `apps/importer/src/enrichment_staging.py` | Pure canonicalisation, hashing, source classification, validation, and report skeleton helpers. |
| `apps/importer/src/enrichment_snapshot_loader.py` | Offline-only local JSON/JSON.GZ loader for EDSM station and body/ring snapshot-style records. |
| `apps/importer/src/enrichment_staging_db_loader.py` | Explicitly gated staging-only DB loader, schema preflight, staged-row reports, and read-only reconciliation CLI. |
| `apps/importer/src/enrichment_warehouse.py` / `apps/importer/src/enrichment_warehouse_repository.py` | Warehouse boundary, SQL safety checks, and repository-backed access to warehouse tables. |
| `apps/importer/src/enrichment_write_plans.py` | Pure staging write-plan builders used before DB execution. |
| `apps/importer/src/enrichment_reconciliation.py` / `apps/importer/src/enrichment_reconciliation_scoring.py` | Read-only candidate shaping and report-only confidence/risk scoring. |
| `apps/importer/src/enrichment_analytics.py` | Pure report-only analytics, colonisation, and mission-density signal scaffolds. |
| `tests/fixtures/edsm_station_snapshot.json` | Tiny deterministic EDSM station snapshot fixture. |
| `tests/fixtures/edsm_body_ring_snapshot.json` | Tiny deterministic EDSM body/ring snapshot fixture. |
| `tests/test_enrichment_staging.py` / `tests/test_enrichment_snapshot_loader.py` | Fixture-backed tests for hashes, source classes, report versions, JSON/GZIP loading, source metadata, skipped rows, duplicates, unsupported shapes, and deterministic output. |

This warehouse path is deliberately not wired into any operations job. It does
not call EDSM, invoke Docker, connect to production Postgres, run migrations,
update canonical station/body/system rows, or create station-body links. The
default mode emits `enrichment_snapshot_load_plan/v1` dry-run reports only.
Staging DB writes are opt-in and require `--write-staging`, `--dsn`, and
`--confirm-staging-db`; they target only the enrichment warehouse tables.

Run the local fixture loader from the repo root:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source edsm_nightly_stations \
    --source-file tests/fixtures/edsm_station_snapshot.json \
    --json
```

Use `--limit N` for bounded inspection of larger local snapshots. `--dry-run`
is the default. `--apply`, `--write`, and `--commit` fail closed.

The current warehouse also supports local body/ring snapshots through
`--source edsm_nightly_bodies`, read-only reconciliation via
`--report-reconciliation`, staged-row summaries via `--report-staged-run`, and
pure report-only analytics/signals. Optional real-Postgres smoke tests for the
staging loaders and reconciliation are skipped by default unless
`EDFINDER_STAGING_TEST_DSN` and `EDFINDER_CONFIRM_STAGING_TEST_DB=yes` are set.

Stage 18D keeps this path report-only while making snapshot inputs more
explainable: reports expose source format/version, record stream shape,
source timestamp/freshness summaries, skipped-row reason distributions,
duplicate source-record hashes, report-only source-identity conflicts, and
body/ring ring-array evidence. Missing ring arrays remain unknown, source-only
ring evidence remains source-only, and future nested body source shapes are
reported as unsupported until a dedicated adapter exists.

Stage 18E adds a versioned `warehouse_coverage_report` section to read-only
reconciliation output. It is for operator review of evidence completeness:
station coverage by system, missing station evidence where body/ring evidence
exists, trusted versus unknown ring evidence, explicit trusted no-ring scan
evidence, confirmed/inferred/unresolved station-body links, stale or undated
source evidence, skipped/malformed source rows, duplicate source-record hashes,
source identity conflicts, high-value systems needing better evidence, and
source type/source-format coverage. It remains dry-run/report-only and does
not promote source-only evidence to canonical truth.

Stage 18F hardens reconciliation confidence as a versioned, report-only model.
Candidates now carry deterministic confidence levels, reason codes, source
freshness impact, risk classes, review classifications, and future canonical
review markers that explicitly disable auto-promotion. These labels explain
confirmed, inferred/verify, unresolved, source-only, stale, volatile, blocked,
report-only, and unknown states for operator review only; they do not change
planner scoring, canonical write eligibility, or any production job wiring.

Stage 18G exposes warehouse run and evidence status in the token-gated Admin
surface. The API reads only a configured, prepublished JSON artifact and
returns sanitized counts for latest snapshot/reconciliation state, source
coverage, unresolved/risky/blocked/stale evidence, skipped or duplicate source
records, and canonical-safety flags. Missing or invalid artifacts remain
unavailable/unknown; the panel does not run warehouse scripts, query the
warehouse, call live APIs, or add write controls.

Stage 18H adds a read-only warehouse-to-planner evidence bridge. It lets the
Colony Planner present selected warehouse/report-only evidence as evidence, not
truth. Because the Stage 18G warehouse artifact is admin-token-gated and
aggregate-only (it carries review counts, not per-`system_id64` rows), there is
no safe key to link warehouse evidence to a planner system yet. Per the stage
decision gate, Stage 18H ships the conservative path: a typed read-only
`PlannerWarehouseEvidence` model, a compact source-labelled planner card that
defaults to a safe unavailable/unknown state, tests proving the unavailable
state and no-mutation guarantee, and a design doc with the future per-system
integration path
(`docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md`).
It adds no backend endpoint, makes no live calls, and never mutates planner,
Build Plan, role, observed-evidence, validation, scoring, Preview, optimiser, or
canonical state.

Stage 18I documents the canonical-write design review without implementing any
write path. It defines future candidate write paths, evidence-only and banned
paths, source/confidence requirements, audit and rollback requirements,
operator approval, table risks, safety blocks, and required tests. Its
conclusion is conservative: no canonical writes are authorized, Stage 18I.5
must decide the warehouse database boundary first, and any Stage 18J pilot
should start with exact station type promotion only. See
[`stage-18i-canonical-write-design-review.md`](./stage-18i-canonical-write-design-review.md).

Stage 18I.5 documents the warehouse database boundary decision without
implementing it. It recommends a separate `edfinder_enrichment` database on the
same Postgres stack if feasible, preserves a future path to a separate Postgres
instance, defines role/permission boundaries, snapshot/read-only comparison,
write-plan transfer, audit ownership, retention, and Stage 18J readiness
criteria. See
[`stage-18i5-warehouse-database-boundary-review.md`](./stage-18i5-warehouse-database-boundary-review.md).

Stage 18T hardens the canonical safety test environment for Stage 18J-class
work. It adds a dedicated CI job, explicit test prerequisites, a one-command
local runner, and disposable Postgres rehearsal/permission-boundary coverage
for the guarded station type pilot. It does not authorize production apply,
artifact approval, production DB access, or wider canonical backfill. See
[`stage-18t-canonical-safety-test-environment.md`](./stage-18t-canonical-safety-test-environment.md).

The operator workflow and current command examples live in
[`../operations/enrichment-warehouse-runbook.md`](../operations/enrichment-warehouse-runbook.md).
Use that runbook before loading any local snapshot into staging tables.

This is the long-term replacement direction for large live API crawls: load
repeatable offline snapshots into raw/staging evidence, compare read-only
against canonical ED-Finder tables, produce pure versioned dry-run plans, and
keep warehouse output report-only unless a separate canonical write design is
approved later.

---

## 9. Roadmap

The list below is intentionally narrow — anything not on it should be
treated as a separate proposal.

* **Status integration hardening**: keep the station and warehouse Admin tab
  status artifacts mounted from operator-managed paths, and add deployment
  alerts around missing or stale artifacts if production operations need them.
* **Sticky failed-system retry queue**: today, fetch-failed systems naturally
  re-enter the next batch because they have no trusted provenance yet. If
  that becomes too slow for very large outages, materialise a separate
  retry queue (with its own backoff schedule) instead of pulling them in
  via the regular eligible-station SQL.
* **PostgreSQL-backed checkpoint**: the JSON file is fine for one-host ops.
  When we move to multi-host nightly enrichment we should put the
  checkpoint in Postgres (`enrichment_progress` table) so multiple workers
  can coordinate without stepping on each other.
* **Optional `--retry-failed` mode**: a second top-level mode that only
  re-runs the systems that appeared in any historical `systems_fetch_failed`
  list, with a tighter rate-limit profile.
* **Ring enrichment guarded mode**: parity wrapper for the Spansh-first ring
  enrichment, sharing the same checkpoint discipline.
* **Warehouse reconciliation hardening**: broaden read-only reconciliation
  quality checks across staged station, body, and ring evidence while
  preserving `distanceToArrival` as volatile evidence instead of a churn
  source.
* **Report-only analytics maturation**: improve confidence/risk explanations,
  source coverage summaries, colonisation signals, and mission-density signals
  without writing canonical data.
* **Optional smoke coverage**: keep real-Postgres smoke tests skipped by
  default and focused on staging tables plus read-only reports.

---

## 10. Suggested local test commands

These all run offline; they never touch EDSM or the production database.

```sh
# Importer probe (distance trust-and-hold, 429 floor, identity gating, …)
python3 -m pytest tests/test_edsm_station_enrichment_probe.py -q

# Guard wrapper (checkpoint, no-op skip, success-only checkpointing, …)
python3 -m pytest tests/test_station_enrichment_guard.py -q

# Status helper
python3 -m pytest tests/test_station_enrichment_status.py -q

# All three together
python3 -m pytest \
    tests/test_edsm_station_enrichment_probe.py \
    tests/test_station_enrichment_guard.py \
    tests/test_station_enrichment_status.py -q
```
