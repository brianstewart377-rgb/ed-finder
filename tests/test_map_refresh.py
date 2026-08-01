import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MAP_REFRESH = ROOT / 'scripts' / 'run_map_refresh.sh'


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


def _run_map_refresh(
    tmp_path: Path,
    *,
    heartbeat_url: str | None = 'https://heartbeat.invalid/map-refresh',
    dotenv: str | None = None,
    docker_exit_code: int = 0,
    curl_result: str = 'success',
) -> dict[str, object]:
    bash = _find_bash()
    assert bash is not None, 'bash is required for map refresh behavior tests'

    project = tmp_path / 'project'
    scripts_dir = project / 'scripts'
    fake_bin = tmp_path / 'bin'
    scripts_dir.mkdir(parents=True)
    fake_bin.mkdir()
    (project / 'docker-compose.yml').write_text('services: {}\n', encoding='utf-8')
    if dotenv is not None:
        (project / '.env').write_text(dotenv, encoding='utf-8', newline='\n')

    sandboxed_script = scripts_dir / 'run_map_refresh.sh'
    _write_executable(
        sandboxed_script,
        MAP_REFRESH.read_text(encoding='utf-8'),
    )

    docker_log = tmp_path / 'docker-calls.log'
    curl_log = tmp_path / 'curl-calls.log'

    _write_executable(fake_bin / 'docker', '''#!/bin/bash
set -eu
printf '%s|%s\n' "${MAP_REFRESH_ENV_LEAK_PROBE-<unset>}" "$*" >> "${DOCKER_CALL_LOG}"
exit "${FAKE_DOCKER_EXIT_CODE}"
''')
    _write_executable(fake_bin / 'curl', '''#!/bin/bash
set -eu
printf '%s|%s\n' "${!#}" "${MAP_REFRESH_ENV_LEAK_PROBE-<unset>}" >> "${CURL_CALL_LOG}"
if [[ "${FAKE_CURL_RESULT:-success}" == 'fail' ]]; then
    echo 'fake curl failure' >&2
    exit 28
fi
''')

    env = {
        **os.environ,
        'DOCKER_CALL_LOG': docker_log.as_posix(),
        'CURL_CALL_LOG': curl_log.as_posix(),
        'FAKE_DOCKER_EXIT_CODE': str(docker_exit_code),
        'FAKE_CURL_RESULT': curl_result,
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
            'map-refresh-test',
            str(fake_bin),
            str(sandboxed_script),
        ]
    else:
        env['PATH'] = f'{fake_bin}:{os.environ.get("PATH", "")}'
        command = [bash, str(sandboxed_script)]
    env.pop('MAP_REFRESH_HEARTBEAT_URL', None)
    env.pop('MAP_REFRESH_ENV_LEAK_PROBE', None)
    if heartbeat_url is not None:
        env['MAP_REFRESH_HEARTBEAT_URL'] = heartbeat_url

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
        'docker_calls': calls(docker_log),
        'curl_calls': calls(curl_log),
    }


def test_unset_url_runs_refresh_without_ping_and_exits_zero(tmp_path: Path):
    observation = _run_map_refresh(tmp_path, heartbeat_url=None)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert len(observation['docker_calls']) == 1
    assert observation['curl_calls'] == []
    assert 'heartbeat: skipped (unconfigured)' in observation['output']


def test_success_pings_once_and_exits_zero(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/map-refresh-success'
    observation = _run_map_refresh(tmp_path, heartbeat_url=heartbeat_url)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [f'{heartbeat_url}|<unset>']
    assert 'heartbeat: sent' in observation['output']


def test_refresh_failure_sends_no_ping_and_preserves_exit_code(tmp_path: Path):
    observation = _run_map_refresh(tmp_path, docker_exit_code=37)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 37, observation['output']
    assert observation['curl_calls'] == []
    assert 'ERROR: map refresh failed (exit 37)' in observation['output']


def test_ping_failure_does_not_change_success_exit_code(tmp_path: Path):
    observation = _run_map_refresh(tmp_path, curl_result='fail')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert len(observation['curl_calls']) == 1
    assert 'heartbeat: ping-failed' in observation['output']


def test_refresh_invocation_enables_psql_on_error_stop(tmp_path: Path):
    observation = _run_map_refresh(tmp_path, heartbeat_url=None)

    assert len(observation['docker_calls']) == 1
    invocation = observation['docker_calls'][0]
    assert 'compose exec -T postgres psql' in invocation
    assert 'ON_ERROR_STOP=1' in invocation
    assert 'SELECT * FROM refresh_map_mviews(TRUE)' in invocation


def test_url_is_read_from_dotenv_without_sourcing_other_keys(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/map-refresh-dotenv?token=a&mode=b'
    observation = _run_map_refresh(
        tmp_path,
        heartbeat_url=None,
        dotenv=(
            f'MAP_REFRESH_HEARTBEAT_URL={heartbeat_url}\n'
            'export MAP_REFRESH_ENV_LEAK_PROBE=must-not-leak\n'
        ),
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['docker_calls'][0].startswith('<unset>|')
    assert observation['curl_calls'] == [f'{heartbeat_url}|<unset>']
    assert 'must-not-leak' not in observation['output']


def test_env_example_contains_map_refresh_heartbeat():
    env_example = (ROOT / 'env.example').read_text(encoding='utf-8')

    assert 'MAP_REFRESH_HEARTBEAT_URL=' in env_example.splitlines()
