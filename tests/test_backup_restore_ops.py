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
    rclone_prune_result: str = 'success',
    rclone_sleep_seconds: int = 0,
    pg_dump_result: str = 'success',
    existing_latest: bool = False,
    old_archive_count: int = 1,
    retention_min_archives: int | None = 1,
    remote_archive_count: int = 0,
    offsite_retention_days: int | None = 30,
    offsite_retention_min_archives: int | None = 3,
    fresh_sidecars_for_oldest: bool = False,
    local_heartbeat_url: str = '',
    offsite_heartbeat_url: str = '',
    curl_result: str = 'success',
) -> dict[str, object]:
    bash = shutil.which('bash')
    assert bash is not None, 'bash is required for the backup-script behavior tests'

    backup_dir = tmp_path / 'backups'
    remote_dir = tmp_path / 'remote'
    fake_bin = tmp_path / 'bin'
    backup_dir.mkdir()
    remote_dir.mkdir()
    fake_bin.mkdir()

    old_archive_groups = []
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    for index in range(old_archive_count):
        old_base = backup_dir / f'edfinder_200001{index + 1:02d}T000000Z.dump'
        old_group = [
            old_base,
            Path(f'{old_base}.sha256'),
            Path(f'{old_base}.json'),
        ]
        for path in old_group:
            path.write_text('expired', encoding='utf-8')
            os.utime(path, (old_timestamp + index, old_timestamp + index))
        old_archive_groups.append(old_group)

    if fresh_sidecars_for_oldest:
        for path in old_archive_groups[0][1:]:
            os.utime(path, None)

    old_archives = [group[0] for group in old_archive_groups]
    old_files = [path for group in old_archive_groups for path in group]
    old_base = old_archives[0]

    remote_archive_groups = []
    for index in range(remote_archive_count):
        remote_base = remote_dir / f'edfinder_200002{index + 1:02d}T000000Z.dump'
        remote_group = [
            remote_base,
            Path(f'{remote_base}.sha256'),
            Path(f'{remote_base}.json'),
        ]
        for path in remote_group:
            path.write_text('remote expired', encoding='utf-8')
        remote_archive_groups.append(remote_group)
    (remote_dir / 'latest.json').write_text('remote latest sentinel', encoding='utf-8')

    previous_archive = None
    previous_metadata = None
    if existing_latest:
        previous_archive = backup_dir / 'edfinder_20010101T000000Z.dump'
        previous_metadata = Path(f'{previous_archive}.json')
        previous_checksum = Path(f'{previous_archive}.sha256')
        previous_archive.write_text('previous valid archive', encoding='utf-8')
        previous_checksum.write_text('previous checksum', encoding='utf-8')
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
command="$1"
shift
case "$command" in
    copyto)
        source="$1"
        destination="$2"
        if [[ "$source" == *.dump ]]; then
            cp "${source}.json" "${RCLONE_PRE_UPLOAD_METADATA}"
            sleep "${FAKE_RCLONE_SLEEP_SECONDS:-0}"
        fi
        if [[ "${FAKE_RCLONE_RESULT:-success}" == 'fail' ]]; then
            echo 'fake rclone failure' >&2
            exit 23
        fi
        if [[ "${FAKE_RCLONE_RESULT:-success}" == 'metadata-fail' && "$source" == *.dump.json ]]; then
            echo 'fake rclone metadata failure' >&2
            exit 24
        fi
        cp "$source" "${RCLONE_REMOTE_DIR}/${destination##*/}"
        ;;
    lsf)
        find "${RCLONE_REMOTE_DIR}" -maxdepth 1 -type f -printf '%f\n' | sort
        ;;
    deletefile)
        if [[ "${FAKE_RCLONE_PRUNE_RESULT:-success}" == 'fail' ]]; then
            echo 'fake rclone prune failure' >&2
            exit 25
        fi
        remote_name="${1##*/}"
        test -f "${RCLONE_REMOTE_DIR}/${remote_name}"
        rm -f -- "${RCLONE_REMOTE_DIR}/${remote_name}"
        ;;
    *)
        echo "unexpected fake rclone command: $command" >&2
        exit 26
        ;;
