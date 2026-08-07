import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
NIGHTLY_UPDATE = ROOT / 'scripts' / 'nightly_update.sh'


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding='utf-8', newline='\n')
    path.chmod(0o755)


def _find_bash() -> str | None:
    if os.name == 'nt':
        git_bash = (
            Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
            / 'Git'
            / 'bin'
            / 'bash.exe'
        )
        if git_bash.is_file():
            return str(git_bash)
    return shutil.which('bash')


def _run_nightly_update(
    tmp_path: Path,
    *,
    heartbeat_url: str | None = 'https://heartbeat.invalid/nightly',
    dotenv: str | None = None,
    degraded: bool = False,
    fatal: bool = False,
    pg_count_failure: bool = False,
    started_at_write_failure: bool = False,
    curl_result: str = 'success',
    use_real_flock: bool = False,
) -> dict[str, object]:
    bash = _find_bash()
    assert bash is not None, 'bash is required for nightly update behavior tests'

    project = tmp_path / 'project'
    scripts_dir = project / 'scripts'
    log_dir = tmp_path / 'logs'
    dump_dir = tmp_path / 'dumps'
    fake_bin = tmp_path / 'bin'
    scripts_dir.mkdir(parents=True)
    log_dir.mkdir()
    dump_dir.mkdir()
    fake_bin.mkdir()
    (project / 'docker-compose.yml').write_text('services: {}\n', encoding='utf-8')
    if dotenv is not None:
        (project / '.env').write_text(dotenv, encoding='utf-8', newline='\n')

    script = NIGHTLY_UPDATE.read_text(encoding='utf-8')
    script = script.replace(
        'LOG_DIR=/data/logs',
        f"LOG_DIR='{log_dir.as_posix()}'",
        1,
    ).replace(
        'DUMP_DIR=/data/dumps',
        f"DUMP_DIR='{dump_dir.as_posix()}'",
        1,
    )
    sandboxed_script = scripts_dir / 'nightly_update.sh'
    _write_executable(sandboxed_script, script)

    docker_log = tmp_path / 'docker-calls.log'
    curl_log = tmp_path / 'curl-calls.log'

    _write_executable(fake_bin / 'date', '''#!/bin/bash
set -eu
case "${1:-}" in
    +%u) printf '%s\n' '2' ;;
    +%d) printf '%s\n' '02' ;;
    +%s) printf '%s\n' '2000000000' ;;
    -u) printf '%s\n' '2033-05-18T03:33:20Z' ;;
    *) printf '%s\n' '2033-05-18 03:33:20' ;;
esac
''')
    _write_executable(fake_bin / 'wget', '''#!/bin/bash
set -eu
output=''
while (( $# > 0 )); do
    if [[ "$1" == '-O' ]]; then
        shift
        output="$1"
    fi
    shift
done
[[ -n "$output" ]]
: > "$output"
''')
    _write_executable(fake_bin / 'docker', '''#!/bin/bash
set -eu
printf '%s\n' "$*" >> "${DOCKER_CALL_LOG}"
if [[ "${FAKE_FATAL:-0}" == '1' && "$*" == *'systems_1day.json.gz'* ]]; then
    exit 23
fi
if [[ "${FAKE_DEGRADED:-0}" == '1' && "$*" == *'galaxy_stations.json.gz'* ]]; then
    exit 17
fi
if [[ "${FAKE_STARTED_AT_WRITE_FAILURE:-0}" == '1' && "$*" == *"nightly_update_started_at_epoch"* ]]; then
    exit 55
fi
if [[ "$*" == *'-tAc'* ]]; then
    if [[ "${FAKE_PG_COUNT_FAILURE:-0}" == '1' ]]; then
        exit 42
    fi
    printf '%s\n' '0'
fi
''')
    _write_executable(fake_bin / 'df', '''#!/bin/bash
set -eu
printf '%s\n' 'Filesystem Size Used Avail Use% Mounted on'
printf '%s\n' 'fakefs 100G 20G 80G 20% /data'
''')
    _write_executable(fake_bin / 'curl', '''#!/bin/bash
set -eu
printf '%s|%s\n' "${!#}" "${NIGHTLY_ENV_LEAK_PROBE-<unset>}" >> "${CURL_CALL_LOG}"
if [[ "${FAKE_CURL_RESULT:-success}" == 'fail' ]]; then
    echo 'fake curl failure' >&2
    exit 28
fi
''')
    if not use_real_flock:
        # Default: always "acquire" the lock. These tests exercise a single
        # run at a time and assert on heartbeat/docker/vacuum behavior
        # further downstream in the script — not the lock itself — and this
        # repo's tests run on Windows dev machines too, where Git Bash does
        # not ship flock. test_concurrent_run_skips_instead_of_stacking below
        # uses the real system flock instead (skipping if unavailable) to
        # actually exercise contention.
        _write_executable(fake_bin / 'flock', '#!/bin/bash\nexit 0\n')

    lock_file = tmp_path / 'nightly-update.lock'

    env = {
        **os.environ,
        'DOCKER_CALL_LOG': docker_log.as_posix(),
        'CURL_CALL_LOG': curl_log.as_posix(),
        'FAKE_DEGRADED': '1' if degraded else '0',
        'FAKE_FATAL': '1' if fatal else '0',
        'FAKE_PG_COUNT_FAILURE': '1' if pg_count_failure else '0',
        'FAKE_STARTED_AT_WRITE_FAILURE': '1' if started_at_write_failure else '0',
        'FAKE_CURL_RESULT': curl_result,
        'NIGHTLY_LOCK_FILE': lock_file.as_posix(),
    }
    for key in list(env):
        if key.lower() == 'path':
            del env[key]
    if os.name == 'nt':
        command = [
            bash,
            '-c',
            (
                'fake_bin="$(/usr/bin/cygpath -u "$1")"; '
                'script="$(/usr/bin/cygpath -u "$2")"; '
                'PATH="$fake_bin:/usr/bin:/bin"; export PATH; '
                'exec /usr/bin/bash "$script"'
            ),
            'nightly-update-test',
            str(fake_bin),
            str(sandboxed_script),
        ]
    else:
        env['PATH'] = f'{fake_bin}:{os.environ.get("PATH", "")}'
        command = [bash, str(sandboxed_script)]
    env.pop('NIGHTLY_UPDATE_HEARTBEAT_URL', None)
    env.pop('NIGHTLY_ENV_LEAK_PROBE', None)
    if heartbeat_url is not None:
        env['NIGHTLY_UPDATE_HEARTBEAT_URL'] = heartbeat_url

    completed = subprocess.run(
        command,
        cwd=project,
        env=env,
        text=True,
        encoding='utf-8',
        capture_output=True,
        check=False,
    )

    def calls(path: Path) -> list[str]:
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    return {
        'completed': completed,
        'output': completed.stdout + completed.stderr,
        'curl_calls': calls(curl_log),
        'docker_calls': calls(docker_log),
    }


