"""The disposable V4 persistence contract, exercised on real PostgreSQL 18."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import BodyFact, SystemFacts  # noqa: E402
from scripts.ratings_v4.generation import bootstrap, schema_name, stage, validate  # noqa: E402

pytestmark = pytest.mark.db

@pytest.fixture
def database():
    url = os.getenv('RATINGS_V4_VALIDATION_DATABASE_URL')
    if not url:
        pytest.skip('dedicated RATINGS_V4_VALIDATION_DATABASE_URL required')
    psycopg = pytest.importorskip('psycopg')
    with psycopg.connect(url, autocommit=True) as connection:
        assert connection.info.server_version // 10000 == 18
        schema = schema_name('ratings_v4_validation_' + uuid4().hex)
        bootstrap(connection, schema)
        try:
            yield connection, schema
        finally:
            # This name was locally generated and validated; no caller schema
            # or canonical/production relation can reach this cleanup.
            connection.execute(f'DROP SCHEMA {schema} CASCADE')


def fixture_systems():
    body = BodyFact('rock', 'Rocky', rings=False, biologicals=False,
                    geologicals=False, usable_ground_opportunity=None,
                    feature_provenance={'provenance': 'integration fixture'})
    return {
        1: SystemFacts((body,), body_inventory_complete=True),
        2: SystemFacts((replace(body, usable_ground_opportunity=False),), body_inventory_complete=True),
        3: SystemFacts((replace(body, usable_ground_opportunity=True),), body_inventory_complete=True),
    }


MANIFEST = {'canonical_generation': 'fixture', 'source_lineage': {'source': 'integration fixture'}}


def test_roundtrip_preserves_unknown_failed_satisfied_ground(database):
    connection, schema = database
    generation_id = stage(connection, schema, fixture_systems(), MANIFEST)
    assert connection.execute(f'SELECT status FROM {schema}.generation').fetchone() == ('VALIDATING',)
    receipt = validate(connection, schema, generation_id)
    assert receipt['status'] == 'READY' and receipt['published'] is False
    assert receipt['counts']['system_economy_rating'] == 21
    rows = connection.execute(f'''
        SELECT system_id64, potential_score, specialisation_quality,
            specialisation_quality_min, specialisation_quality_max
        FROM {schema}.system_economy_rating WHERE economy='Refinery' ORDER BY system_id64
    ''').fetchall()
    assert rows == [(1, 62, None, 0, 100), (2, 62, 0, 0, 0), (3, 62, 100, 100, 100)]
    with pytest.raises(ValueError, match='must be VALIDATING'):
        validate(connection, schema, generation_id)
    assert connection.execute(f'SELECT status FROM {schema}.generation').fetchone() == ('READY',)


@pytest.mark.parametrize('tamper', ['score', 'contributor', 'feature', 'input', 'lineage', 'canonical', 'version'])
def test_corruption_fails_closed_before_ready(database, tamper):
    connection, schema = database
    generation_id = stage(connection, schema, fixture_systems(), MANIFEST)
    updates = {
        'score': f'UPDATE {schema}.system_economy_rating SET potential_score=1',
        'contributor': f'DELETE FROM {schema}.economy_rating_contributor',
        'feature': f'DELETE FROM {schema}.mechanics_feature',
        'input': f"UPDATE {schema}.system_input SET payload=jsonb_set(payload, '{{body_inventory_complete}}', 'false')",
        'lineage': f"UPDATE {schema}.generation SET manifest='{{}}'::jsonb",
        'canonical': f"UPDATE {schema}.generation SET canonical_generation='other'",
        'version': f"UPDATE {schema}.generation SET scorer_version='other'",
    }
    connection.execute(updates[tamper])
    with pytest.raises(ValueError):
        validate(connection, schema, generation_id)
    assert connection.execute(f'SELECT status FROM {schema}.generation').fetchone() == ('FAILED',)


def test_failed_stage_is_atomic_and_generation_id_cannot_be_replaced(database):
    connection, schema = database
    generation_id = stage(connection, schema, fixture_systems(), MANIFEST)
    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation):
        stage(connection, schema, fixture_systems(), MANIFEST, generation_id)
    assert connection.execute(f'SELECT count(*) FROM {schema}.generation').fetchone() == (1,)
    assert validate(connection, schema, generation_id)['status'] == 'READY'


def test_full_source_cohort_roundtrip(database):
    from domain.ratings_v4_canonical import adapt_canonical_export, canonical_lineage, load_source_fixture
    source = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    systems = adapt_canonical_export(*source)
    connection, schema = database
    manifest = {'canonical_generation': source[0]['canonical_schema'], 'source_lineage': canonical_lineage(*source)}
    receipt = validate(connection, schema, stage(connection, schema, systems, manifest))
    assert receipt['counts']['system_input'] == 12
    assert receipt['counts']['system_economy_rating'] == 84
    assert receipt['counts']['economy_opportunity'] == 360 * 7


def test_partial_component_insert_failure_rolls_back_every_table(database, monkeypatch):
    import psycopg
    from scripts.ratings_v4 import generation
    connection, schema = database
    rows = generation.materialize(fixture_systems())
    rows['system_economy_rating'][0][2] = 101
    monkeypatch.setattr(generation, 'materialize', lambda systems: rows)
    with pytest.raises(psycopg.errors.CheckViolation):
        stage(connection, schema, fixture_systems(), MANIFEST)
    for table in ('generation', *generation.TABLES):
        assert connection.execute(f'SELECT count(*) FROM {schema}.{table}').fetchone() == (0,)


def test_database_rejects_exact_quality_with_unresolved_bounds(database):
    import psycopg
    connection, schema = database
    stage(connection, schema, fixture_systems(), MANIFEST)
    with pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(f"UPDATE {schema}.system_economy_rating SET specialisation_quality=50 WHERE system_id64=1 AND economy='Refinery'")
