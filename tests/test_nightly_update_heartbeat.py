import os
from pathlib import Path
import shutil
import subprocess


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
    curl_result: str = 'success',
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
if [[ "$*" == *'-tAc'* ]]; then
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

    env = {
        **os.environ,
        'DOCKER_CALL_LOG': docker_log.as_posix(),
        'CURL_CALL_LOG': curl_log.as_posix(),
        'FAKE_DEGRADED': '1' if degraded else '0',
        'FAKE_FATAL': '1' if fatal else '0',
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
