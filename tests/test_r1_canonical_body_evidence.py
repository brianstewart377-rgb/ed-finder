from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'importer' / 'src'))

from r1_canonical_body_evidence import (  # noqa: E402
    CONTRACT_VERSION,
    CORE_R1_SELECT_SQL,
    aggregate_system_classifications,
    build_dry_run_report_from_cases,
    canonical_json,
    classify_body_row,
    coalesce_source_rows,
    load_fixture_cases,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'r1_canonical_body_cases.json'
MIGRATION_PATH = Path(__file__).resolve().parents[1] / 'sql' / '030_r1_canonical_body_evidence.sql'


def _load_cases():
    return load_fixture_cases(FIXTURE_PATH)


def _build_report():
    systems, meta = _load_cases()
    return build_dry_run_report_from_cases(
        systems,
        source_snapshot_identifier=meta['source_snapshot_identifier'],
        generated_at='2026-06-30T00:00:00Z',
        git_commit='test-commit',
    )


def _system(report: dict, system_id64: int) -> dict:
    return next(item for item in report['systems'] if item['system_id64'] == system_id64)


def test_ammonia_world_and_ammonia_life_stay_separate():
    report = _build_report()
    eorgh = _system(report, 203324695)
    brambai = _system(report, 2164124190)
    hip_70564 = _system(report, 972533320043)

    assert eorgh['aggregate']['true_ammonia_world_count'] == 1
    assert eorgh['aggregate']['gas_giant_ammonia_life_count'] == 0
    assert eorgh['expectation_result']['pass'] is True

    assert brambai['aggregate']['true_ammonia_world_count'] == 0
    assert brambai['aggregate']['gas_giant_ammonia_life_count'] == 1
    assert brambai['expectation_result']['pass'] is True

    assert hip_70564['aggregate']['true_ammonia_world_count'] == 0
    assert hip_70564['aggregate']['gas_giant_ammonia_life_count'] == 1
    assert hip_70564['expectation_result']['pass'] is True


def test_36_ophiuchi_mixed_case_keeps_distinct_counts():
    report = _build_report()
    mixed = _system(report, 1865903245675)

    assert mixed['aggregate']['true_ammonia_world_count'] == 1
    assert mixed['aggregate']['gas_giant_ammonia_life_count'] == 1
    assert mixed['legacy_comparison']['ammonia_count'] == 2


def test_hip_294_uses_canonical_water_worlds_without_rating_inputs():
    report = _build_report()
    hip_294 = _system(report, 5601477812)
    assert hip_294['aggregate']['true_water_world_count'] == 3
    assert hip_294['aggregate']['water_world_count'] == 3
    assert hip_294['expectation_result']['pass'] is True
    assert report['query_contract_proof']['forbidden_inputs_absent'] is True
    assert 'ratings' not in CORE_R1_SELECT_SQL.casefold()
    assert 'mv_archetype_rankings' not in CORE_R1_SELECT_SQL.casefold()


def test_unknown_fixture_preserves_unknowns():
    systems, _ = _load_cases()
    incomplete_case = next(item for item in systems if item['system_id64'] == 999999000001)
    trace = classify_body_row(
        {
            'system_id64': incomplete_case['system_id64'],
            **incomplete_case['bodies'][0],
        }
    ).as_dict()

    assert trace['canonical_facts']['true_ammonia_world'] is None
    assert trace['canonical_facts']['rings'] is None
    assert trace['canonical_facts']['distance_from_arrival_star_ls'] is None

    report = _build_report()
    incomplete = _system(report, 999999000001)
    assert incomplete['aggregate']['unknown_body_count'] == 1
    assert incomplete['expectation_result']['pass'] is True


def test_body_join_multiplication_prevention_and_single_trace_row():
    duplicated_rows = [
        {
            'system_id64': 1,
            'body_id': 10,
            'body_name': 'Test 1',
            'body_type': 'Planet',
            'subtype': 'Rocky body',
            'is_ammonia_world': False,
            'is_water_world': False,
            'is_earth_like': False,
            'is_landable': True,
            'is_terraformable': False,
            'distance_from_star': 1200.0,
            'bio_signal_count': 0,
            'geo_signal_count': 0,
            'ring_row_count': 2,
            'scan_is_ringed': None,
            'scan_data_sources': [],
        },
        {
            'system_id64': 1,
            'body_id': 10,
            'body_name': 'Test 1',
            'body_type': 'Planet',
            'subtype': 'Rocky body',
            'is_ammonia_world': False,
            'is_water_world': False,
            'is_earth_like': False,
            'is_landable': True,
            'is_terraformable': False,
            'distance_from_star': 1200.0,
            'bio_signal_count': 0,
            'geo_signal_count': 0,
            'ring_row_count': 0,
            'scan_is_ringed': True,
            'scan_data_sources': ['eddn_scan'],
        },
    ]
    collapsed = coalesce_source_rows(duplicated_rows)
    assert len(collapsed) == 1
    assert collapsed[0]['source_row_count'] == 2

    aggregate, traces = aggregate_system_classifications(1, 'Test System', duplicated_rows)
    assert aggregate['total_body_rows_seen'] == 2
    assert aggregate['total_body_rows_classified'] == 1
    assert len(traces) == 1
    assert traces[0]['query_result_evidence']['ring_evidence']['ring_row_count'] == 2


def test_boolean_subtype_contradiction_produces_documented_conflict():
    trace = classify_body_row(
        {
            'system_id64': 1,
            'body_id': 11,
            'body_name': 'Contradiction',
            'body_type': 'Planet',
            'subtype': 'Ammonia world',
            'is_ammonia_world': False,
            'distance_from_star': 2000.0,
            'bio_signal_count': 0,
            'geo_signal_count': 0,
            'ring_row_count': 0,
            'scan_is_ringed': None,
            'scan_data_sources': [],
        }
    ).as_dict()

    assert trace['canonical_facts']['true_ammonia_world'] is None
    assert 'conflict_true_ammonia_world_explicit_false_vs_exact_subtype' in trace['conflict_flags']
    assert 'conflict_true_ammonia_world_explicit_false_vs_exact_subtype' in trace['ambiguous_flags']


def test_explicit_false_is_distinct_from_source_unknown():
    trace = classify_body_row(
        {
            'system_id64': 1,
            'body_id': 12,
            'body_name': 'Explicit False',
            'body_type': 'Planet',
            'subtype': None,
            'is_earth_like': False,
            'is_water_world': False,
            'is_ammonia_world': False,
            'distance_from_star': None,
            'bio_signal_count': None,
            'geo_signal_count': None,
            'ring_row_count': 0,
            'scan_is_ringed': None,
            'scan_data_sources': [],
        }
    ).as_dict()

    assert trace['canonical_facts']['true_ammonia_world'] is False
    assert 'missing_special_body_boolean' not in trace['unknown_flags']


def test_dry_run_report_is_deterministic_for_fixed_inputs():
    report_a = _build_report()
    report_b = _build_report()
    assert canonical_json(report_a) == canonical_json(report_b)
    assert report_a['artifact_integrity']['canonical_json_sha256'] == report_b['artifact_integrity']['canonical_json_sha256']
    assert 'order by s.id64, b.id' in CORE_R1_SELECT_SQL.casefold()


def test_dry_run_report_contains_machine_readable_evidence():
    report = _build_report()
    assert report['contract_version'] == CONTRACT_VERSION
    assert report['summary']['systems_failing_expectations'] == 0
    for system in report['systems']:
        assert 'aggregate' in system
        assert 'body_classification_trace' in system
        assert 'legacy_comparison' in system


def test_migration_is_r1_only_and_reversible_on_paper():
    sql = MIGRATION_PATH.read_text(encoding='utf-8').casefold()
    assert 'create table if not exists r1_aggregate_runs' in sql
    assert 'create table if not exists r1_system_body_aggregates' in sql
    assert 'create table if not exists r1_body_classification_trace' in sql
    assert 'drop table if exists r1_body_classification_trace' in sql
    assert 'drop table if exists r1_system_body_aggregates' in sql
    assert 'drop table if exists r1_aggregate_runs' in sql
    assert 'primary key (run_id, system_id64)' in sql
    assert 'primary key (run_id, system_id64, body_id)' in sql
    assert 'check (source_row_count >= 0)' in sql
    assert 'check (total_body_rows_seen >= 0)' in sql
    assert 'check (true_ammonia_world_count >= 0)' in sql
    assert 'status in (\'planned\', \'dry_run\', \'completed\', \'partial\', \'failed\')' in sql
    assert 'score_' not in sql
    assert 'economy_suggestion' not in sql
