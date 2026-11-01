"""023 reapplication and name-collision checks on disposable PostgreSQL 18."""

from pathlib import Path

import psycopg
import pytest

from tests.ratings_v4_pg_fixture import canonical_database


pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/v3/migrations/023_v3_system_search_name_prefix_index.sql"


@pytest.fixture
def database():
    with canonical_database() as (conn, *_):
        assert int(conn.execute("SHOW server_version_num").fetchone()[0]) // 10000 == 18
        for name in ("003_ratings_v4_derived.sql", "004_v3_search_spatial_clusters.sql"):
            conn.execute((ROOT / "sql/v3/migrations" / name).read_text())
        yield conn


def test_023_reapplication_keeps_both_name_indexes(database):
    database.execute(MIGRATION.read_text())
    before = database.execute(
        "SELECT 'v3_derived.system_search_name_prefix'::regclass::oid"
    ).fetchone()[0]
    database.execute(MIGRATION.read_text())
    after, original = database.execute(
        "SELECT 'v3_derived.system_search_name_prefix'::regclass::oid, "
        "to_regclass('v3_derived.system_search_name_lower')"
    ).fetchone()
    assert before == after
    assert original is not None


@pytest.mark.parametrize("name_key", ["lower(name)", 'lower(name) COLLATE "POSIX" text_pattern_ops'])
def test_023_refuses_a_same_name_incompatible_index(database, name_key):
    database.execute(
        "CREATE INDEX system_search_name_prefix ON "
        f"v3_derived.system_search (derived_generation_id, {name_key})"
    )
    with pytest.raises(psycopg.errors.RaiseException, match="incompatible definition"):
        database.execute(MIGRATION.read_text())
    database.execute("ROLLBACK")
    assert name_key in database.execute(
        "SELECT pg_get_indexdef('v3_derived.system_search_name_prefix'::regclass)"
    ).fetchone()[0]
