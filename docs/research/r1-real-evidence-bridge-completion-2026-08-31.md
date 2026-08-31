# ED-Finder R1 — Real Evidence Bridge Completion

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`

## Result
Implemented the isolated, pure R1 real-evidence bridge from canonical row-shaped inputs into composable R1 facts/capabilities.

## Key semantics proven
- HMC identity remains HMC when geologicals are present.
- Rocky identity, rings and geologicals remain independent/composable.
- stored false landable/terraformable values remain Unknown unless a negative is explicitly confirmed;
- stored zero bio/geo counts remain Unknown unless a complete scan is explicitly evidenced;
- volcanism does not imply geological presence;
- true Ammonia World requires exact canonical `Ammonia world` identity;
- ammonia-life gas giants are not true Ammonia Worlds;
- conflicting ammonia flag/subtype withholds the true-Ammonia claim;
- only trusted `local_matched` ring rows become positive ring facts; missing ring rows remain Unknown;
- no-body data never becomes a complete zero-body system;
- surface-slot prediction is versioned and labelled Prediction, with exact boundary semantics and the two historical residuals retained as caveats;
- gas giants receive current first-slice orbital capacity 1; other orbital classes remain Unknown;
- CandidateEvidence projection contains no plan-pair resilience and no calibrated numeric support;
- the bridge does not construct CandidateProgrammePlan;
- an externally supplied P-ER plan with Unknown resilience correctly remains Not assessable.

## Local verification
Executed:

```text
PYTHONPATH=/tmp/r1test/apps/api/src python -m pytest /tmp/r1test/tests/test_r1_evidence_bridge.py -q
.................................                                        [100%]
33 passed in 0.08s
```

The tested local source was the exact content subsequently committed for the bridge files and focused test file.

## New implementation files
- `apps/api/src/r1_evidence_bridge/__init__.py`
- `apps/api/src/r1_evidence_bridge/types.py`
- `apps/api/src/r1_evidence_bridge/provenance.py`
- `apps/api/src/r1_evidence_bridge/body_projection.py`
- `apps/api/src/r1_evidence_bridge/slot_prediction.py`
- `apps/api/src/r1_evidence_bridge/candidate_projection.py`
- `apps/api/src/r1_evidence_bridge/fixtures.py`
- `tests/test_r1_evidence_bridge.py`

## Boundaries
No database access or writes, migrations, Evidence Store mutation, API route changes, live Finder ordering changes, frontend changes, legacy rating/archetype rebuilds, merge or deployment were performed.

## Next stage
Use a bounded read-only real-system snapshot loader to feed canonical system/body/ring rows plus explicit availability/provenance hints into this bridge. Validate named golden systems and measure how much currently stored data is sufficient vs Unknown before designing live Finder integration and plan-generation/link-outcome modelling.
