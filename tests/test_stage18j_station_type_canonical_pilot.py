from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18J_CLOSEOUT_PATH = DOCS / 'stage-18j-station-type-canonical-pilot-closeout.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
PILOT_MODULE_PATH = ROOT / 'apps' / 'importer' / 'src' / 'station_type_canonical_pilot.py'
PILOT_TEST_PATH = ROOT / 'tests' / 'test_station_type_canonical_pilot.py'
PILOT_POSTGRES_TEST_PATH = ROOT / 'tests' / 'test_station_type_canonical_pilot_postgres.py'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18j_authority_records_bounded_station_type_pilot_and_stage18t_handoff():
    authority = _json(AUTHORITY_PATH)
    stage18j = authority['stage18j']

    assert STAGE18J_CLOSEOUT_PATH.exists()
    assert PILOT_MODULE_PATH.exists()
    assert PILOT_TEST_PATH.exists()
    assert PILOT_POSTGRES_TEST_PATH.exists()
    assert authority['stage21']['next_checkpoint'] is None
    assert stage18j['status'] == 'completed'
    assert stage18j['checkpoint_type'] == 'narrow_canonical_pilot'
    assert stage18j['document'] == 'docs/colonisation-redesign/stage-18j-station-type-canonical-pilot-closeout.md'
    assert stage18j['pilot_scope'] == 'stations.station_type_only'
    assert stage18j['write_path_implemented'] is True
    assert stage18j['dry_run_artifact_support'] is True
    assert stage18j['guarded_apply_support'] is True
    assert stage18j['rollback_preimage_support'] is True
    assert stage18j['post_apply_verification_support'] is True
    assert stage18j['bounded_station_type_write_chain_completed'] is True
    assert stage18j['production_apply_authorized'] is False
    assert stage18j['broad_canonical_backfill_authorized'] is False
    assert stage18j['db_writes_authorized'] is False
    assert stage18j['production_like_db_execution_authorized'] is False


def test_stage18j_docs_and_ci_parity_record_the_delivered_pilot():
    document = _read(STAGE18J_CLOSEOUT_PATH)
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'Stage 18J is complete as the first narrow canonical write pilot.',
        'station_type',
        'deterministic dry-run artifact',
        'guarded apply helpers',
        'Production apply remains unauthorized',
        'Stage 18T',
    ):
        assert fragment in document

    assert 'stage-18j-station-type-canonical-pilot-closeout.md' in readme
    assert 'tests/test_stage18j_station_type_canonical_pilot.py' in parity
    assert 'tests/test_station_type_canonical_pilot.py' in parity
