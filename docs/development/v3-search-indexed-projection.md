# Target-keyed Search projection — code and read-only proof

## Evidence motivating the change

PR #699 improved the bodies.system_id64 statistics estimate, but profile runs
3 and 4 still scanned all 25,019,890 signal rows: full SELECT 4,384.013 ms versus
4,270.343 ms (about 2.6%). This is not a material hot-path improvement.

[Profile run 5](https://github.com/brianstewart377-rgb/ed-finder/actions/runs/34711184503)
captured a complete, fixed-cohort full query on Ratings chunk 36840:

| Variant | Execution time | Main evidence |
| --- | ---: | --- |
| Baseline | 10,741.340 ms | Whole signal and body_mechanics scans |
| JIT off | 11,993.742 ms | Same broad scans |
| JIT off, sequential scans discouraged | 35.970 ms | Existing body, signal and mechanics indexes |

The third variant is diagnostic evidence that an indexed path is viable, not a
recommendation to disable sequential scans globally. These are single runs in
fixed order; cache warming and concurrent workers limit causal timing claims.
Runs 4 and 5 used different cohorts, so their full-query times are not a
controlled longitudinal comparison.

## Candidate and proof

The writer's shared SELECT now uses a system-correlated signal aggregate and
a generation/system-correlated main-star lookup with ORDER BY body_pk LIMIT 1.
All other projection fields, false defaults, and product lifecycle guards remain.
The profiler imports this exact SELECT without database dependencies; its frozen
legacy SELECT is retained separately for comparison.

The existing protected profile workflow renders both SELECTs from trusted main.
It fixes the earliest committed Ratings chunk missing a Search receipt and the
latest committed Ratings chunk at startup. Each cohort uses one repeatable-read,
read-only transaction for baseline, JIT-off, forced-index diagnostic, candidate
defaults, candidate JIT-off, and bidirectional EXCEPT ALL with receipt coverage.
Every statement has a 60-second limit. Complete JSON plans are retained.

Acceptance requires zero differing rows, exact receipt coverage, and natural
candidate plans with bounded body/signal/mechanics lookups in both cohorts.
Compare execution/JIT time, rows, loops, read blocks and temporary I/O; repeat
with counterbalanced order before quoting a stable speedup. SELECT profiling
does not measure insertion, index maintenance, receipt hashing or worker rate.

## Rollout is a separate gate

This change does not deploy or restart workers, migrate schemas, publish a
generation, change statistics, or persist planner settings. The current Search
product manifest pins the exact builder code hash. The new builder must reject
that existing manifest; do not edit the manifest or bypass its identity check.

A live cutover needs a separately reviewed, explicitly authorized product
identity/resume strategy after the read-only proof passes. Until then the
currently running worker remains on its original immutable source bundle.
