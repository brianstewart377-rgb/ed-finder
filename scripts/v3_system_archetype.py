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
import time
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
                  round(a.confidence::numeric, 6), a.archetype_version, a.explanation
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


def _gate_coverage(connection, generation_id: str) -> tuple[bool, list[str], dict]:
    '''Hard gate 1: every system in system_rating_vector has exactly the
    ARCHETYPE_KEYS set of system_archetype rows (not merely 8 rows of any
    regex-valid key), each stamped with the expected archetype_version, and
    exactly one system_archetype_summary row. Set-based; never fetches
    per-row data.'''
    n_keys = len(model.ARCHETYPE_KEYS)
    expected_keys = sorted(model.ARCHETYPE_KEYS)
    vector_count = int(connection.execute(
        'SELECT count(*) FROM v3_derived.system_rating_vector WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0])
    archetype_rows = int(connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0])
    summary_rows = int(connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype_summary WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0])
    bad_archetype = int(connection.execute(
        '''SELECT count(*) FROM (
               SELECT v.system_id64,
                      array_agg(a.archetype_key ORDER BY a.archetype_key)
                          FILTER (WHERE a.archetype_key IS NOT NULL) AS keys,
                      bool_or(a.archetype_version IS DISTINCT FROM %s) AS bad_version
                 FROM v3_derived.system_rating_vector v
                 LEFT JOIN v3_derived.system_archetype a
                   ON a.derived_generation_id=v.derived_generation_id
                  AND a.system_id64=v.system_id64
                WHERE v.derived_generation_id=%s
                GROUP BY v.system_id64
               HAVING array_agg(a.archetype_key ORDER BY a.archetype_key)
                          FILTER (WHERE a.archetype_key IS NOT NULL) IS DISTINCT FROM %s::text[]
                   OR bool_or(a.archetype_version IS DISTINCT FROM %s)
           ) bad''',
        (PRODUCT_VERSION, generation_id, expected_keys, PRODUCT_VERSION),
    ).fetchone()[0])
    bad_summary = int(connection.execute(
        '''SELECT count(*) FROM (
               SELECT v.system_id64, count(s.system_id64) AS n
                 FROM v3_derived.system_rating_vector v
                 LEFT JOIN v3_derived.system_archetype_summary s
                   ON s.derived_generation_id=v.derived_generation_id
                  AND s.system_id64=v.system_id64
                WHERE v.derived_generation_id=%s
                GROUP BY v.system_id64
               HAVING count(s.system_id64)<>1
           ) bad''',
        (generation_id,),
    ).fetchone()[0])

    reasons = []
    if bad_archetype:
        reasons.append(
            f'coverage: {bad_archetype} system(s) do not have exactly the '
            f'{n_keys} expected archetype_key values at archetype_version '
            f'{PRODUCT_VERSION!r}'
        )
    if bad_summary:
        reasons.append(
            f'coverage: {bad_summary} system(s) do not have exactly one '
            'system_archetype_summary row'
        )
    ok = vector_count > 0 and bad_archetype == 0 and bad_summary == 0
    counts = {
        'systems': vector_count,
        'archetype_rows': archetype_rows,
        'summary_rows': summary_rows,
    }
    return ok, reasons, counts


def _tier_case_expression() -> tuple[str, list]:
    '''Build a fully-parameterized SQL CASE mirroring model.tier_of, so the
    invariant gate never hardcodes/duplicates the tier thresholds.'''
    clauses = []
    params: list = []
    for threshold, name in model._TIERS:
        clauses.append('WHEN archetype_score>=%s THEN %s')
        params.extend([threshold, name])
    return 'CASE ' + ' '.join(clauses) + " ELSE 'D' END", params


def _gate_score_and_tier(connection, generation_id: str) -> tuple[bool, list[str]]:
    '''Hard gate 2: archetype_score in [0,100] and tier consistent with
    tier_of(score). Set-based; the CASE expression is built from
    model._TIERS so it cannot drift from the pure model.'''
    case_sql, case_params = _tier_case_expression()
    bad = int(connection.execute(
        f'''SELECT count(*) FROM v3_derived.system_archetype
             WHERE derived_generation_id=%s
               AND (archetype_score<0 OR archetype_score>100
                    OR tier<>{case_sql})''',
        (generation_id, *case_params),
    ).fetchone()[0])
    if bad:
        return False, [
            f'invariants: {bad} system_archetype row(s) have an out-of-range '
            'score or a tier inconsistent with tier_of(score)'
        ]
    return True, []


