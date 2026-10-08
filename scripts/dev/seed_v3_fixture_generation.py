"""Publish a fixture-backed V3 derived generation."""
from __future__ import annotations

from pathlib import Path
import re
import sys
from uuid import uuid4

from psycopg import sql

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
GENERATION_KEY_MAX_LENGTH = 63
GENERATION_KEY_SUFFIX_LENGTH = 16
GENERATION_KEY_PREFIX_MAX_LENGTH = GENERATION_KEY_MAX_LENGTH - GENERATION_KEY_SUFFIX_LENGTH
CANONICAL_SCHEMA = re.compile(r'^v3_gen_[a-z][a-z0-9_]{0,30}$')


def _published_generation(connection):
    return connection.execute(
        'SELECT c.publication_sequence, d.generation_key, d.canonical_generation_id '
        'FROM v3_meta.current_derived_generation c '
        'JOIN v3_meta.derived_generation d USING (derived_generation_id) '
        'WHERE c.singleton').fetchone()


def _canonical_system_id64s(connection, canonical_generation_id) -> set[int]:
    row = connection.execute(
        'SELECT relation_schema FROM v3_meta.canonical_generation WHERE generation_id=%s',
        (canonical_generation_id,),
    ).fetchone()
    if row is None or CANONICAL_SCHEMA.fullmatch(str(row[0])) is None:
        raise RuntimeError('published derived generation has an unsafe canonical schema')
    return {
        result[0]
        for result in connection.execute(
            sql.SQL('SELECT id64 FROM {}').format(sql.Identifier(row[0], 'systems'))
        ).fetchall()
    }


def _owned_published_sequence(
    connection,
    published_generation,
    fixture_dir: Path,
    generation_key_prefix: str,
) -> int:
    sequence, generation_key, canonical_generation_id = published_generation
    key_pattern = re.compile(
        re.escape(generation_key_prefix) + rf'[0-9a-f]{{{GENERATION_KEY_SUFFIX_LENGTH}}}'
    )
    if key_pattern.fullmatch(generation_key) is None:
        raise RuntimeError('published derived generation is not owned by the requested fixture')

    canonical, _, _ = load_source_fixture(fixture_dir)
    fixture_system_id64s = {system['id64'] for system in canonical['systems']}
    if _canonical_system_id64s(connection, canonical_generation_id) != fixture_system_id64s:
        raise RuntimeError('published derived generation is not owned by the requested fixture')
    return sequence


def _ensure_migrations(connection) -> None:
    for name, probe in _MIGRATION_PROBES:
        if not connection.execute(probe).fetchone()[0]:
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())


def seed_v3_fixture_generation(
    connection,
    fixture_dir: Path,
    *,
    generation_key_prefix: str,
    publication_actor: str,
    publication_note: str,
) -> int:
    """Build and publish a fixture-backed V3 derived generation."""
    string_arguments = {
        'generation_key_prefix': generation_key_prefix,
        'publication_actor': publication_actor,
        'publication_note': publication_note,
    }
    for name, value in string_arguments.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} must be a non-empty string')
    if re.fullmatch(r'[a-z][a-z0-9_]*_', generation_key_prefix) is None:
        raise ValueError('generation_key_prefix must match ^[a-z][a-z0-9_]*_$')
    if len(generation_key_prefix) > GENERATION_KEY_PREFIX_MAX_LENGTH:
        raise ValueError(
            f'generation_key_prefix must be at most {GENERATION_KEY_PREFIX_MAX_LENGTH} characters'
        )

    _ensure_migrations(connection)
    existing = _published_generation(connection)
    if existing is not None:
        return _owned_published_sequence(
            connection, existing, fixture_dir, generation_key_prefix
        )

    canonical, metadata, payloads = load_source_fixture(fixture_dir)
    bootstrap_published_canonical(connection, canonical, metadata)

    snapshot = CanonicalSnapshot.pin(connection)
    key = generation_key_prefix + uuid4().hex[:GENERATION_KEY_SUFFIX_LENGTH]
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
         publication_actor, publication_note)).fetchone()[0]
