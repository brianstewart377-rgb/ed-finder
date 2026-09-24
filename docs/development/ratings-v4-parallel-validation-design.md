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
one Python process. On the current full-galaxy run this is averaging roughly
36k systems/minute, so a complete validation is approximately 79 hours.
The build phase used eight encoder workers, so validation has become the
dominant tail of the generation lifecycle.

The running `ratings_v4_prod_p4_opt1` generation must be left alone. This design
is for a future generation image and does not alter the current `VALIDATING`
process.

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

Static contiguous ranges are the first implementation because they are
deterministic and easy to reason about. If real chunk-density variance is
large, switch to a bounded work queue where workers claim batches of chunks.

Proposed default is `workers=8`, matching the encoder path. Keep a separate
`MAX_VALIDATION_WORKERS` limit rather than reusing the encoder constant.

### Progress

Keep the already-drafted validation progress callback and extend it for
parallel execution:

- `phase: validation`
- `chunk_ordinal` and `chunk_index`
- `validated_systems` and `expected_systems`
- `percent_complete`
- `worker_id` or batch identifier
- `elapsed_seconds`

The parent emits one progress record per completed batch, which keeps log volume
bounded while still making the phase observable.

## Failure and resume

- Workers are read-only. Any worker failure cancels the remaining work and
  leaves the generation in `VALIDATING`.
- No `validation_receipt` or `validated_at` is written until every chunk has
  been replayed successfully.
- Version 1 does not checkpoint partial validation. A failed run restarts from
  chunk zero. With eight workers this is expected to be acceptable; a separate
  append-only validation-progress table can be added later if needed.

## Code identity and rollout

1. Refactor `validate_generation()` in `scripts/ratings_v4/production_generation.py`.
2. Add tests proving `workers=1` and `workers>1` produce identical receipts.
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

## Outcome (2026-09-16)

The run completed successfully and is the currently published generation:

- `derived_generation_id` `cfc25d36-3bc7-4011-a465-d6460eaaf826`,
  lifecycle `PUBLISHED`, `current_derived_generation` pointer → this generation
  at derived publication_sequence 1.
- Receipt `VERIFIED`: 198,528,286 systems (all replayed), 1,389,698,002 ratings,
  577,709,320 physical bodies, 740,001,532 eligible opportunities;
  `every_system_replayed` and `every_stored_chunk_read_back` true.
- Total run ≈ 10.5 h (`elapsed_seconds` 37,769), of which validation ≈ 6.7 h —
  vs the ~79 h serial projection. The 10–15 h target was met.

## Landing status (deferred)

This design is documented; the code is **not yet in the repo**. Bringing the
parallel validator into `scripts/ratings_v4/` changes `code_identity()`, because
that function SHA-hashes `production_generation.py` and `run_generation.py`
themselves. Those SHAs are pinned in the independently approved
`sql/v3/proposals/007_ratings_v4_code_upgrade_target.json`, and
`tests/test_ratings_v4_resume_upgrade.py` asserts
`to_code_sha256_lf == generation.code_identity()`. Landing therefore requires a
governed regeneration of the 007 approved target, not a routine feature PR, and
is deferred to a dedicated governance session together with the test plan below.

## Expected impact

- Current serial long-run average: about 36k systems/minute, roughly 79 hours
  for the full 198,528,286 systems.
- Eight-way parallel validation should target roughly 6-8x that rate, assuming
  Postgres read throughput and host CPU scale like the encoder phase.
- A realistic target is full validation in roughly 10-15 hours instead of
  roughly 79 hours, with the exact figure to be confirmed on a rehearsal.

## Test plan

- Extend `tests/test_ratings_v4_production_generation.py` for:
  - `workers=1` produces the current receipt shape.
  - `workers=4` produces the exact same receipt and aggregates as `workers=1`.
  - progress includes `phase=validation` and is emitted in chunk order.
  - a worker-side checksum mismatch leaves lifecycle state `VALIDATING`.
  - resumed generation behavior is unchanged.
- Add a runtime profile script or fixture-level benchmark that reports serial
  versus parallel throughput on a representative multi-chunk subset.
