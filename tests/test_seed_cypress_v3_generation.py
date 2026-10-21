"""Task 3: the Cypress seed publishes a real V3 derived generation and the
journey id64s are exposed through ``v3_app.system_search``; F4a: the Product
fixture-output contract pins the archetype results Product E2E may assert.

Skips unless the isolated local PostgreSQL validation service is configured
(see reference_local_test_database)."""
from __future__ import annotations

import inspect
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
ARCHETYPE_KEYS = (
    'paradise',
    'mining_hub',
    'manufacturing_hub',
    'megacomplex',
    'research_hub',
    'stronghold',
    'population_capital',
    'flexible',
)


def test_neutral_seed_probes_wide_archetype_table_and_summary_view():
    from scripts.dev.seed_v3_fixture_generation import _MIGRATION_PROBES

    migration, probe = next(
        entry for entry in _MIGRATION_PROBES
        if entry[0] == '011_v3_system_archetype.sql'
    )
    assert migration == '011_v3_system_archetype.sql'
    assert "table_schema='v3_derived' AND table_name='system_archetype'" in probe
    assert "table_type='BASE TABLE'" in probe
    assert "table_schema='v3_app' AND table_name='system_archetype_summary'" in probe
    assert 'information_schema.views' in probe
    assert 'v3_derived.system_archetype_summary' not in probe
    assert _MIGRATION_PROBES[-1] == (
        '015_v3_derived_product_publication.sql',
        "SELECT to_regclass('v3_meta.derived_product_publication_audit') IS NOT NULL",
    )


def test_neutral_seed_publishes_products_atomically_in_dependency_order():
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation

    source = inspect.getsource(seed_v3_fixture_generation)
    transaction = source.index('with connection.transaction():')
    generation = source.index('publish_derived_generation', transaction)
    search = source.index("(generation_id, 'system_search', publication_actor)", generation)
    archetype = source.index("(generation_id, 'system_archetype', publication_actor)", search)
    assert transaction < generation < search < archetype


def test_cypress_wrapper_passes_fixture_and_publication_metadata(monkeypatch, tmp_path):
    from scripts.dev import seed_cypress_v3_generation as seed

    connection = object()
    calls = []

    def publish(conn, fixture_dir, **metadata):
        calls.append((conn, fixture_dir, metadata))
        return 17

    monkeypatch.setattr(seed, 'seed_v3_fixture_generation', publish)

    assert seed.seed_cypress_v3_generation(connection, tmp_path) == 17
    assert calls == [
        (
            connection,
            tmp_path,
            {
                'generation_key_prefix': 'cypress_v3_',
                'publication_actor': 'cypress-seed',
                'publication_note': 'cypress v3 finder journey',
            },
        ),
    ]


@pytest.mark.parametrize(
    ('generation_key_prefix', 'publication_actor', 'publication_note'),
    [
        ('', 'actor', 'note'),
        ('Cypress-v3_', 'actor', 'note'),
        ('fixture_', '', 'note'),
        ('fixture_', 'actor', ''),
    ],
)
def test_neutral_seed_rejects_invalid_publication_metadata_before_connection_access(
    generation_key_prefix,
    publication_actor,
    publication_note,
    tmp_path,
):
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation

    class Connection:
        def execute(self, *_args, **_kwargs):
            pytest.fail('connection touched before publication metadata validation')

    with pytest.raises(ValueError):
        seed_v3_fixture_generation(
            Connection(),
            tmp_path,
            generation_key_prefix=generation_key_prefix,
            publication_actor=publication_actor,
            publication_note=publication_note,
        )


def test_neutral_seed_accepts_maximum_length_prefix_before_connection_access(tmp_path):
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation

    class ConnectionAccessed(Exception):
        pass

    class Connection:
        def execute(self, *_args, **_kwargs):
            raise ConnectionAccessed

    prefix = 'a' * 46 + '_'
    assert len(prefix) == 47
    with pytest.raises(ConnectionAccessed):
        seed_v3_fixture_generation(
            Connection(),
            tmp_path,
            generation_key_prefix=prefix,
            publication_actor='actor',
            publication_note='note',
        )


