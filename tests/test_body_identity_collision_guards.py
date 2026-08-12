from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / 'scripts' / 'dev'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_environment_seed as review_seed  # noqa: E402


class _OwnershipCheckConnection:
    def __init__(self, existing_rows: list[dict[str, int]]):
        self.existing_rows = existing_rows
        self.fetch_calls: list[tuple[str, list[int]]] = []
        self.executemany_calls: list[tuple[str, list[tuple]]] = []

    async def fetch(self, query: str, body_ids: list[int]):
        self.fetch_calls.append((query, body_ids))
        requested_ids = set(body_ids)
        return [row for row in self.existing_rows if row['id'] in requested_ids]

    async def executemany(self, query: str, rows: list[tuple]):
        self.executemany_calls.append((query, rows))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_seed_rejects_cross_system_body_id_before_insert(monkeypatch):
    incoming_system = review_seed.REVIEW_SYSTEMS[0]
    body_id = int(incoming_system['bodies'][0]['id'])
    existing_system_id64 = int(incoming_system['id64']) + 999
    conn = _OwnershipCheckConnection(
        [{'id': body_id, 'system_id64': existing_system_id64}]
    )
    monkeypatch.setattr(review_seed, 'REVIEW_SYSTEMS', (incoming_system,))

    with pytest.raises(review_seed.ReviewSeedError, match='refusing to re-parent'):
        await review_seed._upsert_bodies(conn)

    assert len(conn.fetch_calls) == 1
    assert conn.executemany_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_seed_allows_same_system_body_update_with_sql_backstop(monkeypatch):
    incoming_system = review_seed.REVIEW_SYSTEMS[0]
    body_id = int(incoming_system['bodies'][0]['id'])
    system_id64 = int(incoming_system['id64'])
    conn = _OwnershipCheckConnection(
        [{'id': body_id, 'system_id64': system_id64}]
    )
    monkeypatch.setattr(review_seed, 'REVIEW_SYSTEMS', (incoming_system,))

    await review_seed._upsert_bodies(conn)

    assert len(conn.executemany_calls) == 1
    query, rows = conn.executemany_calls[0]
    assert 'WHERE bodies.system_id64 = EXCLUDED.system_id64' in query
    assert rows[0][0:2] == (body_id, system_id64)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_seed_rejects_cross_system_body_id_inside_one_batch():
    conn = _OwnershipCheckConnection([])

    with pytest.raises(review_seed.ReviewSeedError, match='multiple review systems'):
        await review_seed._validate_body_ownership(
            conn,
            [(42, 1001), (42, 1002)],
        )

    assert conn.fetch_calls == []


@pytest.mark.unit
def test_all_executable_body_writers_keep_an_ownership_guard():
    literal_writer_paths = {
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / 'apps', ROOT / 'scripts')
        for path in base.rglob('*.py')
        if re.search(
            r'\binsert\s+into\s+bodies\b',
            path.read_text(encoding='utf-8'),
            flags=re.IGNORECASE,
        )
    }

    assert literal_writer_paths == {
        'apps/eddn/src/eddn_listener.py',
        'scripts/dev/review_environment_seed.py',
    }

    eddn_source = (ROOT / 'apps' / 'eddn' / 'src' / 'eddn_listener.py').read_text(
        encoding='utf-8'
    )
    spansh_source = (ROOT / 'apps' / 'importer' / 'src' / 'import_spansh.py').read_text(
        encoding='utf-8'
    )
    review_seed_source = (SCRIPT_DIR / 'review_environment_seed.py').read_text(
        encoding='utf-8'
    )
    preview_seed_source = (ROOT / 'sql' / 'seed_preview.sql').read_text(encoding='utf-8')

    assert 'bodies.system_id64 = EXCLUDED.system_id64' in eddn_source
    assert "'bodies', BODY_COLS" in spansh_source
    assert "guard_col='system_id64'" in spansh_source
    assert 'await _validate_body_ownership(' in review_seed_source
    assert 'WHERE bodies.system_id64 = EXCLUDED.system_id64' in review_seed_source
    assert 'ON CONFLICT (id) DO NOTHING' in preview_seed_source
