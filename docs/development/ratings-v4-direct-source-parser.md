# Ratings V4 direct source parsing

The production observer in PR #706 measured Ratings using approximately 4.05 of
its 16 allocated CPU cores. Its coordinator used approximately 81% of one core;
encoder processes were partly idle, and database sessions mostly waited for the
application. This motivates reducing sequential coordinator work before adding
encoder workers or changing the pipeline architecture.

The existing reader called `ijson.parse()` and passed its Python event iterator
to `ijson.items()`. Every JSON token crossed into Python before record assembly.
The new reader passes the gzip byte stream directly to `ijson.items()` so the
native backend can assemble complete records. A bounded, transparent read wrapper
retains the root-array check, including long leading whitespace and the existing
YAJL whitespace behavior. It forwards bytes unchanged and ignores binary-stream
`read(0)` probes.

All fields, float handling, chunk limits, compressed-byte hashing, verified EOF
receipts, canonical adaptation, scoring, ordered atomic writes and validation
remain in the existing builder. No source projection or parsing field is dropped.
The parser still validates the entire document and gzip stream; malformed or
truncated inputs cannot produce an EOF receipt.

## Evidence

The exploratory CPython 3.14.7 / ijson 3.5.1 comparison used eight repetitions of
the retained twelve-system cohort: 96 records, 3,112 bodies and approximately
87 MB of JSON. Across six alternating AB/BA rounds, median parsing time fell from
3.098 seconds to 1.515 seconds (2.05× parsing throughput). Full record digests and
compressed-source receipts matched.

This cohort contains substantially richer records than many galaxy systems.
Repeated identifiers are acceptable only in the parsing benchmark, which never
writes those repeated records to a database. These numbers are not a production
throughput forecast.

Run the reproducible comparison with:

```bash
python scripts/ratings_v4/benchmark_source_parser.py --receipt /tmp/parser.json
```

The Ratings freeze workflow also uses `--postgres --rounds 4` against its isolated
PostgreSQL 18 service. Each complete-builder case uses the original unique
twelve-system cohort in a new disposable database, two encoder workers and
three-system chunks. It measures source parsing, canonical reads, compaction,
ordered writes, encoder wait, validation and total time. Warmups are excluded;
measured ordering alternates. Every build must validate and produce identical
stored rows and chunk hashes. The `ratings-v4-parser-benchmark` artifact records
all samples, medians, runtime versions and source checksums. Timing is reported;
there is no fragile wall-clock pass threshold.

The full-build fixture has small chunks and includes process startup and complete
validation. It proves behavior and measures this isolated workload; it does not
reproduce production chunk sizes, storage, canonical query plans or data mix.

## Current production generation

This changes a generation-bound source file, so the existing code-identity guard
will reject resuming the running generation with the new builder. Do not replace
its code, edit its manifest, relax the guard, or restart it to apply this change.
Any deployment for the current generation requires a separately reviewed
compatibility/cutover design. No operator workflow or running worker is changed
by this development work.
