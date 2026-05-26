import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
for path in (API_SRC, IMPORTER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from station_body_resolver import (  # noqa: E402
    build_station_body_link_rows,
    classify_station_lane,
    is_transient_non_slot_station_type,
    normalise_station_type_label,
    resolve_station_body_association,
)
from backfill_station_body_links import summarize  # noqa: E402


BODIES = [
    {'id': 1, 'system_id64': 42, 'name': 'Resolver Test A', 'distance_from_star': 0},
    {'id': 2, 'system_id64': 42, 'name': 'Resolver Test A 1', 'distance_from_star': 120.0},
    {'id': 3, 'system_id64': 42, 'name': 'Resolver Test A 2', 'distance_from_star': 240.0},
]


def test_exact_body_name_maps_confirmed_exact_orbital():
    link = resolve_station_body_association({
        'id': 100,
        'market_id': 100,
        'system_id64': 42,
        'name': 'Holden Orbital',
        'station_type': 'Coriolis',
        'body_name': 'Resolver Test A 1',
    }, BODIES)

    assert link.body_id == 2
    assert link.body_name == 'Resolver Test A 1'
    assert link.lane == 'orbital'
    assert link.association_status == 'confirmed'
    assert link.association_confidence == 'exact'
    assert link.association_source == 'resolver_body_name'


def test_exact_body_id_maps_confirmed_exact_surface():
    link = resolve_station_body_association({
        'id': 101,
        'market_id': 101,
        'system_id64': 42,
        'name': 'Surface Port',
        'station_type': 'PlanetaryPort',
        'body_id': 3,
        'body_name': 'Wrong Body Name',
    }, BODIES)

    assert link.body_id == 3
    assert link.body_name == 'Resolver Test A 2'
    assert link.lane == 'surface'
    assert link.association_status == 'confirmed'
    assert link.association_confidence == 'exact'
    assert link.association_source == 'resolver_body_id'


def test_unique_distance_match_maps_inferred_strong():
    link = resolve_station_body_association({
        'id': 102,
        'market_id': 102,
        'system_id64': 42,
        'name': 'Distance Station',
        'station_type': 'Outpost',
        'distance_from_star': 240.005,
    }, BODIES)

    assert link.body_id == 3
    assert link.lane == 'orbital'
    assert link.association_status == 'inferred'
    assert link.association_confidence == 'strong_inference'
    assert link.association_source == 'resolver_distance'
    assert 'Unique distance_from_star match' in (link.resolver_notes or '')


def test_ambiguous_distance_match_remains_unresolved():
    link = resolve_station_body_association({
        'id': 103,
        'market_id': 103,
        'system_id64': 42,
        'name': 'Ambiguous Station',
        'station_type': 'Outpost',
        'distance_from_star': 120.0,
    }, [
        *BODIES,
        {'id': 4, 'system_id64': 42, 'name': 'Resolver Test A 3', 'distance_from_star': 120.004},
    ])

    assert link.body_id is None
    assert link.lane == 'orbital'
    assert link.association_status == 'unresolved'
    assert link.association_confidence == 'unresolved'
    assert link.association_source == 'resolver_distance'
    assert 'matched 2 bodies' in (link.resolver_notes or '')


def test_no_body_match_remains_visible_as_unresolved():
    link = resolve_station_body_association({
        'id': 104,
        'market_id': 104,
        'system_id64': 42,
        'name': 'Lost Station',
        'station_type': 'Outpost',
    }, BODIES)

    assert link.body_id is None
    assert link.body_name is None
    assert link.association_status == 'unresolved'
    assert link.lane == 'orbital'


def test_blank_body_name_without_unique_distance_remains_unresolved():
    link = resolve_station_body_association({
        'id': 110,
        'market_id': 110,
        'system_id64': 42,
        'name': 'No Evidence Station',
        'station_type': 'Planetary Port',
        'body_name': ' ',
    }, BODIES)

    assert link.body_id is None
    assert link.body_name is None
    assert link.lane == 'surface'
    assert link.association_status == 'unresolved'
    assert link.association_confidence == 'unresolved'


def test_fleet_carrier_and_megaship_do_not_become_slot_occupiers():
    carrier = resolve_station_body_association({
        'id': 105,
        'system_id64': 42,
        'station_type': 'FleetCarrier',
        'body_name': 'Resolver Test A 1',
    }, BODIES)
    megaship = resolve_station_body_association({
        'id': 106,
        'system_id64': 42,
        'station_type': 'MegaShip',
        'body_name': 'Resolver Test A 1',
    }, BODIES)

    assert carrier.body_id is None
    assert carrier.association_status == 'unresolved'
    assert carrier.association_source == 'transient_non_slot'
    assert carrier.lane == 'unknown'
    assert 'not treated as permanent colony-slot' in (carrier.resolver_notes or '')
    assert megaship.body_id is None
    assert megaship.association_status == 'unresolved'
    assert megaship.lane == 'unknown'


def test_build_rows_skips_transient_non_slot_station_types():
    rows = build_station_body_link_rows([
        {
            'id': 201,
            'system_id64': 42,
            'station_type': 'FleetCarrier',
            'body_name': 'Resolver Test A 1',
        },
        {
            'id': 202,
            'system_id64': 42,
            'station_type': 'Carrier',
            'body_name': 'Resolver Test A 1',
        },
        {
            'id': 203,
            'system_id64': 42,
            'station_type': 'MegaShip',
            'body_name': 'Resolver Test A 2',
        },
        {
            'id': 204,
            'system_id64': 42,
            'station_type': 'Orbis',
            'body_name': 'Resolver Test A 1',
        },
    ], BODIES)

    assert [row.station_id for row in rows] == [204]
    assert rows[0].body_id == 2


def test_station_type_lane_classification():
    assert classify_station_lane('Coriolis')[0] == 'orbital'
    assert classify_station_lane('Orbis')[0] == 'orbital'
    assert classify_station_lane('Ocellus')[0] == 'orbital'
    assert classify_station_lane('Outpost')[0] == 'orbital'
    assert classify_station_lane('AsteroidBase')[0] == 'orbital'
    assert classify_station_lane('PlanetaryPort')[0] == 'surface'
    assert classify_station_lane('PlanetaryOutpost')[0] == 'surface'
    assert classify_station_lane('Unknown')[0] == 'unknown'


def test_station_type_lane_classification_accepts_edsm_labels():
    assert classify_station_lane('Coriolis Starport')[0] == 'orbital'
    assert classify_station_lane('Orbis Starport')[0] == 'orbital'
    assert classify_station_lane('Ocellus Starport')[0] == 'orbital'
    assert classify_station_lane('Planetary settlement')[0] == 'surface'
    assert classify_station_lane('Planetary Outpost')[0] == 'surface'
    assert classify_station_lane('Fleet Carrier')[0] == 'unknown'
    assert is_transient_non_slot_station_type('Carrier') is True


def test_station_type_lane_classification_is_not_fuzzy():
    assert normalise_station_type_label('Coriolis Logistics') == 'Unknown'
    assert normalise_station_type_label('Planetary Warehouse') == 'Unknown'
    assert classify_station_lane('Coriolis Logistics')[0] == 'unknown'
    assert classify_station_lane('Planetary Warehouse')[0] == 'unknown'


def test_resolver_accepts_raw_station_evidence_aliases():
    link = resolve_station_body_association({
        'id': 111,
        'market_id': 111,
        'system_id64': 42,
        'name': 'Raw Evidence Station',
        'stationType': 'Planetary Settlement',
        'body': {'name': 'Resolver Test A 2'},
        'distanceToArrival': 0,
    }, BODIES)

    assert link.body_id == 3
    assert link.lane == 'surface'
    assert link.association_status == 'confirmed'
    assert link.association_confidence == 'exact'


def test_existing_confirmed_link_is_not_downgraded_by_weaker_inference():
    link = resolve_station_body_association(
        {
            'id': 107,
            'market_id': 107,
            'system_id64': 42,
            'station_type': 'Outpost',
            'distance_from_star': 120.0,
        },
        BODIES,
        existing_link={
            'station_id': 107,
            'market_id': 107,
            'system_id64': 42,
            'body_id': 3,
            'body_name': 'Manual Body',
            'lane': 'surface',
            'association_status': 'confirmed',
            'association_confidence': 'exact',
            'association_source': 'manual',
            'resolver_notes': 'curated',
        },
    )

    assert link.body_id == 3
    assert link.body_name == 'Manual Body'
    assert link.lane == 'surface'
    assert link.association_source == 'manual'


def test_migration_defines_normalized_link_contract():
    migration = (ROOT / 'sql' / '021_station_body_links.sql').read_text()

    assert 'CREATE TABLE IF NOT EXISTS station_body_links' in migration
    assert 'association_status' in migration
    assert 'association_confidence' in migration
    assert 'association_source' in migration
    assert "CHECK (lane IN ('orbital', 'surface', 'unknown'))" in migration


def test_backfill_summary_reports_status_confidence_and_lane():
    rows = [
        resolve_station_body_association({
            'id': 108,
            'system_id64': 42,
            'station_type': 'Coriolis',
            'body_name': 'Resolver Test A 1',
        }, BODIES),
        resolve_station_body_association({
            'id': 109,
            'system_id64': 42,
            'station_type': 'Outpost',
            'distance_from_star': 240.0,
        }, BODIES),
    ]

    counts = summarize(rows)

    assert counts['status:confirmed'] == 1
    assert counts['status:inferred'] == 1
    assert counts['confidence:exact'] == 1
    assert counts['confidence:strong_inference'] == 1
    assert counts['lane:orbital'] == 2
