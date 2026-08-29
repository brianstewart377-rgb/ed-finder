"""Unit tests for the V3 journal event contract (30-event allowlist + strip).

The frozen 30-event allowlist is the single source of truth (Global
Constraints of the implementation plan); per-event payload field allowlists
mirror frontend/src/lib/journalParsing/journalParser.ts exactly plus the
V3 client-attached GameVersion/GameBuild fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest

from edfinder_api.journal.event_contract import (
    EVENT_PAYLOAD_ALLOWLIST,
    JOURNAL_EVENT_ALLOWLIST,
    strip_payload,
)

FROZEN_ALLOWLIST = {
    'ApproachBody', 'CarrierJump', 'CodexEntry', 'Commander', 'Died',
    'Disembark', 'Docked', 'Embark', 'Fileheader', 'FSDJump', 'FSDTarget',
    'FSSAllBodiesFound', 'FSSBodySignals', 'FSSDiscoveryScan', 'LeaveBody',
    'Liftoff', 'LoadGame', 'Location', 'MultiSellExplorationData',
    'NavRoute', 'NavRouteClear', 'Resurrect', 'SAAScanComplete',
    'SAASignalsFound', 'Scan', 'ScanOrganic', 'Screenshot',
    'SellExplorationData', 'SellOrganicData', 'Touchdown',
}


def test_allowlist_matches_the_frozen_30_event_list():
    assert len(JOURNAL_EVENT_ALLOWLIST) == 30
    assert set(JOURNAL_EVENT_ALLOWLIST) == FROZEN_ALLOWLIST


def test_every_event_has_a_payload_allowlist_entry():
    assert set(EVENT_PAYLOAD_ALLOWLIST.keys()) == set(JOURNAL_EVENT_ALLOWLIST)
    for event_type in JOURNAL_EVENT_ALLOWLIST:
        assert isinstance(EVENT_PAYLOAD_ALLOWLIST[event_type], frozenset)


def test_gameversion_and_gamebuild_allowed_on_every_event():
    for event_type in JOURNAL_EVENT_ALLOWLIST:
        allowed = EVENT_PAYLOAD_ALLOWLIST[event_type]
        assert 'GameVersion' in allowed, event_type
        assert 'GameBuild' in allowed, event_type


def test_strip_payload_keeps_only_allowlisted_fields():
    stripped, removed = strip_payload('Scan', {'BodyName': 'A', 'SystemAddress': 1, 'Secret': 42})
    assert removed == 1
    assert 'Secret' not in stripped
    assert stripped == {'BodyName': 'A', 'SystemAddress': 1}


def test_strip_payload_counts_every_removed_key():
    stripped, removed = strip_payload('FSDJump', {
        'StarSystem': 'Sol', 'SystemAddress': 10477373803,
        'JumpDist': 0.0, 'FuelLevel': 1.0, 'Credits': 999999,
    })
    assert removed == 1
    assert 'Credits' not in stripped
    assert stripped['StarSystem'] == 'Sol'


def test_strip_payload_keeps_parser_fields_exactly():
    # ScanOrganic parser fields include the raw journal 'Body' name plus
    # 'BodyID'; the server allowlist mirrors that exactly.
    stripped, removed = strip_payload('ScanOrganic', {
        'ScanType': 'Log', 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
        'Variant': 'V1', 'SystemAddress': 10, 'Body': 3, 'BodyID': 3,
        'BodyName': 'Foo 1', 'UntrustedField': 'x',
    })
    assert removed == 1
    assert stripped == {
        'ScanType': 'Log', 'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;',
        'Variant': 'V1', 'SystemAddress': 10, 'Body': 3, 'BodyID': 3,
        'BodyName': 'Foo 1',
    }


def test_strip_payload_allows_gameversion_gamebuild():
    stripped, removed = strip_payload('Scan', {'BodyName': 'A', 'GameVersion': '4.0', 'GameBuild': 'r12345'})
    assert removed == 0
    assert stripped['GameVersion'] == '4.0' and stripped['GameBuild'] == 'r12345'


def test_strip_payload_unknown_event_raises():
    with pytest.raises(ValueError):
        strip_payload('TotallyFakeEvent', {})


def test_navrouteclear_allowlist_is_empty_plus_attachments():
    allowed = EVENT_PAYLOAD_ALLOWLIST['NavRouteClear']
    assert allowed == frozenset({'GameVersion', 'GameBuild'})


def test_strip_payload_removes_non_allowlisted_loadgame_fields():
    stripped, removed = strip_payload('LoadGame', {'Commander': 'X', 'FID': 'F123', 'SquadronName': 'SQ'})
    # Commander/FID are allowlisted on LoadGame (identity events are
    # content-addressed and stay private); SquadronName is not a parser field.
    assert removed == 1
    assert stripped['Commander'] == 'X' and 'SquadronName' not in stripped


def test_exported_events_can_carry_the_sanitizer_system_name_fields():
    # Payload-allowlist gap regression (backend fix wave): the sanitizer
    # fail-closes on a missing system name for every non-sale exported type,
    # so CodexEntry / ScanOrganic / SAAScanComplete must be ABLE to carry
    # SystemName/StarSystem (plus CodexEntry's journal-native 'System').
    for event_type in ('CodexEntry', 'ScanOrganic', 'SAAScanComplete'):
        allowed = EVENT_PAYLOAD_ALLOWLIST[event_type]
        assert 'SystemName' in allowed, event_type
        assert 'StarSystem' in allowed, event_type
    assert 'System' in EVENT_PAYLOAD_ALLOWLIST['CodexEntry']
    # And the strip path actually keeps them.
    stripped, removed = strip_payload('SAAScanComplete', {
        'StarSystem': 'Sol', 'SystemName': 'Sol', 'BodyName': 'Earth',
        'SystemAddress': 1, 'BodyID': 2, 'Secret': 1,
    })
    assert removed == 1
    assert stripped['StarSystem'] == 'Sol' and stripped['SystemName'] == 'Sol'
