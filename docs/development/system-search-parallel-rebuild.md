# Parallel chunk-range workers for V3 Search

This change adds a bounded parallel builder for the Finder F1 `system_search`
product. It is code and disposable-database validation, not authorization to
access production, replace the running worker, apply a production migration, or
publish a generation. No production database or real rebuild was used for this
work. The rollout below is a proposed, owner-gated procedure and was not run.

The current branch already decouples the map density pyramid from Ratings/Search:
[the roadmap](../ROADMAP.md) and migration
[`012_v3_spatial_pyramid_decouple.sql`](../../sql/v3/migrations/012_v3_spatial_pyramid_decouple.sql)
give it a canonical-generation lifecycle and independent publication. Search
completion remains relevant to Finder F1 and derived-generation publication; it
is no longer the pyramid's publication prerequisite in this codebase.

## Investigation: the existing serial builder

[`scripts/v3_system_search.py`](../../scripts/v3_system_search.py) owns Search
registration, projection, checkpoint receipts, and validation. The existing
production launcher is
[`scripts/operator/actions/v3-system-search-f1.sh`](../../scripts/operator/actions/v3-system-search-f1.sh).
It launches one worker with `--follow --poll-seconds 5`, verifies a specific
deployment and generation, and uses pinned Psycopg 3.3.4. That operator authority
is unchanged by this work; the script was inspected, not executed.

Search uses **existing committed Ratings chunk ordinals**, not numeric id64
intervals, `OFFSET`, or an independently generated work list. Ratings streams
the retained artifact in source order, assigning successive `chunk_ordinal`
values. Its default chunk size is 500 systems, with hard bounds of 1,000 systems
and 100,000 canonical bodies. Therefore adjacent chunks need not represent
adjacent id64 values. `system_rating_vector` assigns every unique
`(derived_generation_id, system_id64)` to one chunk; the
`(derived_generation_id, chunk_ordinal)` index supports chunk reads.

The baseline serial sequence is:

1. Register or verify an immutable `v3_meta.derived_product` manifest for
   `system_search`. The manifest pins the canonical generation/schema,
   publication sequence, expected systems, projection policy, and source hashes.
2. Read committed `v3_derived.build_chunk` receipts missing a corresponding
   `v3_derived.search_build_chunk`, ordered by ordinal. The baseline loads that
   missing-chunk list into memory; `--max-chunks` limits writes, not discovery.
3. For one chunk, take a `FOR UPDATE` lock on the Search product, recheck its
   lifecycle and manifest, then check for an existing Search receipt.
4. Use one parameterized `INSERT ... SELECT` to project the chunk's systems from
   the pinned canonical relations, Ratings vectors, and body mechanics. It is
   insert-only, with no upsert. A transaction-local `jit=off` retains the existing
   bounded-query optimization.
5. Verify the inserted row count, hash the ordered projected contents, and insert
   a Search chunk receipt in the **same transaction**. A commit publishes both
   rows and receipt to other sessions; a failure rolls back both.
6. Validate total coverage, contiguous Ratings ordinals, receipt source/version
   seals, and cube/numeric-coordinate agreement before marking Search `READY`.
   Neither builder publishes the derived generation.

A resumed matching receipt skips the chunk. A receipt with different source,
version, or coverage fails; existing Search rows without a receipt also fail.
The baseline accepts a base generation in `BUILDING`, `VALIDATING`, or `READY`
so that `--follow` can consume newly committed Ratings chunks.

The important bottleneck is the baseline's product-row `FOR UPDATE`: it spans
the projection, digest, and receipt transaction. Additional unchanged serial
processes contend for that same row even when targeting different systems.

### F1 body-composition fields

Migration
[`010_v3_system_search_body_type_counts.sql`](../../sql/v3/migrations/010_v3_system_search_body_type_counts.sql)
adds these 18 integer fields:

| Fields | Existing projection policy |
| --- | --- |
| `elw_count`, `ww_count`, `ammonia_count` | Normalized body-mechanics class matches for Earth-like, water, and ammonia worlds. |
| `terraformable_count` | Body-mechanics rows marked terraformable. |
| `gas_giant_count`, `hmc_count`, `metal_rich_count` | Normalized gas giant, high metal content, and metal rich classes. |
| `rocky_count`, `rocky_ice_count`, `icy_count` | Normalized rocky, rocky ice, and icy classes. |
| `black_hole_count`, `neutron_count`, `white_dwarf_count` | Body class or spectral-class matches. |
| `other_star_count` | Rows with a spectral class, excluding the preceding three groups. |
| `ring_count` | Active canonical `RING` rows; asteroid belts are excluded. |
| `walkable_count` | Active landable bodies with absent/no atmosphere; bounded by `landable_count`. |
| `bio_signal_total`, `geo_signal_total` | Biological/geological signal totals on active canonical bodies. |

