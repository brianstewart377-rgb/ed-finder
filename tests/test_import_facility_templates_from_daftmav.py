from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'importer' / 'src'))

import import_facility_templates_from_daftmav as importer  # noqa: E402


CATALOGUE_PATH = ROOT / 'apps' / 'api' / 'src' / 'domain' / 'facility_catalogue_v1.json'


@pytest.mark.parametrize(
    ('family', 'location', 'is_port', 'category'),
    [
        ('Starport', 'Orbital', True, 'port'),
        ('Outpost', 'Orbital', True, 'port'),
        ('Planetary Port', 'Surface', True, 'port'),
        ('Settlement', 'Surface', False, 'agriculture'),
        ('Hub', 'Surface', False, 'agriculture'),
        ('Installation', 'Orbital', False, 'agriculture'),
    ],
)
@pytest.mark.parametrize(
    ('t2_effect', 't3_effect', 'tier', 'strong_link_value'),
    [(1, 0, 1, 0.4), (-1, 1, 2, 0.8), (0, -6, 3, 1.2)],
)
def test_row_classification_uses_cp_tier_and_facility_family(
    family, location, is_port, category, t2_effect, t3_effect, tier, strong_link_value,
):
    template = importer._row_to_template(importer.CellRow(2, {
        'A': f'{location} - {family} - Agriculture T1 S',
        'F': t2_effect,
        'G': t3_effect,
        'N': '*Agricultural',
    }))

    assert template['tier'] == tier
    assert template['strong_link_value'] == strong_link_value
    assert template['is_port'] is is_port
    assert template['is_support_facility'] is (not is_port)
    assert template['category'] == category
    assert template['economy'] == 'Agriculture'


@pytest.mark.parametrize(
    ('structure', 'family', 't2_effect', 't3_effect', 'expected'),
    [
        ('Surface - Settlement - Research Bio T1 S', 'Settlement', -1, 1, 2),
        ('Surface - Settlement - Agriculture T2 L', 'Settlement', -1, -1, 3),
        # Explicit zero effects represent a free Tier 1 facility even when the
        # old name-based fallback would have selected Tier 2 or Tier 3.
        ('Orbital - Starport - Orbis', 'Starport', 0, 0, 1),
        ('Orbital - Starport - Coriolis', 'Starport', 0, None, 1),
        ('Orbital - Starport - Coriolis', 'Starport', None, 0, 1),
        ('Orbital - Starport - Coriolis', 'Starport', None, -6, 3),
        ('Surface - Hub - Refinery', 'Hub', -1, None, 2),
        ('Surface - Settlement - Agriculture T2 L', 'Settlement', 1, None, 1),
        # Only wholly missing CP effects retain the conservative old fallback.
        ('Orbital - Starport - Orbis', 'Starport', None, None, 3),
        ('Surface - Settlement - Agriculture T3 L', 'Settlement', None, None, 3),
        ('Orbital - Starport - Coriolis', 'Starport', None, None, 2),
        ('Orbital - Outpost - Civilian', 'Outpost', None, None, 2),
        ('Surface - Planetary Port - Port', 'Planetary Port', None, None, 2),
        ('Surface - Settlement - Agriculture T2 L', 'Settlement', None, None, 2),
        ('Surface - Hub - Refinery', 'Hub', None, None, 1),
        ('Orbital - Installation - Medical', 'Installation', None, None, 1),
    ],
)
def test_tier_from_cp_effects_handles_precedence_and_missing_effects(
    structure, family, t2_effect, t3_effect, expected,
):
    assert importer._tier_from_cp_effects(structure, family, t2_effect, t3_effect) == expected


@pytest.mark.parametrize(
    ('family', 'economy', 'expected'),
    [
        ('Starport', 'Agriculture', 'port'),
        ('Outpost', None, 'port'),
        ('Planetary Port', 'Industrial', 'port'),
        ('Settlement', 'HighTech', 'hightech'),
        ('Settlement', None, 'settlement'),
        ('Hub', 'Refinery', 'refinery'),
        ('Hub', None, 'hub'),
        ('Installation', 'Tourism', 'tourism'),
        ('Installation', None, 'installation'),
        ('Unknown Family', None, 'unknown_family'),
        ('', None, 'support'),
    ],
)
def test_category_uses_economy_for_support_families(family, economy, expected):
    assert importer._category(family, economy) == expected


@pytest.mark.parametrize('family', ['Settlement', 'Hub', 'Installation'])
def test_support_rows_can_infer_economy_without_an_economy_cell(family):
    template = importer._row_to_template(importer.CellRow(2, {
        'A': f'Surface - {family} - Agriculture T1 S',
        'F': '1',
    }))

    assert template['economy'] == 'Agriculture'
    assert template['category'] == 'agriculture'
    assert template['is_port'] is False
    assert template['is_support_facility'] is True


@pytest.mark.parametrize('family', ['Starport', 'Outpost', 'Planetary Port', 'Settlement', 'Hub', 'Installation'])
@pytest.mark.parametrize('economy', ['Colony', '*Colony', 'Industrial', None])
def test_colony_port_requires_port_family_and_colony_economy(family, economy):
    template = importer._row_to_template(importer.CellRow(2, {
        'A': f'Surface - {family} - Agriculture T1 S',
        'F': 1,
        'N': economy,
    }))

    assert template['is_colony_port'] is (
        family in {'Starport', 'Outpost', 'Planetary Port'}
        and economy in {'Colony', '*Colony'}
    )


def test_bundled_catalogue_matches_importer_rows_order_and_serialisation():
    catalogue_text = CATALOGUE_PATH.read_text(encoding='utf-8')
    catalogue = json.loads(catalogue_text)
    regenerated = []
    for template in catalogue['templates']:
        if template['id'] == 'colony_ship':
            continue
        source_fields = template['stat_effects']['source_fields']
        assert source_fields['structure'] == template['source_structure']
        row = importer.CellRow(
            template['stat_effects']['source_row'],
            {column: source_fields[name] for column, name in importer.HEADERS.items()},
        )
        regenerated_template = importer._row_to_template(row)
        # Full equality also guards every unchanged cost, point generation,
        # prerequisite, unlock and source field, beyond the five corrected fields.
        assert regenerated_template == template, template['id']
        regenerated.append(regenerated_template)

    assert len(regenerated) == 55
    regenerated.extend(importer._bootstrap_templates())
    regenerated.sort(key=lambda item: (
        item['allowed_location'], item['category'], item['tier'], item['name'],
    ))
    assert catalogue['templates'] == regenerated
    assert catalogue_text == json.dumps(catalogue, indent=2, sort_keys=True) + '\n'
