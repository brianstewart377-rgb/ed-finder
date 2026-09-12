#!/usr/bin/env python3
'''Build and validate the generation-scoped V3 system-search product.

Ratings V4 owns the base derived generation. Search attaches an independent
manifest and lifecycle to that same generation, consumes only committed Ratings
chunks plus the pinned canonical generation, and never publishes anything.
'''
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRODUCT_CODE = 'system_search'
PRODUCT_VERSION = 'v3-system-search-1'
GENERATION_KEY = re.compile(r'[a-z][a-z0-9_]{0,62}\Z')
SCHEMA_NAME = re.compile(r'v3_gen_[a-z][a-z0-9_]{0,30}\Z')
Progress = Callable[[dict], None]


@dataclass(frozen=True)
class Generation:
    identifier: str
    key: str
    state: str
    canonical_generation_id: str
    canonical_publication_sequence: int
    canonical_schema: str
    expected_systems: int


def _json(value) -> str:
    def convert(item):
        if isinstance(item, (bytes, bytearray, memoryview)):
            return bytes(item).hex()
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat()
        return str(item)

    return json.dumps(
        value, default=convert, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False,
    )


def _digest(value) -> bytes:
    return hashlib.sha256(_json(value).encode()).digest()


def code_identity(root: Path = ROOT) -> dict[str, str]:
    files = (
        'scripts/v3_system_search.py',
        'sql/v3/migrations/004_v3_search_spatial_clusters.sql',
        'sql/v3/migrations/006_v3_derived_product_lifecycle.sql',
    )
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in files
    }


