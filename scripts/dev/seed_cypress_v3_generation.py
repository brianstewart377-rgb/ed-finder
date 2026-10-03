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
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from domain.ratings_v4_canonical import load_source_fixture  # noqa: E402
from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical  # noqa: E402
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk)
import scripts.v3_system_archetype as archetype_builder  # noqa: E402
from scripts.v3_system_search import (  # noqa: E402
    build_available as search_build_available,
    register_product as search_register_product,
    validate_product as search_validate_product)

FIXTURE_DIR = ROOT / 'tests/fixtures/cypress_v3_sources'

# The Cypress edfinder database is built from sql/migration-manifest.txt, which
# lists ONLY legacy sql/*.sql -- it has no V3 schema at all. So the seed brings
# up the V3 baseline + the exact derived-build migration set that
# test_local_search_v3.py's fixture proves is sufficient ({001} + these five).
# Apply each required migration ONLY if the object it creates is still missing.
# Two live shapes must both work: (a) the Cypress edfinder DB with NO V3 schema,
# and (b) a DB where the account-browser seed already ran derive_entries
# (001-006/008/009/012 present, but NOT the Finder migrations 010/011). A flat
# "apply the derived set" list would re-run 003/004/006 in case (b) and error,
# so probe-then-apply instead. (migration file, probe true-when-already-applied.)
_MIGRATION_PROBES: tuple[tuple[str, str], ...] = (
    ('001_v3_baseline.sql',
     "SELECT to_regnamespace('v3_meta') IS NOT NULL"),
    ('003_ratings_v4_derived.sql',
     "SELECT to_regclass('v3_derived.system_rating_vector') IS NOT NULL"),
    ('004_v3_search_spatial_clusters.sql',
     "SELECT to_regclass('v3_derived.system_search') IS NOT NULL"),
    ('006_v3_derived_product_lifecycle.sql',
     "SELECT to_regclass('v3_meta.derived_product') IS NOT NULL"),
    ('010_v3_system_search_body_type_counts.sql',
     "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
     "WHERE table_schema='v3_derived' AND table_name='system_search' "
     "AND column_name='elw_count')"),
    ('011_v3_system_archetype.sql',
     "SELECT to_regclass('v3_derived.system_archetype_summary') IS NOT NULL"),
)

# Mirrors tests/test_local_search_v3.py::_ratings_generation (chunk_size=4). The
# curated fixture is tiny (one chunk), but the loop keeps the seed correct for
# any fixture up to MAX_CHUNK_SYSTEMS.
CHUNK_SIZE = 4


def _published_sequence(connection) -> int | None:
    row = connection.execute(
        'SELECT publication_sequence FROM v3_meta.current_derived_generation '
        'WHERE singleton').fetchone()
    return row[0] if row else None


def _ensure_migrations(connection) -> None:
    for name, probe in _MIGRATION_PROBES:
        if not connection.execute(probe).fetchone()[0]:
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())


def seed_cypress_v3_generation(connection, fixture_dir: Path = FIXTURE_DIR) -> int:
    """Build + publish the curated V3 derived generation. Idempotent: if a
    published derived generation already exists, returns its sequence without
    republishing. Returns the derived publication sequence (1 on first publish).
    """
    _ensure_migrations(connection)
    existing = _published_sequence(connection)
    if existing is not None:
        return existing

    canonical, metadata, payloads = load_source_fixture(fixture_dir)
    bootstrap_published_canonical(connection, canonical, metadata)

    snapshot = CanonicalSnapshot.pin(connection)
    key = 'cypress_v3_' + uuid4().hex[:16]
    generation_id = create_generation(connection, snapshot, key)

    # write_chunk needs the REAL source records (id64 + bodies) so
    # adapt_retained_chunk's source/canonical body-inventory check passes;
    # id-only records would fail it for any system that has bodies.
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), CHUNK_SIZE)):
        chunk = records[start:start + CHUNK_SIZE]
        chunk_canonical = snapshot.export_chunk(connection, [record['id64'] for record in chunk])
        assert write_chunk(connection, generation_id, ordinal, chunk_canonical,
                           snapshot.metadata, chunk)

    search_generation, _, search_manifest_sha = search_register_product(connection, key)
    search_build_available(connection, search_generation, search_manifest_sha)
    archetype_generation, _, archetype_manifest_sha = archetype_builder.register_product(connection, key)
    archetype_builder.build_available(connection, archetype_generation, archetype_manifest_sha)

    eof_receipt = {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    }
    seal_source(connection, generation_id, eof_receipt)
    assert validate_generation(connection, generation_id)['status'] == 'VERIFIED'
    assert search_validate_product(
        connection, search_generation, search_manifest_sha)['status'] == 'VERIFIED'
    assert archetype_builder.validate_product(
        connection, archetype_generation, archetype_manifest_sha)['status'] == 'VERIFIED'

    return connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
        (generation_id, None, 0, snapshot.generation_id, snapshot.publication_sequence,
         'cypress-seed', 'cypress v3 finder journey')).fetchone()[0]


def main() -> int:
    import psycopg

    dsn = os.environ['DATABASE_URL']
    with psycopg.connect(dsn, autocommit=True) as connection:
        sequence = seed_cypress_v3_generation(connection)
    print(f'cypress v3 published generation sequence={sequence}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
