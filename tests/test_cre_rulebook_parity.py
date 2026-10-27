"""Parity between ED-Finder's hand-coded mechanics and the pinned CRE rulebook.

Owner decision D1 (2026-10-21, ``docs/ROADMAP.md``): the Colonisation Research
Engine (CRE) publishes a versioned rulebook that ED-Finder reads. The pinned
release lives in ``docs/reference/colonisation/cre-rulebook/``. This test
compares the tables and numbers ED-Finder hard-codes with it.

Every comparison either matches the rulebook or is listed in
``KNOWN_DIFFERENCES`` with the reason it differs. A new difference fails, and so
does a listed difference that no longer exists (delete its entry). The test
only reads code: it changes no score, constant or behaviour.

It compares rule tables, not data adapters: how the canonical V4 adapter maps
body and reserve data onto ``BodyFact`` (Mega Guide audit 2026-10-21, finding
F6) is out of scope.
"""
from __future__ import annotations

import ast
import hashlib
import json
import operator
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from domain import colonisation_rules, ratings_v4  # noqa: E402
from domain.ratings_v4 import BodyFact, SystemFacts, opportunities_from_facts  # noqa: E402
from mechanics import cp_rules, link_rules  # noqa: E402


RULEBOOK_DIR = ROOT / 'docs' / 'reference' / 'colonisation' / 'cre-rulebook'
SCHEMA = 'cre-rulebook/v1'
STATUSES = {'Confirmed', 'Likely', 'Extracted', 'Disputed'}

AUDIT = 'Mega Guide audit 2026-10-21 (docs/development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md)'
V2_PLANNER = (
    'Legacy V2 planner/simulator code, reachable only through API routes; the V3 web app has no '
    'planner UI.'
)

KNOWN_DIFFERENCES: dict[str, str] = {
    # RB-0003: construction-point escalation.
    'RB-0003: cp_rules escalates dodecahedron_t3, which RB-0003 does not list': (
        'The guide (v2.3.0) does not name the Dodecahedron; #902 treats it as a Tier 3 port like '
        'Orbis and Ocellus (comment in cp_rules.py). Not verified in game.'
    ),
    # RB-0010 / RB-0011: inherited economies.
    'RB-0010: colonisation_rules base ammonia_world': (
        f'{V2_PLANNER} It treats Ammonia HighTech as a modifier ({AUDIT}, finding 7). The CPE '
        'fold-in (D2) will read RB-0010.'
    ),
    'RB-0010: colonisation_rules base brown_dwarf': f'{V2_PLANNER} Stars get no Military ({AUDIT}, finding 7).',
    'RB-0010: colonisation_rules base other_star': f'{V2_PLANNER} Stars get no Military ({AUDIT}, finding 7).',
    'RB-0011: colonisation_rules has no Terraforming economy': (
        f'{V2_PLANNER} Terraforming is not modelled ({AUDIT}, gap 5).'
    ),
    'RB-0011: colonisation_rules rings differ on ammonia_world, black_hole, brown_dwarf, earth_like_world, '
    'gas_giant, icy_body, neutron_star, other_star, rocky_ice_body, water_world, white_dwarf': (
        f'{V2_PLANNER} Most ring, geological and biological modifiers are missing ({AUDIT}, finding 7).'
    ),
    'RB-0011: colonisation_rules organics differ on icy_body, metal_rich_body, rocky_ice_body': 'As above.',
    'RB-0011: colonisation_rules geologicals differ on icy_body, metal_rich_body, rocky_ice_body': 'As above.',
    'RB-0011: ratings_v4 has no Terraforming economy': (
        'Ratings V4.0 rates seven economies; Terraforming is not one of them (frozen scorer 4.0.0).'
    ),
    # RB-0012: inherited strength.
    'RB-0012: ratings_v4 scores native plus modifier above native alone': (
        f'Frozen Ratings V4.0 scores 85 against 75 ({AUDIT}, F1). RB-0012 is Disputed (C-0011); the '
        'owner decided on 2026-10-21 to publish on V4.0 and fix this in Ratings V4.1.'
    ),
    'RB-0012: ratings_v4 scores a modifier-only economy below a native one': (
        f'Frozen Ratings V4.0 scores 55 against 75 by design ({AUDIT}, F2: "inheritance establishes '
        'eligibility, not equal suitability").'
    ),
    # RB-0018: strong-link modifiers.
    'RB-0018: ratings_v4 applies Disputed Agriculture boosts on_or_orbiting_terraformable_body': (
        f'Frozen Ratings V4.0 applies the boost; the guide reports it bugged (C-0013; {AUDIT}, F3). '
        'Fix in Ratings V4.1.'
    ),
    'RB-0018: ratings_v4 does not model Agriculture decreases '
    'orbiting_moon_tidally_locked_to_planet_tidally_locked_to_star': (
        'V4 BodyFact has one tidally_locked flag and no parent chain, so every locked body takes the '
        f'planet malus ({AUDIT}, F4).'
    ),
    'RB-0018: ratings_v4 does not model Agriculture decreases '
    'on_moon_tidally_locked_to_planet_tidally_locked_to_star': 'As above.',
    # RB-0019: link modifier size.
    'RB-0019: link_rules.LINK_MODIFIER_DELTAS': (
        f'{V2_PLANNER} The simulator uses its own per-condition sizes, not the flat +/-0.4 '
        f'({AUDIT}, finding 7). Ratings V4 does not read this table.'
    ),
}


