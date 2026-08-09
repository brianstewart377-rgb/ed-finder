from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from exploration.api_models import ExplorationImportRequest  # noqa: E402
from exploration import store  # noqa: E402

pytestmark = pytest.mark.db


def _sync_key() -> str:
    return f'synckey_{uuid4().hex[:24]}'


async def test_import_stages_rows_and_dedupes_on_replay(pool):
    sync_key = _sync_key()
    observation_key = uuid4().hex
    request = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'source': 'journal',
        'observations': [{
            'observation_key': observation_key,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:00:00Z',
            'system_id64': 12345,
            'system_name': 'Store Test System',
            'body_id': 1,
            'body_name': 'Store Test System 1',
            'payload': {'PlanetClass': 'Rocky body'},
        }],
    })

    receipt = await store.import_exploration_batch(pool, request)
    assert receipt.status == 'succeeded'
    assert receipt.summary.observations_staged == 1
    assert receipt.summary.duplicates_skipped == 0

    replay_receipt = await store.import_exploration_batch(pool, request)
    assert replay_receipt.summary.observations_staged == 0
    assert replay_receipt.summary.duplicates_skipped == 1


async def test_get_exploration_facts_returns_only_matching_sync_key(pool):
    sync_key_a = _sync_key()
    sync_key_b = _sync_key()
    for sync_key in (sync_key_a, sync_key_b):
        await store.import_exploration_batch(pool, ExplorationImportRequest.model_validate({
            'sync_key': sync_key,
            'source': 'journal',
            'observations': [{
                'observation_key': uuid4().hex,
                'event_type': 'FSDJump',
                'observed_at': '2026-08-08T09:00:00Z',
                'system_id64': 54321,
                'system_name': 'Visited System',
                'payload': {},
            }],
        }))

    facts = await store.get_exploration_facts(pool, sync_key_a)
    assert facts.sync_key == sync_key_a
    assert len(facts.facts) == 1
    assert facts.facts[0].system_id64 == 54321
    assert facts.facts[0].source == 'journal'
    assert facts.count == 1
    assert facts.truncated is False


async def test_get_exploration_facts_sets_truncated_when_more_rows_exist(pool):
    sync_key = _sync_key()
    total_rows = 5
    page_limit = 3
    observations = [
        {
            'observation_key': uuid4().hex,
            'event_type': 'FSDJump',
            'observed_at': f'2026-08-08T09:{i:02d}:00Z',
            'system_id64': 60000 + i,
            'system_name': f'Truncation Test System {i}',
            'payload': {},
        }
        for i in range(total_rows)
    ]
    await store.import_exploration_batch(pool, ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': observations,
    }))

    facts = await store.get_exploration_facts(pool, sync_key, limit=page_limit)
    assert facts.count == page_limit
    assert len(facts.facts) == page_limit
    assert facts.truncated is True


async def test_get_exploration_facts_not_truncated_when_fewer_rows_than_limit(pool):
    sync_key = _sync_key()
    await store.import_exploration_batch(pool, ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [{
            'observation_key': uuid4().hex,
            'event_type': 'FSDJump',
            'observed_at': '2026-08-08T09:00:00Z',
            'system_id64': 70000,
            'system_name': 'Not Truncated System',
            'payload': {},
        }],
    }))

    facts = await store.get_exploration_facts(pool, sync_key, limit=50)
    assert facts.count == 1
    assert facts.truncated is False


async def test_import_raises_rate_limit_error_over_daily_budget(pool, monkeypatch):
    monkeypatch.setattr(store, 'MAX_DAILY_ROWS_PER_SYNC_KEY', 1)
    sync_key = _sync_key()
    first = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [{
            'observation_key': uuid4().hex,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:00:00Z',
            'system_id64': 11111,
            'payload': {},
        }],
    })
    await store.import_exploration_batch(pool, first)

    second = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [{
            'observation_key': uuid4().hex,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:05:00Z',
            'system_id64': 22222,
            'payload': {},
        }],
    })
    with pytest.raises(store.ExplorationImportRateLimitError):
        await store.import_exploration_batch(pool, second)


async def test_import_budget_charges_only_novel_keys_not_overlap(pool, monkeypatch):
    # Budget is 15: first batch of 10 rows fits under budget. A later batch that
    # re-submits all 10 of those same observation_keys plus 5 genuinely new ones
    # should succeed, because only the 5 novel rows count toward the budget
    # (10 + 10 + 5 = 25 > 15 would wrongly reject under the old raw-batch-size
    # check, but 10 + 5 = 15 is exactly at budget under the corrected check).
    monkeypatch.setattr(store, 'MAX_DAILY_ROWS_PER_SYNC_KEY', 15)
    sync_key = _sync_key()

    first_keys = [uuid4().hex for _ in range(10)]
    first_request = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [
            {
                'observation_key': key,
                'event_type': 'Scan',
                'observed_at': f'2026-08-08T09:{i:02d}:00Z',
                'system_id64': 30000 + i,
                'payload': {},
            }
            for i, key in enumerate(first_keys)
        ],
    })
    first_receipt = await store.import_exploration_batch(pool, first_request)
    assert first_receipt.summary.observations_staged == 10

    new_keys = [uuid4().hex for _ in range(5)]
    overlap_observations = [
        {
            'observation_key': key,
            'event_type': 'Scan',
            'observed_at': f'2026-08-08T10:{i:02d}:00Z',
            'system_id64': 30000 + i,
            'payload': {},
        }
        for i, key in enumerate(first_keys)
    ]
    new_observations = [
        {
            'observation_key': key,
            'event_type': 'Scan',
            'observed_at': f'2026-08-08T11:{i:02d}:00Z',
            'system_id64': 40000 + i,
            'payload': {},
        }
        for i, key in enumerate(new_keys)
    ]
    second_request = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': overlap_observations + new_observations,
    })

    second_receipt = await store.import_exploration_batch(pool, second_request)
    assert second_receipt.summary.observations_staged == 5
    assert second_receipt.summary.duplicates_skipped == 10
