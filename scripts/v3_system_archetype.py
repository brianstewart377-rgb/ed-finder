#!/usr/bin/env python3
'''Build and validate the generation-scoped V3 system-archetype product.

Ratings V4 owns the base derived generation. Archetype attaches an independent
manifest and lifecycle to that same generation, consumes only the pinned
Ratings V4 generation's `system_rating_vector` and `economy_opportunity`
relations (no `public.*` reads), and never publishes anything.
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
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import v3_system_archetype_model as model  # noqa: E402

PRODUCT_CODE = 'system_archetype'
PRODUCT_VERSION = model.ARCHETYPE_VERSION
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
        'scripts/v3_system_archetype.py',
        'scripts/v3_system_archetype_model.py',
        'sql/v3/migrations/011_v3_system_archetype.sql',
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


def _anchors() -> dict:
    return {
        key: {'required': list(required), 'supporting': list(supporting)}
        for key, (required, supporting) in model._ANCHORS.items()
    }


def _coefficients() -> dict:
    return {
        'alpha': model.ALPHA,
        'spec_floor': model.SPEC_FLOOR,
        'spec_span': model.SPEC_SPAN,
        'cap_floor': model.CAP_FLOOR,
        'cap_span': model.CAP_SPAN,
        'capacity_target': model.CAPACITY_TARGET,
        'synergy_bonus': model.SYNERGY_BONUS,
        'synergy_threshold': model.SYNERGY_THRESHOLD,
        'spec_unknown_conf': model.SPEC_UNKNOWN_CONF,
        'breadth_pot': model.BREADTH_POT,
        'breadth_qual': model.BREADTH_QUAL,
        'breadth_target': model.BREADTH_TARGET,
    }


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
        'archetype_keys': list(model.ARCHETYPE_KEYS),
        'anchors': _anchors(),
        'coefficients': _coefficients(),
        'field_policy': {
            'archetype_score': 'round(clamp(core*spec*cap + synergy_bonus, 0, 100)); flexible uses breadth instead of core/spec/cap',
            'tier': 'S>=88, A>=76, B>=60, C>=45, else D',
            'confidence': (
                'min(confidence[a] for a in required anchors), multiplied by '
                'spec_unknown_conf when any anchor quality was bounded-null'
            ),
            'primary_archetype': 'highest archetype_score, ties broken by archetype_keys order',
            'secondary_archetype': 'next highest archetype_score; null only if every other score is 0',
            'source': (
                'pinned Ratings V4 generation: v3_derived.system_rating_vector and '
                'v3_derived.economy_opportunity only; no public.* reads'
            ),
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
        raise ValueError('generation cannot accept an Archetype product')
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
        raise ValueError('Archetype product registration failed')
    if (
        existing[0] != PRODUCT_VERSION
        or existing[2] != manifest
        or bytes(existing[3]) != manifest_sha
        or int(existing[4]) != generation.expected_systems
    ):
        raise ValueError('existing Archetype product manifest differs from current code/input')
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


def _ratings_chunks_missing_archetype(connection, generation_id: str):
    return connection.execute(
        '''SELECT b.chunk_ordinal,b.systems,b.canonical_input_sha256,b.content_sha256
             FROM v3_derived.build_chunk b
        LEFT JOIN v3_derived.archetype_build_chunk a
               ON a.derived_generation_id=b.derived_generation_id
              AND a.chunk_ordinal=b.chunk_ordinal
            WHERE b.derived_generation_id=%s
              AND a.chunk_ordinal IS NULL
            ORDER BY b.chunk_ordinal''',
        (generation_id,),
    ).fetchall()


def _read_chunk_vectors(connection, generation_id: str, ordinal: int) -> dict[int, model.SystemVectors]:
    rows = connection.execute(
        '''SELECT system_id64, potential, quality, quality_min, quality_max,
                  completeness, confidence
             FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=%s
            ORDER BY system_id64''',
        (generation_id, ordinal),
    ).fetchall()
    opp = connection.execute(
        '''SELECT o.system_id64, o.economy_ordinal,
                  count(*)::int, avg(o.local_score)::double precision
             FROM v3_derived.economy_opportunity o
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=o.derived_generation_id
              AND v.system_id64=o.system_id64
            WHERE o.derived_generation_id=%s AND v.chunk_ordinal=%s
            GROUP BY o.system_id64, o.economy_ordinal''',
        (generation_id, ordinal),
    ).fetchall()
    opp_by_system: dict[int, dict[int, tuple[int, float]]] = {}
    for sid, ordn, cnt, mean_local in opp:
        opp_by_system.setdefault(sid, {})[ordn] = (cnt, float(mean_local or 0.0))
    vectors: dict[int, model.SystemVectors] = {}
    for sid, pot, qual, qmin, qmax, comp, conf in rows:
        vectors[sid] = model.SystemVectors(
            pot=tuple(pot), qual=tuple(qual),
            qual_min=tuple(qmin), qual_max=tuple(qmax),
            completeness=tuple(c / 10000.0 for c in comp),
            confidence=tuple(c / 10000.0 for c in conf),
            opp=opp_by_system.get(sid, {}),
        )
    return vectors


def _chunk_content_sha(connection, generation_id: str, ordinal: int) -> bytes:
    archetype_rows = connection.execute(
        '''SELECT a.system_id64, a.archetype_key, a.archetype_score, a.tier,
                  round(a.confidence::numeric, 6)
             FROM v3_derived.system_archetype a
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=a.derived_generation_id
              AND v.system_id64=a.system_id64
            WHERE a.derived_generation_id=%s AND v.chunk_ordinal=%s
            ORDER BY a.system_id64, a.archetype_key''',
        (generation_id, ordinal),
    ).fetchall()
    summary_rows = connection.execute(
        '''SELECT s.system_id64, s.primary_archetype, s.secondary_archetype,
                  s.best_colony_potential, s.best_tier,
                  round(s.archetype_confidence::numeric, 6)
             FROM v3_derived.system_archetype_summary s
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=s.derived_generation_id
              AND v.system_id64=s.system_id64
            WHERE s.derived_generation_id=%s AND v.chunk_ordinal=%s
            ORDER BY s.system_id64''',
        (generation_id, ordinal),
    ).fetchall()
    return _digest({'archetypes': archetype_rows, 'summaries': summary_rows})


def _build_chunk(
    connection,
    generation: Generation,
    manifest_sha: bytes,
    chunk,
) -> tuple[bool, int]:
    ordinal, systems, canonical_input_sha, ratings_content_sha = chunk
    ordinal = int(ordinal)
    systems = int(systems)
    if ordinal < 0 or not 1 <= systems <= 1000:
        raise ValueError('Archetype chunk is outside the bounded Ratings contract')
    source_sha = _source_projection_sha(
        generation, manifest_sha, ordinal,
        bytes(canonical_input_sha), bytes(ratings_content_sha),
    )

    with connection.transaction():
        # Match the insert guard's base -> product lock order (mirrors
        # v3_system_search._insert_chunk). Shared locks permit disjoint
        # chunks while excluding lifecycle/publication changes.
        base = connection.execute(
            '''SELECT lifecycle_state FROM v3_meta.derived_generation
                WHERE derived_generation_id=%s FOR SHARE''',
            (generation.identifier,),
        ).fetchone()
        if base is None or base[0] not in {'BUILDING', 'VALIDATING', 'READY'}:
            raise ValueError('generation cannot accept Archetype rows')
        product = connection.execute(
            '''SELECT lifecycle_state,manifest_sha256
                 FROM v3_meta.derived_product
                WHERE derived_generation_id=%s AND product_code=%s
                FOR SHARE''',
            (generation.identifier, PRODUCT_CODE),
        ).fetchone()
        if product is None or product[0] != 'BUILDING':
            raise ValueError('Archetype product is not BUILDING')
        if bytes(product[1]) != manifest_sha:
            raise ValueError('Archetype product manifest changed')

        # A committed Ratings receipt is the stable per-chunk mutex.
        source = connection.execute(
            '''SELECT systems,canonical_input_sha256,content_sha256
                 FROM v3_derived.build_chunk
                WHERE derived_generation_id=%s AND chunk_ordinal=%s
                FOR NO KEY UPDATE''',
            (generation.identifier, ordinal),
        ).fetchone()
        if (source is None or int(source[0]) != systems
                or bytes(source[1]) != bytes(canonical_input_sha)
                or bytes(source[2]) != bytes(ratings_content_sha)):
            raise ValueError('Archetype Ratings chunk source changed')

        receipt = connection.execute(
            '''SELECT archetype_version,source_projection_sha256,content_sha256,systems
                 FROM v3_derived.archetype_build_chunk
                WHERE derived_generation_id=%s AND chunk_ordinal=%s''',
            (generation.identifier, ordinal),
        ).fetchone()
        if receipt is not None:
            if (
                receipt[0] != PRODUCT_VERSION
                or bytes(receipt[1]) != source_sha
                or int(receipt[3]) != systems
            ):
                raise ValueError('resumed Archetype chunk source/coverage changed')
            return False, 0

        preexisting = connection.execute(
            '''SELECT count(*)
                 FROM v3_derived.system_archetype a
                 JOIN v3_derived.system_rating_vector v
                   ON v.derived_generation_id=a.derived_generation_id
                  AND v.system_id64=a.system_id64
                WHERE a.derived_generation_id=%s AND v.chunk_ordinal=%s''',
            (generation.identifier, ordinal),
        ).fetchone()[0]
        if preexisting:
            raise ValueError('unreceipted Archetype rows already exist for chunk')

        vectors = _read_chunk_vectors(connection, generation.identifier, ordinal)
        if len(vectors) != systems:
            raise ValueError('Archetype chunk did not cover every Ratings system')

        archetype_rows = []
        summary_rows = []
        for system_id64 in sorted(vectors):
            fits = model.fit_all(vectors[system_id64])
            for fit in fits:
                archetype_rows.append((
                    generation.identifier, system_id64, fit.key, PRODUCT_VERSION,
                    fit.score, fit.tier, fit.confidence, _json(fit.explanation),
                ))
            summary = model.summarise(fits)
            summary_rows.append((
                generation.identifier, system_id64,
                summary['primary_archetype'], summary['secondary_archetype'],
                summary['best_colony_potential'], summary['best_tier'],
                summary['archetype_confidence'],
            ))

        # Bulk-write safety exception: only derived Archetype rows/receipts are
        # inserted. No canonical systems/bodies/ratings rows are touched. Keep
        # origin triggers and FKs active: they enforce insert-only data,
        # generation lifecycle, and the atomic receipt contract.
        with connection.cursor() as cursor:
            cursor.executemany(
                '''INSERT INTO v3_derived.system_archetype(
                       derived_generation_id,system_id64,archetype_key,archetype_version,
                       archetype_score,tier,confidence,explanation)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
                archetype_rows,
            )
            cursor.executemany(
                '''INSERT INTO v3_derived.system_archetype_summary(
                       derived_generation_id,system_id64,primary_archetype,secondary_archetype,
                       best_colony_potential,best_tier,archetype_confidence)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                summary_rows,
            )

        content_sha = _chunk_content_sha(connection, generation.identifier, ordinal)
        connection.execute(
            '''INSERT INTO v3_derived.archetype_build_chunk(
                   derived_generation_id,chunk_ordinal,product_code,archetype_version,
                   source_projection_sha256,content_sha256,systems)
               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (
                generation.identifier, ordinal, PRODUCT_CODE, PRODUCT_VERSION,
                source_sha, content_sha, systems,
            ),
        )
    return True, systems


