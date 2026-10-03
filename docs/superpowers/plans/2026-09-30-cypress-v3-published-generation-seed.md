# Cypress V3 Published-Generation Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the F3-repointed `POST /api/local/search` and `GET /api/archetypes/rankings` return `200` in the Cypress product-journey E2E (and Review Lab) by publishing a *real* V3 derived generation into the Cypress database through the genuine build→validate→publish pipeline — no hand-faked lifecycle rows — so PR #777's endpoint cutover is verified end-to-end in a browser.

**Architecture:** After F3, only search + archetype-rankings read the V3 `v3_app.*` projections; autocomplete (`local_search.py:1535`) and system detail (`systems.py:76`) still read legacy `public.systems`. This mirrors production, where legacy tables and V3 projections coexist and must share id64s. We therefore *keep* the legacy Cypress seed and *add* a published V3 generation beside it, built by reusing the exact pipeline functions the unit tests use (`scripts/ratings_v4/production_generation.py`, `scripts/v3_system_search.py`, `scripts/v3_system_archetype.py`, `v3_meta.publish_derived_generation`). The V3 dataset is sourced from a committed, checksum-locked canonical fixture curated to contain the journey's exact id64s (Achenar `10477373803000` with a Primary-star body; "V3 Lossless Reach" `9007199254740993`). A CI invariant fails loudly if legacy and V3 ever drift on those id64s.

**Tech Stack:** CPython 3.14 + uv 0.11.33 (frozen `apps/api/pyproject.toml`), Psycopg 3 (sync seed path) + asyncpg (API), PostgreSQL 18, PostgreSQL lifecycle triggers in `sql/v3/migrations/`, Cypress (chrome+firefox) via `.github/workflows/cypress-parity.yml`.

## Global Constraints

- Python runtime is exact CPython 3.14; seed code runs under `apps/api/.venv/bin/python`, same interpreter the workflow already uses (`cypress-parity.yml:66` asserts it).
- Sync PostgreSQL access uses pinned Psycopg 3 (importer/tooling lane), NOT asyncpg, for the seed path — matches `tests/ratings_v4_pg_fixture.py`.
- Parameterized SQL only; no string interpolation of values (CLAUDE.md).
- The seed writes ONLY to the disposable Cypress `edfinder` database (`postgresql://edfinder:edfinder@localhost:5432/edfinder`). Never a production DSN (CLAUDE.md: DB tests on disposable/test databases).
- No lifecycle shortcuts: the published generation and both products MUST reach `PUBLISHED`/`VERIFIED` through `v3_meta.publish_derived_generation`, whose contract (`006:245-267`) requires genuine `validation_receipt->>'status'='VERIFIED'` on the generation and every registered `derived_product`. Hand-inserted final-state rows are forbidden by this plan.
- The canonical fixture is checksum-locked: any fixture bytes must have a matching SHA-256 in its `manifest.json` (`load_source_fixture`, `ratings_v4_canonical.py:361-378`). The existing `tests/fixtures/ratings_v4_sources/` fixture is used by the Ratings V4 validation tests and MUST NOT be mutated — a separate Cypress fixture directory is created.
- Do not weaken the E2E to make it green (CLAUDE.md). The endpoint must genuinely return real data.
- Journey-critical id64s are contract: Achenar `10477373803000` (with a body whose display is "Primary star"), "V3 Lossless Reach" `9007199254740993` (id64 > 2^53, the lossless big-int case). These already exist in the legacy seed (`sql/seed_preview.sql` + `cypress-parity.yml:78-88`) and MUST also appear in the published `v3_app.system_search`.

---

## Design decisions (read before implementing)

**D1 — Real pipeline, not SQL fixture.** The lifecycle triggers (`003:41-71` immutable manifest + transition guard; `006:32-107` product guard requiring INSERT-as-`BUILDING`) make hand-crafted final-state rows both fragile and a direct violation of the safety contract this subsystem exists to enforce. We drive the same functions the tests use. Confirmed feasible: `tests/test_local_search_v3.py:_build_published_generation` already does exactly this in ~30 lines.

**D2 — Keep legacy seed; add V3 beside it.** Autocomplete + detail stay legacy post-F3 (`local_search.py:1535`, `systems.py:76`). Replacing the legacy seed is unnecessary and would break map/regions/nebula/account journeys. We add one V3 seed step.