The parallel path calls the same projection and digest functions. Zero remains
"no positive observation in the pinned input," not proof of absence. Existing
`body_count`, `landable_count`, flags, confidence, and completeness retain their
serial definitions.

## Parallel design

[`scripts/v3_system_search_parallel.py`](../../scripts/v3_system_search_parallel.py)
provides `prepare`, `work`, `finalize`, and `run`. Migration
[`013_v3_system_search_parallel.sql`](../../sql/v3/migrations/013_v3_system_search_parallel.sql)
adds shared scheduler metadata:

| Relation | Purpose |
| --- | --- |
| `v3_meta.search_rebuild_plan` | One pinned plan per derived generation: Search manifest hash, scheduler hash, range count, and total chunks. |
| `v3_meta.search_rebuild_range` | One half-open ordinal range `[first_chunk, end_chunk)` and its committed `next_chunk` cursor. |
| `v3_derived.search_build_chunk` | Existing immutable per-chunk source/content receipt; still the materialization authority. |

The new scheduler requires an **unpublished `READY` Ratings generation** and a
compatible Search product. Preparation verifies Ratings ordinals are contiguous
from zero and their system counts equal the expected generation coverage. This
freezes a complete source space; the parallel command has no follow mode.

For `C` chunks and `N` ranges, range `i` is
`[floor(i*C/N), floor((i+1)*C/N))`. The partition has no gaps or overlap. Since
each Ratings vector belongs to exactly one ordinal, the ranges also partition
systems even when id64 values interleave. Bounds are 1–64 ranges, at most the
number of chunks, and at most 2,147,483,647 chunks. A batch remains one Ratings
chunk, bounded to 1,000 systems. Progress queries read a bounded range set and
one source receipt at a time.

Each worker owns its own direct Psycopg connection. Within each chunk transaction
the lock order is base generation `FOR SHARE`, Search product `FOR SHARE`, range
checkpoint `FOR UPDATE`, then source chunk `FOR NO KEY UPDATE`. The shared
lifecycle locks permit different ranges to project concurrently while excluding
incompatible state changes. The source-receipt lock also coordinates same-chunk
calls through the updated serial path; `NO KEY UPDATE` is compatible with the
deferred foreign key's key-share check.

The common serial `_insert_chunk` now uses shared lifecycle locks and the
per-source-chunk lock instead of the global exclusive product lock. Search rows,
content receipt, and range-cursor advancement commit together. Its nested
transaction is a savepoint inside the worker's outer transaction, not an
independent commit. Duplicate invocations of the same range serialize on its
checkpoint and reread the advanced cursor. A crashed connection releases its
locks automatically; there are no durable leases or stale-owner repairs.

`prepare` is idempotent for the same plan. Changing `N`, projection identity, or
scheduler identity fails closed. The scheduler identity hashes the parallel
script and migration 013; the Search manifest continues to hash the serial
script and migrations 004/006/010. A resume requires the same artifact bytes and
input identity. The command does not rewrite manifests or old receipts.
The hashed Search scripts and migration sources are pinned to LF in
`.gitattributes` so a Windows checkout does not change their byte identities.

`finalize` takes the existing publication advisory lock, base lifecycle lock,
and exclusive Search product lock before checking that all range cursors are at
their ends. This waits for active chunks and fences new writes during the
existing full Search validation. Incomplete ranges return `INCOMPLETE`; complete
valid coverage reaches `READY`. `run` prepares, starts one worker per range,
joins them, then finalizes once. A process failure can leave already committed
work from other ranges; restart the same plan to continue.

## Bulk-write and concurrency safety

The implementation follows
[`bulk-database-write-safety.md`](bulk-database-write-safety.md). Its writes are
derived Search inserts, immutable receipts, and scheduler metadata. It does not
update canonical `systems`, `bodies`, clusters, or ratings. Adjacent code comments
explain why the replica-mode helper is not used: foreign-key, insert-only, and
lifecycle triggers **must remain enabled**. The parallel entry points reject a
connection unless `session_replication_role` is `origin`, isolation is
`read committed`, and the connection is idle/autocommit before explicit batch
transactions. Autocommit here does not make the batch nontransactional.

