import builtins
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
FIXTURES = ROOT / 'tests' / 'fixtures'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import reconciliation_artifact_summary as summary_tool  # noqa: E402
from shared_contracts.enrichment_artifact_contracts import validate_compact_warehouse_status_artifact  # noqa: E402


def write_artifact(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding='utf-8')
    return path


def candidate(index: int, **overrides):
    row = {
        'entity': 'station',
        'candidate_action': 'no_change',
        'confidence': 'high',
        'confidence_level': 'high',
        'risk_class': 'clear',
        'reconciliation_state': 'confirmed',
        'review_classifications': ['confirmed', 'report_only'],
        'risk_flags': [],
        'source': {
            'system_id64': 1000 + index,
            'system_name': f'Synthetic System {index}',
            'station_name': f'Synthetic Port {index}',
            'source': 'synthetic_fixture',
            'source_record_hash': f'hash-{index}',
            'source_path': f'/home/example/private/source-{index}.json',
        },
        'canonical': {
            'station_id': index,
            'password': 'must-not-leak',
        },
        'canonical_matches': [{'station_id': index}],
        'differences': [],
        'warnings': [],
        'raw_payload': {'secret': 'must-not-leak'},
    }
    row.update(overrides)
    return row


def artifact(**overrides):
    payload = {
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'summary': {
            'schema_version': 'nested-schema-must-not-win',
            'staged_station_rows_considered': 1,
            'canonical_writes_planned': 0,
            'candidate_station_updates': 0,
            'errors': 0,
        },
        'station_candidates': [candidate(1)],
        'body_candidates': [],
        'ring_candidates': [],
        'station_body_association_candidates': [],
        'source_coverage_summary': {
            'schema_version': 'enrichment_source_coverage_summary/v1',
            'canonical_writes_planned': 0,
            'entities': {
                'station': {
                    'candidates': 1,
                    'candidate_actions': {'no_change': 1},
                    'confidence': {'high': 1},
                    'source_runs': ['/home/example/private/run'],
                    'source_files': ['/home/example/private/file.json'],
                    'missing_system_identifiers': 0,
                    'volatile_warnings': 0,
                },
            },
            'ring_evidence': {
                'staged_ring_candidates': 0,
                'trusted_local_matched_ring_candidates': 0,
                'missing_ring_arrays_state': 'unknown_not_false',
                'ringed_truth_requires_trusted_body_rings': True,
            },
        },
        'warehouse_coverage_report': {
            'schema_version': 'enrichment_warehouse_coverage_report/v1',
            'canonical_writes_planned': 0,
            'summary': {
                'systems_with_station_evidence': 1,
                'source_files_considered': 1,
                'canonical_writes_planned': 0,
            },
            'operator_review': {
                'needs_attention_buckets': {'unresolved_stations': 0},
            },
        },
        'confidence_risk_summary': {
            'schema_version': 'enrichment_confidence_risk_summary/v1',
            'canonical_writes_planned': 0,
            'confidence_distribution': {'high': 1},
            'risk_class_distribution': {'clear': 1},
            'risk_flag_distribution': {},
            'future_canonical_review_candidates': 0,
        },
        'warnings': [],
        'errors': [],
    }
    payload.update(overrides)
    return payload


def test_top_level_schema_version_detection_ignores_nested_schema_versions(tmp_path):
    path = write_artifact(tmp_path / 'synthetic-reconciliation.json', artifact())

    summary = summary_tool.build_compact_summary(path)

    assert summary['artifact_schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert summary['artifact_summary_counts']['schema_version'] == 'nested-schema-must-not-win'
    assert summary['canonical_writes_planned'] == 0


def test_candidate_samples_are_capped_and_station_count_is_streamed(tmp_path):
    rows = [
        candidate(1, candidate_action='candidate_update'),
        candidate(2, candidate_action='candidate_insert_missing_canonical', canonical=None, canonical_matches=[]),
        candidate(3),
    ]
    path = write_artifact(tmp_path / 'synthetic-reconciliation.json', artifact(station_candidates=rows))

    summary = summary_tool.build_compact_summary(path, max_candidate_samples=2)

    assert summary['station_candidate_count'] == 3
    assert summary['candidate_samples']['samples_included'] == 2
    assert summary['candidate_update_counts']['station_candidates'] == 1
    assert summary['candidate_insert_missing_canonical_counts']['station_candidates'] == 1


def test_raw_payloads_and_private_paths_are_excluded(tmp_path):
    path = write_artifact(
        tmp_path / 'synthetic-reconciliation.json',
        artifact(filters={'source_file': '/home/example/private/full-path.json'}),
    )

    summary = summary_tool.build_compact_summary(path)
    dumped = json.dumps(summary, sort_keys=True)

    assert 'must-not-leak' not in dumped
    assert 'raw_payload' not in dumped
    assert '/home/example/private' not in dumped
    assert str(path.parent) not in dumped
    assert summary['source_artifact_basename'] == path.name


def test_unsupported_schema_is_rejected(tmp_path):
    path = write_artifact(
        tmp_path / 'synthetic-reconciliation.json',
        artifact(schema_version='enrichment_snapshot_load_plan/v1'),
    )

    with pytest.raises(ValueError, match='unsupported reconciliation artifact schema'):
        summary_tool.build_compact_summary(path)


def test_output_is_deterministic(tmp_path):
    path = write_artifact(
        tmp_path / 'synthetic-reconciliation.json',
        artifact(station_candidates=[
            candidate(2, candidate_action='candidate_update', risk_flags=['canonical_difference_review']),
            candidate(1, candidate_action='candidate_update', risk_flags=['canonical_difference_review']),
        ]),
    )

    first = summary_tool.build_compact_summary(path)
    second = summary_tool.build_compact_summary(path)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_tool_runs_without_db_access(tmp_path, monkeypatch):
    path = write_artifact(tmp_path / 'synthetic-reconciliation.json', artifact())
    output = tmp_path / 'summary.json'
    real_import = builtins.__import__

    def fail_on_db_import(name, *args, **kwargs):
        if name.startswith('psycopg2'):
            raise AssertionError('summary tool must not import DB drivers')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fail_on_db_import)

    exit_code = summary_tool.main([
        '--artifact',
        str(path),
        '--output',
        str(output),
        '--max-candidate-samples',
        '1',
    ])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['candidate_samples']['samples_included'] == 1
    assert payload['safe_for_git'] is False


def test_compact_summary_shared_fixture_matches_contract():
    payload = json.loads(
        (FIXTURES / 'enrichment_reconciliation_artifact_summary_fixture.json').read_text(encoding='utf-8')
    )

    validated = validate_compact_warehouse_status_artifact(payload)

    assert validated.schema_version == 'enrichment_reconciliation_artifact_summary/v1'
    assert validated.artifact_schema_version == 'enrichment_staging_reconciliation/v1'
