from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE18H_PATH = DOCS / 'stage-18h-warehouse-planner-evidence-bridge.md'
STAGE18H1_PATH = DOCS / 'stage-18h1-per-system-warehouse-evidence-contract.md'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path) -> dict:
    return json.loads(_read(path))


def _squash(text: str) -> str:
    return ' '.join(text.split())


def test_stage18h1_contract_review_is_recorded_without_authorizing_live_planner_mutation():
    authority = _json(AUTHORITY_PATH)
    stage18h1 = authority['stage18h1']

    assert stage18h1['status'] == 'planned'
    assert stage18h1['checkpoint_type'] == 'contract_review'
    assert stage18h1['document'] == 'docs/colonisation-redesign/stage-18h1-per-system-warehouse-evidence-contract.md'
    assert stage18h1['planning_authorized'] is True
    assert stage18h1['implementation_started'] is False
    assert stage18h1['implementation_authorized'] is False
    assert stage18h1['contract_id'] == 'warehouse_planner_evidence/v1'
    assert stage18h1['frontend_scaffolding_added'] is True
    assert stage18h1['backend_scaffolding_added'] is True
    assert stage18h1['live_endpoint_added'] is False
    assert stage18h1['planner_fetch_added'] is False
    assert stage18h1['stage19_remains_paused'] is True
    assert stage18h1['db_writes_authorized'] is False
    assert stage18h1['production_like_db_execution_authorized'] is False


def test_stage18h1_docs_define_contract_and_link_from_stage18h_and_readme():
    authority = _json(AUTHORITY_PATH)
    stage18h1 = _squash(_read(STAGE18H1_PATH))
    stage18h = _squash(_read(STAGE18H_PATH))
    readme = _squash(_read(README_PATH))

    assert STAGE18H1_PATH.exists()
    assert authority['stage21']['next_checkpoint'] == 'Stage 18H.1 - Per-system warehouse evidence contract review'
    assert 'warehouse_planner_evidence/v1' in stage18h1
    assert 'This slice is intentionally contract-first.' in stage18h1
    assert 'live endpoint' in stage18h1
    assert 'Prohibited Fields' in _read(STAGE18H1_PATH)
    assert 'stage-18h1-per-system-warehouse-evidence-contract.md' in stage18h
    assert 'stage-18h1-per-system-warehouse-evidence-contract.md' in readme
