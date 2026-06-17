import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
CONTRACT_PATH = DOCS / 'stage-20a-provenance-cockpit-implementation-contract.md'
FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'stage20a'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

PRIMARY_CONTRACT_SET = 'System provenance cockpit summary contract'
SCHEMA_VERSION = 'stage20a_provenance_cockpit/v1'
FIXTURE_NAMES = (
    'provenance_cockpit_happy_path.json',
    'provenance_cockpit_stale_evidence.json',
    'provenance_cockpit_unknown_evidence.json',
)


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


@pytest.mark.unit
def test_stage20a_contract_doc_records_concrete_backend_and_frontend_ownership():
    contract = _read(CONTRACT_PATH)

    assert CONTRACT_PATH.exists()
    assert f'Stage 20A primary contract set: `{PRIMARY_CONTRACT_SET}`.' in contract
    for fragment in (
        'apps/api/src/routers/operator.py',
        'apps/api/src/operator_visibility.py',
        'apps/api/src/enrichment_operator_status.py',
        'apps/api/src/routers/systems.py',
        'apps/api/src/routers/simulation.py',
        'frontend-v2/src/features/system-detail/SimulationPreviewPanel.tsx',
        'frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx',
        'frontend-v2/src/features/system-detail/simulation-preview/EvidenceWorkspaceView.tsx',
        'frontend-v2/src/lib/api.ts',
        'frontend-v2/src/types/api.ts',
        'apps/api/src/routers/provenance_cockpit.py',
        'frontend-v2/src/features/system-detail/simulation-preview/provenance/ProvenanceCockpitPanel.tsx',
    ):
        assert fragment in contract


@pytest.mark.unit
def test_stage20a_contract_authority_keeps_deferred_production_lanes_false():
    authority = _json(AUTHORITY_PATH)
    stage20 = authority['stage20']
    contract = authority['stage20a_implementation_contract']

    assert stage20['primary_contract_set'] == PRIMARY_CONTRACT_SET
    assert stage20['contract_schema_version'] == SCHEMA_VERSION
    assert contract['primary_contract_set'] == PRIMARY_CONTRACT_SET
    assert contract['contract_schema_version'] == SCHEMA_VERSION
    assert contract['stage20_implementation_started'] is False
    assert contract['stage20_feature_delivery_started'] is False
    assert contract['stage19_remains_paused'] is True
    assert contract['stage19_production_activation_complete'] is False
    assert contract['next_stage19_write_lane_authorized'] is False
    assert contract['canonical_apply_complete'] is False
    assert contract['canonical_apply_authorized'] is False
    assert contract['rebaseline_complete'] is False
    assert contract['rebaseline_authorized'] is False
    assert contract['scheduler_enabled'] is False
    assert contract['scheduler_service_authorized'] is False
    assert contract['db_writes_authorized'] is False
    assert contract['db_commands_run'] is False
    assert contract['stage19_operator_commands_run'] is False
    assert contract['source_acquisition_run'] is False
    assert contract['staging_loader_run'] is False
    assert contract['db_mutation_performed'] is False


@pytest.mark.unit
def test_stage20a_fixture_payloads_exist_and_are_non_secret():
    contract = _read(CONTRACT_PATH)

    assert FIXTURES_DIR.exists()
    for fixture_name in FIXTURE_NAMES:
        fixture_path = FIXTURES_DIR / fixture_name
        payload = _json(fixture_path)

        assert fixture_name in contract
        assert payload['schema_version'] == SCHEMA_VERSION
        assert payload['guardrails']['stage19_paused'] is True
        assert payload['guardrails']['stage19_production_activation_complete'] is False
        assert payload['guardrails']['next_stage19_write_lane_authorized'] is False
        assert payload['guardrails']['canonical_apply_complete'] is False
        assert payload['guardrails']['rebaseline_complete'] is False
        assert payload['guardrails']['scheduler_enabled'] is False
        assert payload['guardrails']['db_writes_authorized'] is False
        assert payload['guardrails']['stage19_operator_commands_authorized'] is False
        assert 'artifact_path' not in json.dumps(payload)
        assert '/home/' not in json.dumps(payload)
        assert 'token' not in json.dumps(payload).lower()
        assert 'password' not in json.dumps(payload).lower()


@pytest.mark.unit
def test_stage20a_contract_defines_required_fields_and_safe_states():
    contract = _read(CONTRACT_PATH)

    for fragment in (
        'stage20a_provenance_cockpit/v1',
        '`schema_version`',
        '`system`',
        '`provenance_summary`',
        '`evidence_panels`',
        '`guardrails`',
        '`warnings`',
        '`ui_hints`',
        '`available`',
        '`stale`',
        '`unknown`',
        'Stage 20B - Read-only evidence and status surfaces',
    ):
        assert fragment in contract


@pytest.mark.unit
def test_stage20a_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage20a_implementation_contract.py' in parity
    assert 'tests/fixtures/stage20a/' not in parity
    assert '--commit' not in parity
    assert 'psql' not in parity
