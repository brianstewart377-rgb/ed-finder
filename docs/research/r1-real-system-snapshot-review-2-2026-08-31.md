# ED-Finder R1 — Bounded Real-System Snapshot
## Review 2 — Final Pre-Code Contract

Date: 2026-08-31
Status: final pre-code Review 2; continuation approved by owner
Branch: `chatgpt-ed-new-ops-requests`

## Allowed files
- `apps/api/src/r1_real_snapshot/__init__.py`
- `apps/api/src/r1_real_snapshot/types.py`
- `apps/api/src/r1_real_snapshot/loader.py`
- `apps/api/src/r1_real_snapshot/report.py`
- `scripts/operator/actions/r1-real-system-snapshot.py`
- `tests/test_r1_real_snapshot.py`
- completion doc.

No existing production file may change.

## Loader contract
Maximum 20 systems. Exact-name or id64 selectors are resolved using parameterized static SELECTs. No SQL identifiers are built from user input.

Before canonical reads, loader executes `SHOW transaction_read_only` and aborts unless value is `on`.

Static reads:
1. `systems`: id64, name, has_body_data, body_count, updated_at.
2. `bodies`: all fields required by `CanonicalBodyRow`, including exact subtype, nullable environment fields, defaulted flags/counts, and `is_ammonia_world`.
3. `body_rings`: provenance/association fields required by `CanonicalRingRow`.

Rows are ordered deterministically.

## Evidence hints
First slice creates no negative-confirmation hints from canonical defaults. `BodyEvidenceHints` remains empty unless a future explicit evidence-hint source is added. This intentionally leaves stored false/zero values Unknown where source presence is not provable.

## Projection/report
Each snapshot runs through `project_system()` then `project_candidate()`.
Report fields:
- system id/name;
- body-data completeness;
- body count supplied/declared;
- availability counts across all projected body fields;
- known/unknown surface-slot prediction count;
- gas-giant orbital predictions;
- Extraction/Refinery evidence `satisfied` + disposition (no numeric support);
- evidence/projection digest;
- caveats.

No CandidateProgrammePlan or Plan Fit is generated.

## CLI safety
Operator script:
- requires explicit selectors;
- refuses >20;
- creates psycopg2 connection;
- `conn.set_session(readonly=True, autocommit=True)`;
- prints DB identity + `transaction_read_only` before results;
- emits deterministic JSON;
- never reads/writes secrets except connection configuration already supplied by environment;
- no file/database writes.

## Tests
Must prove:
- >20 refused;
- read/write session refused;
- parameterized exact-name/id64 resolution;
- deterministic ordering;
- rows map exactly to bridge dataclasses;
- missing canonical negatives are not upgraded by loader;
- ring associations preserved;
- projection and digest deterministic;
- no plan resilience/Plan Fit emitted;
- SQL constants are SELECT/SHOW only;
- fake DB cursor observes no mutation SQL.

Production DB execution is not claimed by unit tests. A later operator run must provide a read-only evidence artifact for the named golden systems.
