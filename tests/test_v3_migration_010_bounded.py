from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'sql/v3/migrations/010_v3_system_search_body_type_counts.sql'
MIGRATE = ROOT / 'scripts/operator/v3_production_migrate.py'


def test_migration_010_is_self_transactional_and_bounded():
    spec = importlib.util.spec_from_file_location('v3_production_migrate_010_test', MIGRATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = MIGRATION.read_text(encoding='utf-8')
    module.terminal_commit_span(source, MIGRATION.name)

    statements = [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith('--')
    ]
    assert statements[0] == 'BEGIN;'
    assert statements[-1] == 'COMMIT;'
    assert source.rstrip().endswith('COMMIT;')
    assert "SET LOCAL lock_timeout = '5s';" in source
    assert "SET LOCAL statement_timeout = '30s';" in source

    add_columns = source.split(
        'ALTER TABLE v3_derived.system_search', 1
    )[1].split(';', 1)[0]
    assert 'ADD COLUMN' in add_columns
    assert 'CHECK(' not in add_columns
    assert source.count('NOT VALID') == 18