Values are DB parameters; the validated canonical schema is quoted with Psycopg
`Identifier`. CLI inputs are bounded, the DSN has no fallback, and
`--expected-database` must match the connected database. The CLI requires
CPython 3.14 and Psycopg 3.3.4. A direct connection is required; transaction
pooling is outside the contract. The expected database name is an additional
check, not proof of host authorization: the owner must separately establish the
approved endpoint, credentials, and deployment identity.

Each chunk transaction has a 30-second lock timeout and 15-minute statement
timeout. A timeout fails the invocation and rolls back its current chunk. It
does not relax constraints or automatically retry forever. Final validation is
subject to the same statement timeout; a large-generation timeout requires
separate reviewed tuning, not bypassing validation.

Disjoint row keys remove same-system unique-key contention. They do **not**
provide independent storage or linear speedup:

- `system_search` maintains its generation/system primary key, global spatial
  GiST index, generation/name index, and generation/region index during every
  insert. Different id64 ranges can touch the same index pages or regions.
- Workers share heap extension, buffers, storage bandwidth, WAL generation,
  fsync/checkpoints, CPU, connection capacity, and canonical input reads.
  PostgreSQL execution parallelism can add further resource use per session.
- Autovacuum and autoanalyze still matter for insert-heavy tables, statistics,
  freezing, and the updated checkpoint rows. Failed transactions can leave dead
  tuples for vacuum. Keep transactions short and retain normal maintenance.
- The projection queries rely on Ratings chunk and canonical child-relation
  indexes. Measure their plans on a disposable representative workload before
  assuming more connections improve throughput.
- Do not drop indexes, disable triggers/FKs, suppress autovacuum, change global
  replication role, or perform table-wide cleanup to increase throughput.

Normal same-code serial chunk calls use the common per-chunk mutex, but running
the serial builder/validator alongside the parallel scheduler is **unsupported
and prohibited**. The serial validator acquires its product UPDATE lock before
its trigger obtains the publication advisory lock; parallel finalization takes
the advisory lock first. Mixing those lifecycle owners can deadlock. Only
quiescent same-code receipts may be resumed under a compatible parallel plan;
the supported running configuration has parallel workers and one parallel
finalization owner.

## Can workers join the currently running serial rebuild?

**No, this delivery cannot safely be attached to that running worker without a
separately reviewed transition.** This assessment is from source inspection; no
live process or production database was queried.

Unchanged extra serial processes take the same product `FOR UPDATE` lock, so
they serialize instead of providing the desired parallel chunk execution. The
running worker does not participate in the new fixed range plan or checkpoint
ownership. New code changes `scripts/v3_system_search.py`, whose complete hash is
part of the immutable Search manifest. Registration/resume against an existing
old-code product therefore rejects the new code. Scheduler preparation also
requires a `READY` Ratings base, rather than the serial follow path's broader
lifecycle allowance.

Do not edit the stored manifest/hash, pretend the old file hash describes new
code, disable immutability guards, reset checkpoints, or copy old Search
receipts. Their source seals bind the original manifest. Merely stopping the
serial worker does not resolve this identity mismatch. The old product can
continue under its original artifact. To use this implementation when the old
manifest differs, the supported rollout requires a **fresh Search product on a
compatible new unpublished Ratings generation**, prepared through the approved
Ratings-generation process and already `READY`. This code does not implement a
legacy-product adoption or in-place identity-upgrade procedure.

## Proposed owner-gated rollout — not executed

This procedure needs an owner-approved target, deployment, migration operation,
and resource budget. It is not a replacement production operator runbook.
Migration 013 is intentionally not added to the externally pinned production
migration manifest in this change; its declaration, hash/ledger verification,
schema-identity update, and application belong to a separately reviewed governed
migration operation. Existing operator allowlists and launchers are unchanged.

1. Review the branch artifact and disposable test evidence. Pin its exact commit,
   CPython 3.14 patch release, uv 0.11.33, `apps/api/uv.lock`, and Psycopg 3.3.4.
   Rehearse against disposable PostgreSQL 18 using representative chunk sizes
   and skew. Record baseline duration, rows/second, resource use, and query plans.
2. Obtain explicit owner authorization for the concrete deployment target,
   reviewed migrations, resource limits, and a fresh compatible generation.
   Verify host/database identity, direct DB access, backup/recovery readiness,
   required migrations 003/004/006/010 plus 013, and their approved ledger hashes.
   Review worker privileges for lifecycle row locks, derived inserts, and
   checkpoint updates without granting canonical-table mutation authority.
   Do not infer authorization from a database name or the existence of code.