**D3 — Curate a Cypress canonical fixture containing the journey id64s.** Reusing the existing 12-system fixture fails: its "Achenar" is not id64 `10477373803000`, and `9007199254740993` is in neither dataset. Rather than change the browser test's hardcoded ids (which would also require re-aligning the legacy seed and risks the lossless-id contract), we curate a dedicated fixture whose canonical `systems`/`bodies` carry the exact journey id64s. The fixture is produced by a committed generator script so it is reproducible on schema changes, and its checksums are committed in a `manifest.json`.

**D4 — DRY the bootstrap.** `tests/ratings_v4_pg_fixture.py:canonical_database` bootstraps the `v3_gen_*` canonical generation but CREATE/DROPs its own disposable DB — unusable for seeding the live Cypress DB. Extract the *bootstrap-into-an-existing-connection* logic into a shared, importable module used by BOTH the test fixture and the Cypress seed, so there is one canonical-bootstrap code path.

**D5 — Fail loudly on drift.** A CI invariant asserts every journey-critical id64 exists in BOTH legacy `systems` AND published `v3_app.system_search` with matching name — so future seed edits can't silently desync the two datasets.

**D6 — Production rollout gate (separate from this plan, but MUST be recorded).** This same dependency exists in prod: the F3 cutover must not be *promoted* until the `system_search` + `system_archetype` products are built and published against the live `ratings_v4_prod_p4_parallel_v1` generation. This plan closes the CI gap; Task 7 records the prod gate so the merge of #777 does not imply a safe promotion.

---

## File structure

- Create `scripts/dev/v3_canonical_bootstrap.py` — shared canonical-generation bootstrap into an existing psycopg connection (extracted from `canonical_database`). One responsibility: given a connection + a loaded fixture, create+finalize+publish the `v3_gen_*` canonical generation.
- Create `scripts/dev/build_cypress_v3_fixture.py` — generator that emits the curated Cypress canonical fixture (canonical.json, source-metadata.json, spansh-system-dumps.zip, manifest.json) containing the journey id64s. Run once locally; its output is committed.
- Create `tests/fixtures/cypress_v3_sources/` — committed, checksum-locked curated fixture (output of the generator). Read-only in CI.
- Create `scripts/dev/seed_cypress_v3_generation.py` — CLI seed: connect to `$DATABASE_URL`, load the Cypress fixture, bootstrap canonical (via `v3_canonical_bootstrap`), run the Ratings V4 derived generation + both products + publish (reusing existing pipeline fns), assert `/api/local/search`-shaped read returns the journey id64s.
- Create `scripts/checks/assert_legacy_v3_consistency.py` — CI invariant (D5).
- Modify `tests/ratings_v4_pg_fixture.py` — call the extracted bootstrap so tests and seed share one path (DRY; no behaviour change).
- Modify `.github/workflows/cypress-parity.yml` — add "Seed V3 published generation" + "Assert legacy/V3 consistency" steps after the ratings top-up, before Boot API.
- Modify `docs/operations/v3-production-application-release.md` — record the D6 prod gate.
- Test `tests/test_seed_cypress_v3_generation.py` — verifies the seed publishes a generation and the journey id64s are query-visible through `local_search.local_db_search_v3`.

**Reused pipeline signatures (verbatim, from `tests/test_local_search_v3.py:31-40, 61-116`):**
- `scripts.ratings_v4.production_generation`: `create_generation(connection, snapshot, key) -> generation_id`; `write_chunk(connection, generation_id, ordinal, canonical, metadata, chunk) -> bool`; `seal_source(connection, generation_id, eof_receipt)`; `validate_generation(connection, generation_id) -> receipt(dict, receipt['status']=='VERIFIED')`.
- `scripts.ratings_v4.canonical_stream.CanonicalSnapshot`: `.pin(connection) -> snapshot`; `.export_chunk(connection, [id64,...]) -> canonical(dict)`; attrs `.generation_id`, `.publication_sequence`, `.metadata`.
- `scripts.v3_system_search`: `register_product(connection, key) -> (search_generation, _, search_manifest_sha)`; `build_available(connection, search_generation, search_manifest_sha)`; `validate_product(connection, search_generation, search_manifest_sha) -> {'status':'VERIFIED'}`.
- `scripts.v3_system_archetype` (imported as `archetype_builder`): `register_product`, `build_available`, `validate_product` — same shapes.
- `v3_meta.publish_derived_generation(target, expected_current, expected_sequence, expected_canonical, expected_canonical_sequence, actor, reason) -> bigint` (SQL fn; call via `connection.execute(...).fetchone()[0]`, returns new sequence `1` on first publish).