def test_unset_url_preserves_successful_behavior_without_ping(tmp_path: Path):
    observation = _run_nightly_update(tmp_path, heartbeat_url=None)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == []
    assert 'Nightly update complete' in observation['output']
    assert 'heartbeat: skipped' in observation['output']


def test_clean_run_pings_plain_url_exactly_once(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/nightly-clean'
    observation = _run_nightly_update(tmp_path, heartbeat_url=heartbeat_url)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}|<unset>']
    assert all('/fail' not in call for call in observation['curl_calls'])
    assert 'heartbeat: sent-clean' in observation['output']
    docker_calls = observation['docker_calls']
    vacuum_calls = [call for call in docker_calls if 'VACUUM ANALYZE' in call]
    expected_vacuum_tables = (
        'cluster_summary',
        'stations',
        'system_archetype_scores',
        'system_archetype_traits',
    )
    assert len(vacuum_calls) == 4
    assert all(
        any(f'VACUUM ANALYZE {table}' in call for call in vacuum_calls)
        for table in expected_vacuum_tables
    )
    assert all('VACUUM ANALYZE systems' not in call for call in vacuum_calls)
    assert all('VACUUM ANALYZE ratings' not in call for call in vacuum_calls)
    stamp_index = next(i for i, call in enumerate(docker_calls) if 'last_nightly_update' in call)
    last_vacuum_index = max(i for i, call in enumerate(docker_calls) if 'VACUUM ANALYZE' in call)
    assert stamp_index > last_vacuum_index


