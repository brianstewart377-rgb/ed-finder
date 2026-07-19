import os
import shutil
import subprocess
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

    assert 'test: export DATABASE_URL :=' in makefile
    assert 'test: export REDIS_URL :=' in makefile
    assert 'test: export CORS_ORIGINS :=' in makefile
    assert 'test: export ADMIN_TOKEN :=' in makefile
    assert 'test: export LOG_LEVEL :=' in makefile
    assert 'test: export EXPOSE_ERROR_DETAIL := true' in makefile
    assert '\tDATABASE_URL=' not in makefile


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
    assert '.venv/Scripts/python.exe -B -m pytest' in result.stdout
    assert 'PYTHONDONTWRITEBYTECODE=1' not in result.stdout