3. Verify the selected Ratings generation is unpublished `READY`, its canonical
   source/sequence and expected rows match the review, and committed Ratings
   chunks cover the complete source. If an old incompatible Search product is
   already registered, stop this rollout: arrange a new compatible Ratings
   generation through its separate approved process. Leave old rows and receipts
   retained.
4. Choose the immutable range count `N` within both the available chunks and the
   approved connection/resource budget. Inject `V3_SYSTEM_SEARCH_DATABASE_URL`
   through approved secret handling, never shell history, logs, or checked-in
   files. Prepare one plan and retain its output and artifact identity.
5. Canary a small number of chunks per range, review committed receipts and
   resource impact, then resume the same plan. `run --max-chunks K` processes up
   to `K` chunks **per range**, not globally; its aggregate canary is at most
   `N*K` chunks. `INCOMPLETE` after a canary is expected. For a smaller initial
   concurrency budget, invoke `work` for only a chosen subset of range IDs.
6. Increase active concurrency only after reviewing measurements. Launch more
   of the already prepared range IDs; reduce it by stopping selected workers
   at chunk boundaries. Keep `N` unchanged. Do not delete/repartition a plan.
   Record which ranges are active so omitted ranges are eventually resumed.
7. After all workers finish, run a single finalizer, require its `VERIFIED`
   receipt and Search `READY`, and retain range/receipt coverage evidence.
   Publication and any application deployment remain separate existing
   owner-authorized operations; this builder performs neither.

The following commands are templates **only for a future owner-authorized
rollout**. Placeholder names must be replaced with the reviewed generation and
database; no actual production host or credentials are supplied. `uv` must use
the approved locked environment, and the DSN must already have been injected as
described above.

```sh
uv run --project apps/api --no-sync python scripts/v3_system_search_parallel.py prepare \
  --generation-key APPROVED_GENERATION_KEY --expected-database APPROVED_DATABASE --workers 4

# Canary at most two committed chunks per range, retaining the four-range plan.
uv run --project apps/api --no-sync python scripts/v3_system_search_parallel.py run \
  --generation-key APPROVED_GENERATION_KEY --expected-database APPROVED_DATABASE \
  --workers 4 --max-chunks 2

# Independent process for one existing range; repeat with reviewed range IDs.
uv run --project apps/api --no-sync python scripts/v3_system_search_parallel.py work \
  --generation-key APPROVED_GENERATION_KEY --expected-database APPROVED_DATABASE --range-id 0

# Resume all four existing ranges, then finalize once.
uv run --project apps/api --no-sync python scripts/v3_system_search_parallel.py run \
  --generation-key APPROVED_GENERATION_KEY --expected-database APPROVED_DATABASE --workers 4

# Alternatively, finalize after separately managed work processes finish.
uv run --project apps/api --no-sync python scripts/v3_system_search_parallel.py finalize \
  --generation-key APPROVED_GENERATION_KEY --expected-database APPROVED_DATABASE
```

The illustrative four ranges are not a production sizing recommendation. The
generation-key placeholder must be replaced with a lowercase key accepted by
the CLI. Plan size is not a throughput promise; a small disposable fixture
cannot establish speedup for a roughly 198.5-million-system rebuild.

### Monitoring, pause, and recovery

Track per-range `next_chunk - first_chunk`, remaining chunks, last `updated_at`,
receipt counts/system totals, batch latency, and aggregate progress rate.
Compare observed coverage with the immutable plan and generation expectations.
Monitor `pg_stat_activity` for the `v3-system-search-parallel` application name,
transaction ages, wait events, blockers/deadlocks and timeout errors, plus
`pg_stat_user_tables` vacuum/analyze progress and dead tuples. Monitor CPU,
memory, storage latency/free space, WAL rate, checkpoint pressure, replication
lag where applicable, connection usage, and serving-query latency. Prefer the
small receipt/checkpoint relations for routine progress checks; repeated full
counts of the Search table can themselves be expensive.

Before starting, the owner must set stop thresholds against the target's
baseline and service objectives for disk/WAL growth, replication lag, lock waits,
query latency, and resource saturation. Pause on a threshold breach, unexplained
coverage/hash mismatch, repeat timeouts, or increasing latency without aggregate
throughput improvement. Do not compensate by disabling safeguards.

For a planned pause, use bounded `--max-chunks` invocations and let active chunks
finish, or stop only the approved worker process using its approved control
mechanism. Check active transactions have ended before declaring the pause
complete. A forced worker loss rolls back only its in-flight transaction; other
workers may continue and commit. Inspect DB state instead of inferring completion
from a missing process or last log line.

