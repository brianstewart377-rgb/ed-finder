# Ratings V4 Parallel Validation Design

Status: **proven in production, not yet landed in the repo.** The parallel
validator ran on ed-finder-prod as `ratings_v4_prod_p4_parallel_v1`, completed
`VERIFIED`/`READY`, and was published as the live derived generation (see
"Outcome" below). The implementation currently exists only in the prod staged
bundle; the repo's `scripts/ratings_v4/production_generation.py` is still the
serial validator. Landing it is deferred to a dedicated governance session
because it changes `code_identity()` (see "Landing status").

## Problem

`validate_generation()` currently replays every derived chunk sequentially on
one Python process. At the serial validator's average of roughly
36k systems/minute, a complete validation of 198,528,286 systems is on the order
of 90 hours (198,528,286 ÷ 36,000 ≈ 5,515 minutes ≈ 92 hours). The build phase
used eight encoder workers, so validation has become the dominant tail of the
generation lifecycle.

Historical context: at the time this was written the `ratings_v4_prod_p4_opt1`
serial generation was mid-validation and had to be left alone. It is now paused
and superseded — `parallel_v1` (built and validated by this design) is the
published generation. This design targets a fresh generation image and did not
alter that in-flight serial process.

## Constraints

- `v3_meta.derived_generation` only allows `VALIDATING -> READY` once. There is
  no partial validation receipt or partial state.
- Derived relation triggers reject writes after `BUILDING`. Validation workers
  must be read-only until the final receipt transaction.
- `manifest.code_sha256_lf` covers `production_generation.py`. Changing
  validation logic therefore changes the code identity for newly created
  generations; it cannot be applied to an existing generation without an
  explicit reviewed code-upgrade path.
- A validation unit must remain the existing `build_chunk`. Chunk contents are
  individually sealed by `content_sha256`, and all three derived tables can be
  scoped to a chunk through `system_rating_vector.chunk_ordinal`.

## Design

### Parallel unit

Partition ordered chunk ordinals into contiguous ranges. Each worker validates
the chunks in its range using the existing per-chunk read/replay path:

1. `_read_chunk(connection, generation_id, ordinal)`
2. `_digest(payload) == build_chunk.content_sha256`
3. inventory counts match `build_chunk.systems`, `canonical_bodies`,
   `physical_bodies`, and `eligible_opportunities`
4. `replay_facts()`, `opportunities_from_facts()`, and `rate_all()`
5. stored vectors/opportunities match replayed values
6. worker returns aggregate counts and scalar aggregates

The parent performs the existing preflight exactly once:

- verify `lifecycle_state = VALIDATING`
- verify manifest, content seal, and frozen scorer contract
- load the complete ordered `build_chunk` checkpoint list
- verify `_digest(checkpoints) == derived_generation.content_sha256`
- dispatch chunk ranges to workers

The parent then merges worker aggregates, checks full-system coverage, builds
the same `validation_receipt`, and performs the single
`VALIDATING -> READY` update transaction.

### Worker model

Use `ProcessPoolExecutor` with `multiprocessing.get_context('spawn')`, matching
the existing encoder path. Each worker opens its own read-only psycopg
connection. No connection or DB cursor crosses process boundaries.

Because the parent connection cannot cross that boundary, each spawned worker
needs **explicit connection authority** — the parent must pass a full DSN (or
discrete connection parameters incl. password) to every worker, not derive it
from the parent handle. `connection.info.dsn` is **not** usable as a fallback:
psycopg redacts the password from it. Landing therefore threads the same
connection source the runner already uses (env DSN / connection params) into the
worker factory alongside the worker count; the worker count alone is
insufficient.

Static contiguous ranges are the first implementation because they are
deterministic and easy to reason about. If real chunk-density variance is
large, switch to a bounded work queue where workers claim batches of chunks.

