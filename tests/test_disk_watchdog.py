import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_disk_watchdog.sh'


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding='utf-8', newline='\n')
    path.chmod(0o755)


def _run_disk_watchdog(
    tmp_path: Path,
    *,
    heartbeat_url: str = 'https://heartbeat.invalid/disk',
    min_free_gb: str | int = 40,
    max_percent_used: str | int = 80,
    watchdog_path: str = '/data',
    free_bytes: int = 80_000_000_000,
    percent_used: int = 20,
    df_result: str = 'success',
    df_output: str = '',
    curl_result: str = 'success',
) -> dict[str, object]:
    bash = shutil.which('bash')
    assert bash is not None, 'bash is required for watchdog behavior tests'

    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    df_log = tmp_path / 'df-calls.log'
    curl_log = tmp_path / 'curl-calls.log'

    _write_executable(fake_bin / 'df', '''#!/bin/bash
set -eu
printf '%s\n' "$*" >> "${DF_CALL_LOG}"
if [[ "${FAKE_DF_RESULT:-success}" == 'fail' ]]; then
    echo 'fake df measurement failure' >&2
    exit 42
fi
if [[ -n "${FAKE_DF_OUTPUT:-}" ]]; then
    printf '%s\n' "${FAKE_DF_OUTPUT}"
    exit 0
fi
printf '%s\n' 'Filesystem 1B-blocks Used Available Capacity Mounted on'
printf 'fakefs 100000000000 20000000000 %s %s%% %s\n' \
    "${FAKE_FREE_BYTES}" \
    "${FAKE_PERCENT_USED}" \
    "${DISK_WATCHDOG_PATH}"
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
        'DISK_WATCHDOG_HEARTBEAT_URL': heartbeat_url,
        'DISK_WATCHDOG_MIN_FREE_GB': str(min_free_gb),
        'DISK_WATCHDOG_MAX_PERCENT_USED': str(max_percent_used),
        'DISK_WATCHDOG_PATH': watchdog_path,
        'FAKE_FREE_BYTES': str(free_bytes),
        'FAKE_PERCENT_USED': str(percent_used),
        'FAKE_DF_RESULT': df_result,
        'FAKE_DF_OUTPUT': df_output,
        'FAKE_CURL_RESULT': curl_result,
        'DF_CALL_LOG': df_log.as_posix(),
        'CURL_CALL_LOG': curl_log.as_posix(),
        'PATH': f'{fake_bin}{os.pathsep}{os.environ.get("PATH", "")}',
    }
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
        'df_calls': calls(df_log),
        'curl_calls': calls(curl_log),
    }


def test_plenty_of_free_space_pings_once_and_exits_zero(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/disk-healthy'
    observation = _run_disk_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        min_free_gb=40,
        free_bytes=80_000_000_000,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert len(observation['df_calls']) == 1
    assert '-B1' in observation['df_calls'][0]
    assert '/data' in observation['df_calls'][0]
    assert 'actual free 80.00 GB' in observation['output']
    assert 'threshold 40 GB' in observation['output']


def test_below_threshold_skips_ping_logs_values_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        min_free_gb=40,
        free_bytes=30_000_000_000,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'actual free 30.00 GB' in observation['output']
    assert 'threshold 40 GB' in observation['output']
    assert 'ERROR:' in observation['output']


def test_exactly_at_threshold_is_healthy_and_pings(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/disk-boundary'
    observation = _run_disk_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        min_free_gb=40,
        free_bytes=40_000_000_000,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert 'actual free 40.00 GB' in observation['output']
    assert 'threshold 40 GB' in observation['output']


def test_one_byte_below_threshold_is_unhealthy_despite_rounded_log(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        min_free_gb=40,
        free_bytes=39_999_999_999,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'actual free 40.00 GB' in observation['output']
    assert 'threshold 40 GB' in observation['output']


def test_invalid_threshold_skips_df_and_ping_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(tmp_path, min_free_gb='0')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog cannot measure free space' in observation['output']


def test_df_failure_skips_ping_logs_loudly_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(tmp_path, df_result='fail')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog measurement failed' in observation['output']


def test_unparseable_df_output_skips_ping_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        df_output='Filesystem nonsense\nthis output has no byte count',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog measurement output is unparseable' in observation['output']


def test_unset_url_skips_df_and_ping_and_exits_zero(tmp_path: Path):
    observation = _run_disk_watchdog(tmp_path, heartbeat_url='')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'disk watchdog: skipped (heartbeat URL unconfigured)' in observation['output']


def test_ping_failure_does_not_change_healthy_disk_exit_code(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        free_bytes=80_000_000_000,
        curl_result='fail',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert len(observation['curl_calls']) == 1
    assert 'disk watchdog heartbeat: failed' in observation['output']


def test_high_percent_used_skips_ping_despite_plenty_of_free_gb(tmp_path: Path):
    """The GB-free floor alone can stay 'healthy' while the disk is
    uncomfortably full in percentage terms (e.g. 89% used on a 1.9TB disk
    still leaves >200GB free) - this is the gap that let production disk
    usage climb to 89% with the watchdog reporting healthy the whole time."""
    observation = _run_disk_watchdog(
        tmp_path,
        min_free_gb=40,
        free_bytes=200_000_000_000,
        max_percent_used=80,
        percent_used=89,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'usage 89% exceeds threshold 80%' in observation['output']
    assert 'ERROR:' in observation['output']


def test_exactly_at_percent_threshold_is_healthy_and_pings(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/disk-percent-boundary'
    observation = _run_disk_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        free_bytes=200_000_000_000,
        max_percent_used=80,
        percent_used=80,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]
    assert 'usage 80% (threshold 80%)' in observation['output']


def test_one_percent_above_threshold_is_unhealthy(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        free_bytes=200_000_000_000,
        max_percent_used=80,
        percent_used=81,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'usage 81% exceeds threshold 80%' in observation['output']


def test_both_checks_failing_reports_both_reasons(tmp_path: Path):
    observation = _run_disk_watchdog(
        tmp_path,
        min_free_gb=40,
        free_bytes=30_000_000_000,
        max_percent_used=80,
        percent_used=95,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['curl_calls'] == []
    assert 'actual free 30.00 GB is below threshold 40 GB' in observation['output']
    assert 'usage 95% exceeds threshold 80%' in observation['output']


def test_invalid_percent_threshold_skips_df_and_ping_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(tmp_path, max_percent_used='0')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog cannot measure usage' in observation['output']


def test_percent_threshold_over_100_skips_df_and_ping_and_exits_nonzero(tmp_path: Path):
    observation = _run_disk_watchdog(tmp_path, max_percent_used='101')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog cannot measure usage' in observation['output']


def test_zero_padded_percent_threshold_is_rejected_not_silently_widened(tmp_path: Path):
    """Bash's (( )) arithmetic context treats a leading-zero operand as
    octal. '0999' contains an invalid octal digit ('9'), which without an
    explicit base-10 conversion causes the range-check arithmetic itself to
    error out silently inside the `if` condition - the validation is then
    skipped entirely (not enforced), and downstream awk parses '0999' as
    plain decimal 999, disabling the percentage check for any real disk
    (max 100% used). Codex Review finding, 2026-08-09."""
    observation = _run_disk_watchdog(tmp_path, max_percent_used='0999')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0, (
        f'a zero-padded out-of-range value must still be rejected: {observation["output"]}'
    )
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog cannot measure usage' in observation['output']


def test_overflowing_percent_threshold_is_rejected_not_wrapped(tmp_path: Path):
    """A digit-only value outside Bash's 64-bit signed arithmetic range
    wraps instead of erroring inside `(( ))` - e.g. 18446744073709551716
    (2^64 + 100) wraps to 100, which then passes the 1-100 range check and
    is accepted as a valid, permissive threshold rather than rejected as
    the malformed input it is. Codex Review finding, 2026-08-09."""
    observation = _run_disk_watchdog(
        tmp_path, max_percent_used='18446744073709551716'
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0, (
        f'an overflowing value must still be rejected: {observation["output"]}'
    )
    assert observation['df_calls'] == []
    assert observation['curl_calls'] == []
    assert 'ERROR: disk watchdog cannot measure usage' in observation['output']


def test_zero_padded_valid_percent_threshold_is_still_accepted(tmp_path: Path):
    """The base-10 fix must not reject legitimately zero-padded in-range
    values (e.g. '080' meaning 80) - only widen validation, not narrow it."""
    heartbeat_url = 'https://heartbeat.invalid/disk-zero-padded'
    observation = _run_disk_watchdog(
        tmp_path,
        heartbeat_url=heartbeat_url,
        max_percent_used='080',
        percent_used=50,
        free_bytes=200_000_000_000,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, observation['output']
    assert observation['curl_calls'] == [heartbeat_url]


def test_disk_watchdog_is_wired_into_maintenance_runtime():
    script = _read('apps', 'maintenance', 'scripts', 'run_disk_watchdog.sh')
    compose = _read('docker-compose.yml')
    env_example = _read('env.example')
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    dockerfile = _read('apps', 'maintenance', 'Dockerfile')

    assert 'df -B1' in script
    assert 'DISK_WATCHDOG_HEARTBEAT_URL: ${DISK_WATCHDOG_HEARTBEAT_URL:-}' in compose
    assert 'DISK_WATCHDOG_MIN_FREE_GB: ${DISK_WATCHDOG_MIN_FREE_GB:-40}' in compose
    assert 'DISK_WATCHDOG_MAX_PERCENT_USED: ${DISK_WATCHDOG_MAX_PERCENT_USED:-80}' in compose
    assert 'DISK_WATCHDOG_PATH: ${DISK_WATCHDOG_PATH:-/data}' in compose
    assert 'DISK_WATCHDOG_HEARTBEAT_URL=' in env_example.splitlines()
    assert 'DISK_WATCHDOG_MIN_FREE_GB=40' in env_example.splitlines()
    assert 'DISK_WATCHDOG_MAX_PERCENT_USED=80' in env_example.splitlines()
    assert 'DISK_WATCHDOG_PATH=/data' in env_example.splitlines()
    assert "inverted dead-man's switch" in env_example
    assert '61GB' in env_example
    assert '40GB' in env_example
    assert '*/30 * * * * /usr/local/bin/run_disk_watchdog.sh' in crontab
    assert (
        'COPY apps/maintenance/scripts/run_disk_watchdog.sh '
        '/usr/local/bin/run_disk_watchdog.sh'
    ) in ' '.join(dockerfile.split())
    assert '/usr/local/bin/run_disk_watchdog.sh' in dockerfile
