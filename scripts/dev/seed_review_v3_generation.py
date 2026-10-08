"""INTERIM Review Lab V3 plumbing proof using the proven Cypress builder.

Run host-side in the apps/api test venv, never in the production API image.
TODO(Phase 2): replace the source fixture with purpose-built Review Lab data;
see docs/development/review-lab-v3-redo.md. Publication is idempotent and uses
the genuine canonical, Search, Archetype and spatial validation/CAS pipelines.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.api.src.review_runtime_guard import EXPECTED_REVIEW_DATABASE_NAME  # noqa: E402
from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation  # noqa: E402
from scripts import v3_spatial_pyramid as spatial_builder  # noqa: E402
from tests.helpers.db_isolation import DbIsolationError, DbTarget, validate_test_db_target  # noqa: E402

EXPECTED_REVIEW_SEED_HOST = '127.0.0.1'
EXPECTED_REVIEW_SEED_PORT = 55433
REVIEW_PYRAMID_VERSION = 'review_pyramid_v1'
MAX_REVIEW_SPATIAL_SYSTEMS = 1_000


class ReviewSeedError(RuntimeError):
    """A review seed target or connected database is unsafe."""


def validate_review_seed_target(dsn: str) -> DbTarget:
    # Accept only an unambiguous URI: query overrides (hostaddr/service/dbname)
    # and libpq keyword DSNs must not bypass the exact host/database boundary.
    try:
        parsed = urlsplit(dsn)
        if (
            parsed.scheme not in {'postgresql', 'postgres'}
            or parsed.hostname != EXPECTED_REVIEW_SEED_HOST
            or parsed.port != EXPECTED_REVIEW_SEED_PORT
            or parsed.path != f'/{EXPECTED_REVIEW_DATABASE_NAME}'
            or parsed.query
            or parsed.fragment
        ):
            raise ReviewSeedError('review seed requires the exact loopback Review Lab database target')
        return validate_test_db_target(dsn, source='review-v3-seed')
    except (ValueError, DbIsolationError) as exc:
        raise ReviewSeedError('review seed refused an unsafe database target') from exc


def seed_review_spatial_pyramid(connection) -> int:
    """Build and CAS-publish canonical density cells, or return the existing sequence."""
    from psycopg import sql

    # The caller uses autocommit. Keep the entire tiny build + publication in
    # one transaction so reconciliation/CAS failures leave no partial pyramid.
    # Only spatial projections are inserted; their lifecycle/FK guards stay on.
    with connection.transaction():
        prior = connection.execute(
            'SELECT spatial_generation_id, publication_sequence '
            'FROM v3_spatial.current_spatial_generation WHERE singleton').fetchone()
        if prior is not None:
            return prior[1]

        canonical = connection.execute(
            'SELECT c.generation_id, g.relation_schema '
            'FROM v3_meta.current_canonical_generation c '
            'JOIN v3_meta.canonical_generation g USING (generation_id) '
            "WHERE c.singleton AND g.lifecycle_state='PUBLISHED'").fetchone()
        if canonical is None or not spatial_builder.SCHEMA_NAME.fullmatch(canonical[1]):
            raise ReviewSeedError('review spatial seed requires a valid published canonical generation')
        canonical_id, schema = canonical
        # Bound the source before running the seven aggregations, even if this
        # disposable database contains an unexpectedly large canonical fixture.
        canonical_count = connection.execute(
            sql.SQL('SELECT count(*) FROM (SELECT 1 FROM {}.systems LIMIT %s) AS bounded_systems')
            .format(sql.Identifier(schema)),
            (MAX_REVIEW_SPATIAL_SYSTEMS + 1,)).fetchone()[0]
        if not 0 < canonical_count <= MAX_REVIEW_SPATIAL_SYSTEMS:
            raise ReviewSeedError('review spatial seed requires a nonempty bounded canonical fixture')

        spatial_builder.register_cell_levels(connection, REVIEW_PYRAMID_VERSION)
        spatial_id = connection.execute(
            'INSERT INTO v3_spatial.spatial_generation '
            '(canonical_generation_id, pyramid_version, expected_systems) '
            'VALUES (%s,%s,%s) RETURNING spatial_generation_id',
            (canonical_id, REVIEW_PYRAMID_VERSION, canonical_count)).fetchone()[0]
        per_level = spatial_builder.build_all_levels(
            connection, spatial_generation_id=spatial_id, version=REVIEW_PYRAMID_VERSION)
        # build_receipt reconciles every registered level against the actual
        # canonical count and fails closed before mark_pyramid_ready can run.
        receipt = spatial_builder.build_receipt(
            connection, spatial_generation_id=spatial_id, version=REVIEW_PYRAMID_VERSION,
            canonical_count=canonical_count, per_level=per_level)
        spatial_builder.mark_pyramid_ready(
            connection, spatial_generation_id=spatial_id, version=REVIEW_PYRAMID_VERSION,
            receipt=receipt)
        # The observed pointer was empty. CAS must still expect (None, 0) so a
        # concurrent publication fails instead of being overwritten. Argument 4
        # is the pinned canonical id, not the pyramid version or its sequence.
        return connection.execute(
            'SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)',
            (spatial_id, None, 0, canonical_id, 'review-seed',
             'interim review v3 density pyramid')).fetchone()[0]


def main() -> int:
    import psycopg

    try:
        target = validate_review_seed_target(os.environ.get('DATABASE_URL', ''))
        with psycopg.connect(target.dsn, autocommit=True) as connection:
            database = connection.execute('SELECT current_database()').fetchone()[0]
            if database != EXPECTED_REVIEW_DATABASE_NAME:
                raise ReviewSeedError('review seed connected to an unexpected database')
            sequence = seed_cypress_v3_generation(connection)
            seed_review_spatial_pyramid(connection)
    except Exception as exc:
        # Driver/build exceptions can contain connection strings. Preserve a
        # useful failure category without logging credentials or raw exceptions.
        print(f'Review V3 generation seed failed ({type(exc).__name__}).', file=sys.stderr)
        return 1
    print(f'INTERIM Review Lab V3 published generation sequence={sequence}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