def _gate_summary_matches_max(connection, generation_id: str) -> tuple[bool, list[str]]:
    '''Hard gate 3: each summary's full row -- primary_archetype,
    secondary_archetype, best_colony_potential, best_tier and
    archetype_confidence -- matches the system's top-2 scoring archetype rows
    (ties broken by ARCHETYPE_KEYS order, matching model.summarise). Set-based
    via a window function; the tie-break order is passed as a bound array
    parameter. archetype_confidence is compared with a small float tolerance
    (the stored value was already rounded to 6dp by model.summarise).'''
    bad = int(connection.execute(
        '''WITH ranked AS (
               SELECT system_id64, archetype_key, archetype_score, tier,
                      row_number() OVER (
                          PARTITION BY system_id64
                          ORDER BY archetype_score DESC,
                                   array_position(%s::text[], archetype_key) ASC
                      ) AS rnk
                 FROM v3_derived.system_archetype
                WHERE derived_generation_id=%s
           ),
           top2 AS (
               SELECT system_id64,
                      max(archetype_key) FILTER (WHERE rnk=1) AS primary_key,
                      max(archetype_score) FILTER (WHERE rnk=1) AS s1,
                      max(tier) FILTER (WHERE rnk=1) AS tier1,
                      max(archetype_key) FILTER (WHERE rnk=2) AS secondary_key,
                      max(archetype_score) FILTER (WHERE rnk=2) AS s2
                 FROM ranked
                WHERE rnk<=2
                GROUP BY system_id64
           )
           SELECT count(*)
             FROM v3_derived.system_archetype_summary s
             JOIN top2 t ON t.system_id64=s.system_id64
            WHERE s.derived_generation_id=%s
              AND (s.primary_archetype<>t.primary_key
                   OR s.best_colony_potential<>t.s1
                   OR s.best_tier<>t.tier1
                   OR s.secondary_archetype IS DISTINCT FROM
                          (CASE WHEN t.s2>0 THEN t.secondary_key END)
                   OR abs(s.archetype_confidence -
                          LEAST(
                              (t.s1-t.s2)::double precision
                                  / GREATEST(t.s1,1)::double precision * 2,
                              1.0
                          )) > 1e-6)''',
        (list(model.ARCHETYPE_KEYS), generation_id, generation_id),
    ).fetchone()[0])
    if bad:
        return False, [
            f"invariants: {bad} summary row(s) do not match their system's "
            'top-2 archetype rows (primary_archetype/secondary_archetype/'
            'best_colony_potential/best_tier/archetype_confidence)'
        ]
    return True, []


def _gate_chunk_seals(
    connection, generation: Generation, manifest_sha: bytes,
) -> tuple[bool, list[str], int]:
    '''Hard gate 4: reproducible from generation + archetype_version — every
    archetype_build_chunk receipt's source seal is recomputed from the
    generation, manifest and the immutable Ratings chunk it was built from,
    AND the receipt's content_sha256 is recomputed from the materialized
    system_archetype/system_archetype_summary rows themselves (not merely
    trusted from the stored receipt) so a corrupted/drifted materialization
    cannot pass reproducibility on a still-matching source seal alone.'''
    rows = connection.execute(
        '''SELECT b.chunk_ordinal,b.systems,b.canonical_input_sha256,b.content_sha256,
                  a.archetype_version,a.source_projection_sha256,a.content_sha256,a.systems
             FROM v3_derived.build_chunk b
             JOIN v3_derived.archetype_build_chunk a
               ON a.derived_generation_id=b.derived_generation_id
              AND a.chunk_ordinal=b.chunk_ordinal
            WHERE b.derived_generation_id=%s
            ORDER BY b.chunk_ordinal''',
        (generation.identifier,),
    ).fetchall()
    reasons: list[str] = []
    for (
        ordinal, systems, canonical_input_sha, ratings_content_sha,
        version, source_sha, stored_content_sha, archetype_systems,
    ) in rows:
        ordinal = int(ordinal)
        if version != PRODUCT_VERSION:
            reasons.append(
                f'reproducibility: chunk {ordinal} archetype_version {version!r} '
                f'does not match {PRODUCT_VERSION!r}'
            )
            continue
        if int(archetype_systems) != int(systems):
            reasons.append(
                f'reproducibility: chunk {ordinal} systems count {archetype_systems} '
                f'does not match Ratings chunk systems {systems}'
            )
            continue
        expected_source = _source_projection_sha(
            generation, manifest_sha, ordinal,
            bytes(canonical_input_sha), bytes(ratings_content_sha),
        )
        if bytes(source_sha) != expected_source:
            reasons.append(
                f'reproducibility: chunk {ordinal} source seal does not match '
                'generation+manifest+Ratings inputs'
            )
            continue
        actual_content_sha = _chunk_content_sha(connection, generation.identifier, ordinal)
        if bytes(stored_content_sha) != actual_content_sha:
            reasons.append(
                f'reproducibility: chunk {ordinal} content seal does not match '
                'the materialized system_archetype/system_archetype_summary rows'
            )
    return not reasons, reasons, len(rows)


