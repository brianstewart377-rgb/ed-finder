# V3 Finder F2b — system_archetype Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/v3_system_archetype.py` — a generation-scoped, chunked, resumable derived-product builder that computes all 8 archetype fits per system from the published Ratings V4 generation, writes `v3_derived.system_archetype` + `system_archetype_summary`, seals each chunk, and validates coverage/invariants — without ever publishing.

**Architecture:** Mirror the proven `scripts/v3_system_search.py` product lifecycle (`register_product` → `build_available` → `validate_product` → follow loop). The pure fit model lives in a separate, DB-free module (`scripts/v3_system_archetype_model.py`) so it can be unit-tested exhaustively; the builder is the DB/IO shell around it. Coefficients ship as reasoned defaults in versioned config (`archetype_version = v3-archetype-1`); calibration against real V4 is an authorized read-only checkpoint before the governed full build.

**Tech Stack:** CPython 3.14, psycopg 3 (sync), pytest on the disposable PG18 fixture (`docker-compose.localtest.yml`, `127.0.0.1:55434`), migration 011 (already merged, PR #738).

## Global Constraints

- CPython **3.14** exact; Ruff target `py314`. Parameterized SQL only; no f-string SQL values.
- Product code `system_archetype`; `archetype_version = 'v3-archetype-1'` (must equal the value migration 011's `archetype_build_chunk.product_code` CHECK and the summary tables expect).
- Reads only from the pinned V4 generation: `v3_derived.system_rating_vector` and `v3_derived.economy_opportunity`. **No `public.*` reads.**
- The builder **never publishes** — publication is the governed operator op (mirrors F1 `system_search` / Ratings V4). Migration 011 ships as a committed file; its manifest declaration + authority refresh is deferred to the governed migration operation (do NOT add 011 to `sql/v3/migration-manifest.txt`).
- Insert-only: the migration-011 guards reject UPDATE/DELETE/TRUNCATE on all three archetype relations, and INSERT only while the base generation is `BUILDING`/`VALIDATING` and the product is registered. Write once per chunk inside one transaction.
- Economy ordinal → name is fixed: `1=Agriculture, 2=Refinery, 3=Industrial, 4=HighTech, 5=Military, 6=Tourism, 7=Extraction` (`sql/v3/migrations/003_ratings_v4_derived.sql:220`).
- All 8 archetypes emit a row for **every** system (coverage is a hard gate); exactly one `system_archetype_summary` row per system.
- Tier thresholds: `S≥88, A≥76, B≥60, C≥45, else D`. Scores are integers 0–100 (`smallint`), confidence is `double precision` in [0,1].

---

## The 8 archetypes and their anchors

| key | required anchors (ordinals) | supporting (ordinals) |
|---|---|---|
| `paradise` | Agriculture(1), Tourism(6) | — |
| `mining_hub` | Extraction(7), Refinery(2) | — |
| `manufacturing_hub` | Refinery(2), Industrial(3) | — |
| `megacomplex` | Extraction(7), Refinery(2), Industrial(3) | — |
| `research_hub` | HighTech(4) | Industrial(3) |
| `stronghold` | Military(5), Industrial(3) | — |
| `population_capital` | Agriculture(1), HighTech(4) | — |
| `flexible` | — (breadth over all 7) | — |

## Fit model (reasoned defaults — `v3-archetype-1`)

Per system, arrays are 1-indexed by economy ordinal (Python: subtract 1). For an archetype with required anchors `A`:

- **Economy core** (weakest-link): `core = α·min(pot[a] for a in A) + (1-α)·mean(pot[a] for a in A)`, `α = 0.6`. Single-anchor archetype → `core = pot[a]`.
- **Specialisation factor** ∈ [0.85, 1.0]: `spec = 0.85 + 0.15·(mean(qual[a])/100)`. Where `quality[a]` is NULL (bounded `quality_min<quality_max`), use the midpoint `(quality_min[a]+quality_max[a])/2` **and** multiply the archetype confidence by `SPEC_UNKNOWN_CONF = 0.85` (unknown widens uncertainty; it never fabricates a penalty).
- **Capacity factor** ∈ [0.6, 1.0]: `cap = 0.6 + 0.4·min(1, mean_over_A(opp_count[a])/CAPACITY_TARGET)·(mean_over_A(mean_local[a])/100)`, `CAPACITY_TARGET = 8`. Anchors with no `economy_opportunity` rows contribute `opp_count=0, mean_local=0`.
- **Synergy bonus** (bounded): `+SYNERGY_BONUS = 5` iff every required **and** supporting anchor has `pot ≥ SYNERGY_THRESHOLD = 60`; else `0`.
- **Raw score**: `raw = core·spec·cap + synergy_bonus`; `archetype_score = round(clamp(raw, 0, 100))`.
- **Confidence**: `conf = min(confidence[a] for a in A) · (SPEC_UNKNOWN_CONF if any anchor quality was NULL else 1.0)`. `min` is taken over required anchors; low `completeness` does not subtract from the score.
- **`flexible`** (special): `breadth = count(e in 1..7 where pot[e] ≥ BREADTH_POT = 55 and qual_present_or_bounded_mid[e] ≥ BREADTH_QUAL = 40)`; `archetype_score = round(clamp(100·min(1, breadth/BREADTH_TARGET), 0, 100))`, `BREADTH_TARGET = 4`; `conf = mean(confidence[1..7])`.

Per-archetype **explanation** JSONB: `{"anchors": [ordinals], "core": …, "spec": …, "cap": …, "synergy": …, "components": {"pot": {...}, "qual": {...}, "opp_count": {...}}}`.

**Summary** per system: `primary_archetype` = highest `archetype_score` (ties broken by the archetype order above); `secondary_archetype` = next highest (nullable only if all others are 0); `best_colony_potential` = primary's score; `best_tier` = primary's tier; `archetype_confidence = min((s1 − s2)/max(s1, 1)·2, 1)` where `s1,s2` are the top two scores.

---

## Test harness & builder API (AUTHORITATIVE — read before Tasks 2–5)

The DB-backed tests mirror **`tests/ratings_v4_system_search.py`'s sibling
`tests/test_ratings_v4_system_search.py`** exactly — that file already drives a
derived-product builder (`register_product`/`build_available`/`validate_product`)
against a real derived generation, and the archetype product is the same shape.
There is **no** `seed_validating_generation`/`pg_connection` fixture; do not
invent one. Use this real pattern:

```python
from tests.ratings_v4_pg_fixture import canonical_database

@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in ('003_ratings_v4_derived.sql', '006_v3_derived_product_lifecycle.sql',
                     '011_v3_system_archetype.sql'):
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        yield connection, canonical, metadata, payloads
```

- `canonical_database()` needs env `RATINGS_V4_VALIDATION_DATABASE_URL` — the
  disposable PG18 test DB (docker-compose.localtest.yml, `127.0.0.1:55434`,
  db `ratings_v4_validation`). It is prod-isolated; tests skip if unset.
- Build the base derived generation with the ratings helpers, copied verbatim
  from `test_ratings_v4_system_search.py`: `_ratings_generation(database)` uses
  `CanonicalSnapshot.pin`, `create_generation`, `write_chunk`. The source fixture
  produces **12 systems across 3 chunks** (chunk_size 4) — assert those numbers,
  not `systems=N`. `_ready_ratings(database, generation_id)` calls `seal_source`
  + `validate_generation` to move the base generation to READY (required before
  a product's `validate_product` can return `VERIFIED`).

**Real builder signatures (mirror `scripts/v3_system_search.py`):**
- `register_product(connection, generation_key) -> (generation: Generation, state: str, manifest_sha: bytes)` — returns the base **lifecycle state** (`'BUILDING'` etc.), NOT a product version.
- `build_available(connection, generation: Generation, manifest_sha: bytes) -> {'chunks_written': int, ...}` — takes the Generation object + manifest_sha, not a key. Skips chunks with an existing receipt (resumable).
- `validate_product(connection, generation: Generation, manifest_sha: bytes) -> {'status': 'VERIFIED'|'INCOMPLETE'|..., 'base_lifecycle_state': str, ...}` — `INCOMPLETE` while the base generation is still `BUILDING`; `VERIFIED` only after `_ready_ratings`. On `VERIFIED` it promotes the **product** row (`v3_meta.derived_product`) `BUILDING -> READY` and stores the `validation_receipt`/`validation_sha256`/`validated_at`, mirroring `v3_system_search.validate_product` — this product-level promotion is REQUIRED (migration 006's publish gate rejects a generation with any non-`READY`/`VERIFIED` product), and is idempotent when already `READY`. It never touches the **base generation's** lifecycle and never calls `publish_derived_generation` (publishing is the separate governed op).

Canonical test skeleton (adapt for archetype; mirrors the search build test):

```python
def test_archetype_builds_resumes_and_validates(database):
    connection, canonical, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, state, manifest_sha = register_product(connection, key)
    assert state == 'BUILDING'
    first = build_available(connection, generation, manifest_sha)
    second = build_available(connection, generation, manifest_sha)
    assert first['chunks_written'] == 3 and second['chunks_written'] == 0
    # 12 systems × 8 archetypes archetype rows, 12 summary rows, 3 receipts
    incomplete = validate_product(connection, generation, manifest_sha)
    assert incomplete['status'] == 'INCOMPLETE'
    _ready_ratings(database, generation_id)
    assert validate_product(connection, generation, manifest_sha)['status'] == 'VERIFIED'
```

Copy `_ratings_generation`, `_eof_receipt`, `_ready_ratings` verbatim from
`test_ratings_v4_system_search.py` into the new archetype test module (or import
them). Where Tasks 2–5 below show `seed_validating_generation(...)` or
`validate_product(connection, key)`, that scaffolding is superseded by this
section — use the signatures and fixture here.

---

### Task 1: Pure fit-model module (no DB)

**Files:**
- Create: `scripts/v3_system_archetype_model.py`
- Test: `tests/test_v3_system_archetype_model.py`

**Interfaces:**
- Produces (imported by the builder in Task 2+):
  - `ARCHETYPE_VERSION: str = 'v3-archetype-1'`
  - `ARCHETYPE_KEYS: tuple[str, ...]` — the 8 keys in tie-break order.
  - `SystemVectors` dataclass: `pot: tuple[int,...]` (len 7), `qual: tuple[int|None,...]`, `qual_min: tuple[int,...]`, `qual_max: tuple[int,...]`, `completeness: tuple[float,...]`, `confidence: tuple[float,...]`, `opp: dict[int, tuple[int, float]]` (ordinal → (opp_count, mean_local)).
  - `ArchetypeFit` dataclass: `key: str`, `score: int`, `tier: str`, `confidence: float`, `explanation: dict`.
  - `fit_all(v: SystemVectors) -> list[ArchetypeFit]` — one per key, in `ARCHETYPE_KEYS` order.
  - `summarise(fits: list[ArchetypeFit]) -> dict` with keys `primary_archetype, secondary_archetype, best_colony_potential, best_tier, archetype_confidence`.
  - `tier_of(score: int) -> str`.

- [ ] **Step 1: Write the failing test for tier thresholds and a clean two-anchor fit**

```python
# tests/test_v3_system_archetype_model.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_model.py -q`
Expected: FAIL — `ModuleNotFoundError: scripts.v3_system_archetype_model`.

- [ ] **Step 3: Implement the model module**

```python
# scripts/v3_system_archetype_model.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_model.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Add edge-case tests (NULL quality, summary tie-break, flexible breadth)**

```python
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
```

- [ ] **Step 6: Run and commit**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_model.py -q`
Expected: PASS (7 tests).

```bash
git add scripts/v3_system_archetype_model.py tests/test_v3_system_archetype_model.py
git commit -m "feat(finder): F2b pure archetype fit model (v3-archetype-1)"
```

---

### Task 2: Builder scaffolding — Generation, manifest, code_identity, register_product, CLI

**Files:**
- Create: `scripts/v3_system_archetype.py`
- Test: `tests/test_v3_system_archetype_register.py`

**Interfaces:**
- Consumes: `scripts/v3_system_archetype_model.ARCHETYPE_VERSION`.
- Produces (used by Tasks 3–5): `PRODUCT_CODE='system_archetype'`, `PRODUCT_VERSION=ARCHETYPE_VERSION`, `Generation` dataclass (same fields as `v3_system_search.Generation`), `code_identity(root)->dict`, `product_manifest(generation)->dict`, `register_product(connection, generation_key)->tuple[Generation, str, bytes]` (returns `(generation, product_version, manifest_sha)`), `_json`, `_digest`, `main(argv)->int`.

The scaffolding is a direct structural copy of `scripts/v3_system_search.py` lines 1–193 with these substitutions: `PRODUCT_CODE='system_archetype'`; `PRODUCT_VERSION = ARCHETYPE_VERSION`; `code_identity()` hashes `('scripts/v3_system_archetype.py', 'scripts/v3_system_archetype_model.py', 'sql/v3/migrations/011_v3_system_archetype.sql')`; `product_manifest()` records the product code/version, the anchor config, and the coefficient constants (so a coefficient change re-versions the manifest and is caught by `register_product`'s manifest-equality check).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_system_archetype_register.py
import scripts.v3_system_archetype as builder
from tests.v3_derived_fixture import seed_validating_generation  # existing helper used by search tests

def test_register_is_idempotent_and_pins_manifest(pg_connection):
    key = seed_validating_generation(pg_connection, systems=3)
    gen1, version1, sha1 = builder.register_product(pg_connection, key)
    gen2, version2, sha2 = builder.register_product(pg_connection, key)  # second call: no-op
    assert version1 == builder.PRODUCT_VERSION == 'v3-archetype-1'
    assert sha1 == sha2 and gen1.identifier == gen2.identifier

def test_manifest_includes_coefficients(pg_connection):
    key = seed_validating_generation(pg_connection, systems=1)
    gen, _, _ = builder.register_product(pg_connection, key)
    manifest = builder.product_manifest(gen)
    assert manifest['product_version'] == 'v3-archetype-1'
    assert manifest['coefficients']['alpha'] == 0.6
```

> **Note:** `seed_validating_generation` / the `pg_connection` fixture: reuse the exact fixture module the `system_search` builder tests use. Before Step 2, locate it with `grep -rl "def seed_validating_generation\|def pg_connection" tests/`. If the search-product tests seed via a different helper name, adapt the import to that helper — do not invent a new fixture.

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_register.py -q`
Expected: FAIL — module/attribute missing.

- [ ] **Step 3: Implement scaffolding**

Copy the structure of `scripts/v3_system_search.py:1-193` (`imports`, `Generation`, `_json`, `_digest`, `code_identity`, `_generation`, `_product`, `product_manifest`, `register_product`) into `scripts/v3_system_archetype.py`, applying the substitutions above. `product_manifest` must include a `coefficients` block copied from the model module (`alpha`, `spec_floor/span`, `cap_floor/span/target`, `synergy_bonus/threshold`, `spec_unknown_conf`, `breadth_*`) and an `anchors` block, so any coefficient edit changes `manifest_sha` and is rejected by `register_product` unless the version is bumped.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_register.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_system_archetype.py tests/test_v3_system_archetype_register.py
git commit -m "feat(finder): F2b builder scaffolding + register_product"
```

---

### Task 3: `build_available` — read, compute, write, seal per chunk

**Files:**
- Modify: `scripts/v3_system_archetype.py`
- Test: `tests/test_v3_system_archetype_build.py`

**Interfaces:**
- Consumes: `register_product` (Task 2), `fit_all`/`summarise` (Task 1), the migration-011 relations.
- Produces: `build_available(connection, generation_key, *, progress=None, max_chunks=None)->dict` returning `{'chunks_written': int, 'systems_written': int}`. Helpers: `_ratings_chunks_missing_archetype(connection, gen_id)`, `_read_chunk_vectors(connection, gen_id, ordinal)->dict[int, SystemVectors]`, `_source_projection_sha(...)`, `_chunk_content_sha(connection, gen_id, ordinal)`.

Read plan per chunk:
1. `system_rating_vector` for the chunk → per-system arrays (`potential`, `quality`, `quality_min`, `quality_max`, `completeness`, `confidence`); divide `completeness`/`confidence` by 10000.0 to reach [0,1].
2. `economy_opportunity` aggregated per `(system_id64, economy_ordinal)` scoped to the chunk via a join on `system_rating_vector.chunk_ordinal` → `{ordinal: (opp_count, mean_local)}`.
3. For each system, build `SystemVectors`, call `fit_all` + `summarise`, collect rows.
4. In one transaction: insert 8 `system_archetype` rows/system + 1 `system_archetype_summary` row/system + one `archetype_build_chunk` receipt with `source_projection_sha256` and `content_sha256`.

Skip chunks that already have an `archetype_build_chunk` receipt (resumability).

- [ ] **Step 1: Write the failing test — a built chunk produces 8 rows/system + a summary + a receipt**

```python
# tests/test_v3_system_archetype_build.py
import scripts.v3_system_archetype as builder
from scripts.v3_system_archetype_model import ARCHETYPE_KEYS
from tests.v3_derived_fixture import seed_validating_generation

def test_build_writes_all_rows_and_receipt(pg_connection):
    key = seed_validating_generation(pg_connection, systems=5)  # 1 chunk
    builder.register_product(pg_connection, key)
    result = builder.build_available(pg_connection, key)
    assert result['chunks_written'] == 1
    assert result['systems_written'] == 5
    (arch,) = pg_connection.execute(
        "SELECT count(*) FROM v3_derived.system_archetype").fetchone()
    assert arch == 5 * len(ARCHETYPE_KEYS)
    (summ,) = pg_connection.execute(
        "SELECT count(*) FROM v3_derived.system_archetype_summary").fetchone()
    assert summ == 5
    (rec,) = pg_connection.execute(
        "SELECT count(*) FROM v3_derived.archetype_build_chunk").fetchone()
    assert rec == 1

def test_build_is_resumable_and_deterministic(pg_connection):
    key = seed_validating_generation(pg_connection, systems=5)
    builder.register_product(pg_connection, key)
    builder.build_available(pg_connection, key)
    shas_1 = [bytes(r[0]) for r in pg_connection.execute(
        "SELECT content_sha256 FROM v3_derived.archetype_build_chunk ORDER BY chunk_ordinal").fetchall()]
    again = builder.build_available(pg_connection, key)  # nothing left to do
    assert again['chunks_written'] == 0
    # Re-derive on a fresh generation of identical inputs -> identical content shas.
    key2 = seed_validating_generation(pg_connection, systems=5, seed=key)
    builder.register_product(pg_connection, key2)
    builder.build_available(pg_connection, key2)
    shas_2 = [bytes(r[0]) for r in pg_connection.execute(
        "SELECT content_sha256 FROM v3_derived.archetype_build_chunk "
        "WHERE derived_generation_id=(SELECT derived_generation_id FROM v3_meta.derived_generation WHERE generation_key=%s) "
        "ORDER BY chunk_ordinal", (key2,)).fetchall()]
    assert shas_1 == shas_2
```

> **Note:** if the fixture cannot seed two input-identical generations, drop `test_build_is_resumable_and_deterministic`'s second half and instead assert determinism by re-reading the same generation's `content_sha256` against a recomputed digest via `_chunk_content_sha`. Keep the resumability assertion (`chunks_written == 0` on second run) regardless.

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_build.py -q`
Expected: FAIL — `build_available` not defined.

- [ ] **Step 3: Implement `build_available` and helpers**

Model the reads and chunk sealing on `scripts/v3_system_search.py:196-512` (`_source_projection_sha`, `_rating_chunks`, `_chunk_content_sha`, `build_available`). The per-system compute replaces the search projection. Key read SQL:

```python
def _read_chunk_vectors(connection, gen_id, ordinal):
    rows = connection.execute(
        '''SELECT system_id64, potential, quality, quality_min, quality_max,
                  completeness, confidence
             FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=%s
            ORDER BY system_id64''',
        (gen_id, ordinal),
    ).fetchall()
    opp = connection.execute(
        '''SELECT o.system_id64, o.economy_ordinal,
                  count(*)::int, avg(o.local_score)::double precision
             FROM v3_derived.economy_opportunity o
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=o.derived_generation_id
              AND v.system_id64=o.system_id64
            WHERE o.derived_generation_id=%s AND v.chunk_ordinal=%s
            GROUP BY o.system_id64, o.economy_ordinal''',
        (gen_id, ordinal),
    ).fetchall()
    opp_by_system = {}
    for sid, ordn, cnt, mean_local in opp:
        opp_by_system.setdefault(sid, {})[ordn] = (cnt, float(mean_local or 0.0))
    from scripts.v3_system_archetype_model import SystemVectors
    vectors = {}
    for sid, pot, qual, qmin, qmax, comp, conf in rows:
        vectors[sid] = SystemVectors(
            pot=tuple(pot), qual=tuple(qual),
            qual_min=tuple(qmin), qual_max=tuple(qmax),
            completeness=tuple(c / 10000.0 for c in comp),
            confidence=tuple(c / 10000.0 for c in conf),
            opp=opp_by_system.get(sid, {}),
        )
    return vectors
```

The write inserts, per chunk, in one transaction: `system_archetype` (8 rows/system, `explanation` via `_json(...)::jsonb`), `system_archetype_summary` (1/system), then the `archetype_build_chunk` receipt. `content_sha256 = _digest(<ordered list of (system_id64, [(key,score,tier,round(conf,6)) for each fit], summary)>)` — a stable, sorted structure so the digest is reproducible. `source_projection_sha256` mirrors `v3_system_search._source_projection_sha` (product code/version, generation ids, ordinal, manifest sha, the chunk's `canonical_input_sha256` and ratings `content_sha256` from `build_chunk`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_build.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_system_archetype.py tests/test_v3_system_archetype_build.py
git commit -m "feat(finder): F2b build_available — compute+seal archetype chunks"
```

---

### Task 4: `validate_product` — coverage + invariants (hard gates)

**Files:**
- Modify: `scripts/v3_system_archetype.py`
- Test: `tests/test_v3_system_archetype_validate.py`

**Interfaces:**
- Consumes: `build_available` (Task 3).
- Produces: `validate_product(connection, generation, manifest_sha)->dict` returning a receipt `{'status': 'VERIFIED'|'INCOMPLETE'|'FAILED', 'base_lifecycle_state': str, 'systems': int, 'archetype_rows': int, 'every_system_has_all_archetypes': bool, 'invariants_ok': bool, 'summary_matches_max': bool, 'reasons': list[str], ...}`. On `VERIFIED`, `validate_product` promotes the **product** row `BUILDING -> READY` + stores the receipt (mirrors `v3_system_search.validate_product`; REQUIRED so migration 006's publish gate can later accept the generation) — idempotent when already `READY`, leaves the product `BUILDING` on `INCOMPLETE`/`FAILED`, never touches the base-generation lifecycle, and never publishes. (Correction: an earlier draft said "does not change lifecycle" — that conflated product-`READY` promotion with publishing; the product promotion is required and is not publishing.)

Hard gates:
1. Every system in `system_rating_vector` has exactly `len(ARCHETYPE_KEYS)` `system_archetype` rows and exactly one `system_archetype_summary` row.
2. All `archetype_score ∈ [0,100]`, `tier` consistent with `tier_of(score)`.
3. Each summary's `best_colony_potential`/`best_tier`/`primary_archetype` equals the max archetype row for that system.
4. No `public.*` reference anywhere in the read path (assert by static check: the module source contains no `public.` string).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_system_archetype_validate.py
import scripts.v3_system_archetype as builder
from tests.v3_derived_fixture import seed_validating_generation

def test_validate_passes_after_full_build(pg_connection):
    key = seed_validating_generation(pg_connection, systems=7)
    builder.register_product(pg_connection, key)
    builder.build_available(pg_connection, key)
    receipt = builder.validate_product(pg_connection, key)
    assert receipt['status'] == 'VERIFIED'
    assert receipt['every_system_has_all_archetypes'] is True
    assert receipt['summary_matches_max'] is True

def test_validate_fails_on_incomplete_coverage(pg_connection):
    key = seed_validating_generation(pg_connection, systems=7)
    builder.register_product(pg_connection, key)
    builder.build_available(pg_connection, key, max_chunks=0)  # build nothing
    receipt = builder.validate_product(pg_connection, key)
    assert receipt['status'] == 'FAILED'
    assert any('coverage' in r for r in receipt['reasons'])

def test_module_never_reads_public_schema():
    from pathlib import Path
    src = Path('scripts/v3_system_archetype.py').read_text()
    assert 'public.' not in src
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_validate.py -q`
Expected: FAIL — `validate_product` not defined.

- [ ] **Step 3: Implement `validate_product`**

Model on `scripts/v3_system_search.py:540-716` (`validate_product`). Use set-based SQL for the gates (a `GROUP BY system_id64 HAVING count(*) <> :n` coverage probe; a summary-vs-max join). Assemble the receipt dict; return `FAILED` with reasons rather than raising, so the operator sees all gate failures at once.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_validate.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/v3_system_archetype.py tests/test_v3_system_archetype_validate.py
git commit -m "feat(finder): F2b validate_product — coverage+invariant gates"
```

---

### Task 5: CLI + follow loop + code-identity/manifest test

**Files:**
- Modify: `scripts/v3_system_archetype.py`
- Test: `tests/test_v3_system_archetype_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv=None)->int` with argparse mirroring `v3_system_search.py:716-750`: `--generation-key` (required), `--follow`, `--poll-seconds` (default 5.0), `--max-chunks`, and a `--validate` mode that runs `validate_product` and prints the receipt JSON. The follow loop calls `register_product` then `build_available` in a poll loop until no committed ratings chunk lacks an archetype receipt.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_system_archetype_cli.py
import json
import scripts.v3_system_archetype as builder
from tests.v3_derived_fixture import seed_validating_generation, dsn_for

def test_cli_build_then_validate(pg_connection, capsys):
    key = seed_validating_generation(pg_connection, systems=4)
    assert builder.main(['--generation-key', key, '--dsn', dsn_for()]) == 0
    assert builder.main(['--generation-key', key, '--dsn', dsn_for(), '--validate']) == 0
    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt['status'] == 'VERIFIED'

def test_code_identity_lists_model_and_migration():
    ident = builder.code_identity()
    assert 'scripts/v3_system_archetype_model.py' in ident
    assert 'sql/v3/migrations/011_v3_system_archetype.sql' in ident
```

> **Note:** `--dsn` / `dsn_for()`: check how `v3_system_search.py:main` obtains its connection (env var vs `--dsn`). Match that exact convention — if it reads `V3_DSN`/`DATABASE_URL` from the environment rather than a flag, drop `--dsn` from the test and set the env var in the fixture instead.

- [ ] **Step 2: Run to verify it fails**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_cli.py -q`
Expected: FAIL — `main` not defined / wrong signature.

- [ ] **Step 3: Implement `main` + follow loop**

Copy `v3_system_search.py:716-750` argparse/`main` structure; add the `--validate` branch. Connection acquisition must match the search builder exactly.

- [ ] **Step 4: Run full F2b suite**

Run: `cd /c/Users/brian/ed-finder && python -m pytest tests/test_v3_system_archetype_model.py tests/test_v3_system_archetype_register.py tests/test_v3_system_archetype_build.py tests/test_v3_system_archetype_validate.py tests/test_v3_system_archetype_cli.py -q`
Expected: PASS (all).

- [ ] **Step 5: Lint + commit**

Run: `cd /c/Users/brian/ed-finder && ruff check scripts/v3_system_archetype.py scripts/v3_system_archetype_model.py`
Expected: no findings.

```bash
git add scripts/v3_system_archetype.py tests/test_v3_system_archetype_cli.py
git commit -m "feat(finder): F2b CLI, follow loop, code-identity test"
```

---

### Task 6: Calibration checkpoint against real V4 (authorized read-only prod)

**Files:**
- Create: `scripts/v3_archetype_calibration_probe.py` (read-only diagnostic; not part of the governed build)
- Create: `docs/development/v3-finder-f2b-calibration-notes.md`

**Interfaces:**
- Consumes: `fit_all`/`summarise` (Task 1). Reads `system_rating_vector` + `economy_opportunity` for a **bounded sample** (e.g. `LIMIT`-ed chunk ordinals) of the published prod generation.

> **Authorization:** the user explicitly authorized read-only production reads for this work (2026-09-24). This probe is read-only and must use the current V3 read-only connection path; it performs **no** writes and **no** lifecycle changes. It is a diagnostic, not the governed build.

- [ ] **Step 1: Write the probe (bounded, read-only)**

The probe pulls a bounded sample of systems, runs `fit_all`, and reports: per-archetype score distribution (min/median/p90/max), how many systems have each archetype as `primary`, and the overlap between `mining_hub`/`manufacturing_hub`/`megacomplex` primaries (the spec's "do these separate distinct systems?" question). Enforce a hard `LIMIT` and read-only transaction.

- [ ] **Step 2: Run against the published generation (sample)**

Run the probe against the published prod generation over a bounded sample. Record the distributions and the Mining/Manufacturing/Megacomplex separation in the notes doc.

- [ ] **Step 3: Decide coefficient adjustments (or confirm defaults)**

If the sample shows the anchor chain does not separate (e.g. one archetype dominates or `megacomplex` never wins where all three anchors are strong), adjust the versioned coefficients — **and bump `ARCHETYPE_VERSION`** so the manifest/receipt identity changes. If defaults hold, record "v3-archetype-1 confirmed against prod sample" with the evidence.

- [ ] **Step 4: Commit the probe + notes**

```bash
git add scripts/v3_archetype_calibration_probe.py docs/development/v3-finder-f2b-calibration-notes.md
git commit -m "feat(finder): F2b calibration probe + prod-sample notes"
```

---

## Out of scope (later)

- **The governed production build/publish** of `system_archetype` (register → build_available → validate_product → publish through the 006 gate) — an operator op, gated on migration 011's manifest declaration + authority refresh, like F1/V4.
- **F2c** — the ranking profile definition (`ranking_version`) and the full divergence report vs retained V2 archetype outputs.
- **F3/F4** — the Finder API pointed at these projections, and the `apps/web` archetype picker UI.

## Self-Review

- **Spec coverage:** fit model (Task 1) covers §"Fit model" incl. weakest-link, specialisation, synergy, capacity, gating, flexible breadth, tiers, Best Colony Potential, archetype_confidence. Builder (Tasks 2–5) covers §"Builder" (register/build/validate/never-publish) and §"Validation & parity" coverage+invariant gates. Calibration (Task 6) covers §"Open items" #1 and the archetype-separation validation, now unblocked by the prod-read authorization. F2c items (ranking profile, divergence report) are explicitly out of scope, matching the spec's F2b/F2c split.
- **Placeholder scan:** every code step has concrete code; fixture-helper names are flagged with a `grep` to confirm the exact existing name rather than guessed (the search-product tests already establish this fixture — reuse it).
- **Type consistency:** `SystemVectors`/`ArchetypeFit`/`fit_all`/`summarise`/`tier_of`/`ARCHETYPE_KEYS`/`ARCHETYPE_VERSION` are defined in Task 1 and consumed unchanged in Tasks 2–6; `register_product`/`build_available`/`validate_product`/`main` signatures are fixed in their defining tasks and reused verbatim.