The validation-worker count is a **separate** setting (`--validation-workers`)
with its own `MAX_VALIDATION_WORKERS` limit, not the encoder constant. Its
default must stay **conservative (1)**, not 8: the ordinary operator path
(`scripts/operator/actions/ratings-v4-generation.sh:214-236`) launches
`run_generation.py` with no worker flag inside a container capped at `--cpus 2
--memory 12g`, so an 8-way default would silently fan out eight DB readers and
replay processes under those small limits. The proven `parallel_v1` run used a
separately accelerated worker container and passed `--validation-workers 8`
explicitly. Landing therefore keeps the default at 1 and makes the optimized
operator pass pass `--validation-workers 8` (updating the operator invocation and,
if 8 processes exceed the standard caps, its container resources) rather than
changing the no-flag default.

### Progress

Keep the already-drafted validation progress callback and extend it for
parallel execution:

- `phase: validation`
- `chunk_ordinal` and `chunk_index`
- `validated_systems` and `expected_systems`
- `percent_complete`
- `worker_id` or batch identifier
- `elapsed_seconds`

One progress record per *completed range* is not enough: with the static
one-range-per-worker model a range can run for hours, so the parent would stay
silent — and the `chunk_ordinal`/`percent_complete` fields would not advance —
for that whole span. Progress must be emitted *while* a range is running.
Concretely: workers report per **sub-batch** (a bounded number of chunks) over
an interprocess channel — a `multiprocessing.Queue` the parent drains, or the
bounded work-queue model of the Worker section where each claimed batch yields a
progress record on completion. The parent still throttles emission to keep log
volume bounded, but the source is sub-batch results, not whole-range aggregates.

## Failure and resume

- Workers are read-only. Any worker failure leaves the generation in
  `VALIDATING`. Note that with a static one-range-per-worker model the other
  ranges are already running when a failure is observed, and neither
  `Future.cancel()` nor `shutdown(cancel_futures=True)` can stop in-flight
  `ProcessPoolExecutor` work — so an early checksum failure can leave the
  remaining processes scanning their multi-hour ranges before the error
  propagates. To bound that tail the implementation must either poll a shared
  cancellation flag between chunks or terminate the worker pool on the failure
  path (`ProcessPoolExecutor.shutdown(wait=False)` plus process termination),
  rather than relying on future cancellation.
- No `validation_receipt` or `validated_at` is written until every chunk has
  been replayed successfully.
- Version 1 does not checkpoint partial validation. A failed run restarts from
  chunk zero. With eight workers this is expected to be acceptable; a separate
  append-only validation-progress table can be added later if needed.

## Code identity and rollout

1. Refactor `validate_generation()` in `scripts/ratings_v4/production_generation.py`
   to accept a validation-worker count **and an explicit connection source** for
   the spawned workers (a DSN / connection params, since the parent connection
   cannot cross the process boundary and `connection.info.dsn` redacts the
   password), **and** thread both through the
   runner: `run_generation.py` currently parses only `--workers`
   (`run_generation.py:288-292`) and calls `validate_generation()` with no worker
   argument (`build_generation()` at `run_generation.py:162,263`). Landing must add
   the `--validation-workers` parser argument, its bounds check against
   `MAX_VALIDATION_WORKERS`, the `build_generation()` signature/call change, and
   CLI tests — otherwise the documented `--validation-workers 8` invocation fails
   as an unknown option.
2. Add tests proving `workers=1` and `workers>1` produce identical receipts
   across the deterministic fields (see "Test plan"; `elapsed_seconds` excluded).
3. Build a new generation image. The new `code_identity()` hash is recorded in
   the new generation manifest.
4. Run a new full generation key or a bounded rehearsal before relying on it.
5. Do not run the new image against the current `ratings_v4_prod_p4_opt1`
   generation unless a reviewed code-upgrade migration is installed.

Current remote run:

