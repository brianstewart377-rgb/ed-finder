#!/usr/bin/env python3
"""
ED Finder — smoke tests
========================
No database required.  Run with:

    cd /opt/ed-finder
    python3 -m pytest tests/test_smoke.py -v

Or without pytest:

    python3 -m unittest tests.test_smoke -v
"""

import sys
import os
import unittest

# Redirect log files to /dev/null so imports don't fail in test environments
# that don't have /data/logs/.  Must be set before the modules are imported.
os.environ.setdefault('LOG_FILE', '/dev/null')

# Make sure both backend dirs are importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# build_ratings public API (v3.0+):
#   classify_bodies(bodies) -> counts
#   rate_system(id64, bodies, main_star_type) -> dict
#   SCOOPABLE_STARS         -> set of scoopable spectral-class letters
from build_ratings import (
    classify_bodies,
    rate_system,
    SCOOPABLE_STARS,
    _distance_weight,
    compute_terraforming_potential,
    compute_body_diversity,
    compute_confidence,
    generate_rationale,
)

from import_spansh import (
    parse_ts,
    parse_bool,
    norm_economy,
    norm_security,
    norm_allegiance,
    norm_government,
    norm_station_type,
    _to_signal_count,
    _parse_bio_signals,
    _parse_geo_signals,
)


# ---------------------------------------------------------------------------
# 1. rate_system — end-to-end smoke tests of the v3.0 scoring engine.
# ---------------------------------------------------------------------------
class TestRateSystem(unittest.TestCase):

    def test_empty_system_low_score(self):
        """Empty system has no bodies → score is in the low range and no
        economy is suggested. The exact baseline (~11) comes from the safety
        component in build_ratings.py v3.0."""
        result = rate_system(12345, [], None)
        self.assertLess(result['score'], 25)
        self.assertIsNone(result['economy_suggestion'])

    def test_rich_system_scores_above_empty(self):
        bodies = [
            {'is_earth_like': True,  'subtype': 'Earth-like world'},
            {'is_water_world': True, 'subtype': 'Water world'},
            {'subtype': 'Rocky body', 'is_landable': True, 'is_terraformable': True},
            {'subtype': 'Rocky body', 'is_landable': True},
            {'subtype': 'Gas giant with water-based life'},
        ]
        rich = rate_system(99999, bodies, 'G')
        empty = rate_system(99998, [], None)
        self.assertGreater(rich['score'], empty['score'])
        self.assertIsNotNone(rich['economy_suggestion'])

    def test_result_keys_present(self):
        """rate_system result must include every column the DB schema expects."""
        result = rate_system(1, [], None)
        required = (
            'score', 'score_agriculture', 'score_refinery',
            'score_industrial', 'score_hightech', 'score_military',
            'score_tourism', 'economy_suggestion', 'elw_count',
            'ww_count', 'neutron_count', 'black_hole_count',
            'score_breakdown',
        )
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_scores_are_bounded(self):
        """All per-economy scores must be in [0, 100]."""
        bodies = [{'subtype': 'Earth-like world', 'is_earth_like': True}] * 50
        result = rate_system(42, bodies, 'G')
        for k in ('score', 'score_agriculture', 'score_refinery',
                  'score_industrial', 'score_hightech',
                  'score_military', 'score_tourism'):
            v = result.get(k) or 0
            self.assertGreaterEqual(v, 0)
            self.assertLessEqual(v, 100, f"{k}={v} exceeds 100")


# ---------------------------------------------------------------------------
# 2. classify_bodies — verifies subtype string matching
# ---------------------------------------------------------------------------
class TestClassifyBodies(unittest.TestCase):

    def test_earth_like_flag(self):
        bodies = [{'is_earth_like': True, 'subtype': 'Earth-like world'}]
        c = classify_bodies(bodies)
        self.assertEqual(c['elw'], 1)

    def test_neutron_star(self):
        bodies = [{'subtype': 'Neutron Star'}]
        c = classify_bodies(bodies)
        self.assertEqual(c['neutron'], 1)

    def test_black_hole(self):
        bodies = [{'subtype': 'Black Hole'}]
        c = classify_bodies(bodies)
        self.assertEqual(c['black_hole'], 1)

    def test_empty_list(self):
        c = classify_bodies([])
        # All integer counts should be 0.
        for key in ('elw', 'ww', 'ammonia', 'neutron', 'black_hole', 'landable'):
            self.assertEqual(c.get(key, 0), 0)


