from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from domain.facilities import get_catalogue, load_catalogue_from_json_data


CATALOGUE_PATH = ROOT / 'apps' / 'api' / 'src' / 'domain' / 'facility_catalogue_v1.json'


def load_templates() -> dict[str, dict]:
    data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    return {item['id']: item for item in data['templates']}


def test_catalogue_has_daftmav_source_metadata():
    data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))

    assert data['catalogue_version'] == 1
    assert data['source']['sheet'] == 'Stats'
    assert 'DaftMav' in data['source']['name']
    assert len(data['templates']) >= 55


def test_catalogue_contains_major_facility_families():
    templates = load_templates()
    structures = {item['source_structure'] for item in templates.values()}

    assert 'Orbital - Starport - Coriolis' in structures
    assert 'Orbital - Starport - Asteroid Base' in structures
    assert 'Orbital - Installation - Mining Outpost' in structures
    assert 'Surface - Planetary Port - Port' in structures
    assert 'Surface - Settlement - Agriculture T1 S' in structures
    assert 'Surface - Settlement - Tourism T2 L' in structures
    assert 'Surface - Hub - High Tech' in structures
    assert 'Surface - Hub - Industrial' in structures


def test_catalogue_preserves_t2_t3_cp_effects():
    templates = load_templates()

    coriolis = templates['coriolis_station']
    assert coriolis['tier'] == 2
    assert coriolis['stat_effects']['t2_cp_effect'] == -3.0
    assert coriolis['yellow_cp_cost'] == 3

    orbis = templates['orbis_t3']
    assert orbis['tier'] == 3
    assert orbis['stat_effects']['t3_cp_effect'] == -6.0
    assert orbis['green_cp_cost'] == 6


def test_catalogue_preserves_prerequisites_and_unlocks():
    templates = load_templates()

    tourism = templates['surface_settlement_tourism_t1_s']
    assert tourism['prerequisites'][0]['description'] == 'Installation - Satellite'
    assert any(
        unlock['description'] == 'Tourist Installations'
        for unlock in tourism['stat_effects']['unlocks']
    )

    military = templates['orbital_installation_military']
    assert military['prerequisites'][0]['description'] == 'Settlement - Military'
    assert 'Shipyard' in military['stat_effects']['unlocks'][0]['description']


def test_catalogue_preserves_economies_and_locations():
    templates = load_templates()

    assert templates['refinery']['economy'] == 'Refinery'
    assert templates['industrial_facility']['economy'] == 'Industrial'
    assert templates['hightech_research']['economy'] == 'HighTech'
    assert templates['tourism_installation']['economy'] == 'Tourism'
    assert templates['asteroid_base']['allowed_location'] == 'ringed_orbital'
    assert templates['coriolis_station']['allowed_location'] == 'orbital'
    assert templates['planetary_port']['allowed_location'] == 'surface'


def test_generated_catalogue_loads_into_facility_templates():
    data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))

    load_catalogue_from_json_data(data)
    templates = get_catalogue()

    assert templates['colony_ship'].is_colony_port
    assert templates['refinery'].is_support_facility
    assert templates['refinery'].stat_effects['source_sheet'] == 'Stats'
    assert templates['tourism_installation'].economy_effects['is_modifier_economy'] is True
