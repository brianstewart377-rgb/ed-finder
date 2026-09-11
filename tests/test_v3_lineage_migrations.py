"""Structural guards for the committed V3 lineage migrations.

Rules that every migration must satisfy for the reviewed production migration
operation to apply it safely, plus the objects each migration promises.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sql/v3/migration-manifest.txt"

# 002 predates the self-transaction rule and is already applied, so it is never
# re-applied. Nothing else may join this set.
APPLIED_BEFORE_THE_RULE = {"002_v3_accounts_identity.sql"}


def _entries() -> list[tuple[str, str]]:
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        checksum, _, remainder = line.partition("  ")
        ledger_name, _, path = remainder.partition("  ")
        rows.append((ledger_name, f"sql/{path}"))
        assert re.fullmatch(r"[0-9a-f]{64}", checksum), line
    return rows


def test_every_manifest_migration_exists_and_hashes_as_recorded():
    from hashlib import sha256

    for ledger_name, path in _entries():
        source = (ROOT / path).read_bytes()
        recorded = next(
            line.split("  ")[0]
            for line in MANIFEST.read_text(encoding="utf-8").splitlines()
            if line.strip().endswith(path.removeprefix("sql/"))
        )
        assert sha256(source).hexdigest() == recorded, ledger_name
        assert b"\r\n" not in source, f"{path} must stay LF-terminated"


def test_every_migration_about_to_be_applied_owns_its_transaction():
    module = importlib.util.spec_from_file_location(
        "v3_production_migrate", ROOT / "scripts/operator/v3_production_migrate.py"
    )
    assert module and module.loader
    migrate = importlib.util.module_from_spec(module)
    module.loader.exec_module(migrate)

    for ledger_name, path in _entries():
        text = (ROOT / path).read_text(encoding="utf-8")
        if ledger_name in APPLIED_BEFORE_THE_RULE:
            continue
        migrate.require_self_transactional(text, ledger_name)


def test_004_creates_the_search_spatial_and_cluster_objects():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    for relation in (
        "v3_derived.system_search",
        "v3_spatial.cell_level",
        "v3_spatial.cell_summary",
        "v3_spatial.cluster_run",
        "v3_spatial.cluster",
        "v3_spatial.cluster_member",
    ):
        assert f"CREATE TABLE {relation}" in source
    assert "CREATE SCHEMA v3_spatial" in source
    assert "CREATE VIEW v3_app.system_search" in source
    assert "CREATE VIEW v3_app.cluster_member" in source


def test_004_uses_cube_with_gist_and_not_postgis():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE EXTENSION IF NOT EXISTS cube" in source
    assert "position_ly cube NOT NULL" in source
    assert "USING gist(position_ly)" in source
    # Verified against the retained production database: postgis is unavailable,
    # so nothing may depend on it. The comment naming it is fine; using it is not.
    assert "CREATE EXTENSION IF NOT EXISTS postgis" not in source.lower()
    assert "USING gist(geometry" not in source
    assert "geometry" not in source.lower()


def test_004_applies_the_shared_immutability_guard_to_every_new_relation():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    assert "v3_derived.guard_generation_write()" in source
    for relation in (
        "v3_derived.system_search",
        "v3_spatial.cell_summary",
        "v3_spatial.cluster_run",
        "v3_spatial.cluster",
        "v3_spatial.cluster_member",
    ):
        assert f"'{relation}'" in source, relation
    # Five trigger forms per relation, as 003 established.
    assert "immutable_insert" in source
    assert "immutable_update_old" in source
    assert "immutable_update_new" in source
    assert "immutable_delete" in source
    assert "immutable_truncate" in source


def test_004_never_touches_canonical_truth():
    source = (ROOT / "sql/v3/migrations/004_v3_search_spatial_clusters.sql").read_text(
        encoding="utf-8"
    )

    # TRUNCATE is deliberately absent from this list: the migration adds a
    # BEFORE TRUNCATE guard that forbids it, so the word appears by design.
    for forbidden in (
        "v3_gen_",
        "v3_identity.",
        "v3_vocab.",
        "v3_source.",
        "DROP TABLE",
        "DROP SCHEMA",
    ):
        assert forbidden not in source, forbidden
    # Derived data is generated, never hand-written into canonical relations.
    assert "INSERT INTO v3_gen" not in source
