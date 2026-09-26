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
