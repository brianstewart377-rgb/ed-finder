from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SYNC_PASSWORD = ROOT / 'scripts' / 'sync_password.sh'
RUN_IMPORT = ROOT / 'scripts' / 'run_import.sh'
APPLY_MIGRATIONS = ROOT / 'scripts' / 'apply_migrations.sh'
BASELINE_MIGRATIONS = ROOT / 'scripts' / 'baseline_migration_ledger.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _find_bash() -> str | None:
    candidates = [shutil.which('bash')]
    if os.name == 'nt':
        for env_name in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA'):
            root = os.environ.get(env_name)
            if not root:
                continue
            candidates.extend(
                (
                    str(Path(root) / 'Git' / 'bin' / 'bash.exe'),
                    str(Path(root) / 'Git' / 'usr' / 'bin' / 'bash.exe'),
                    str(Path(root) / 'Programs' / 'Git' / 'bin' / 'bash.exe'),
                )
            )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            probe = subprocess.run(
                [candidate, '--version'], capture_output=True, text=True, check=False
            )
            if probe.returncode == 0:
                return candidate
    return None


def _bash_path(path: Path) -> str:
    value = str(path.resolve()).replace('\\', '/')
    if os.name == 'nt' and len(value) >= 3 and value[1:3] == ':/':
        return f'/{value[0].lower()}/{value[3:]}'
    return value


def test_password_sync_uses_non_argv_secret_channels_and_one_canonical_path():
    sync_source = _read(SYNC_PASSWORD)
    import_source = _read(RUN_IMPORT)

    for source in (sync_source, import_source):
        assert 'postgresql://edfinder:${POSTGRES_PASSWORD}' not in source
        assert "PASSWORD '${POSTGRES_PASSWORD}'" not in source
        assert '${POSTGRES_PASSWORD:0:3}' not in source

    assert 'Password  : [redacted]' in sync_source
    assert 'ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env}"' in sync_source
    assert 'POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ed-postgres}"' in sync_source
    assert 'PGBOUNCER_CONTAINER="${PGBOUNCER_CONTAINER:-ed-pgbouncer}"' in sync_source
    assert 'PGPASSFILE="$passfile" psql -X -w' in sync_source
    assert 'set -- $(hostname -i)' in sync_source
    assert '-h "$database_host"' in sync_source
    assert "-c '\\password edfinder'" in sync_source
    assert "sed -e 's/\\\\/\\\\\\\\/g' -e 's/:/\\\\:/g'" in sync_source
    assert 'bash "$INSTALL_DIR/scripts/sync_password.sh" --verify-only' in import_source
    assert 'bash "$INSTALL_DIR/scripts/sync_password.sh"' in import_source


def test_password_sync_update_and_verification_do_not_log_or_argv_expose_secret(tmp_path: Path):
    bash = _find_bash()
    if bash is None:
        pytest.skip('a working Bash is required for the operator-script rehearsal')

    secret = "prefix:quo'te\\slash $value with spaces"
    env_file = tmp_path / 'operator.env'
    env_file.write_text(
        'POSTGRES_PASSWORD="prefix:quo\'te\\\\slash \\$value with spaces"\n',
        encoding='utf-8',
    )
    mock_bin = tmp_path / 'bin'
    mock_bin.mkdir()
    args_log = tmp_path / 'docker-args.log'
    stdin_log = tmp_path / 'docker-stdin.log'
    count_file = tmp_path / 'connection-count'
    docker_mock = mock_bin / 'docker'
    docker_mock.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$MOCK_DOCKER_ARGS"
if [[ "${1:-}" == "inspect" && "${2:-}" == "ed-postgres" ]]; then
  exit 0
fi
if [[ "${1:-}" == "inspect" && "${2:-}" == "ed-pgbouncer" ]]; then
  exit 1
fi
if [[ "${1:-}" == "exec" ]]; then
  cat >> "$MOCK_DOCKER_STDIN"
  printf '\n--CALL--\n' >> "$MOCK_DOCKER_STDIN"
  if [[ "$*" == *"\\password edfinder"* ]]; then
    exit 0
  fi
  count=0
  [[ -f "$MOCK_DOCKER_COUNT" ]] && count="$(cat "$MOCK_DOCKER_COUNT")"
  count=$((count + 1))
  printf '%s' "$count" > "$MOCK_DOCKER_COUNT"
  [[ "$count" -gt 1 ]]
fi
""",
        encoding='utf-8',
    )
    docker_mock.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            'ENV_FILE': _bash_path(env_file),
            'MOCK_DOCKER_ARGS': _bash_path(args_log),
            'MOCK_DOCKER_STDIN': _bash_path(stdin_log),
            'MOCK_DOCKER_COUNT': _bash_path(count_file),
            'PATH': f'{mock_bin}{os.pathsep}{env.get("PATH", "")}',
        }
    )
    result = subprocess.run(
        [bash, _bash_path(SYNC_PASSWORD)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    combined_output = result.stdout + result.stderr
    assert secret not in combined_output
    assert secret not in args_log.read_text(encoding='utf-8')
    assert '[redacted]' in combined_output
    stdin_text = stdin_log.read_text(encoding='utf-8')
    assert f'{secret}\n{secret}' in stdin_text
    assert r"prefix\:quo'te\\slash $value with spaces" in stdin_text


@pytest.mark.parametrize('script', (APPLY_MIGRATIONS, BASELINE_MIGRATIONS))
def test_migration_scripts_default_to_finite_validated_timeouts(script: Path):
    source = _read(script)

    assert 'MIGRATION_STATEMENT_TIMEOUT="${MIGRATION_STATEMENT_TIMEOUT:-1h}"' in source
    assert 'MIGRATION_LOCK_TIMEOUT="${MIGRATION_LOCK_TIMEOUT:-30s}"' in source
    assert 'EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS' in source
    assert 'zero migration timeouts require EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS=yes' in source
    assert 'statement_timeout=${MIGRATION_STATEMENT_TIMEOUT}' in source
    assert 'lock_timeout=${MIGRATION_LOCK_TIMEOUT}' in source
    assert 'statement_timeout=0 -c lock_timeout=0' not in source


@pytest.mark.parametrize(
    ('name', 'value', 'expected'),
    (
        (
            'MIGRATION_STATEMENT_TIMEOUT',
            '0',
            'zero migration timeouts require EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS=yes',
        ),
        (
            'MIGRATION_LOCK_TIMEOUT',
            "30s'; echo unsafe",
            'MIGRATION_LOCK_TIMEOUT must be a non-negative PostgreSQL duration',
        ),
    ),
)
def test_migration_timeout_policy_rejects_unsafe_values_before_database_access(
    name: str, value: str, expected: str
):
    bash = _find_bash()
    if bash is None:
        pytest.skip('a working Bash is required for the timeout-policy rehearsal')

    env = os.environ.copy()
    env.update(
        {
            'DATABASE_URL': 'postgresql://invalid.invalid/never-contact',
            name: value,
        }
    )
    result = subprocess.run(
        [bash, _bash_path(APPLY_MIGRATIONS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert expected in (result.stderr + result.stdout)
    assert 'could not translate host name' not in (result.stderr + result.stdout)
