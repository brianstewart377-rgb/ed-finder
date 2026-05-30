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
    system=None,
    metadata=None,
    links=None,
    conflicts=None,
    fetch_errors=None,
    systems_fetch_failed=None,
    dirty_planned=0,
    dirty_marked=0,
):
    system = dict(system or SYSTEM)
    metadata = metadata or []
    links = links or []
    conflicts = conflicts or []
    fetch_errors = fetch_errors or []
    systems_fetch_failed = systems_fetch_failed or []
    return {
        'dry_run': True,
        'source': 'edsm',
        'stations': {
            'systems': [dict(system)],
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
        'dirty': {'system_ids': [system['id64']] if dirty_planned else [], 'marked': dirty_marked},
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


def test_confirmed_links_apply_after_metadata_pass_reveals_link_candidates(tmp_path):
    outputs = [
        report(metadata=[metadata_update(field='body_name', new_value='Exioce 1')]),
        report(metadata=[metadata_update(field='body_name', new_value='Exioce 1')], dirty_planned=1, dirty_marked=1),
        report(links=[confirmed_link()]),
        report(links=[confirmed_link()], dirty_planned=1, dirty_marked=1),
        report(),
    ]
    modes = []

    def fake_runner(cmd, _cwd, output_path):
        if '--apply-station-metadata' in cmd:
            modes.append('metadata')
        elif '--apply-confirmed-links' in cmd:
            modes.append('confirmed_links')
        else:
            modes.append('dry_run')
        write_report(output_path, outputs.pop(0))
        return guard.CommandResult(returncode=0)

    args = guard.parse_args(['--limit', '2000', '--yes'])
    runner = guard.GuardedStationEnrichmentRunner(args, output_dir=tmp_path / 'run', command_runner=fake_runner)

    runner.run()

    assert modes == ['dry_run', 'metadata', 'dry_run', 'confirmed_links', 'dry_run']


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


def test_docker_command_mounts_checkpoint_state_read_only(tmp_path):
    checkpoint = tmp_path / 'state' / 'station-checkpoint.json'
    args = guard.parse_args(['--limit', '2000', '--yes', '--checkpoint-file', str(checkpoint)])
    args.checkpoint_read_only = True

    cmd = guard.build_docker_compose_command(args, mode='dry_run', repo_root=tmp_path)

    assert f'{checkpoint.parent}:/workspace/enrichment-state' in cmd
    assert '--checkpoint-file' in cmd
    assert f'/workspace/enrichment-state/{checkpoint.name}' in cmd
    assert '--checkpoint-read-only' in cmd


def test_all_records_batches_are_checkpointed_and_apply_without_manual_yes(tmp_path):
    system_one = {'id64': 1, 'name': 'Alpha'}
    system_two = {'id64': 2, 'name': 'Beta'}
    empty = report(system=system_two)
    empty['stations']['systems'] = []
    empty['summary']['systems_processed'] = 0
    # Batch 1 (system_one) needs a metadata pass, so the guard runs:
    #   initial dry-run -> metadata apply -> after-metadata dry-run -> final dry-run.
    # Batch 2 (system_two) is a no-op batch, so the guard runs a single
    # initial dry-run and skips the final re-fetch.
    # Batch 3 sees no eligible systems and exits without re-running.
    outputs = [
        report(system=system_one, metadata=[metadata_update(system_id64=1)]),
        report(system=system_one, metadata=[metadata_update(system_id64=1)], dirty_planned=1, dirty_marked=1),
        report(system=system_one),
        report(system=system_one),
        report(system=system_two),
        empty,
    ]
    modes = []
    checkpoint_flags = []
    checkpoint_path_in_cmd: list[str] = []

    def fake_runner(cmd, _cwd, output_path):
        checkpoint_flags.append('--checkpoint-read-only' in cmd)
        assert '--limit' in cmd
        assert cmd[cmd.index('--limit') + 1] == '2'
        # The CLI checkpoint path always travels via the docker-compose mount.
        ck_index = cmd.index('--checkpoint-file')
        checkpoint_path_in_cmd.append(cmd[ck_index + 1])
        if '--apply-station-metadata' in cmd:
            modes.append('metadata')
        elif '--apply-confirmed-links' in cmd:
            modes.append('confirmed_links')
        else:
            modes.append('dry_run')
        write_report(output_path, outputs.pop(0))
        return guard.CommandResult(returncode=0)

    checkpoint_override = tmp_path / 'state' / 'all-records-checkpoint.json'
    args = guard.parse_args([
        '--all-records',
        '--batch-size',
        '2',
        '--output-dir',
        str(tmp_path),
        '--checkpoint-file',
        str(checkpoint_override),
    ])

    assert args.allow_apply is True

    runner = guard.GuardedStationEnrichmentRunner(args, command_runner=fake_runner)
    runner.run()

    checkpoint_payload = json.loads(checkpoint_override.read_text(encoding='utf-8'))
    assert checkpoint_payload['processed_system_id64s'] == [1, 2]
    # No-op batch (system_two) skips its final dry-run; batch 3 sees no eligible
    # rows and is the only dry-run. So the modes list is shorter than before.
    assert modes == ['dry_run', 'metadata', 'dry_run', 'dry_run', 'dry_run', 'dry_run']
    assert all(checkpoint_flags)
    # Every batch must mount the same checkpoint path (no per-batch path drift).
    assert len(set(checkpoint_path_in_cmd)) == 1


def test_all_records_default_checkpoint_path_is_stable_across_runs(tmp_path, monkeypatch):
    """When --checkpoint-file is omitted the guard MUST use a stable global
    path so a second run resumes from the first run's checkpoint instead of
    starting again from system 0.
    """
    stable_root = tmp_path / 'edfinder-station-enrichment'
    monkeypatch.setattr(guard, 'DEFAULT_OUTPUT_ROOT', stable_root)
    monkeypatch.setattr(
        guard,
        'DEFAULT_ALL_RECORDS_CHECKPOINT',
        stable_root / 'all-records-station-enrichment-checkpoint.json',
    )

    empty_report_payload = report()
    empty_report_payload['stations']['systems'] = []
    empty_report_payload['summary']['systems_processed'] = 0

    def fake_runner(_cmd, _cwd, output_path):
        write_report(output_path, empty_report_payload)
        return guard.CommandResult(returncode=0)

    # Pre-seed a checkpoint with system 7 already processed.
    checkpoint = stable_root / 'all-records-station-enrichment-checkpoint.json'
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps({'processed_system_id64s': [7], 'last_system_id64': 7}),
        encoding='utf-8',
    )

    args = guard.parse_args(['--all-records', '--batch-size', '2'])
    runner = guard.GuardedStationEnrichmentRunner(
        args,
        output_dir=tmp_path / 'run',
        command_runner=fake_runner,
    )
    runner.run()

    # The checkpoint file MUST be the stable default path, not a per-run dir.
    payload = json.loads(checkpoint.read_text(encoding='utf-8'))
    assert payload['processed_system_id64s'] == [7]


def test_all_records_does_not_checkpoint_systems_that_only_failed_to_fetch(tmp_path):
    """Systems listed under ``systems_fetch_failed`` MUST NOT be checkpointed
    so a later batch can retry them once the rate-limit clears.
    """
    success_one = {'id64': 1, 'name': 'Alpha'}
    failed_two = {'id64': 2, 'name': 'Beta'}
    failed_three = {'id64': 3, 'name': 'Gamma'}

    initial = report(system=success_one)
    initial['stations']['systems'] = [dict(success_one)]
    initial['stations']['systems_fetch_failed'] = [dict(failed_two), dict(failed_three)]
    initial['stations']['fetch_errors'] = [
        {'system': dict(failed_two), 'reason': 'edsm_fetch_failed', 'message': '429 Too Many Requests',
         'rate_limited': True, 'system_id64': 2},
        {'system': dict(failed_three), 'reason': 'edsm_fetch_failed', 'message': 'timeout',
         'system_id64': 3},
    ]
    initial['summary']['systems_processed'] = 1
    initial['summary']['stations']['fetch_errors'] = 2
    initial['summary']['stations']['systems_fetch_failed'] = 2

    empty = report()
    empty['stations']['systems'] = []
    empty['summary']['systems_processed'] = 0

    outputs = [initial, empty]

    def fake_runner(_cmd, _cwd, output_path):
        write_report(output_path, outputs.pop(0))
        return guard.CommandResult(returncode=0)

    checkpoint_override = tmp_path / 'state' / 'checkpoint.json'
    args = guard.parse_args([
        '--all-records',
        '--batch-size',
        '5',
        '--output-dir',
        str(tmp_path),
        '--checkpoint-file',
        str(checkpoint_override),
    ])
    runner = guard.GuardedStationEnrichmentRunner(args, command_runner=fake_runner)
    runner.run()

    payload = json.loads(checkpoint_override.read_text(encoding='utf-8'))
    assert payload['processed_system_id64s'] == [1]
    assert 2 not in payload['processed_system_id64s']
    assert 3 not in payload['processed_system_id64s']


def test_all_records_aborts_when_every_system_fails_to_fetch(tmp_path):
    """If a batch contains only fetch failures, the guard must stop instead
    of busy-looping; the checkpoint stays empty so the next run retries the
    same systems.
    """
    failed_two = {'id64': 2, 'name': 'Beta'}
    initial = report(system=failed_two)
    initial['stations']['systems'] = []
    initial['stations']['systems_fetch_failed'] = [dict(failed_two)]
    initial['stations']['fetch_errors'] = [
        {'system': dict(failed_two), 'reason': 'edsm_fetch_failed', 'message': '429',
         'rate_limited': True, 'system_id64': 2},
    ]
    initial['summary']['systems_processed'] = 0
    initial['summary']['stations']['fetch_errors'] = 1
    initial['summary']['stations']['systems_fetch_failed'] = 1

    runner_calls: list[str] = []

    def fake_runner(_cmd, _cwd, output_path):
        runner_calls.append(output_path.name)
        write_report(output_path, initial)
        return guard.CommandResult(returncode=0)

    checkpoint_override = tmp_path / 'state' / 'checkpoint.json'
    args = guard.parse_args([
        '--all-records',
        '--batch-size',
        '5',
        '--output-dir',
        str(tmp_path),
        '--checkpoint-file',
        str(checkpoint_override),
    ])
    runner = guard.GuardedStationEnrichmentRunner(args, command_runner=fake_runner)
    runner.run()

    # The guard should bail out after a single batch instead of looping.
    assert sum(1 for name in runner_calls if name.startswith('01_initial_dryrun')) == 1
    if checkpoint_override.exists():
        payload = json.loads(checkpoint_override.read_text(encoding='utf-8'))
        assert payload.get('processed_system_id64s', []) == []


def test_no_op_initial_dryrun_skips_final_rerun(tmp_path):
    """When the initial dry-run has 0 metadata + 0 confirmed-link plans we
    must NOT run a second 'final dry-run' (it would re-fetch every system
    from EDSM and risk introducing distance jitter).
    """
    runner_calls: list[str] = []

    def fake_runner(_cmd, _cwd, output_path):
        runner_calls.append(output_path.name)
        write_report(output_path, report())
        return guard.CommandResult(returncode=0)

    args = guard.parse_args(['--limit', '500', '--yes'])
    runner = guard.GuardedStationEnrichmentRunner(
        args,
        output_dir=tmp_path / 'run',
        command_runner=fake_runner,
    )
    runner.run()

    assert runner_calls == ['01_initial_dryrun.json']


def test_write_batch_still_runs_final_dryrun(tmp_path):
    """When the guard actually applies metadata writes, the final dry-run
    re-fetch is still required so we validate the write landed cleanly.
    """
    outputs = [
        report(metadata=[metadata_update()]),
        report(metadata=[metadata_update()], dirty_planned=1, dirty_marked=1),
        report(),
        report(),
    ]
    runner_calls: list[str] = []

    def fake_runner(_cmd, _cwd, output_path):
        runner_calls.append(output_path.name)
        write_report(output_path, outputs.pop(0))
        return guard.CommandResult(returncode=0)

    args = guard.parse_args(['--limit', '500', '--yes'])
    runner = guard.GuardedStationEnrichmentRunner(
        args,
        output_dir=tmp_path / 'run',
        command_runner=fake_runner,
    )
    runner.run()

    assert 'final_dryrun.json' in runner_calls


def test_successful_system_id64s_excludes_fetch_failed():
    success = {'id64': 11, 'name': 'Ok'}
    failed = {'id64': 22, 'name': 'Bad'}
    payload = report(
        system=success,
        fetch_errors=[
            {'system': dict(failed), 'reason': 'edsm_fetch_failed', 'message': '429',
             'rate_limited': True, 'system_id64': 22},
        ],
        systems_fetch_failed=[failed],
    )

    assert guard.successful_system_id64s(payload) == {11}
    assert guard.report_system_id64s(payload) == {11, 22}


@pytest.mark.parametrize('raw', ['', '{not-json'])
def test_empty_or_invalid_json_fails(tmp_path, raw):
    path = tmp_path / 'bad.json'
    path.write_text(raw, encoding='utf-8')

    with pytest.raises(guard.GuardFailure):
        guard.load_report_file(path)


@pytest.mark.parametrize(
    'line,expected',
    [
        ('Fetching EDSM station enrichment system=Exioce id64=42\n', False),
        ('EDSM rate limit retry system=Exioce endpoint=stations next_attempt=2/3 reason=429\n', True),
        ('http 429 Too Many Requests\n', True),
        ('status=429 reason=blocked\n', True),
        ('EDSM fetch retry next_attempt=2/3 reason=timeout\n', False),
    ],
)
def test_is_rate_limit_log_classifies_lines(line, expected):
    assert guard._is_rate_limit_log(line) is expected


def test_run_docker_compose_command_streams_and_counts_429(tmp_path, capsys):
    """The live runner streams importer stderr to our stderr line-by-line and
    detects consecutive 429 lines so the guard can warn the operator.
    """
    output_path = tmp_path / 'phase.json'
    # /bin/sh script that emits a tiny JSON report to stdout and 4 fake 429
    # log lines to stderr (above the warning threshold of 3).
    script = (
        r'''printf '{"stations":{"systems":[]}}' && \
        for i in 1 2 3 4; do \
          echo "EDSM rate limit retry system=Test endpoint=stations next_attempt=$i/5 reason=429 Too Many Requests" 1>&2; \
        done'''
    )
    cmd = ['/bin/sh', '-c', script]

    result = guard.run_docker_compose_command(cmd, tmp_path, output_path)

    captured = capsys.readouterr()
    # JSON stdout has been written to disk verbatim.
    assert json.loads(output_path.read_text(encoding='utf-8'))['stations']['systems'] == []
    # Streaming worked: every 429 line and the warning landed on our stderr.
    assert captured.err.count('EDSM rate limit retry') == 4
    assert '[guard] EDSM 429 observed' in captured.err
    # The CommandResult surfaces the consecutive count for higher-level logic.
    assert result.consecutive_rate_limits >= guard.RATE_LIMIT_RUN_THRESHOLD
    # Captured stderr is also persisted alongside the JSON report.
    stderr_path = output_path.with_name(f'{output_path.name}.stderr.txt')
    assert stderr_path.exists()
    persisted = stderr_path.read_text(encoding='utf-8')
    assert persisted.count('EDSM rate limit retry') == 4
    assert '[guard] EDSM 429 observed' in persisted
    assert result.returncode == 0


def test_run_docker_compose_command_resets_429_counter_on_normal_output(tmp_path, capsys):
    """A non-rate-limit log line resets the consecutive 429 counter so a
    transient burst that recovers does not trip the warning.
    """
    output_path = tmp_path / 'phase.json'
    script = (
        r'''printf '{"stations":{"systems":[]}}' && \
        echo "Fetching EDSM station enrichment system=Alpha id64=1" 1>&2 && \
        echo "http 429 Too Many Requests" 1>&2 && \
        echo "Fetching EDSM station enrichment system=Beta id64=2" 1>&2 && \
        echo "http 429 Too Many Requests" 1>&2 && \
        echo "Fetching EDSM station enrichment system=Gamma id64=3" 1>&2'''
    )
    cmd = ['/bin/sh', '-c', script]

    result = guard.run_docker_compose_command(cmd, tmp_path, output_path)

    captured = capsys.readouterr()
    # The warning must NOT fire because the 429s were not consecutive.
    assert '[guard] EDSM 429 observed' not in captured.err
    assert result.consecutive_rate_limits == 0