Resume with the **same** artifact, generation, plan, and range IDs. Committed
cursors/receipts skip completed work; an aborted chunk is repeated atomically.
After an uncertain client/network outcome, reconnect and consult those durable
checkpoints. Do not decrement cursors, delete data, or reconstruct receipts by
hand. Source/manifest mismatches and orphan rows need investigation; rerunning
with relaxed guards is not recovery. If the exact artifact cannot be restored,
stop and obtain a separately reviewed migration/rebuild decision. An incomplete
Search product remains unpublished under the existing lifecycle guards.

## Disposable validation

Use exact CPython 3.14, uv 0.11.33, and the locked API test dependency graph; do
not resolve an independent Psycopg dependency. From the repository root, a
PowerShell reproduction is:

```powershell
uv --version  # Must be 0.11.33.
uv sync --project apps/api --frozen --group test --no-install-project --python 3.14
uv run --project apps/api --no-sync python -c "import platform, psycopg, sys; assert platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 14); assert psycopg.__version__ == '3.3.4'; print(sys.version, psycopg.__version__)"

# Verify Docker targets the local daemon before starting this local-only service.
docker compose -f docker-compose.localtest.yml up -d --wait
$env:RATINGS_V4_VALIDATION_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:55434/ratings_v4_validation'
$env:PYTHONPATH = 'apps/api/src'
uv run --project apps/api --no-sync python -m pytest tests/test_v3_system_search_parallel.py tests/test_ratings_v4_system_search.py tests/test_v3_system_search_body_type_counts_migration.py -q
```

The validation fixture rejects a non-loopback host or any entry database other
than `ratings_v4_validation`. It creates a random `v4_test_*` database, loads a
small test cohort and V3 migrations, and removes only that fixture database
afterward. The parallel test module shares that disposable database but creates
a separate derived generation for each test. It does not read a production DSN.
If the local service is unavailable,
the DB tests must be reported as unexecuted/skipped rather than treated as proof.

Required assertions cover serial/parallel content equivalence across disjoint
ranges; interruption and restart preserving committed progress; rollback of
rows, receipt, and cursor together; duplicate workers/replays without duplicate
writes; bounded input/identity rejection; and finalization only after complete
coverage. Include a real overlapping-connection test so removal of the global
writer lock is exercised rather than inferred solely from sequential output.

### Execution results

Validated on 2026-09-21 with CPython **3.14.4**, Psycopg **3.3.4**, pytest
**9.1.1**, and disposable PostgreSQL **18.6**. The environment was installed by
`uv tool run --from uv==0.11.33 uv sync --project apps/api --frozen --group test --python 3.14`;
the dependency graph was not changed. The existing local test container was
verified as `postgres:18`, bound to `127.0.0.1:55434`, and owned by the local-test
Compose configuration. Only fixture-created random databases were mutated.

- Final parallel suite: `apps/api/.venv/Scripts/python.exe -m pytest tests/test_v3_system_search_parallel.py -q -x`
  with the local test URL and `PYTHONPATH` above: **33 passed, 0 skipped**
  (452.79 seconds). Coverage includes actual overlapping transactions, all-column
  and content-hash parity, both range and source-chunk mutexes, rollback before
  checkpoint commit, resume/adoption of compatible receipts, finalizer fencing,
  unsafe-connection rejection, and the complete CLI orchestration path.
- Existing `test_ratings_v4_system_search.py` and
  `test_v3_system_search_body_type_counts_migration.py`: **6 passed, 0 skipped**
  in the combined disposable-DB run. Its first concurrency tests exposed a test
  harness issue: `connection.info.dsn` omits passwords. Secondary fixture
  connections now explicitly preserve the local fixture password; the final
  33-test run above passed after that correction.
- Search profile, signal-profile, production-operator, analyze-stats, and
  systemid-stats operator regression files: **19 passed, 0 skipped**. These are
  source/contract and shell-rendering tests, not production operator executions.
  Windows selected its WSL `bash` stub for bare subprocess calls, so the local
  test launcher explicitly resolved those calls to installed Git Bash. Existing
  checksum-sensitive migration files were restored to their committed LF bytes
  in the worktree for those checks; no migration contents or stored hashes were
  changed.
- Ruff passed for both builders and the parallel tests; `git diff --check`,
  document-link checks, and the CPython 3.14 runtime check passed.

The synthetic fixture proves correctness and concurrent execution, not production
throughput. No production DB access, real rebuild, rollout, or publication was
performed.