# ---------------------------------------------------------------- rulebook


def load_rulebook() -> dict[str, dict]:
    pin = json.loads((RULEBOOK_DIR / 'pin.json').read_text(encoding='utf-8'))
    raw = (RULEBOOK_DIR / 'rulebook.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin['sha256'], 'rulebook.json does not match its pin'
    book = json.loads(raw)
    assert book['schema'] == SCHEMA
    assert book['release_tag'] == pin['release_tag'] == f"cre-knowledge-v{book['knowledge_version']}"
    rules = {rule['id']: rule for rule in book['rules']}
    assert len(rules) == len(book['rules']), 'duplicate rule ids'
    return rules


RULES = load_rulebook()


def value(rule_id: str) -> dict:
    return RULES[rule_id]['value']


_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


def _formula(text: str, n: int) -> int:
    """Evaluate a rulebook formula such as ``3+(n-2)*2`` (integers, + - * and n only)."""
    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.Name) and node.id == 'n':
            return n
        raise ValueError(f'unsupported formula: {text}')
    return walk(ast.parse(text, mode='eval').body)


def port_cost(tier: dict, n: int) -> int:
    """The rulebook cost of the n-th counted T2/T3 port (1-based, Primary Port not counted)."""
    first = tier['first_five']
    return first[n - 1] if n <= len(first) else _formula(tier['nth_formula'], n)


# RB-0003 facility name -> catalogue facility id in cp_rules.ESCALATING_PORT_TIER_BY_ID.
ESCALATING_PORT_IDS = {
    'Coriolis': 'coriolis_station',
    'Asteroid Base': 'asteroid_base',
    'Orbis': 'orbis_t3',
    'Ocellus': 'ocellus_station',
    'T3 Planetary Port': 'planetary_port',
}
COUNTED_PORTS_CHECKED = 20


# ---------------------------------------------------------------- samples

# RB-0010 body key -> (Ratings V4 body_class, colonisation_rules row).
BODY_SAMPLES: dict[str, tuple[str, dict[str, str]]] = {
    'black_hole': ('Black Hole', {'body_type': 'Star', 'subtype': 'Black Hole'}),
    'neutron_star': ('Neutron Star', {'body_type': 'Star', 'subtype': 'Neutron Star'}),
    'white_dwarf': ('White Dwarf (DA) Star', {'body_type': 'Star', 'subtype': 'White Dwarf (DA) Star'}),
    'brown_dwarf': ('L (Brown dwarf) Star', {'body_type': 'Star', 'subtype': 'L (Brown dwarf) Star'}),
    'other_star': ('G (White-Yellow) Star', {'body_type': 'Star', 'subtype': 'G (White-Yellow) Star'}),
    'earth_like_world': ('Earth-like world', {'body_type': 'Planet', 'subtype': 'Earth-like world'}),
    'water_world': ('Water world', {'body_type': 'Planet', 'subtype': 'Water world'}),
    'ammonia_world': ('Ammonia world', {'body_type': 'Planet', 'subtype': 'Ammonia world'}),
    'gas_giant': ('Class I gas giant', {'body_type': 'Planet', 'subtype': 'Class I gas giant'}),
    'high_metal_content_world': ('High metal content world', {'body_type': 'Planet', 'subtype': 'High metal content world'}),
    'metal_rich_body': ('Metal-rich body', {'body_type': 'Planet', 'subtype': 'Metal-rich body'}),
    'rocky_ice_body': ('Rocky Ice world', {'body_type': 'Planet', 'subtype': 'Rocky Ice world'}),
    'rocky_body': ('Rocky body', {'body_type': 'Planet', 'subtype': 'Rocky body'}),
    'icy_body': ('Icy body', {'body_type': 'Planet', 'subtype': 'Icy body'}),
}
STARS = {'black_hole', 'neutron_star', 'white_dwarf', 'brown_dwarf', 'other_star'}

