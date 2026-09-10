from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V3_ROOT = ROOT / "sql" / "v3"
BASELINE_SHA256 = (
    "ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_entries() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw_line in (V3_ROOT / "migration-manifest.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        assert match is not None
        entries.append((match.group(1), match.group(2)))
    return entries


def test_v3_manifest_is_a_checksum_locked_separate_lineage() -> None:
    entries = _manifest_entries()
    assert [name for _, name in entries] == [
        "001_v3_baseline.sql",
        "002_v3_accounts_identity.sql",
    ]
    assert entries[0][0] == BASELINE_SHA256
    for expected_sha, name in entries:
        assert _sha256(V3_ROOT / "migrations" / name) == expected_sha

    legacy_manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(
        encoding="utf-8"
    )
    assert "001_v3_baseline.sql" not in legacy_manifest
    assert "002_v3_accounts_identity.sql" not in legacy_manifest
    assert "048_v3_accounts_identity.sql" not in legacy_manifest
    assert "048_frontier_accounts.sql" not in legacy_manifest


def test_v3_runner_uses_only_the_v3_manifest_and_ledger() -> None:
    runner = (ROOT / "scripts" / "v3" / "apply_migrations.py").read_text(
        encoding="utf-8"
    )
    assert 'ROOT / "sql" / "v3" / "migration-manifest.txt"' in runner
    assert 'ROOT / "sql" / "v3" / "migrations"' in runner
    assert "v3_meta.schema_migration" in runner
    assert "bootstrap-empty" in runner
    assert "non_relation_user_object_count" in runner
    assert "bootstrap-empty requires a database with no user objects" in runner
    assert "upgrade" in runner
    assert "schema_migrations" not in runner
    assert "sql/migration-manifest.txt" not in runner
    assert "048_frontier_accounts" not in runner
    assert BASELINE_SHA256 in runner


def test_first_post_baseline_migration_extends_frozen_v3_identity() -> None:
    migration = (
        V3_ROOT / "migrations" / "002_v3_accounts_identity.sql"
    ).read_text(encoding="utf-8")
    lowered = migration.lower()
    for authority in (
        "v3_identity.account",
        "v3_identity.external_identity",
        "v3_identity.commander",
        "v3_identity.account_commander_access",
        "v3_identity.account_role",
        "v3_identity.session",
        "v3_identity.oauth_login_state",
        "v3_identity.security_audit_event",
    ):
        assert authority in lowered
    assert "create table accounts" not in lowered
    assert "create table app_users" not in lowered
    assert "create table web_sessions" not in lowered
    assert "public." not in lowered
    assert "access_token" not in lowered
    assert "refresh_token" not in lowered


def test_oauth_runtime_queries_are_schema_qualified_to_v3() -> None:
    source = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "apps/api/src/auth.py",
            "apps/api/src/routers/auth.py",
        )
    )
    for legacy_relation in (
        "accounts",
        "external_identities",
        "commanders",
        "account_role_assignments",
        "account_sessions",
        "oauth_login_states",
        "security_audit_events",
    ):
        assert legacy_relation not in source
    for relation in (
        "v3_identity.account",
        "v3_identity.external_identity",
        "v3_identity.commander",
        "v3_identity.account_role",
        "v3_identity.session",
        "v3_identity.oauth_login_state",
        "v3_identity.security_audit_event",
    ):
        assert relation in source