def build_available(
    connection,
    generation: Generation,
    manifest_sha: bytes,
    *,
    max_chunks: int | None = None,
    progress: Progress | None = None,
) -> dict:
    if max_chunks is not None and (type(max_chunks) is not int or max_chunks < 0):
        raise ValueError('max_chunks must be a non-negative integer')
    chunks_seen = chunks_written = systems_written = 0
    if max_chunks != 0:
        for chunk in _ratings_chunks_missing_archetype(connection, generation.identifier):
            written, systems = _build_chunk(connection, generation, manifest_sha, chunk)
            chunks_seen += 1
            if written:
                chunks_written += 1
                systems_written += systems
                if progress is not None:
                    progress({
                        'derived_generation_id': generation.identifier,
                        'product_code': PRODUCT_CODE,
                        'chunk_ordinal': int(chunk[0]),
                        'systems': systems,
                        'written': True,
                    })
            if max_chunks is not None and chunks_written >= max_chunks:
                break
    return {
        'chunks_seen': chunks_seen,
        'chunks_written': chunks_written,
        'systems_written': systems_written,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-key', required=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    dsn = os.environ.get('V3_SYSTEM_ARCHETYPE_DATABASE_URL')
    if not dsn:
        print(json.dumps({'status': 'FAILED', 'error': 'database_authority_missing'}), file=sys.stderr)
        return 64
    try:
        import psycopg
        with psycopg.connect(dsn, autocommit=True) as connection:
            generation, state, manifest_sha = register_product(connection, args.generation_key)
            result = {
                'status': 'REGISTERED',
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'product_version': PRODUCT_VERSION,
                'base_lifecycle_state': state,
                'manifest_sha256': manifest_sha.hex(),
            }
    except Exception as exc:
        print(json.dumps({'status': 'FAILED', 'error': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
