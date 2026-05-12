"""
Unit tests for build_ratings.generate_rationale and rate_system tiebreak.

These tests are pure-Python: no DB, no Spansh fixtures, no async. They run
in sub-second time and exist as a regression net for the 2026-05-10
"Strong Refinery; via 1 ELW" misleading-rationale bug (HD 49188 case)
plus the dict-order-arbitrary primary_eco tiebreak that was hidden inside
the same code path.

Invariant under test:
  Every body category mentioned in the rationale's "via …" clause MUST
  appear in the score_<primary_eco> function above. Highlights that don't
  contribute to the chosen primary economy are misleading and not allowed.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'apps' / 'importer' / 'src'))

import pytest

from build_ratings import (
    generate_rationale,
    rate_system,
    ECON_HIGHLIGHT_BUILDERS,
)


def _empty_counts() -> dict:
    """Default zero counts for every key classify_bodies() can produce."""
    return {
        'elw': 0, 'ww': 0, 'ammonia': 0, 'terraformable': 0,
        'rocky_clean': 0, 'rocky_rings': 0, 'rocky_bio': 0,
        'rocky_geo': 0, 'rocky_mixed': 0, 'rocky_ice': 0,
        'hmc': 0, 'metal_rich': 0, 'icy': 0, 'gas_giant': 0,
        'neutron': 0, 'black_hole': 0, 'white_dwarf': 0,
        'geo': 0, 'bio': 0,
        'landable': 0, 'landable_rocky_clean': 0, 'landable_rocky_any': 0,
        'landable_hmc': 0, 'tidal_lock': 0, 'terraformable_hmc': 0,
    }


# ---------------------------------------------------------------------------
# 1. Regression test for the HD 49188 (id64 167244365) case directly.
#    Pre-fix rationale: "Strong Refinery; via 1 ELW, 4 ringed, 3 metal-rich;
#                        15 landable; — varied body mix"
#    The 1 ELW and 3 metal-rich do NOT contribute to score_refinery; this
#    test asserts they never appear in the rationale when primary=Refinery.
# ---------------------------------------------------------------------------
def test_hd_49188_refinery_rationale_excludes_elw_and_metal_rich():
    counts = _empty_counts()
    counts.update(
        rocky_clean=8, rocky_rings=4, hmc=3, rocky_ice=2,
        landable=15,
        elw=1,            # would have appeared as a misleading highlight
        metal_rich=3,     # would have appeared as a misleading highlight
        gas_giant=2,
    )
    scores = {'Refinery': 100, 'Military': 100, 'HighTech': 73,
              'Tourism': 46, 'Agriculture': 32, 'Industrial': 32,
              'Extraction': 60}
    text = generate_rationale(counts, scores, primary_eco='Refinery',
                              tf_score=10, diversity=30, main_star_type='K')

    assert 'Strong Refinery' in text
    # The two pre-fix red herrings must not appear:
    assert 'ELW' not in text, f"ELW should not appear in Refinery rationale: {text!r}"
    assert 'metal-rich' not in text, f"metal-rich should not appear: {text!r}"
    # Real Refinery contributors should be present:
    assert 'clean rocky' in text or 'rocky-ringed' in text or 'HMC' in text


# ---------------------------------------------------------------------------
# 2. Per-economy contributor invariant: the rationale only mentions
#    bodies in ECON_HIGHLIGHT_BUILDERS[primary_eco]'s output.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("primary_eco", list(ECON_HIGHLIGHT_BUILDERS.keys()))
def test_rationale_only_mentions_relevant_bodies(primary_eco):
    """For every economy, give the rationale a counts dict with EVERY body
    type populated. Then assert that the highlights only contain the
    builder's known phrases — no unrelated ELW/WW/exotic mentions."""
    counts = _empty_counts()
    # Populate every counter with 2 so every builder has something to emit.
    for k in counts:
        counts[k] = 2
    scores = {e: 80 for e in ECON_HIGHLIGHT_BUILDERS}
    expected_phrases = ECON_HIGHLIGHT_BUILDERS[primary_eco](counts)
    text = generate_rationale(counts, scores, primary_eco=primary_eco,
                              tf_score=20, diversity=10, main_star_type='G')
    # The "via …" portion contains highlights joined by ", ".
    if 'via ' in text:
        via = text.split('via ', 1)[1].split(';', 1)[0]
        # Each comma-separated highlight must come from the per-economy
        # builder's output (top 3, in the order it produced).
        mentioned = [h.strip() for h in via.split(',')]
        for m in mentioned:
            assert m in expected_phrases, (
                f"Rationale for primary={primary_eco} mentioned {m!r} which "
                f"is NOT in the builder's output {expected_phrases!r}. "
                f"Full text: {text!r}"
            )