# RB-0011 modifier -> (Ratings V4 BodyFact flag, colonisation_rules row flag).
MODIFIER_FLAGS = {
    'rings': ('rings', 'is_ringed'),
    'organics': ('biologicals', 'has_bio'),
    'geologicals': ('geologicals', 'has_geo'),
}


def modifier_bodies(modifier: str) -> list[str]:
    """Bodies that can carry the modifier: stars only have rings (belts); RB-0027 exclusions apply."""
    if modifier == 'rings':
        return sorted(BODY_SAMPLES)
    excluded = set(value('RB-0027')['bodies_without_geological_or_biological_overrides'])
    return sorted(set(BODY_SAMPLES) - STARS - excluded)


def v4_body(body_class: str, name: str = 'target', **flags: object) -> BodyFact:
    return BodyFact(candidate_id=name, body_class=body_class, **flags)


def v4_opportunities(*bodies: BodyFact, reserve: str | None = None) -> dict[str, ratings_v4.Opportunity]:
    """The first body's opportunity per economy."""
    facts = SystemFacts(bodies=bodies, reserve_level=reserve, body_inventory_complete=True)
    target = bodies[0].candidate_id
    return {o.economy: o for o in opportunities_from_facts(facts) if o.candidate_id == target}


# ---------------------------------------------------------------- comparisons


def cp_differences() -> set[str]:
    escalation = value('RB-0003')
    t2, t3 = escalation['T2'], escalation['T3']
    assert (t2['currency'], t3['currency']) == ('yellow', 'green')
    found = set()
    counted = range(1, COUNTED_PORTS_CHECKED + 1)
    if [cp_rules.t2_port_yellow_cost(n) for n in counted] != [port_cost(t2, n) for n in counted]:
        found.add('RB-0003: cp_rules.t2_port_yellow_cost')
    if [cp_rules.t3_port_green_cost(n) for n in counted] != [port_cost(t3, n) for n in counted]:
        found.add('RB-0003: cp_rules.t3_port_green_cost')
    # Which catalogue ports escalate, and at which tier.
    names = set(t2['facilities']) | set(t3['facilities'])
    assert names <= set(ESCALATING_PORT_IDS), f'RB-0003 names ports ESCALATING_PORT_IDS lacks: {sorted(names - set(ESCALATING_PORT_IDS))}'
    expected = {ESCALATING_PORT_IDS[name]: 2 for name in t2['facilities']}
    expected |= {ESCALATING_PORT_IDS[name]: 3 for name in t3['facilities']}
    ours = cp_rules.ESCALATING_PORT_TIER_BY_ID
    for facility_id in sorted(set(ours) | set(expected)):
        if facility_id not in expected:
            found.add(f'RB-0003: cp_rules escalates {facility_id}, which RB-0003 does not list')
        elif ours.get(facility_id) != expected[facility_id]:
            found.add(f'RB-0003: cp_rules tier for {facility_id}')
    return found


def link_differences() -> set[str]:
    found = set()
    strong = {int(tier): strength for tier, strength in value('RB-0015')['strong_by_tier'].items()}
    if link_rules.STRONG_LINK_BY_TIER != strong:
        found.add('RB-0015: link_rules.STRONG_LINK_BY_TIER')
    if link_rules.WEAK_LINK_STRENGTH != value('RB-0016')['weak']:
        found.add('RB-0016: link_rules.WEAK_LINK_STRENGTH')
    size = value('RB-0019')
    if link_rules.MIN_STRONG_LINK_MODIFIER != size['minimum_strong_link']:
        found.add('RB-0019: link_rules.MIN_STRONG_LINK_MODIFIER')
    if any(delta != (size['boost'] if delta > 0 else size['decrease']) for delta in link_rules.LINK_MODIFIER_DELTAS.values()):
        found.add('RB-0019: link_rules.LINK_MODIFIER_DELTAS')
    return found


