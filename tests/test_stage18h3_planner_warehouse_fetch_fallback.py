from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18H3_PATH = DOCS / 'stage-18h3-planner-warehouse-fetch-fallback.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18h3_authority_records_fetch_then_fallback_planner_integration():
    authority = _json(AUTHORITY_PATH)
    stage18h3 = authority['stage18h3']

    assert STAGE18H3_PATH.exists()
    assert authority['stage21']['next_checkpoint'] is None
    assert stage18h3['status'] == 'completed'
    assert stage18h3['checkpoint_type'] == 'planner_fetch_integration'
    assert stage18h3['document'] == 'docs/colonisation-redesign/stage-18h3-planner-warehouse-fetch-fallback.md'
    assert stage18h3['planner_fetch_added'] is True
    assert stage18h3['route_preferred'] == '/api/colony-planner/system/{id64}/warehouse-planner-evidence'
    assert stage18h3['fallback_route'] == '/api/colony-planner/system/{id64}/provenance-cockpit'
    assert stage18h3['read_only'] is True
    assert stage18h3['report_only'] is True
    assert stage18h3['planner_truth_changed'] is False
    assert stage18h3['fallback_to_provenance_enabled'] is True
    assert stage18h3['db_writes_authorized'] is False


def test_stage18h3_docs_and_ci_parity_record_the_fetch_fallback_slice():
    document = _read(STAGE18H3_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'warehouse-planner-evidence',
        'falls back to the current provenance cockpit warehouse bridge',
        'report-only',
        'does **not**',
        'Stage 18H.4',
    ):
        assert fragment in document

    assert 'stage-18h3-planner-warehouse-fetch-fallback.md' in readme
    assert 'tests/test_stage18h3_planner_warehouse_fetch_fallback.py' in parity
