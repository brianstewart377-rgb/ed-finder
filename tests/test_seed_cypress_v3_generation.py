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
