import json
import os
import sys
from pathlib import Path


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_analytics as analytics  # noqa: E402


def _stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _mixed_reconciliation_report():
    return {
        'schema_version': 'enrichment_staging_reconciliation/v1',
        'dry_run': True,
        'station_candidates': [
            {
                'entity': 'station',
                'candidate_action': 'ambiguous_match',
                'source': {
                    'source_record_hash': 'station-ambiguous',
                    'system_id64': 42,
                    'system_name': 'Alpha',
                    'station_name': 'Alpha Port',
                },
                'canonical': None,
                'canonical_matches': [{'station_id': 1}, {'station_id': 2}],
                'warnings': [],
            },
            {
                'entity': 'station',
                'candidate_action': 'candidate_insert_missing_canonical',
                'source': {
                    'source_record_hash': 'station-source-only',
                    'system_name': 'Beta',
                    'station_name': 'Beta Port',
                },
                'canonical': None,
                'canonical_matches': [],
                'warnings': [],
            },
        ],
        'body_candidates': [
            {
                'entity': 'body',
                'candidate_action': 'insufficient_evidence',
                'source': {
                    'source_record_hash': 'body-missing',
                    'system_id64': None,
                    'system_name': None,
                    'source_body_id': None,
                    'body_name': None,
                },
                'canonical': None,
                'canonical_matches': [],
                'warnings': [],
            },
        ],
        'ring_candidates': [
            {
                'entity': 'ring',
                'candidate_action': 'candidate_insert_missing_canonical',
                'source': {
                    'source_record_hash': 'ring-source-only',
                    'system_id64': 42,
                    'system_name': 'Alpha',
                    'source_body_id': 7,
                    'body_name': 'Alpha 7',
                    'ring_name': 'Alpha 7 A Ring',
                },
                'canonical': None,
                'canonical_matches': [],
                'warnings': [],
            },
        ],
        'warnings': [
            {
                'reason': 'volatile_source_evidence_not_canonical_update',
                'source_record_hash': 'station-source-only',
            }
        ],
        'errors': [],
    }


def test_enrichment_analytics_handles_empty_reconciliation_report():
    report = analytics.build_enrichment_analytics_signals({})

    assert report['schema_version'] == 'enrichment_analytics_signals/v1'
    assert report['dry_run'] is True
    assert report['summary'] == {
        'station_candidates': 0,
        'body_candidates': 0,
        'ring_candidates': 0,
        'total_candidates': 0,
        'missing_system_identifiers': 0,
        'missing_body_identifiers': 0,
        'ambiguous_station_matches': 0,
        'staged_records_without_canonical_match': 0,
        'rings_without_body_match': 0,
        'warnings': 0,
        'errors': 0,
    }
    assert report['station_quality_signals'] == []
    assert report['body_quality_signals'] == []
    assert report['ring_quality_signals'] == []
    assert report['source_coverage_signals'] == []


def test_enrichment_analytics_emits_mixed_quality_signals():
    report = analytics.build_enrichment_analytics_signals(_mixed_reconciliation_report())

    assert report['summary']['station_candidates'] == 2
    assert report['summary']['body_candidates'] == 1
    assert report['summary']['ring_candidates'] == 1
    assert report['summary']['missing_system_identifiers'] == 1
    assert report['summary']['missing_body_identifiers'] == 1
    assert report['summary']['ambiguous_station_matches'] == 1
    assert report['summary']['staged_records_without_canonical_match'] == 2
    assert report['summary']['rings_without_body_match'] == 1
    assert any(signal['signal'] == 'ambiguous_station_match' for signal in report['station_quality_signals'])
    assert any(signal['signal'] == 'missing_body_identifier' for signal in report['body_quality_signals'])
    assert any(signal['signal'] == 'ring_without_canonical_body_match' for signal in report['ring_quality_signals'])
    assert any(signal['signal'] == 'high_warning_rate' for signal in report['source_coverage_signals'])
    assert any(warning.get('reason') == 'high_reconciliation_warning_rate' for warning in report['warnings'])


def test_enrichment_analytics_output_is_deterministic():
    first = analytics.build_enrichment_analytics_signals(_mixed_reconciliation_report())
    second = analytics.build_enrichment_analytics_signals(_mixed_reconciliation_report())

    assert _stable_json(first) == _stable_json(second)


def test_colonisation_candidate_signals_are_report_only_and_conservative():
    quality_report = analytics.build_enrichment_analytics_signals(_mixed_reconciliation_report())

    report = analytics.build_colonisation_candidate_signals(quality_report)

    assert report['schema_version'] == 'colonisation_candidate_signals/v1'
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['summary']['review_candidates'] >= 1
    assert all(candidate['candidate_action'] == 'needs_review' for candidate in report['candidate_systems'])
    assert all(candidate['system_key'] != 'unknown-system' for candidate in report['candidate_systems'])
    assert _stable_json(report) == _stable_json(analytics.build_colonisation_candidate_signals(quality_report))


def test_colonisation_candidate_signals_ignore_aggregate_rows_without_system_identity():
    analytics_report = {
        'source_coverage_signals': [
            {'signal': 'candidate_action:ambiguous_match', 'severity': 'info', 'count': 3},
            {'signal': 'high_warning_rate', 'severity': 'review', 'warnings': 2, 'candidates': 4},
        ],
        'station_quality_signals': [],
        'body_quality_signals': [],
        'ring_quality_signals': [],
    }

    report = analytics.build_colonisation_candidate_signals(analytics_report)

    assert report['summary']['systems_considered'] == 0
    assert report['summary']['review_candidates'] == 0
    assert report['candidate_systems'] == []


def test_mission_density_signals_count_source_evidence_by_system():
    report = analytics.build_mission_density_signals(_mixed_reconciliation_report())

    assert report['schema_version'] == 'mission_density_signals/v1'
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['summary']['station_evidence_count'] == 2
    assert report['summary']['body_evidence_count'] == 1
    assert report['summary']['ring_evidence_count'] == 1
    alpha = [signal for signal in report['system_signals'] if signal['system_key'] == 'id64:42'][0]
    assert alpha['station_evidence_count'] == 1
    assert alpha['ring_evidence_count'] == 1
    assert 'ambiguous_match' in alpha['review_flags']
    assert _stable_json(report) == _stable_json(analytics.build_mission_density_signals(_mixed_reconciliation_report()))


def test_enrichment_analytics_module_has_no_db_network_or_container_dependency():
    module_text = (IMPORTER_SRC / 'enrichment_analytics.py').read_text(encoding='utf-8')

    assert 'psycopg' not in module_text
    assert 'connect(' not in module_text
    assert 'requests' not in module_text
    assert 'docker' not in module_text
