"""2026-08-07 incident: scripts/deploy_main.sh's post-deploy invariants
check failed twice on dirty_truthful_no_bodies, a count documented
elsewhere (CLAUDE.md's "Dirty ratings maintenance" section) as expected to
be transiently nonzero between runs of the 30-minute reconciliation cron
job — not a real regression. The app was healthy and serving the new code
both times; only this verification step was miscalibrated. Regression
test for the fix, not a broader test of the whole (very large) script.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _find_bash() -> str | None:
    """Same resolution as tests/test_nightly_update_heartbeat.py: on
    Windows, a bare 'bash' on PATH can resolve to WSL's bash.exe via a
    broken RPC shim rather than Git Bash, which fails with an unrelated
    "RPC call contains a handle that differs from the declared handle
    type" error that has nothing to do with the script under test."""
    if os.name == 'nt':
        git_bash = (
            Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
            / 'Git' / 'bin' / 'bash.exe'
        )
        if git_bash.is_file():
            return str(git_bash)
    return shutil.which('bash')


def test_post_deploy_invariants_allows_known_bounded_churn():
    deploy_main = (ROOT / 'scripts' / 'deploy_main.sh').read_text(encoding='utf-8')

    assert 'run_data_invariants_receipted.sh' in deploy_main
    assert '--allow-stale-colonisation-status' in deploy_main
    assert '--allow-stale-noneligible' in deploy_main, (
        'deploy_main.sh must pass --allow-stale-noneligible to the '
        'post-deploy invariants check — without it, a deploy fails '
        'whenever the dirty-ratings reconciliation job (which runs on its '
        'own 30-minute cron cycle, independent of deploys) happens to be '
        'mid-cycle, even though nothing is actually wrong.'
    )


def test_wrapper_script_actually_accepts_the_new_flag(tmp_path: Path):
    """Codex Review finding: the assertion above only proves deploy_main.sh
    *passes* the flag — it doesn't prove scripts/run_data_invariants_
    receipted.sh (the wrapper deploy_main.sh actually calls) recognizes it.
    That wrapper has its own hardcoded argument parser with a `*) die
    "unknown flag: $1"` default case; without teaching it the new flag too,
    the first version of this fix would have made deploy_main.sh crash on
    every single deploy, not just occasionally fail — worse than the bug
    it was fixing. Invokes the real wrapper with a deliberately bogus
    DATABASE_URL and asserts it gets past argument parsing to the actual
    connection attempt, rather than dying on "unknown flag" first."""
    bash = _find_bash()
    if bash is None:
        pytest.skip('bash not found on this host')

    # On Windows, bare 'python3' on PATH resolves to the Microsoft Store
    # alias stub (there's no python3.exe in the venv to shadow it, so
    # prepending the venv alone doesn't help — `command -v python3` still
    # finds the broken stub first). That stub prints garbage and fails
    # instead of the wrapper reaching its DB-connection stage. Give bash a
    # real `python3` via a shebang shim that execs the venv interpreter by
    # its original absolute path — copying the .exe itself breaks the
    # venv's relative pyvenv.cfg lookup. Production runs on Linux, where a
    # real python3 always exists and this isn't an issue.
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

    result = subprocess.run(
        [bash, str(ROOT / 'scripts' / 'run_data_invariants_receipted.sh'),
         '--production-safe', '--allow-stale-colonisation-status', '--allow-stale-noneligible'],
        cwd=ROOT,
        env={'DATABASE_URL': 'postgresql://bogus:bogus@127.0.0.1:1/bogus', 'PATH': path},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert 'unknown flag' not in result.stderr, result.stderr
    assert 'unknown flag' not in result.stdout, result.stdout
    # Getting this far (a real, if failing, connection attempt) is the
    # proof the flag parsed — an actual DB isn't needed for that proof.
    assert 'could not connect' in (result.stdout + result.stderr).lower() \
        or 'could not translate' in (result.stdout + result.stderr).lower() \
        or 'connection' in (result.stdout + result.stderr).lower(), (
        f'expected a connection-stage failure, got:\n{result.stdout}\n{result.stderr}'
    )
