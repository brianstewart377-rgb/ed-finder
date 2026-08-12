from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from edfinder_api.powerplay.parser import (  # noqa: E402
    POWERPLAY_POWERS,
    cycle_start_for,
    parse_powerplay_event,
    project_commander_state,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


@pytest.mark.parametrize('power', POWERPLAY_POWERS)
def test_parses_every_march_2025_community_schema_power_name(power: str):
    parsed = parse_powerplay_event(
        {
            'event': 'Location',
            'SystemAddress': 10477373803,
            'StarSystem': 'Test',
            'ControllingPower': power,
            'Powers': [power],
            'PowerplayState': 'Fortified',
        },
        observed_at=utc('2025-03-20T08:00:00Z'),
        source_version='trailblazers-march-2025',
    )
    assert parsed is not None
    assert parsed.values['controlling_power'] == power
    assert parsed.values['powers'] == [power]
    assert parsed.value_provenance['controlling_power']['version'] == 'trailblazers-march-2025'


def test_raw_control_anomalies_are_not_clamped_rescaled_or_corrected():
    payload = {
        'event': 'FSDJump',
        'SystemAddress': '10477373803',
        'ControllingPower': 'Yuri Grom',
        'PowerplayStateControlProgress': 987654.321,
        'PowerplayStateReinforcement': -75,
        'PowerplayStateUndermining': 2**40,
        'Powers': ['Yuri Grom', 'Nakato Kaine'],
    }
    parsed = parse_powerplay_event(payload, observed_at=utc('2025-03-20T08:00:00Z'))
    assert parsed is not None
    assert parsed.system_address == 10477373803
    assert parsed.values['control_progress'] == 987654.321
    assert parsed.values['reinforcement_points'] == -75
    assert parsed.values['undermining_points'] == 2**40
    assert parsed.source_payload == payload


def test_cycle_boundary_is_thursday_0700_utc():
    assert cycle_start_for(utc('2025-03-20T06:59:59Z')) == utc('2025-03-13T07:00:00Z')
    assert cycle_start_for(utc('2025-03-20T07:00:00Z')) == utc('2025-03-20T07:00:00Z')
    assert cycle_start_for(utc('2025-03-27T06:59:59Z')) == utc('2025-03-20T07:00:00Z')
    assert cycle_start_for(utc('2025-03-27T07:00:00Z')) == utc('2025-03-27T07:00:00Z')


def test_unoccupied_conflict_progress_keeps_raw_per_power_shape():
    raw = {'Felicia Winters': 1.25, 'Yuri Grom': -0.5}
    parsed = parse_powerplay_event(
        {
            'event': 'Location',
            'SystemAddress': 99,
            'PowerplayState': 'Unoccupied',
            'PowerplayConflictProgress': raw,
        },
        observed_at=utc('2025-03-20T07:00:00Z'),
    )
    assert parsed is not None
    assert parsed.values['control_progress'] == raw
    assert parsed.value_provenance['control_progress']['journal_field'] == 'PowerplayConflictProgress'


def _personal(event: str, timestamp: str, **values: object):
    return parse_powerplay_event(
        {'event': event, **values},
        observed_at=utc(timestamp),
        source_version='test-v1',
    )


def test_personal_state_transitions_rebuild_pledge_rank_and_merits():
    events = [
        _personal('PowerplayJoin', '2025-03-20T08:00:00Z', Power='Edmund Mahon'),
        _personal('PowerplayRank', '2025-03-20T09:00:00Z', Power='Edmund Mahon', Rank=4),
        _personal(
            'PowerplayMerits', '2025-03-20T10:00:00Z',
            Power='Edmund Mahon', MeritsGained=125, TotalMerits=9125,
        ),
        _personal(
            'PowerplayDefect', '2025-03-20T11:00:00Z',
            FromPower='Edmund Mahon', ToPower='Felicia Winters',
        ),
        _personal('PowerplayRank', '2025-03-20T12:00:00Z', Power='Felicia Winters', Rank=1),
    ]
    state = project_commander_state([event for event in events if event is not None])
    assert state.pledge == 'Felicia Winters'
    assert state.rank == 1
    assert state.merits is None
    assert set(state.value_provenance) == {'pledge', 'rank', 'merits'}


def test_powerplay_migration_is_isolated_and_versions_every_value():
    migration = (ROOT / 'sql' / '046_powerplay_observations.sql').read_text()
    assert 'CREATE TABLE IF NOT EXISTS powerplay_observations' in migration
    assert 'CREATE TABLE IF NOT EXISTS powerplay_cycles' in migration
    assert 'CREATE TABLE IF NOT EXISTS commander_powerplay_state' in migration
    assert 'commander_key' in migration
    assert 'source_version' in migration
    assert 'value_provenance' in migration
    assert 'REFERENCES systems' not in migration
    assert 'INSERT INTO systems' not in migration
    assert 'UPDATE systems' not in migration
