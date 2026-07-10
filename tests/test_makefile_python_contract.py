from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_makefile_prefers_repo_venv_python_before_global_python():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    assert 'ifeq ($(OS),Windows_NT)' in makefile
    assert 'VENV_PYTHON := .venv\\Scripts\\python.exe' in makefile
    assert 'VENV_PYTHON := .venv/bin/python' in makefile
    assert 'PYTHON ?= $(VENV_PYTHON)' in makefile
    assert 'PYTHON ?= python' in makefile


def test_makefile_test_target_uses_configured_python_variable_everywhere():
    makefile = ROOT.joinpath('Makefile').read_text(encoding='utf-8')

    assert '\t$(PYTHON) -m unittest discover -s tests -p test_smoke.py' in makefile
    assert '\t$(PYTHON) -m pytest tests/integration/ -q' in makefile
    assert '\tpython -m unittest discover -s tests -p test_smoke.py' not in makefile
    assert '\tpython -m pytest tests/integration/ -q' not in makefile
