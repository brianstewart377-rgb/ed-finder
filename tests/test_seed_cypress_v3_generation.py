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


def test_seed_main_refuses_non_disposable_target(monkeypatch):
    """The CLI entry point applies migrations and publishes a generation, so it
    must fail closed on a production-looking target before opening any
    connection — no database required for this check."""
    from scripts.dev.seed_cypress_v3_generation import main
    from tests.helpers.db_isolation import DbIsolationError

    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@db.ed-finder.app:5432/edfinder')
    with pytest.raises(DbIsolationError):
        main()


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
@pytest.mark.parametrize('full_review_lineage', [False, True])
def test_seed_publishes_and_exposes_journey_ids(full_review_lineage):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.review_lab.lifecycle import V3_LINEAGE_FILES
    from tests.helpers.db_isolation import validate_test_db_target

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                lineage = V3_LINEAGE_FILES if full_review_lineage else ('v3/migrations/001_v3_baseline.sql',)
                for path in lineage:
                    conn.execute((ROOT / 'sql' / path).read_text())
                sequence = seed_cypress_v3_generation(conn)
                assert sequence == 1
                exposed = {r[0] for r in conn.execute(
                    'SELECT system_id64 FROM v3_app.system_search').fetchall()}
                assert ACHENAR in exposed
                assert LOSSLESS in exposed
                assert 158872029 in exposed
                assert len(exposed) == 3
                published = conn.execute(
                    'SELECT d.lifecycle_state FROM v3_meta.derived_generation d '
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id)'
                ).fetchone()
                assert published == ('PUBLISHED',)
                products = dict(conn.execute(
                    'SELECT p.product_code, p.lifecycle_state FROM v3_meta.derived_product p '
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id) '
                    'WHERE p.product_code = ANY(%s)',
                    (['system_search', 'system_archetype'],),
                ).fetchall())
                assert products == {'system_search': 'READY', 'system_archetype': 'READY'}
                receipts = conn.execute(
                    "SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p "
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id) '
                    'WHERE p.product_code = ANY(%s)',
                    (['system_search', 'system_archetype'],),
                ).fetchall()
                assert receipts == [('VERIFIED',), ('VERIFIED',)]
                assert conn.execute('SELECT COUNT(*) FROM v3_app.system_archetype').fetchone()[0] > 0
                if full_review_lineage:
                    assert conn.execute("SELECT to_regclass('v3_private.watchlist') IS NOT NULL").fetchone()[0]
                    assert conn.execute("SELECT to_regclass('public.systems') IS NULL").fetchone()[0]
                # idempotent: a second call does not republish.
                assert seed_cypress_v3_generation(conn) == 1
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))
