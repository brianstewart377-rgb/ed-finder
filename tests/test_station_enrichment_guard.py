import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import station_enrichment_guard as guard  # noqa: E402


SYSTEM = {'id64': 2008132031194, 'name': 'Exioce'}
STATION = {
    'id': 1001,
    'market_id': 1001,
    'system_id64': SYSTEM['id64'],
    'name': 'Harper Plant',
}


def metadata_update(**overrides):
    update = {
        'local_station': dict(STATION),
        'station_id': STATION['id'],
        'market_id': STATION['market_id'],
        'system_id64': STATION['system_id64'],
        'field': 'station_type',
        'old_value': 'Unknown',
        'new_value': 'Orbis',
    }
    update.update(overrides)
    return update


def confirmed_link(**overrides):
    update = {
        'local_station': dict(STATION),
        'station_id': STATION['id'],
        'market_id': STATION['market_id'],
        'system_id64': STATION['system_id64'],
        'body_id': 11,
        'body_name': 'Exioce 1',
        'lane': 'orbital',
        'association_status': 'confirmed',
        'association_confidence': 'exact',
        'association_source': 'edsm_body_name',
    }
    update.update(overrides)
    return update


def risky_conflict(conflict_type='known_station_type_mismatch'):
    return {
        'local_station': dict(STATION),
        'conflict': {
            'type': conflict_type,
            'write_safety': 'identity_context_unsafe',
            'identity_context_unsafe': True,
        },
    }


def report(
    *,
    metadata=None,
    links=None,
    conflicts=None,
    fetch_errors=None,
    systems_fetch_failed=None,
    dirty_planned=0,
    dirty_marked=0,
):
    metadata = metadata or []
    links = links or []
    conflicts = conflicts or []
    fetch_errors = fetch_errors or []
    systems_fetch_failed = systems_fetch_failed or []
    return {
        'dry_run': True,
        'source': 'edsm',
        'stations': {
            'systems': [dict(SYSTEM)],
            'metadata_updates_planned': metadata,
            'metadata_updates_applied': [],
            'confirmed_link_updates_planned': links,
            'confirmed_link_updates_applied': [],
            'conflicts': conflicts,
            'skipped': [],
            'ignored_transient_non_slot': [],
            'fetch_errors': fetch_errors,
            'systems_fetch_failed': systems_fetch_failed,
            'counts': {
                'station_write_suppressed_non_benign_conflict': len(conflicts),
            },
        },
        'dirty': {'system_ids': [SYSTEM['id64']] if dirty_planned else [], 'marked': dirty_marked},
        'summary': {
            'systems_processed': 1,
            'stations': {
                'conflicts': len(conflicts),
                'skipped': 0,
                'fetch_errors': len(fetch_errors),
                'systems_fetch_failed': len(systems_fetch_failed),
            },
            'dirty_systems_planned': dirty_planned,
            'dirty_systems_marked': dirty_marked,
            'conflicts': len(conflicts),
            'fetch_errors': len(fetch_errors),
            'systems_fetch_failed': len(systems_fetch_failed),
        },
    }


def write_report(path, payload):
    path.write_text(json.dumps(payload), encoding='utf-8')


def test_load_report_file_parses_fixture_json_and_summary(tmp_path):
    path = tmp_path / 'fixture.json'
    payload = report(metadata=[metadata_update()], links=[confirmed_link()], dirty_planned=1)
    write_report(path, payload)

    loaded = guard.load_report_file(path)
    summary = guard.compact_summary(loaded, path)

    assert summary.systems_processed == 1
    assert summary.metadata_updates == 1
    assert summary.confirmed_links == 1
    assert summary.dirty_systems_planned == 1
    assert guard.analyse_report(loaded).metadata_updates == 1


def test_risky_metadata_blocks_apply():
    payload = report(
        metadata=[metadata_update()],
        conflicts=[risky_conflict('known_station_type_mismatch')],
    )

    with pytest.raises(guard.GuardFailure, match='risky metadata writes > 0'):
        guard.assert_safe_to_continue(payload, phase='initial dry-run')


def test_risky_links_blocks_apply():
    payload = report(
        links=[confirmed_link()],
        conflicts=[risky_conflict('station_economy_mismatch')],
    )

    with pytest.raises(guard.GuardFailure, match='risky confirmed links > 0'):
        guard.assert_safe_to_continue(payload, phase='initial dry-run')