def test_neutral_seed_rejects_too_long_prefix_before_connection_access(tmp_path):
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation

    class Connection:
        def execute(self, *_args, **_kwargs):
            pytest.fail('connection touched before generation_key_prefix validation')

    prefix = 'a' * 47 + '_'
    assert len(prefix) == 48
    with pytest.raises(ValueError, match='generation_key_prefix'):
        seed_v3_fixture_generation(
            Connection(),
            tmp_path,
            generation_key_prefix=prefix,
            publication_actor='actor',
            publication_note='note',
        )


@pytest.mark.parametrize(
    ('argument', 'publication_actor', 'publication_note'),
    [
        ('publication_actor', ' \t\n', 'note'),
        ('publication_note', 'actor', ' \t\n'),
    ],
)
def test_neutral_seed_rejects_whitespace_publication_metadata_before_connection_access(
    argument,
    publication_actor,
    publication_note,
    tmp_path,
):
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation

    class Connection:
        def execute(self, *_args, **_kwargs):
            pytest.fail(f'connection touched before {argument} validation')

    with pytest.raises(ValueError, match=argument):
        seed_v3_fixture_generation(
            Connection(),
            tmp_path,
            generation_key_prefix='fixture_',
            publication_actor=publication_actor,
            publication_note=publication_note,
        )


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
                product_rows = conn.execute(
                    'SELECT p.product_code, p.lifecycle_state, p.published_at '
                    'FROM v3_meta.derived_product p '
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id) '
                    'WHERE p.product_code = ANY(%s)',
                    (['system_search', 'system_archetype'],),
                ).fetchall()
                products = {
                    code: (state, published_at)
                    for code, state, published_at in product_rows
                }
                assert set(products) == {'system_search', 'system_archetype'}
                assert all(state == 'READY' for state, _ in products.values())
                assert all(published_at is not None for _, published_at in products.values())
                publication_audits = conn.execute(
                    'SELECT a.product_code,a.published_at,a.actor '
                    'FROM v3_meta.derived_product_publication_audit a '
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id) '
                    'ORDER BY a.product_code'
                ).fetchall()
                assert [row[0] for row in publication_audits] == [
                    'system_archetype', 'system_search',
                ]
                assert all(
                    published_at == products[code][1] and actor == 'cypress-seed'
                    for code, published_at, actor in publication_audits
                )
                receipts = conn.execute(
                    "SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p "
                    'JOIN v3_meta.current_derived_generation c USING (derived_generation_id) '
                    'WHERE p.product_code = ANY(%s)',
                    (['system_search', 'system_archetype'],),
                ).fetchall()
                assert receipts == [('VERIFIED',), ('VERIFIED',)]
                wide_columns = ', '.join(
                    f'{key}_score, {key}_tier, {key}_confidence_ppm, '
                    f'{key}_weighted_e4'
                    for key in ARCHETYPE_KEYS
                )
                wide_rows = conn.execute(
                    f'SELECT system_id64, {wide_columns} '
                    'FROM v3_derived.system_archetype'
                ).fetchall()
                assert {row[0] for row in wide_rows} == exposed
                assert all(all(value is not None for value in row[1:]) for row in wide_rows)
                assert conn.execute(
                    'SELECT COUNT(*) FROM v3_app.system_archetype_summary'
                ).fetchone() == (len(exposed),)
                assert conn.execute(
                    "SELECT to_regclass('v3_derived.system_archetype_summary') IS NULL"
                ).fetchone() == (True,)
                if full_review_lineage:
                    assert conn.execute("SELECT to_regclass('v3_private.watchlist') IS NOT NULL").fetchone()[0]
                    assert conn.execute("SELECT to_regclass('public.systems') IS NULL").fetchone()[0]
                # idempotent: a second call does not republish.
                assert seed_cypress_v3_generation(conn) == 1
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_idempotence_requires_fixture_ownership():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation
    from tests.helpers.db_isolation import validate_test_db_target

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_ownership_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1
                assert seed_cypress_v3_generation(conn) == 1

                review_fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'

                def assert_original_publication_unchanged():
                    assert conn.execute(
                        'SELECT COUNT(*) FROM v3_meta.derived_generation'
                    ).fetchone()[0] == 1
                    assert conn.execute(
                        'SELECT publication_sequence '
                        'FROM v3_meta.current_derived_generation WHERE singleton'
                    ).fetchone() == (1,)

                with pytest.raises(RuntimeError):
                    seed_v3_fixture_generation(
                        conn,
                        review_fixture,
                        generation_key_prefix='review_lab_v3_',
                        publication_actor='review-lab-seed',
                        publication_note='review lab v3 fixture',
                    )
                assert_original_publication_unchanged()

                with pytest.raises(RuntimeError):
                    seed_v3_fixture_generation(
                        conn,
                        review_fixture,
                        generation_key_prefix='cypress_v3_',
                        publication_actor='review-lab-seed',
                        publication_note='review lab v3 fixture',
                    )
                assert_original_publication_unchanged()
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