---

### Task 1: Extract the canonical bootstrap into a shared module (DRY, no behaviour change)

**Files:**
- Create: `scripts/dev/v3_canonical_bootstrap.py`
- Modify: `tests/ratings_v4_pg_fixture.py:11-74`
- Test: `tests/test_v3_canonical_bootstrap.py`

**Interfaces:**
- Produces: `bootstrap_published_canonical(connection, canonical: dict, metadata: dict, *, additional_sources: tuple = ()) -> uuid` — runs the exact INSERT/`create_canonical_generation_relations`/`finalize_canonical_generation`/`publish_canonical_generation` sequence currently inline in `canonical_database` (`ratings_v4_pg_fixture.py:34-73`), against an already-connected, already-migrated psycopg `connection`. Returns the canonical `generation_id`. Does NOT create or drop databases and does NOT apply migrations.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_canonical_bootstrap.py
import os
from pathlib import Path
from uuid import uuid4
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_bootstrap_publishes_canonical_generation():
    import psycopg
    from psycopg.conninfo import make_conninfo
    from domain.ratings_v4_canonical import load_source_fixture
    from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical

    dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    db = 'boot_test_' + uuid4().hex
    canonical, metadata, _ = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{db}"')
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                gen = bootstrap_published_canonical(conn, canonical, metadata)
                row = conn.execute(
                    "SELECT lifecycle_state FROM v3_meta.canonical_generation WHERE generation_id=%s",
                    (gen,)).fetchone()
                assert row[0] == 'PUBLISHED'
        finally:
            admin.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `apps/api/.venv/bin/python -m pytest tests/test_v3_canonical_bootstrap.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.dev.v3_canonical_bootstrap`.

- [ ] **Step 3: Implement the module by lifting the inline logic**

Move the body of `canonical_database`'s transaction block (`ratings_v4_pg_fixture.py:36-73` — the `insert` helper, `v3_source.*` inserts, `canonical_generation` insert, `create_canonical_generation_relations`, generation-input inserts, vocab + systems + bodies + extras inserts, `finalize_canonical_generation`, `publish_canonical_generation`) into:

```python
# scripts/dev/v3_canonical_bootstrap.py
"""Bootstrap a published v3_gen_* canonical generation into an existing,
already-migrated psycopg connection. Extracted verbatim from
tests/ratings_v4_pg_fixture.canonical_database so tests and the Cypress seed
share one canonical-bootstrap path."""
from __future__ import annotations
import json
from uuid import uuid4, UUID
from psycopg import sql


def bootstrap_published_canonical(connection, canonical: dict, metadata: dict,
                                  *, additional_sources: tuple = ()) -> UUID:
    sources = [metadata, *additional_sources]

    def insert(schema, table, rows):
        relation = sql.Identifier(schema, table)
        for row in rows:
            connection.execute(sql.SQL(
                'INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{}, %s::jsonb)'
            ).format(relation, relation), (json.dumps(row),))

    with connection.transaction():
        insert('v3_source', 'source', [metadata['source']])
        connection.execute('''INSERT INTO v3_source.source_rights_policy(
            rights_policy_id,source_id,policy_version,rights_class,retention_class,effective_at)
            VALUES (1,40,'test-fixture','CANONICAL_ELIGIBLE','TEST_ONLY',now())''')
        insert('v3_source', 'source_artifact', [item['artifact'] for item in sources])
        insert('v3_source', 'source_run', [item['run'] for item in sources])
        generation = uuid4()
        schema = canonical['canonical_schema']
        connection.execute('''INSERT INTO v3_meta.canonical_generation(
            generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id)
            VALUES (%s,%s,%s,%s,%s)''',
            (generation, schema.removeprefix('v3_gen_'), schema, bytes(32),
             metadata['run']['source_run_id']))
        connection.execute('SELECT v3_meta.create_canonical_generation_relations(%s)', (generation,))
        for ordinal, item in enumerate(sources):
            connection.execute('''INSERT INTO v3_meta.canonical_generation_input(
                generation_id,input_ordinal,source_id,source_run_id,artifact_id,input_role)
                VALUES (%s,%s,40,%s,%s,'TEST_FIXTURE')''',
                (generation, ordinal, item['run']['source_run_id'], item['artifact']['artifact_id']))
        for extra in canonical['extras']:
            if extra['schema'] == 'v3_vocab':
                insert('v3_vocab', extra['relation'], extra['rows'])
        insert(schema, 'systems', canonical['systems'])
        insert(schema, 'bodies', canonical['bodies'])
        for extra in canonical['extras']:
            if extra['schema'] == schema:
                insert(schema, extra['relation'], extra['rows'])
        receipt = {'systems': len(canonical['systems']), 'bodies': len(canonical['bodies'])}
        connection.execute('SELECT v3_meta.finalize_canonical_generation(%s,%s::jsonb)',
                           (generation, json.dumps(receipt)))
        connection.execute('SELECT v3_meta.publish_canonical_generation(%s,%s,%s)',
                           (generation, 'disposable-test', 'fixture'))
    return generation
```

