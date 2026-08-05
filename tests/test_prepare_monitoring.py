import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PREPARE_MONITORING = ROOT / 'scripts' / 'prepare_monitoring.sh'


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


def _run_prepare_monitoring(
    tmp_path: Path,
    *,
    configured_token: str | None = None,
) -> dict[str, object]:
    bash = _find_bash()
    assert bash is not None, 'bash is required for monitoring preparation behavior tests'

    project = tmp_path / 'project'
    scripts_dir = project / 'scripts'
    config_dir = project / 'config'
    fake_bin = tmp_path / 'bin'
    scripts_dir.mkdir(parents=True)
    config_dir.mkdir()
    fake_bin.mkdir()

    (project / '.env').write_text(
        'GRAFANA_PASSWORD_FILE=./config/grafana_admin_password\n'
        f'HEALTHCHECKS_PROMETHEUS_TOKEN_FILE={configured_token or ""}\n'
        'HEALTHCHECKS_PROMETHEUS_TARGETS_FILE=\n',
        encoding='utf-8',
        newline='\n',
    )
    (config_dir / 'grafana_admin_password').write_text(
        'a-real-grafana-password\n',
        encoding='utf-8',
        newline='\n',
    )
    for name in (
        'healthchecks_readonly_api_key.disabled',
        'healthchecks_targets.empty.yml',
    ):
        (config_dir / name).write_bytes((ROOT / 'config' / name).read_bytes())
    if configured_token is not None:
        configured_path = project / configured_token.removeprefix('./')
        configured_path.write_text(
            'not-configured\n',
            encoding='utf-8',
            newline='\n',
        )

    sandboxed_script = scripts_dir / 'prepare_monitoring.sh'
    _write_executable(
        sandboxed_script,
        PREPARE_MONITORING.read_text(encoding='utf-8'),
    )

    stat_log = tmp_path / 'stat-calls.log'
    _write_executable(fake_bin / 'uname', '''#!/bin/bash
set -eu
printf '%s\n' 'Linux'
''')
    _write_executable(fake_bin / 'stat', '''#!/bin/bash
set -eu
printf '%s\n' "${!#}" >> "${STAT_CALL_LOG}"
printf '%s\n' '472:0 400'
''')

    env = {
        **os.environ,
        'STAT_CALL_LOG': stat_log.as_posix(),
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
                'exec /usr/bin/bash "$script" --check'
            ),
            'prepare-monitoring-test',
            str(fake_bin),
            str(sandboxed_script),
        ]
    else:
        env['PATH'] = f'{fake_bin}:{os.environ.get("PATH", "")}'
        command = [bash, str(sandboxed_script), '--check']

    completed = subprocess.run(
        command,
        cwd=project,
        env=env,
        text=True,
        encoding='utf-8',
        capture_output=True,
        check=False,
    )
    stat_calls = (
        stat_log.read_text(encoding='utf-8').splitlines()
        if stat_log.exists()
        else []
    )
    return {
        'completed': completed,
        'output': completed.stdout + completed.stderr,
        'stat_calls': stat_calls,
    }


def test_check_succeeds_with_disabled_healthchecks_defaults(tmp_path: Path):
    observation = _run_prepare_monitoring(tmp_path)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert '[OK] grafana_admin_password: 472:0 400' in observation['output']
    assert '[OK] monitoring file permissions are ready (check mode)' in observation['output']
    stat_calls = observation['stat_calls']
    assert isinstance(stat_calls, list)
    assert len(stat_calls) == 1
    assert stat_calls[0].replace('\\', '/').endswith(
        '/config/grafana_admin_password'
    )


def test_check_rejects_configured_token_without_read_only_key(tmp_path: Path):
    observation = _run_prepare_monitoring(
        tmp_path,
        configured_token='./config/healthchecks_readonly_api_key',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 1, observation['output']
    assert (
        '[ERROR] Healthchecks key file does not contain a read-only hcr_ key'
        in observation['output']
    )