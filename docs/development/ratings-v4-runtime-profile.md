# Ratings V4 runtime observation

The protected Ratings V4 runtime profile observes the existing optimized Ratings
worker, PostgreSQL and Search for 120 seconds. It makes no worker, resource-limit,
schema, publication or persistent-setting changes. It does not attach a debugger,
read process environments or command arguments, execute application queries, or
reset statistics. Unreadable OS counters are reported without an elevated fallback.

Use a single new JSON file in .github/ratings-v4-profile-requests on the governed
chatgpt-ed-new-ops-requests branch, containing only:

```json
{"operation":"ratings-v4-runtime-profile"}
```

The workflow validates the one-file request, checks out trusted main, records
source checksums, and runs the standalone standard-library profiler through the
existing pinned SSH connection and ed-new-operator environment. The remote command
is bounded to 210 seconds and the workflow to eight minutes. Partial JSONL output
is retained even if a required observation fails.

The artifact contains:

- Container identities, unchanged-limit checks and network addresses for attributing
  database sessions. Ambiguous addresses remain unattributed.
- Per-process CPU ticks, kernel wait channel, namespace PID and available I/O
  counters; PID/start-time pairs prevent interpreting PID reuse as CPU work.
- Container cgroup CPU/throttling, memory and I/O counters, host CPU/disk counters,
  memory availability and pressure; compressed source offsets when readable.
- Fresh, short READ ONLY snapshots of database activity and COPY progress roughly
  every two seconds. Queries are classified into fixed categories; raw SQL is
  never returned.
- Before/after committed Ratings and Search counts and cumulative database,
  WAL, checkpoint and I/O statistics, including their reset timestamps and timing
  settings. No canonical or derived data tables are scanned for these counts:
  only the bounded chunk-receipt tables.

Compute throughput from committed count deltas and their database timestamps.
CPU percentages use one CPU core as 100%; compare totals with the recorded quota.
Process CPU sums matching PID/start-time deltas across adjacent observations,
including processes absent at either endpoint. Process lists refresh each sample.
Unobserved entry/exit intervals and lifetimes shorter than the sample cadence remain
unknown; cgroup counters provide the full container total. The receipt reports
observed restarts, running-state changes and resource-limit changes separately.
Do not sum disk counters across partitions, RAID devices and their members.
Database I/O/WAL counters are database/cluster-wide, not attributable solely to
Ratings. Timing counters are uninformative when the corresponding tracking
setting is off. Sampled waits describe observations, not exact wall-time shares;
an idle backend or ClientRead wait can indicate that PostgreSQL is waiting for
its client. Correlate with coordinator/encoder CPU and COPY progress before
choosing an optimization.

The sampler does not change any generation-bound builder file or its code
identity. Any subsequent performance change must preserve the current generation
and its immutable source/code/receipt guarantees under separate review.