- [ ] **Step 4: Refactor `canonical_database` to call the shared fn**

In `tests/ratings_v4_pg_fixture.py`, replace the inline transaction block (lines 42-73) with:

```python
                from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical
                bootstrap_published_canonical(connection, canonical, metadata,
                                              additional_sources=additional_sources)
                yield connection, canonical, metadata, payloads
```

Keep the `additional_sources = prepare(...) if prepare else ()` line and the DB create/drop as-is.

- [ ] **Step 5: Run the new test AND the existing ratings_v4 tests to prove no regression**

Run: `apps/api/.venv/bin/python -m pytest tests/test_v3_canonical_bootstrap.py tests/test_local_search_v3.py tests/test_ratings_v4_system_search.py -v`
Expected: PASS (or SKIP where `RATINGS_V4_VALIDATION_DATABASE_URL` unset — see reference_local_test_database for the local PG18 service).

- [ ] **Step 6: Commit**

```bash
git add scripts/dev/v3_canonical_bootstrap.py tests/ratings_v4_pg_fixture.py tests/test_v3_canonical_bootstrap.py
git commit -m "refactor(finder): extract shared v3 canonical bootstrap for tests + cypress seed"
```

---

### Task 2: Generate the curated Cypress canonical fixture (journey id64s)

**Files:**
- Create: `scripts/dev/build_cypress_v3_fixture.py`
- Create: `tests/fixtures/cypress_v3_sources/{canonical.json,source-metadata.json,spansh-system-dumps.zip,manifest.json}` (generator output, committed)
- Test: `tests/test_cypress_v3_fixture.py`

**Interfaces:**
- Produces: a fixture directory that `domain.ratings_v4_canonical.load_source_fixture` loads without error, whose `canonical['systems']` contains id64 `10477373803000` (name "Achenar") and `9007199254740993` (name "V3 Lossless Reach"), and whose `canonical['bodies']` includes at least one body for `10477373803000` classifiable as a primary star. At least 3 systems total (journey asserts a 2nd distinct result).
- Consumes: the shape of the existing `tests/fixtures/ratings_v4_sources/canonical.json` as the template (same `canonical_schema`, `extras` vocab rows, body/ring/signal column contract).

- [ ] **Step 1: Study the template fixture shape**

Run: `apps/api/.venv/bin/python - <<'PY'
import json,collections
d=json.load(open('tests/fixtures/ratings_v4_sources/canonical.json'))
print('keys', list(d))
print('schema', d['canonical_schema'])
print('system0 keys', sorted(d['systems'][0]))
print('body0 keys', sorted(d['bodies'][0]))
print('extras', [(e['schema'],e['relation'],len(e['rows'])) for e in d['extras']])
PY`
Expected: prints the column contract you must reproduce (system columns incl. `id64`,`name`,`galaxy_region_id`,coords; body columns incl. `system_id64`,`body_pk`,`source_body_id64`,`frontier_body_id`, type/subType refs; vocab extras: body_type, reserve_type, signal_type, volcanism_type, terraforming_state, atmosphere_classification, galaxy_region).

- [ ] **Step 2: Write the failing test (fixture loads + carries journey ids)**

