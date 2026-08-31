# ED-Finder R1 — Bounded Real-System Snapshot Completion

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`

## Result
Implemented an operator/research-only bounded read-only loader for canonical `systems`, `bodies`, and `body_rings` rows, feeding the completed R1 evidence bridge.

## Safety
- maximum 20 explicit selectors;
- exact name/id64 parameter binding only;
- static SELECT/SHOW SQL constants;
- loader executes `SHOW transaction_read_only` and aborts unless `on`;
- operator CLI calls `conn.set_session(readonly=True, autocommit=True)`;
- no writes, migrations, temp tables, Evidence Store mutation, Finder/API/frontend changes.

## Semantics
- canonical false/zero defaults are not upgraded to proven negatives;
- ring association semantics pass through the bridge;
- no evidence hints are invented in this first snapshot slice;
- no plan resilience, CandidateProgrammePlan, or Plan Fit is emitted;
- reports expose completeness, field availability counts, slot prediction coverage, gas-giant orbital predictions, Extraction/Refinery evidence presence/disposition, caveats and deterministic digest.

## Local verification
Executed against the fake read-only DB harness:

```text
PYTHONPATH=/tmp/r1test/apps/api/src python -m pytest /tmp/r1test/tests/test_r1_real_snapshot.py -q
...............                                                          [100%]
15 passed in 0.06s
```

The suite includes writable-session refusal, >20 refusal, parameterization, deterministic ordering, default-false Unknown preservation, ring projection, digest determinism, no plan output, SELECT/SHOW-only SQL and no mutation statements.

## Production DB status
Not executed from this environment. No claim is made that HR 1188, HIP 294 or other named golden systems were queried in production by this stage.

## Operator entry point
`scripts/operator/actions/r1-real-system-snapshot.py`

The next evidence step is a bounded operator run against named golden systems using the existing read-only DB access pattern, followed by review of Unknown/known coverage before any Finder integration.
