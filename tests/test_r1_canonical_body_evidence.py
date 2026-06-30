from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'importer' / 'src'))

from r1_canonical_body_evidence import (  # noqa: E402
    CONTRACT_VERSION,
    CORE_R1_SELECT_SQL,
    build_dry_run_report_from_cases,
    canonical_json,
    classify_body_row,
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


def test_dry_run_report_is_deterministic_for_fixed_inputs():
    report_a = _build_report()
    report_b = _build_report()
    assert canonical_json(report_a) == canonical_json(report_b)
    assert report_a['artifact_integrity']['canonical_json_sha256'] == report_b['artifact_integrity']['canonical_json_sha256']


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
    assert 'score_' not in sql
    assert 'economy_suggestion' not in sql