```python
# tests/test_cypress_v3_fixture.py
from pathlib import Path
from domain.ratings_v4_canonical import load_source_fixture
ROOT = Path(__file__).resolve().parents[1]

def test_cypress_fixture_has_journey_systems():
    canonical, metadata, _ = load_source_fixture(ROOT / 'tests/fixtures/cypress_v3_sources')
    ids = {s['id64']: s['name'] for s in canonical['systems']}
    assert ids.get(10477373803000) == 'Achenar'
    assert ids.get(9007199254740993) == 'V3 Lossless Reach'
    assert len(canonical['systems']) >= 3
    assert any(b['system_id64'] == 10477373803000 for b in canonical['bodies'])
```

- [ ] **Step 3: Run to verify it fails**

Run: `apps/api/.venv/bin/python -m pytest tests/test_cypress_v3_fixture.py -v`
Expected: FAIL — fixture directory missing / checksum manifest absent.

- [ ] **Step 4: Implement the generator**

Write `scripts/dev/build_cypress_v3_fixture.py` that: (a) loads the template `tests/fixtures/ratings_v4_sources/canonical.json` to copy its `canonical_schema` + `extras` vocab rows verbatim (so vocab foreign keys resolve); (b) builds a `systems` list of ≥3 curated systems including `10477373803000`/"Achenar" and `9007199254740993`/"V3 Lossless Reach" with valid coords + `galaxy_region_id` present in the vocab; (c) builds a matching `bodies` list (≥1 primary-star body for Achenar) using the template body columns; (d) writes `canonical.json`, a minimal valid `source-metadata.json` (copy the template `source`/`run`/`artifact` records, regenerating `source_run_id`/`artifact_id` as needed), and a `spansh-system-dumps.zip` whose members are `<id64>.json` subType artifacts for the curated systems; (e) computes SHA-256 of each file and writes `manifest.json` in the exact `load_source_fixture` shape (`schema_version`, `files_sha256` with all three keys). Keep body inventories internally consistent so `adapt_retained_chunk` (`canonical_stream.py:159-206`) accepts them: every canonical body for a system must match a source-record body `(id64, bodyId)`.

Run the generator: `apps/api/.venv/bin/python scripts/dev/build_cypress_v3_fixture.py --out tests/fixtures/cypress_v3_sources`

- [ ] **Step 5: Run the fixture test AND a load-through-bootstrap smoke test**

Run: `apps/api/.venv/bin/python -m pytest tests/test_cypress_v3_fixture.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/dev/build_cypress_v3_fixture.py tests/fixtures/cypress_v3_sources tests/test_cypress_v3_fixture.py
git commit -m "feat(finder): curated cypress v3 canonical fixture with journey id64s"
```

---

### Task 3: Cypress V3 seed CLI — build + publish a real generation

**Files:**
- Create: `scripts/dev/seed_cypress_v3_generation.py`
- Test: `tests/test_seed_cypress_v3_generation.py`

**Interfaces:**
- Consumes: Task 1 `bootstrap_published_canonical`; Task 2 fixture; the reused pipeline signatures listed in File Structure.
- Produces: `seed_cypress_v3_generation(connection, fixture_dir: Path) -> int` (returns the derived publication_sequence, `1` on first publish) and a `__main__` that connects to `$DATABASE_URL`, applies the five V3 migrations the derived build needs if not already present (`003,004,006,010,011` — same list as `test_local_search_v3.py:50-57`), and calls it. Idempotent: exits 0 without republishing if a published derived generation already exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_cypress_v3_generation.py
import os
from pathlib import Path
from uuid import uuid4
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(
    not os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL'),
    reason='isolated PostgreSQL validation URL not set',
)
def test_seed_publishes_and_exposes_journey_ids():
    import psycopg
    from psycopg.conninfo import make_conninfo
    from scripts.dev.seed_cypress_v3_generation import seed_cypress_v3_generation

    dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    db = 'seed_test_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{db}"')
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=db), autocommit=True) as conn:
                conn.execute((ROOT / 'sql/v3/migrations/001_v3_baseline.sql').read_text())
                seq = seed_cypress_v3_generation(conn, ROOT / 'tests/fixtures/cypress_v3_sources')
                assert seq == 1
                exposed = {r[0] for r in conn.execute(
                    "SELECT system_id64 FROM v3_app.system_search").fetchall()}
                assert 10477373803000 in exposed
                assert 9007199254740993 in exposed
        finally:
            admin.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
