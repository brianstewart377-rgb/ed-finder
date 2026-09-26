from scripts.v3_system_archetype_model import (
    SystemVectors, fit_all, summarise, tier_of, ARCHETYPE_VERSION, ARCHETYPE_KEYS,
)

def _vectors(**over):
    base = dict(
        pot=(0,)*7, qual=(None,)*7, qual_min=(0,)*7, qual_max=(0,)*7,
        completeness=(1.0,)*7, confidence=(1.0,)*7, opp={},
    )
    base.update(over)
    return SystemVectors(**base)

def test_tier_thresholds():
    assert [tier_of(s) for s in (88, 87, 76, 60, 45, 44, 0)] == ['S','A','A','B','C','D','D']

def test_version_and_key_set():
    assert ARCHETYPE_VERSION == 'v3-archetype-1'
    assert set(ARCHETYPE_KEYS) == {
        'paradise','mining_hub','manufacturing_hub','megacomplex',
        'research_hub','stronghold','population_capital','flexible',
    }

def test_paradise_strong_both_anchors_high_score():
    # Agriculture(1) & Tourism(6) both strong, high quality, ample capacity.
    v = _vectors(
        pot=(90,0,0,0,0,90,0),
        qual=(90,None,None,None,None,90,None),
        opp={1:(10, 80.0), 6:(10, 80.0)},
    )
    fits = {f.key: f for f in fit_all(v)}
    p = fits['paradise']
    # core=90, spec=0.85+0.15*0.9=0.985, cap=0.6+0.4*1*0.8=0.92, +5 synergy
    assert p.score >= 80 and p.tier in ('A','S')
    assert p.confidence == 1.0

def test_weakest_link_caps_score():
    # One weak anchor must drag the archetype down vs. a single strong economy.
    v = _vectors(pot=(90,0,0,0,0,10,0), opp={1:(10,80.0), 6:(10,80.0)})
    p = {f.key: f for f in fit_all(v)}['paradise']
    # core = 0.6*min(90,10) + 0.4*mean(90,10) = 6 + 20 = 26
    assert p.score < 40

def test_null_quality_uses_midpoint_and_lowers_confidence():
    v = _vectors(
        pot=(80,0,0,0,0,80,0), qual=(None,None,None,None,None,None,None),
        qual_min=(40,0,0,0,0,40,0), qual_max=(60,0,0,0,0,60,0),
        opp={1:(8,70.0), 6:(8,70.0)},
    )
    p = {f.key: f for f in fit_all(v)}['paradise']
    assert p.confidence < 1.0  # SPEC_UNKNOWN_CONF applied
    assert p.explanation['spec'] == round(0.85 + 0.15*0.5, 4)  # midpoint 50

def test_summary_picks_primary_and_secondary_by_score():
    v = _vectors(
        pot=(90,90,90,0,0,0,0), qual=(90,90,90,None,None,None,None),
        opp={1:(9,80.0),2:(9,80.0),3:(9,80.0)},
    )
    s = summarise(fit_all(v))
    assert s['best_colony_potential'] == max(f.score for f in fit_all(v))
    assert s['primary_archetype'] in ('manufacturing_hub','paradise','population_capital')
    assert 0.0 <= s['archetype_confidence'] <= 1.0

def test_flexible_rewards_breadth():
    broad = _vectors(pot=(60,60,60,60,0,0,0), qual=(60,60,60,60,None,None,None))
    narrow = _vectors(pot=(90,0,0,0,0,0,0), qual=(90,None,None,None,None,None,None))
    fb = {f.key: f for f in fit_all(broad)}['flexible']
    fn = {f.key: f for f in fit_all(narrow)}['flexible']
    assert fb.score > fn.score