def base_economy_differences() -> set[str]:
    table = value('RB-0010')['economies']
    assert set(table) == set(BODY_SAMPLES), 'RB-0010 body keys changed: update BODY_SAMPLES'
    found = set()
    for key, expected in table.items():
        v4_class, row = BODY_SAMPLES[key]
        v4 = {economy for economy, o in v4_opportunities(v4_body(v4_class)).items() if o.native}
        if v4 != set(expected):
            found.add(f'RB-0010: ratings_v4 native {key}')
        if set(colonisation_rules.profile_body(row).base_economies) != set(expected):
            found.add(f'RB-0010: colonisation_rules base {key}')
    return found


def _colonisation_economies(row: dict) -> set[str]:
    profile = colonisation_rules.profile_body(row)
    return set(profile.base_economies) | set(profile.modifier_economies)


def modifier_differences() -> set[str]:
    base = value('RB-0010')['economies']
    modifiers = value('RB-0011')['economies']
    assert set(modifiers) == set(MODIFIER_FLAGS), 'RB-0011 modifiers changed: update MODIFIER_FLAGS'
    found = set()
    for module, economies in (('ratings_v4', set(ratings_v4.ECONOMIES)), ('colonisation_rules', colonisation_rules.ECONOMIES)):
        if not set().union(*modifiers.values()) <= economies:
            found.add(f'RB-0011: {module} has no Terraforming economy')
    for modifier, (v4_flag, row_flag) in MODIFIER_FLAGS.items():
        v4_wrong, colonisation_wrong = [], []
        for key in modifier_bodies(modifier):
            v4_class, row = BODY_SAMPLES[key]
            # Ratings V4 marks modifier-derived economies explicitly.
            v4 = {economy for economy, o in v4_opportunities(v4_body(v4_class, **{v4_flag: True})).items() if o.modifier}
            if v4 != set(modifiers[modifier]) & set(ratings_v4.ECONOMIES):
                v4_wrong.append(key)
            # colonisation_rules folds them in: compare what the modifier adds to the body.
            added = _colonisation_economies({**row, row_flag: True}) - _colonisation_economies(row)
            expected = (set(modifiers[modifier]) - set(base[key])) & colonisation_rules.ECONOMIES
            if added != expected:
                colonisation_wrong.append(key)
        if v4_wrong:
            found.add(f"RB-0011: ratings_v4 {modifier} differ on {', '.join(v4_wrong)}")
        if colonisation_wrong:
            found.add(f"RB-0011: colonisation_rules {modifier} differ on {', '.join(colonisation_wrong)}")
    return found


def stacking_differences() -> set[str]:
    strength = value('RB-0012')
    assert strength['stacks_with_base'] is False and strength['inherited_economy_strength'] == 1.0
    found = set()
    if ratings_v4.NATIVE_AND_MODIFIER_BASE != ratings_v4.NATIVE_BASE:
        found.add('RB-0012: ratings_v4 scores native plus modifier above native alone')
    if ratings_v4.MODIFIER_BASE != ratings_v4.NATIVE_BASE:
        found.add('RB-0012: ratings_v4 scores a modifier-only economy below a native one')
    return found


Probe = Callable[[], Iterable[dict[str, ratings_v4.Opportunity]]]


def _probe(*systems: tuple[tuple[BodyFact, ...], str | None]) -> Probe:
    return lambda: [v4_opportunities(*bodies, reserve=reserve) for bodies, reserve in systems]


def _body(body_class: str, **flags: object) -> Probe:
    return _probe(((v4_body(body_class, **flags),), None))


def _reserves(*levels: str) -> Probe:
    return _probe(*(((v4_body('Rocky body'),), level) for level in levels))


def _exotic(body_class: str) -> Probe:
    return _probe(((v4_body('Rocky body'), v4_body(body_class, name='exotic')), None))