```

- [ ] **Step 2: Run to verify it fails**

Run: `apps/api/.venv/bin/python -m pytest tests/test_seed_cypress_v3_generation.py -v`
Expected: FAIL — `seed_cypress_v3_generation` undefined.

- [ ] **Step 3: Implement the seed (mirrors `_build_published_generation`)**

```python
# scripts/dev/seed_cypress_v3_generation.py
"""Publish a real V3 derived generation into the Cypress database so the
F3-repointed /api/local/search + /api/archetypes/rankings return 200.
No lifecycle shortcuts: generation + both products reach VERIFIED and are
published through v3_meta.publish_derived_generation."""
from __future__ import annotations
import os, sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api/src'))

from domain.ratings_v4_canonical import load_source_fixture
from scripts.dev.v3_canonical_bootstrap import bootstrap_published_canonical
from scripts.ratings_v4.canonical_stream import CanonicalSnapshot
from scripts.ratings_v4.production_generation import (
    create_generation, seal_source, validate_generation, write_chunk)
import scripts.v3_system_archetype as archetype_builder
from scripts.v3_system_search import (
    build_available as search_build_available,
    register_product as search_register_product,
    validate_product as search_validate_product)

DERIVED_MIGRATIONS = ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
                      '006_v3_derived_product_lifecycle.sql',
                      '010_v3_system_search_body_type_counts.sql',
                      '011_v3_system_archetype.sql')


def _ensure_migrations(connection):
    have = connection.execute(
        "SELECT to_regclass('v3_app.system_archetype_summary') IS NOT NULL").fetchone()[0]
    if have:
        return
    for name in DERIVED_MIGRATIONS:
        connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())


def seed_cypress_v3_generation(connection, fixture_dir: Path) -> int:
    already = connection.execute(
        "SELECT derived_generation_id FROM v3_meta.current_derived_generation "
        "WHERE singleton").fetchone()
    if already:
        return connection.execute(
            "SELECT publication_sequence FROM v3_meta.current_derived_generation "
            "WHERE singleton").fetchone()[0]

    canonical, metadata, _ = load_source_fixture(fixture_dir)
    bootstrap_published_canonical(connection, canonical, metadata)

    snapshot = CanonicalSnapshot.pin(connection)
    key = 'cypress_v3_' + uuid4().hex[:16]
    generation_id = create_generation(connection, snapshot, key)
    records = [{'id64': s['id64']} for s in canonical['systems']]  # export by id
    ids = [s['id64'] for s in canonical['systems']]
    chunk = snapshot.export_chunk(connection, ids)
    assert write_chunk(connection, generation_id, 0, chunk, snapshot.metadata,
                       [{'id64': i} for i in ids])

    search_gen, _, search_sha = search_register_product(connection, key)
    search_build_available(connection, search_gen, search_sha)
    arch_gen, _, arch_sha = archetype_builder.register_product(connection, key)
    archetype_builder.build_available(connection, arch_gen, arch_sha)

    eof = {'consumed_to_eof': True,
           'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
           'size_bytes': metadata['artifact']['size_bytes'],
           'systems': len(canonical['systems']), 'bodies': len(canonical['bodies'])}
    seal_source(connection, generation_id, eof)
    assert validate_generation(connection, generation_id)['status'] == 'VERIFIED'
    assert search_validate_product(connection, search_gen, search_sha)['status'] == 'VERIFIED'
    assert archetype_builder.validate_product(connection, arch_gen, arch_sha)['status'] == 'VERIFIED'

    return connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
        (generation_id, None, 0, snapshot.generation_id, snapshot.publication_sequence,
         'cypress-seed', 'cypress v3 finder journey')).fetchone()[0]


if __name__ == '__main__':
    import psycopg
    dsn = os.environ['DATABASE_URL']
    with psycopg.connect(dsn, autocommit=True) as conn:
        _ensure_migrations(conn)
        seq = seed_cypress_v3_generation(conn, ROOT / 'tests/fixtures/cypress_v3_sources')
        print(f'cypress v3 published generation sequence={seq}')
