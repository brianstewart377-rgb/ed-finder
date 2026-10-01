"""Task 3: the Cypress seed publishes a real V3 derived generation and the
journey id64s are exposed through ``v3_app.system_search``.

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

ACHENAR = 10477373803000
LOSSLESS = 9007199254740993


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_publishes_and_exposes_journey_ids():
    import psycopg
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation

    dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    db = 'seed_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{db}"')
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                sequence = seed_cypress_v3_generation(conn)
                assert sequence == 1
                exposed = {r[0] for r in conn.execute(
                    'SELECT system_id64 FROM v3_app.system_search').fetchall()}
                assert ACHENAR in exposed
                assert LOSSLESS in exposed
                # idempotent: a second call does not republish.
                assert seed_cypress_v3_generation(conn) == 1
        finally:
            admin.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
