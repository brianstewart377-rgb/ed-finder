from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_ingest_watchdog.sh'


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding='utf-8', newline='\n')
    path.chmod(0o755)


def _postgres_timestamp_minutes_ago(
    minutes: float,
    *,
    include_timezone: bool = True,
) -> str:
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    if include_timezone:
        return timestamp.strftime('%Y-%m-%d %H:%M:%S.%f+00')
    return timestamp.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S.%f')


def _logged_actual_age_minutes(output: str) -> float:
    match = re.search(r'actual age ([0-9]+(?:\.[0-9]+)?) minutes', output)
    assert match is not None, output
    return float(match.group(1))


def _run_watchdog(
    tmp_path: Path,
    *,
    heartbeat_url: str = 'https://heartbeat.invalid/eddn-ingest',
    max_age_minutes: int = 30,
    age_seconds: int = 600,
    age_minutes: str = '10.0',
    freshness: str = 'fresh',
    query_result: str = 'success',
    curl_result: str = 'success',
    eddn_timestamp: str = '2026-08-01 12:00:00+00',
    use_real_python: bool = False,
) -> dict[str, object]:
    bash = shutil.which('bash')
    assert bash is not None, 'bash is required for watchdog behavior tests'

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    psql_log = tmp_path / 'psql-calls.log'
    python_log = tmp_path / 'python-calls.log'
    curl_log = tmp_path / 'curl-calls.log'

    _write_executable(fake_bin / 'psql', '''#!/bin/bash
set -eu
printf '%s\n' "$*" >> "${PSQL_CALL_LOG}"
if [[ "${FAKE_QUERY_RESULT:-success}" == 'fail' ]]; then
    echo 'fake psql query failure' >&2
    exit 42
fi
printf '%s\n' "${FAKE_EDDN_TIMESTAMP:-2026-08-01 12:00:00+00}"
''')
    if not use_real_python:
        _write_executable(fake_bin / 'python3', '''#!/bin/bash
set -eu
printf '%s\n' "$*" >> "${PYTHON_CALL_LOG}"
printf '%s\t%s\t%s\n' \
    "${FAKE_AGE_SECONDS}" \
    "${FAKE_AGE_MINUTES}" \
    "${FAKE_FRESHNESS}"
''')
    _write_executable(fake_bin / 'curl', '''#!/bin/bash
set -eu
printf '%s\n' "${!#}" >> "${CURL_CALL_LOG}"
if [[ "${FAKE_CURL_RESULT:-success}" == 'fail' ]]; then
    echo 'fake curl failure' >&2
    exit 28
fi
''')

    env = {
        **os.environ,
        'EDDN_WATCHDOG_HEARTBEAT_URL': heartbeat_url,
        'EDDN_WATCHDOG_MAX_AGE_MINUTES': str(max_age_minutes),
        'DATA_INVARIANTS_DATABASE_URL': 'postgresql://watchdog-readonly/test',
        'DATABASE_URL': 'postgresql://watchdog-fallback/test',
        'FAKE_QUERY_RESULT': query_result,
        'FAKE_EDDN_TIMESTAMP': eddn_timestamp,
        'FAKE_CURL_RESULT': curl_result,
        'PSQL_CALL_LOG': psql_log.as_posix(),
        'PYTHON_CALL_LOG': python_log.as_posix(),
        'CURL_CALL_LOG': curl_log.as_posix(),
        'PATH': f'{fake_bin}{os.pathsep}{os.environ.get("PATH", "")}',
    }
    if not use_real_python:
        env.update({
            'FAKE_AGE_SECONDS': str(age_seconds),
            'FAKE_AGE_MINUTES': age_minutes,
            'FAKE_FRESHNESS': freshness,
        })
    completed = subprocess.run(
        [bash, str(WATCHDOG)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    def calls(path: Path) -> list[str]:
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    return {
        'completed': completed,
        'output': completed.stdout + completed.stderr,
        'psql_calls': calls(psql_log),
        'python_calls': calls(python_log),
        'curl_calls': calls(curl_log),
    }


def test_fresh_ingest_pings_heartbeat_once_and_exits_zero(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/eddn-fresh'
    observation = _run_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        age_seconds=720,
        age_minutes='12.0',
        freshness='fresh',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert len(observation['psql_calls']) == 1
    assert observation['psql_calls'][0].startswith(
        'postgresql://watchdog-readonly/test '
    )
    assert 'SELECT MAX(eddn_updated_at) FROM systems;' in observation['psql_calls'][0]
    assert len(observation['python_calls']) == 1
    assert '12.0 minutes' in observation['output']


def test_stale_ingest_skips_ping_logs_age_and_threshold_and_exits_nonzero(
    tmp_path: Path,
):
    observation = _run_watchdog(
        tmp_path,
        age_seconds=2712,
        age_minutes='45.2',
        freshness='stale',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert '45.2 minutes' in observation['output']
    assert 'threshold 30 minutes' in observation['output']
    assert 'ERROR:' in observation['output']


def test_query_failure_skips_ping_logs_loudly_and_exits_nonzero(tmp_path: Path):
    observation = _run_watchdog(tmp_path, query_result='fail')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert observation['python_calls'] == []
    assert 'ERROR: EDDN ingest watchdog query failed' in observation['output']


def test_unset_url_skips_database_and_ping_and_exits_zero(tmp_path: Path):
    observation = _run_watchdog(tmp_path, heartbeat_url='')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['psql_calls'] == []
    assert observation['python_calls'] == []
    assert observation['curl_calls'] == []
    assert 'watchdog: skipped (heartbeat URL unconfigured)' in observation['output']


def test_ping_failure_does_not_change_fresh_data_exit_code(tmp_path: Path):
    observation = _run_watchdog(
        tmp_path,
        age_seconds=300,
        age_minutes='5.0',
        freshness='fresh',
        curl_result='fail',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert len(observation['curl_calls']) == 1
    assert 'watchdog heartbeat: failed' in observation['output']


def test_real_age_arithmetic_pings_for_timestamp_five_minutes_old(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/eddn-real-fresh'
    observation = _run_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        eddn_timestamp=_postgres_timestamp_minutes_ago(5),
        use_real_python=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert observation['python_calls'] == []
    assert 4.9 <= _logged_actual_age_minutes(observation['output']) <= 5.5


def test_real_age_arithmetic_rejects_timestamp_ninety_minutes_old(tmp_path: Path):
    observation = _run_watchdog(
        tmp_path,
        eddn_timestamp=_postgres_timestamp_minutes_ago(90),
        use_real_python=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert observation['python_calls'] == []
    assert 89.9 <= _logged_actual_age_minutes(observation['output']) <= 90.5


def test_real_age_arithmetic_treats_observed_threshold_boundary_as_stale(
    tmp_path: Path,
):
    # The comparison itself includes equality. In a real run, a timestamp that
    # was exactly 30 minutes old when produced is fractionally older by the time
    # it is evaluated, so the observed boundary fails closed as stale.
    observation = _run_watchdog(
        tmp_path,
        max_age_minutes=30,
        eddn_timestamp=_postgres_timestamp_minutes_ago(30),
        use_real_python=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert observation['python_calls'] == []
    assert 30.0 <= _logged_actual_age_minutes(observation['output']) < 31.0


def test_real_age_arithmetic_rejects_malformed_database_timestamp(tmp_path: Path):
    observation = _run_watchdog(
        tmp_path,
        eddn_timestamp='not-a-postgresql-timestamp',
        use_real_python=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert observation['python_calls'] == []
    assert 'cannot verify freshness from database timestamp' in observation['output']


def test_real_age_arithmetic_assumes_naive_database_timestamp_is_utc(tmp_path: Path):
    # The production parser attaches UTC to a timestamp that has no offset; it
    # does not interpret the value in the container's local timezone.
    heartbeat_url = 'https://heartbeat.invalid/eddn-real-naive-utc'
    observation = _run_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        eddn_timestamp=_postgres_timestamp_minutes_ago(5, include_timezone=False),
        use_real_python=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert observation['python_calls'] == []
    assert 4.9 <= _logged_actual_age_minutes(observation['output']) <= 5.5


def test_ingest_watchdog_is_wired_into_maintenance_runtime():
    script = _read('apps', 'maintenance', 'scripts', 'run_ingest_watchdog.sh')
    compose = _read('docker-compose.yml')
    env_example = _read('env.example')
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    dockerfile = _read('apps', 'maintenance', 'Dockerfile')

    assert 'SELECT MAX(eddn_updated_at) FROM systems;' in script
    assert 'DATABASE_URL_OVERRIDE="${DATA_INVARIANTS_DATABASE_URL:-}"' in script
    assert 'effective_database_url="$DATABASE_URL_OVERRIDE"' in script
    assert 'curl -fsS -m 10 --retry 3 "$WATCHDOG_HEARTBEAT_URL"' in script
    assert 'EDDN_WATCHDOG_HEARTBEAT_URL: ${EDDN_WATCHDOG_HEARTBEAT_URL:-}' in compose
    assert (
        'EDDN_WATCHDOG_MAX_AGE_MINUTES: ${EDDN_WATCHDOG_MAX_AGE_MINUTES:-30}'
        in compose
    )
    assert 'EDDN_WATCHDOG_HEARTBEAT_URL=' in env_example.splitlines()
    assert 'EDDN_WATCHDOG_MAX_AGE_MINUTES=30' in env_example.splitlines()
    assert "dead-man's switch" in env_example
    assert '*/15 * * * * /usr/local/bin/run_ingest_watchdog.sh' in crontab
    assert (
        'COPY apps/maintenance/scripts/run_ingest_watchdog.sh '
        '/usr/local/bin/run_ingest_watchdog.sh'
    ) in ' '.join(dockerfile.split())
    assert '/usr/local/bin/run_ingest_watchdog.sh' in dockerfile