# (economy, direction, RB-0018 condition) -> (probe, the V4 rule names it fires).
# Conditions missing here are differences ("does not model").
V4_STRONG_LINK_RULES: dict[tuple[str, str, str], tuple[Probe, set[str]]] = {
    ('Agriculture', 'boosts', 'orbiting_earth_like_world'): (_body('Earth-like world'), {'elw-agriculture'}),
    ('Agriculture', 'boosts', 'orbiting_water_world'): (_body('Water world'), {'water-world-agriculture'}),
    ('Agriculture', 'boosts', 'on_or_orbiting_terraformable_body'): (_body('Rocky body', terraformable=True), {'terraformable-agriculture'}),
    ('Agriculture', 'boosts', 'on_or_orbiting_body_with_organics'): (_body('Rocky body', biologicals=True), {'biologicals-agriculture'}),
    ('Agriculture', 'decreases', 'on_or_orbiting_icy_body'): (_body('Icy body'), {'icy-agriculture'}),
    ('Agriculture', 'decreases', 'on_or_orbiting_planet_tidally_locked_to_star'): (_body('Rocky body', tidally_locked=True), {'tidal-lock-agriculture'}),
    ('Extraction', 'boosts', 'system_major_or_pristine_resources'): (_reserves('Major', 'Pristine'), {'reserves-major', 'reserves-pristine'}),
    ('Extraction', 'boosts', 'on_or_orbiting_body_with_volcanism'): (_body('Rocky body', volcanism=True), {'volcanism-extraction'}),
    ('Extraction', 'decreases', 'system_low_or_depleted_resources'): (_reserves('Low', 'Depleted'), {'reserves-low', 'reserves-depleted'}),
    ('HighTech', 'boosts', 'orbiting_ammonia_world'): (_body('Ammonia world'), {'ammonia-hightech'}),
    ('HighTech', 'boosts', 'orbiting_earth_like_world'): (_body('Earth-like world'), {'elw-hightech'}),
    ('HighTech', 'boosts', 'orbiting_water_world'): (_body('Water world'), {'water-world-hightech'}),
    ('HighTech', 'boosts', 'on_or_orbiting_body_with_geologicals'): (_body('Rocky body', geologicals=True), {'geologicals-hightech'}),
    ('HighTech', 'boosts', 'on_or_orbiting_body_with_organics'): (_body('Rocky body', biologicals=True), {'biologicals-hightech'}),
    ('Industrial', 'boosts', 'system_major_or_pristine_resources'): (_reserves('Major', 'Pristine'), {'reserves-major', 'reserves-pristine'}),
    ('Industrial', 'decreases', 'system_low_or_depleted_resources'): (_reserves('Low', 'Depleted'), {'reserves-low', 'reserves-depleted'}),
    ('Refinery', 'boosts', 'system_major_or_pristine_resources'): (_reserves('Major', 'Pristine'), {'reserves-major', 'reserves-pristine'}),
    ('Refinery', 'decreases', 'system_low_or_depleted_resources'): (_reserves('Low', 'Depleted'), {'reserves-low', 'reserves-depleted'}),
    ('Tourism', 'boosts', 'orbiting_ammonia_world'): (_body('Ammonia world'), {'ammonia-tourism'}),
    ('Tourism', 'boosts', 'system_with_black_hole'): (_exotic('Black Hole'), {'black hole-system-tourism'}),
    ('Tourism', 'boosts', 'orbiting_earth_like_world'): (_body('Earth-like world'), {'elw-tourism'}),
    ('Tourism', 'boosts', 'on_or_orbiting_body_with_geologicals'): (_body('Rocky body', geologicals=True), {'geologicals-tourism'}),
    ('Tourism', 'boosts', 'on_or_orbiting_body_with_organics'): (_body('Rocky body', biologicals=True), {'biologicals-tourism'}),
    ('Tourism', 'boosts', 'orbiting_water_world'): (_body('Water world'), {'water-world-tourism'}),
    ('Tourism', 'boosts', 'system_with_white_dwarf'): (_exotic('White Dwarf (DA) Star'), {'white dwarf-system-tourism'}),
    ('Tourism', 'boosts', 'system_with_neutron_star'): (_exotic('Neutron Star'), {'neutron star-system-tourism'}),
}


def rulebook_conditions() -> dict[tuple[str, str, str], str]:
    conditions = {}
    for economy, entry in value('RB-0018')['economies'].items():
        for direction in ('boosts', 'decreases'):
            for condition in entry[direction]:
                conditions[(economy, direction, condition['condition'])] = condition['status']
    return conditions