def test_degraded_run_pings_fail_url_exactly_once(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/nightly-degraded'
    observation = _run_nightly_update(
        tmp_path,
        heartbeat_url=heartbeat_url,
        degraded=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}/fail|<unset>']
    assert f'{heartbeat_url}|<unset>' not in observation['curl_calls']
    assert 'Nightly update completed WITH WARNINGS' in observation['output']
    assert 'heartbeat: sent-fail' in observation['output']
    assert all("'last_nightly_update'" not in call for call in observation['docker_calls'])


def test_failed_database_measurement_is_degraded_and_cannot_send_clean_heartbeat(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/nightly-measurement-failed'
    observation = _run_nightly_update(
        tmp_path,
        heartbeat_url=heartbeat_url,
        pg_count_failure=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}/fail|<unset>']
    assert 'Database measurement failed' in observation['output']
    assert all("'last_nightly_update'" not in call for call in observation['docker_calls'])


def test_nightly_psql_calls_bound_the_role_statement_timeout(tmp_path: Path):
    observation = _run_nightly_update(tmp_path)
    psql_calls = [
        call for call in observation['docker_calls']
        if ' postgres psql ' in f' {call} '
    ]

    assert psql_calls
    assert all('-e PGOPTIONS=-c statement_timeout=1800000' in call for call in psql_calls)


def test_fatal_abort_sends_no_heartbeat(tmp_path: Path):
    observation = _run_nightly_update(tmp_path, fatal=True)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 1, observation['output']
    assert observation['curl_calls'] == []
    assert '[FATAL]' in observation['output']


def test_ping_failure_does_not_change_clean_run_exit_code(tmp_path: Path):
    observation = _run_nightly_update(tmp_path, curl_result='fail')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert len(observation['curl_calls']) == 1
    assert 'heartbeat: ping-failed' in observation['output']


def test_url_is_read_from_dotenv_without_sourcing_other_keys(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/from-dotenv?token=a&mode=b'
    observation = _run_nightly_update(
        tmp_path,
        heartbeat_url=None,
        dotenv=(
            f'NIGHTLY_UPDATE_HEARTBEAT_URL={heartbeat_url}\n'
            'export NIGHTLY_ENV_LEAK_PROBE=must-not-leak\n'
        ),
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}|<unset>']
    assert 'must-not-leak' not in observation['output']


def test_env_example_documents_nightly_update_heartbeat_clean_fail_split():
    env_example = (ROOT / 'env.example').read_text(encoding='utf-8')

    assert 'NIGHTLY_UPDATE_HEARTBEAT_URL=' in env_example.splitlines()
    assert 'clean' in env_example.lower()
    assert '/fail' in env_example


def test_started_at_write_failure_degrades_the_run(tmp_path: Path):
    """Codex Review finding: if the started_at write fails but the run
    otherwise proceeds, the exporter would keep reading the PREVIOUS run's
    start/completion for this run's entire duration — a real regression
    would look identical to a healthy run the whole time. Escalating the
    failure to warn() makes it degrade the run (heartbeat /fail path)
    instead of silently continuing untracked."""
    heartbeat_url = 'https://heartbeat.invalid/nightly-started-at-failure'
    observation = _run_nightly_update(
        tmp_path,
        heartbeat_url=heartbeat_url,
        started_at_write_failure=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}/fail|<unset>']
    assert 'nightly_update_started_at_epoch recording failed' in observation['output']
    assert 'this run\'s duration will not be reliably trackable' in observation['output']
    assert 'Nightly update completed WITH WARNINGS' in observation['output']


def test_clean_run_records_start_and_completion_epochs(tmp_path: Path):
    observation = _run_nightly_update(tmp_path)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    started_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_started_at_epoch'" in call
    ]
    completed_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_completed_at_epoch'" in call
    ]
    assert len(started_calls) == 1
    assert len(completed_calls) == 1
    assert 'nightly_update_started_at_epoch recorded' in observation['output']
    assert 'nightly_update_completed_at_epoch recorded' in observation['output']


def test_degraded_run_still_records_completion_epoch(tmp_path: Path):
    """Unlike the last_nightly_update timestamp (only written on a clean
    run), start/completion must be recorded regardless of outcome — a run
    that degrades after taking far too long is exactly the case this
    metric exists to catch, not one to exclude."""
    observation = _run_nightly_update(tmp_path, degraded=True)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    started_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_started_at_epoch'" in call
    ]
    completed_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_completed_at_epoch'" in call
    ]
    assert len(started_calls) == 1
    assert len(completed_calls) == 1


