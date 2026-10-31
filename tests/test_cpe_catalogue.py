"""The planner owns a bundled catalogue and reviewed prerequisite mappings."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.cpe import Plan, Site, evaluate_plan  # noqa: E402
from edfinder_api.cpe import catalogue  # noqa: E402
from edfinder_api.domain import facilities  # noqa: E402


def _bundled_data():
    return json.loads(facilities._BUNDLED_CATALOGUE_PATH.read_text(encoding='utf-8'))


def test_all_prerequisites_are_reviewed_and_reference_real_facilities():
    planner = catalogue.planner_facilities()
    descriptions = {
        prerequisite['description']
        for template in _bundled_data()['templates']
        for prerequisite in template.get('prerequisites', [])
    }
    assert descriptions == set(catalogue.PREREQUISITE_FACILITY_IDS)
    for acceptable_ids in catalogue.PREREQUISITE_FACILITY_IDS.values():
        assert acceptable_ids
        assert acceptable_ids <= planner.keys()
    for template in planner.values():
        assert catalogue.prerequisites_for(template.id) == tuple(
            catalogue.PREREQUISITE_FACILITY_IDS[item['description']]
            for item in template.prerequisites
        )


def test_prerequisite_chains_require_the_direct_predecessor():
    assert catalogue.prerequisites_for('military_installation') == (
        frozenset({'orbital_installation_military'}),
    )
    assert catalogue.prerequisites_for('tourism_installation') == (
        frozenset({
            'surface_settlement_tourism_t1_m',
            'surface_settlement_tourism_t1_s',
            'surface_settlement_tourism_t2_l',
        }),
    )


def test_unknown_prerequisite_description_fails_on_load(monkeypatch, tmp_path):
    data = _bundled_data()
    data['templates'][0]['prerequisites'] = [{'description': 'Unreviewed requirement'}]
    path = tmp_path / 'unreviewed.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    catalogue._catalogue.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(facilities, '_BUNDLED_CATALOGUE_PATH', path)
            with pytest.raises(KeyError, match='Unreviewed requirement'):
                catalogue.planner_facilities()
    finally:
        catalogue._catalogue.cache_clear()


def test_planner_catalogue_is_read_only_and_excludes_colony_ship():
    planner = catalogue.planner_facilities()
    assert 'colony_ship' not in planner
    with pytest.raises(TypeError):
        planner['invented'] = catalogue.facility('coriolis_station')
    with pytest.raises(KeyError, match='colony_ship'):
        catalogue.facility('colony_ship')
    with pytest.raises(KeyError, match='unknown'):
        catalogue.prerequisites_for('unknown')


def test_pure_conversion_does_not_change_startup_catalogue():
    original = facilities._CATALOGUE
    data = _bundled_data()
    first = facilities.templates_from_json_data(data)
    second = facilities.templates_from_json_data(data)
    assert facilities._CATALOGUE is original
    assert first == second
    assert first is not second
    assert first == {
        item['id']: facilities.FacilityTemplate.from_db_row(facilities._template_json_to_row(item))
        for item in data['templates']
    }


def test_existing_json_loader_preserves_all_templates_and_defaults():
    original = facilities._CATALOGUE
    try:
        for data in (_bundled_data(), {}, {'templates': None}, {'templates': [
            {'id': 'minimal', 'name': 'Minimal'},
        ]}):
            expected = {
                item['id']: facilities.FacilityTemplate.from_db_row(
                    facilities._template_json_to_row(item),
                )
                for item in data.get('templates') or []
            }
            facilities.load_catalogue_from_json_data(data)
            assert facilities._CATALOGUE == expected
    finally:
        facilities._CATALOGUE = original


def test_planner_results_are_independent_of_shared_catalogue_state():
    original = facilities._CATALOGUE
    plan = Plan(
        system_id64=1,
        bodies=(),
        sites=(
            Site('primary', 'orbital_outpost_civilian', None, 'orbital', 'complete'),
            Site('coriolis', 'coriolis_station', None, 'orbital', 'complete'),
            Site('satellite', 'orbital_installation_satellite', None, 'orbital', 'planned'),
        ),
    )
    results = []
    try:
        for state in ('empty', 'bundled', 'different'):
            if state == 'empty':
                facilities.load_catalogue_from_rows([])
            elif state == 'bundled':
                facilities.load_catalogue_from_json_data(_bundled_data())
            else:
                row = copy.deepcopy(catalogue.facility('coriolis_station').to_dict())
                row['yellow_cp_generated'] = 999
                row['green_cp_cost'] = 888
                facilities.load_catalogue_from_rows([row])
            catalogue._catalogue.cache_clear()
            shared = facilities._CATALOGUE
            results.append(evaluate_plan(plan))
            assert facilities._CATALOGUE is shared
            assert catalogue.facility('coriolis_station').yellow_cp_generated != 999
        assert results[0] == results[1] == results[2]
    finally:
        facilities._CATALOGUE = original
        catalogue._catalogue.cache_clear()
