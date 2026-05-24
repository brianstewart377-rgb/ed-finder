import os
import sys

os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'api', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'importer', 'src'))

from helpers import safe_coords_from_row
from local_search import _safe_distance
from build_ratings import rate_system


def test_safe_coords_treats_non_sol_origin_as_unknown():
    assert safe_coords_from_row({'id64': 123, 'x': 0, 'y': 0, 'z': 0}) == {
        'x': None,
        'y': None,
        'z': None,
    }


def test_safe_coords_allows_sol_origin():
    assert safe_coords_from_row({'id64': 10477373803, 'x': 0, 'y': 0, 'z': 0}) == {
        'x': 0.0,
        'y': 0.0,
        'z': 0.0,
    }


def test_safe_distance_rejects_fake_zero():
    assert _safe_distance(0.0) is None


def test_current_rating_scorer_attenuates_multi_economy_saturation():
    bodies = (
        [{'subtype': 'Earth-like world', 'is_earth_like': True}] * 3
        + [{'subtype': 'Gas giant'}] * 5
        + [{'subtype': 'Rocky body', 'is_landable': True}] * 10
        + [{'subtype': 'Rocky Ice world', 'is_landable': True}] * 2
    )

    rating = rate_system(2008132031194, bodies, 'K')
    scores = [
        rating['score_refinery'],
        rating['score_industrial'],
        rating['score_hightech'],
        rating['score_military'],
    ]

    assert scores.count(100) <= 2
    assert rating['rating_version'] == '3.4'
