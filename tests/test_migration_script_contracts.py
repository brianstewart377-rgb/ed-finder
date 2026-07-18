import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLY_MIGRATIONS = ROOT / 'scripts' / 'apply_migrations.sh'
BASELINE_MIGRATIONS = ROOT / 'scripts' / 'baseline_migration_ledger.sh'
SEED_CHECK = ROOT / 'scripts' / 'seed_check.sh'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
BASELINE_SCHEMA = ROOT / 'sql' / '001_schema.sql'
CLUSTER_WIDENING = ROOT / 'sql' / '040_cluster_summary_widen_counts.sql'
MIGRATION_MANIFEST = ROOT / 'sql' / 'migration-manifest.txt'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_apply_migrations_uses_manifest_ledger_and_checksum_guards():
    script = _read(APPLY_MIGRATIONS)

    assert 'ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"' in script
    assert 'DATABASE_URL="${DATABASE_MIGRATION_URL:-${DATABASE_URL:-}}"' in script
    assert 'MANIFEST_FILE="${MIGRATION_MANIFEST:-$SQL_DIR/migration-manifest.txt}"' in script
    assert 'LEDGER_TABLE="${MIGRATION_LEDGER_TABLE:-schema_migrations}"' in script
    assert 'COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"' in script
    assert '--compose-file' in script
    assert 'dc exec -T "$MIGRATION_DB_SERVICE" sh -lc' in script
    assert 'CREATE TABLE IF NOT EXISTS ${LEDGER_TABLE}' in script
    assert 'checksum_sha256 TEXT NOT NULL' in script
    assert 'if [[ "$mode" == "manual" && "$INCLUDE_MANUAL" -ne 1 ]]; then' in script
    assert 'die "Checksum mismatch for already-recorded migration $filename"' in script
    assert 'PGOPTIONS="$PGOPTIONS_VALUE" psql -v ON_ERROR_STOP=1 -f "$file" "$DATABASE_URL"' in script
    assert 'if [[ -n "${DATABASE_URL:-}" ]]; then' in script
    assert 'need_cmd psql' in script
    assert 'else\n  need_cmd docker\nfi' in script


def test_production_baselined_schema_migration_remains_immutable():
    expected_checksum = '190df25ad2f7ea0f657788e9446581bd6193560aac93dbf846ff20d75f4aa653'
    baseline_bytes = BASELINE_SCHEMA.read_bytes().replace(b'\r\n', b'\n')
    actual_checksum = hashlib.sha256(baseline_bytes).hexdigest()
    widening = _read(CLUSTER_WIDENING)
    manifest = _read(MIGRATION_MANIFEST)

    assert actual_checksum == expected_checksum
    assert '040_cluster_summary_widen_counts.sql' in manifest
    for column in (
        'agriculture_count',
        'agriculture_best',
        'refinery_count',
        'refinery_best',
        'industrial_count',
        'industrial_best',
        'hightech_count',
        'hightech_best',
        'military_count',
        'military_best',
        'tourism_count',
        'tourism_best',
        'total_viable',
    ):
        assert f'ALTER COLUMN {column}' in widening


def test_seed_check_stays_on_manifested_apply_path_and_asserts_seed_invariants():
    script = _read(SEED_CHECK)

    assert 'DATABASE_URL="$DB_URL" bash "$(dirname "$0")/apply_migrations.sh" --include-manual' in script
    assert 'psql -v ON_ERROR_STOP=1 -q -f "$SQL_DIR/seed_preview.sql" "$DB_URL"' in script
    assert 'LEFT JOIN ratings r ON r.system_id64 = s.id64' in script
    assert 'SELECT refresh_map_mviews();' in script
    assert 'REFRESH MATERIALIZED VIEW mv_archetype_rankings;' in script


def test_baseline_migration_script_requires_reviewed_cutover_inputs():
    script = _read(BASELINE_MIGRATIONS)

    assert 'ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"' in script
    assert 'DATABASE_URL="${DATABASE_MIGRATION_URL:-${DATABASE_URL:-}}"' in script
    assert 'MANUAL_STATUS_TABLE="${MIGRATION_MANUAL_STATUS_TABLE:-schema_migration_manual_status}"' in script
    assert 'COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"' in script
    assert '--compose-file' in script
    assert 'dc exec -T "$MIGRATION_DB_SERVICE" sh -lc' in script
    assert '--baseline-through is required' in script
    assert 'manual 019 cannot stay pending when baseline continues past 019' in script
    assert 'provide --manual-019-status applied|pending' in script
    assert "INSERT INTO ${MANUAL_STATUS_TABLE} (filename, status, notes)" in script
    assert "INSERT INTO ${LEDGER_TABLE} (filename, checksum_sha256, apply_mode, notes)" in script
    assert "VALUES ('${filename_sql}', '${checksum_sql}', 'baseline', '${notes_sql}')" in script


def test_local_ci_parity_covers_migration_and_ci_contract_tests():
    script = _read(LOCAL_CI_PARITY)

    assert 'section "Migration/apply and CI contract tests"' in script
    assert 'tests/test_migration_script_contracts.py' in script
    assert 'tests/test_migration_applier_runtime.py' in script
    assert 'tests/test_migration_ledger_baseline_runtime.py' in script
    assert 'tests/test_data_trust_runtime.py' in script
    assert 'tests/test_ci_data_invariants.py' in script
    assert 'tests/test_ci_build_reproducibility_contracts.py' in script
    assert 'tests/test_backup_restore_ops.py' in script
    assert 'bash scripts/checks/openapi-drift.sh' in script
    assert 'git diff --check' in script


def test_ci_workflow_has_focused_script_contracts_job():
    workflow = _read(CI_WORKFLOW)

    assert 'script-contracts:' in workflow
    assert 'name: Script contracts + migration paths' in workflow
    assert 'bash -n scripts/apply_migrations.sh' in workflow
    assert 'bash -n scripts/baseline_migration_ledger.sh' in workflow
    assert 'bash -n scripts/seed_check.sh' in workflow
    assert 'bash -n scripts/checks/local-ci-parity.sh' in workflow
    assert 'bash -n scripts/run_canonical_safety_tests.sh' in workflow
    assert 'tests/test_migration_script_contracts.py' in workflow
    assert 'tests/test_ci_dependency_contract.py' in workflow
    assert 'tests/test_ci_data_invariants.py' in workflow
    assert 'tests/test_backup_restore_ops.py' in workflow
    assert 'tests/test_windows_local_db_reset_contract.py' in workflow


def test_ci_integration_job_runs_migration_runtime_rehearsal():
    workflow = _read(CI_WORKFLOW)

    assert 'Run integration test suite' in workflow
    assert 'tests/integration/' in workflow
    assert 'tests/test_migration_applier_runtime.py' in workflow
    assert 'tests/test_migration_ledger_baseline_runtime.py' in workflow
    assert 'tests/test_data_trust_runtime.py' in workflow
