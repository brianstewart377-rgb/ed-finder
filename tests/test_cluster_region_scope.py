import pytest

from local_search import _resolve_slot_matches


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self):
        self.detail_query = ''
        self.detail_params = ()

    async def fetchrow(self, query, *params):
        return {'grid_cell_id': 100010001}

    async def fetch(self, query, *params):
        self.detail_query = query
        self.detail_params = params
        return []


class _Pool:
    def __init__(self):
        self.connection = _Connection()

    def acquire(self):
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_slot_matches_stay_inside_selected_galactic_region():
    pool = _Pool()

    await _resolve_slot_matches(
        pool,
        anchors=[{
            'anchor_id64': 42,
            'anchor_x': 1,
            'anchor_y': 2,
            'anchor_z': 3,
        }],
        slots_raw=[{
            'economies': ['Agriculture'],
            'min_score': 65,
            'label': 'Agriculture',
        }],
        galaxy_region_id=31,
    )

    assert 's.galaxy_region_id = $7' in pool.connection.detail_query
    assert pool.connection.detail_params[-1] == 31