- Generation key: `ratings_v4_prod_p4_parallel_v1`
- Worker container: `edfinder-ratings-v4-prod-p4-parallel-v1`
- Staged bundle source SHA: `0b9f4003747e7d0f3d0a0c3529f40279471e1765`
- Staged bundle path: `/var/tmp/edfinder-ratings-v4-0b9f4003747e7d0f3d0a0c3529f40279471e1765/scripts/ratings_v4/`
- CLI: `--workers 8 --validation-workers 8`

**Durability gap (landing prerequisite).** The exact implementation that
produced the published generation currently exists *only* at that `/var/tmp`
staging path. SHA `0b9f4003…` is **not** reachable from `git rev-list --all`, and
no copy of the parallel validator lives in the repo (`scripts/ratings_v4/` still
holds the serial validator). If that temporary production bundle is cleaned up,
the code behind the live generation cannot be inspected, reproduced, or used as
the landing baseline — even though its output is the published generation. Before
the staging host is reclaimed, archive the exact staged
`scripts/ratings_v4/` bundle as a durable, reviewable artifact (a reachable
commit or a checked-in patch under version control, with its SHA recorded here),
so the landing session diffs against the proven source rather than
reconstructing it.

## Outcome (2026-09-16)

The run completed successfully and is the currently published generation:

- `derived_generation_id` `cfc25d36-3bc7-4011-a465-d6460eaaf826`,
  lifecycle `PUBLISHED`, `current_derived_generation` pointer → this generation
  at derived publication_sequence 1.
- Receipt `VERIFIED`: 198,528,286 systems (all replayed), 1,389,698,002 ratings,
  577,709,320 physical bodies, 740,001,532 eligible opportunities;
  `every_system_replayed` and `every_stored_chunk_read_back` true.
- Validation ≈ 10.5 h (`elapsed_seconds` 37,769). That field is measured by
  `validate_generation()` from its own entry to the receipt write
  (`scripts/ratings_v4/production_generation.py:297,354`), so it times the
  validation phase only, not the whole generation run. Against the ~90 h serial
  projection that is an ≈ 8.5× speed-up. The target was met.

## Landing status (deferred)

This design is documented; the code is **not yet in the repo**. Bringing the
parallel validator into `scripts/ratings_v4/` changes `code_identity()`, because
that function SHA-hashes `production_generation.py` and `run_generation.py`
themselves. Those SHAs are pinned in
`sql/v3/proposals/007_ratings_v4_code_upgrade_target.json`, and
`tests/test_ratings_v4_resume_upgrade.py` currently asserts
`to_code_sha256_lf == generation.code_identity()`.

**The 007 target must be preserved, not regenerated.**
`007_ratings_v4_code_upgrade.sql` installs the target behind an
UPDATE/DELETE/TRUNCATE trigger that makes the approved row immutable, and
`resume_upgrade.py` defines it as the one-off `ratings-v4-direct-parser-1`
transition for the legacy generation. Replacing those pinned SHAs would either
fail to apply against an existing installation or make the repository identity
disagree with the already-approved database row, breaking verification of that
historical upgrade. So the earlier "regenerate the 007 target" idea is not
viable.

The correct landing path, for the governance session:

- Keep 007 and its JSON exactly as-is (it is the frozen legacy-generation
  transition).
- A freshly created generation already records its own current `code_identity()`
  in its manifest, so the parallel validator needs no upgrade authority to run
  as a new generation (this is exactly how `parallel_v1` ran in production).
- Decouple `tests/test_ratings_v4_resume_upgrade.py` from live identity: the
  `to_code_sha256_lf == generation.code_identity()` assertion must be pinned to
  the frozen 007 legacy target, not to whatever the current tree hashes to.
