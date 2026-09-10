from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / 'scripts' / 'v3' / 'apply_migrations.py'


def _load_runner():
    spec = importlib.util.spec_from_file_location('v3_apply_migrations', RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_baseline_hash_and_separate_manifest_order():
    runner = _load_runner()
    baseline = ROOT / 'sql' / 'v3' / 'migrations' / '001_v3_baseline.sql'
    entries = runner.load_manifest()

    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == (
        'ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e'
    )
    assert [entry.name for entry in entries[:2]] == [
        '001_v3_baseline.sql',
        '002_v3_accounts_identity.sql',
    ]
    assert all(entry.path.parent == baseline.parent for entry in entries)


def test_v3_lineage_does_not_use_v2_oauth_migrations():
    v3_manifest = (ROOT / 'sql' / 'v3' / 'migration-manifest.txt').read_text(
        encoding='utf-8',
    )
    v2_manifest = (ROOT / 'sql' / 'migration-manifest.txt').read_text(
        encoding='utf-8',
    )
    migration = (
        ROOT / 'sql' / 'v3' / 'migrations' / '002_v3_accounts_identity.sql'
    ).read_text(encoding='utf-8')

    assert '048_frontier_accounts.sql' not in v3_manifest
    assert '048_v3_accounts_identity.sql' not in v3_manifest
    assert '048_frontier_accounts.sql' not in v2_manifest
    assert '048_v3_accounts_identity.sql' not in v2_manifest
    assert not (ROOT / 'sql' / '048_frontier_accounts.sql').exists()
    assert not (ROOT / 'sql' / '048_v3_accounts_identity.sql').exists()
    assert 'v2 oauth tables' in migration.lower()
    assert 'v3_identity.oauth_login_state' in migration


def test_runner_preserves_frozen_file_but_can_ledger_it_atomically():
    runner = _load_runner()
    baseline = (
        ROOT / 'sql' / 'v3' / 'migrations' / '001_v3_baseline.sql'
    ).read_text(encoding='utf-8')
    executable = runner.strip_baseline_transaction(baseline)

    assert baseline.count('BEGIN;') == 1
    assert baseline.count('COMMIT;') == 1
    assert '\nBEGIN;\n' not in executable
    assert not executable.rstrip().endswith('COMMIT;')
    assert 'CREATE TABLE v3_meta.schema_migration' in executable


def test_v3_identity_application_sql_is_schema_qualified():
    sources = [
        (ROOT / 'apps' / 'api' / 'src' / 'auth.py').read_text(encoding='utf-8'),
        (ROOT / 'apps' / 'api' / 'src' / 'routers' / 'auth.py').read_text(
            encoding='utf-8',
        ),
    ]
    combined = '\n'.join(sources)

    for retired_name in (
        'oauth_login_states',
        'account_sessions',
        'account_role_assignments',
        'security_audit_events',
    ):
        assert retired_name not in combined
    for authoritative_name in (
        'v3_identity.account',
        'v3_identity.external_identity',
        'v3_identity.session',
        'v3_identity.account_role',
        'v3_identity.oauth_login_state',
        'v3_identity.security_audit_event',
    ):
        assert authoritative_name in combined
