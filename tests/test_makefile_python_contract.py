import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_makefile_prefers_repo_venv_python_before_global_python():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    assert 'ifeq ($(OS),Windows_NT)' in makefile
    assert 'VENV_PYTHON := .venv/Scripts/python.exe' in makefile
    assert 'VENV_PYTHON := .venv/bin/python' in makefile
    assert 'PYTHON ?= $(VENV_PYTHON)' in makefile
    assert 'PYTHON ?= python' in makefile


def test_makefile_test_target_uses_configured_python_variable_everywhere():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    assert '\t$(PYTHON) -m unittest discover -s tests -p test_smoke.py' in makefile
    assert '\t$(PYTHON) -m pytest tests/integration/ -q' in makefile
    assert '\tpython -m unittest discover -s tests -p test_smoke.py' not in makefile
    assert '\tpython -m pytest tests/integration/ -q' not in makefile


def test_makefile_exports_python_policy_without_shell_specific_assignment():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    assert 'export PYTHONDONTWRITEBYTECODE := 1' in makefile
    assert '\tPYTHONDONTWRITEBYTECODE=1 ' not in makefile


def test_makefile_test_target_exports_cross_platform_integration_defaults():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    for variable in (
        'DATABASE_URL',
        'REDIS_URL',
        'CORS_ORIGINS',
        'ADMIN_TOKEN',
        'LOG_LEVEL',
        'EXPOSE_ERROR_DETAIL',
    ):
        assert f'test: export {variable} := $(if $(strip $(value {variable}))' in makefile
    assert '\tDATABASE_URL=' not in makefile


def test_makefile_preserves_dollar_signs_in_environment_overrides(tmp_path):
    make = shutil.which('make')
    if make is None:
        pytest.skip('GNU Make is not installed')

    database_url = 'postgresql://u:pa$ss@localhost/db'
    probe = tmp_path / 'Makefile'
    probe.write_text(
        f'include {ROOT.joinpath("Makefile").as_posix()}\n'
        'test:\n'
        f'\t@"{Path(sys.executable).as_posix()}" -c '
        '"import os; print(os.environ[\'DATABASE_URL\'])"\n',
        encoding='utf-8',
    )
    result = subprocess.run(
        [make, '--no-print-directory', '-f', str(probe), 'test'],
        cwd=ROOT,
        env={**os.environ, 'DATABASE_URL': database_url},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == database_url


@pytest.mark.parametrize(
    ('variable', 'expected'),
    (
        ('DATABASE_URL', 'postgresql://edfinder:edfinder@127.0.0.1:55432/edfinder'),
        ('REDIS_URL', 'redis://localhost:6379/15'),
        ('CORS_ORIGINS', 'http://test'),
        ('ADMIN_TOKEN', 'test-admin-token'),
        ('LOG_LEVEL', 'WARNING'),
        ('EXPOSE_ERROR_DETAIL', 'true'),
    ),
)
def test_makefile_treats_empty_integration_environment_values_as_missing(tmp_path, variable, expected):
    make = shutil.which('make')
    if make is None:
        pytest.skip('GNU Make is not installed')

    probe = tmp_path / 'Makefile'
    probe.write_text(
        f'include {ROOT.joinpath("Makefile").as_posix()}\n'
        'test:\n'
        f'\t@"{Path(sys.executable).as_posix()}" -c '
        f'"import os; print(os.environ[\'{variable}\'])"\n',
        encoding='utf-8',
    )
    result = subprocess.run(
        [make, '--no-print-directory', '-f', str(probe), 'test'],
        cwd=ROOT,
        env={**os.environ, variable: ''},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == expected


@pytest.mark.skipif(os.name != 'nt', reason='Windows-native GNU Make contract')
def test_windows_make_dry_run_uses_cmd_safe_python_command():
    make = shutil.which('make')
    if make is None:
        pytest.skip('GNU Make is not installed')

    result = subprocess.run(
        [make, '--dry-run', 'test-unit'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_python = '.venv/Scripts/python.exe' if ROOT.joinpath('.venv', 'Scripts', 'python.exe').exists() else 'python'
    assert f'{expected_python} -B -m pytest' in result.stdout
    assert 'PYTHONDONTWRITEBYTECODE=1' not in result.stdout
