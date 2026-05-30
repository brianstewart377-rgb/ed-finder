import os
import sys

os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'api', 'src'))

from body_sorting import natural_body_sort_key_string, sort_bodies_by_hierarchy
from routers.systems import _body_payload_from_row, _ring_fields_from_scan_fact


def _sorted_names(names, system_name='Exioce'):
    rows = [{'name': name} for name in names]
    return [row['name'] for row in sort_bodies_by_hierarchy(rows, system_name=system_name)]


def test_exioce_four_hierarchy_order():
    names = [
        'Exioce 4 d a',
        'Exioce 4 d',
        'Exioce 4 b',
        'Exioce 4 a',
        'Exioce 4 a a',
        'Exioce 4',
        'Exioce 4 c',
        'Exioce 4 e',
    ]

    assert _sorted_names(names) == [
        'Exioce 4',
        'Exioce 4 a',
        'Exioce 4 a a',
        'Exioce 4 b',
        'Exioce 4 c',
        'Exioce 4 d',
        'Exioce 4 d a',
        'Exioce 4 e',
    ]


def test_numeric_bodies_sort_naturally():
    assert _sorted_names(['Exioce 10', 'Exioce 2', 'Exioce 1']) == [
        'Exioce 1',
        'Exioce 2',
        'Exioce 10',
    ]


def test_nested_moon_sort_keeps_parent_before_children():
    assert _sorted_names(['Exioce 4 b', 'Exioce 4 a b', 'Exioce 4 a', 'Exioce 4 a a']) == [
        'Exioce 4 a',
        'Exioce 4 a a',
        'Exioce 4 a b',
        'Exioce 4 b',
    ]


def test_non_standard_names_do_not_crash():
    names = ['Exioce 4 A Belt', 'Exioce barycentre', "O'Rourke Colony"]

    assert _sorted_names(names) == names


def test_sort_is_stable_for_unparseable_names():
    names = ['Experiment', "O'Rourke Colony", 'Democracy']

    assert _sorted_names(names) == names


def test_api_body_payload_exposes_hierarchy_sort_key():
    body = _body_payload_from_row(
        {'name': 'Exioce 4 a a', '_scan_is_ringed': None, '_scan_data_sources': None},
        'Exioce',
    )

    assert body['body_sort_key'] == natural_body_sort_key_string('Exioce 4 a a', 'Exioce')


def test_ring_state_true_scan_fact_without_trusted_ring_row_is_unknown():
    assert _ring_fields_from_scan_fact(True, ['eddn_scan']) == (None, 'unknown')


def test_ring_state_false_from_scan_fact():
    assert _ring_fields_from_scan_fact(False, ['eddn_scan']) == (False, 'not_ringed')


def test_missing_scan_fact_ring_state_is_unknown():
    assert _ring_fields_from_scan_fact(None, None) == (None, 'unknown')
    assert _ring_fields_from_scan_fact(False, ['eddn_fsssignals']) == (None, 'unknown')
