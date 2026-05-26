import os
import sys
from pathlib import Path


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
for path in (API_SRC, IMPORTER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from import_spansh import (  # noqa: E402
    DUMP_FILES,
    norm_station_type,
    station_body_name_from_record,
    station_distance_from_record,
    station_type_from_record,
)
from station_body_resolver import classify_station_lane  # noqa: E402


def test_station_type_normaliser_accepts_known_source_labels():
    cases = {
        'Coriolis': 'Coriolis',
        'Coriolis Starport': 'Coriolis',
        'Orbis': 'Orbis',
        'Orbis Starport': 'Orbis',
        'Ocellus': 'Ocellus',
        'Ocellus Starport': 'Ocellus',
        'Outpost': 'Outpost',
        'AsteroidBase': 'AsteroidBase',
        'Asteroid Base': 'AsteroidBase',
        'Planetary Port': 'PlanetaryPort',
        'PlanetaryPort': 'PlanetaryPort',
        'Planetary Outpost': 'PlanetaryOutpost',
        'PlanetaryOutpost': 'PlanetaryOutpost',
        'Planetary Settlement': 'PlanetaryOutpost',
        'Settlement': 'PlanetaryOutpost',
        'Surface Settlement': 'PlanetaryOutpost',
        'MegaShip': 'MegaShip',
        'Megaship': 'MegaShip',
        'FleetCarrier': 'FleetCarrier',
        'Fleet Carrier': 'FleetCarrier',
        'Carrier': 'FleetCarrier',
        'Unknown': 'Unknown',
    }

    for raw, expected in cases.items():
        assert norm_station_type(raw) == expected


def test_station_type_normaliser_does_not_fuzzy_overclassify_unknowns():
    for raw in ('Coriolis Logistics', 'Planetary Warehouse', 'Surface Megaport', '', None):
        assert norm_station_type(raw) == 'Unknown'


def test_normalised_station_type_enables_lane_classification():
    orbital_labels = ('Coriolis Starport', 'Orbis Starport', 'Ocellus Starport', 'Outpost', 'Asteroid Base')
    surface_labels = ('Planetary Port', 'Planetary Outpost', 'Planetary settlement', 'Surface Settlement')

    for raw in orbital_labels:
        assert classify_station_lane(norm_station_type(raw))[0] == 'orbital'
        assert classify_station_lane(raw)[0] == 'orbital'
    for raw in surface_labels:
        assert classify_station_lane(norm_station_type(raw))[0] == 'surface'
        assert classify_station_lane(raw)[0] == 'surface'


def test_fleet_carrier_and_megaship_labels_are_non_slot_lanes():
    for raw in ('FleetCarrier', 'Fleet Carrier', 'Carrier', 'MegaShip', 'Megaship'):
        assert classify_station_lane(norm_station_type(raw))[0] == 'unknown'
        assert classify_station_lane(raw)[0] == 'unknown'


def test_station_record_helpers_accept_spansh_and_edsm_field_shapes():
    assert station_type_from_record({'stationType': 'Coriolis Starport'}) == 'Coriolis'
    assert station_type_from_record({'type': 'Planetary settlement'}) == 'PlanetaryOutpost'
    assert station_distance_from_record({'distanceToArrival': 0, 'distance_from_star': 12}) == 0
    assert station_body_name_from_record({'bodyName': 'Exioce 1'}) == 'Exioce 1'
    assert station_body_name_from_record({'body': {'name': 'Exioce 2'}}) == 'Exioce 2'


def test_edsm_dumps_are_not_added_to_active_heavy_imports():
    assert all('edsm' not in dump_name.lower() for dump_name in DUMP_FILES)
