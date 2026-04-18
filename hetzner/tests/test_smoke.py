#!/usr/bin/env python3
"""
ED Finder — smoke tests
========================
No database required.  Run with:

    cd /opt/ed-finder
    python3 -m pytest tests/test_smoke.py -v

Or without pytest:

    python3 tests/test_smoke.py
"""

import sys
import os
import math
import unittest

# Redirect log files to /dev/null so imports don't fail in test environments
# that don't have /data/logs/.  Must be set before the modules are imported.
os.environ.setdefault('LOG_FILE', '/dev/null')

# Make sure both backend dirs are importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from build_ratings import (
    count_bodies,
    score_economy,
    rate_system,
    ECO_WEIGHTS,
    ECO_THRESHOLDS,
    SCOOPABLE_STARS,
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

from build_grid import _encode_cell_id  # see note below if missing


# ---------------------------------------------------------------------------
# 1. score_economy — the old integer-division bug always returned the same
#    score for any non-zero count.  Verify scaling is now linear up to cap.
# ---------------------------------------------------------------------------
class TestScoreEconomy(unittest.TestCase):

    def _empty_counts(self):
        return {k: 0 for k in [
            'elw','ww','ammonia','gasGiant','rocky','metalRich',
            'icy','rockyIce','hmc','landable','terraformable',
            'bio','geo','neutron','blackHole','whiteDwarf',
        ]}

    def test_zero_bodies_gives_zero(self):
        c = self._empty_counts()
        self.assertEqual(score_economy(c, 'Agriculture', None), 0)
        self.assertEqual(score_economy(c, 'Refinery', None), 0)
        self.assertEqual(score_economy(c, 'Military', None), 0)

    def test_one_elw_scores_lower_than_two_elw(self):
        """Regression: old integer division gave same score for 1 or 2 ELWs."""
        c1 = self._empty_counts(); c1['elw'] = 1
        c2 = self._empty_counts(); c2['elw'] = 2
        self.assertLess(
            score_economy(c1, 'Agriculture', None),
            score_economy(c2, 'Agriculture', None),
            "2 ELWs must score higher than 1 ELW",
        )

    def test_one_gas_giant_scores_lower_than_two(self):
        """Regression: old code — gasGiant count made no difference past 1."""
        c1 = self._empty_counts(); c1['gasGiant'] = 1
        c2 = self._empty_counts(); c2['gasGiant'] = 2
        self.assertLess(
            score_economy(c1, 'Industrial', None),
            score_economy(c2, 'Industrial', None),
        )

    def test_cap_is_respected(self):
        """Score must not exceed 100 even with absurdly many bodies."""
        c = self._empty_counts()
        c['elw'] = 999; c['ww'] = 999; c['terraformable'] = 999
        c['bio'] = 999; c['landable'] = 999
        score = score_economy(c, 'Agriculture', 'G')
        self.assertLessEqual(score, 100)
        self.assertGreater(score, 0)

    def test_scoopable_star_gives_bonus_for_agriculture(self):
        c = self._empty_counts(); c['elw'] = 1
        score_no_bonus = score_economy(c, 'Agriculture', 'M')   # non-scoopable
        score_bonus    = score_economy(c, 'Agriculture', 'G')   # scoopable
        self.assertGreater(score_bonus, score_no_bonus,
                           "Scoopable star should give Agriculture bonus")

    def test_scoopable_star_no_effect_on_refinery(self):
        c = self._empty_counts(); c['rocky'] = 3
        score_m = score_economy(c, 'Refinery', 'M')
        score_g = score_economy(c, 'Refinery', 'G')
        self.assertEqual(score_m, score_g,
                         "Scoopable star should NOT affect Refinery score")

    def test_score_is_int(self):
        c = self._empty_counts(); c['elw'] = 2
        self.assertIsInstance(score_economy(c, 'Agriculture', 'G'), int)