# ---------------------------------------------------------------------------
# 3. parse_ts — timestamp normalisation
# ---------------------------------------------------------------------------
class TestParseTs(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(parse_ts(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_ts(''))

    def test_unix_epoch_int_realistic(self):
        result = parse_ts(1700000000)
        self.assertIsNotNone(result)
        self.assertIn('2023', result)

    def test_iso8601_z_suffix(self):
        result = parse_ts('2024-03-15T12:00:00Z')
        self.assertIsNotNone(result)
        self.assertIn('2024', result)

    def test_iso8601_offset(self):
        result = parse_ts('2024-03-15T12:00:00+00:00')
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# 4. parse_bool
# ---------------------------------------------------------------------------
class TestParseBool(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(parse_bool(None))

    def test_true_bool(self):
        self.assertTrue(parse_bool(True))

    def test_false_bool(self):
        self.assertFalse(parse_bool(False))

    def test_string_true(self):
        self.assertTrue(parse_bool('true'))
        self.assertTrue(parse_bool('1'))
        self.assertTrue(parse_bool('yes'))

    def test_string_false(self):
        self.assertFalse(parse_bool('false'))
        self.assertFalse(parse_bool('0'))
        self.assertFalse(parse_bool('no'))


# ---------------------------------------------------------------------------
# 5. norm_economy and friends
# ---------------------------------------------------------------------------
class TestNormalisers(unittest.TestCase):

    def test_hightech_variants(self):
        self.assertEqual(norm_economy('HighTech'), 'HighTech')
        self.assertEqual(norm_economy('hightech'), 'HighTech')
        self.assertEqual(norm_economy('$economy_HighTech;'), 'HighTech')

    def test_unknown_economy(self):
        self.assertEqual(norm_economy(None), 'Unknown')
        self.assertEqual(norm_economy(''), 'Unknown')
        self.assertEqual(norm_economy('garbage'), 'Unknown')

    def test_all_core_economies_map(self):
        for eco in ('Agriculture', 'Refinery', 'Industrial',
                    'HighTech', 'Military', 'Tourism'):
            self.assertEqual(norm_economy(eco), eco,
                             f"{eco} should map to itself")

    def test_security_variants(self):
        self.assertEqual(norm_security('High'), 'High')
        self.assertEqual(norm_security('$GAlAXY_MAP_INFO_state_High;'), 'High')
        self.assertEqual(norm_security(None), 'Unknown')

    def test_allegiance_variants(self):
        self.assertEqual(norm_allegiance('Federation'), 'Federation')
        self.assertEqual(norm_allegiance('empire'), 'Empire')
        self.assertEqual(norm_allegiance(None), 'Unknown')

    def test_government_variants(self):
        self.assertEqual(norm_government('Democracy'), 'Democracy')
        self.assertEqual(norm_government('$government_Democracy;'), 'Democracy')
        self.assertEqual(norm_government(None), 'Unknown')

    def test_station_type_variants(self):
        self.assertEqual(norm_station_type('Coriolis'), 'Coriolis')
        self.assertEqual(norm_station_type('coriolis'), 'Coriolis')
        self.assertEqual(norm_station_type('CraterPort'), 'PlanetaryPort')
        self.assertEqual(norm_station_type(None), 'Unknown')


# ---------------------------------------------------------------------------
# 6. Signal count helpers
# ---------------------------------------------------------------------------
class TestSignalHelpers(unittest.TestCase):

    def test_to_signal_count_none(self):
        self.assertEqual(_to_signal_count(None), 0)

    def test_to_signal_count_int(self):
        self.assertEqual(_to_signal_count(3), 3)

    def test_to_signal_count_string(self):
        self.assertEqual(_to_signal_count('5'), 5)

    def test_to_signal_count_list(self):
        self.assertEqual(_to_signal_count(['a', 'b', 'c']), 3)

    def test_parse_bio_signals_list_of_dicts(self):
        b = {'signals': [
            {'type': 'Biology', 'count': 2},
            {'type': 'Geology', 'count': 1},
        ]}
        self.assertEqual(_parse_bio_signals(b), 2)

    def test_parse_bio_signals_fallback(self):
        b = {'bio_signal_count': 4}
        self.assertEqual(_parse_bio_signals(b), 4)

    def test_parse_geo_signals_fallback(self):
        b = {'geo_signal_count': 7}
        self.assertEqual(_parse_geo_signals(b), 7)


# ---------------------------------------------------------------------------
# 7. SCOOPABLE_STARS — constant sanity check
# ---------------------------------------------------------------------------
class TestScoopableStars(unittest.TestCase):

    def test_contains_main_sequence_classes(self):
        for cls in ('O', 'B', 'A', 'F', 'G', 'K', 'M'):
            self.assertIn(cls, SCOOPABLE_STARS)

    def test_excludes_non_scoopable(self):
        for cls in ('L', 'T', 'Y', 'D', 'N', 'W'):
            self.assertNotIn(cls, SCOOPABLE_STARS)


# ---------------------------------------------------------------------------
# 8. v3.1 — distance-from-arrival-star weighting
# ---------------------------------------------------------------------------
class TestDistanceWeight(unittest.TestCase):

    def test_none_returns_one(self):
        self.assertEqual(_distance_weight(None), 1.0)

    def test_unknown_returns_one(self):
        self.assertEqual(_distance_weight("garbage"), 1.0)

    def test_close_is_full_weight(self):
        self.assertEqual(_distance_weight(500), 1.0)
        self.assertEqual(_distance_weight(1000), 1.0)

    def test_medium_is_reduced(self):
        self.assertLess(_distance_weight(5_000), 1.0)
        self.assertGreater(_distance_weight(5_000), 0.5)

    def test_far_is_low(self):
        self.assertLess(_distance_weight(50_000), 0.80)

    def test_very_far_is_floored(self):
        self.assertAlmostEqual(_distance_weight(250_000), 0.30)
        self.assertAlmostEqual(_distance_weight(1_000_000), 0.30)


# ---------------------------------------------------------------------------
# 9. v3.1 — terraforming potential quality score
# ---------------------------------------------------------------------------
class TestTerraformingPotential(unittest.TestCase):

    def test_empty_system_is_zero(self):
        c = classify_bodies([])
        self.assertEqual(compute_terraforming_potential(c, None), 0)

    def test_hmc_near_g_star_scores_high(self):
        bodies = [
            {'subtype': 'High metal content world', 'is_terraformable': True,
             'distance_from_star': 200},
            {'subtype': 'High metal content world', 'is_terraformable': True,
             'distance_from_star': 500},
        ]
        c = classify_bodies(bodies)
        score = compute_terraforming_potential(c, 'G')
        self.assertGreater(score, 40)

    def test_far_terraformable_scores_lower_than_close(self):
        close = classify_bodies([
            {'subtype': 'Rocky body', 'is_terraformable': True,
             'distance_from_star': 200},
        ])
        far = classify_bodies([
            {'subtype': 'Rocky body', 'is_terraformable': True,
             'distance_from_star': 250_000},
        ])
        self.assertGreater(
            compute_terraforming_potential(close, 'G'),
            compute_terraforming_potential(far, 'G'),
        )


# ---------------------------------------------------------------------------
# 10. v3.1 — body diversity bonus
# ---------------------------------------------------------------------------
class TestBodyDiversity(unittest.TestCase):

    def test_single_type_is_zero(self):
        c = classify_bodies([{'subtype': 'High metal content world'}] * 12)
        self.assertEqual(compute_body_diversity(c), 0)

    def test_varied_system_gets_bonus(self):
        c = classify_bodies([
            {'subtype': 'Earth-like world',          'is_earth_like': True},
            {'subtype': 'Water world',               'is_water_world': True},
            {'subtype': 'Rocky body',                'is_landable': True},
            {'subtype': 'High metal content world'},
            {'subtype': 'Icy body'},
            {'subtype': 'Gas giant with ammonia-based life'},
        ])
        self.assertGreater(compute_body_diversity(c), 15)

    def test_empty_is_zero(self):
        c = classify_bodies([])
        self.assertEqual(compute_body_diversity(c), 0)


# ---------------------------------------------------------------------------
# 11. v3.1 — data-freshness confidence
# ---------------------------------------------------------------------------
class TestConfidence(unittest.TestCase):

    def test_none_is_mid(self):
        self.assertEqual(compute_confidence(None), 0.85)

    def test_recent_is_high(self):
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc)
        self.assertGreaterEqual(compute_confidence(recent), 0.95)

    def test_old_is_floored(self):
        from datetime import datetime, timezone, timedelta
        ten_years_ago = datetime.now(timezone.utc) - timedelta(days=10 * 365)
        conf = compute_confidence(ten_years_ago)
        self.assertGreaterEqual(conf, 0.70)
        self.assertLessEqual(conf, 0.80)

    def test_iso_string_accepted(self):
        self.assertIsInstance(compute_confidence("2024-06-15T12:00:00Z"), float)

    def test_multi_report_boost(self):
        from datetime import datetime, timezone, timedelta
        ts = datetime.now(timezone.utc) - timedelta(days=500)
        single = compute_confidence(ts, report_count=1)
        triple = compute_confidence(ts, report_count=3)
        self.assertGreaterEqual(triple, single)


# ---------------------------------------------------------------------------
# 12. v3.1 — rationale string is always populated, under 160 chars
# ---------------------------------------------------------------------------
class TestRationale(unittest.TestCase):

    def test_empty_system_gets_some_text(self):
        result = rate_system(1, [], None)
        self.assertTrue(result['rationale'])
        self.assertLessEqual(len(result['rationale']), 160)

    def test_rich_system_mentions_signatures(self):
        bodies = [
            {'subtype': 'Earth-like world', 'is_earth_like': True},
            {'subtype': 'Water world',      'is_water_world': True},
            {'subtype': 'Rocky body',       'is_landable': True, 'is_terraformable': True},
        ]
        result = rate_system(2, bodies, 'G')
        text = result['rationale'].lower()
        self.assertTrue('elw' in text or 'earth' in text
                        or 'ww' in text or 'water' in text)
        self.assertLessEqual(len(result['rationale']), 160)


# ---------------------------------------------------------------------------
# 13. v3.1 — new fields are present in rate_system output
# ---------------------------------------------------------------------------
class TestV31ResultFields(unittest.TestCase):

    def test_all_v31_keys_present(self):
        result = rate_system(1, [], None)
        for key in ('score_extraction', 'terraforming_potential',
                    'body_diversity', 'confidence', 'rationale'):
            self.assertIn(key, result, f"Missing v3.1 field: {key}")

    def test_extraction_in_breakdown(self):
        """v3.0 segregated Extraction from the economies dict; v3.1 includes it."""
        bodies = [{'subtype': 'Metal-rich body'}] * 5
        result = rate_system(3, bodies, 'G')
        economies = result['score_breakdown']['economies']
        self.assertIn('Extraction', economies)

    def test_confidence_always_float_in_range(self):
        result = rate_system(1, [], None)
        self.assertIsInstance(result['confidence'], float)
        self.assertGreaterEqual(result['confidence'], 0.70)
        self.assertLessEqual(result['confidence'], 1.00)


# ---------------------------------------------------------------------------
# Run directly (no pytest required on the server)
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=2)
    result  = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
