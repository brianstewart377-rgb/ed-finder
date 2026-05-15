"""Focused Stage 7D tests for ratings rerank explanation fields.

These tests exercise the real endpoint function with a fake asyncpg pool so
the contribution contract is covered without requiring local PostgreSQL.
DB-backed integration tests still cover the route wiring when CI services are
available.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from routers.ratings import RerankRequest, ratings_rerank
from models import RerankWeights


class FakeAcquire:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetch(self, *_args, **_kwargs):
        return self.rows


class FakePool:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def acquire(self):
        return FakeAcquire(self.rows)


@pytest.mark.asyncio
async def test_rerank_contributions_are_additive_pre_confidence_and_sorted():
    rows = [
        {
            'id64': 1001,
            'original_score': 70,
            'eco_score': 80,
            'slots': 0,
            'strategic': 0,
            'safety': 20,
            'terraforming': 0,
            'diversity': 0,
            'confidence': 0.5,
            'rationale': 'Stored rationale A',
            'economy_suggestion': 'Extraction',
        },
        {
            'id64': 1002,
            'original_score': 65,
            'eco_score': 60,
            'slots': 0,
            'strategic': 0,
            'safety': 60,
            'terraforming': 0,
            'diversity': 0,
            'confidence': None,
            'rationale': 'Stored rationale B',
            'economy_suggestion': 'Extraction',
        },
    ]

    response = await ratings_rerank.__wrapped__(
        request=None,
        body=RerankRequest(
            id64s=[1001, 1002],
            weights=RerankWeights(
                economy=0.5,
                slots=0,
                strategic=0,
                safety=0.5,
                terraforming=0,
                diversity=0,
            ),
            economy='Extraction',
        ),
        pool=FakePool(rows),
    )

    assert [row['id64'] for row in response['results']] == [1002, 1001]
    assert [row['reranked_score'] for row in response['results']] == [60, 25]

    row = next(item for item in response['results'] if item['id64'] == 1001)
    assert {'id64', 'reranked_score', 'original_score', 'confidence', 'rationale', 'economy_used'} <= set(row)
    assert row['contributions']['economy'] == 40.0
    assert row['contributions']['safety'] == 10.0
    assert row['reranked_score'] == 25
    assert row['signals']['economy_score'] == 80.0
    assert row['signals']['orbital_safety'] == 20.0
    assert row['signals']['confidence'] == 0.5