def test_fatal_abort_still_records_completion_epoch(tmp_path: Path):
    """The completion trap is installed via `trap ... EXIT`, which must
    fire even on fatal()'s early `exit 1` — a run that fails after running
    for hours is the highest-value case to have visibility into, not one
    where the trap should be skipped."""
    observation = _run_nightly_update(tmp_path, fatal=True)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 1, observation['output']
    started_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_started_at_epoch'" in call
    ]
    completed_calls = [
        call for call in observation['docker_calls']
        if "'nightly_update_completed_at_epoch'" in call
    ]
    assert len(started_calls) == 1
    assert len(completed_calls) == 1


def test_skipped_run_due_to_overlap_records_no_start_or_completion(tmp_path: Path):
    """Both writes are installed after the overlap-guard lock check — a run
    skipped because a previous run is still active must not overwrite the
    truly-active instance's start time with its own, or record a spurious
    completion for a run it never actually performed."""
    if shutil.which('flock') is None:
        pytest.skip('flock is not available on this host (e.g. Windows Git Bash)')

    lock_file = tmp_path / 'nightly-update.lock'
    holder = subprocess.Popen(['flock', '-n', str(lock_file), 'sleep', '10'])
    try:
        for _ in range(50):
            probe = subprocess.run(['flock', '-n', str(lock_file), '-c', 'true'])
            if probe.returncode != 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail('background holder never acquired the lock')

        observation = _run_nightly_update(tmp_path, use_real_flock=True)
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    completed = observation['completed']
    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['docker_calls'] == []


def test_concurrent_run_skips_instead_of_stacking(tmp_path: Path):
    """2026-08-06 incident regression: nightly_update.sh had no overlap
    guard, so a backlog-clearing regional-analysis backfill that ran past
    24h didn't stop cron from starting a second full run on top of it —
    the two then ran concurrently for two more days, contending on the same
    upserts, neither ever reaching the heartbeat ping. A still-running
    instance must now make the next invocation skip immediately instead."""
    if shutil.which('flock') is None:
        pytest.skip('flock is not available on this host (e.g. Windows Git Bash)')

    lock_file = tmp_path / 'nightly-update.lock'
    holder = subprocess.Popen(['flock', '-n', str(lock_file), 'sleep', '10'])
    try:
        for _ in range(50):
            probe = subprocess.run(['flock', '-n', str(lock_file), '-c', 'true'])
            if probe.returncode != 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail('background holder never acquired the lock')

        observation = _run_nightly_update(tmp_path, use_real_flock=True)
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    completed = observation['completed']
    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert 'still active' in observation['output']
    assert observation['docker_calls'] == []
    assert observation['curl_calls'] == []