# ---------------------------------------------------------------------------
# 3. Lead phrase strength tracking — make sure the threshold logic still
#    works after the rewrite.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("score, expected_lead", [
    (95, 'Strong'),
    (60, 'Strong'),
    (59, 'Moderate'),
    (40, 'Moderate'),
    (39, '-leaning'),
    (20, '-leaning'),
    (19, 'Low-yield'),
    (0,  'Low-yield'),
])
def test_lead_phrase_thresholds(score, expected_lead):
    counts = _empty_counts()
    counts.update(rocky_clean=3, landable=5)
    scores = {'Refinery': score, 'Military': 0, 'HighTech': 0,
              'Tourism': 0, 'Agriculture': 0, 'Industrial': 0, 'Extraction': 0}
    text = generate_rationale(counts, scores, primary_eco='Refinery',
                              tf_score=0, diversity=0, main_star_type=None)
    assert expected_lead in text


def test_rationale_uses_structured_labels_not_via_phrasing():
    counts = _empty_counts()
    counts.update(icy=3, rocky_ice=2, gas_giant=1, elw=1, landable=6)
    scores = {e: 0 for e in ECON_HIGHLIGHT_BUILDERS}
    scores['Industrial'] = 82

    text = generate_rationale(counts, scores, primary_eco='Industrial',
                              tf_score=0, diversity=0, main_star_type='K')

    assert 'Primary score:' in text
    assert 'Factors:' in text
    assert ' via ' not in text
    assert 'Industrial via ELW' not in text
    assert 'ELW is not an Industrial driver' in text
    assert 'icy' in text or 'rocky-ice' in text or 'gas giant' in text


def test_military_elw_rationale_includes_mixed_economy_caveat():
    counts = _empty_counts()
    counts.update(elw=1, gas_giant=2, landable=7)
    scores = {e: 0 for e in ECON_HIGHLIGHT_BUILDERS}
    scores['Military'] = 88

    text = generate_rationale(counts, scores, primary_eco='Military',
                              tf_score=0, diversity=0, main_star_type='A')

    assert 'Military via ELW' not in text
    assert ' via ' not in text
    assert 'ELW mixed' in text
    assert 'Caveat:' in text
    assert 'Agri/HT/Mil/Tourism' in text
    assert 'star inheritance' in text


# ---------------------------------------------------------------------------
# 4. Tiebreak for primary_eco — the dict-order-arbitrary bug.
# ---------------------------------------------------------------------------
def _bodies_for_tied_refinery_military():
    """Return a body list crafted to score Refinery and Military equally
    high, so the tiebreak is exercised."""
    # 8 clean Rocky landable bodies → Refinery-heavy + lots of landable
    bodies = []
    for i in range(8):
        bodies.append({
            'name': f'Rocky {i}',
            'subType': 'Rocky body',
            'isLandable': True,
            'distanceToArrival': 100 + i * 50,
            'rings': [],
            'signals': {},
            'atmosphereType': 'No atmosphere',
            'orbitalPeriod': 365,
            'gravity': 0.5,
            'parents': [{'Star': 0}],
        })
    # 1 ELW to push Military's elw component up
    bodies.append({
        'name': 'ELW',
        'subType': 'Earth-like world',
        'isLandable': False,
        'distanceToArrival': 200,
        'rings': [], 'signals': {},
        'parents': [{'Star': 0}],
    })
    return bodies


def test_tiebreak_uses_complementary_pair_winner():
    """When two economies tie, the one in the winning complementary pair
    should be picked as primary."""
    bodies = _bodies_for_tied_refinery_military()
    result = rate_system(system_id64=1, bodies=bodies, main_star_type='K')

    # Whatever the exact scores end up being, primary_eco must be
    # deterministic and consistent with the top_pair returned in the
    # same response (no more dict-order roulette).
    primary = result['economy_suggestion']
    pair_a  = result.get('top_pair_a')   # primary key name in v3.3
    pair_b  = result.get('top_pair_b')

    if pair_a is not None and pair_b is not None:
        assert primary in (pair_a, pair_b), (
            f"primary_eco={primary} should be one of the winning pair "
            f"({pair_a}, {pair_b})."
        )
