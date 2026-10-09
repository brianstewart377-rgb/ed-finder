"""Publish a real V3 derived generation into the Cypress database so the
F3-repointed ``POST /api/local/search`` and ``GET /api/archetypes/rankings``
return 200 for the browser product-journey.

No lifecycle shortcuts: the canonical generation, the derived generation, and
BOTH Finder products (``system_search`` + ``system_archetype``) reach
``VERIFIED`` through the genuine build pipeline and are published via
``v3_meta.publish_derived_generation`` (which refuses anything less). The
source data is the committed, checksum-locked curated fixture
``tests/fixtures/cypress_v3_sources`` (journey id64s). Reuses the exact pipeline
functions the unit tests use (see tests/test_local_search_v3.py).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from scripts.dev.seed_v3_fixture_generation import (  # noqa: E402
    load_source_fixture as load_source_fixture,
    seed_v3_fixture_generation,
)
from tests.helpers.db_isolation import validate_test_db_target  # noqa: E402

FIXTURE_DIR = ROOT / 'tests/fixtures/cypress_v3_sources'


def seed_cypress_v3_generation(connection, fixture_dir: Path = FIXTURE_DIR) -> int:
    """Build + publish the curated V3 derived generation. Idempotent: if a
    published derived generation already exists, returns its sequence without
    republishing. Returns the derived publication sequence (1 on first publish).
    """
    return seed_v3_fixture_generation(
        connection,
        fixture_dir,
        generation_key_prefix='cypress_v3_',
        publication_actor='cypress-seed',
        publication_note='cypress v3 finder journey',
    )


def main() -> int:
    import psycopg

    # Fail closed before opening a mutating connection. This entry point applies
    # Finder migrations and publishes a canonical/derived generation, so it must
    # refuse any non-disposable (production-looking) target rather than trust an
    # arbitrary DATABASE_URL. Mirrors the sibling account-browser seed's guard;
    # CI's localhost Cypress database is allowed (CI=true), a mispointed prod
    # DSN is rejected before any write.
    target = validate_test_db_target(os.environ['DATABASE_URL'], source='cypress-v3-seed')
    with psycopg.connect(target.dsn, autocommit=True) as connection:
        sequence = seed_cypress_v3_generation(connection)
    print(f'cypress v3 published generation sequence={sequence}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