- Pinning that assertion alone is **not sufficient**. The resume test does not
  just check a receipt — it *executes a resume* of the legacy generation, and
  `resume_upgrade.approved_target()` (`scripts/ratings_v4/resume_upgrade.py:74-85`)
  raises `parser upgrade target differs from independently approved identity`
  whenever the immutable 007 DB row no longer equals the live `code_identity()`.
  Once the parallel validator lands and changes `code_identity()`, that runtime
  guard fails *before* the pinned assertion is ever reached. So the landing path
  must additionally do one of: (a) preserve execution of the historical 007
  target code so the legacy resume still runs against a matching identity (e.g.
  the fixture resumes under the pinned legacy SHAs, not the live tree); (b)
  introduce a distinct approved transition for the new identity; or (c) explicitly
  retire and revise the legacy-resume behaviour this test documents. Decide which
  in the governance session — this is a landing blocker, not a test-only tweak.
- Introduce a new, distinct upgrade authority (its own `upgrade_id` + proposal +
  approved target) **only if** an existing older generation actually needs to be
  upgraded in place — not merely to land new-generation code.

This is deferred to a dedicated governance session together with the test plan
below.

## Expected impact

- Serial baseline: about 36k systems/minute, which for the full 198,528,286
  systems projects to roughly 90 hours of validation.
- Eight-way parallel validation targeted a 6–8x improvement, assuming Postgres
  read throughput and host CPU scale like the encoder phase, i.e. validation in
  the low tens of hours.
- Measured result (see "Outcome"): the `parallel_v1` run validated the full
  galaxy in ≈ 10.5 hours (`elapsed_seconds` 37,769, the validation phase only),
  an ≈ 8.5× speed-up over the ~90 h serial projection — comfortably beating the
  target and removing validation as the lifecycle tail.

## Test plan

- Extend `tests/test_ratings_v4_production_generation.py` for:
  - `workers=1` produces the current receipt shape.
  - `workers=4` produces the same **deterministic** receipt fields and
    aggregates as `workers=1`. The receipt's wall-clock `elapsed_seconds` is not
    deterministic across runs, so the equality assertion must exclude it (or the
    clock must be injected/frozen); compare the counts, coverage flags, and
    quality minima/maxima. **Compare content/manifest hashes only across the same
    generation identity:** `_digest(payload)` embeds `derived_generation_id`, and
    `VALIDATING -> READY` is permitted once, so exercising `workers=1` and
    `workers=4` as two independent committed validations would use two different
    generations whose hashes cannot match by construction. Either run both worker
    counts against the *same* generation without committing the terminal
    transition (a dry-run validation path that returns the receipt it *would*
    write), or exclude the generation-id-dependent hashes and compare the
    per-chunk replayed values instead.
  - progress includes `phase=validation` and advances monotonically. Do **not**
    assert global chunk-ordinal ordering: with static contiguous ranges a later
    worker normally completes a sub-batch before the worker owning the earliest
    range, so a global-order assertion would either fail on immediate reporting or
    force the implementation to buffer later workers' events until the earliest
    range finishes — hiding most parallel progress. Assert instead that each
    worker's own sub-batch records are ordered and that the aggregate
    `validated_systems`/`percent_complete` is non-decreasing.
  - a worker-side checksum mismatch leaves lifecycle state `VALIDATING` **and
    tears down the pool promptly**. Asserting the lifecycle state alone is
    insufficient — it would still pass if the implementation used
    `shutdown(wait=True)` and blocked for hours on the other in-flight ranges.
    The test must prove the bounded-tail behaviour from "Failure and resume":
    inject a mismatch in one range while another long range is running and assert
    the run returns without waiting for that range to finish (e.g. the shared
    cancellation flag is observed / `shutdown(wait=False)` + process termination
    is invoked / the observed teardown time is bounded).
  - legacy-generation resume behaviour is exercised under the resolution chosen
    for the runtime-guard blocker in "Landing status" (preserved historical-target
    execution, a distinct approved transition, or an explicitly revised
    legacy-resume path) — not merely a re-pinned assertion.
- Add a runtime profile script or fixture-level benchmark that reports serial
  versus parallel throughput on a representative multi-chunk subset.
