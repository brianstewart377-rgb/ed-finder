'''Pure, DB-free V3 archetype fit model (v3-archetype-1).

Economy ordinals: 1=Agriculture 2=Refinery 3=Industrial 4=HighTech
5=Military 6=Tourism 7=Extraction.
'''
from __future__ import annotations

from dataclasses import dataclass, field

ARCHETYPE_VERSION = 'v3-archetype-1'

# key -> (required anchor ordinals, supporting ordinals)
_ANCHORS: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    'paradise': ((1, 6), ()),
    'mining_hub': ((7, 2), ()),
    'manufacturing_hub': ((2, 3), ()),
    'megacomplex': ((7, 2, 3), ()),
    'research_hub': ((4,), (3,)),
    'stronghold': ((5, 3), ()),
    'population_capital': ((1, 4), ()),
    'flexible': ((), ()),
}
ARCHETYPE_KEYS = tuple(_ANCHORS)

ALPHA = 0.6
SPEC_FLOOR, SPEC_SPAN = 0.85, 0.15
CAP_FLOOR, CAP_SPAN, CAPACITY_TARGET = 0.6, 0.4, 8
SYNERGY_BONUS, SYNERGY_THRESHOLD = 5, 60
SPEC_UNKNOWN_CONF = 0.85
BREADTH_POT, BREADTH_QUAL, BREADTH_TARGET = 55, 40, 4

_TIERS = ((88, 'S'), (76, 'A'), (60, 'B'), (45, 'C'))


@dataclass(frozen=True)
class SystemVectors:
    pot: tuple[int, ...]
    qual: tuple[int | None, ...]
    qual_min: tuple[int, ...]
    qual_max: tuple[int, ...]
    completeness: tuple[float, ...]
    confidence: tuple[float, ...]
    opp: dict[int, tuple[int, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchetypeFit:
    key: str
    score: int
    tier: str
    confidence: float
    explanation: dict


def tier_of(score: int) -> str:
    for threshold, name in _TIERS:
        if score >= threshold:
            return name
    return 'D'


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _quality(v: SystemVectors, ordinal: int) -> tuple[float, bool]:
    '''(quality_value, was_unknown). Bounded-null -> midpoint, unknown=True.'''
    i = ordinal - 1
    q = v.qual[i]
    if q is not None:
        return float(q), False
    return (v.qual_min[i] + v.qual_max[i]) / 2.0, True


def _fit_anchored(v: SystemVectors, key: str) -> ArchetypeFit:
    required, supporting = _ANCHORS[key]
    pots = [v.pot[a - 1] for a in required]
    core = ALPHA * min(pots) + (1 - ALPHA) * (sum(pots) / len(pots))

    qvals, unknown = [], False
    for a in required:
        q, was_unknown = _quality(v, a)
        qvals.append(q)
        unknown = unknown or was_unknown
    spec = SPEC_FLOOR + SPEC_SPAN * (sum(qvals) / len(qvals) / 100.0)

    counts, locals_ = [], []
    for a in required:
        c, ml = v.opp.get(a, (0, 0.0))
        counts.append(c)
        locals_.append(ml)
    mean_count = sum(counts) / len(counts)
    mean_local = sum(locals_) / len(locals_)
    cap = CAP_FLOOR + CAP_SPAN * min(1.0, mean_count / CAPACITY_TARGET) * (mean_local / 100.0)

    synergy_pool = tuple(required) + tuple(supporting)
    synergy = SYNERGY_BONUS if all(v.pot[a - 1] >= SYNERGY_THRESHOLD for a in synergy_pool) else 0

    raw = core * spec * cap + synergy
    score = round(_clamp(raw, 0, 100))
    conf = min(v.confidence[a - 1] for a in required) * (SPEC_UNKNOWN_CONF if unknown else 1.0)

    explanation = {
        'anchors': list(required),
        'supporting': list(supporting),
        'core': round(core, 3), 'spec': round(spec, 4),
        'cap': round(cap, 4), 'synergy': synergy,
        'components': {
            'pot': {a: v.pot[a - 1] for a in synergy_pool},
            'qual': {a: v.qual[a - 1] for a in required},
            'opp_count': {a: v.opp.get(a, (0, 0.0))[0] for a in required},
        },
    }
    return ArchetypeFit(key, score, tier_of(score), round(conf, 6), explanation)


def _fit_flexible(v: SystemVectors) -> ArchetypeFit:
    breadth = 0
    for ordinal in range(1, 8):
        q, _ = _quality(v, ordinal)
        if v.pot[ordinal - 1] >= BREADTH_POT and q >= BREADTH_QUAL:
            breadth += 1
    score = round(_clamp(100.0 * min(1.0, breadth / BREADTH_TARGET), 0, 100))
    conf = sum(v.confidence) / len(v.confidence)
    explanation = {'anchors': [], 'breadth': breadth, 'breadth_target': BREADTH_TARGET}
    return ArchetypeFit('flexible', score, tier_of(score), round(conf, 6), explanation)


def fit_all(v: SystemVectors) -> list[ArchetypeFit]:
    return [
        _fit_flexible(v) if key == 'flexible' else _fit_anchored(v, key)
        for key in ARCHETYPE_KEYS
    ]


def summarise(fits: list[ArchetypeFit]) -> dict:
    ordered = sorted(
        fits, key=lambda f: (-f.score, ARCHETYPE_KEYS.index(f.key))
    )
    first, second = ordered[0], ordered[1]
    s1, s2 = first.score, second.score
    archetype_confidence = min((s1 - s2) / max(s1, 1) * 2, 1.0)
    return {
        'primary_archetype': first.key,
        'secondary_archetype': second.key if s2 > 0 else None,
        'best_colony_potential': s1,
        'best_tier': first.tier,
        'archetype_confidence': round(archetype_confidence, 6),
    }
