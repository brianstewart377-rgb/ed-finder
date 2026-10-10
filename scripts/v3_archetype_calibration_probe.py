#!/usr/bin/env python3
'''Read-only, bounded calibration probe for the V3 system-archetype model.

Exit status 5 means the calibration sample is empty because no full selected
chunk fit the bound or the selected chunks contained no systems.
'''
from __future__ import annotations

import argparse
from array import array
from collections.abc import Iterable, Sequence
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import v3_system_archetype as archetype_builder  # noqa: E402
from scripts import v3_system_archetype_model as model  # noqa: E402

PROBE_VERSION = 'v3-archetype-calibration-probe-1'
DEFAULT_DATABASE_URL_ENV = 'V3_ARCHETYPE_PROBE_DATABASE_URL'
MAX_SYSTEMS_HARD_CAP = 1_000_000
TIERS = ('S', 'A', 'B', 'C', 'D')
SEPARATION_KEYS = ('mining_hub', 'manufacturing_hub', 'megacomplex')


def nearest_rank(values: Sequence[int | float], percentile: float) -> int | float | None:
    '''Return the nearest-rank percentile (percentile is in the range 0..100).'''
    if not values:
        return None
    if not 0 <= percentile <= 100:
        raise ValueError('percentile must be between 0 and 100')
    ordered = sorted(values)
    if percentile == 0:
        return ordered[0]
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


_nearest_rank = nearest_rank


