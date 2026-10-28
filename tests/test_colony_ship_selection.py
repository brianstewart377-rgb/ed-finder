"""Bootstrap ship selection stays separate from body-inheriting colony ports."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from edfinder_api.domain import facilities
from edfinder_api.domain.facilities import is_colony_ship
from edfinder_api.optimiser.candidate_generator import _is_useful_candidate
from edfinder_api.optimiser.facility_selection import select_port_template
from edfinder_api.optimiser.guided_planner import _select_port
from edfinder_api.optimiser.guided_planner_models import GuidedPlanRequest
from edfinder_api.optimiser.models import CandidatePlacement, OptimiserCandidate
from edfinder_api.simulation.buildability import _select_facilities_for_archetype


@pytest.fixture
def bundled_catalogue(monkeypatch):
    monkeypatch.setattr(facilities, '_CATALOGUE', {})
    return facilities.load_bundled_catalogue()


def test_colony_ship_is_identified_only_by_bootstrap_id(bundled_catalogue):
    assert {
        template.id for template in bundled_catalogue.values() if is_colony_ship(template)
    } == {'colony_ship'}
    assert is_colony_ship(replace(bundled_catalogue['colony_ship'], is_colony_port=False))
    assert not is_colony_ship(replace(bundled_catalogue['coriolis_station'], is_colony_port=True))


@pytest.mark.parametrize(('strategy', 'expected_id'), [
    ('primary_port_bootstrap', 'orbital_outpost_civilian'),
    ('low_cp', 'orbital_outpost_civilian'),
    ('services_aware', 'asteroid_base'),
    ('balanced', 'asteroid_base'),
    ('balanced_expansion', 'asteroid_base'),
    ('support_body', 'asteroid_base'),
    ('main_station', 'planetary_port'),
    ('industrial_refinery', 'orbital_outpost_civilian'),
    ('tourism_agriculture', 'orbital_outpost_civilian'),
])
def test_port_strategies_keep_bundled_catalogue_choices(bundled_catalogue, strategy, expected_id):
    selected = select_port_template(bundled_catalogue, strategy)

    assert selected is not None
    assert selected.id == expected_id


@pytest.mark.parametrize(('preset', 'expected_id'), [
    ('light', 'orbital_outpost_civilian'),
    ('balanced', 'asteroid_base'),
    ('medium', 'asteroid_base'),
    ('high', 'asteroid_base'),
    ('maxed', 'planetary_port'),
])
def test_guided_port_presets_keep_bundled_catalogue_choices(bundled_catalogue, preset, expected_id):
    selected = _select_port(bundled_catalogue, GuidedPlanRequest(system_id64=1, preset=preset))

    assert selected is not None
    assert selected.id == expected_id


@pytest.mark.parametrize('archetype', [None, 'refinery_industrial', 'hitech_tourism'])
def test_buildability_starts_with_only_bootstrap_ship(bundled_catalogue, archetype):
    # Put other colony-type ports before the ship so ordering cannot hide a
    # mistaken use of the economy flag to identify the bootstrap facility.
    templates = [template for template in bundled_catalogue.values() if not is_colony_ship(template)]
    templates.append(bundled_catalogue['colony_ship'])

    selected = _select_facilities_for_archetype(archetype, templates)

    assert selected[0].id == 'colony_ship'
    assert [template.id for template in selected if template.is_port] == ['colony_ship']
    assert all(template.is_support_facility for template in selected[1:])


def _candidate(*template_ids):
    return OptimiserCandidate(
        candidate_id='colony-ship-separation',
        label='Colony ship separation',
        target_archetype='refinery_industrial',
        strategy='balanced',
        placements=[
            CandidatePlacement(facility_template_id=template_id, build_order=index + 1)
            for index, template_id in enumerate(template_ids)
        ],
        tags=['balanced'],
    )


def test_candidate_with_only_known_colony_ship_is_rejected(bundled_catalogue):
    candidate = _candidate('colony_ship', 'unknown_facility')

    assert not _is_useful_candidate(candidate, bundled_catalogue)

    # Exercise the ship rejection independently of the later support-count
    # condition: bootstrap identity must still exclude this candidate.
    ship_marked_support = {
        **bundled_catalogue,
        'colony_ship': replace(bundled_catalogue['colony_ship'], is_support_facility=True),
    }
    assert not _is_useful_candidate(candidate, ship_marked_support)


def test_colony_type_port_with_support_remains_useful_candidate(bundled_catalogue):
    support = next(template for template in bundled_catalogue.values() if template.is_support_facility)

    assert _is_useful_candidate(_candidate('coriolis_station', support.id), bundled_catalogue)