def _fired(opportunity: ratings_v4.Opportunity, direction: str) -> set[str]:
    return set(opportunity.strong_positive_rules if direction == 'boosts' else opportunity.strong_negative_rules)


def strong_link_differences() -> set[str]:
    conditions = rulebook_conditions()
    unknown = set(V4_STRONG_LINK_RULES) - set(conditions)
    assert not unknown, f'V4_STRONG_LINK_RULES names conditions RB-0018 does not have: {sorted(unknown)}'
    found = set()
    for key, status in conditions.items():
        economy, direction, condition = key
        if key not in V4_STRONG_LINK_RULES:
            found.add(f'RB-0018: ratings_v4 does not model {economy} {direction} {condition}')
            continue
        probe, expected = V4_STRONG_LINK_RULES[key]
        fired = set().union(*(_fired(system[economy], direction) for system in probe()))
        assert fired == expected, f'{key}: V4 fires {sorted(fired)}, expected {sorted(expected)}'
        if status == 'Disputed':
            found.add(f'RB-0018: ratings_v4 applies Disputed {economy} {direction} {condition}')
    return found


COMPARISONS: dict[str, Callable[[], set[str]]] = {
    'construction points (RB-0003)': cp_differences,
    'link strengths (RB-0015, RB-0016, RB-0019)': link_differences,
    'base economies (RB-0010)': base_economy_differences,
    'modifiers (RB-0011)': modifier_differences,
    'stacking (RB-0012)': stacking_differences,
    'strong-link modifiers (RB-0018)': strong_link_differences,
}
_RULE_IDS = {
    'construction points (RB-0003)': ('RB-0003',),
    'link strengths (RB-0015, RB-0016, RB-0019)': ('RB-0015', 'RB-0016', 'RB-0019'),
    'base economies (RB-0010)': ('RB-0010',),
    'modifiers (RB-0011)': ('RB-0011',),
    'stacking (RB-0012)': ('RB-0012',),
    'strong-link modifiers (RB-0018)': ('RB-0018',),
}


# ---------------------------------------------------------------- tests


def test_pinned_rulebook_is_well_formed():
    assert len(RULES) >= 27
    for rule_id, rule in RULES.items():
        assert rule['status'] in STATUSES, rule_id
        assert rule['sources'], rule_id
    for rule_ids in _RULE_IDS.values():
        assert set(rule_ids) <= set(RULES)


@pytest.mark.parametrize('name', sorted(COMPARISONS))
def test_differences_are_exactly_the_known_ones(name):
    prefixes = tuple(f'{rule_id}: ' for rule_id in _RULE_IDS[name])
    known = {key for key in KNOWN_DIFFERENCES if key.startswith(prefixes)}
    found = COMPARISONS[name]()
    assert found - known == set(), f'new differences from the CRE rulebook: {sorted(found - known)}'
    assert known - found == set(), f'resolved differences: delete from KNOWN_DIFFERENCES: {sorted(known - found)}'


def test_every_known_difference_belongs_to_a_comparison_and_has_a_reason():
    prefixes = tuple(f'{rule_id}: ' for rule_ids in _RULE_IDS.values() for rule_id in rule_ids)
    for key, reason in KNOWN_DIFFERENCES.items():
        assert key.startswith(prefixes), key
        assert reason.strip(), key


def test_every_v4_strong_link_rule_maps_to_a_rulebook_condition():
    """Ratings V4 fires no strong-link rule the rulebook does not have."""
    mapped = set().union(*(names for _, names in V4_STRONG_LINK_RULES.values()))
    fired: set[str] = set()
    flags = ('rings', 'biologicals', 'geologicals', 'volcanism', 'terraformable', 'tidally_locked')
    for v4_class, _ in BODY_SAMPLES.values():
        for reserve in (None, 'Pristine', 'Major', 'Common', 'Low', 'Depleted'):
            for flagged in (False, True):
                body = v4_body(v4_class, **{flag: flagged for flag in flags})
                for exotic in ('Black Hole', 'Neutron Star', 'White Dwarf (DA) Star'):
                    system = v4_opportunities(body, v4_body(exotic, name='exotic'), reserve=reserve)
                    for opportunity in system.values():
                        fired |= _fired(opportunity, 'boosts') | _fired(opportunity, 'decreases')
    assert fired == mapped, f'unmapped V4 rules: {sorted(fired - mapped)}; never fired: {sorted(mapped - fired)}'
