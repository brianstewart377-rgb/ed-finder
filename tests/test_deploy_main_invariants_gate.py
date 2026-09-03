"""Invariant-wrapper contracts after retirement of the V2 deploy entrypoint."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _find_bash() -> str | None:
    if os.name == 'nt':
        git_bash = (
            Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
            / 'Git' / 'bin' / 'bash.exe'
        )
        if git_bash.is_file():
            return str(git_bash)
    return shutil.which('bash')


def test_v2_deploy_entrypoint_cannot_run_post_deploy_invariants():
    deploy_main = (ROOT / 'scripts' / 'deploy_main.sh').read_text(encoding='utf-8')

    assert 'RETIRED — V2 single-host deployment entrypoint' in deploy_main
    assert 'exit 64' in deploy_main
    assert 'run_data_invariants_receipted.sh' not in deploy_main
    assert '--allow-stale-colonisation-status' not in deploy_main
    assert '--allow-stale-noneligible' not in deploy_main


def test_invariant_wrapper_still_accepts_the_bounded_waiver_flags(tmp_path: Path):
    """The invariant wrapper remains independently testable repository tooling.

    Exercise its parser with a deliberately unreachable database and prove both
    bounded waiver flags are accepted and receipted. This no longer implies
    that a retired deploy wrapper may invoke it against production.
    """
    bash = _find_bash()
    if bash is None:
        pytest.skip('bash not found on this host')

    venv_python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    path = os.environ['PATH']
    if venv_python.is_file():
        shim_dir = tmp_path / 'python_shim'
        shim_dir.mkdir()
        shim = shim_dir / 'python3'
        shim.write_text(
            f'#!/bin/sh\nexec "{venv_python.as_posix()}" "$@"\n',
            encoding='utf-8',
        )
        shim.chmod(0o755)
        path = f"{shim_dir}{os.pathsep}{path}"

    receipt_file = tmp_path / 'receipt.json'
    result = subprocess.run(
        [bash, str(ROOT / 'scripts' / 'run_data_invariants_receipted.sh'),
         '--production-safe', '--allow-stale-colonisation-status', '--allow-stale-noneligible',
         '--receipt-file', str(receipt_file)],
        cwd=ROOT,
        env={'DATABASE_URL': 'postgresql://bogus:bogus@127.0.0.1:1/bogus', 'PATH': path},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert 'unknown flag' not in result.stderr, result.stderr
    assert 'unknown flag' not in result.stdout, result.stdout
    assert 'could not connect' in (result.stdout + result.stderr).lower() \
        or 'could not translate' in (result.stdout + result.stderr).lower() \
        or 'connection' in (result.stdout + result.stderr).lower(), (
        f'expected a connection-stage failure, got:\n{result.stdout}\n{result.stderr}'
    )

    assert receipt_file.is_file(), 'wrapper should write a receipt even on a failed run'
    receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
    assert receipt['allow_stale_noneligible'] is True
    assert receipt['allow_stale_colonisation_status'] is True
