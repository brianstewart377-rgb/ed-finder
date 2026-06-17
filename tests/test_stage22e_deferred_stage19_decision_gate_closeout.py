from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE22E_PATH = DOCS / 'stage-22e-deferred-stage19-decision-gate-and-closeout.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage22e_authority_records_closeout_and_separate_stage19_gate():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    stage22e = authority['stage22e']

    assert stage22['status'] == 'completed'
    assert stage22['current_checkpoint'] == 'Stage 22E - Deferred Stage 19 decision gate and closeout'
    assert stage22['next_checkpoint'] is None
    assert stage22['stage22e_reactivation_gate_completed'] is True
    assert stage22['closeout_ready'] is True
    assert stage22['stage22_closed'] is True
    assert stage22['stage19_remains_paused'] is True
    assert stage22['db_writes_authorized'] is False

    assert stage22e['status'] == 'completed'
    assert stage22e['checkpoint_type'] == 'deferred_stage19_decision_gate_closeout'
    assert stage22e['document'] == 'docs/colonisation-redesign/stage-22e-deferred-stage19-decision-gate-and-closeout.md'
    assert stage22e['stage22_closed'] is True
    assert stage22e['future_stage19_lane_requires_new_control_document'] is True
    assert stage22e['future_stage19_lane_requires_explicit_authorization'] is True
    assert stage22e['stage19_remains_paused'] is True
    assert stage22e['stage19_production_activation_authorized'] is False
    assert stage22e['canonical_apply_authorized'] is False
    assert stage22e['rebaseline_authorized'] is False
    assert stage22e['scheduler_service_authorized'] is False
    assert stage22e['db_writes_authorized'] is False
    assert stage22e['stage19_operator_commands_authorized'] is False
    assert stage22e['production_like_db_execution_authorized'] is False


def test_stage22e_docs_and_ci_parity_record_the_closeout_boundary():
    document = ' '.join(_read(STAGE22E_PATH).split())
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    assert STAGE22E_PATH.exists()
    assert 'Stage 22 is complete as a read-only post-18/20/21 control programme.' in document
    assert 'The Stage 19 lane remains deferred unless a later, separately approved control document explicitly authorizes it.' in document
    assert 'Stage 19 production reactivation' in document
    assert 'separate gated lane' in document
    assert 'stage-22e-deferred-stage19-decision-gate-and-closeout.md' in readme
    assert 'tests/test_stage22e_deferred_stage19_decision_gate_closeout.py' in parity
