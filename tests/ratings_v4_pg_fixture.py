"""Original V3 schema and retained cohort, in a newly created disposable database."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest


@contextmanager
def canonical_database():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from domain.ratings_v4_canonical import load_source_fixture

    dsn = os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL')
    if not dsn:
        pytest.skip('isolated PostgreSQL validation URL not set')
    settings = conninfo_to_dict(dsn)
    if (settings.get('host') not in {'127.0.0.1', 'localhost'} or
            settings.get('dbname') != 'ratings_v4_validation'):
        raise ValueError('canonical fixture requires the local ratings_v4_validation service')
    database = 'v4_test_' + uuid4().hex
    root = Path(__file__).resolve().parents[1]
    canonical, metadata, payloads = load_source_fixture(root / 'tests/fixtures/ratings_v4_sources')
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=database), autocommit=True) as connection:
                connection.execute((root / 'sql/v3/migrations/001_v3_baseline.sql').read_text())

                def insert(schema, table, rows):
                    relation = sql.Identifier(schema, table)
                    for row in rows:
                        connection.execute(sql.SQL('INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{}, %s::jsonb)').format(
                            relation, relation), (json.dumps(row),))

                with connection.transaction():
                    insert('v3_source', 'source', [metadata['source']])
                    connection.execute('''INSERT INTO v3_source.source_rights_policy(
                        rights_policy_id,source_id,policy_version,rights_class,retention_class,effective_at)
                        VALUES (1,40,'test-fixture','CANONICAL_ELIGIBLE','TEST_ONLY',now())''')
                    insert('v3_source', 'source_artifact', [metadata['artifact']])
                    insert('v3_source', 'source_run', [metadata['run']])
                    generation = uuid4()
                    schema = canonical['canonical_schema']
                    connection.execute('''INSERT INTO v3_meta.canonical_generation(
                        generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id)
                        VALUES (%s,%s,%s,%s,%s)''',
                        (generation, schema.removeprefix('v3_gen_'), schema, bytes(32), metadata['run']['source_run_id']))
                    connection.execute('SELECT v3_meta.create_canonical_generation_relations(%s)', (generation,))
                    connection.execute('''INSERT INTO v3_meta.canonical_generation_input(
                        generation_id,input_ordinal,source_id,source_run_id,artifact_id,input_role)
                        VALUES (%s,0,40,%s,%s,'TEST_FIXTURE')''',
                        (generation, metadata['run']['source_run_id'], metadata['artifact']['artifact_id']))
                    for extra in canonical['extras']:
                        if extra['schema'] == 'v3_vocab':
                            insert('v3_vocab', extra['relation'], extra['rows'])
                    insert(schema, 'systems', canonical['systems'])
                    insert(schema, 'bodies', canonical['bodies'])
                    for extra in canonical['extras']:
                        if extra['schema'] == schema:
                            insert(schema, extra['relation'], extra['rows'])
                    receipt = {'systems': len(canonical['systems']), 'bodies': len(canonical['bodies'])}
                    connection.execute('SELECT v3_meta.finalize_canonical_generation(%s,%s::jsonb)',
                                       (generation, json.dumps(receipt)))
                    connection.execute('SELECT v3_meta.publish_canonical_generation(%s,%s,%s)',
                                       (generation, 'disposable-test', 'fixture'))
                yield connection, canonical, metadata, payloads
        finally:
            # Only the random database created by this context can be removed.
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