def _generation(connection, generation_key: str) -> Generation:
    if not GENERATION_KEY.fullmatch(generation_key):
        raise ValueError('invalid derived generation key')
    row = connection.execute(
        '''SELECT derived_generation_id::text,generation_key,lifecycle_state,
                  canonical_generation_id::text,canonical_publication_sequence,
                  manifest,expected_systems
             FROM v3_meta.derived_generation
            WHERE generation_key=%s''',
        (generation_key,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown derived generation')
    manifest = row[5]
    schema = manifest.get('canonical_schema') if isinstance(manifest, dict) else None
    if not isinstance(schema, str) or not SCHEMA_NAME.fullmatch(schema):
        raise ValueError('derived generation has invalid canonical schema')
    return Generation(
        identifier=row[0],
        key=row[1],
        state=row[2],
        canonical_generation_id=row[3],
        canonical_publication_sequence=int(row[4]),
        canonical_schema=schema,
        expected_systems=int(row[6]),
    )


def product_manifest(generation: Generation) -> dict:
    return {
        'product_code': PRODUCT_CODE,
        'product_version': PRODUCT_VERSION,
        'derived_generation_id': generation.identifier,
        'generation_key': generation.key,
        'canonical_generation_id': generation.canonical_generation_id,
        'canonical_publication_sequence': generation.canonical_publication_sequence,
        'canonical_schema': generation.canonical_schema,
        'expected_rows': generation.expected_systems,
        'code_sha256': code_identity(),
        'field_policy': {
            'position': 'canonical systems x/y/z; cube point is derived from those exact LY coordinates',
            'body_count': 'Ratings V4 loaded_body_count for the same generation/system',
            'landable_count': 'ACTIVE canonical bodies with is_landable=true',
            'station_count': 'ACTIVE canonical stations',
            'has_rings': 'positive observation of an ACTIVE canonical RING; asteroid BELT rows do not set this Finder flag',
            'has_biologicals': 'positive biological signal_count on an ACTIVE canonical body',
            'has_geologicals': 'positive geological signal_count on an ACTIVE canonical body',
            'has_terraformable': 'ACTIVE canonical body with terraforming state terraformable/terraformed/terraforming',
            'main_star_class': 'lowest-body_pk Ratings V4 mechanics body explicitly marked is_main_star=true',
            'source_observed_at': 'canonical systems.source_updated_at',
            'completeness': 'minimum of the seven frozen Ratings V4 completeness values',
            'confidence': 'minimum of the seven frozen Ratings V4 confidence values',
            'false_flags': 'false means no positive observation in the pinned canonical generation, not proof of known absence',
        },
    }


def _product(connection, generation_id: str):
    return connection.execute(
        '''SELECT product_version,lifecycle_state,manifest,manifest_sha256,
                  expected_rows,validation_receipt,validation_sha256
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (generation_id, PRODUCT_CODE),
    ).fetchone()


def register_product(connection, generation_key: str) -> tuple[Generation, str, bytes]:
    generation = _generation(connection, generation_key)
    if generation.state not in {'BUILDING', 'VALIDATING', 'READY'}:
        raise ValueError('generation cannot accept a Search product')
    manifest = product_manifest(generation)
    manifest_sha = _digest(manifest)

    existing = _product(connection, generation.identifier)
    if existing is None:
        with connection.transaction():
            connection.execute(
                '''INSERT INTO v3_meta.derived_product(
                       derived_generation_id,product_code,product_version,
                       manifest,manifest_sha256,expected_rows)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s)''',
                (
                    generation.identifier, PRODUCT_CODE, PRODUCT_VERSION,
                    _json(manifest), manifest_sha, generation.expected_systems,
                ),
            )
        existing = _product(connection, generation.identifier)

    if existing is None:
        raise ValueError('Search product registration failed')
    if (
        existing[0] != PRODUCT_VERSION
        or existing[2] != manifest
        or bytes(existing[3]) != manifest_sha
        or int(existing[4]) != generation.expected_systems
    ):
        raise ValueError('existing Search product manifest differs from current code/input')
    return generation, existing[1], manifest_sha


def _source_projection_sha(
    generation: Generation,
    manifest_sha: bytes,
    ordinal: int,
    canonical_input_sha: bytes,
    ratings_content_sha: bytes,
) -> bytes:
    return _digest({
        'product': PRODUCT_CODE,
        'product_version': PRODUCT_VERSION,
        'derived_generation_id': generation.identifier,
        'canonical_generation_id': generation.canonical_generation_id,
        'canonical_publication_sequence': generation.canonical_publication_sequence,
        'chunk_ordinal': ordinal,
        'product_manifest_sha256': manifest_sha.hex(),
        'ratings_canonical_input_sha256': bytes(canonical_input_sha).hex(),
        'ratings_content_sha256': bytes(ratings_content_sha).hex(),
    })


def _rating_chunks(connection, generation_id: str, *, missing_search_only: bool = False):
    if missing_search_only:
        return connection.execute(
            '''SELECT b.chunk_ordinal,b.systems,b.canonical_input_sha256,b.content_sha256
                 FROM v3_derived.build_chunk b
            LEFT JOIN v3_derived.search_build_chunk s
                   ON s.derived_generation_id=b.derived_generation_id
                  AND s.chunk_ordinal=b.chunk_ordinal
                WHERE b.derived_generation_id=%s
                  AND s.chunk_ordinal IS NULL
                ORDER BY b.chunk_ordinal''',
            (generation_id,),
        ).fetchall()
    return connection.execute(
        '''SELECT chunk_ordinal,systems,canonical_input_sha256,content_sha256
             FROM v3_derived.build_chunk
            WHERE derived_generation_id=%s
            ORDER BY chunk_ordinal''',
        (generation_id,),
    ).fetchall()


def _chunk_content_sha(connection, generation_id: str, ordinal: int) -> bytes:
    rows = connection.execute(
        '''SELECT s.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
                  s.galaxy_region_id,s.region_name,s.main_star_class,
                  s.body_count,s.landable_count,s.station_count,s.has_rings,
                  s.has_biologicals,s.has_geologicals,s.has_terraformable,
                  s.source_observed_at,s.completeness,s.confidence
             FROM v3_derived.system_search s
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=s.derived_generation_id
              AND v.system_id64=s.system_id64
            WHERE s.derived_generation_id=%s AND v.chunk_ordinal=%s
            ORDER BY s.system_id64''',
        (generation_id, ordinal),
    ).fetchall()
    return _digest(rows)


def _insert_chunk(
    connection,
    generation: Generation,
    manifest_sha: bytes,
    chunk,
) -> bool:
    from psycopg import sql

    ordinal, systems, canonical_input_sha, ratings_content_sha = chunk
    ordinal = int(ordinal)
    systems = int(systems)
    source_sha = _source_projection_sha(
        generation, manifest_sha, ordinal,
        bytes(canonical_input_sha), bytes(ratings_content_sha),
    )

    with connection.transaction():
        product = connection.execute(
            '''SELECT lifecycle_state,manifest_sha256
                 FROM v3_meta.derived_product
                WHERE derived_generation_id=%s AND product_code=%s
                FOR UPDATE''',
            (generation.identifier, PRODUCT_CODE),
        ).fetchone()
        if product is None or product[0] != 'BUILDING':
            raise ValueError('Search product is not BUILDING')
        if bytes(product[1]) != manifest_sha:
            raise ValueError('Search product manifest changed')

        receipt = connection.execute(
            '''SELECT projection_version,source_projection_sha256,content_sha256,systems
                 FROM v3_derived.search_build_chunk
                WHERE derived_generation_id=%s AND chunk_ordinal=%s''',
            (generation.identifier, ordinal),
        ).fetchone()
        if receipt is not None:
            if (
                receipt[0] != PRODUCT_VERSION
                or bytes(receipt[1]) != source_sha
                or int(receipt[3]) != systems
            ):
                raise ValueError('resumed Search chunk source/coverage changed')
            return False

        preexisting = connection.execute(
            '''SELECT count(*)
                 FROM v3_derived.system_search s
                 JOIN v3_derived.system_rating_vector v
                   ON v.derived_generation_id=s.derived_generation_id
                  AND v.system_id64=s.system_id64
                WHERE s.derived_generation_id=%s AND v.chunk_ordinal=%s''',
            (generation.identifier, ordinal),
        ).fetchone()[0]
        if preexisting:
            raise ValueError('unreceipted Search rows already exist for chunk')

        schema = sql.Identifier(generation.canonical_schema)
        query = sql.SQL(
            '''
            WITH target AS MATERIALIZED (
                SELECT v.system_id64,v.loaded_body_count,v.completeness,v.confidence
                  FROM v3_derived.system_rating_vector v
                 WHERE v.derived_generation_id=%s AND v.chunk_ordinal=%s
            ),
            body_summary AS (
                SELECT b.system_id64,
                       (count(*) FILTER (
                           WHERE b.lifecycle_state='ACTIVE' AND b.is_landable IS TRUE
                       ))::integer AS landable_count,
                       bool_or(
                           b.lifecycle_state='ACTIVE'
                           AND ts.public_code IN ('terraformable','terraformed','terraforming')
                       ) AS has_terraformable
                  FROM {}.bodies b
                  JOIN target t ON t.system_id64=b.system_id64
             LEFT JOIN v3_vocab.terraforming_state ts
                    ON ts.terraforming_state_id=b.terraforming_state_id
              GROUP BY b.system_id64
            ),
            ring_summary AS (
                SELECT r.system_id64,true AS has_rings
                  FROM {}.rings r
                  JOIN target t ON t.system_id64=r.system_id64
                 WHERE r.lifecycle_state='ACTIVE' AND r.kind='RING'
              GROUP BY r.system_id64
            ),
            signal_summary AS (
                SELECT b.system_id64,
                       bool_or(st.public_code='saa_signaltype_biological'
                               AND bs.signal_count>0) AS has_biologicals,
                       bool_or(st.public_code='saa_signaltype_geological'
                               AND bs.signal_count>0) AS has_geologicals
                  FROM {}.body_signal_current bs
                  JOIN {}.bodies b ON b.body_pk=bs.body_pk
                  JOIN target t ON t.system_id64=b.system_id64
                  JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
                 WHERE b.lifecycle_state='ACTIVE'
              GROUP BY b.system_id64
            ),
            station_summary AS (
                SELECT st.system_id64,
                       (count(*) FILTER (WHERE st.lifecycle_state='ACTIVE'))::integer
                           AS station_count
                  FROM {}.stations st
                  JOIN target t ON t.system_id64=st.system_id64
              GROUP BY st.system_id64
            ),
            main_star AS (
                SELECT DISTINCT ON (bm.system_id64)
                       bm.system_id64,bm.body_class AS main_star_class
                  FROM v3_derived.body_mechanics bm
                  JOIN target t ON t.system_id64=bm.system_id64
                 WHERE bm.derived_generation_id=%s AND bm.is_main_star IS TRUE
              ORDER BY bm.system_id64,bm.body_pk
            )
            INSERT INTO v3_derived.system_search(
                derived_generation_id,system_id64,name,x_ly,y_ly,z_ly,position_ly,
                galaxy_region_id,region_name,main_star_class,body_count,landable_count,
                station_count,has_rings,has_biologicals,has_geologicals,
                has_terraformable,source_observed_at,completeness,confidence
            )
            SELECT %s,t.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
                   cube(ARRAY[s.x_ly,s.y_ly,s.z_ly]),
                   s.galaxy_region_id,gr.display_name,ms.main_star_class,
                   t.loaded_body_count,COALESCE(bs.landable_count,0),
                   COALESCE(ss.station_count,0),COALESCE(rs.has_rings,false),
                   COALESCE(sig.has_biologicals,false),
                   COALESCE(sig.has_geologicals,false),
                   COALESCE(bs.has_terraformable,false),
                   s.source_updated_at,
                   (SELECT min(value)::double precision/10000
                      FROM unnest(t.completeness) AS value),
                   (SELECT min(value)::double precision/10000
                      FROM unnest(t.confidence) AS value)
              FROM target t
              JOIN {}.systems s ON s.id64=t.system_id64
         LEFT JOIN v3_vocab.galaxy_region gr
                ON gr.galaxy_region_id=s.galaxy_region_id
         LEFT JOIN body_summary bs USING(system_id64)
         LEFT JOIN ring_summary rs USING(system_id64)
         LEFT JOIN signal_summary sig USING(system_id64)
         LEFT JOIN station_summary ss USING(system_id64)
         LEFT JOIN main_star ms USING(system_id64)
            ORDER BY t.system_id64
            '''
        ).format(schema, schema, schema, schema, schema, schema)

        cursor = connection.execute(
            query,
            (
                generation.identifier, ordinal,
                generation.identifier,
                generation.identifier,
            ),
        )
        if cursor.rowcount != systems:
            raise ValueError('Search chunk did not cover every Ratings system')

        content_sha = _chunk_content_sha(connection, generation.identifier, ordinal)
        connection.execute(
            '''INSERT INTO v3_derived.search_build_chunk(
                   derived_generation_id,chunk_ordinal,product_code,projection_version,
                   source_projection_sha256,content_sha256,systems)
               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (
                generation.identifier, ordinal, PRODUCT_CODE, PRODUCT_VERSION,
                source_sha, content_sha, systems,
            ),
        )
    return True


def build_available(
    connection,
    generation: Generation,
    manifest_sha: bytes,
    *,
    max_chunks: int | None = None,
    progress: Progress | None = None,
) -> dict:
    if max_chunks is not None and (type(max_chunks) is not int or max_chunks <= 0):
        raise ValueError('max_chunks must be a positive integer')
    chunks_seen = chunks_written = 0
    for chunk in _rating_chunks(connection, generation.identifier, missing_search_only=True):
        written = _insert_chunk(connection, generation, manifest_sha, chunk)
        chunks_seen += 1
        chunks_written += int(written)
        if written and progress is not None:
            progress({
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'chunk_ordinal': int(chunk[0]),
                'systems': int(chunk[1]),
                'written': True,
            })
        if max_chunks is not None and chunks_written >= max_chunks:
            break
    return {'chunks_seen': chunks_seen, 'chunks_written': chunks_written}


def validate_product(
    connection,
    generation: Generation,
    manifest_sha: bytes,
) -> dict:
    generation = _generation(connection, generation.key)
    product = _product(connection, generation.identifier)
    if product is None:
        raise ValueError('Search product is not registered')
    if product[1] == 'READY':
        receipt = product[5]
        if not isinstance(receipt, dict) or receipt.get('status') != 'VERIFIED':
            raise ValueError('READY Search product has no VERIFIED receipt')
        return receipt
    if product[1] != 'BUILDING':
        raise ValueError('Search product cannot be validated from current state')

    vector_count = int(connection.execute(
        'SELECT count(*) FROM v3_derived.system_rating_vector WHERE derived_generation_id=%s',
        (generation.identifier,),
    ).fetchone()[0])
    search_count = int(connection.execute(
        'SELECT count(*) FROM v3_derived.system_search WHERE derived_generation_id=%s',
        (generation.identifier,),
    ).fetchone()[0])
    rating_chunks = _rating_chunks(connection, generation.identifier)
    search_chunks = connection.execute(
        '''SELECT chunk_ordinal,projection_version,source_projection_sha256,
                  content_sha256,systems
             FROM v3_derived.search_build_chunk
            WHERE derived_generation_id=%s
            ORDER BY chunk_ordinal''',
        (generation.identifier,),
    ).fetchall()

    complete = (
        generation.state in {'VALIDATING', 'READY'}
        and vector_count == generation.expected_systems
        and search_count == generation.expected_systems
        and len(rating_chunks) == len(search_chunks)
        and sum(int(row[1]) for row in rating_chunks) == generation.expected_systems
        and all(int(row[0]) == index for index, row in enumerate(rating_chunks))
    )
    if not complete:
        return {
            'status': 'INCOMPLETE',
            'derived_generation_id': generation.identifier,
            'product_code': PRODUCT_CODE,
            'base_lifecycle_state': generation.state,
            'expected_systems': generation.expected_systems,
            'rating_systems': vector_count,
            'search_systems': search_count,
            'rating_chunks': len(rating_chunks),
            'search_chunks': len(search_chunks),
        }

    validation_digest = hashlib.sha256()
    validation_digest.update(manifest_sha)
    for rating, search in zip(rating_chunks, search_chunks, strict=True):
        ordinal, systems, canonical_input_sha, ratings_content_sha = rating
        if int(search[0]) != int(ordinal):
            raise ValueError('Search chunk receipt ordinal gap')
        if search[1] != PRODUCT_VERSION or int(search[4]) != int(systems):
            raise ValueError('Search chunk receipt version/coverage mismatch')
        expected_source = _source_projection_sha(
            generation, manifest_sha, int(ordinal),
            bytes(canonical_input_sha), bytes(ratings_content_sha),
        )
        if bytes(search[2]) != expected_source:
            raise ValueError('Search chunk source seal mismatch')
        validation_digest.update(_json({
            'chunk_ordinal': int(ordinal),
            'source_projection_sha256': bytes(search[2]).hex(),
            'content_sha256': bytes(search[3]).hex(),
            'systems': int(search[4]),
        }).encode())

    invalid_positions = int(connection.execute(
        '''SELECT count(*)
             FROM v3_derived.system_search
            WHERE derived_generation_id=%s
              AND cube_distance(position_ly,cube(ARRAY[x_ly,y_ly,z_ly]))<>0''',
        (generation.identifier,),
    ).fetchone()[0])
    if invalid_positions:
        raise ValueError('Search cube position differs from numeric LY truth')

    receipt = {
        'status': 'VERIFIED',
        'derived_generation_id': generation.identifier,
        'product_code': PRODUCT_CODE,
        'product_version': PRODUCT_VERSION,
        'expected_systems': generation.expected_systems,
        'systems': search_count,
        'chunks': len(search_chunks),
        'coverage_complete': True,
        'source_seals_verified': True,
        'position_truth_verified': True,
        'base_lifecycle_state': generation.state,
        'product_manifest_sha256': manifest_sha.hex(),
    }
    validation_digest.update(_json(receipt).encode())
    validation_sha = validation_digest.digest()
    with connection.transaction():
        updated = connection.execute(
            '''UPDATE v3_meta.derived_product
                  SET lifecycle_state='READY',validation_receipt=%s::jsonb,
                      validation_sha256=%s,validated_at=now()
                WHERE derived_generation_id=%s AND product_code=%s
                  AND lifecycle_state='BUILDING' ''',
            (_json(receipt), validation_sha, generation.identifier, PRODUCT_CODE),
        ).rowcount
        if updated != 1:
            raise ValueError('Search product validation state changed')
    return receipt


def run(
    connection,
    generation_key: str,
    *,
    follow: bool = False,
    poll_seconds: float = 5.0,
    max_chunks: int | None = None,
    progress: Progress | None = None,
) -> dict:
    if not isinstance(poll_seconds, (int, float)) or poll_seconds <= 0:
        raise ValueError('poll_seconds must be positive')
    generation, state, manifest_sha = register_product(connection, generation_key)
    total_seen = total_written = 0

    if state == 'READY':
        receipt = validate_product(connection, generation, manifest_sha)
        return {
            'status': 'VERIFIED',
            'derived_generation_id': generation.identifier,
            'product_code': PRODUCT_CODE,
            'chunks_seen': 0,
            'chunks_written': 0,
            'validation_receipt': receipt,
        }
    if state != 'BUILDING':
        raise ValueError('Search product cannot resume from current state')

    while True:
        result = build_available(
            connection, generation, manifest_sha,
            max_chunks=max_chunks, progress=progress,
        )
        total_seen += result['chunks_seen']
        total_written += result['chunks_written']
        generation = _generation(connection, generation_key)

        receipt = validate_product(connection, generation, manifest_sha)
        if receipt.get('status') == 'VERIFIED':
            return {
                'status': 'VERIFIED',
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'chunks_seen': total_seen,
                'chunks_written': total_written,
                'validation_receipt': receipt,
            }
        if not follow or max_chunks is not None:
            return {
                'status': 'INCOMPLETE',
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'chunks_seen': total_seen,
                'chunks_written': total_written,
                'validation_receipt': receipt,
            }
        time.sleep(float(poll_seconds))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--follow', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=5.0)
    parser.add_argument('--max-chunks', type=int)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    dsn = os.environ.get('V3_SYSTEM_SEARCH_DATABASE_URL')
    if not dsn:
        print(json.dumps({'status': 'FAILED', 'error': 'database_authority_missing'}), file=sys.stderr)
        return 64
    try:
        import psycopg
        with psycopg.connect(dsn, autocommit=True) as connection:
            result = run(
                connection, args.generation_key,
                follow=args.follow,
                poll_seconds=args.poll_seconds,
                max_chunks=args.max_chunks,
                progress=lambda item: print(json.dumps(
                    {'status': 'PROGRESS', **item}, sort_keys=True
                ), flush=True),
            )
    except Exception as exc:
        print(json.dumps({'status': 'FAILED', 'error': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