```

> NOTE for implementer: the exact `write_chunk` record/payload shape and `export_chunk` id list must match what `_ratings_generation` (`test_local_search_v3.py:61-71`) passes. If the archetype/search build needs more than one chunk for >4 systems, loop chunks exactly as that helper does (chunk_size=4). Verify against the real functions during Step 4 and adjust the chunk loop rather than guessing.

- [ ] **Step 4: Run the test**

Run: `apps/api/.venv/bin/python -m pytest tests/test_seed_cypress_v3_generation.py -v`
Expected: PASS — both journey id64s present in `v3_app.system_search`.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/seed_cypress_v3_generation.py tests/test_seed_cypress_v3_generation.py
git commit -m "feat(finder): cypress seed that publishes a real v3 derived generation"
```

---

### Task 4: Legacy↔V3 consistency invariant (fail loudly on drift)

**Files:**
- Create: `scripts/checks/assert_legacy_v3_consistency.py`
- Test: `tests/test_assert_legacy_v3_consistency.py`

**Interfaces:**
- Consumes: a `$DATABASE_URL` with both legacy `systems` seeded and a published V3 generation.
- Produces: exit 0 if every journey-critical id64 exists in BOTH `public.systems` and `v3_app.system_search` with matching `name`; non-zero + a clear message otherwise. Journey ids are a module constant `JOURNEY_SYSTEMS = {10477373803000: 'Achenar', 9007199254740993: 'V3 Lossless Reach'}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assert_legacy_v3_consistency.py
import subprocess, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_check_reports_missing(monkeypatch):
    # Runs the module's pure checker against an in-memory dict pair.
    from scripts.checks.assert_legacy_v3_consistency import diff_journey_systems
    legacy = {10477373803000: 'Achenar', 9007199254740993: 'V3 Lossless Reach'}
    v3 = {10477373803000: 'Achenar'}  # missing the lossless system
    problems = diff_journey_systems(legacy, v3)
    assert any('9007199254740993' in p for p in problems)
    assert diff_journey_systems(legacy, legacy) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `apps/api/.venv/bin/python -m pytest tests/test_assert_legacy_v3_consistency.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Implement**

```python
# scripts/checks/assert_legacy_v3_consistency.py
"""Fail CI if the browser-journey systems drift between legacy `systems` and
the published `v3_app.system_search`. Autocomplete/detail read legacy; search
reads V3 -- they MUST agree on these id64s."""
from __future__ import annotations
import os, sys

JOURNEY_SYSTEMS = {10477373803000: 'Achenar', 9007199254740993: 'V3 Lossless Reach'}


def diff_journey_systems(legacy: dict[int, str], v3: dict[int, str]) -> list[str]:
    problems = []
    for id64, name in JOURNEY_SYSTEMS.items():
        if legacy.get(id64) != name:
            problems.append(f'legacy systems missing/mismatched {id64} (want {name!r}, got {legacy.get(id64)!r})')
        if v3.get(id64) != name:
            problems.append(f'v3_app.system_search missing/mismatched {id64} (want {name!r}, got {v3.get(id64)!r})')
    return problems


def main() -> int:
    import psycopg
    ids = list(JOURNEY_SYSTEMS)
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as conn:
        legacy = dict(conn.execute(
            "SELECT id64, name FROM systems WHERE id64 = ANY(%s)", (ids,)).fetchall())
        v3 = dict(conn.execute(
            "SELECT system_id64, name FROM v3_app.system_search WHERE system_id64 = ANY(%s)",
            (ids,)).fetchall())
    problems = diff_journey_systems(legacy, v3)
    if problems:
        print('legacy/V3 journey-system drift:', *problems, sep='\n  ')
        return 1
    print('legacy/V3 journey systems consistent:', ids)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

> NOTE: confirm `v3_app.system_search` exposes a `name` column (check `sql/v3/migrations/010`); if the column is named differently, use that name in the SQL and keep the checker signature.

- [ ] **Step 4: Run the test**

Run: `apps/api/.venv/bin/python -m pytest tests/test_assert_legacy_v3_consistency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/checks/assert_legacy_v3_consistency.py tests/test_assert_legacy_v3_consistency.py
git commit -m "feat(finder): CI invariant for legacy/v3 journey-system consistency"
```

---

### Task 5: Wire the seed + invariant into the Cypress workflow

**Files:**
- Modify: `.github/workflows/cypress-parity.yml:110-124` (insert two steps between "Validate seeded Cypress database" and "Seed isolated V3 account browser journeys")

**Interfaces:**
- Consumes: Task 3 CLI, Task 4 check.
- Produces: a Cypress run where `/api/local/search` returns 200.

- [ ] **Step 1: Add the two workflow steps**

Insert after the "Validate seeded Cypress database" step (`:114`):

```yaml
      - name: Seed V3 published generation (F3 finder)
        env:
          DATABASE_URL: postgresql://edfinder:edfinder@localhost:5432/edfinder
          PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/apps/api/src
        run: apps/api/.venv/bin/python scripts/dev/seed_cypress_v3_generation.py

      - name: Assert legacy/V3 journey-system consistency
        env:
          DATABASE_URL: postgresql://edfinder:edfinder@localhost:5432/edfinder
        run: apps/api/.venv/bin/python scripts/checks/assert_legacy_v3_consistency.py
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `apps/api/.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/cypress-parity.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/cypress-parity.yml
git commit -m "ci(finder): seed + verify a published v3 generation before cypress"
```