def validate_product(connection, generation: Generation, manifest_sha: bytes) -> dict:
    '''Coverage + invariant hard gates for the Archetype product.

    Mirrors v3_system_search.validate_product's lifecycle behaviour: on
    VERIFIED this promotes the archetype v3_meta.derived_product row from
    BUILDING to READY (guarded UPDATE + rowcount check), storing the VERIFIED
    receipt and its validation_sha256. It never touches the base generation's
    own lifecycle and never calls publish_derived_generation -- publishing
    remains a separate governed operation. `INCOMPLETE` while the base
    Ratings generation has not reached READY (VALIDATING is a transient,
    still-reversible-to-FAILED state and does not count) or the archetype
    build has not covered every Ratings chunk yet (product stays BUILDING);
    `VERIFIED` only once the base is READY and every hard gate passes
    (product promoted to READY); `FAILED` with `reasons` if a gate is
    violated despite full coverage (product stays BUILDING). Calling this
    again once the product is READY is idempotent: it returns the stored
    VERIFIED receipt without re-promoting or re-validating. Every gate
    failure is collected rather than raised, so an operator sees the whole
    picture in one call.
    '''
    generation = _generation(connection, generation.key)
    product = _product(connection, generation.identifier)
    if product is None:
        raise ValueError('Archetype product is not registered')
    if bytes(product[3]) != manifest_sha:
        raise ValueError('Archetype product manifest changed')
    if product[1] == 'READY':
        receipt = product[5]
        if not isinstance(receipt, dict) or receipt.get('status') != 'VERIFIED':
            raise ValueError('READY Archetype product has no VERIFIED receipt')
        return receipt
    if product[1] != 'BUILDING':
        raise ValueError('Archetype product cannot be validated from current state')

    rating_chunks = int(connection.execute(
        'SELECT count(*) FROM v3_derived.build_chunk WHERE derived_generation_id=%s',
        (generation.identifier,),
    ).fetchone()[0])
    archetype_chunks = int(connection.execute(
        'SELECT count(*) FROM v3_derived.archetype_build_chunk WHERE derived_generation_id=%s',
        (generation.identifier,),
    ).fetchone()[0])

    coverage_ok, coverage_reasons, counts = _gate_coverage(connection, generation.identifier)
    # VERIFIED (and promotion) requires the base to be fully READY, not merely
    # VALIDATING -- VALIDATING is a transient, reversible-on-FAILED state for
    # the base generation, so the Archetype product must not promote against it.
    base_ready = generation.state == 'READY'
    chunks_complete = rating_chunks > 0 and archetype_chunks == rating_chunks

    if not (base_ready and chunks_complete and coverage_ok):
        reasons = []
        if not base_ready:
            reasons.append(
                f'base generation not ready for validation (state={generation.state})'
            )
        if not chunks_complete:
            reasons.append(
                f'coverage: archetype build incomplete ({archetype_chunks}/'
                f'{rating_chunks} Ratings chunks built)'
            )
        reasons.extend(coverage_reasons)
        return {
            'status': 'INCOMPLETE',
            'derived_generation_id': generation.identifier,
            'product_code': PRODUCT_CODE,
            'base_lifecycle_state': generation.state,
            'expected_systems': generation.expected_systems,
            'systems': counts['systems'],
            'archetype_rows': counts['archetype_rows'],
            'every_system_has_all_archetypes': coverage_ok,
            'summary_matches_max': False,
            'reasons': reasons,
        }

    score_tier_ok, score_tier_reasons = _gate_score_and_tier(connection, generation.identifier)
    summary_ok, summary_reasons = _gate_summary_matches_max(connection, generation.identifier)
    seals_ok, seal_reasons, chunk_count = _gate_chunk_seals(connection, generation, manifest_sha)

    all_reasons = [*score_tier_reasons, *summary_reasons, *seal_reasons]
    if all_reasons:
        return {
            'status': 'FAILED',
            'derived_generation_id': generation.identifier,
            'product_code': PRODUCT_CODE,
            'base_lifecycle_state': generation.state,
            'expected_systems': generation.expected_systems,
            'systems': counts['systems'],
            'archetype_rows': counts['archetype_rows'],
            'every_system_has_all_archetypes': coverage_ok,
            'invariants_ok': score_tier_ok,
            'summary_matches_max': summary_ok,
            'reasons': all_reasons,
        }

    receipt = {
        'status': 'VERIFIED',
        'derived_generation_id': generation.identifier,
        'product_code': PRODUCT_CODE,
        'product_version': PRODUCT_VERSION,
        'base_lifecycle_state': generation.state,
        'expected_systems': generation.expected_systems,
        'systems': counts['systems'],
        'archetype_rows': counts['archetype_rows'],
        'chunks': chunk_count,
        'every_system_has_all_archetypes': True,
        'invariants_ok': True,
        'summary_matches_max': True,
        'coverage_complete': True,
        'seals_verified': seals_ok,
        'reasons': [],
        'product_manifest_sha256': manifest_sha.hex(),
    }

    validation_digest = hashlib.sha256()
    validation_digest.update(manifest_sha)
    chunk_rows = connection.execute(
        '''SELECT chunk_ordinal,source_projection_sha256,content_sha256,systems
             FROM v3_derived.archetype_build_chunk
            WHERE derived_generation_id=%s
            ORDER BY chunk_ordinal''',
        (generation.identifier,),
    ).fetchall()
    for ordinal, source_sha, content_sha, systems in chunk_rows:
        validation_digest.update(_json({
            'chunk_ordinal': int(ordinal),
            'source_projection_sha256': bytes(source_sha).hex(),
            'content_sha256': bytes(content_sha).hex(),
            'systems': int(systems),
        }).encode())
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
            refreshed = _product(connection, generation.identifier)
            if refreshed is None or refreshed[1] != 'READY':
                raise ValueError('Archetype product validation state changed')
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
    '''register_product then build_available in a poll loop.

    Mirrors v3_system_search.run's follow-loop shape, but termination is
    coverage-based rather than validate_product-based: the Archetype product
    is never promoted here. validate_product already promotes idempotently
    on VERIFIED, so this loop only builds -- promotion/validation is the
    separate `--validate` CLI mode (or a direct validate_product call).

    Completion requires more than archetype_chunks==rating_chunks: while the
    base Ratings generation is still BUILDING, its own build_chunk count is
    still growing, so archetype_chunks can transiently equal rating_chunks
    (e.g. right after this loop catches up) without every Ratings chunk that
    will ever exist having been built yet. Mirroring how
    v3_system_search.run only finishes via validate_product (which itself
    requires the base to be VALIDATING/READY), this loop refreshes the base
    generation every iteration and only treats equal chunk counts as final
    once the base has sealed its source (lifecycle VALIDATING or READY) with
    its full expected system coverage -- otherwise it keeps polling.
    '''
    if not isinstance(poll_seconds, (int, float)) or poll_seconds <= 0:
        raise ValueError('poll_seconds must be positive')
    generation, state, manifest_sha = register_product(connection, generation_key)
    if state not in {'BUILDING', 'READY'}:
        raise ValueError('Archetype product cannot be built from current state')
    total_seen = total_written = 0

    while True:
        result = build_available(
            connection, generation, manifest_sha,
            max_chunks=max_chunks, progress=progress,
        )
        total_seen += result['chunks_seen']
        total_written += result['chunks_written']

        generation = _generation(connection, generation_key)
        rating_row = connection.execute(
            '''SELECT count(*),coalesce(sum(systems),0)
                 FROM v3_derived.build_chunk WHERE derived_generation_id=%s''',
            (generation.identifier,),
        ).fetchone()
        rating_chunks, rating_systems = int(rating_row[0]), int(rating_row[1])
        archetype_chunks = int(connection.execute(
            'SELECT count(*) FROM v3_derived.archetype_build_chunk WHERE derived_generation_id=%s',
            (generation.identifier,),
        ).fetchone()[0])
        base_sealed = generation.state in {'VALIDATING', 'READY'}
        complete = (
            base_sealed
            and rating_chunks > 0
            and archetype_chunks == rating_chunks
            and rating_systems == generation.expected_systems
        )

        if complete:
            return {
                'status': 'BUILT',
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'chunks_seen': total_seen,
                'chunks_written': total_written,
            }
        if not follow or max_chunks is not None:
            return {
                'status': 'INCOMPLETE',
                'derived_generation_id': generation.identifier,
                'product_code': PRODUCT_CODE,
                'chunks_seen': total_seen,
                'chunks_written': total_written,
            }
        time.sleep(float(poll_seconds))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--follow', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=5.0)
    parser.add_argument('--max-chunks', type=int)
    parser.add_argument('--validate', action='store_true')
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
            if args.validate:
                generation, _, manifest_sha = register_product(connection, args.generation_key)
                result = validate_product(connection, generation, manifest_sha)
            else:
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
    # --validate must fail closed on the exit code even though the receipt is
    # still printed: a caller that only checks the exit code (e.g. CI/ops
    # tooling) must not treat FAILED/INCOMPLETE validation as success.
    if args.validate and result.get('status') != 'VERIFIED':
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