# ---------------------------------------------------------------------------
# 2. count_bodies — verifies subtype string matching
# ---------------------------------------------------------------------------
class TestCountBodies(unittest.TestCase):

    def test_earth_like_flag(self):
        bodies = [{'is_earth_like': True, 'subtype': 'Rocky body'}]
        c = count_bodies(bodies)
        self.assertEqual(c['elw'], 1)

    def test_earth_like_subtype_string(self):
        bodies = [{'is_earth_like': False, 'subtype': 'Earth-like world'}]
        c = count_bodies(bodies)
        self.assertEqual(c['elw'], 1)

    def test_gas_giant_subtype(self):
        bodies = [{'subtype': 'Gas giant with water-based life'}]
        c = count_bodies(bodies)
        self.assertEqual(c['gasGiant'], 1)

    def test_neutron_star(self):
        bodies = [{'subtype': 'Neutron Star'}]
        c = count_bodies(bodies)
        self.assertEqual(c['neutron'], 1)

    def test_black_hole(self):
        bodies = [{'subtype': 'Black Hole'}]
        c = count_bodies(bodies)
        self.assertEqual(c['blackHole'], 1)

    def test_bio_signals_counted(self):
        bodies = [{'subtype': 'Rocky body', 'bio_signal_count': 3}]
        c = count_bodies(bodies)
        self.assertEqual(c['bio'], 3)

    def test_landable_flag(self):
        bodies = [{'subtype': 'Rocky body', 'is_landable': True}]
        c = count_bodies(bodies)
        self.assertEqual(c['landable'], 1)

    def test_empty_list(self):
        c = count_bodies([])
        self.assertTrue(all(v == 0 for v in c.values()))

    def test_multiple_bodies(self):
        bodies = [
            {'is_earth_like': True,  'subtype': 'Earth-like world'},
            {'is_water_world': True, 'subtype': 'Water world'},
            {'subtype': 'Neutron Star'},
            {'subtype': 'Rocky body', 'is_landable': True, 'bio_signal_count': 2},
        ]
        c = count_bodies(bodies)
        self.assertEqual(c['elw'], 1)
        self.assertEqual(c['ww'], 1)
        self.assertEqual(c['neutron'], 1)
        self.assertEqual(c['landable'], 1)
        self.assertEqual(c['bio'], 2)


# ---------------------------------------------------------------------------
# 3. rate_system — end-to-end rating smoke test
# ---------------------------------------------------------------------------
class TestRateSystem(unittest.TestCase):

    def test_empty_system_scores_zero(self):
        result = rate_system(12345, [], None)
        self.assertEqual(result['score'], 0)
        self.assertIsNone(result['economy_suggestion'])

    def test_rich_system_scores_high(self):
        bodies = [
            {'is_earth_like': True,  'subtype': 'Earth-like world'},
            {'is_water_world': True, 'subtype': 'Water world'},
            {'subtype': 'Rocky body', 'is_landable': True, 'is_terraformable': True},
            {'subtype': 'Rocky body', 'is_landable': True},
            {'subtype': 'Gas giant with water-based life'},
        ]
        result = rate_system(99999, bodies, 'G')
        self.assertGreater(result['score'], 30,
                           "Rich system with ELW, WW, terraformable should score > 30")
        self.assertIsNotNone(result['economy_suggestion'])

    def test_result_keys_present(self):
        result = rate_system(1, [], None)
        for key in ('score', 'score_agriculture', 'score_refinery',
                    'score_industrial', 'score_hightech', 'score_military',
                    'score_tourism', 'economy_suggestion', 'elw_count',
                    'ww_count', 'neutron_count', 'black_hole_count',
                    'score_breakdown'):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_economy_suggestion_requires_score_20(self):
        """economy_suggestion should be None when best score < 20."""
        bodies = [{'subtype': 'Rocky body', 'is_landable': True}]
        result = rate_system(2, bodies, None)
        if result['score_agriculture'] < 20 and result['score_refinery'] < 20:
            self.assertIsNone(result['economy_suggestion'])


