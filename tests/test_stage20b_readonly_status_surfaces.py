import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
STAGE20B_DOC_PATH = DOCS / 'stage-20b-readonly-evidence-status-surfaces.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
API_SRC = ROOT / 'apps' / 'api' / 'src'

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from provenance_cockpit import build_provenance_cockpit  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage20b_authority_records_read_only_surface_completion():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    stage20b = authority['stage20b_readonly_status_surfaces']

    assert STAGE20B_DOC_PATH.exists()
    assert stage20['status'] in {
        'read_only_status_surfaces_completed',
        'map_foundation_completed',
        'sequence_cp_cockpit_completed',
        'completed',
    }
    assert stage20['implementation_started'] is True
    assert stage20['implementation_authorized'] is True
    assert stage20['current_checkpoint'] in {
        'Stage 20B - Read-only evidence and status surfaces',
        'Stage 20C - Map planning surface foundation',
        'Stage 20D - Planner sequence and CP curve cockpit',
        'Stage 20E - Export/operator pack and closeout readiness',
    }
    assert stage20['next_checkpoint'] in {
        'Stage 20C - Map planning surface foundation',
        'Stage 20D - Planner sequence and CP curve cockpit',
        'Stage 20E - Export/operator pack and closeout readiness',
        None,
    }
    assert stage20['stage20b_read_only_status_surfaces_completed'] is True
    assert stage20['stage20b_fixture_backed_surface'] is True

    assert stage20b['status'] == 'completed'
    assert stage20b['fixture_backed'] is True
    assert stage20b['db_reads_performed'] is False
    assert stage20b['db_writes_performed'] is False
    assert stage20b['operator_commands_run'] is False
    assert stage20b['openapi_included'] is False
    assert stage20b['route'] == '/api/colony-planner/system/{id64}/provenance-cockpit'
    assert stage20b['response_schema_version'] == 'stage20a_provenance_cockpit/v1'
    assert stage20b['stage19_remains_paused'] is True
    assert stage20b['stage19_production_activation_complete'] is False
    assert stage20b['next_stage19_write_lane_authorized'] is False
    assert stage20b['canonical_apply_complete'] is False
    assert stage20b['rebaseline_complete'] is False
    assert stage20b['scheduler_enabled'] is False
    assert stage20b['db_writes_authorized'] is False
    assert stage20b['stage19_operator_commands_authorized'] is False
    assert stage20b['production_like_db_execution_authorized'] is False


@pytest.mark.unit
def test_stage20b_backend_returns_available_stale_and_unknown_fixture_safe_states():
    available = build_provenance_cockpit(12866676218109)
    stale = build_provenance_cockpit(9466842275401)
    unknown = build_provenance_cockpit(2293822313194)
    fallback = build_provenance_cockpit(42)

    assert available.schema_version == 'stage20a_provenance_cockpit/v1'
    assert available.provenance_summary.state == 'available'
    assert available.evidence_panels.source_run.rows_read == 250
    assert available.evidence_panels.source_run.rows_staged == 250
    assert available.guardrails.stage19_paused is True
    assert available.guardrails.db_writes_authorized is False

    assert stale.provenance_summary.state == 'stale'
    assert stale.evidence_panels.warehouse.state == 'stale'
    assert stale.evidence_panels.warehouse.stale_records == 14
    assert stale.warnings

    assert unknown.provenance_summary.state == 'unknown'
    assert unknown.system.id64 == 2293822313194
    assert unknown.evidence_panels.source_run.artifact_name is None
    assert unknown.warnings

    assert fallback.provenance_summary.state == 'unknown'
    assert fallback.system.id64 == 42
    assert fallback.guardrails.scheduler_enabled is False


@pytest.mark.unit
def test_stage20b_doc_and_ci_parity_keep_surface_bounded_to_read_only_work():
    document = _read(STAGE20B_DOC_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for fragment in (
        'GET /api/colony-planner/system/{id64}/provenance-cockpit',
        'OpenAPI',
        'fixture-backed',
        'Evidence Workspace',
        'DB writes',
        'Stage 19 operator execution',
        'canonical apply',
        'rebaseline',
        'scheduler/service activation',
    ):
        assert fragment in document

    assert 'tests/test_stage20b_readonly_status_surfaces.py' in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
