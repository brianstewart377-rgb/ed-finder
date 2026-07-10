# Production Repair Drain 2026-07-10

This artifact records the bounded production repair outputs observed during the
post-deploy remediation pass on `ed-finder-prod` after deploy/promotion of
`ee6707c`.

It is intentionally explicit about being a committed transcription of operator
observations from the live repair commands, because the original repair-script
JSON was not persisted automatically at the time of the run.

## Ring Drift

Observed bounded repair summary:

- `repair_body_ring_association_status.py --apply`
- initial dry-run observed `total_drift = 154`
- later bounded repair pass observed:
  - `before.total_drift = 5`
  - `after.total_drift = 0`
  - `updated = 5`

Final follow-up dry-run:

- `total_drift = 0`

## No-Body Dirty Tail

Observed bounded reconciliation summaries:

1. `before.total_candidates = 10769`, `after.total_candidates = 5769`
2. `before.total_candidates = 5831`, `after.total_candidates = 831`
3. `before.total_candidates = 966`, `after.total_candidates = 0`
4. `before.total_candidates = 237`, `after.total_candidates = 0`
5. `before.total_candidates = 67`, `after.total_candidates = 0`

Latest follow-up dry-run after those passes:

- `total_candidates = 27`
- `candidates_with_rating = 3`
- `candidates_without_rating = 24`

Interpretation:

- the original audit-scale stale no-body backlog was drained
- the remaining tail was observed as small live churn rather than a stuck bulk
  backlog

## Body-Contract Tail

Observed production-safe invariants state after the repair loop:

- `stored_body_flag_drift = 3`
- `zero_body_count_drift = 3`

This remained the only persistent structural residue at the end of the
remediation session.
