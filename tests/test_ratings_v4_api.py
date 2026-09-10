"""Ratings V4 API contract over a verified, immutable derived generation."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import os
from pathlib import Path
import sys

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://ratings-v4-test.invalid')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.domain.ratings_v4 import ECONOMIES, opportunities_from_facts, rate_all  # noqa: E402
from edfinder_api.routers.ratings_v4 import (  # noqa: E402
    SystemExplanationResponse, _facts, _read_system, _summary, router,
)
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Connection:
    def __init__(self, current, vector, bodies):
        self.current, self.vector, self.bodies = current, vector, bodies

    def transaction(self, *, readonly):
        assert readonly is True
        return _Transaction()

    async def fetchrow(self, query, *_):
        if 'current_derived_generation' in query:
            return self.current
        if 'system_rating_vector' in query:
            return self.vector
        raise AssertionError(query)

    async def fetch(self, query, *_):
        assert 'body_mechanics' in query
        return self.bodies


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def _receipt(canonical, metadata):
    return {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    }


def test_read_only_api_replays_the_published_vector_from_immutable_mechanics():
    with canonical_database() as (connection, canonical, _metadata, payloads):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        snapshot = CanonicalSnapshot.pin(connection)
        exported = snapshot.export_chunk(connection, [row['id64'] for row in canonical['systems']])
        generation = create_generation(connection, snapshot, 'api_contract_fixture')
        records = [payload['system'] for payload in payloads]
        assert write_chunk(connection, generation, 0, exported, snapshot.metadata, records)
        seal_source(connection, generation, _receipt(exported, snapshot.metadata))
        validate_generation(connection, generation)
        connection.execute('SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)', (
            generation, None, 0, snapshot.generation_id, snapshot.publication_sequence,
            'test', 'verified API contract fixture',
        ))

        identifier = canonical['systems'][0]['id64']
        with connection.cursor(row_factory=dict_row) as cursor:
            current = cursor.execute('''SELECT c.derived_generation_id,c.publication_sequence,c.published_at,
                d.canonical_generation_id,d.canonical_publication_sequence,d.scorer_version,d.mechanics_version,
                d.adapter_version,d.validation_receipt,d.manifest
                FROM v3_meta.current_derived_generation c
                JOIN v3_meta.derived_generation d USING(derived_generation_id)''').fetchone()
            vector = cursor.execute('''SELECT derived_generation_id,system_id64,chunk_ordinal,loaded_body_count,
                physical_body_count,subtype_projection_sha256,potential,quality,quality_min,quality_max,
                completeness,confidence FROM v3_derived.system_rating_vector
                WHERE derived_generation_id=%s AND system_id64=%s''', (generation, identifier)).fetchone()
            bodies = cursor.execute('''SELECT derived_generation_id,system_id64,body_pk,source_body_id64,body_class,
                spectral_class,luminosity_class,rings,biologicals,geologicals,volcanism,terraformable,
                tidally_locked,is_main_star,reserve_level,usable_ground_opportunity,subtype_present,
                subtype_observed_at FROM v3_derived.body_mechanics
                WHERE derived_generation_id=%s AND system_id64=%s ORDER BY body_pk''',
                (generation, identifier)).fetchall()

    facts = _facts(current['manifest'], vector, bodies)
    expected = rate_all(opportunities_from_facts(facts))
    expected_rows = [{'economy': economy, **asdict(expected[economy])} for economy in ECONOMIES]
    expected_summary = [{key: row[key] for key in (
        'economy', 'potential_score', 'specialisation_quality',
        'specialisation_quality_min', 'specialisation_quality_max',
        'evidence_completeness', 'confidence',
    )} for row in expected_rows]
    assert _summary(vector) == expected_summary
    assert any('source_projection_sha256' in body.feature_provenance['body_class'] for body in facts.bodies)

    response = asyncio.run(_read_system(_Pool(_Connection(current, vector, bodies)), identifier, explanation=True))
    assert response['ratings'] == expected_rows
    assert 'overall_score' not in response
    assert response['derived_generation_id'] == str(generation)
    assert SystemExplanationResponse.model_validate(response).ratings[0].economy == ECONOMIES[0]


def test_api_router_exposes_only_generation_and_independent_economy_reads():
    assert [route.path for route in router.routes] == [
        '/api/ratings/v4/generation',
        '/api/ratings/v4/systems/{system_id64}',
        '/api/ratings/v4/systems/{system_id64}/explanation',
    ]