def default_stride(chunks_total: int, max_systems: int) -> int:
    '''Choose an even sampling stride targeting max_systems/1000 chunks.'''
    desired_chunks = max(1, max_systems // 1000)
    return max(1, math.ceil(chunks_total / desired_chunks))


def select_chunk_ordinals(
    chunk_rows: Iterable[tuple[int, int]], max_systems: int, stride: int,
) -> list[int]:
    '''Select ordinals 0, stride, 2*stride... without exceeding max_systems.'''
    chosen: list[int] = []
    systems = 0
    for ordinal, chunk_systems in sorted(chunk_rows):
        if ordinal % stride:
            continue
        if systems + chunk_systems > max_systems:
            break
        chosen.append(ordinal)
        systems += chunk_systems
    return chosen


_select_chunk_ordinals = select_chunk_ordinals


class CalibrationAggregate:
    '''Bounded calibration counters plus the values required for quantiles.'''

    def __init__(self) -> None:
        self.systems = 0
        self.scores = {key: array('h') for key in model.ARCHETYPE_KEYS}
        self.confidences = {key: array('d') for key in model.ARCHETYPE_KEYS}
        self.tier_histograms = {
            key: {tier: 0 for tier in TIERS} for key in model.ARCHETYPE_KEYS
        }
        self.primary_counts = {key: 0 for key in model.ARCHETYPE_KEYS}
        self.secondary_counts = {key: 0 for key in model.ARCHETYPE_KEYS}
        self.secondary_counts['none'] = 0
        self.best_tier_histogram = {tier: 0 for tier in TIERS}
        self.summary_confidences = array('d')
        self.separation_primary_counts = {key: 0 for key in SEPARATION_KEYS}
        self.two_or_more_separation = 0
        self.all_three_separation = 0
        self.pairwise_primary_runner_up = {
            f'{primary}->{secondary}': 0
            for primary in SEPARATION_KEYS
            for secondary in SEPARATION_KEYS
            if primary != secondary
        }

    def add(self, vectors: model.SystemVectors) -> None:
        fits = model.fit_all(vectors)
        summary = model.summarise(fits)
        fits_by_key = {fit.key: fit for fit in fits}

        self.systems += 1
        for fit in fits:
            self.scores[fit.key].append(fit.score)
            self.confidences[fit.key].append(fit.confidence)
            self.tier_histograms[fit.key][fit.tier] += 1

        primary = summary['primary_archetype']
        secondary = summary['secondary_archetype']
        self.primary_counts[primary] += 1
        self.secondary_counts[secondary if secondary is not None else 'none'] += 1
        self.best_tier_histogram[summary['best_tier']] += 1
        self.summary_confidences.append(summary['archetype_confidence'])

        if primary in self.separation_primary_counts:
            self.separation_primary_counts[primary] += 1
        separation_good = sum(
            fits_by_key[key].tier in {'S', 'A', 'B'} for key in SEPARATION_KEYS
        )
        if separation_good >= 2:
            self.two_or_more_separation += 1
        if separation_good == len(SEPARATION_KEYS):
            self.all_three_separation += 1
        pair = f'{primary}->{secondary}'
        if pair in self.pairwise_primary_runner_up:
            self.pairwise_primary_runner_up[pair] += 1

    def result(self) -> dict:
        per_archetype = {}
        for key in model.ARCHETYPE_KEYS:
            scores = self.scores[key]
            confidences = self.confidences[key]
            per_archetype[key] = {
                'count': len(scores),
                'score_min': min(scores) if scores else None,
                'score_p10': nearest_rank(scores, 10),
                'score_p50': nearest_rank(scores, 50),
                'score_p90': nearest_rank(scores, 90),
                'score_max': max(scores) if scores else None,
                'score_mean': round(sum(scores) / len(scores), 3) if scores else None,
                'tier_histogram': self.tier_histograms[key],
                'confidence_p10': nearest_rank(confidences, 10),
                'confidence_p50': nearest_rank(confidences, 50),
                'confidence_p90': nearest_rank(confidences, 90),
            }
        below = sum(value < 0.1 for value in self.summary_confidences)
        return {
            'per_archetype': per_archetype,
            'primary_counts': self.primary_counts,
            'secondary_counts': self.secondary_counts,
            'best_tier_histogram': self.best_tier_histogram,
            'archetype_confidence': {
                'p10': nearest_rank(self.summary_confidences, 10),
                'p50': nearest_rank(self.summary_confidences, 50),
                'p90': nearest_rank(self.summary_confidences, 90),
                'share_below_0_1': round(below / self.systems, 6) if self.systems else 0.0,
            },
            'separation': {
                'primary_counts': self.separation_primary_counts,
                'systems_with_two_or_more_at_tier_B_or_better': self.two_or_more_separation,
                'systems_with_all_three_at_tier_B_or_better': self.all_three_separation,
                'pairwise_primary_runner_up': self.pairwise_primary_runner_up,
            },
        }


def aggregate_vectors(vectors: Iterable[model.SystemVectors]) -> dict:
    aggregate = CalibrationAggregate()
    for vector in vectors:
        aggregate.add(vector)
    return aggregate.result()


_aggregate_vectors = aggregate_vectors


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--max-systems', type=int, default=200_000)
    parser.add_argument('--stride', type=int)
    parser.add_argument('--statement-timeout-ms', type=int, default=60_000)
    parser.add_argument('--database-url-env', default=DEFAULT_DATABASE_URL_ENV)
    parser.add_argument('--allow-unpublished', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.max_systems <= MAX_SYSTEMS_HARD_CAP:
        parser.error(f'--max-systems must be between 1 and {MAX_SYSTEMS_HARD_CAP}')
    if args.stride is not None and args.stride < 1:
        parser.error('--stride must be at least 1')
    if args.statement_timeout_ms < 1:
        parser.error('--statement-timeout-ms must be at least 1')
    if not args.database_url_env:
        parser.error('--database-url-env must not be empty')
    return args


def _generation(connection, generation_key: str):
    return connection.execute(
        '''SELECT g.derived_generation_id::text,g.lifecycle_state,
                  g.generation_key,g.expected_systems,
                  EXISTS(
                      SELECT 1 FROM v3_meta.current_derived_generation c
                       WHERE c.derived_generation_id=g.derived_generation_id
                  ) AS is_current
             FROM v3_meta.derived_generation g
            WHERE g.generation_key=%s''',
        (generation_key,),
    ).fetchone()


def _chunk_rows(connection, generation_id: str) -> list[tuple[int, int]]:
    rows = connection.execute(
        '''SELECT chunk_ordinal,systems
             FROM v3_derived.build_chunk
            WHERE derived_generation_id=%s
            ORDER BY chunk_ordinal''',
        (generation_id,),
    ).fetchall()
    return [(int(ordinal), int(systems)) for ordinal, systems in rows]


def _run(connection, args) -> tuple[int, dict | None]:
    connection.read_only = True
    connection.execute(
        "SELECT set_config('statement_timeout',%s,false)",
        (f'{args.statement_timeout_ms}ms',),
    )
    generation = _generation(connection, args.generation_key)
    if generation is None:
        connection.rollback()
        print('generation not found', file=sys.stderr)
        return 3, None

    generation_id, lifecycle_state, generation_key, expected_systems, is_current = generation
    is_current = lifecycle_state == 'PUBLISHED' and bool(is_current)
    if not args.allow_unpublished and (
        lifecycle_state != 'PUBLISHED' or not is_current
    ):
        connection.rollback()
        print('generation is not the current published generation', file=sys.stderr)
        return 3, None

    chunks = _chunk_rows(connection, generation_id)
    stride = args.stride or default_stride(len(chunks), args.max_systems)
    ordinals = select_chunk_ordinals(chunks, args.max_systems, stride)
    connection.commit()
    if not ordinals:
        print(
            'calibration sample is empty: raise --max-systems '
            '(at least one full chunk must fit)',
            file=sys.stderr,
        )
        return 5, None

    aggregate = CalibrationAggregate()
    for ordinal in ordinals:
        vectors = archetype_builder._read_chunk_vectors(
            connection, generation_id, ordinal,
        )
        for vector in vectors.values():
            aggregate.add(vector)
        connection.commit()
    if aggregate.systems == 0:
        print(
            'calibration sample is empty: raise --max-systems '
            '(at least one full chunk must fit)',
            file=sys.stderr,
        )
        return 5, None

    aggregation = aggregate.result()
    sample = {
        'chunks_total': len(chunks),
        'chunks_sampled': len(ordinals),
        'stride': stride,
        'systems_sampled': aggregate.systems,
        'max_systems': args.max_systems,
        'ordinals_first_last': [ordinals[0], ordinals[-1]] if ordinals else [None, None],
    }
    result = {
        'probe_version': PROBE_VERSION,
        'generation': {
            'generation_key': generation_key,
            'derived_generation_id': generation_id,
            'lifecycle_state': lifecycle_state,
            'is_current_published_pointer': is_current,
            'expected_systems': int(expected_systems),
        },
        'sample': sample,
        'coefficients': archetype_builder._coefficients(),
        'archetype_version': model.ARCHETYPE_VERSION,
        'anchors': archetype_builder._anchors(),
        'code_identity': archetype_builder.code_identity(),
        **aggregation,
        'read_only': True,
        'writes_performed': False,
    }
    return 0, result


def main(argv=None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    dsn = os.environ.get(args.database_url_env)
    if not dsn:
        print(f'database URL environment variable {args.database_url_env} is missing', file=sys.stderr)
        return 2

    try:
        import psycopg

        with psycopg.connect(dsn, autocommit=False) as connection:
            exit_code, result = _run(connection, args)
    except psycopg.Error as exc:
        print(f'database error: {type(exc).__name__}', file=sys.stderr)
        return 4

    if exit_code:
        return exit_code
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
