from __future__ import annotations

import hashlib
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


def test_catalogue_tiers_and_links_follow_cp_costs():
    templates = load_templates()

    expected = {
        'orbital_outpost_civilian': (1, 0.4),
        'surface_planetary_port_outpost_civilian': (1, 0.4),
        'planetary_port': (3, 1.2),
        'refinery': (2, 0.8),
        'orbital_installation_medical': (2, 0.8),
        'orbital_installation_satellite': (1, 0.4),
        'surface_settlement_agriculture_t1_s': (1, 0.4),
        'surface_settlement_agriculture_t2_l': (2, 0.8),
        'surface_settlement_research_bio_t1_s': (2, 0.8),
        'surface_settlement_tourism_t1_m': (2, 0.8),
    }
    for template_id, (tier, link) in expected.items():
        template = templates[template_id]
        assert (template['tier'], template['strong_link_value']) == (tier, link), template_id

    # These retained T1 size labels do not override their one-yellow-point cost.
    for size in ('s', 'm'):
        research = templates[f'surface_settlement_research_bio_t1_{size}']
        assert research['yellow_cp_cost'] == 1
        assert research['green_cp_cost'] == 0
        assert research['yellow_cp_generated'] == 0
        assert research['green_cp_generated'] == 1


def test_all_settlements_are_support_facilities():
    templates = load_templates()
    settlements = [
        template
        for template in templates.values()
        if template['source_structure'].startswith('Surface - Settlement - ')
    ]

    assert len(settlements) == 18
    for settlement in settlements:
        assert settlement['is_port'] is False, settlement['id']
        assert settlement['is_support_facility'] is True, settlement['id']
        assert settlement['category'] != 'port', settlement['id']


def test_catalogue_corrects_exactly_thirty_previous_tiers():
    templates = load_templates()
    # Snapshot of the previous catalogue's tier-2 and tier-3 entries; all other
    # entries (including the bootstrap colony ship) previously carried tier 1.
    previous_tier_2_ids = {
        'asteroid_base',
        'coriolis_station',
        'orbital_outpost_civilian',
        'orbital_outpost_commercial',
        'orbital_outpost_criminal',
        'orbital_outpost_industrial',
        'orbital_outpost_military',
        'orbital_outpost_scientific',
        'planetary_port',
        'surface_planetary_port_outpost_civilian',
        'surface_planetary_port_outpost_industrial',
        'surface_planetary_port_outpost_scientific',
        'surface_settlement_agriculture_t2_l',
        'surface_settlement_extraction_t2_l',
        'surface_settlement_industrial_t2_l',
        'surface_settlement_military_t2_l',
        'surface_settlement_research_bio_t2_l',
        'surface_settlement_tourism_t2_l',
    }
    previous_tier_3_ids = {'dodecahedron_t3', 'ocellus_station', 'orbis_t3'}
    expected_changes = {
        'extraction_facility': (1, 2),
        'hightech_research': (1, 2),
        'industrial_facility': (1, 2),
        'military_installation': (1, 2),
        'orbital_installation_government': (1, 2),
        'orbital_installation_medical': (1, 2),
        'orbital_installation_military': (1, 2),
        'orbital_installation_research_station': (1, 2),
        'orbital_installation_security_station': (1, 2),
        'orbital_installation_space_bar': (1, 2),
        'orbital_outpost_civilian': (2, 1),
        'orbital_outpost_commercial': (2, 1),
        'orbital_outpost_criminal': (2, 1),
        'orbital_outpost_industrial': (2, 1),
        'orbital_outpost_military': (2, 1),
        'orbital_outpost_scientific': (2, 1),
        'planetary_port': (2, 3),
        'refinery': (1, 2),
        'surface_hub_civilian': (1, 2),
        'surface_hub_exploration': (1, 2),
        'surface_hub_outpost': (1, 2),
        'surface_hub_scientific': (1, 2),
        'surface_planetary_port_outpost_civilian': (2, 1),
        'surface_planetary_port_outpost_industrial': (2, 1),
        'surface_planetary_port_outpost_scientific': (2, 1),
        'surface_settlement_research_bio_t1_m': (1, 2),
        'surface_settlement_research_bio_t1_s': (1, 2),
        'surface_settlement_tourism_t1_m': (1, 2),
        'surface_settlement_tourism_t1_s': (1, 2),
        'tourism_installation': (1, 2),
    }

    assert len(templates) == 56
    assert len(expected_changes) == 30
    assert previous_tier_2_ids | previous_tier_3_ids <= templates.keys()
    actual_changes = {}
    for template_id, template in templates.items():
        previous_tier = (
            3 if template_id in previous_tier_3_ids
            else 2 if template_id in previous_tier_2_ids
            else 1
        )
        if template['tier'] != previous_tier:
            actual_changes[template_id] = (previous_tier, template['tier'])
    assert actual_changes == expected_changes


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


def test_catalogue_corrects_exactly_eight_previous_colony_port_flags():
    templates = load_templates()
    expected_changes = {
        'orbital_outpost_civilian': (False, True),
        'orbital_outpost_commercial': (False, True),
        'coriolis_station': (False, True),
        'orbis_t3': (False, True),
        'ocellus_station': (False, True),
        # Not named in Mega Guide v2.3.0; Raven Colonial lists it as colony.
        'dodecahedron_t3': (False, True),
        'surface_planetary_port_outpost_civilian': (False, True),
        'planetary_port': (False, True),
    }
    # The previous catalogue marked only the bootstrap colony ship as colony.
    actual_changes = {}
    for template_id, template in templates.items():
        previous_flag = template_id == 'colony_ship'
        if template['is_colony_port'] is not previous_flag:
            actual_changes[template_id] = (previous_flag, template['is_colony_port'])

    assert len(templates) == 56
    assert len(expected_changes) == 8
    assert actual_changes == expected_changes
    assert templates['colony_ship']['is_colony_port'] is True
    for template_id in (
        'asteroid_base',
        'orbital_outpost_industrial',
        'orbital_outpost_criminal',
        'orbital_outpost_military',
        'orbital_outpost_scientific',
        'surface_planetary_port_outpost_industrial',
        'surface_planetary_port_outpost_scientific',
    ):
        assert templates[template_id]['is_colony_port'] is False, template_id


def test_colony_port_correction_preserves_all_other_catalogue_fields():
    data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    for template in data['templates']:
        del template['is_colony_port']

    # Fingerprint of the previous catalogue with only is_colony_port removed;
    # includes costs, tiers, port flags, source fields and template ordering.
    assert hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest() == (
        '7deb84d20e090fb99eb0b4f5f26fd253b5656dfc9f1de2fb34785c9cbe9f4018'
    )


def test_generated_catalogue_loads_into_facility_templates():
    data = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))

    load_catalogue_from_json_data(data)
    templates = get_catalogue()

    assert templates['colony_ship'].is_colony_port
    assert templates['refinery'].is_support_facility
    assert templates['refinery'].stat_effects['source_sheet'] == 'Stats'
    assert templates['tourism_installation'].economy_effects['is_modifier_economy'] is True
