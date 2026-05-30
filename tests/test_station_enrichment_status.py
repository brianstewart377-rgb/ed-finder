import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import station_enrichment_status as status  # noqa: E402


def write_checkpoint(path: Path, ids: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'processed_system_id64s': sorted(ids),
        'last_system_id64': max(ids) if ids else None,
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def write_report(path: Path) -> None:
    payload = {
        'stations': {
            'systems': [{'id64': 1, 'name': 'Alpha'}],
            'metadata_updates_planned': [],
            'confirmed_link_updates_planned': [],
            'conflicts': [],
            'skipped': [],
            'fetch_errors': [],
            'systems_fetch_failed': [],
            'counts': {},
            'ignored_transient_non_slot': [],
        },
        'summary': {
            'systems_processed': 1,
            'stations': {
                'conflicts': 0,
                'skipped': 0,
                'fetch_errors': 0,
                'systems_fetch_failed': 0,
            },
            'dirty_systems_planned': 0,
            'dirty_systems_marked': 0,
        },
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def test_status_reports_checkpoint_and_latest_run(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [10, 20, 30])

    output_root = tmp_path / 'runs'
    run_dir = output_root / '20260530-181500-all-records'
    batch_dir = run_dir / 'batch-0001'
    batch_dir.mkdir(parents=True)
    write_report(batch_dir / '01_initial_dryrun.json')

    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--output-root', str(output_root),
        '--system-id64', '20',
    ])
    payload = status.build_status(args)

    assert payload['checkpoint']['exists'] is True
    assert payload['checkpoint']['processed_count'] == 3
    assert payload['checkpoint']['last_system_id64'] == 30
    assert payload['latest_run']['output_dir'] == str(run_dir)
    assert payload['latest_run']['batch_dir'] == str(batch_dir)
    assert payload['latest_report_summary']['systems_processed'] == 1
    assert payload['system_query'] == {
        'system_id64': 20,
        'is_checkpointed': True,
    }


def test_status_handles_missing_checkpoint(tmp_path):
    args = status.parse_args([
        '--checkpoint-file', str(tmp_path / 'missing.json'),
        '--output-root', str(tmp_path / 'no-runs'),
    ])
    payload = status.build_status(args)

    assert payload['checkpoint']['exists'] is False
    assert payload['checkpoint']['processed_count'] == 0
    assert payload['latest_run']['output_dir'] is None


def test_system_id64_not_checkpointed_returns_false(tmp_path):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [1, 2])
    args = status.parse_args([
        '--checkpoint-file', str(checkpoint),
        '--output-root', str(tmp_path),
        '--system-id64', '99',
    ])
    payload = status.build_status(args)
    assert payload['system_query']['is_checkpointed'] is False


@pytest.mark.parametrize('flag', [['--json'], []])
def test_status_main_emits_output(flag, tmp_path, capsys):
    checkpoint = tmp_path / 'state' / 'checkpoint.json'
    write_checkpoint(checkpoint, [42])
    rc = status.main([
        '--checkpoint-file', str(checkpoint),
        '--output-root', str(tmp_path / 'no-runs'),
        *flag,
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert '42' in out