def test_bounded_system_count_mismatch_does_not_select_system_rows():
    from scripts.dev.seed_v3_fixture_generation import _bounded_canonical_rows

    class Result:
        def fetchone(self):
            return (4,)

    class Connection:
        def __init__(self):
            self.queries = []

        def execute(self, query, params=None):
            rendered = query.as_string() if hasattr(query, 'as_string') else query
            self.queries.append((rendered, params))
            return Result()

    connection = Connection()
    with pytest.raises(RuntimeError, match='canonical systems count mismatch'):
        _bounded_canonical_rows(
            connection,
            'v3_gen_fixture',
            'systems',
            ('id64', 'name'),
            3,
        )

    assert connection.queries == [
        (
            'SELECT count(*) FROM (SELECT 1 FROM '
            '"v3_gen_fixture"."systems" LIMIT %s) AS bounded',
            (4,),
        ),
    ]
    assert not any(
        'SELECT "id64", "name"' in query for query, _params in connection.queries
    )


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_idempotence_rejects_same_ids_with_different_content(tmp_path):
    from hashlib import sha256
    import json
    import shutil

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation
    from tests.helpers.db_isolation import validate_test_db_target

    fixture = tmp_path / 'cypress_v3_sources'
    shutil.copytree(ROOT / 'tests/fixtures/cypress_v3_sources', fixture)
    canonical_path = fixture / 'canonical.json'
    canonical = json.loads(canonical_path.read_bytes())
    canonical['systems'][0]['name'] += ' changed'
    canonical_path.write_text(
        json.dumps(canonical, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    manifest_path = fixture / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['files_sha256'] = {
        name: sha256((fixture / name).read_bytes()).hexdigest()
        for name in manifest['files_sha256']
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_content_mismatch_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1

                with pytest.raises(RuntimeError, match='canonical systems content mismatch'):
                    seed_v3_fixture_generation(
                        conn,
                        fixture,
                        generation_key_prefix='cypress_v3_',
                        publication_actor='cypress-seed',
                        publication_note='cypress v3 finder journey',
                    )

                assert conn.execute(
                    'SELECT COUNT(*) FROM v3_meta.derived_generation'
                ).fetchone() == (1,)
                assert conn.execute(
                    'SELECT publication_sequence '
                    'FROM v3_meta.current_derived_generation WHERE singleton'
                ).fetchone() == (1,)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_idempotence_rejects_moved_canonical_pointer():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from domain.ratings_v4_canonical import load_source_fixture
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical
    from tests.helpers.db_isolation import validate_test_db_target

    class ReusedFixtureSourceConnection:
        """Reuse the fixtures' shared source ledger while bootstrapping generation two."""

        def __init__(self, connection):
            self.connection = connection

        def transaction(self):
            return self.connection.transaction()

        def execute(self, query, params=None):
            rendered = (
                query.as_string(self.connection)
                if hasattr(query, 'as_string')
                else query
            )
            normalized = ' '.join(rendered.split())
            reused_inserts = (
                'INSERT INTO "v3_source"."source" ',
                'INSERT INTO "v3_source"."source_artifact" ',
                'INSERT INTO "v3_source"."source_run" ',
                'INSERT INTO v3_source.source_rights_policy(',
            )
            if normalized.startswith(reused_inserts):
                return None
            return self.connection.execute(query, params)

    review_fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    review_canonical, review_metadata, _ = load_source_fixture(review_fixture)
    original_schema = review_canonical['canonical_schema']
    moved_schema = 'v3_gen_review_lab_pointer_moved'
    review_canonical['canonical_schema'] = moved_schema
    review_canonical['extras'] = [
        {
            **extra,
            'schema': moved_schema if extra['schema'] == original_schema else extra['schema'],
        }
        for extra in review_canonical['extras']
        if extra['schema'] != 'v3_vocab'
    ]

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_pointer_mismatch_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1
                bootstrap_published_canonical(
                    ReusedFixtureSourceConnection(conn),
                    review_canonical,
                    review_metadata,
                )

                with pytest.raises(RuntimeError, match='canonical pointer mismatch'):
                    seed_cypress_v3_generation(conn)

                assert conn.execute(
                    'SELECT COUNT(*) FROM v3_meta.derived_generation'
                ).fetchone() == (1,)
                assert conn.execute(
                    'SELECT publication_sequence '
                    'FROM v3_meta.current_derived_generation WHERE singleton'
                ).fetchone() == (1,)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_records_fixture_digest_in_publication_audit():
    from hashlib import sha256

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from tests.helpers.db_isolation import validate_test_db_target

    fixture = ROOT / 'tests/fixtures/cypress_v3_sources'
    digest = sha256((fixture / 'manifest.json').read_bytes()).hexdigest()
    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_digest_audit_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1
                assert conn.execute(
                    'SELECT actor, reason FROM v3_meta.derived_publication_audit '
                    'WHERE publication_sequence=1'
                ).fetchone() == (
                    'cypress-seed',
                    f'cypress v3 finder journey [fixture_manifest_sha256={digest}]',
                )
                assert seed_cypress_v3_generation(conn) == 1
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_idempotence_rejects_changed_body_fixture_digest(tmp_path):
    from hashlib import sha256
    import json
    import shutil

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation
    from tests.helpers.db_isolation import validate_test_db_target

    fixture = tmp_path / 'cypress_v3_sources'
    shutil.copytree(ROOT / 'tests/fixtures/cypress_v3_sources', fixture)
    canonical_path = fixture / 'canonical.json'
    canonical = json.loads(canonical_path.read_bytes())
    canonical['bodies'][0]['distance_from_arrival_ls'] += 1
    canonical_path.write_text(
        json.dumps(canonical, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    manifest_path = fixture / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['files_sha256'] = {
        name: sha256((fixture / name).read_bytes()).hexdigest()
        for name in manifest['files_sha256']
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_body_digest_mismatch_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1

                with pytest.raises(RuntimeError, match='fixture digest mismatch'):
                    seed_v3_fixture_generation(
                        conn,
                        fixture,
                        generation_key_prefix='cypress_v3_',
                        publication_actor='cypress-seed',
                        publication_note='cypress v3 finder journey',
                    )

                assert conn.execute(
                    'SELECT COUNT(*) FROM v3_meta.derived_generation'
                ).fetchone() == (1,)
                assert conn.execute(
                    'SELECT publication_sequence '
                    'FROM v3_meta.current_derived_generation WHERE singleton'
                ).fetchone() == (1,)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_idempotence_rejects_different_publication_actor():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from scripts.dev.seed_v3_fixture_generation import seed_v3_fixture_generation
    from tests.helpers.db_isolation import validate_test_db_target

    fixture = ROOT / 'tests/fixtures/cypress_v3_sources'
    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_actor_mismatch_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1

                with pytest.raises(RuntimeError, match='fixture digest mismatch'):
                    seed_v3_fixture_generation(
                        conn,
                        fixture,
                        generation_key_prefix='cypress_v3_',
                        publication_actor='someone-else',
                        publication_note='cypress v3 finder journey',
                    )
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))


# ---------------------------------------------------------------------------
# Product fixture-output contract (F4 design section 7, PR F4a)
# ---------------------------------------------------------------------------
# docs/superpowers/specs/2026-10-10-v3-finder-f4-archetype-ui-design.md asks
# for a PostgreSQL contract that builds the committed Product E2E corpus with
# the real seed (Ratings V4 encoder -> F1 search builder -> F2d wide archetype
# builder -> product publication) and pins, for all three systems, the
# primary/secondary classification, Best Colony Potential, every
# selected-archetype score/tier, confidence and completeness -- and that proves
# the Flexible / minimum-tier-B journey admits all three in a fixed order
# before any Cypress test copies exact values. A model, encoder or fixture
# change that moves any of these numbers must update this table explicitly;
# it can no longer surface first as a silent screenshot change.
HD_38179 = 158872029
PRODUCT_FIXTURE_NAMES = {
    LOSSLESS: 'V3 Lossless Reach',
    ACHENAR: 'Achenar',
    HD_38179: 'HD 38179',
}

# Stored wide row per system: key -> (score, tier, confidence_ppm, weighted_e4).
EXPECTED_WIDE_ARCHETYPES = {
    LOSSLESS: {
        'paradise': (64, 'B', 957215, 397037),
        'mining_hub': (68, 'B', 453984, 200074),
        'manufacturing_hub': (67, 'B', 623838, 270887),
        'megacomplex': (68, 'B', 453984, 200074),
        'research_hub': (82, 'A', 1000000, 531442),
        'stronghold': (63, 'B', 893735, 364915),
        'population_capital': (75, 'B', 957215, 465278),
        'flexible': (100, 'S', 866514, 561588),
    },
    ACHENAR: {
        'paradise': (58, 'C', 914970, 337302),
        'mining_hub': (69, 'B', 441825, 193769),
        'manufacturing_hub': (72, 'B', 638315, 292113),
        'megacomplex': (72, 'B', 441825, 202193),
        'research_hub': (73, 'B', 973359, 451627),
        'stronghold': (74, 'B', 750958, 353209),
        'population_capital': (67, 'B', 914970, 389642),
        'flexible': (100, 'S', 848637, 539394),
    },
    HD_38179: {
        'paradise': (0, 'D', 678747, 0),
        'mining_hub': (13, 'D', 522067, 42825),
        'manufacturing_hub': (7, 'D', 514580, 22729),
        'megacomplex': (15, 'D', 514580, 48705),
        'research_hub': (0, 'D', 1000000, 0),
        'stronghold': (57, 'C', 514580, 185079),
        'population_capital': (0, 'D', 678747, 0),
        'flexible': (75, 'B', 803002, 380021),
    },
}

# Summary per system: (primary, secondary, best_colony_potential, best_tier,
# archetype_confidence_ppm, completeness_ppm). archetype_confidence is the
# primary/secondary classification separation, min(2 * (first - second) /
# first, 1): V3 Lossless Reach (100 - 82) -> 0.36, Achenar (100 - 74) -> 0.52,
# HD 38179 (75 - 57) / 75 -> 0.48.
EXPECTED_SUMMARY = {
    LOSSLESS: ('flexible', 'research_hub', 100, 'S', 360000, 648100),
    ACHENAR: ('flexible', 'stronghold', 100, 'S', 520000, 635600),
    HD_38179: ('flexible', 'stronghold', 75, 'B', 480000, 631000),
}

# Search projection evidence used by the Any-mode badge: (confidence, completeness).
EXPECTED_SEARCH_EVIDENCE = {
    LOSSLESS: (0.8241, 0.6481),
    ACHENAR: (0.8178, 0.6356),
    HD_38179: (0.8155, 0.631),
}

# `GET /api/archetypes/rankings?archetype=<key>&min_score=60` page order (the
# canonical `<key>_weighted_e4 DESC, system_id64 ASC` window order). Flexible
# is the only archetype whose B floor admits all three Product systems, so it
# is the only key that can drive the three one-row pages of the E2E journey.
EXPECTED_B_FLOOR_ORDER = {
    'paradise': (LOSSLESS,),
    'mining_hub': (LOSSLESS, ACHENAR),
    'manufacturing_hub': (ACHENAR, LOSSLESS),
    'megacomplex': (ACHENAR, LOSSLESS),
    'research_hub': (LOSSLESS, ACHENAR),
    'stronghold': (LOSSLESS, ACHENAR),
    'population_capital': (LOSSLESS, ACHENAR),
    'flexible': (LOSSLESS, ACHENAR, HD_38179),
}

# The Flexible B journey exactly as Product Cypress will assert it (section 7
# step 4): selected score/tier, selected-fit confidence, completeness,
# primary/secondary, classification confidence and Best Colony Potential.
EXPECTED_FLEXIBLE_B_ROWS = (
    {
        'id64': LOSSLESS, 'name': 'V3 Lossless Reach', 'score': 100.0, 'tier': 'S',
        'selected_archetype': 'flexible', 'confidence': 0.8665, 'completeness': 0.6481,
        'primary_archetype': 'flexible', 'secondary_archetype': 'research_hub',
        'archetype_confidence': 0.36, 'overall_development_potential': 100.0,
    },
    {
        'id64': ACHENAR, 'name': 'Achenar', 'score': 100.0, 'tier': 'S',
        'selected_archetype': 'flexible', 'confidence': 0.8486, 'completeness': 0.6356,
        'primary_archetype': 'flexible', 'secondary_archetype': 'stronghold',
        'archetype_confidence': 0.52, 'overall_development_potential': 100.0,
    },
    {
        'id64': HD_38179, 'name': 'HD 38179', 'score': 75.0, 'tier': 'B',
        'selected_archetype': 'flexible', 'confidence': 0.803, 'completeness': 0.631,
        'primary_archetype': 'flexible', 'secondary_archetype': 'stronghold',
        'archetype_confidence': 0.48, 'overall_development_potential': 75.0,
    },
)

# Explore's Any-mode galaxy-wide request (the exact disabled-gate body the
# F4a regression deep-compares) and its development order.
ANY_EXPLORE_BODY = {'galaxy_wide': True, 'sort_by': 'development', 'size': 24, 'from': 0}
EXPECTED_ANY_ROWS = (
    {
        'id64': LOSSLESS, 'name': 'V3 Lossless Reach',
        'archetype_score': 100.0, 'archetype_tier': 'S',
        'primary_archetype': 'flexible', 'secondary_archetype': 'research_hub',
        'archetype_confidence': 0.36, 'overall_development_potential': 100.0,
        'confidence': 0.8241, 'completeness': 0.6481,
    },
    {
        'id64': ACHENAR, 'name': 'Achenar',
        'archetype_score': 100.0, 'archetype_tier': 'S',
        'primary_archetype': 'flexible', 'secondary_archetype': 'stronghold',
        'archetype_confidence': 0.52, 'overall_development_potential': 100.0,
        'confidence': 0.8178, 'completeness': 0.6356,
    },
    {
        'id64': HD_38179, 'name': 'HD 38179',
        'archetype_score': 75.0, 'archetype_tier': 'B',
        'primary_archetype': 'flexible', 'secondary_archetype': 'stronghold',
        'archetype_confidence': 0.48, 'overall_development_potential': 75.0,
        'confidence': 0.8155, 'completeness': 0.631,
    },
)


def test_product_fixture_contract_tables_are_internally_consistent():
    """Pure checks on the pinned tables, independent of PostgreSQL: every pinned
    tier is the API-owned threshold tier of its score, every weighted key is the
    model's integer weighting of score x fit confidence x completeness, the
    summary agrees with the wide row, and each B-floor order is exactly the
    weighted window order over the systems scoring at least 60."""
    from edfinder_api.ranking.profile import TIER_THRESHOLDS
    from shared_contracts.v3_system_archetype_model import weighted_key_e4

    def tier_of(score):
        for tier in ('S', 'A', 'B', 'C'):
            if score >= TIER_THRESHOLDS[tier]:
                return tier
        return 'D'

    assert set(EXPECTED_WIDE_ARCHETYPES) == set(PRODUCT_FIXTURE_NAMES)
    for id64, archetypes in EXPECTED_WIDE_ARCHETYPES.items():
        assert tuple(archetypes) == ARCHETYPE_KEYS
        completeness_ppm = EXPECTED_SUMMARY[id64][5]
        for score, tier, confidence_ppm, weighted in archetypes.values():
            assert tier == tier_of(score)
            assert weighted == weighted_key_e4(score, confidence_ppm, completeness_ppm)
        primary, secondary, best, best_tier, separation_ppm, _ = EXPECTED_SUMMARY[id64]
        assert archetypes[primary][:2] == (best, best_tier)
        assert archetypes[secondary][0] < best
        assert separation_ppm == round(
            min((best - archetypes[secondary][0]) / max(best, 1) * 2, 1.0) * 1_000_000
        )
        assert EXPECTED_SEARCH_EVIDENCE[id64][1] * 1_000_000 == pytest.approx(completeness_ppm)

    for key, order in EXPECTED_B_FLOOR_ORDER.items():
        admitted = [
            id64 for id64, archetypes in EXPECTED_WIDE_ARCHETYPES.items()
            if archetypes[key][0] >= 60
        ]
        assert tuple(sorted(
            admitted,
            key=lambda id64: (-EXPECTED_WIDE_ARCHETYPES[id64][key][3], id64),
        )) == order
    assert [key for key, order in EXPECTED_B_FLOOR_ORDER.items() if len(order) == 3] == [
        'flexible',
    ]
    # Section 3: Manufacturing Hub cannot be the B-floor pagination fixture,
    # because HD 38179 scores 7/D on it.
    assert EXPECTED_WIDE_ARCHETYPES[HD_38179]['manufacturing_hub'][:2] == (7, 'D')
    assert [row['id64'] for row in EXPECTED_FLEXIBLE_B_ROWS] == list(
        EXPECTED_B_FLOOR_ORDER['flexible']
    )


@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
@pytest.mark.asyncio
async def test_seeded_product_fixture_archetype_output_contract(monkeypatch):
    """Seed the committed Product corpus exactly as the Cypress lane does, then
    read it back through the stored projections and through the real ranking
    handlers (`_archetype_rankings_v3` for selected mode, `local_db_search_v3`
    for Any) and compare every field to the pinned tables above."""
    if not os.environ.get('CORS_ORIGINS'):
        monkeypatch.setenv('CORS_ORIGINS', 'https://seed-cypress-v3-contract.invalid')

    import asyncpg
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    from edfinder_api import local_search
    from edfinder_api.routers import archetypes as archetypes_router
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation
    from tests.helpers.db_isolation import validate_test_db_target

    dsn = validate_test_db_target(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']).dsn
    db = 'seed_output_contract_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                assert seed_cypress_v3_generation(conn) == 1

                wide_columns = ', '.join(
                    f'{key}_score, {key}_tier, {key}_confidence_ppm, {key}_weighted_e4'
                    for key in ARCHETYPE_KEYS
                )
                wide = {
                    row[0]: {
                        key: tuple(row[1 + 4 * index:5 + 4 * index])
                        for index, key in enumerate(ARCHETYPE_KEYS)
                    }
                    for row in conn.execute(
                        f'SELECT system_id64, {wide_columns} FROM v3_app.system_archetype'
                    ).fetchall()
                }
                assert wide == EXPECTED_WIDE_ARCHETYPES

                summary = {
                    row[0]: tuple(row[1:])
                    for row in conn.execute(
                        'SELECT system_id64, primary_archetype, secondary_archetype, '
                        'best_colony_potential, best_tier, archetype_confidence_ppm, '
                        'completeness_ppm FROM v3_app.system_archetype'
                    ).fetchall()
                }
                assert summary == EXPECTED_SUMMARY
                view = {
                    row[0]: tuple(row[1:])
                    for row in conn.execute(
                        'SELECT system_id64, primary_archetype, secondary_archetype, '
                        'best_colony_potential, best_tier, archetype_confidence '
                        'FROM v3_app.system_archetype_summary'
                    ).fetchall()
                }
                assert view == {
                    id64: (primary, secondary, best, best_tier, separation_ppm / 1_000_000)
                    for id64, (primary, secondary, best, best_tier, separation_ppm, _)
                    in EXPECTED_SUMMARY.items()
                }

                search = {
                    row[0]: (row[1], (float(row[2]), float(row[3])))
                    for row in conn.execute(
                        'SELECT system_id64, name, confidence, completeness '
                        'FROM v3_app.system_search'
                    ).fetchall()
                }
                assert search == {
                    id64: (PRODUCT_FIXTURE_NAMES[id64], EXPECTED_SEARCH_EVIDENCE[id64])
                    for id64 in PRODUCT_FIXTURE_NAMES
                }

            settings = conninfo_to_dict(dsn)
            pool = await asyncpg.create_pool(
                host=settings.get('host'),
                port=int(settings.get('port', 5432)),
                user=settings.get('user'),
                password=settings.get('password'),
                database=db,
                min_size=1, max_size=2, statement_cache_size=0,
            )
            try:
                async def rankings(key, *, limit=50, offset=0):
                    return await archetypes_router._archetype_rankings_v3(
                        archetype=key, min_score=60, galaxy_region=None,
                        max_distance_ly=None, has_elw=None, min_slots=None,
                        max_contamination=None, limit=limit, offset=offset, pool=pool,
                    )

                for key, order in EXPECTED_B_FLOOR_ORDER.items():
                    page = await rankings(key)
                    assert [row['id64'] for row in page['results']] == list(order), key
                    assert (page['total'], page['count'], page['is_truncated']) == (
                        len(order), len(order), False,
                    ), key
                    for row in page['results']:
                        score, tier, confidence_ppm, _ = EXPECTED_WIDE_ARCHETYPES[row['id64']][key]
                        primary, secondary, best, _, separation_ppm, completeness_ppm = (
                            EXPECTED_SUMMARY[row['id64']]
                        )
                        assert row['name'] == PRODUCT_FIXTURE_NAMES[row['id64']]
                        assert (row['score'], row['tier']) == (float(score), tier), key
                        assert row['selected_archetype'] == key
                        assert row['confidence'] == round(confidence_ppm / 1_000_000, 4), key
                        assert row['completeness'] == pytest.approx(completeness_ppm / 1_000_000)
                        assert (row['primary_archetype'], row['secondary_archetype']) == (
                            primary, secondary,
                        )
                        assert row['archetype_confidence'] == separation_ppm / 1_000_000
                        assert row['overall_development_potential'] == float(best)
                        # Slice 1b has not landed: no ranking row carries the
                        # summary `best_tier`, so F4a/F4b must omit the headline
                        # tier (design section 8, PR F4a).
                        assert 'best_tier' not in row

                flexible = await rankings('flexible')
                assert [
                    {field: row[field] for field in EXPECTED_FLEXIBLE_B_ROWS[0]}
                    for row in flexible['results']
                ] == list(EXPECTED_FLEXIBLE_B_ROWS)

                # The E2E pagination contract: page_size=1 -> wire limit=1 gives
                # three deterministic one-row pages at offsets 0, 1 and 2 over
                # the same window, then an empty page.
                for offset, expected in enumerate(EXPECTED_FLEXIBLE_B_ROWS):
                    page = await rankings('flexible', limit=1, offset=offset)
                    assert [row['id64'] for row in page['results']] == [expected['id64']]
                    assert (page['total'], page['count'], page['is_truncated']) == (3, 1, False)
                past_end = await rankings('flexible', limit=1, offset=3)
                assert (past_end['results'], past_end['total'], past_end['count']) == ([], 3, 0)

                any_page = await local_search.local_db_search_v3(dict(ANY_EXPLORE_BODY), pool)
                assert [
                    {field: row[field] for field in EXPECTED_ANY_ROWS[0]}
                    for row in any_page['results']
                ] == list(EXPECTED_ANY_ROWS)
                assert (any_page['total'], any_page['count']) == (3, 3)
                assert not any('best_tier' in row for row in any_page['results'])
            finally:
                await pool.close()
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(db)))
