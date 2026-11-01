"""Database-free best-rival selection for selected-archetype ranking rows."""

import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://archetype-rival-test.invalid')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.ranking.profile import ARCHETYPE_KEYS  # noqa: E402
from edfinder_api.routers.archetypes import best_rival  # noqa: E402

pytestmark = pytest.mark.unit


def test_tied_rivals_follow_archetype_key_order_not_mapping_order():
    scores = dict.fromkeys(reversed(ARCHETYPE_KEYS), 20)
    scores.update(paradise=100, megacomplex=79, research_hub=79)

    assert best_rival(scores, 'paradise') == ('megacomplex', 79)


def test_flexible_is_excluded_for_a_non_flexible_pick():
    scores = dict.fromkeys(ARCHETYPE_KEYS, 20)
    scores.update(flexible=100, paradise=90, mining_hub=80)

    assert best_rival(scores, 'paradise') == ('mining_hub', 80)


def test_flexible_pick_uses_the_best_of_the_other_seven():
    scores = dict.fromkeys(ARCHETYPE_KEYS, 20)
    scores.update(flexible=100, population_capital=85)

    assert best_rival(scores, 'flexible') == ('population_capital', 85)


def test_rival_can_score_above_the_picked_archetype():
    scores = dict.fromkeys(ARCHETYPE_KEYS, 0)
    scores.update(stronghold=100)

    assert best_rival(scores, 'paradise') == ('stronghold', 100)


@pytest.mark.parametrize('picked', ARCHETYPE_KEYS)
def test_all_scores_equal_use_the_earliest_eligible_key(picked):
    scores = dict.fromkeys(ARCHETYPE_KEYS, 60)
    expected = 'mining_hub' if picked == 'paradise' else 'paradise'

    assert best_rival(scores, picked) == (expected, 60)
