from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLY_MIGRATIONS = ROOT / 'scripts' / 'apply_migrations.sh'
SEED_CHECK = ROOT / 'scripts' / 'seed_check.sh'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_apply_migrations_uses_manifest_ledger_and_checksum_guards():
    script = _read(APPLY_MIGRATIONS)

    assert 'MANIFEST_FILE="${MIGRATION_MANIFEST:-$SQL_DIR/migration-manifest.txt}"' in script
    assert 'LEDGER_TABLE="${MIGRATION_LEDGER_TABLE:-schema_migrations}"' in script
    assert 'CREATE TABLE IF NOT EXISTS ${LEDGER_TABLE}' in script
    assert 'checksum_sha256 TEXT NOT NULL' in script
    assert 'if [[ "$mode" == "manual" && "$INCLUDE_MANUAL" -ne 1 ]]; then' in script
    assert 'die "Checksum mismatch for already-recorded migration $filename"' in script
    assert 'docker compose exec -T "$MIGRATION_DB_SERVICE" sh -lc' in script
    assert 'PGOPTIONS="$PGOPTIONS_VALUE" psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"' in script


def test_seed_check_stays_on_manifested_apply_path_and_asserts_seed_invariants():
    script = _read(SEED_CHECK)

    assert 'DATABASE_URL="$DB_URL" bash "$(dirname "$0")/apply_migrations.sh" --include-manual' in script
    assert 'psql "$DB_URL" -v ON_ERROR_STOP=1 -q -f "$SQL_DIR/seed_preview.sql"' in script
    assert 'LEFT JOIN ratings r ON r.system_id64 = s.id64' in script
    assert 'SELECT refresh_map_mviews();' in script
    assert 'REFRESH MATERIALIZED VIEW mv_archetype_rankings;' in script


def test_local_ci_parity_covers_migration_and_ci_contract_tests():
    script = _read(LOCAL_CI_PARITY)

    assert 'section "Migration/apply and CI contract tests"' in script
    assert 'tests/test_migration_script_contracts.py' in script
    assert 'tests/test_ci_data_invariants.py' in script
    assert 'tests/test_backup_restore_ops.py' in script
    assert 'bash scripts/checks/openapi-drift.sh' in script
    assert 'git diff --check' in script


def test_ci_workflow_has_focused_script_contracts_job():
    workflow = _read(CI_WORKFLOW)

    assert 'script-contracts:' in workflow
    assert 'name: Script contracts + migration paths' in workflow
    assert 'bash -n scripts/apply_migrations.sh' in workflow
    assert 'bash -n scripts/seed_check.sh' in workflow
    assert 'bash -n scripts/checks/local-ci-parity.sh' in workflow
    assert 'bash -n scripts/run_canonical_safety_tests.sh' in workflow
    assert 'tests/test_migration_script_contracts.py' in workflow
    assert 'tests/test_ci_data_invariants.py' in workflow
    assert 'tests/test_backup_restore_ops.py' in workflow