esac
''')
    _write_executable(fake_bin / 'curl', '''#!/bin/bash
set -eu
printf '%s\n' "${!#}" >> "${CURL_CALL_LOG}"
if [[ "${FAKE_CURL_RESULT:-success}" == 'fail' ]]; then
    echo 'fake curl failure' >&2
    exit 28
fi
''')

    log_file = tmp_path / 'backup.log'
    order_log = tmp_path / 'rclone-order.log'
    call_log = tmp_path / 'rclone-calls.log'
    curl_call_log = tmp_path / 'curl-calls.log'
    pre_upload_metadata = tmp_path / 'pre-upload-metadata.json'
    env = {
        **os.environ,
        'DATABASE_URL': 'postgresql://unused/backup-test',
        'BACKUP_DIR': backup_dir.as_posix(),
        'BACKUP_LOG_FILE': log_file.as_posix(),
        'BACKUP_RETENTION_DAYS': '0',
        'BACKUP_OFFSITE_REMOTE': 'fake:backups' if offsite else '',
        'BACKUP_HEARTBEAT_URL': local_heartbeat_url,
        'BACKUP_OFFSITE_HEARTBEAT_URL': offsite_heartbeat_url,
        'FAKE_PG_DUMP_RESULT': pg_dump_result,
        'FAKE_RCLONE_RESULT': rclone_result,
        'FAKE_RCLONE_PRUNE_RESULT': rclone_prune_result,
        'FAKE_RCLONE_SLEEP_SECONDS': str(rclone_sleep_seconds),
        'FAKE_CURL_RESULT': curl_result,
        'CURL_CALL_LOG': curl_call_log.as_posix(),
        'RCLONE_OBSERVED_OLD_FILE': old_base.as_posix(),
        'RCLONE_ORDER_LOG': order_log.as_posix(),
        'RCLONE_CALL_LOG': call_log.as_posix(),
        'RCLONE_PRE_UPLOAD_METADATA': pre_upload_metadata.as_posix(),
        'RCLONE_REMOTE_DIR': remote_dir.as_posix(),
        'PATH': f'{fake_bin}{os.pathsep}{os.environ.get("PATH", "")}',
    }
    if retention_min_archives is not None:
        env['BACKUP_RETENTION_MIN_ARCHIVES'] = str(retention_min_archives)
    if offsite_retention_days is not None:
        env['BACKUP_OFFSITE_RETENTION_DAYS'] = str(offsite_retention_days)
    if offsite_retention_min_archives is not None:
        env['BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES'] = str(
            offsite_retention_min_archives
        )
    completed = subprocess.run(
        [bash, str(ROOT / 'apps' / 'maintenance' / 'scripts' / 'run_backup.sh'), 'manual'],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

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
    rclone_calls = call_log.read_text(encoding='utf-8').splitlines() if call_log.exists() else []
    return {
        'completed': completed,
        'backup_dir': backup_dir,
        'old_archives': old_archives,
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
        'calls': rclone_calls,
        'remote_archive_groups': remote_archive_groups,
        'remote_files': sorted(path.name for path in remote_dir.iterdir()),
        'remote_delete_calls': [
            call for call in rclone_calls if call.startswith('deletefile ')
        ],
        'heartbeat_calls': (
            curl_call_log.read_text(encoding='utf-8').splitlines()
            if curl_call_log.exists()
            else []
        ),
    }


def _assert_archive_sidecars_consistent(backup_dir: Path) -> None:
    archives = list(backup_dir.glob('edfinder_*.dump'))
    checksums = list(backup_dir.glob('edfinder_*.dump.sha256'))
    metadata_files = list(backup_dir.glob('edfinder_*.dump.json'))

    for archive in archives:
        assert Path(f'{archive}.sha256').exists()
        assert Path(f'{archive}.json').exists()
    for checksum in checksums:
        assert Path(str(checksum).removesuffix('.sha256')).exists()
    for metadata_file in metadata_files:
        assert Path(str(metadata_file).removesuffix('.json')).exists()


def test_backup_helpers_remain_in_legacy_maintenance_compose_without_v2_storagebox_authority():
    compose = _read('docker-compose.yml')
    env_example = _read('env.example')
    env_example_lines = env_example.splitlines()
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    dockerfile = _read('apps', 'maintenance', 'Dockerfile')

    assert 'LEGACY SELF-HOST / LOCAL-CI COMPOSE — NEVER V3 PRODUCTION OR BACKUP AUTHORITY' in compose
    assert 'PostgreSQL 16 services' in compose
    assert 'current V3 production uses PostgreSQL 18' in compose
    assert 'context: .' in compose
    assert 'dockerfile: apps/maintenance/Dockerfile' in compose
    assert 'BACKUP_DIR:    /data/backups/postgres' in compose
    assert 'BACKUP_RETENTION_MIN_ARCHIVES: ${BACKUP_RETENTION_MIN_ARCHIVES:-3}' in compose
    assert 'BACKUP_OFFSITE_REMOTE: ${BACKUP_OFFSITE_REMOTE:-}' in compose
    assert 'BACKUP_OFFSITE_RETENTION_DAYS: ${BACKUP_OFFSITE_RETENTION_DAYS:-30}' in compose
    assert (
        'BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES: '
        '${BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES:-3}'
    ) in compose
    assert 'RCLONE_CONFIG_STORAGEBOX_' not in compose
    assert 'RCLONE_CONFIG_STORAGEBOX_' not in env_example
    assert 'storagebox:ed-finder/backups/postgres' not in env_example
    assert 'V3 backup/PITR storage is not to' in env_example
    assert 'be inferred from V2 history' in env_example
    assert 'BACKUP_RETENTION_MIN_ARCHIVES=3' in env_example_lines
    assert 'BACKUP_OFFSITE_RETENTION_DAYS=30' in env_example_lines
    assert 'BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES=3' in env_example_lines
    assert 'BACKUP_HEARTBEAT_URL: ${BACKUP_HEARTBEAT_URL:-}' in compose
    assert 'BACKUP_OFFSITE_HEARTBEAT_URL: ${BACKUP_OFFSITE_HEARTBEAT_URL:-}' in compose
    assert 'BACKUP_HEARTBEAT_URL=' in env_example
    assert 'BACKUP_OFFSITE_HEARTBEAT_URL=' in env_example
    assert "dead-man's-switch heartbeat URLs" in env_example
    assert '- /data/backups:/data/backups' in compose
    assert '- /data/receipts:/data/receipts' in compose
    assert '/usr/local/bin/run_backup.sh nightly' in crontab
    assert '/usr/local/bin/run_data_invariants_receipted.sh --target-rating-version 3.4' in crontab
    assert '--production-safe --allow-stale-colonisation-status' in crontab
    assert 'apk add --no-cache dcron tini bash python3 py3-psycopg2 rclone curl' in dockerfile
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
    assert 'LOCAL/CI ONLY — NEVER V3 PRODUCTION' in restore
    assert 'PostgreSQL 16' in restore
    assert 'PostgreSQL 18' in restore
    assert 'not V3 PostgreSQL 18 backup, restore' in restore


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
    assert 'LOCAL/CI ONLY — NEVER V3 PRODUCTION' in rehearsal
    assert 'retained legacy' in rehearsal
    assert 'Compose PostgreSQL 16 tooling only' in rehearsal
    assert 'says nothing about V3' in rehearsal


def test_backup_script_can_optionally_mirror_archives_offsite():
    backup = _read('apps', 'maintenance', 'scripts', 'run_backup.sh')

    assert 'BACKUP_OFFSITE_REMOTE="${BACKUP_OFFSITE_REMOTE:-}"' in backup
    assert 'BACKUP_HEARTBEAT_URL="${BACKUP_HEARTBEAT_URL:-}"' in backup
    assert 'BACKUP_OFFSITE_HEARTBEAT_URL="${BACKUP_OFFSITE_HEARTBEAT_URL:-}"' in backup
    assert 'BACKUP_RETENTION_MIN_ARCHIVES:-3' in backup
    assert 'BACKUP_OFFSITE_RETENTION_DAYS:-30' in backup
    assert 'BACKUP_OFFSITE_RETENTION_MIN_ARCHIVES:-3' in backup
    assert 'curl -fsS -m 10 --retry 3 "$url"' in backup
    assert 'command -v rclone >/dev/null 2>&1' in backup
    assert 'rclone copyto "$ARCHIVE"' in backup
    assert 'rclone copyto "$SHA_FILE"' in backup
    assert 'rclone copyto "$META_FILE"' in backup
    assert 'rclone lsf "$BACKUP_OFFSITE_REMOTE" --files-only' in backup
    assert 'rclone deletefile "$BACKUP_OFFSITE_REMOTE/$sidecar"' in backup
    assert 'rclone deletefile "$BACKUP_OFFSITE_REMOTE/$archive"' in backup
    assert 'rclone delete --min-age' not in backup
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
    local_url = 'https://heartbeat.invalid/local-offsite-success'
    offsite_url = 'https://heartbeat.invalid/offsite-success'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['metadata']['offsite_sync_status'] == 'synced'
    assert observation['metadata']['offsite_synced_at_utc'] is not None
    assert all(not path.exists() for path in observation['old_files'])
    assert observation['order'] == ['old-absent'] * 5
    assert len(observation['calls']) == 5
    assert observation['heartbeat_calls'] == [local_url, offsite_url]


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
    offsite_heartbeat_url = 'https://heartbeat.invalid/offsite-metadata-failure'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_result='metadata-fail',
        offsite_heartbeat_url=offsite_heartbeat_url,
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
    assert observation['heartbeat_calls'] == []


def test_offsite_retention_prunes_over_age_archives_with_sidecars(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        remote_archive_count=5,
        offsite_retention_min_archives=3,
    )
    completed = observation['completed']
    remote_groups = observation['remote_archive_groups']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert all(not path.exists() for group in remote_groups[:3] for path in group)
    assert all(path.exists() for group in remote_groups[3:] for path in group)
    assert observation['metadata']['offsite_prune_status'] == 'succeeded'
    assert len(observation['remote_delete_calls']) == 9
    for offset in range(0, 9, 3):
        calls = observation['remote_delete_calls'][offset : offset + 3]
        assert calls[0].endswith('.dump.sha256')
        assert calls[1].endswith('.dump.json')
        assert calls[2].endswith('.dump')


def test_offsite_retention_floor_keeps_three_over_age_archives(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        remote_archive_count=3,
        offsite_retention_min_archives=4,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert all(
        path.exists()
        for group in observation['remote_archive_groups']
        for path in group
    )
    assert observation['remote_delete_calls'] == []
    assert 'offsite retention floor: keeping' in completed.stdout + completed.stderr


def test_failed_offsite_upload_never_attempts_remote_pruning(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_result='fail',
        remote_archive_count=4,
    )

    assert observation['remote_delete_calls'] == []
    assert all(not call.startswith('lsf ') for call in observation['calls'])
    assert observation['metadata']['offsite_prune_status'] == 'not_run'
    assert 'offsite prune: skipped (offsite status failed)' in (
        observation['completed'].stdout + observation['completed'].stderr
    )


def test_failed_pg_dump_never_attempts_remote_pruning(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        pg_dump_result='fail',
        remote_archive_count=4,
    )

    assert observation['remote_delete_calls'] == []
    assert observation['calls'] == []
    assert 'offsite prune: skipped (no valid local archive)' in (
        observation['completed'].stdout + observation['completed'].stderr
    )


def test_offsite_retention_never_deletes_latest_json(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        remote_archive_count=4,
        offsite_retention_min_archives=1,
    )

    assert 'latest.json' in observation['remote_files']
    assert any(call.startswith('lsf ') for call in observation['calls'])
    assert all(
        not call.endswith('/latest.json') for call in observation['remote_delete_calls']
    )


def test_remote_prune_failure_exits_nonzero_without_changing_local_archive_set(
    tmp_path: Path,
):
    successful_root = tmp_path / 'successful'
    failed_root = tmp_path / 'failed'
    successful_root.mkdir()
    failed_root.mkdir()
    scenario_options = {
        'offsite': True,
        'old_archive_count': 2,
        'retention_min_archives': 1,
        'remote_archive_count': 4,
        'offsite_retention_min_archives': 1,
    }
    successful = _run_backup_scenario(successful_root, **scenario_options)
    failed = _run_backup_scenario(
        failed_root,
        rclone_prune_result='fail',
        **scenario_options,
    )
    successful_completed = successful['completed']
    failed_completed = failed['completed']

    assert isinstance(successful_completed, subprocess.CompletedProcess)
    assert isinstance(failed_completed, subprocess.CompletedProcess)
    assert successful_completed.returncode == 0
    assert failed_completed.returncode != 0
    assert all(not path.exists() for path in successful['old_files'])
    assert all(not path.exists() for path in failed['old_files'])
    successful_shape = (
        len(list(successful['backup_dir'].glob('edfinder_*.dump'))),
        len(list(successful['backup_dir'].glob('edfinder_*.dump.sha256'))),
        len(list(successful['backup_dir'].glob('edfinder_*.dump.json'))),
    )
    failed_shape = (
        len(list(failed['backup_dir'].glob('edfinder_*.dump'))),
        len(list(failed['backup_dir'].glob('edfinder_*.dump.sha256'))),
        len(list(failed['backup_dir'].glob('edfinder_*.dump.json'))),
    )
    assert failed_shape == successful_shape == (1, 1, 1)
    assert failed['metadata']['offsite_sync_status'] == 'synced'
    assert failed['metadata']['offsite_prune_status'] == 'failed'
    assert failed['remote_delete_calls']
    assert 'ERROR: offsite backup prune failed' in failed['log']


def test_remote_prune_failure_skips_offsite_heartbeat_with_reason(tmp_path: Path):
    local_url = 'https://heartbeat.invalid/local-prune-failure'
    offsite_url = 'https://heartbeat.invalid/offsite-prune-failure'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_prune_result='fail',
        remote_archive_count=4,
        offsite_retention_min_archives=1,
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert offsite_url not in observation['heartbeat_calls']
    assert 'offsite heartbeat: skipped (offsite prune failed)' in output


def test_remote_prune_failure_still_sends_local_heartbeat(tmp_path: Path):
    local_url = 'https://heartbeat.invalid/local-prune-failure'
    offsite_url = 'https://heartbeat.invalid/offsite-prune-failure'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_prune_result='fail',
        remote_archive_count=4,
        offsite_retention_min_archives=1,
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )

    assert observation['heartbeat_calls'] == [local_url]


def test_fully_healthy_offsite_path_sends_both_heartbeats_and_exits_zero(tmp_path: Path):
    local_url = 'https://heartbeat.invalid/local-healthy'
    offsite_url = 'https://heartbeat.invalid/offsite-healthy'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['metadata']['offsite_prune_status'] == 'not_required'
    assert observation['heartbeat_calls'] == [local_url, offsite_url]


def test_offsite_disabled_exits_zero_without_offsite_heartbeat(tmp_path: Path):
    backup = _read('apps', 'maintenance', 'scripts', 'run_backup.sh')
    local_url = 'https://heartbeat.invalid/local-disabled'
    offsite_url = 'https://heartbeat.invalid/offsite-disabled'
    observation = _run_backup_scenario(
        tmp_path,
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )
    completed = observation['completed']

    assert '"$OFFSITE_PRUNE_STATUS" == "not_required"' in backup
    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert observation['metadata']['offsite_sync_status'] == 'disabled'
    assert observation['heartbeat_calls'] == [local_url]


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


def test_retention_floor_holds_under_repeated_dump_failure(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        pg_dump_result='fail',
        old_archive_count=3,
        retention_min_archives=None,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert all(path.exists() for path in observation['old_files'])
    assert len(list(observation['backup_dir'].glob('edfinder_*.dump'))) == 3
    assert 'retention floor: keeping' in completed.stdout + completed.stderr
    _assert_archive_sidecars_consistent(observation['backup_dir'])


def test_retention_floor_allows_normal_pruning_down_to_floor(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        old_archive_count=6,
        retention_min_archives=None,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert len(list(observation['backup_dir'].glob('edfinder_*.dump'))) == 3
    assert all(not path.exists() for path in observation['old_archives'][:4])
    assert all(path.exists() for path in observation['old_archives'][4:])
    _assert_archive_sidecars_consistent(observation['backup_dir'])


def test_retention_prunes_archive_and_sidecars_as_one_unit(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        old_archive_count=4,
        retention_min_archives=3,
        fresh_sidecars_for_oldest=True,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    _assert_archive_sidecars_consistent(observation['backup_dir'])


def test_retention_floor_is_configurable(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        pg_dump_result='fail',
        old_archive_count=3,
        retention_min_archives=1,
    )
    completed = observation['completed']

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert len(list(observation['backup_dir'].glob('edfinder_*.dump'))) == 1
    assert all(not path.exists() for path in observation['old_archives'][:2])
    assert observation['old_archives'][2].exists()
    _assert_archive_sidecars_consistent(observation['backup_dir'])


def test_unconfigured_heartbeats_are_skipped_without_attempting_a_ping(tmp_path: Path):
    observation = _run_backup_scenario(tmp_path)
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, output
    assert observation['heartbeat_calls'] == []
    assert 'local heartbeat: skipped (unconfigured)' in output
    assert 'offsite heartbeat: skipped (unconfigured)' in output


def test_local_success_sends_the_local_heartbeat_once(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/local-success'
    observation = _run_backup_scenario(
        tmp_path,
        local_heartbeat_url=heartbeat_url,
    )
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, output
    assert observation['heartbeat_calls'] == [heartbeat_url]
    assert 'local heartbeat: sent' in output


def test_offsite_failure_does_not_suppress_the_local_heartbeat(tmp_path: Path):
    local_url = 'https://heartbeat.invalid/local-offsite-failure'
    offsite_url = 'https://heartbeat.invalid/offsite-failure'
    observation = _run_backup_scenario(
        tmp_path,
        offsite=True,
        rclone_result='fail',
        local_heartbeat_url=local_url,
        offsite_heartbeat_url=offsite_url,
    )
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['heartbeat_calls'] == [local_url]
    assert 'local heartbeat: sent' in output
    assert 'offsite heartbeat: skipped (offsite status failed)' in output


def test_dump_failure_sends_no_heartbeat(tmp_path: Path):
    observation = _run_backup_scenario(
        tmp_path,
        pg_dump_result='fail',
        local_heartbeat_url='https://heartbeat.invalid/local-dump-failure',
        offsite_heartbeat_url='https://heartbeat.invalid/offsite-dump-failure',
    )
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0
    assert observation['heartbeat_calls'] == []
    assert 'local heartbeat: skipped (no valid local archive)' in output
    assert 'offsite heartbeat: skipped (no valid local archive)' in output


def test_heartbeat_failure_does_not_change_backup_success(tmp_path: Path):
    heartbeat_url = 'https://heartbeat.invalid/local-ping-failure'
    observation = _run_backup_scenario(
        tmp_path,
        local_heartbeat_url=heartbeat_url,
        curl_result='fail',
    )
    completed = observation['completed']
    output = completed.stdout + completed.stderr

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0, output
    assert observation['heartbeat_calls'] == [heartbeat_url]
    assert 'local heartbeat: failed' in output


def test_backup_runbook_and_remediation_docs_are_historical_v2_not_v3_recovery_authority():
    runbook = _read('docs', 'operations', 'postgres-backup-and-restore.md')
    remediation = _read('docs', 'operations', 'audit-remediation-plan.md')
    roadmap = _read('docs', 'ROADMAP.md')
    status = _read('docs', 'operations', 'infrastructure-status.md')

    assert 'RETIRED — V2/Hetzner PostgreSQL backup and restore contract' in runbook
    assert 'Historical evidence only. Do not execute this document.' in runbook
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
    assert 'historical minimum V2 restore-readiness baseline' in squashed
    assert 'do **not** constitute a V3 PostgreSQL 18 recovery runbook' in roadmap
    assert 'does not currently contain an executable PostgreSQL 18 backup/restore/PITR recovery runbook' in status


def test_local_backup_retention_repo_default_stays_safe_without_offsite_mirror():
    """The repo/local BACKUP_RETENTION_DAYS default remains conservative.

    This is a repository-helper contract only. The former V2 production
    Storage Box override is historical evidence and is not current V3 backup
    policy; V3 recovery configuration comes from a current reviewed runbook.
    """
    compose = _read('docker-compose.yml')
    env_example = _read('env.example')
    runbook = _read('docs', 'operations', 'postgres-backup-and-restore.md')

    assert 'BACKUP_RETENTION_DAYS: ${BACKUP_RETENTION_DAYS:-14}' in compose
    assert 'BACKUP_RETENTION_DAYS: ${BACKUP_RETENTION_DAYS:-3}' not in compose
    env_example_lines = env_example.splitlines()
    assert 'BACKUP_RETENTION_DAYS=14' in env_example_lines
    assert 'BACKUP_RETENTION_DAYS=3' not in env_example_lines
    assert 'retention: `14` days locally by repo default' in runbook
    assert 'untracked `.env`' in runbook


def test_data_invariant_helpers_remain_available_but_v2_post_deploy_path_is_retired():
    compose = _read('docker-compose.yml')
    crontab = _read('apps', 'maintenance', 'scripts', 'crontab')
    deploy = _read('scripts', 'deploy_main.sh')
    wrapper = _read('scripts', 'run_data_invariants_receipted.sh')
    runbook = _read('docs', 'operations', 'stage17n2c-data-trust-runbook.md')

    assert 'DATA_INVARIANTS_DATABASE_URL: ${DATABASE_READONLY_URL:-${DATABASE_APP_URL:-postgresql://edfinder:${POSTGRES_PASSWORD}@postgres:5432/edfinder}}' in compose
    assert '/usr/local/bin/run_data_invariants_receipted.sh --target-rating-version 3.4' in crontab
    assert 'RETIRED — V2 single-host deployment entrypoint' in deploy
    assert '--skip-invariants' not in deploy
    assert 'run_data_invariants_receipted.sh' not in deploy
    assert 'TARGET_RATING_VERSION="${TARGET_RATING_VERSION:-3.4}"' in wrapper
    assert 'DURABLE_RECEIPT_DIR="${DURABLE_RECEIPT_DIR:-}"' in wrapper
    assert 'DATABASE_URL_OVERRIDE="${DATA_INVARIANTS_DATABASE_URL:-}"' in wrapper
    assert '--database-url) DATABASE_URL_OVERRIDE="$2"; shift 2 ;;' in wrapper
    assert '--durable-receipt-dir) DURABLE_RECEIPT_DIR="$2"; shift 2 ;;' in wrapper
    assert '--production-safe' in wrapper
    assert '--allow-stale-colonisation-status) ALLOW_STALE_COLONISATION_STATUS=1; shift ;;' in wrapper
    assert '"status": "$status"' in wrapper
    assert '"allow_stale_colonisation_status":' in wrapper
    assert '"allow_stale_noneligible":' in wrapper
    assert 'data-invariants-${durable_stamp}.json' in wrapper
    assert 'latest.json' in wrapper
    assert 'RETIRED — Stage 17N2C V2/Hetzner data-trust runbook' in runbook
    assert '45 4 * * 0 /usr/local/bin/run_data_invariants_receipted.sh' in runbook
    assert '/data/receipts/data-invariants/weekly-latest.json' in runbook
    assert 'DATA_INVARIANTS_DATABASE_URL' in runbook
    assert 'scripts/deploy_main.sh` now runs the wrapper by default' in runbook