def test_precision_churn_blocks_apply():
    local_station = {
        **STATION,
        'distance_source': 'edsm_system_api',
        'distance_confidence': 'exact_station_identity',
    }
    payload = report(metadata=[
        metadata_update(
            local_station=local_station,
            field='distance_from_star',
            old_value=120.0,
            new_value=120.00001,
        )
    ])

    with pytest.raises(guard.GuardFailure, match='precision churn > 0'):
        guard.assert_safe_to_continue(payload, phase='initial dry-run')


def test_safe_metadata_tail_allows_another_metadata_pass(tmp_path):
    outputs = [
        report(metadata=[metadata_update(field='station_type')]),
        report(metadata=[metadata_update(field='station_type')], dirty_planned=1, dirty_marked=1),
        report(metadata=[metadata_update(field='body_name', new_value='Exioce 1')]),
        report(metadata=[metadata_update(field='body_name', new_value='Exioce 1')], dirty_planned=1, dirty_marked=1),
        report(),
        report(),
    ]
    modes = []
    written = []

    def fake_runner(cmd, _cwd, output_path):
        if '--apply-station-metadata' in cmd:
            modes.append('metadata')
        elif '--apply-confirmed-links' in cmd:
            modes.append('confirmed_links')
        else:
            modes.append('dry_run')
        written.append(output_path.name)
        write_report(output_path, outputs.pop(0))
        return guard.CommandResult(returncode=0)

    args = guard.parse_args(['--limit', '2000', '--yes', '--max-metadata-passes', '3'])
    runner = guard.GuardedStationEnrichmentRunner(args, output_dir=tmp_path / 'run', command_runner=fake_runner)

    runner.run()

    assert modes == ['dry_run', 'metadata', 'dry_run', 'metadata', 'dry_run', 'dry_run']
    assert written == [
        '01_initial_dryrun.json',
        '02_metadata_apply_1.json',
        '03_after_metadata_1_dryrun.json',
        '04_metadata_apply_2.json',
        '05_after_metadata_2_dryrun.json',
        'final_dryrun.json',
    ]


def test_final_clean_state_success():
    analysis = guard.assert_final_clean(report(), phase='final dry-run')

    assert analysis.metadata_updates == 0
    assert analysis.confirmed_links == 0


def test_fetch_errors_are_reported_but_not_fatal_when_systems_fetch_failed():
    fetch_error = {
        'system': dict(SYSTEM),
        'system_id64': SYSTEM['id64'],
        'system_name': SYSTEM['name'],
        'reason': 'edsm_fetch_failed',
        'message': 'The read operation timed out',
    }
    payload = report(fetch_errors=[fetch_error], systems_fetch_failed=[SYSTEM])

    guard.assert_safe_to_continue(payload, phase='initial dry-run')
    summary = guard.compact_summary(payload, Path('initial.json'))

    assert summary.fetch_errors == 1
    assert summary.systems_fetch_failed == 1


def test_docker_command_uses_hetzner_source_mounts_and_separate_apply_flags(tmp_path):
    args = guard.parse_args(['--limit', '2000', '--yes'])

    metadata_cmd = guard.build_docker_compose_command(args, mode='metadata', repo_root=tmp_path)
    link_cmd = guard.build_docker_compose_command(args, mode='confirmed_links', repo_root=tmp_path)

    assert '/workspace/apps/importer/src/enrich_system_data.py' in metadata_cmd
    assert f'{tmp_path / "apps" / "importer" / "src"}:/workspace/apps/importer/src:ro' in metadata_cmd
    assert f'{tmp_path / "apps" / "api" / "src"}:/workspace/apps/api/src:ro' in metadata_cmd
    assert '--apply-station-metadata' in metadata_cmd
    assert '--apply-confirmed-links' not in metadata_cmd
    assert '--apply-confirmed-links' in link_cmd
    assert '--apply-station-metadata' not in link_cmd


@pytest.mark.parametrize('raw', ['', '{not-json'])
def test_empty_or_invalid_json_fails(tmp_path, raw):
    path = tmp_path / 'bad.json'
    path.write_text(raw, encoding='utf-8')

    with pytest.raises(guard.GuardFailure):
        guard.load_report_file(path)
