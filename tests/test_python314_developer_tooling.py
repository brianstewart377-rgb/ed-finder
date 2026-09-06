from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8-sig")


@pytest.mark.parametrize(
    "parts",
    (
        ("scripts", "dev", "bootstrap-windows.ps1"),
        ("scripts", "dev", "doctor.ps1"),
        ("frontend", "scripts", "types-gen.mjs"),
        ("scripts", "checks", "openapi-drift.sh"),
        ("scripts", "checks", "local-ci-parity.sh"),
        ("docs", "development", "windows-dev-environment.md"),
        ("frontend", "README.md"),
        ("docs", "api-contracts.md"),
    ),
)
def test_current_developer_launchers_and_docs_have_no_pre314_fallback(parts: tuple[str, ...]):
    source = _read(*parts)

    assert re.search(r"\b3\.(?:11|12)\b", source) is None


def test_windows_bootstrap_selects_and_verifies_exact_cpython314():
    source = _read("scripts", "dev", "bootstrap-windows.ps1")

    assert "& py -3.14 --version" in source
    assert "args = @('-3.14')" in source
    assert source.count("$runtime -ne 'cpython:3.14'") == 2
    assert "$venvRuntime -ne 'cpython:3.14'" in source
    assert "The repository virtualenv must use CPython 3.14.x" in source


def test_windows_doctor_fails_closed_on_non_cpython314():
    source = _read("scripts", "dev", "doctor.ps1")

    assert "& py -3.14 --version" in source
    assert "path = 'py -3.14'" in source
    assert source.count("ok = ($runtime -eq 'cpython:3.14')") == 2
    assert "The Python launcher did not select CPython 3.14.x." in source
    assert source.count("'python314_required'") == 2
    assert "if (-not $records.python.ok)" in source


def test_react_openapi_generator_only_accepts_cpython314():
    source = _read("frontend", "scripts", "types-gen.mjs")

    assert "['py', '-3.14']" in source
    assert "['python3.14']" in source
    assert 'sys.implementation.name == "cpython"' in source
    assert "sys.version_info[:2] == (3, 14)" in source
    assert "No usable CPython 3.14.x interpreter found" in source


@pytest.mark.parametrize(
    "script_name",
    ("openapi-drift.sh", "local-ci-parity.sh"),
)
def test_shell_developer_launchers_verify_selected_cpython314(script_name: str):
    source = _read("scripts", "checks", script_name)

    assert "command -v python3.14" in source
    assert "assert_python314()" in source
    assert 'sys.implementation.name == "cpython"' in source
    assert "sys.version_info[:2] == (3, 14)" in source
    assert 'assert_python314 "$PYTHON_BIN"' in source


def test_current_windows_and_generation_docs_state_exact_cpython314():
    windows = _read("docs", "development", "windows-dev-environment.md")
    frontend = _read("frontend", "README.md")
    api_contracts = _read("docs", "api-contracts.md")

    assert "CPython `3.14.x`" in windows
    assert "CPython 3.14.x environment" in frontend
    assert "exact\nCPython 3.14.x execution surface" in api_contracts
