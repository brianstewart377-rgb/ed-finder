from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / 'apps' / 'api' / 'src' / 'main.py'
ADMIN_PATH = ROOT / 'apps' / 'api' / 'src' / 'routers' / 'admin.py'
MAINTENANCE_PATH = ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_maintenance.sh'


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


def test_maintenance_script_has_valid_bash_syntax():
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required for maintenance script syntax test')

    probe = subprocess.run(
        [bash, '-lc', 'printf ready'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != 'ready':
        pytest.skip('usable bash is unavailable for maintenance script syntax test')

    result = subprocess.run(
        [bash, '-n', str(MAINTENANCE_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