---

### Task 6: Full local dry-run against the Cypress schema

**Files:** none (verification task).

- [ ] **Step 1: Stand up a disposable edfinder-shaped DB and run the real seed chain**

Using the local PG18 service (reference_local_test_database), create a scratch DB, apply `apply_migrations.sh --include-manual` + `seed_preview.sql` + the ratings top-up SQL (`cypress-parity.yml:78-108`), then:

Run:
```bash
DATABASE_URL=<scratch> apps/api/.venv/bin/python scripts/dev/seed_cypress_v3_generation.py
DATABASE_URL=<scratch> apps/api/.venv/bin/python scripts/checks/assert_legacy_v3_consistency.py
```
Expected: seed prints `sequence=1`; consistency check prints "consistent".

- [ ] **Step 2: Exercise the real endpoint code path**

Run a short asyncpg script (pattern: `test_local_search_v3.py:119-140`) calling `local_search.local_db_search_v3({}, pool)` against the scratch DB; assert the response `ranking` block is present and results include `10477373803000`.
Expected: 200-shaped dict, journey id present, no legacy relations touched.

- [ ] **Step 3: Commit any fixes surfaced (fixture/seed/chunk-loop adjustments), else note the clean dry-run in the PR.**

---

### Task 7: Record the production rollout gate (D6)

**Files:**
- Modify: `docs/operations/v3-production-application-release.md`

- [ ] **Step 1: Add a fail-closed note**

Add a subsection stating: promoting the F3 endpoint cutover (PR #777) to production REQUIRES that the `system_search` and `system_archetype` products are built and `VERIFIED` and published against the live `ratings_v4_prod_p4_parallel_v1` derived generation first; otherwise the production Finder `/api/local/search` returns 404 (no published generation) or empty results. Cross-link the roadmap's outstanding "F1 system_search rebuild + F2b product build" items.

- [ ] **Step 2: Commit**

```bash
git add docs/operations/v3-production-application-release.md
git commit -m "docs(finder): record F3 prod-promotion gate on v3 product publish"
```

---

## Self-review

**Spec coverage:**
- Red E2E root cause (404 no published gen) → Tasks 1-3+5 publish a real generation.
- id64 alignment (Achenar 10477373803000, V3 Lossless 9007199254740993) → Task 2 fixture + Task 4 invariant.
- No lifecycle shortcuts (Global Constraints, D1) → Task 3 uses `publish_derived_generation`.
- Don't mutate the pinned ratings_v4 fixture → Task 2 uses a separate `cypress_v3_sources` dir.
- Autocomplete/detail stay legacy → design (D2), not changed.
- Prod-rollout risk (D6) → Task 7.
- Drift protection (D5) → Task 4.

**Open verification items flagged inline for the implementer (must resolve during execution, not guess):**
1. Exact `write_chunk`/`export_chunk` record + payload shapes and chunk-loop count for the curated system set (Task 3, Step 3 NOTE).
2. `v3_app.system_search` `name` column name (Task 4, Step 3 NOTE) — confirm against `sql/v3/migrations/010`.
3. The curated fixture's body/source inventory must satisfy `adapt_retained_chunk`'s inventory-match validator (Task 2, Step 4).

**Placeholder scan:** none — every code step carries real code; verification items are explicit, bounded, and assigned.

**Type consistency:** `bootstrap_published_canonical`, `seed_cypress_v3_generation`, `diff_journey_systems` signatures are used consistently across tasks and tests.
