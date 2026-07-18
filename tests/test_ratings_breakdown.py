"""Cross-check guardrail for ratings_breakdown.reconstruct_score_breakdown().

score_breakdown was retired from build_ratings.py's rate_system() in
"Stop writing score_breakdown in build_ratings (Phase B step 1)"
(commit 81865ba). That commit deleted the only code that assembled
top_pair, has_standout, primary_economy, and secondary_economy — so
there is no longer any importable "ground truth" for those four
fields. This test freezes the pre-removal algorithm for exactly those
four fields (_golden_rank_economies / _golden_has_standout below,
copied verbatim from build_ratings.py as it existed before 81865ba)
and treats it as the oracle.

For the rocky sub-splits (rocky_clean/geo/bio/rings), classify_bodies()
itself was NOT touched by the removal and is still live importer code
— this test calls the real, current classify_bodies() as the oracle,
so if its rocky branch changes, this test fails. That is the actual
drift guardrail plan §7 asked for.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault('LOG_FILE', '/dev/null')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'api', 'src'))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'importer', 'src'))

from build_ratings import rate_system, classify_bodies  # noqa: E402
from ratings_breakdown import reconstruct_score_breakdown  # noqa: E402


# ---------------------------------------------------------------------------
# Frozen pre-removal oracle (build_ratings.py rate_system(), before 81865ba)
# ---------------------------------------------------------------------------
_COMPLEMENTARY_PAIRS = (
    ('Extraction',  'Refinery'),
    ('Refinery',    'Industrial'),
    ('Industrial',  'HighTech'),
    ('HighTech',    'Tourism'),
    ('Agriculture', 'Tourism'),
    ('HighTech',    'Military'),
    ('Industrial',  'Military'),
    ('Agriculture', 'HighTech'),
)


def _golden_rank_economies(economies: dict) -> tuple[str, str | None, dict]:
    sorted_ecos = sorted(economies.items(), key=lambda x: x[1], reverse=True)
    pair_scores = [(a, b, (economies[a] + economies[b]) / 2)
                   for a, b in _COMPLEMENTARY_PAIRS]
    best_a, best_b, best_pair = max(pair_scores, key=lambda t: t[2])

    top_score = sorted_ecos[0][1]
    tied_top = [eco for eco, sc in sorted_ecos if sc == top_score]
    if len(tied_top) >= 2:
        if best_a in tied_top:
            primary_eco = best_a
        elif best_b in tied_top:
            primary_eco = best_b
        else:
            primary_eco = tied_top[0]
    else:
        primary_eco = sorted_ecos[0][0]

    secondary_eco = next((eco for eco, _ in sorted_ecos if eco != primary_eco), None)

    top_pair = {
        'a':          best_a,
        'b':          best_b,
        'a_score':    int(economies[best_a]),
        'b_score':    int(economies[best_b]),
        'pair_score': int(round(best_pair)),
    }
    return primary_eco, secondary_eco, top_pair


def _golden_has_standout(counts: dict) -> bool:
    return (
        counts['elw']           >= 1 or
        counts['ammonia']       >= 1 or
        counts['black_hole']    >= 1 or
        counts['neutron']       >= 1 or
        counts['ww']            >= 2 or
        counts['terraformable'] >= 5
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _rocky_mix_bodies() -> list[dict]:
    common = {
        'is_landable': False, 'is_terraformable': False, 'is_tidal_lock': False,
        'distance_from_star': 1000,
    }
    return [
        {**common, 'subtype': 'Rocky body', 'geo_signal_count': 3, 'bio_signal_count': 0, 'has_rings': False},  # -> rocky_geo
        {**common, 'subtype': 'Rocky body', 'geo_signal_count': 0, 'bio_signal_count': 2, 'has_rings': False},  # -> rocky_bio
        {**common, 'subtype': 'Rocky body', 'geo_signal_count': 0, 'bio_signal_count': 0, 'has_rings': True},   # -> rocky_rings
        {**common, 'subtype': 'Rocky body', 'geo_signal_count': 0, 'bio_signal_count': 0, 'has_rings': False},  # -> rocky_clean
        {**common, 'subtype': 'Rocky body', 'geo_signal_count': 1, 'bio_signal_count': 1, 'has_rings': False},  # -> rocky_mixed (not counted)
    ]


def _elw_bodies() -> list[dict]:
    return [{
        'subtype': 'Earth-like world', 'is_earth_like': True,
        'is_landable': False, 'is_terraformable': False, 'is_tidal_lock': False,
        'geo_signal_count': 0, 'bio_signal_count': 0, 'has_rings': False,
        'distance_from_star': 500,
    }]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_reconstruction_matches_golden_breakdown_for_rocky_mix():
    bodies = _rocky_mix_bodies()
    row = rate_system(1001, bodies, 'G')
    counts = classify_bodies(bodies)

    economies = {
        'Agriculture': row['score_agriculture'],
        'Refinery':    row['score_refinery'],
        'Industrial':  row['score_industrial'],
        'HighTech':    row['score_hightech'],
        'Military':    row['score_military'],
        'Tourism':     row['score_tourism'],
        'Extraction':  row['score_extraction'],
    }
    # sanity: non-trivial scores so the tie-break path is actually exercised
    assert sum(economies.values()) > 0
    assert len({v for v in economies.values()}) > 1

    golden_primary, golden_secondary, golden_top_pair = _golden_rank_economies(economies)
    golden_has_standout = _golden_has_standout(counts)

    result = reconstruct_score_breakdown(row, bodies)

    # -- economies: all 7 keys, including Extraction --
    assert set(result['economies']) == {
        'Agriculture', 'Refinery', 'Industrial', 'HighTech',
        'Military', 'Tourism', 'Extraction',
    }
    assert result['economies'] == economies

    # -- dimensions: all 5 keys --
    assert set(result['dimensions']) == {
        'slots', 'strategic', 'safety', 'terraforming', 'diversity',
    }
    assert result['dimensions'] == {
        'slots':        row['slots'],
        'strategic':    row['body_quality'],
        'safety':       row['orbital_safety'],
        'terraforming': row['terraforming_potential'],
        'diversity':    row['body_diversity'],
    }

    # -- rocky sub-splits, against the real (unmodified) classify_bodies() --
    assert result['bodies']['rocky_geo']   == counts['rocky_geo']   == 1
    assert result['bodies']['rocky_bio']   == counts['rocky_bio']   == 1
    assert result['bodies']['rocky_rings'] == counts['rocky_rings'] == 1
    assert result['bodies']['rocky_clean'] == counts['rocky_clean'] == 1
    # the 5th body (geo+bio) must NOT land in any of the 4 reconstructed buckets
    assert counts['rocky_mixed'] == 1
    assert (result['bodies']['rocky_geo'] + result['bodies']['rocky_bio']
            + result['bodies']['rocky_rings'] + result['bodies']['rocky_clean']) == 4

    # -- top_pair shape and values --
    assert set(result['top_pair']) == {'a', 'b', 'a_score', 'b_score', 'pair_score'}
    assert result['top_pair'] == golden_top_pair

    # -- secondary_economy --
    assert result['secondary_economy'] == golden_secondary

    # -- primary_economy (NOT the same thing as the economy_suggestion column) --
    assert result['primary_economy'] == golden_primary

    # -- has_standout: no ELW/ammonia/black_hole/neutron, ww < 2, terraformable < 5 --
    assert result['has_standout'] is golden_has_standout is False

    # -- rationale / confidence / rating_version passthrough --
    assert result['rationale']      == row['rationale']
    assert result['confidence']     == row['confidence']
    assert result['rating_version'] == row['rating_version']


def test_has_standout_triggers_on_elw():
    bodies = _elw_bodies()
    row = rate_system(1002, bodies, 'G')
    assert row['elw_count'] >= 1

    result = reconstruct_score_breakdown(row, bodies)
    assert result['has_standout'] is True


def test_has_standout_false_when_no_trigger_present():
    bodies = _rocky_mix_bodies()
    row = rate_system(1003, bodies, 'G')
    result = reconstruct_score_breakdown(row, bodies)
    assert result['has_standout'] is False


def test_reconstruction_normalizes_missing_and_null_rating_values():
    row = {
        'score_agriculture': None,
        'score_refinery': 12,
        'score_industrial': None,
        'score_hightech': None,
        'score_military': None,
        'score_tourism': None,
        'score_extraction': None,
        'rocky_count': None,
    }

    result = reconstruct_score_breakdown(row)

    assert result['economies']['Agriculture'] == 0
    assert result['economies']['Refinery'] == 12
    assert result['primary_economy'] == 'Refinery'
    assert result['dimensions'] == {
        'slots': 0,
        'strategic': 0,
        'safety': 0,
        'terraforming': 0,
        'diversity': 0,
    }
    assert set(result['bodies'].values()) == {0}
    assert result['has_standout'] is False
