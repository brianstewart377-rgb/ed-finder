"""Task 1: the shared canonical bootstrap publishes a ``v3_gen_*`` generation
into an already-migrated connection (no DB create/drop, no migrations).

Skips unless the isolated local PostgreSQL validation service is configured
(see reference_local_test_database)."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_bootstrap_publishes_canonical_generation():
    import psycopg
    from psycopg.conninfo import make_conninfo
    from domain.ratings_v4_canonical import load_source_fixture
    from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical

    dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    db = 'boot_test_' + uuid4().hex
    canonical, metadata, _ = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{db}"')
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                gen = bootstrap_published_canonical(conn, canonical, metadata)
                row = conn.execute(
                    'SELECT lifecycle_state FROM v3_meta.canonical_generation WHERE generation_id=%s',
                    (gen,)).fetchone()
                assert row[0] == 'PUBLISHED'
        finally:
            admin.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
