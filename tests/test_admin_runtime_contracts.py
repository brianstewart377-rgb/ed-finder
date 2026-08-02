from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / 'apps' / 'api' / 'src' / 'main.py'
ADMIN_PATH = ROOT / 'apps' / 'api' / 'src' / 'routers' / 'admin.py'
MAINTENANCE_PATH = ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_maintenance.sh'


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != 'nt':
        return resolved.as_posix()
    return f'/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}'


def _usable_bash() -> str:
    candidates: list[str] = []
    if os.name == 'nt':
        program_files = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
        candidates.append(str(program_files / 'Git' / 'bin' / 'bash.exe'))
    discovered = shutil.which('bash')
    if discovered:
        candidates.append(discovered)

    for candidate in dict.fromkeys(candidates):
        if not Path(candidate).is_file():
            continue
        probe = subprocess.run(
            [candidate, '-lc', 'printf ready'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0 and probe.stdout == 'ready':
            return candidate
    pytest.skip('usable bash is required for maintenance script tests')


def _run_maintenance_with_stubbed_psql(
    tmp_path: Path,
    task: str,
    *,
    fail_match: str = '',
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bash = _usable_bash()

    stub_dir = tmp_path / 'bin'
    stub_dir.mkdir()
    call_log = tmp_path / 'psql-calls.log'
    stub = stub_dir / 'psql'
    stub.write_text(
        '''#!/bin/bash
{
    printf '%s\t' "${PGOPTIONS:-}"
    printf '%q ' "$@"
    printf '\n'
} >> "${PSQL_CALL_LOG:?}"
if [[ -n "${PSQL_FAIL_MATCH:-}" && "$*" == *"$PSQL_FAIL_MATCH"* ]]; then
    exit 9
fi
exit 0
''',
        encoding='utf-8',
    )
    stub.chmod(0o755)

    env = os.environ.copy()
    env.update({
        'DATABASE_URL': 'postgresql://test.invalid/edfinder',
        'LOG_FILE': _bash_path(tmp_path / 'maintenance.log'),
        'PSQL_CALL_LOG': _bash_path(call_log),
        'PSQL_FAIL_MATCH': fail_match,
    })
    command = (
        f'export PATH={shlex.quote(_bash_path(stub_dir))}:$PATH; '
        f'exec {shlex.quote(_bash_path(MAINTENANCE_PATH))} {shlex.quote(task)}'
    )
    result = subprocess.run(
        [bash, '-lc', command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = call_log.read_text(encoding='utf-8').splitlines() if call_log.exists() else []
    return result, calls


def test_startup_reaps_stale_admin_operation_runs_and_cron_status_is_schema_visible():
    main_source = MAIN_PATH.read_text(encoding='utf-8')
    admin_source = ADMIN_PATH.read_text(encoding='utf-8')

    assert 'reap_stale_admin_operation_runs' in admin_source
    assert 'await reap_stale_admin_operation_runs(pool)' in main_source

    cron_block = admin_source.split("@router.get(\n    '/api/admin/cron-status',", 1)[1].split(')\nasync def admin_cron_status', 1)[0]
    assert 'include_in_schema=False' not in cron_block

    station_status_block = admin_source.split("@router.get(\n    '/api/admin/enrichment/station-status',", 1)[1].split(')\nasync def station_enrichment_operator_status', 1)[0]
    warehouse_status_block = admin_source.split("@router.get(\n    '/api/admin/enrichment/warehouse-status',", 1)[1].split(')\nasync def warehouse_enrichment_operator_status', 1)[0]
    data_status_block = admin_source.split("@router.get(\n    '/api/admin/data-status',", 1)[1].split(')\nasync def admin_data_status', 1)[0]

    assert 'include_in_schema=False' not in station_status_block
    assert 'include_in_schema=False' not in warehouse_status_block
    assert 'include_in_schema=False' not in data_status_block


def test_maintenance_script_schedules_freshness_sweep_and_retention_pruning():
    script = MAINTENANCE_PATH.read_text(encoding='utf-8')

    assert 'EVIDENCE_RECORD_RETENTION_DAYS' in script
    assert 'ADMIN_JOB_RUN_RETENTION_DAYS' in script
    assert 'expire evidence by explicit expires_at' in script
    assert 'expire aged evidence by policy' in script
    assert 'mark stale evidence by policy' in script
    assert 'prune retained evidence history' in script
    assert 'prune admin job history' in script
    assert "WHERE record_status = 'superseded'" in script
    assert "OR record_status = 'archived'" in script
    assert "record_status = 'active'" in script
    assert "freshness_status = 'expired'" in script
    assert "record_status = 'quarantined'" not in script
    assert "SET statement_timeout = '60min'; SELECT * FROM refresh_map_mviews(TRUE);" in script


def test_maintenance_script_has_valid_bash_syntax():
    bash = _usable_bash()

    result = subprocess.run(
        [bash, '-n', str(MAINTENANCE_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_weekly_maintenance_disables_role_timeout_and_targets_real_coordinate_index(tmp_path: Path):
    result, calls = _run_maintenance_with_stubbed_psql(tmp_path, 'weekly')

    assert result.returncode == 0, result.stderr or result.stdout
    assert len(calls) == 7
    assert all('-c statement_timeout=0' in call.split('\t', 1)[0] for call in calls)
    assert any('idx_sys_coords' in call for call in calls)
    assert all('idx_sys_xyz' not in call for call in calls)


def test_weekly_maintenance_finishes_remaining_steps_but_exits_nonzero_after_failure(tmp_path: Path):
    result, calls = _run_maintenance_with_stubbed_psql(
        tmp_path,
        'weekly',
        fail_match='idx_sys_name_lower_pattern',
    )

    assert result.returncode == 1
    assert len(calls) == 7
    combined_output = result.stdout + result.stderr
    assert 'REINDEX idx_sys_name_lower_pattern FAILED (exit 9)' in combined_output
    assert 'Weekly maintenance FAILED: 1 step(s)' in combined_output