# ---------------------------------------------------------------------------
# 4. parse_ts — timestamp normalisation
# ---------------------------------------------------------------------------
class TestParseTs(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(parse_ts(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_ts(''))

    def test_unix_epoch_int(self):
        # epoch 0 is a valid (if unusual) timestamp; parse_ts must not discard it
        result = parse_ts(0)
        self.assertIsNotNone(result)
        self.assertIn('1970', result)

    def test_unix_epoch_int_realistic(self):
        result = parse_ts(1700000000)
        self.assertIsNotNone(result)
        self.assertIn('2023', result)

    def test_unix_epoch_float(self):
        result = parse_ts(1700000000.0)
        self.assertIsNotNone(result)
        self.assertIn('2023', result)

    def test_iso8601_z_suffix(self):
        result = parse_ts('2024-03-15T12:00:00Z')
        self.assertIsNotNone(result)
        self.assertIn('2024', result)

    def test_iso8601_offset(self):
        result = parse_ts('2024-03-15T12:00:00+00:00')
        self.assertIsNotNone(result)

    def test_invalid_string_passed_through(self):
        # Non-ISO strings pass through rather than returning None
        # (PostgreSQL will reject them, which is the right behaviour)
        result = parse_ts('not-a-date')
        self.assertEqual(result, 'not-a-date')

    def test_spansh_format(self):
        # Format seen in Spansh dumps
        result = parse_ts('2024-01-20 08:45:11')
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# 5. parse_bool
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
# 6. norm_economy and friends
# ---------------------------------------------------------------------------
class TestNormalisers(unittest.TestCase):

    # norm_economy
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

    # norm_security
    def test_security_variants(self):
        self.assertEqual(norm_security('High'), 'High')
        self.assertEqual(norm_security('$GAlAXY_MAP_INFO_state_High;'), 'High')
        self.assertEqual(norm_security(None), 'Unknown')

    # norm_allegiance
    def test_allegiance_variants(self):
        self.assertEqual(norm_allegiance('Federation'), 'Federation')
        self.assertEqual(norm_allegiance('empire'), 'Empire')
        self.assertEqual(norm_allegiance(None), 'Unknown')

    # norm_government
    def test_government_variants(self):
        self.assertEqual(norm_government('Democracy'), 'Democracy')
        self.assertEqual(norm_government('$government_Democracy;'), 'Democracy')
        self.assertEqual(norm_government(None), 'Unknown')

    # norm_station_type
    def test_station_type_variants(self):
        self.assertEqual(norm_station_type('Coriolis'), 'Coriolis')
        self.assertEqual(norm_station_type('coriolis'), 'Coriolis')
        self.assertEqual(norm_station_type('CraterPort'), 'PlanetaryPort')
        self.assertEqual(norm_station_type(None), 'Unknown')


# ---------------------------------------------------------------------------
# 7. Signal count helpers
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

    def test_parse_bio_signals_dict(self):
        b = {'signals': {'genuses': 3}}
        self.assertEqual(_parse_bio_signals(b), 3)

    def test_parse_bio_signals_list_of_dicts(self):
        b = {'signals': [
            {'type': 'Biology', 'count': 2},
            {'type': 'Geology', 'count': 1},
        ]}
        self.assertEqual(_parse_bio_signals(b), 2)

    def test_parse_bio_signals_fallback(self):
        b = {'bio_signal_count': 4}
        self.assertEqual(_parse_bio_signals(b), 4)

    def test_parse_geo_signals_dict(self):
        b = {'signals': {'geology': 2}}
        self.assertEqual(_parse_geo_signals(b), 2)

    def test_parse_geo_signals_fallback(self):
        b = {'geo_signal_count': 7}
        self.assertEqual(_parse_geo_signals(b), 7)


# ---------------------------------------------------------------------------
# 8. cell_id encoding — no hash collisions
# ---------------------------------------------------------------------------
class TestCellIdEncoding(unittest.TestCase):

    def test_distinct_cells_have_distinct_ids(self):
        """
        Regression: old base-1000 encoding caused collisions when z >= 1000.
        New base-100_000_000 encoding must be collision-free for realistic
        galaxy bounds (~2000 x 2000 x 2000 cells at 500ly resolution).
        """
        seen = set()
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2000):   # z goes well past the old 1000 limit
                    cid = _encode_cell_id(x, y, z)
                    self.assertNotIn(cid, seen,
                                     f"Collision at ({x},{y},{z})")
                    seen.add(cid)

    def test_large_z_no_collision_with_small_x(self):
        """Old encoding: (0, 0, 1000) == (0, 1, 0) because 1*1000 == 1000."""
        id_a = _encode_cell_id(0, 0, 1000)
        id_b = _encode_cell_id(0, 1, 0)
        self.assertNotEqual(id_a, id_b,
                            "cell (0,0,1000) must not collide with (0,1,0)")

    def test_result_fits_in_bigint(self):
        """cell_id must fit in a PostgreSQL BIGINT (< 2^63)."""
        # Worst-case realistic coords: 4000 cells each axis
        max_id = _encode_cell_id(4000, 4000, 4000)
        self.assertLess(max_id, 2**63)


# ---------------------------------------------------------------------------
# Run directly (no pytest required on the server)
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=2)
    result  = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
