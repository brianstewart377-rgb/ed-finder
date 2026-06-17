from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
OPS = ROOT / 'docs' / 'operations'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE21_CLOSEOUT_PATH = DOCS / 'stage-21-closeout.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18jq_follow_on_authority_records_q2_through_q9_and_pfilter_handoff():
    authority = _json(AUTHORITY_PATH)

    assert authority['stage21']['next_checkpoint'] is None

    assert authority['stage18jq2']['read_only_command_defined'] is True
    assert authority['stage18jq2']['production_connected_command_run'] is False
    assert authority['stage18jq3']['pre_run_gate_failed'] is True
    assert authority['stage18jq3']['production_artifact_generated'] is False
    assert authority['stage18jq4']['operator_packet_present'] is True
    assert authority['stage18jq4b']['readonly_dsn_defined_in_repo'] is False
    assert authority['stage18jq4c']['readonly_role_provisioning_plan_present'] is True
    assert authority['stage18jq5']['nested_station_loader_support_implemented'] is True
    assert authority['stage18jq5']['nested_body_support_implemented'] is False
    assert authority['stage18jq6']['streaming_station_write_path_implemented'] is True
    assert authority['stage18jq6']['compact_write_summary_implemented'] is True
    assert authority['stage18jq7']['json_safe_report_serialization_implemented'] is True
    assert authority['stage18jq8']['compact_summary_tool_implemented'] is True
    assert authority['stage18jq9']['readiness_verdict'] == 'ready_only_with_strict_filter'
    assert authority['stage18jq9']['stage18jpfilter_required_before_stage18jp'] is True


def test_stage18jq_follow_on_docs_readme_parity_and_implementation_surfaces_exist():
    readme = _read(README_PATH)
    closeout = _read(STAGE21_CLOSEOUT_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for path in (
        DOCS / 'stage-18j-q2-readonly-production-reconciliation-plan.md',
        DOCS / 'stage-18j-q3-readonly-production-reconciliation-artifact.md',
        OPS / 'stage-18j-q4-operator-access-packet.md',
        OPS / 'stage-18j-q4b-readonly-warehouse-dsn-operator-note.md',
        OPS / 'stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md',
        DOCS / 'stage-18j-q5-nested-edsm-station-snapshot-support.md',
        DOCS / 'stage-18j-q6-memory-safe-warehouse-station-load.md',
        DOCS / 'stage-18j-q7-reconciliation-json-serialization-fix.md',
        DOCS / 'stage-18j-q8-compact-reconciliation-summary.md',
        DOCS / 'stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md',
        DOCS / 'stage-18j-p-filter-strict-station-type-dry-run-filter.md',
        ROOT / 'apps' / 'importer' / 'src' / 'enrichment_staging_db_loader.py',
        ROOT / 'apps' / 'importer' / 'src' / 'reconciliation_artifact_summary.py',
        ROOT / 'tests' / 'test_enrichment_staging_db_loader.py',
        ROOT / 'tests' / 'test_enrichment_staging_reconciliation.py',
        ROOT / 'tests' / 'test_reconciliation_artifact_summary.py',
    ):
        assert path.exists()

    for fragment in (
        'stage-18j-q3-readonly-production-reconciliation-artifact.md',
        'stage-18j-q5-nested-edsm-station-snapshot-support.md',
        'stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md',
        'stage-18j-p-filter-strict-station-type-dry-run-filter.md',
    ):
        assert fragment in readme

    assert 'Stage 18J-Q2 through Stage 18J-Q9 are complete' in closeout
    assert 'Stage 18J-P-filter is complete' in closeout

    for fragment in (
        'tests/test_stage18jq_production_reconciliation_artifact_readiness.py',
        'tests/test_stage18jq_chain_followons.py',
        'tests/test_enrichment_staging_db_loader.py',
        'tests/test_enrichment_staging_reconciliation.py',
        'tests/test_reconciliation_artifact_summary.py',
    ):
        assert fragment in parity
