from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE22B_PATH = DOCS / 'stage-22b-current-state-planner-evidence-hardening.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

import provenance_cockpit as provenance_backend  # noqa: E402
import warehouse_planner_evidence as warehouse_backend  # noqa: E402
from routers.provenance_cockpit import router as provenance_router  # noqa: E402
from routers.warehouse_planner_evidence import router as warehouse_router  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage22b_authority_records_planner_evidence_hardening_completion():
    authority = _json(AUTHORITY_PATH)
    stage22 = authority['stage22']
    stage22b = authority['stage22b']

    assert STAGE22B_PATH.exists()
    assert stage22['stage22a_control_reset_completed'] is True
    assert stage22['stage22b_planner_evidence_simplification_completed'] is True
    assert stage22['current_checkpoint'] == 'Stage 22E - Deferred Stage 19 decision gate and closeout'
    assert stage22['stage22_closed'] is True

    assert stage22b['status'] == 'completed'
    assert stage22b['checkpoint_type'] == 'planner_evidence_hardening'
    assert stage22b['document'] == 'docs/colonisation-redesign/stage-22b-current-state-planner-evidence-hardening.md'
    assert stage22b['dedicated_warehouse_endpoint_preferred'] is True
    assert stage22b['provenance_fallback_preserved'] is True
    assert stage22b['runtime_fixtures_isolated_by_default'] is True
    assert stage22b['development_fixture_provider_supported'] is True
    assert stage22b['historical_authority_snapshots_not_used_as_live_system_evidence'] is True
    assert stage22b['authority_json_fail_safe_loading_present'] is True
    assert stage22b['system_evidence_separated_from_global_authority_status'] is True
    assert stage22b['freshness_vocabulary_hardened'] is True
    assert stage22b['missing_timestamp_implies_fresh'] is False
    assert stage22b['unknown_systems_remain_unknown'] is True
    assert stage22b['warehouse_endpoint_openapi_included'] is False
    assert stage22b['db_writes_authorized'] is False
    assert stage22b['stage19_operator_commands_authorized'] is False
    assert stage22b['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage22b_backend_defaults_are_unknown_unavailable_and_conservative(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES', raising=False)
    monkeypatch.setattr(
        warehouse_backend,
        'read_warehouse_status_snapshot',
        lambda _path: {
            'available': True,
            'artifact': {'file_name': 'warehouse-status.json', 'updated_at': '2026-06-17T14:00:00+00:00'},
            'latest_reconciliation_run': {'report_file_name': 'run-20260617.json'},
            'evidence_health': {'stale_records': 0},
            'warnings': [],
        },
    )

    provenance = provenance_backend.build_provenance_cockpit(12866676218109)
    warehouse = warehouse_backend.build_warehouse_planner_evidence(12866676218109)

    assert provenance.provenance_summary.state == 'unknown'
    assert provenance.evidence_panels.source_run.state == 'unknown'
    assert provenance.evidence_panels.source_run.source_name is None
    assert provenance.provenance_summary.latest_source_run_key is None
    assert provenance.guardrails.stage19_paused is True
    assert provenance.guardrails.db_writes_authorized is False

    assert warehouse.evidence_summary.availability == 'unavailable'
    assert warehouse.evidence_summary.items == []
    assert warehouse.freshness.status == 'not_evaluated'
    assert warehouse.freshness.evaluated_at is None
    assert any('fallback' in warning.lower() for warning in warehouse.warnings)


@pytest.mark.unit
def test_stage22b_provenance_authority_failures_fall_back_safely(monkeypatch: pytest.MonkeyPatch):
    class _BrokenAuthorityPath:
        def read_text(self, encoding: str = 'utf-8') -> str:
            return '{not-valid-json'

    provenance_backend._load_authority_snapshot.cache_clear()
    monkeypatch.setattr(provenance_backend, 'AUTHORITY_PATH', _BrokenAuthorityPath())

    response = provenance_backend.build_provenance_cockpit(42)

    assert response.provenance_summary.state == 'unknown'
    assert response.guardrails.stage19_paused is True
    assert response.guardrails.db_writes_authorized is False
    assert any('authority snapshot is malformed' in warning.lower() for warning in response.warnings)
    provenance_backend._load_authority_snapshot.cache_clear()


@pytest.mark.unit
def test_stage22b_docs_and_ci_parity_record_the_hardening_boundaries():
    document = ' '.join(_read(STAGE22B_PATH).split()).lower()
    readme = _read(README_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'runtime per-system fixture data is isolated behind explicit development/test providers',
        'global safety state is visible separately from selected-system evidence',
        'freshness now uses an explicit conservative vocabulary',
        'the dedicated `warehouse_planner_evidence/v1` endpoint remains the preferred planner source',
        'the provenance cockpit remains the safe read-only fallback',
    ):
        assert fragment in document

    assert 'stage-22b-current-state-planner-evidence-hardening.md' in readme
    assert 'tests/test_stage22b_planner_evidence_hardening.py' in parity


@pytest.mark.unit
def test_stage22b_readonly_evidence_routes_remain_hidden_from_openapi():
    provenance_route = next(route for route in provenance_router.routes if getattr(route, 'path', '') == '/api/colony-planner/system/{id64}/provenance-cockpit')
    warehouse_route = next(route for route in warehouse_router.routes if getattr(route, 'path', '') == '/api/colony-planner/system/{id64}/warehouse-planner-evidence')

    assert provenance_route.include_in_schema is False
    assert warehouse_route.include_in_schema is False
