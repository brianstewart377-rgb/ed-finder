import json
import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return ' '.join(text.split())


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding='utf-8', newline='\n')
    path.chmod(0o755)


def _run_backup_scenario(
    tmp_path: Path,
    *,
    offsite: bool = False,
    rclone_result: str = 'success',
    rclone_sleep_seconds: int = 0,
    pg_dump_result: str = 'success',
    existing_latest: bool = False,
) -> dict[str, object]:
    bash = shutil.which('bash')
    assert bash is not None, 'bash is required for the backup-script behavior tests'

    backup_dir = tmp_path / 'backups'
    fake_bin = tmp_path / 'bin'
    backup_dir.mkdir()
    fake_bin.mkdir()

    old_base = backup_dir / 'edfinder_20000101T000000Z.dump'
    old_files = [
        old_base,
        Path(f'{old_base}.sha256'),
        Path(f'{old_base}.json'),
    ]
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    for path in old_files:
        path.write_text('expired', encoding='utf-8')
        os.utime(path, (old_timestamp, old_timestamp))

    previous_archive = None
    previous_metadata = None
    if existing_latest:
        previous_archive = backup_dir / 'edfinder_20010101T000000Z.dump'
        previous_metadata = Path(f'{previous_archive}.json')
        previous_archive.write_text('previous valid archive', encoding='utf-8')
        previous_metadata.write_text('{"previous": true}\n', encoding='utf-8')
        (backup_dir / 'latest.dump').symlink_to(previous_archive.name)
        (backup_dir / 'latest.json').symlink_to(previous_metadata.name)

    baseline_metadata_files = set(backup_dir.glob('edfinder_*.dump.json'))

    _write_executable(fake_bin / 'pg_dump', '''#!/bin/bash
set -eu
output=''
for argument in "$@"; do
    case "$argument" in
        --file=*) output="${argument#--file=}" ;;
    esac
done
test -n "$output"
: > "$output"
if [[ "${FAKE_PG_DUMP_RESULT:-success}" == 'fail' ]]; then
    echo 'fake pg_dump failure' >&2
    exit 41
fi
printf 'valid fake archive\n' > "$output"
''')
    _write_executable(fake_bin / 'pg_restore', '''#!/bin/bash
exit 0
''')
    _write_executable(fake_bin / 'rclone', '''#!/bin/bash
set -eu
if [[ -e "${RCLONE_OBSERVED_OLD_FILE}" ]]; then
    echo 'old-present' >> "${RCLONE_ORDER_LOG}"
else
    echo 'old-absent' >> "${RCLONE_ORDER_LOG}"
fi
printf '%s\n' "$*" >> "${RCLONE_CALL_LOG}"
if [[ "$2" == *.dump ]]; then
    cp "${2}.json" "${RCLONE_PRE_UPLOAD_METADATA}"
    sleep "${FAKE_RCLONE_SLEEP_SECONDS:-0}"
fi
if [[ "${FAKE_RCLONE_RESULT:-success}" == 'fail' ]]; then
    echo 'fake rclone failure' >&2
    exit 23
fi
if [[ "${FAKE_RCLONE_RESULT:-success}" == 'metadata-fail' && "$2" == *.dump.json ]]; then
    echo 'fake rclone metadata failure' >&2
    exit 24
fi
''')

    log_file = tmp_path / 'backup.log'
    order_log = tmp_path / 'rclone-order.log'
    call_log = tmp_path / 'rclone-calls.log'
    pre_upload_metadata = tmp_path / 'pre-upload-metadata.json'
    env = {
        **os.environ,
        'DATABASE_URL': 'postgresql://unused/backup-test',
        'BACKUP_DIR': str(backup_dir),
        'BACKUP_LOG_FILE': str(log_file),
        'BACKUP_RETENTION_DAYS': '0',
        'BACKUP_OFFSITE_REMOTE': 'fake:backups' if offsite else '',
        'FAKE_PG_DUMP_RESULT': pg_dump_result,
        'FAKE_RCLONE_RESULT': rclone_result,
        'FAKE_RCLONE_SLEEP_SECONDS': str(rclone_sleep_seconds),
        'RCLONE_OBSERVED_OLD_FILE': str(old_base),
        'RCLONE_ORDER_LOG': str(order_log),
        'RCLONE_CALL_LOG': str(call_log),
        'RCLONE_PRE_UPLOAD_METADATA': str(pre_upload_metadata),
        'PATH': f'{fake_bin}{os.pathsep}{os.environ.get("PATH", "")}',
    }
    completed = subprocess.run(
        [bash, str(ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_backup.sh'), 'manual'],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    # The script's process-substitution logger can finish a few milliseconds
    # after the parent shell exits. Give it a bounded window to flush.
    deadline = time.monotonic() + 1
    while not log_file.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    metadata_files = list(backup_dir.glob('edfinder_*.dump.json'))
    current_metadata = [path for path in metadata_files if path not in baseline_metadata_files]
    metadata = (
        json.loads(current_metadata[0].read_text(encoding='utf-8'))
        if len(current_metadata) == 1
        else None
    )
    return {
        'completed': completed,
        'backup_dir': backup_dir,
        'old_files': old_files,
        'previous_archive': previous_archive,
        'previous_metadata': previous_metadata,
        'metadata': metadata,
        'metadata_files_created': current_metadata,
        'pre_upload_metadata': (
            json.loads(pre_upload_metadata.read_text(encoding='utf-8'))
            if pre_upload_metadata.exists()
            else None
        ),
        'log': log_file.read_text(encoding='utf-8') if log_file.exists() else '',
        'order': order_log.read_text(encoding='utf-8').splitlines() if order_log.exists() else [],
        'calls': call_log.read_text(encoding='utf-8').splitlines() if call_log.exists() else [],
    }


def test_backup_automation_is_wired_through_maintenance_sidecar():
    compose = _read('docker-compose.yml')
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    dockerfile = _read('apps', 'maintenance', 'Dockerfile')

    assert 'context: .' in compose
    assert 'dockerfile: apps/maintenance/Dockerfile' in compose
    assert 'BACKUP_DIR:    /data/backups/postgres' in compose
    assert 'BACKUP_OFFSITE_REMOTE: ${BACKUP_OFFSITE_REMOTE:-}' in compose
    assert '- /data/backups:/data/backups' in compose
    assert '- /data/receipts:/data/receipts' in compose
    assert '/usr/local/bin/run_backup.sh nightly' in crontab
    assert '/usr/local/bin/run_data_invariants_receipted.sh --target-rating-version 3.4' in crontab
    assert '--production-safe --allow-stale-colonisation-status' in crontab
    assert 'apk add --no-cache dcron tini bash python3 py3-psycopg2 rclone' in dockerfile
    assert 'COPY apps/maintenance/scripts/run_backup.sh                /usr/local/bin/run_backup.sh' in dockerfile
    assert 'COPY scripts/run_data_invariants_receipted.sh              /usr/local/bin/run_data_invariants_receipted.sh' in dockerfile
    assert 'COPY scripts/checks/data_invariants.py                     /opt/ed-finder/scripts/checks/data_invariants.py' in dockerfile
    assert 'COPY shared_contracts/data_invariant_contracts.py          /opt/ed-finder/shared_contracts/data_invariant_contracts.py' in dockerfile


def test_restore_helper_defaults_to_safe_non_live_target():
    restore = _read('scripts', 'restore_postgres_backup.sh')

    assert 'TARGET_DB="${TARGET_DB:-edfinder_restore}"' in restore
    assert "refusing to restore over live database 'edfinder' without --allow-live-db" in restore
    assert 'COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"' in restore
    assert '--compose-file' in restore
    assert 'dc() {' in restore
    assert 'pg_restore' in restore


def test_restore_rehearsal_helper_wraps_backup_restore_and_readiness_checks():
    rehearsal = _read('scripts', 'rehearse_postgres_restore.sh')

    assert 'TARGET_DB="${TARGET_DB:-edfinder_restore_rehearsal}"' in rehearsal
    assert 'SOURCE_DB="${SOURCE_DB:-edfinder}"' in rehearsal
    assert 'BACKUP_MODE="${EDFINDER_RESTORE_BACKUP_MODE:-auto}"' in rehearsal
    assert 'compose_has_service()' in rehearsal
    assert 'run_postgres_direct_backup()' in rehearsal
    assert '--source-db' in rehearsal
    assert 'dc exec -T postgres pg_dump -U edfinder -d "$SOURCE_DB" \\' in rehearsal
    assert 'dc exec maintenance /usr/local/bin/run_backup.sh manual' in rehearsal
    assert 'restore_args=(' in rehearsal
    assert 'bash scripts/restore_postgres_backup.sh "${restore_args[@]}"' in rehearsal
    assert 'SELECT COUNT(*) FROM schema_migrations;' in rehearsal
    assert 'dropdb -U edfinder --if-exists "$TARGET_DB"' in rehearsal
    assert '--receipt-file' in rehearsal


def test_backup_script_can_optionally_mirror_archives_offsite():
    backup = _read('apps', 'maintenance', 'scripts', 'run_backup.sh')

    assert 'BACKUP_OFFSITE_REMOTE="${BACKUP_OFFSITE_REMOTE:-}"' in backup
    assert 'command -v rclone >/dev/null 2>&1' in backup
    assert 'rclone copyto "$ARCHIVE"' in backup
    assert 'rclone copyto "$SHA_FILE"' in backup
    assert 'rclone copyto "$META_FILE"' in backup
    assert '"offsite_sync_status": "$OFFSITE_SYNC_STATUS"' in backup
    assert 'latest.json' in backup


def test_backup_with_offsite_disabled_creates_metadata_and_prunes(tmp_path: Path):
    observation = _run_backup_scenario(tmp_path)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['metadata']['offsite_sync_status'] == 'disabled'
    assert observation['metadata']['offsite_synced_at_utc'] is None
    assert all(not path.exists() for path in observation['old_files'])
    assert len(list(observation['backup_dir'].glob('edfinder_*.dump'))) == 1


def test_successful_offsite_sync_runs_after_prune_and_records_synced(tmp_path: Path):
    observation = _run_backup_scenario(tmp_path, offsite=True)
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['metadata']['offsite_sync_status'] == 'synced'
    assert observation['metadata']['offsite_synced_at_utc'] is not None
    assert all(not path.exists() for path in observation['old_files'])
    assert observation['order'] == ['old-absent'] * 4
    assert len(observation['calls']) == 4


def test_offsite_metadata_rewrite_preserves_archive_creation_time(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_sleep_seconds=2,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['pre_upload_metadata'] is not None
    assert (
        observation['pre_upload_metadata']['created_at_utc']
        == observation['metadata']['created_at_utc']
    )


def test_failed_offsite_sync_still_prunes_and_records_loud_failure(tmp_path: Path):
    observation = _run_backup_scenario(tmp_path, offsite=True, rclone_result='fail')
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert all(not path.exists() for path in observation['old_files'])
    assert observation['metadata']['offsite_sync_status'] == 'failed'
    assert observation['metadata']['offsite_synced_at_utc'] is None
    assert 'ERROR: offsite backup sync failed' in observation['log']


def test_metadata_upload_failure_records_archive_as_synced_and_exits_nonzero(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_result='metadata-fail',
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert all(not path.exists() for path in observation['old_files'])
    assert observation['metadata']['offsite_sync_status'] == 'synced_metadata_failed'
    assert observation['metadata']['offsite_synced_at_utc'] is not None
    assert 'ERROR: offsite backup metadata sync failed' in observation['log']
    assert len(observation['calls']) == 3
    assert '.dump ' in observation['calls'][0]
    assert '.dump.sha256 ' in observation['calls'][1]
    assert '.dump.json ' in observation['calls'][2]


def test_failed_pg_dump_still_prunes_without_replacing_latest(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        pg_dump_result='fail',
        existing_latest=True,
    )
    completed = observation['completed']
    latest_dump = observation['backup_dir'] / 'latest.dump'
    latest_metadata = observation['backup_dir'] / 'latest.json'

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert all(not path.exists() for path in observation['old_files'])
    assert list(observation['backup_dir'].glob('*.dump.tmp')) == []
    assert observation['metadata_files_created'] == []
    assert latest_dump.readlink() == Path(observation['previous_archive'].name)
    assert latest_metadata.readlink() == Path(observation['previous_metadata'].name)
    assert observation['previous_archive'].exists()
    assert observation['previous_metadata'].exists()


def test_backup_runbook_and_remediation_docs_reflect_current_state():
    runbook = _read('docs', 'operations', 'postgres-backup-and-restore.md')
    remediation = _read('docs', 'operations', 'audit-remediation-plan.md')
    roadmap = _read('docs', 'ROADMAP.md')

    assert 'daily at `02:10 UTC`' in runbook
    assert 'scripts/restore_postgres_backup.sh' in runbook
    assert 'scripts/rehearse_postgres_restore.sh' in runbook
    assert 'optional offsite mirror via `rclone`' in runbook
    assert 'BACKUP_OFFSITE_REMOTE' in runbook
    assert 'storagebox:ed-finder/backups/postgres' in runbook
    assert '--compose-file' in runbook
    assert 'docker-compose.local.yml' in runbook
    assert 'falls back to a direct `pg_dump` via the `postgres` service' in _squash(runbook)
    assert 'schema-migration count' in runbook
    assert '- [x] Add scheduled Postgres backups through the maintained ops path.' in remediation
    assert '- [x] Execute and record at least one real restore rehearsal.' in remediation
    assert '- `scripts/rehearse_postgres_restore.sh`' in remediation

    squashed = _squash(roadmap)
    assert 'Backup/restore automation and a recorded disposable restore rehearsal now establish the minimum restore-readiness baseline.' in squashed
    assert 'artifacts/restore-rehearsals/local-restore-receipt-2026-07-09.json' in roadmap


def test_data_invariants_ops_path_is_wired_for_post_deploy_and_weekly_maintenance_schedule():
    compose = _read('docker-compose.yml')
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    deploy = _read('scripts', 'deploy_main.sh')
    wrapper = _read('scripts', 'run_data_invariants_receipted.sh')
    runbook = _read('docs', 'operations', 'stage17n2c-data-trust-runbook.md')

    assert 'DATA_INVARIANTS_DATABASE_URL: ${DATABASE_READONLY_URL:-${DATABASE_APP_URL:-postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder}}' in compose
    assert '/usr/local/bin/run_data_invariants_receipted.sh --target-rating-version 3.4' in crontab
    assert '--skip-invariants' in deploy
    assert 'bash scripts/run_data_invariants_receipted.sh \\' in deploy
    assert '/tmp/ed-finder-data-invariants-post-deploy.json' in deploy
    assert '--durable-receipt-dir /data/receipts/data-invariants/post-deploy' in deploy
    assert '--allow-stale-colonisation-status' in deploy
    assert 'TARGET_RATING_VERSION="${TARGET_RATING_VERSION:-3.4}"' in wrapper
    assert 'DURABLE_RECEIPT_DIR="${DURABLE_RECEIPT_DIR:-}"' in wrapper
    assert 'DATABASE_URL_OVERRIDE="${DATA_INVARIANTS_DATABASE_URL:-}"' in wrapper
    assert '--database-url) DATABASE_URL_OVERRIDE="$2"; shift 2 ;;' in wrapper
    assert '--durable-receipt-dir) DURABLE_RECEIPT_DIR="$2"; shift 2 ;;' in wrapper
    assert '--production-safe' in wrapper
    assert '--allow-stale-colonisation-status) ALLOW_STALE_COLONISATION_STATUS=1; shift ;;' in wrapper
    assert '"status": "$status"' in wrapper
    assert '"allow_stale_colonisation_status":' in wrapper
    assert 'data-invariants-${durable_stamp}.json' in wrapper
    assert 'latest.json' in wrapper
    assert '45 4 * * 0 /usr/local/bin/run_data_invariants_receipted.sh' in runbook
    assert '/data/receipts/data-invariants/weekly-latest.json' in runbook
    assert 'DATA_INVARIANTS_DATABASE_URL' in runbook
    assert 'scripts/deploy_main.sh` now runs the wrapper by default' in runbook
