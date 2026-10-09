"""Review Lab publishes its dedicated fixture through the full V3 lineage.

Skips unless the isolated local PostgreSQL validation service is configured
(see reference_local_test_database).
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

REVIEW_FIXTURE_DIR = ROOT / 'tests/fixtures/review_lab_v3_sources'
REVIEW_SYSTEM_IDS = {9100000000001, 9100000000002, 9100000000003}


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_review_seed_publishes_dedicated_fixture_and_spatial_pyramid():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.review_lab.lifecycle import V3_LINEAGE_FILES
    from scripts.dev.seed_review_v3_generation import seed_review_spatial_pyramid
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation
    from tests.helpers.db_isolation import validate_test_db_target

    dsn = validate_test_db_target(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    ).dsn
    database = 'seed_review_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        try:
            with psycopg.connect(
                make_conninfo(dsn, dbname=database), autocommit=True
            ) as connection:
                for path in V3_LINEAGE_FILES:
                    connection.execute((ROOT / 'sql' / path).read_text())

                assert seed_v3_fixture_generation(
                    connection,
                    REVIEW_FIXTURE_DIR,
                    generation_key_prefix='review_lab_v3_',
                    publication_actor='review-lab-seed',
                    publication_note='review lab v3 fixture',
                ) == 1

                exposed = {
                    row[0]
                    for row in connection.execute(
                        'SELECT system_id64 FROM v3_app.system_search'
                    ).fetchall()
                }
                assert exposed == REVIEW_SYSTEM_IDS

                products = dict(
                    connection.execute(
                        'SELECT p.product_code, p.lifecycle_state '
                        'FROM v3_meta.derived_product p '
                        'JOIN v3_meta.current_derived_generation c '
                        'USING (derived_generation_id) '
                        'WHERE p.product_code = ANY(%s)',
                        (['system_search', 'system_archetype'],),
                    ).fetchall()
                )
                assert products == {
                    'system_search': 'READY',
                    'system_archetype': 'READY',
                }
                receipts = dict(
                    connection.execute(
                        "SELECT p.product_code, p.validation_receipt->>'status' "
                        'FROM v3_meta.derived_product p '
                        'JOIN v3_meta.current_derived_generation c '
                        'USING (derived_generation_id) '
                        'WHERE p.product_code = ANY(%s)',
                        (['system_search', 'system_archetype'],),
                    ).fetchall()
                )
                assert receipts == {
                    'system_search': 'VERIFIED',
                    'system_archetype': 'VERIFIED',
                }

                manifest_digest = sha256(
                    (REVIEW_FIXTURE_DIR / 'manifest.json').read_bytes()
                ).hexdigest()
                audit_reason = connection.execute(
                    'SELECT reason FROM v3_meta.derived_publication_audit '
                    'WHERE publication_sequence=1'
                ).fetchone()[0]
                assert audit_reason.endswith(
                    f' [fixture_manifest_sha256={manifest_digest}]'
                )

                assert connection.execute(
                    'SELECT COUNT(*) '
                    'FROM v3_spatial.current_spatial_generation'
                ).fetchone() == (0,)
                assert connection.execute(
                    "SELECT to_regclass('public.mv_map_heatmap_200ly') IS NULL"
                ).fetchone() == (True,)
                assert seed_review_spatial_pyramid(connection) == 1
                spatial = connection.execute(
                    'SELECT sg.spatial_generation_id, '
                    'sg.canonical_generation_id, sg.lifecycle_state, '
                    'sg.expected_systems, sg.validation_receipt '
                    'FROM v3_spatial.spatial_generation sg '
                    'JOIN v3_spatial.current_spatial_generation c '
                    'USING (spatial_generation_id)'
                ).fetchone()
                canonical_id = connection.execute(
                    'SELECT generation_id '
                    'FROM v3_meta.current_canonical_generation WHERE singleton'
                ).fetchone()[0]
                assert spatial[1:4] == (canonical_id, 'PUBLISHED', 3)
                assert spatial[4]['status'] == 'VERIFIED'
                assert spatial[4]['reconciliation'] == 'passed'

                level_counts = connection.execute(
                    'SELECT level, COUNT(*), SUM(system_count) '
                    'FROM v3_spatial.cell_summary '
                    'WHERE spatial_generation_id=%s '
                    'GROUP BY level ORDER BY level',
                    (spatial[0],),
                ).fetchall()
                assert level_counts == [
                    (0, 2, 3),
                    (1, 2, 3),
                    (2, 2, 3),
                    (3, 3, 3),
                    (4, 3, 3),
                    (5, 3, 3),
                    (6, 3, 3),
                ]
                representatives = {
                    row[0]
                    for row in connection.execute(
                        'SELECT representative_system_id64 '
                        'FROM v3_spatial.cell_summary '
                        'WHERE spatial_generation_id=%s',
                        (spatial[0],),
                    ).fetchall()
                }
                assert representatives and representatives <= exposed

                assert seed_v3_fixture_generation(
                    connection,
                    REVIEW_FIXTURE_DIR,
                    generation_key_prefix='review_lab_v3_',
                    publication_actor='review-lab-seed',
                    publication_note='review lab v3 fixture',
                ) == 1
                assert seed_review_spatial_pyramid(connection) == 1
                assert connection.execute(
                    'SELECT COUNT(*) FROM v3_spatial.spatial_generation'
                ).fetchone() == (1,)
                assert connection.execute(
                    'SELECT COUNT(*) FROM v3_spatial.spatial_publication_audit'
                ).fetchone() == (1,)
        finally:
            admin.execute(
                sql.SQL('DROP DATABASE {} WITH (FORCE)').format(
                    sql.Identifier(database)
                )
            )
