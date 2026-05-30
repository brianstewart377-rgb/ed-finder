import os
import sys
from pathlib import Path


os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from body_ring_enrichment_plan import (  # noqa: E402
    DRY_RUN_SCHEMA_VERSION,
    build_body_ring_dry_run_report,
    is_trusted_ring_row,
    ring_state_from_evidence,
)


def test_source_only_ring_true_remains_unknown_without_trusted_ring_rows():
    state = ring_state_from_evidence(
        scan_is_ringed=True,
        data_sources=['eddn_scan'],
        trusted_ring_rows=[],
    )

    assert state == {
        'is_ringed': None,
        'ring_state': 'unknown',
        'reason': 'source_only_ring_true_requires_trusted_body_rings',
        'trusted_ring_rows': 0,
    }


def test_eddn_scan_false_is_trusted_no_ring_evidence():
    state = ring_state_from_evidence(
        scan_is_ringed=False,
        data_sources=['eddn_scan'],
        trusted_ring_rows=[],
    )

    assert state['is_ringed'] is False
    assert state['ring_state'] == 'not_ringed'
    assert state['reason'] == 'trusted_scan_no_rings'


def test_only_local_matched_body_ring_rows_confirm_ringed_state():
    unresolved = {
        'system_id64': 42,
        'body_id': 7,
        'ring_name': 'Test 4 A Ring',
        'association_status': 'unresolved_body_identity',
    }
    trusted = {
        'system_id64': 42,
        'body_id': 7,
        'ring_name': 'Test 4 A Ring',
        'association_status': 'local_matched',
    }

    assert is_trusted_ring_row(unresolved) is False
    assert is_trusted_ring_row(trusted) is True
    assert ring_state_from_evidence(
        scan_is_ringed=True,
        data_sources=['eddn_scan'],
        trusted_ring_rows=[unresolved],
    )['ring_state'] == 'unknown'
    assert ring_state_from_evidence(
        scan_is_ringed=True,
        data_sources=['eddn_scan'],
        trusted_ring_rows=[trusted],
    ) == {
        'is_ringed': True,
        'ring_state': 'ringed',
        'reason': 'trusted_body_rings',
        'trusted_ring_rows': 1,
    }


def test_body_ring_dry_run_report_shape_counts_safety_rules():
    report = build_body_ring_dry_run_report(
        source='spansh_dump',
        systems=[{'id64': 42, 'name': 'Test'}],
        body_updates=[{
            'system_id64': 42,
            'body_id': 7,
            'body_name': 'Test 4',
            'field': 'estimated_mapping_value',
            'current': None,
            'planned': 12345,
            'source': 'spansh_dump',
            'confidence': 'source_body_payload',
        }],
        ring_rows=[{
            'system_id64': 42,
            'body_id': 7,
            'body_name': 'Test 4',
            'ring_name': 'Test 4 A Ring',
            'source': 'spansh_dump',
            'confidence': 'source_ring_payload',
            'association_status': 'local_matched',
        }],
        scan_fact_updates=[
            {
                'system_address': 42,
                'body_id': 7,
                'body_name': 'Test 4',
                'is_ringed': True,
                'data_sources': ['spansh_dump'],
            },
            {
                'system_address': 42,
                'body_id': 8,
                'body_name': 'Test 5',
                'is_ringed': False,
                'data_sources': ['eddn_scan'],
            },
        ],
        skipped=[{'system_id64': 42, 'body_name': 'Test 6', 'reason': 'body_not_matched_exactly'}],
        conflicts=[{'system_id64': 42, 'type': 'body_id_name_mismatch'}],
    )

    assert report['schema_version'] == DRY_RUN_SCHEMA_VERSION
    assert report['dry_run'] is True
    assert report['dirty_system_ids_planned'] == [42]
    assert any('source-only is_ringed=true' in rule for rule in report['safety_rules'])
    assert report['summary'] == {
        'systems': 1,
        'body_updates_planned': 1,
        'ring_rows_planned': 1,
        'trusted_ring_rows_planned': 1,
        'confirmed_ringed_bodies_planned': 1,
        'scan_fact_updates_planned': 2,
        'explicit_no_ring_scan_facts_planned': 1,
        'source_only_ring_true_retained_unknown': 0,
        'skipped': 1,
        'conflicts': 1,
        'fetch_errors': 0,
        'dirty_systems_planned': 1,
    }


def test_report_counts_source_only_true_as_unknown_when_no_trusted_ring_row_exists():
    report = build_body_ring_dry_run_report(
        source='eddn_scan',
        systems=[{'id64': 42, 'name': 'Test'}],
        scan_fact_updates=[{
            'system_address': 42,
            'body_id': 7,
            'body_name': 'Test 4',
            'is_ringed': True,
            'data_sources': ['eddn_scan'],
        }],
    )

    assert report['summary']['source_only_ring_true_retained_unknown'] == 1
    assert report['summary']['confirmed_ringed_bodies_planned'] == 0
    assert report['dirty_system_ids_planned'] == []
