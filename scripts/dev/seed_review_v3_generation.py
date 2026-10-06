"""INTERIM Review Lab V3 plumbing proof using the proven Cypress builder.

Run host-side in the apps/api test venv, never in the production API image.
TODO(Phase 2): replace the source fixture with purpose-built Review Lab data;
see docs/development/review-lab-v3-redo.md. Publication is idempotent and uses
the genuine canonical, Search and Archetype validation/CAS pipeline.
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
from tests.helpers.db_isolation import DbIsolationError, DbTarget, validate_test_db_target  # noqa: E402

EXPECTED_REVIEW_SEED_HOST = '127.0.0.1'
EXPECTED_REVIEW_SEED_PORT = 55433


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


def main() -> int:
    import psycopg

    try:
        target = validate_review_seed_target(os.environ.get('DATABASE_URL', ''))
        with psycopg.connect(target.dsn, autocommit=True) as connection:
            database = connection.execute('SELECT current_database()').fetchone()[0]
            if database != EXPECTED_REVIEW_DATABASE_NAME:
                raise ReviewSeedError('review seed connected to an unexpected database')
            sequence = seed_cypress_v3_generation(connection)
    except Exception as exc:
        # Driver/build exceptions can contain connection strings. Preserve a
        # useful failure category without logging credentials or raw exceptions.
        print(f'Review V3 generation seed failed ({type(exc).__name__}).', file=sys.stderr)
        return 1
    print(f'INTERIM Review Lab V3 published generation sequence={sequence}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
