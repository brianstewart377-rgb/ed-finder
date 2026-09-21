# Spansh spectral class and body classification ingest

## Scope, source and authority

This change prepares a versioned V3 importer extension and verifies it using a
small local sample. It does not access a production database, build a governed
canonical generation, mutate published catalogue rows, publish a generation,
or push to `main`.

Implementation commit: **`6c87448948c1b7034c965d7ab2d37cdc62368d04`** on local
branch `codex/spansh-v3-classification`, based on freshly fetched `origin/main`
commit `89408bf12c0035baff0fd6d70cb1159e13b56092`. The report is committed
separately after validation.

Source attribution: **Spansh**, [galaxy data dumps](https://spansh.co.uk/dumps).
The task owner states that ED-Finder received an authorized Spansh data grant on
**2026-09-19**. That authorization is supplied by the owner; this work has not
read or independently verified the grant terms and makes no broader licensing
claim. A later production operation must retain the applicable grant evidence,
source attribution, artifact identity and acquisition provenance.

## Investigation

The findings below describe the checked-in source and retained fixture evidence,
not a fresh production database inspection.

| Area | Finding |
| --- | --- |
| Retained adapter | `apps/importer/src/v3_spansh/adapter.py:499` maps only body `type` through the broad body vocabulary. Lines 536–538 copy `mainStar`, `spectralClass` and `luminosity`. There is no classification fallback from `subType`, `StarType`, `PlanetClass` or uppercase `SpectralClass`, and no inferred main-star selection. |
| Existing vocabulary | `adapter.py:30` defines `star` (ID 1), `planet` (2), `barycentre` (3), `belt_cluster` (4). `pipeline.py:357` seeds their `v3_vocab.body_type.public_code` values. |
| Canonical body storage | `sql/v3/migrations/001_v3_baseline.sql:1060` declares the generation's `bodies` table. `body_type_id`, `is_main_star`, `spectral_class` and `luminosity_class` are nullable. Existing nonblank checks do not require spectral/luminosity values. |
| Bulk write path | `apps/importer/src/v3_spansh/pipeline.py:461` loops canonical batch relations and writes body tuples with Psycopg `COPY ... FROM STDIN` and `copy.write_row()`. The retained `contracts.py:36` body column contract already includes all four classification/main-star fields. |
| Main-star selection in API | Both `apps/api/src/routers/map.py:580` (whole-galaxy sample) and `:656` (bounded viewport) join bodies by `system_id64`, require `b.is_main_star`, order by `body_pk`, and return `spectral_class` as `main_star_class`. The route does not derive a class from body vocabulary or select a fallback star. |
| Duplicate-main risk | The baseline has no constraint enforcing one main star per system. With multiple flags the API chooses the lowest `body_pk`, even if its spectral value is null. The extension must resolve main-star selection deterministically before writing. |
| Renderer | The current file is `apps/web/src/lib/spatial/stellar-presentation.ts`, not the `babylon/` subdirectory. `leadingClass()` at line 242 recognizes a single leading class separated by whitespace, `(` or end of string; unnormalized `G2V` would fall through to unknown. `stellarPresentation()` at line 253 accepts the listed ordinary and compact-object keys. |
| Client handoff | `apps/web/src/lib/api/client.ts:446` retains `main_star_class` as `mainStarClass`; `apps/web/src/lib/spatial/galaxy-star-stream.ts:141` passes it to `primaryStar.type`. No API or renderer production change is necessary once canonical rows contain the expected class and main flag. |

Thus an absent source `spectralClass` becomes a null canonical `spectral_class`
even when a useful Spansh `subType` exists. An absent `mainStar` is a separate
cause of a null API result. The unknown presentation's cyan core
`[0.47, 0.78, 0.88]` explains why missing classes share one apparent colour.

## Extension and vocabulary compatibility

The restored `v3_spansh` package is historical source evidence. Its files, the
baseline SQL and their source-recovery manifest remain unchanged.
`scripts/ratings_v4/canonical_stream.py:33` verifies per-file hashes and a hash
of **every sorted Python file** in the retained package. Adding a Python file
inside that package would also invalidate the retained importer identity.
The extension therefore lives in the versioned sibling package
`apps/importer/src/v3_spansh_classified`, reuses the canonical row contract,
and identifies its own normalization rules.

The baseline schema's `body_type_id` has **broad entity-type semantics**. The
explicit source-class mapping populates the existing public codes rather than
replacing them with fine-grained planet names:

| Recognized source classification family | `v3_vocab.body_type.public_code` | Meaning |
| --- | --- | --- |
| Ordinary spectral classes, brown dwarfs, pre-main-sequence stars, giant/Wolf-Rayet/carbon stars, neutron stars, white dwarfs, black holes | `star` | Stellar body, including compact objects |
| Earth-like, water, ammonia, rocky, icy, rocky-ice, metal-rich, high-metal-content worlds and supported gas-giant classes | `planet` | Planetary body |
| Barycentre | `barycentre` | Nonphysical system/orbit grouping |
| Belt cluster | `belt_cluster` | Belt cluster entity |
| Missing or unrecognized classification | Unknown unless independent recognized broad type exists | Do not invent a physical class |

An independent comparison against the
[Spansh galaxy schema](https://docs.spansh.co.uk/galaxy.schema.json), fetched
2026-09-20, found all **219 non-null spectral enum values**, **43 stellar
subtypes** and **18 planetary subtypes** recognized, with zero unmapped values.
The explicit tables in
`apps/importer/src/v3_spansh_classified/classification.py` are the authoritative
list of accepted source spellings: `PLANET_CLASS_TO_PUBLIC_CODE`,
`STAR_SUBTYPE_TO_SPECTRAL_CLASS` and `STAR_TYPE_TO_SPECTRAL_CLASS`. They include
the 18 Spansh-schema planet subtypes and the named stellar subtypes, plus
explicit Frontier aliases. Examples include `G (White-Yellow) Star` →
`star`/`G`, `StarType=N` → `star`/`neutron`, `White Dwarf (DA) Star` →
`star`/`white-dwarf`, `Black Hole` → `star`/`black-hole`,
`PlanetClass=Earthlike body` → `planet`, and `High metal content world` →
`planet`. Unknown values remain observable rather than being silently mapped
by an arbitrary first letter.

The classifier reconciles `type`/`Type`, `spectralClass`/`SpectralClass`,
`starType`/`StarType`, `planetClass`/`PlanetClass` and
`subType`/`SubType`/`subtype`; conflicting recognized stellar/planetary or
spectral evidence is rejected. Numbered spectral values such as `G2 V`
normalize to the supported class. Luminosity aliases are retained separately.

Main selection considers only recognized stars. It prefers explicit true
main flags; otherwise it considers stars with no explicit false flag. Within
those candidates it ranks zero arrival distance, Frontier body ID zero,
nearest finite nonnegative arrival distance, then stable body identity.
Duplicate explicit true flags use the same deterministic rule and produce
diagnostic evidence. Nonboolean flags, contradictory aliases, duplicate body
identity and a planet explicitly flagged as main are rejected. The adapter
copies the source payload before normalization and writes at most one true
main flag per system. An explicitly selected main star with an unknown
spectral class remains unknown; a classified companion does not substitute
its colour. Exact `subType` text and numeric subclass evidence remain in the
source artifact; this extension adds no canonical columns.

Keeping these public codes preserves Ratings V4 compatibility:
`apps/api/src/domain/ratings_v4_canonical.py:244` compares the canonical code
directly with the source's broad `type`; replacing `planet` with, for example,
`water_world` would reject the otherwise matching source body. That adapter
already consumes source `subType` separately for detailed mechanics. This work
does not change its frozen scoring or source-admission contract. Its stellar
spectral fallback recognizes `N`/`H`/`D` codes rather than the map's normalized
compact-object strings; known detailed Spansh `subType` evidence still resolves
those objects. A future consumer reading only broad `star` and the new
normalized spectral string needs a separately versioned compatibility update.
Detailed planetary taxonomy is an explicit remaining canonical-schema gap,
not a claim that `body_type_id` now distinguishes water and rocky worlds.

## Spectral values and existing colour keys

The normalized values below are existing renderer inputs, not new UI classes.
Colours are the renderer's display palette, not inferred physical temperatures.

| Example source class or subtype | Stored `spectral_class` | Renderer glyph | Core RGB |
| --- | --- | --- | --- |
| `O`, `O5`, `O (Blue-White) Star` | `O` | `main-sequence-o` | `0.18, 0.27, 1` |
| `B`, `B2`, `B (Blue-White) Star` | `B` | `main-sequence-b` | `0.29, 0.34, 1` |
| `A`, `A3`, `A (Blue-White) Star` | `A` | `main-sequence-a` | `0.62, 0.55, 1` |
| `F`, `F4`, `F (White) Star` | `F` | `main-sequence-f` | `0.92, 0.94, 1` |
| `G2`, `G2V`, `G (White-Yellow) Star` | `G` | `main-sequence-g` | `1, 0.98, 0.66` |
| `K`, `K4`, `K (Yellow-Orange) Star` | `K` | `main-sequence-k` | `1, 0.47, 0.19` |
| `M`, `M4`, `M (Red dwarf) Star` | `M` | `main-sequence-m` | `1, 0.20, 0.06` |
| `N`, `N5`, `Neutron Star` | `neutron` | `neutron` | `1, 1, 1` |
| `D`, `DA`, `DAB`, `DAZ5`, `White Dwarf (DA) Star` | `white-dwarf` | `white-dwarf` | `0.86, 0.91, 1` |
| `H`, `H0`, `Black Hole` | `black-hole` | `black-hole` | `0.005, 0.007, 0.012` |
| `SupermassiveBlackHole`, `Supermassive Black Hole` | `supermassive-black-hole` | `supermassive-black-hole` | `0, 0, 0` |
| `L`, `L4`, `L (Brown dwarf) Star` | `L` | `brown-dwarf-l` | `1, 0.16, 0.035` |
| `T2`, `Y1`, corresponding brown-dwarf subtype | `T` / `Y` | `brown-dwarf-y-t` | `0.78, 0.035, 0.08` |
| `C`, `CJ4`, `CN5`, `MS6`, `S7`, corresponding subtype | `carbon` | `carbon` | `0.92, 0.93, 0.42` |
| `W`, `WNC0`, `WO0`, named Wolf-Rayet subtype | `wolf-rayet` | `wolf-rayet` | `1, 1, 1` |
| `AeBe8` / `Herbig Ae/Be Star`; `TTS3` / `T Tauri Star` | `AeBe` / `T Tauri` | `ttauri-herbig` | `1, 0.09, 0.13` |

The additional values also correspond to existing renderer families:
Spansh `L/T/Y (Brown dwarf) Star`, C/CJ/CN/MS/S carbon types, Wolf-Rayet
subtypes, Herbig Ae/Be and T Tauri respectively. `H`/`H0` with an explicit
`Supermassive Black Hole` subtype resolves to the more specific existing
supermassive marker. Luminosity is retained separately where supplied.
`/api/map/systems` currently
returns only spectral class, so it cannot distinguish an ordinary `M` marker
from an `M` giant solely using `luminosity_class`.

## Validation and reproducible local run

The bounded local runner is
`scripts/dev/import_spansh_classified_slice.py`. Its dry run reads the source
without a database connection:

```powershell
python scripts/dev/import_spansh_classified_slice.py `
  --artifact <small-sample.json.gz> `
  --artifact-metadata <small-sample-metadata.json> `
  --generation-key <local-candidate-key> `
  --max-systems 1000 --chunk-systems 100 --dry-run
```

The local writer requires a loopback database on an explicit nondefault port
whose name starts with `spansh_classified_test`. It rejects an existing
generation key and creates only a fresh candidate; it does not change or
require the absence of an existing published pointer, and cannot publish.
The complete extracted local slice is hashed and validated before any write;
an over-limit slice is rejected rather than silently truncated. A complete
slice is not a complete-galaxy inventory or an eligible publication receipt.

Frontend verification: the focused
`apps/web/src/lib/spatial/stellar-presentation.test.ts` suite passes **34
tests** using Node **24.15.0** and Vitest **4.1.0**. Added cases exercise exact
`neutron`, `white-dwarf`, `black-hole`, `supermassive-black-hole`, `T Tauri`,
`AeBe`, `T`, `carbon` and `wolf-rayet` importer outputs alongside the existing
O/B/A/F/G/K/M cases. The isolated configuration resolves source files
from this worktree and reuses installed dependencies from the original local
checkout; the generated Svelte tsconfig was needed for TypeScript transform.

Python validation uses **CPython 3.14.7**, pinned **Psycopg 3.3.4** and a
disposable **PostgreSQL 18.6** instance:

| Check | Result |
| --- | --- |
| Classification, adapter, pipeline and PostgreSQL integration suites | **368 passed, no skips** |
| Existing `test_ratings_v4_canonical_stream.py` regression suite | **24 passed, 3 skipped**; the retained-source checksum test passes. The skips require a separate optional Ratings V4 database fixture. |
| Stellar presentation suite | **34 passed** |
| New Python code lint | **Ruff passed** |
| Genuine eight-system slice dry run and actual PostgreSQL COPY | **Passed**; candidate `READY`, never published |

Tests cover mapping aliases, malformed/unknown source classes, deterministic
main selection, renderer values, public-code lookup with nonbaseline IDs,
parameterized COPY, vocabulary conflict checks, local routing protection,
and preservation of retained source checksums. The database integration
executes the same main-star lateral selection as both map API query paths.

For the committed fixture tests, set `EDFINDER_SPANSH_TEST_DATABASE_URL` to a
dedicated loopback PostgreSQL 18 admin connection on an explicit non-5432
port. Credentials are intentionally omitted here. The fixture creates and
removes its own uniquely named database and applies the original baseline
there; it does not reset the database named in the supplied admin connection.

```powershell
$env:EDFINDER_SPANSH_TEST_DATABASE_URL = '<dedicated-local-PostgreSQL-18-admin-DSN>'
$env:EDFINDER_SPANSH_TEST_DATABASE = 'yes'
.venv-spansh/Scripts/python.exe -m pytest -q `
  tests/test_v3_spansh_classification.py `
  tests/test_v3_spansh_classified_adapter.py `
  tests/test_v3_spansh_classified_pipeline.py `
  tests/test_v3_spansh_classified_postgres.py
.venv-spansh/Scripts/python.exe -m pytest -q tests/test_ratings_v4_canonical_stream.py
```

Two source datasets serve different purposes:

- The committed test fixture uses the existing 12-system Spansh API archive
  `tests/fixtures/ratings_v4_sources/spansh-system-dumps.zip`, unwrapped into
  the galaxy-dump array shape, plus explicitly synthetic ordinary/compact
  stars and main-selection cases. This exercises the full required palette
  and public-code lookup with nonbaseline vocabulary IDs; it is not presented
  as original full-galaxy dump bytes.
- A genuine bounded read of
  [Spansh's galaxy dump](https://downloads.spansh.co.uk/galaxy.json.gz) on
  2026-09-20 returned HTTP **206** for a request capped at **2 MiB**. Only
  **8,192 compressed bytes** were consumed to recover eight complete system
  objects. The reconstructed complete array was gzip-compressed to **5,357
  bytes** with SHA-256
  `6ed093b9763f3d8acad14a5e9915e25457467e93b3836f337761ef6e572e4fe3`.
  This hash covers the extracted slice only; no whole-dump checksum or EOF
  completeness is claimed.

The genuine sample and acquisition metadata are local validation artifacts
under `.local-spansh-db/real-dump-slice/`. Its dry run reports **8 systems,
32 bodies: 17 stars, 8 planets, 7 barycentres**, with **zero unknown bodies or
unmapped values**. Six systems receive main-star classifications. The other
two, **Loihaei AA-A h0** (`752919`) and **Ainaihn AA-A h0** (`752927`), have
empty source body arrays, so their main class correctly remains unknown.
No main star is fabricated for absent body evidence.

The exact local dry-run invocation for that extracted sample is:

```powershell
.venv-spansh/Scripts/python.exe scripts/dev/import_spansh_classified_slice.py `
  --artifact .local-spansh-db/real-dump-slice/galaxy-first-eight.json.gz `
  --artifact-metadata .local-spansh-db/real-dump-slice/metadata.json `
  --max-systems 8 --dry-run
```

The same sample was then copied into a newly created disposable PostgreSQL
18.6 database with the original baseline already applied. The local CLI used:

```powershell
$env:SPANSH_CLASSIFIED_TEST_DSN = '<local-DSN-for-fresh-spansh_classified_test-database>'
.venv-spansh/Scripts/python.exe scripts/dev/import_spansh_classified_slice.py `
  --artifact .local-spansh-db/real-dump-slice/galaxy-first-eight.json.gz `
  --artifact-metadata .local-spansh-db/real-dump-slice/metadata.json `
  --generation-key real_dump_slice_test --max-systems 8 --chunk-systems 3
```

The written candidate contains all **32 bodies**, reaches **READY**, and has
no publication. The real map selection returns `black-hole` for Cygni X-3,
Eephonth AA-A h0 and Juemiae AA-A h0, `O` for Dryoea Flyou AA-A h0,
`wolf-rayet` for Eor Aob AA-A h0, and `B` for Spleedaea AA-A h0. The two empty
systems remain null, matching the dry run. The detailed local receipt is
`.local-spansh-db/real-dump-slice/pg18-rehearsal.json`.
Disposable rehearsal databases were removed and their local servers stopped.

## Later production operation

Production execution remains a separate governed integration. The bounded
local CLI above is not a turnkey full-galaxy production import command.

1. Review the local report and tested extension at an exact commit. Retain the
   2026-09-19 grant evidence and required Spansh attribution in the approved
   source policy. Acquire the authorized full artifact and pin byte count,
   SHA-256, acquisition time and source effective time.
2. Design and authorize a **new unpublished canonical candidate** using the
   versioned normalizer. Wire the extension into the governed source-run,
   admission, checkpoint and publication workflow with an explicit new code
   identity. Neither the restored historical lab runner nor the local sample
   command constitutes authority to operate production.
3. Resolve vocabulary by public code; stream bounded chunks; validate retained
   source identity, complete EOF/hash verification, unknown/conflict coverage,
   referential integrity and deterministic main-star coverage. Follow
   `docs/development/bulk-database-write-safety.md`; keep required identity and
   foreign-key triggers enabled for inserts rather than suppressing them.
4. Validate ordinary/compact-object class distributions, remaining unknowns,
   one selected main star where source evidence supports selection, and both
   map-query paths against the candidate. Rebuild and validate affected derived
   products under their own governed contracts before publication. Retain and
   test the detailed subtype bridge for Ratings V4: its frozen spectral
   fallback does not recognize the new named compact-object strings when
   only broad canonical `star` is available.
5. Publish only through the separately approved canonical pointer transition,
   retain rollback/evidence receipts, account for map cache expiry or approved
   cache invalidation, then verify representative API responses and rendered
   colours. Do not bulk-update the current published generation in place.

No production step above was executed as part of this change.

## Remaining gaps

- Existing production rows remain unchanged until a later governed import and
  publication. This local code change alone does not recolour the live map.
- Detailed planet taxonomy is not a separate canonical body field; the broad
  vocabulary and existing Ratings V4 subtype enrichment are preserved.
- Named remnant spectra alone are not understood by the frozen Ratings V4
  spectral fallback. Its future builder must retain and validate the subtype
  bridge, or introduce a separately versioned compatibility change.
- Unknown or contradictory source classes require reporting and review rather
  than guessed spectral values.
- The API does not expose luminosity alongside the main spectral class, so
  giant-specific map presentation is outside this ingest change.
- Full-artifact resource use, production coverage and published-generation
  rollout remain untested by the bounded local sample.
