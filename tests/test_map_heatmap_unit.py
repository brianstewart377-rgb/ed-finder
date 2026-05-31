"""Focused no-DB coverage for map heatmap economy SQL selection."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


os.environ.setdefault('CORS_ORIGINS', 'http://test')

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'apps' / 'api' / 'src'))


class _FakeConn:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch(self, query: str, *args, **kwargs) -> list[dict]:
        self.queries.append(query)
        return [{'cx': 0, 'cy': 0, 'cz': 0, 'n': 1, 'avg_score': 10, 'max_score': 20}]


class _AcquireContext:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.conn)


def _map_heatmap_handler():
    from routers.map import map_heatmap

    return map_heatmap.__wrapped__


@pytest.mark.parametrize(
    ('economy', 'expected_column'),
    [
        ('HighTech', 'max_hightech'),
        ('High Tech', 'max_hightech'),
        ('high-tech', 'max_hightech'),
        ('tourism', 'max_tourism'),
    ],
)
async def test_map_heatmap_uses_canonical_economy_mv_column(economy, expected_column):
    pool = _FakePool()
    result = await _map_heatmap_handler()(
        request=None,
        voxel_size=200,
        min_systems=1,
        economy=economy,
        pool=pool,
        redis=None,
    )

    query = pool.conn.queries[0]
    assert expected_column in query
    assert f'{expected_column} AS max_score' in query
    assert f'AND {expected_column} IS NOT NULL' in query
    assert result['economy'] == economy


async def test_map_heatmap_rejects_invalid_economy():
    pool = _FakePool()
    with pytest.raises(HTTPException) as exc_info:
        await _map_heatmap_handler()(
            request=None,
            voxel_size=200,
            min_systems=1,
            economy='NotAnEconomy',
            pool=pool,
            redis=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == 'Invalid economy: NotAnEconomy'
    assert pool.conn.queries == []
