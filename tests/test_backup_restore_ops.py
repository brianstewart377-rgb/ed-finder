from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return ' '.join(text.split())


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
