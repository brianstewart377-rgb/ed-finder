# V3 Finder F4 archetype ranking UI design

## 1. Status

**Status: Design only; not implemented — 2026-10-10 — base `origin/main` `3b6ee91a2e4b076a97a2564cc38310411b534beb`.**

F4a and F4b are code-only increments validated against disposable fixtures.
They remain hidden behind a default-off build feature gate until the governed
production sequence has applied the pending migrations (rewritten `011` and
`015` included), built and validated both Finder products on the already
published `ratings_v4_prod_p4_parallel_v1`, **published both products** with
`v3_meta.publish_derived_product` (two product-publication receipts; the
generation pointer does not move — the owner's 2026-10-10 capacity decision
replaced the fresh-generation route, `docs/ROADMAP.md` “Capacity decision”
paragraph and steps 4′–9′), and passed the separate application-release gate.
In addition, F4b must not
be enabled anywhere—not even behind that gate in Product E2E—until slice 1c has
landed with its representative-scale timing proof. F4b suppresses distance from
Compare until F4c makes it reference-safe, and F4c is a hard prerequisite before
the flag is enabled in any governed production/release build. This design does
not authorize migration application, product build/publication, deployment or
promotion.
The first F4 surface keeps Any mode on today's no-floor request; exposing a
minimum tier in Any additionally depends on the bounded access path in slice 1d.

## 2. Goal and non-goals

### Goal

F4 prepares the Svelte application in `apps/web` for a Finder archetype picker,
S/A/B/C/D tier and confidence display, primary and secondary archetype labels on
each result, and a **Best Colony Potential** headline. Ranking comes from the V3
ranking API after the governed data gate opens. This is behavioural parity with
the accepted V2 journey—choose an intent, receive explained ranked results,
then continue to Inspect and the map—not numeric parity with V2 scores
(`docs/development/v3-finder-delivery-plan.md:64-76`,
`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:11-19`).

In this document:

- An **archetype** is a named colony pattern, such as Mining Hub, against which a
  system is scored.
- A **tier** is a readable band derived from a 0–100 score: S is the strongest
  band, followed by A, B, C and D
  (`apps/api/src/ranking/profile.py:52-54`).
- **Confidence** is mode-specific: in Any mode it describes the system's general
  evidence; in selected-archetype mode it describes that selected fit.
  **Completeness** says how much expected system evidence is present. Neither is
  the score or certainty (`apps/api/src/ranking/ranking_sql.py:87-103`,
  `apps/api/src/models.py:264-271`).
- **Slice 1** means the two V3-backed ranking endpoints already delivered;
  **slice 1b** exposes the summary-owned overall tier; **slice 1c** makes every
  selected-archetype request bounded; **slice 1d** is the later API prerequisite
  for a bounded Any-mode tier floor; and **slice 2** means the deferred endpoint
  cutovers described below
  (`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:60-71`).

### Non-goals

- Do not make the first F4 increment depend on slice 2 `/rerank`,
  `/system/{id64}` or `/simulate`. Those may be added only as a clearly later
  increment after their V3 cutover
  (`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:66-71`).
- Do not read, preserve or revive legacy V2 relations. The remaining archetype
  handlers still using them are specifically out of bounds
  (`apps/api/src/routers/archetypes.py:12-19`).
- Do not add work to retired `frontend/`; `apps/web/` is the sole browser target
  (`CLAUDE.md:154-167`).
- Do not calculate rankings, tiers or domain explanations in Babylon. Finder is
  the query/ranking owner and the renderer only presents the supplied spatial
  contribution
  (`docs/colonisation-redesign/spatial-platform-product-contract.md:100-114`).
- Do not claim economy-specific V3 ranking: the current local-search handler
  rejects it because no per-economy projection exists
  (`apps/api/src/local_search.py:871-884`).

The code branch contains the slice-1 handlers described below, but that does not
supersede the roadmap's production gate. Migrations `010`/`011` are not applied,
the published generation has no Finder products, and the required governed
build, validation, publication and release sequence remains outstanding
(`docs/ROADMAP.md:121-179`).

## 3. What exists today

### API and ranking data

| Surface                                        | Current implementation                                                                                                                                                                                                                                                                                                                                                         | Consequence for F4                                                                                                                                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/local/search`                       | The route delegates to `local_db_search_v3` (`apps/api/src/routers/search.py:157-203`, `apps/api/src/routers/search.py:243-245`). That implementation reads V3 search and archetype-summary projections through the ranking query, pins one published generation, and emits ranking identity (`apps/api/src/local_search.py:843-850`, `apps/api/src/local_search.py:925-963`). | Available in code and disposable fixtures for **Any** (no selected archetype); not production-ready until the governed data gate opens.                                                 |
| `GET /api/archetypes/rankings`                 | The handler validates one of the eight V3 keys, passes it as `picked_archetype`, and reads in one repeatable-read snapshot (`apps/api/src/routers/archetypes.py:294-405`).                                                                                                                                                                                                     | Available in code and disposable fixtures, but no selected-archetype F4 mode may be enabled until slice 1c bounds its ordering and count; production also has no usable Finder product. |
| `POST /api/archetypes/rerank`                  | The handler reads `system_archetype_scores` and other legacy relations (`apps/api/src/routers/archetypes.py:535-590`).                                                                                                                                                                                                                                                         | Not usable; wait for slice 2.                                                                                                                                                           |
| `GET /api/archetypes/system/{id64}`            | The current handler reads legacy systems/archetype/topology relations (`apps/api/src/routers/archetypes.py:635-719`).                                                                                                                                                                                                                                                          | No V3 per-system explanation drawer yet; wait for slice 2.                                                                                                                              |
| `POST /api/archetypes/simulate`                | The current handler reads legacy `system_archetype_scores` (`apps/api/src/routers/archetypes.py:905-929`).                                                                                                                                                                                                                                                                     | Not usable; wait for slice 2.                                                                                                                                                           |
| `GET /api/archetypes/profiles`                 | It returns static legacy preset data, including the old archetype set (`apps/api/src/routers/archetypes.py:114-171`, `apps/api/src/routers/archetypes.py:989-1005`).                                                                                                                                                                                                           | It must not populate the V3 picker.                                                                                                                                                     |
| `/api/search/galaxy` and `/api/search/cluster` | The module deliberately leaves both on the older implementation pending slice 2 (`apps/api/src/local_search.py:574-586`).                                                                                                                                                                                                                                                      | Not part of F4a/F4b.                                                                                                                                                                    |

Both usable ranked paths fail explicitly when the published generation lacks
READY `system_search` or `system_archetype` products, instead of presenting a
false empty result (`apps/api/src/local_search.py:602-643`).

That failure is the expected production state today: the published generation
has no Finder products, so the readiness check returns HTTP 503 before a ranked
read (`docs/ROADMAP.md:140-179`, `apps/api/src/local_search.py:620-642`). But the
same handler also maps missing relations and ordinary PostgreSQL errors to 503
(`apps/api/src/routers/archetypes.py:365-387`), so status alone cannot identify
unpublished data. F4 treats every 503 as temporary unavailability, not as zero
matches; readiness-specific copy requires a stable machine-readable reason. It
preserves the current selection and map, offers Retry and Any mode, and never
converts 503 into an empty-state message.

`/api/local/search` has no archetype request field
(`apps/api/src/models.py:537-564`) and currently calls the ranking builder with
`picked_archetype=None` (`apps/api/src/local_search.py:899-917`). The selected
archetype path must therefore call `/api/archetypes/rankings` on current main.
That endpoint accepts no arbitrary reference coordinates and measures distance
from Sol (`apps/api/src/routers/archetypes.py:289-293`,
`apps/api/src/routers/archetypes.py:346-363`). A selected archetype cannot yet be
honestly combined with the current “within 500 ly of this known star” mode.

### Response contracts

The local-search row declares `archetype_score`, `archetype_tier`,
`primary_archetype`, `secondary_archetype`, `archetype_confidence`,
`overall_development_potential`, `confidence`, and `completeness`
(`apps/api/src/models.py:216-271`). Its V3 row builder fills those fields from
the selected score and archetype summary (`apps/api/src/local_search.py:787-840`).

The selected-archetype response declares `score`, `tier`,
`selected_archetype`, primary and secondary archetypes, two confidence concepts,
Best Colony Potential and completeness
(`apps/api/src/models.py:875-924`). The handler preserves the distinction between
selected-fit evidence confidence and primary/secondary classification confidence
(`apps/api/src/routers/archetypes.py:422-459`) and fills the row at
`apps/api/src/routers/archetypes.py:465-494`.

The two row shapes are not interchangeable. Rankings uses `score` and
`distance_to_sol` (`apps/web/src/lib/api/generated/types.gen.ts:36-57`), while
the Explore facade expects `archetype_score` and `distance` plus catalogue facts
(`apps/web/src/lib/api/client.ts:264-299`). The facade must normalize the
ranking response; the component must never cast it to `ExploreSystem`.

The summary relation already owns `best_tier`
(`sql/v3/migrations/011_v3_system_archetype.sql:22-39`), but ranking SQL selects
the summary potential without its tier, and neither response model exposes a
`best_tier` field (`apps/api/src/ranking/ranking_sql.py:485-501`,
`apps/api/src/models.py:216-271`, `apps/api/src/models.py:875-902`). The current
selected-row `tier` belongs only to selected-fit `score`
(`apps/api/src/routers/archetypes.py:462-482`). No current payload can truthfully
put a tier beside the **Best Colony Potential** headline.

### Current `apps/web` Finder flow

The client-only `/explore` route renders `ExploreWorkspace`
(`apps/web/src/routes/explore/+page.svelte:1-5`,
`apps/web/src/routes/explore/+page.ts:1-2`). The workspace holds the query,
anchor, selection and map state locally and has no archetype, tier or weight
state (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:65-113`).

There is no shared runtime configuration or feature-flag module in `apps/web`.
The only analogous app switch is the build-time `VITE_REVIEW_LAB` read
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:65-67`). F4a creates
one central config module exposing fail-closed
`VITE_FINDER_F4_ENABLED === '1'`; fixture/Product E2E builds may opt in, while
ordinary and production builds default to hidden until the governed gate opens.

That flag gates the complete F4 behavior boundary, not only its DOM. With the
flag disabled, Explore does not hydrate ranking state from `archetype`,
`min-tier`, `page_size`, `offset` or future `weight` parameters; it strips those
F4 parameters with SvelteKit replace-state while preserving `selected`, `system`
and unrelated query parameters. The rankings request branch is unreachable, no
rankings query/effect is constructed, and Explore preserves today's exact request derivation and
`searchExploreSystems` call (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-144`).
Picker/cards/status, ranking URL writers, history hydration and selected-point F4
reconstruction are all disabled with it. Thus a hand-authored archetype URL in a
disabled build cannot activate either ranking state or `/api/archetypes/rankings`.

Its only Finder input is an accessible known-system combobox
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:677-741`). With an
anchor it sends an economy-agnostic, distance-sorted 500 ly search; without an
anchor it sends a 24-row galaxy-wide development ranking
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-139`). TanStack
Query keys and issues that request immediately
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:140-144`,
`apps/web/src/lib/api/query.ts:68-79`).

The result array feeds both the DOM list and the renderer-neutral Finder map
contribution (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:280-305`).
Selecting a DOM row persists the exact id64 and focuses the map; a Babylon pick
updates the same selection through a fail-closed id64 parser
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:468-519`). The
Inspect hand-off is already the canonical `/inspect?system={id64}` route
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:818-824`), and Inspect
parses that id64 before rendering detail
(`apps/web/src/routes/inspect/+page.svelte:8-32`).

The current row renders only identity, distance, economy, population and star
type (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:800-816`). It
does not render any F4 ranking content.

### Typed client and persistence

The generated client already contains the V3 rankings operation
(`apps/web/src/lib/api/generated/sdk.gen.ts:744-749`) and generated types already
carry tier, score, primary/secondary archetypes, both confidence values,
completeness and ranking identity
(`apps/web/src/lib/api/generated/types.gen.ts:31-158`,
`apps/web/src/lib/api/generated/types.gen.ts:5006-5023`). The handwritten facade
does not import that operation (`apps/web/src/lib/api/client.ts:35-61`). Its
`ExploreSystem` type already picks most archetype fields, but omits generic
`confidence` and `completeness` (`apps/web/src/lib/api/client.ts:264-299`), even
though generated `SystemRow` includes them
(`apps/web/src/lib/api/generated/types.gen.ts:7579-7587`).

Application components are required to use the facade rather than generated
modules or raw fetch; a repository guard enforces that boundary
(`tests/test_svelte_generated_client_boundary.py:18-62`).

Explore does not currently encode Finder inputs in the URL. The existing URL
pattern parses `?system=` in `AppShell`, copies it into the selected-system store,
and on `/explore` mounts `SystemOverlay`
(`apps/web/src/lib/components/AppShell.svelte:19-52`,
`apps/web/src/lib/components/AppShell.svelte:76`). The modal takes focus and its
close path removes `system` (`apps/web/src/lib/components/SystemOverlay.svelte:37-44`,
`apps/web/src/lib/components/SystemOverlay.svelte:79-86`), so that parameter
cannot also be F4's passive shared-selection contract.
Central persistence keys and validated stores live in
`apps/web/src/lib/persistence/storage.ts:6-26` and
`apps/web/src/lib/persistence/stores.ts:40-125`; there is no Finder-query key.
Selecting a result currently writes only that store
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:468-473`), and a
Babylon system pick does the same
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:505-516`); neither
handler has a distinct passive `selected=` share contract.

### Fixtures

The Product E2E corpus contains exactly three systems: Achenar `10477373803000`, V3 Lossless Reach
`9007199254740993`, and HD 38179 `158872029`
(`tests/test_cypress_v3_fixture.py:20-24`,
`tests/test_cypress_v3_fixture.py:66-83`,
`scripts/dev/build_cypress_v3_fixture.py:39-52`,
`tests/fixtures/ratings_v4_real_systems.json:1`,
`tests/test_seed_cypress_v3_generation.py:186-203`). The Cypress seed builds and validates
both Finder products before publication
(`scripts/dev/seed_cypress_v3_generation.py:1-11`,
`scripts/dev/seed_v3_fixture_generation.py:259-300`). It therefore publishes
`system_archetype` data that F4 can query.

The seed contract asserts `len(exposed) == 3`
(`tests/test_seed_cypress_v3_generation.py:167-191`). Current Explore requests 24
rows (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-139`), while
the rankings endpoint defaults its existing `limit` to 50
(`apps/api/src/routers/archetypes.py:517-518`). Therefore the committed corpus
cannot produce a Next transition at either default page size; the F4 facade and
Product E2E contract below deliberately request one row per page.

The Review Lab corpus is separate and contains Review Wiring, Review Aggregate
and Review Fallback (`scripts/dev/build_review_lab_v3_fixture.py:37-46`); its
contract requires the committed corpus to match the Review identities
(`tests/test_review_lab_v3.py:181-191`). Its seed uses the same V3 generation
builder (`scripts/dev/seed_review_v3_generation.py:108-124`).

No committed fixture expectation yet pins the exact archetype, score, tier,
confidence or completeness for any of those six systems. Existing Product
Cypress asserts system presence and selection, not archetype output
(`apps/web/cypress/e2e/product-journey.cy.ts:43-53`,
`apps/web/cypress/e2e/product-journey.cy.ts:105-182`). Before an E2E test names an
exact expected tier, add a fixture-output contract test that builds the committed
corpus and asserts the resulting V3 rows.

For this design review, the checksum-validated Product fixture was actually run
through the production Ratings encoder and archetype model. The loader verifies
all three source artifacts before reading them
(`apps/api/src/domain/ratings_v4_canonical.py:361-377`), the encoder produces the
rating vectors and economy opportunities consumed by the archetype builder
(`scripts/ratings_v4/production_generation.py:136-168`,
`scripts/v3_system_archetype.py:249-280`), and `fit_all` evaluates all eight
archetypes (`scripts/v3_system_archetype_model.py:148-152`). **Flexible at
minimum tier B (`min_score=60`) is the only B-floor journey that admits all
three systems:** V3 Lossless Reach scores 100/S, Achenar 100/S and HD 38179
75/B. After the within-window confidence/completeness modifier, their endpoint
order is **V3 Lossless Reach → Achenar → HD 38179**. The raw candidate-window
order is separately **Achenar → V3 Lossless Reach → HD 38179** because the two
100 scores tie and `system_id64 ASC` breaks that tie. The current modifier and
tie-break implementation are at `apps/api/src/ranking/ranking_sql.py:451-477`.

Manufacturing Hub cannot be the B-floor pagination fixture. It requires Refinery
and Industrial (`scripts/v3_system_archetype_model.py:22-30`), while HD 38179's
fixture vector has potentials 0 and 64 for those anchors. The anchored core is
therefore `0.6 × 0 + 0.4 × 32 = 12.8`; after specialization and capacity it
scores 7/D, below the B threshold of 60
(`scripts/v3_system_archetype_model.py:35-42`,
`scripts/v3_system_archetype_model.py:85-131`). The fixture-output contract must
pin these computed rows before Cypress relies on the exact values.

### Exact gap list

1. No canonical eight-archetype metadata module in `apps/web`.
2. No archetype picker, minimum-tier control, ranking headline or reserved
   weight-control slot.
3. No facade page-envelope normalizer or query key for
   `/api/archetypes/rankings`; its `total`/`count`/`offset` state is not exposed.
4. `ExploreSystem` omits `confidence`, `completeness`, score kind, selected
   archetype identity and distance reference; persisted snapshots lose the same
   distinctions.
5. The two slice-1 response shapes, search scopes, score meanings and distance
   references are not reconciled, and neither exposes summary `best_tier`.
6. Finder query and offset state is not URL-backed or shareable; result/map
   selection has no passive `selected=` share contract distinct from the
   `system=` detail-overlay trigger.
7. Result rows omit tier, score, confidence/completeness, primary/secondary and
   Best Colony Potential.
8. Ranking loading, empty and error messages do not name the active archetype or
   explain whether the ranking service is unavailable.
9. Result freshness can steal focus, and replacing result points can drop a
   selected marker when the selected system is absent from the new page.
10. No default-off F4 gate, state, component, Cypress or visual-regression
    coverage.
11. V3 explanations, custom reranking and simulation are still blocked on slice
    2, as the handler inventory above shows.
12. Selected-archetype ordering still sorts the eligible set by a cross-table
    modifier and its companion count is uncapped; B/60 is only a predicate, not
    a candidate bound. The three-system Product E2E corpus also cannot exercise
    pagination at the existing default page sizes.
13. A nonzero Any floor filters unindexed `best_colony_potential`; its 10,000
    count limit stops after qualifying rows rather than bounding inspected rows.
14. A render-only feature gate would leave hand-authored F4 URLs able to select
    the rankings request path.
15. Ranking URL hydration has no reactive SvelteKit navigation/popstate contract,
    and current result/map selection writes the store without `selected=`.

## 4. API dependency map

| UI element                         | Endpoint and field available today                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Availability and design rule                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Picker: **Any**                    | `POST /api/local/search`; no archetype request field (`apps/api/src/models.py:537-564`). Its optional `min_development_score` defaults to `None`, and local search adds that hard filter only when it is greater than zero (`apps/api/src/models.py:551-555`, `apps/api/src/local_search.py:725-733`).                                                                                                                                                                                                                                                                                         | Slice 1 code/fixtures. “Any” preserves today's default ranking and sends no `min_development_score`; the production gate still applies. The Minimum tier control is not rendered in Any mode until slice 1d.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Picker: one of eight archetypes    | `GET /api/archetypes/rankings?archetype=…`; key validation and profile query are in `apps/api/src/routers/archetypes.py:294-364`.                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Slice 1 code/fixtures, but **slice 1c is a hard prerequisite for every selected-archetype mode**. Initial selected mode is explicitly galaxy/Sol-oriented because the endpoint has no arbitrary anchor.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Selected-score tier badge          | Any: `results[].archetype_tier`; selected: `results[].tier` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:880-892`).                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Slice 1 code. The value is carried with `score_kind`; it is not automatically the tier for the overall headline.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Best Colony Potential** tier     | `system_archetype_summary.best_tier` exists, but is omitted from ranking SQL and both payloads (`sql/v3/migrations/011_v3_system_archetype.sql:22-39`, `apps/api/src/ranking/ranking_sql.py:485-501`).                                                                                                                                                                                                                                                                                                                                                                                         | **Slice 1b API prerequisite:** expose summary `best_tier` in rankings and local-search payloads/generated types. Until then show the headline number without a tier. Never compute an API-owned tier in the browser.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Minimum tier                       | Selected mode accepts `min_score` (`apps/api/src/routers/archetypes.py:508-518`). Any has an optional `min_development_score`, but it is deliberately omitted in F4 (`apps/api/src/models.py:551-555`).                                                                                                                                                                                                                                                                                                                                                                                            | Selected-archetype-only in the first F4 surface, defaulting to B (`60`) rather than the selected endpoint's non-tier default `40` (`apps/api/src/ranking/profile.py:52-54`). B/A/S are the initial selected-mode scope; the control is hidden in Any and `min-tier` is ignored/removed there.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Selected-ranking bounds            | Picked mode orders by a cross-table score/confidence/completeness product and its count is uncapped (`apps/api/src/ranking/ranking_sql.py:451-462`, `apps/api/src/routers/archetypes.py:348-373`). The existing selected index is `(derived_generation_id, archetype_key, archetype_score DESC, system_id64)` (`sql/v3/migrations/011_v3_system_archetype.sql:45-50`).                                                                                                                                                                                                                         | **Slice 1c hard prerequisite for all selected modes:** first probe at most 10,001 rows through that index in raw `archetype_score DESC, system_id64 ASC` order, constrained only by generation, archetype key and indexed `min_score`; the first 10,000 are the immutable candidate window and the sentinel sets `is_truncated`. Only then join/apply region, distance, ELW/body counts and every other non-indexed filter. Apply `archetype_score × confidence × completeness`, distance and id tie-breaks only to survivors inside the fixed window. Rows outside it cannot re-enter. This bounds every selected request regardless of filter selectivity. |
| Any-mode tier bound                | In Any, the floor is `sum.best_colony_potential >= $n`, but the page orders by `sum.weighted_potential DESC` (`apps/api/src/ranking/ranking_sql.py:315-327`, `apps/api/src/ranking/ranking_sql.py:333-357`, `apps/api/src/ranking/ranking_sql.py:451-462`). The only summary ordering index is `(derived_generation_id, weighted_potential DESC)` (`sql/v3/migrations/011_v3_system_archetype.sql:52-56`). The capped count stops after 10,000 **qualifying** rows (`apps/api/src/ranking/ranking_sql.py:512-565`, `apps/api/src/local_search.py:912-923`), not after inspecting 10,000 candidates. | **Slice 1d API prerequisite before Any can expose Minimum tier:** add a measured index or candidate bound keyed to `best_colony_potential`, or an explicit count/candidate-scan cap that prevents a sparse floor from inspecting most of roughly 198.5 million joined rows (`docs/ROADMAP.md:197-214`). Until then Any sends no floor and retains the existing default behavior. The `weighted_potential` ordering index alone does not bound a `best_colony_potential` predicate. |
| Confidence badge                   | Both paths return `confidence` and `completeness` (`apps/api/src/models.py:264-271`, `apps/api/src/models.py:898-902`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Slice 1 code. Say **Evidence confidence** in Any and **Fit confidence** for a selected archetype; never synthesize a missing value or use “fit” in Any mode.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Primary/secondary                  | Both paths return `primary_archetype` and `secondary_archetype` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:886-893`).                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Slice 1 now. Use canonical labels, not underscore replacement.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Best Colony Potential** headline | Both paths return `overall_development_potential`, sourced from the summary's best potential (`apps/api/src/local_search.py:806-815`, `apps/api/src/routers/archetypes.py:472-482`).                                                                                                                                                                                                                                                                                                                                                                                                           | Slice 1 code. In selected mode, distinguish the selected-fit `score` from the overall headline; attach a tier only after slice 1b supplies `best_tier`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Page/count state                   | Rankings already accepts wire parameter `limit` (default 50, API range 1–500) plus non-negative `offset` (`apps/api/src/routers/archetypes.py:517-518`). Any forwards `size`/`from` to the ranked query's `LIMIT`/`OFFSET` (`apps/api/src/local_search.py:902-911`, `apps/api/src/ranking/ranking_sql.py:479-506`); its count query receives the 10,000 cap only for galaxy-wide requests, while an anchored search (500 LY by default) keeps an exact total (`apps/api/src/local_search.py:248-254`, `apps/api/src/local_search.py:912-923`). | Slice 1c probes at most 10,001 raw/index-eligible rows. `total` is the exact post-filter count within the first-10,000 candidate window, so it may be far below 10,000 even when `is_truncated=true`; the flag says a 10,001st raw-score candidate existed, not that the filtered population overflowed. The F4 facade exposes `page_size` 1–50 (default 50), maps it to wire `limit`, and applies one 10,000 navigation ceiling to every mode before dispatch. Anchored Any shows its exact total but navigates only within the first 10,000. When selected mode is truncated, the UI says **filters applied within the top 10,000 by [Archetype] score**; URL, Next, list, map and count stop together. |
| Weight sliders                     | Current `/api/archetypes/rerank` uses legacy relations and legacy five-weight models (`apps/api/src/routers/archetypes.py:535-590`, `apps/api/src/models.py:744-763`).                                                                                                                                                                                                                                                                                                                                                                                                                         | Needs slice 2. Reserve layout only; do not call it. **Unverified:** the eventual V3 weight dimensions are not defined in current code.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Per-archetype explanation          | The V3 product stores explanation data (`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:73-77`), but `/system/{id64}` is legacy today (`apps/api/src/routers/archetypes.py:635-719`).                                                                                                                                                                                                                                                                                                                                                                                    | Needs slice 2. Do not show legacy rationale as V3 explanation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Rerank action                      | Intended endpoint is `POST /api/archetypes/rerank`; its current implementation is legacy (`apps/api/src/routers/archetypes.py:535-628`).                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Needs slice 2.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Simulation                         | Intended endpoint is `POST /api/archetypes/simulate`; its current handler reads legacy data (`apps/api/src/routers/archetypes.py:905-929`).                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Needs slice 2 and is not required for the first Finder UI.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

Therefore the code-only UI increment buildable against fixtures is: unchanged
no-floor Any plus, only after slice 1c, the eight archetype choices; a
selected-archetype-only B/A/S minimum-tier filter;
normalized ranked cards; selected and overall scores; mode-correct
confidence/completeness and primary/secondary labels; pagination/URL state; and
preserved selection, Inspect and map hand-offs. It stays hidden by default
pending the governed production sequence. Slice 1b adds the overall tier. C/D
remain outside the initial selected-mode product scope, but B/A/S do not become
safe merely by using higher predicates. Slice 1d is required before any Any-mode
tier control. Wired weights, per-archetype explanations, V3 reranking and
simulation are later increments.

## 5. UX design

### Picker

Use a labelled `<fieldset>` with a `<legend>` and nine native radio inputs. This
provides the radio-group role and checked state without recreating keyboard
semantics. Each radio's `<label>` contains only its short archetype name. Its
one-line description is a separate element with a stable id referenced by that
radio's `aria-describedby`; do not also nest the description in the label, which
would put the same text in both its accessible name and description. The first
option is labelled **Any** and its separate description is **Show the best overall
colony opportunities**.

The eight V3 choices are fixed by the current profile
(`apps/api/src/ranking/profile.py:35-50`). Their plain-language descriptions are
derived from the model’s economy ordinals and `_ANCHORS`
(`scripts/v3_system_archetype_model.py:1-4`,
`scripts/v3_system_archetype_model.py:22-33`):

| Key                  | Display name               | One-line description                                                  |
| -------------------- | -------------------------- | --------------------------------------------------------------------- |
| `paradise`           | Paradise World             | Agriculture and Tourism working together for a habitable destination. |
| `mining_hub`         | Mining Hub                 | Extraction and Refinery strength for a resource-processing centre.    |
| `manufacturing_hub`  | Manufacturing Hub          | Refinery and Industrial strength for sustained production.            |
| `megacomplex`        | Megacomplex                | A complete Extraction, Refinery and Industrial chain.                 |
| `research_hub`       | Research Hub               | High Tech potential supported by Industrial capacity.                 |
| `stronghold`         | Stronghold                 | Military and Industrial strength for a defended base.                 |
| `population_capital` | Population Capital         | Agriculture and High Tech supporting a large population centre.       |
| `flexible`           | Flexible Multi-Role Colony | Several viable economies rather than one narrow specialism.           |

In selected-archetype mode, the minimum-tier control is a native `<select>`
labelled **Minimum tier**, with initial options B, A and S and B selected by
default. B maps to `min_score=60`, and uses a real tier threshold rather than the
selected endpoint's raw default 40
(`apps/api/src/ranking/profile.py:52-54`,
`apps/api/src/routers/archetypes.py:508-518`). It remains only a predicate; any
number of the roughly 198.5 million systems may score B or better. Slice 1c's
candidate and count bounds are therefore required before B, A or S selected mode
is enabled. C and D are omitted only to keep the first UI increment focused.
“Minimum” remains explicit so the control does not imply a non-contiguous
multi-select.

Any mode does not render this control and sends no `min_development_score`,
preserving the current request body's no-floor behavior
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-139`,
`apps/api/src/models.py:551-555`). A nonzero Any floor filters
`best_colony_potential` while the indexed result order is `weighted_potential`,
and its 10,000-row count stop applies after filtering, so a sparse floor can
still inspect most of the generation
(`apps/api/src/ranking/ranking_sql.py:315-357`,
`apps/api/src/ranking/ranking_sql.py:451-462`,
`apps/api/src/ranking/ranking_sql.py:551-565`). Slice 1d must provide the bounded
Any access/count path before this control is shown there.

When the user chooses an archetype while a known-star anchor is active, F4b must
not pretend the archetype results are centred on that star. The initial design
switches the result heading to **Galaxy-wide [Archetype] ranking**, keeps the
committed anchor separately from the mutable combobox draft, and displays:
“Archetype ranking is galaxy-wide today; choose Any to search around [star].”
Typing changes only the draft text and suggestions; it does not clear or replace
the committed anchor. Only choosing a suggestion or using an explicit anchor
reset changes the committed anchor and resets the offset. Returning to Any
therefore restores the committed anchored query even if the draft was edited
while archetype mode was active. This separation is required because the current
single `anchor` is cleared on every input edit
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:401-410`,
`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:429-434`). This
behaviour is removable when the API accepts a picked archetype and arbitrary
reference coordinates.

### Result row/card anatomy

Each result remains one native `<li>` containing the existing selection button,
Inspect link and actions. Inside the selection button, render items 1–5 in this
order; keep item 6 after the button as it is today:

1. System name and id64.
2. **Best Colony Potential: _N_**. Append **· _tier_ tier** only when the API
   supplies summary `best_tier` (slice 1b). This is the headline overall value;
   never reuse the selected-fit tier or calculate an API-owned tier locally.
3. In selected mode only: **[Selected archetype] fit: _N_ · _tier_ tier** so a
   user can see when the chosen fit differs from the system’s overall best.
4. **Primary:** label; **Secondary:** label or “No clear secondary fit”.
5. Evidence badge, followed by existing distance/star/catalogue facts that are
   available on that response shape.
6. Existing Inspect and shortlist actions, unchanged.

If an optional value is `null` or absent, omit that datum or say “Unknown”.
A finite zero is a measured fact and is rendered as such — the anchor system's
own distance is `0.00 LY`, not “Unknown” — exactly as the live row already
renders every non-null distance. Only null/absent means unknown under the
product truth contract
(`docs/colonisation-redesign/spatial-platform-product-contract.md:82-98`).

### Tier semantics and colours

The tier label always includes text—for example, **“Tier S”**—so colour is not
the only distinction. The thresholds remain API-owned: S ≥ 88, A ≥ 76, B ≥ 60,
C ≥ 45, otherwise D (`apps/api/src/ranking/profile.py:52-54`).

Existing global tokens live in `apps/web/src/app.css`: void/panel/signal/cyan at
lines 3–9 and line/muted/raised-panel/metal at lines 10–19. There are no semantic
tier tokens today. Add these semantic tokens under `:root`, then verify contrast
against the raised panel:

| Tier | Proposed token   | Intended colour                          |
| ---- | ---------------- | ---------------------------------------- |
| S    | `--color-tier-s` | bright orange, based on `--color-signal` |
| A    | `--color-tier-a` | cyan, based on `--color-cyan`            |
| B    | `--color-tier-b` | accessible green                         |
| C    | `--color-tier-c` | accessible amber                         |
| D    | `--color-tier-d` | muted neutral, based on `--muted`        |

The badge uses a visible border, tier letter and full accessible name. Do not
use star icons or colour alone to encode order. Preserve the existing global
focus ring (`apps/web/src/app.css:41-44`). Exact B/C hues are a visual-validation
decision, not a domain contract.

### Honest uncertainty

Display one badge derived only from the API's mode-specific `confidence` and
general `completeness` fields:

| Condition                 | Any wording                       | Selected-archetype wording   |
| ------------------------- | --------------------------------- | ---------------------------- |
| either value missing      | **Evidence confidence unknown**   | **Fit confidence unknown**   |
| either value below 0.50   | **Evidence confidence: limited**  | **Fit confidence: limited**  |
| both values at least 0.80 | **Evidence confidence: strong**   | **Fit confidence: strong**   |
| otherwise                 | **Evidence confidence: moderate** | **Fit confidence: moderate** |

The accessible description gives both raw percentages. Any says “Evidence
confidence 82%; evidence 64% complete”; selected mode says “Fit confidence 82%;
evidence 64% complete.” The word **fit** is forbidden in Any-mode visible and
accessible text because no archetype was picked
(`apps/api/src/ranking/ranking_sql.py:87-103`). The thresholds above are a
presentation decision and must be unit tested; they do not alter ranking.
`archetype_confidence` has a
different meaning—the separation between the primary and secondary
classification—and may be shown separately as **Clear primary fit** or **Close
alternative**, but must not be folded into the evidence badge
(`apps/api/src/routers/archetypes.py:433-459`).

### Loading, empty and error states

Above the selected-ranking list, show **Showing _COUNT_ of _TOTAL_ within
candidate window (results _START_–_END_)** from the same response page. Slice 1c
first takes the raw-score candidate window, then applies non-indexed filters and
counts their survivors inside it. Its normalized envelope carries
`navigation_limit: 10000`, `navigable_total`, `page_size`, `count`, `total`,
`offset` and API-owned `is_truncated`. Selected-mode `navigable_total` equals the
exact post-filter `total` within the candidate window and ranges from 0 through
10,000. `is_truncated=true` independently means that the index probe found a
10,001st row before non-indexed filters were applied. In that case also show
**filters applied within the top 10,000 by _[Archetype]_ score**. A response such
as `total=3, is_truncated=true` is valid. Provide Previous/Next only across the
filtered rows inside that window; never imply that they cover a broader filtered
search outside it.

**One navigation ceiling for every mode, applied from the URL alone before the
first request.** The local-search count builder passes a cap only for
`galaxy_wide`; an anchored search, whose default distance is 500 LY, receives no
count cap and may return an exact `total` above 10,000
(`apps/api/src/local_search.py:248-254`,
`apps/api/src/local_search.py:918-923`). F4 nevertheless does **not** let any
mode navigate past 10,000: the anchor is not part of the URL contract (see
section 6), so after a reload or from a copied link an anchored search is
indistinguishable from an unanchored one, and a mode-dependent ceiling could not
be restored honestly. Therefore, for selected mode and for Any alike: set
`navigation_limit: 10000`, require `offset < 10000`, cap the wire page at
`min(page_size, 10000 - offset)`, and canonicalize a URL whose offset is at or
beyond that boundary to the last valid page **before** the first request is
issued, without waiting for any response. A freshly loaded shared URL such as
`/explore?offset=2000000000` therefore never reaches the API with that offset:
the request model accepts `from` up to 2,147,483,647 and `local_db_search_v3`
forwards page `LIMIT`/`OFFSET` to SQL independently of its capped count, so a
response-driven clamp would let the first request scan the ranking index
(`apps/api/src/local_search.py:902-923`,
`apps/api/src/ranking/ranking_sql.py:479-506`). Normalize Any responses
separately: `navigable_total` is `min(total, 10000)`, and the Any truncation
state is the existing `total_is_capped === true` rather than selected mode's
differently defined `is_truncated`. An anchored exact `total` above 10,000 is
still **displayed** exactly (“12,345 matches; navigation is limited to the
first 10,000 results”); only navigation is bounded. When `total_is_capped=true`,
show **10,000+ matches; navigation is limited to the first 10,000 results.** Do
not infer a cap from the number 10,000
(`apps/api/src/local_search.py:965-970`, `apps/api/src/models.py:408-412`).

The URL codec, facade request size, Next availability, visible range, DOM list
and Finder contribution all derive from that one normalized envelope. A page
change updates them together, as required by the spatial product contract
(`docs/colonisation-redesign/spatial-platform-product-contract.md:102-110`).

- Loading: retain `aria-busy` on the result region and a `role="status"` message,
  naming the active mode: “Ranking systems for Manufacturing Hub…” Existing
  result loading already uses those semantics
  (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:743-763`).
- Out-of-range page: when a response has `total > 0` and `offset >= total`, or a
  saturated unanchored Any page would cross 10,000, do not render the empty
  state. Clamp to the last valid page, derive the destination from reactive
  `page.url`, then call `goto(destination, { replaceState: true })` from
  `$app/navigation`; never call native `history.replaceState`. Request that page
  and show a one-line polite `role="status"` notice: **Page reset to the last
  available results.** This keeps `page.url` hydration and Back/Forward aligned
  (`apps/web/src/lib/components/AppShell.svelte:2-3`,
  `apps/web/src/lib/components/AppShell.svelte:54-58`).
- Empty: `total === 0` is a no-match state, but its copy depends on
  `is_truncated`. With `is_truncated=false` it is a genuine no-match: “No systems
  meet minimum tier B for Manufacturing Hub.” With `is_truncated=true` the
  bounded window had candidates and every one was removed by a non-indexed
  filter, while lower-scoring systems outside the window might match, so the
  copy is window-qualified: “None of the top 10,000 systems by Manufacturing Hub
  score match these filters.” — never “no systems meet the criteria”. Both
  include **Reset to tier B** (when the active floor is A/S) and **Choose Any**
  actions; the truncated form also offers **Clear filters**. Empty is not an
  error; do not offer gated C/D as an escape hatch.
- Error: HTTP 503 is a first-class **Ranking temporarily unavailable** state with
  `role="alert"`: “Archetype rankings are temporarily unavailable. Try again
  shortly.” If an optional additive slice-1 API reason such as
  `finder_products_not_ready` is present, instead show **Ranking data not ready**:
  “Archetype rankings are unavailable until Finder ranking data is published.”
  Status or free-form detail must never select that readiness copy. Both states
  offer Retry and Choose Any, retain the current selection/map, and never say
  “no matches.” Other errors use the same retained-state retry pattern. Existing
  error state already has an alert and retry pattern
  (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:764-780`).
- Stale transition: keep previous rows visibly marked “Updating…” while the new
  query is in flight; never relabel old rows as the newly selected archetype.

### Keyboard and screen readers

The native radio group supports Tab into the group and arrow-key choice; the
native select supports ordinary platform keyboard behaviour. On a committed
choice, keep focus on the changed control and announce the loading/result count
through a polite `role="status"` live region. Do not move focus to the first row
for a picker-only rerank or page change. F4b replaces the current
`${anchor.id64}:${results.dataUpdatedAt}` freshness key
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:389-399`) with a
dedicated anchor-selection revision. Autofocus runs only after an explicit new
anchor is chosen in Any mode; result freshness never steals focus.

Keep the result `<ul>/<li>` structure, the selection button’s `aria-pressed`, and
Enter/Space behaviour
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:475-482`,
`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:782-828`). Svelte owns
all controls, focus, keyboard and screen-reader text; Babylon owns spatial
presentation only
(`docs/colonisation-redesign/spatial-platform-architecture-decision.md:50-58`,
`docs/colonisation-redesign/spatial-platform-product-contract.md:238-244`).

### Inspect, map and later weight pop-out

Selection continues to update the current persisted selected-system id and the
renderer-neutral scene, and every committed result or system-map pick also
serializes the lossless id as `selected=<id64>` in the shared Explore URL while
preserving ranking and unrelated parameters. **Choosing a known-star anchor is
a selection commit too:** the live `chooseSuggestion` handler sets the anchor as
`selectedSystem` (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:401-411`),
and because an anchor change resets the offset through SvelteKit navigation,
that same navigation must carry `selected=<anchor id64>` — otherwise the
hydration rule (absent `selected` clears URL-owned selection) would discard the
anchor the user just chose and break the existing Product E2E assertion that
the anchor is pressed and present in the selected-system context. One `goto`
writes the offset reset and the selection together. Because the anchor itself
is not URL state (section 6), **no history entry may exist whose query cannot
be restored**: every navigation that depends on the committed anchor stores
`{ anchor: { id64, name, x, y, z } | null }` in SvelteKit history state
(`goto(url, { state })`) — the coordinates included, because the live request
derivation enters the anchored 500-LY branch only when `anchor.x/y/z` are
numeric and otherwise issues a galaxy-wide search, so an id-only payload would
display the restored anchor while querying the wrong result set; a restored
payload with non-finite coordinates is treated as no anchor and the URL is
canonicalized accordingly. Hydration reads `page.state.anchor` before falling
back to “no anchor”, and Back/Forward therefore restore offset, selection
**and** the anchor that produced the page together. A fresh load or copied
link carries no state and hydrates as unanchored, which is exactly what its URL
says. A test drives anchor A → anchor B → Back and asserts the 500-LY request
for A's coordinates
is re-issued for anchor A with its offset and selection. It does not open detail. The
existing `system=<id64>` remains exclusively the explicit Explore
`SystemOverlay`/Inspect trigger: the parameters may coexist, closing the overlay
removes only `system`, and clearing selection removes only `selected`. The current
handlers write only `selectedSystem`
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:468-473`,
`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:505-516`), while
`AppShell` currently makes `system` both store input and overlay id
(`apps/web/src/lib/components/AppShell.svelte:19-43`,
`apps/web/src/lib/components/AppShell.svelte:76`); F4 decouples those paths and
centralizes selection commits so the store, URL, scene and Inspect hand-off
cannot diverge. Inspect remains `/inspect?system={id64}`. No ranking field enters
a Babylon contract. This preserves the north star that the map is the constant and
information changes around it
(`docs/colonisation-redesign/spatial-platform-product-contract.md:10-26`) and the
existing synchronized result/map hand-off
(`docs/colonisation-redesign/spatial-platform-product-contract.md:102-110`).

A rerank or page change may omit the selected system. Before replacing the
result contribution, F4b retains its last known point in a separate deduplicated
Finder-selection contribution until selection changes or clears. The DOM list
still shows only the current page. This guarantees the selected/highlighted
target required by the product contract: the scene may name a selected id that
is absent from new result points today, and Babylon otherwise drops its marker
(`apps/web/src/lib/spatial/explore-scene.ts:92-115`,
`apps/web/src/lib/spatial/babylon/adapter.ts:1432-1438`,
`apps/web/src/lib/spatial/babylon/adapter.ts:2032-2040`).

That point must also survive a hard reload of a shared `selected=` URL in a clean
session without opening `SystemOverlay` or relying on browser storage. The
selected-system store persists only the id64
(`apps/web/src/lib/persistence/stores.ts:107-112`), so F4b chooses API
reconstruction rather than a new persisted point snapshot. After selection and
URL hydration, when the selected id64 is absent from the current result page,
resolve it through the existing facade `getSystem` call
(`apps/web/src/lib/api/client.ts:554-566`) to the supported exact-system
`GET /api/system/{id64}` route
(`apps/api/src/routers/systems.py:38-100`). Its response provides `id64`, `name`,
`x`, `y` and `z` (`apps/api/src/models.py:281-295`). Emit the separate
Finder-selection contribution only after the response id matches the current
selection and all three coordinates are finite; deduplicate it against the
current page and ignore or cancel a stale response when selection changes.
While resolution is pending, or on 404/error/non-finite coordinates, retain the
selection and Inspect hand-off but emit no guessed or origin-defaulted point.

Reserve an end-aligned `ranking-tools` slot beside the picker in the responsive
layout, but render no dead slider controls in the first increment. This preserves
the F2 design's F4 pop-out-slider slot without depending on an endpoint that has
not been cut over (`docs/superpowers/specs/2026-09-16-v3-finder-f2-archetype-ranking-design.md:150-155`).
After slice 2, the slot gets a **Tune ranking** disclosure button with
`aria-expanded` and `aria-controls`. It opens a non-modal labelled
`role="region"` pop-out containing native range inputs, visible numeric values,
Reset, Cancel and Apply. Escape closes it and returns focus to the button; Apply
issues one rerank and commits one URL history entry. **Unverified:** slider names,
ranges, defaults and normalization must come from the future V3 `/rerank`
contract, not the legacy five-weight model.

## 6. State and URL contract

Create a pure, immutable `FinderRankingState` owned by the Explore feature:

```ts
type FinderRankingState = Readonly<{
  archetype: "any" | ArchetypeKey;
  minimumTier: "S" | "A" | "B" | null; // null is mandatory in Any until slice 1d
  pageSize: number; // facade page_size, integer 1..50; default 50
  offset: number;
  weights: Readonly<Record<string, number>>; // empty until slice 2
}>;
```

The normalizer enforces the cross-field invariant: `archetype: "any"` always
has `minimumTier: null`; a selected archetype defaults the field to B. It is not
valid for an Any state to retain a hidden tier floor.

Normalization also preserves semantic identity instead of flattening unlike
facts:

```ts
type DistanceReference = Readonly<{
  kind: "anchor" | "sol";
  id64: Id64;
  name: string;
}>;

type RankingProvenance = Readonly<{
  ranking_version: string;
  ranking_sha256: string;
  derived_generation_id: string;
  publication_sequence: number;
}>;

type RankingIdentityFields = Readonly<{
  ranking_score: number | null;
  // "unknown" is the decoder's result for a pre-F4 snapshot that carries only the
  // ambiguous generic `archetype_score`; it is never produced for a new save and
  // is excluded from every mode-specific comparison.
  score_kind: "overall_potential" | "selected_fit" | "unknown";
  selected_archetype: ArchetypeKey | null;
  distance_reference: DistanceReference | null;
  ranking_provenance: RankingProvenance | null;
}>;
```

`ranking_provenance` is copied from the response envelope that produced the row
(both the local search and the rankings responses carry `ranking_version`,
`ranking_sha256`, the generation id and the publication sequence for
reproducibility). It is persisted with every pin/compare snapshot. Slice 1c
already moves the profile from `v1` to `v2`, and the F2d capacity design
changes the ranking identity again, so two saved selected-fit scores with the
same archetype can have been computed under different semantics; the
provenance is what tells them apart.

Selected rankings carry their `score` as `ranking_score` with
`score_kind: 'selected_fit'`, their exact selected archetype, and Sol
(`id64=10477373803`) as distance reference
(`apps/api/src/helpers.py:16`); anchored Any rows
carry their overall score as `ranking_score` with
`score_kind: 'overall_potential'` and the chosen star reference. A
galaxy-wide Any row with no measured distance has a null reference. These fields,
plus `overall_development_potential`, are retained in pin/compare snapshots.
Never store a selected fit in generic `archetype_score`. Current code otherwise
collapses `archetype_score ?? overall_development_potential` into that generic
field and labels it “Development score,” which would make a normalized selected
fit equally ambiguous
(`apps/web/src/lib/features/explore/shortlist.ts:14-20`,
`apps/web/src/lib/features/explore/compare-metrics.ts:134-170`).

The URL is the source of truth for shareable ranking state:

| State              | Canonical query form                                     | Rules                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Any archetype      | omit `archetype`                                         | Default. `archetype=any` canonicalizes to omission.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Selected archetype | `archetype=manufacturing_hub`                            | Accept only the eight current keys. Unknown values fail closed to Any and show a non-blocking “unsupported link option” status.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Minimum tier       | `min-tier=A`                                             | Selected-archetype-only. Omit B, the selected-mode default, and map S/A/B to 88/76/60. When `archetype` is absent/Any, ignore and remove `min-tier`, normalize `minimumTier` to null and send no `min_development_score`. Treat C/D as unsupported initial-product options; do not accept or emit either value. Every selected value still depends on slice 1c; Any tier filtering depends on slice 1d.                                                                                                                                                                                                                                                                                                                                                                              |
| Page size          | `page_size=1`                                            | Omit 50, the facade default. Accept exactly one integer from 1 through 50; reject duplicates, fractions and out-of-range values. Map this facade/URL field to the rankings endpoint's existing wire `limit`, whose current API contract is default 50 and range 1–500 (`apps/api/src/routers/archetypes.py:517-518`). F4 intentionally exposes the narrower bound. Include it in the query key and reset offset when it changes.                                                                                                                                                                                                                                                                                                                                                                                           |
| Page offset        | `offset=50`                                              | Omit zero. Accept one non-negative integer; reject duplicates, fractions and negatives. In **every** mode — decided from the URL alone, before any request — reject `offset >= 10,000`, canonicalize such a URL to the last valid page before the first dispatch, and send at most `min(page_size, 10,000 - offset)`; this never waits for `total_is_capped` or any other response metadata, and no mode may navigate beyond 10,000 (the anchor is not URL state, so an anchored search cannot be told apart from an unanchored one after a reload). Previous/Next stop at the envelope's `navigable_total` (= `min(total, 10,000)`). Reset to zero when archetype, minimum tier, page size or the **committed** anchor changes; draft text edits do not reset it. Positive out-of-range corrections use SvelteKit `goto(..., { replaceState: true })`, never native History API. |
| Future weights     | repeated, key-sorted `weight=<dimension>:<basis-points>` | Example only: `weight=capacity:2500`. Values are integers 0–10000 to avoid float serialization drift. Do not parse or emit until slice 2 defines allowed keys and total rules. **Unverified:** dimension identifiers.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Selected system    | `selected=<id64>`                                        | Passive Explore selection only. Result selection and a Babylon system pick write the lossless id here and hydrate the persisted selection plus Babylon marker without opening detail. Clearing selection removes only `selected`; omission on `/explore` clears URL-owned selection. |
| Detail overlay     | existing `system=<id64>`                                 | **In F4-enabled builds** exclusively opens `SystemOverlay` on `/explore` and remains the Inspect trigger (`apps/web/src/lib/components/AppShell.svelte:19-33`, `apps/web/src/lib/components/AppShell.svelte:76`); closing the overlay removes only `system`, and it never clears or creates `selected`. **In the default-off build** the live behaviour is unchanged: `AppShell` keeps copying `?system=` into `selectedSystem` exactly as today, and a disabled-build `?system=` regression test proves it. |

Serialize keys in the table's order and weights lexicographically so copying the
same state produces one stable URL. Picker and minimum-tier commits create a
history entry; offset navigation creates one entry; Reset creates one history
entry; selection commits create one entry with `selected=<id64>`; future slider
edits remain local draft state until Apply. Preserve
unrelated query parameters. A response-driven out-of-range correction is not a
user navigation: compute the last valid offset, derive the destination from
reactive `page.url`, use `goto(destination, { replaceState: true })` from
`$app/navigation`, refetch that page, and show the one-line page-reset notice.
Native `history.replaceState` is forbidden. The facade returns
`page_size`, page `count`, raw response `total`, `navigable_total`, request
`offset`, a conditional `navigation_limit`, and source-owned truncation
metadata rather than a bare result array. For selected rankings,
`is_truncated=true` means the bounded raw-score probe observed a 10,001st row;
`total` and `navigable_total` both count only filtered survivors among the first
10,000. For Any, `navigable_total` is `min(total, 10000)` and
`total_is_capped` remains the distinct truncation flag; an anchored exact total
above 10,000 is displayed exactly but, like every mode, navigates only within
`navigation_limit: 10000`, with offset plus page size clamped to that cap before
dispatch.
Navigation, Next, count and truncation copy
must never be computed independently of that envelope.

URL hydration is reactive to SvelteKit's `page.url`, not a one-time `onMount` or
`location` snapshot. On initial load and after every SvelteKit navigation or
browser popstate, parse and canonicalize archetype, selected-only tier, page
size, offset and `selected` together; atomically update committed controls,
selection and the query key so the correct local-search or rankings request and
page refetch. `AppShell` already demonstrates a reactive `page.url` derivation
for non-null selections (`apps/web/src/lib/components/AppShell.svelte:19-47`),
but F4 also defines omission on `/explore`: an Explore history entry without
`selected` clears the URL-owned selection rather than leaving the persisted value
active. `system` independently controls only the detail overlay/Inspect trigger;
closing it leaves `selected` and the marker intact. Other routes retain their
existing detail contract. Hydration never
pushes another history entry and URL-writing effects must not loop. User
picker, pagination and selection commits push; canonicalization and
response-driven page correction replace.

When `VITE_FINDER_F4_ENABLED !== '1'`, the hydrator does not parse or apply the
F4 parameters at all. It removes `archetype`, `min-tier`, `page_size`, `offset`
and `weight` with SvelteKit replace-state, leaves `selected`, `system` and
unrelated parameters intact, and retains the unchanged local-search request
branch described above.

The initial archetype mode is intentionally galaxy-wide. The current anchor is
not added to this new contract because its exact shared reconstruction and its
combination with selected-archetype ranking are not supported by the slice-1 API.
**Unverified:** a future unified request may add `near=<id64>` after a V3 exact
system lookup and arbitrary-reference archetype ranking exist.

Do not persist ranking state or a selected-point snapshot separately in local
storage: the URL is sufficient for ranking state and the existing validated
store continues to persist only the selected id64
(`apps/web/src/lib/persistence/stores.ts:107-112`). Reconstruct an omitted
selected point after hydration through `getSystem` and
`GET /api/system/{id64}`, as specified above; only a matching response with
finite coordinates may contribute a point. If the owner later chooses to
remember Finder defaults across sessions, add a named key, versioned codec and
context-provided store following the central pattern
(`apps/web/src/lib/persistence/storage.ts:84-110`,
`apps/web/src/lib/persistence/context.ts:7-20`); never access `localStorage`
directly from the component.

Comparison is mode-aware and provenance-aware. **Best Colony Potential** is
comparable across modes (its overall value is persisted separately) but only
between entries whose `ranking_provenance.ranking_version` and
`ranking_sha256` are equal; the archetype product that produces it is pinned to
the same ranking identity, and the design already anticipates another identity
change, so overall values from before and after a change are not ranked
against each other — they are omitted with the same “different ranking
versions” note. A selected-fit row is
shown or ranked only when every compared entry has `score_kind: 'selected_fit'`
for the same `selected_archetype` **and** an equal `ranking_provenance`
(`ranking_version` and `ranking_sha256` must match; the generation id and
publication sequence are shown as “ranked on generation …” but do not block
the comparison, because a data refresh changes freshness, not semantics);
otherwise it is omitted with a “different ranking modes” or “different
ranking versions” note. A snapshot without `ranking_provenance` (saved before
F4a) never enters any score comparison, selected or overall; it is still
listed with its stored values and an “older save” note. Distance is compared only when every entry has the same
`distance_reference.kind` and id64, labelled **Distance from Sol** or
**Distance from _name_**. Mixed-reference distances are excluded rather than
silently compared. For referenced snapshots, every finite measured distance is
valid, including `0`; the reference metadata, not a positive-value test, proves
the measurement. A legacy snapshot without `distance_reference` is unknown and
excluded even if it stores zero (or another finite distance). The current
positive-only sentinel is at
`apps/web/src/lib/features/explore/compare-metrics.ts:164-167`.

## 7. Validation plan

### Slice 1c API and representative-scale proof

Unit and disposable-PostgreSQL integration tests must prove that selected mode
uses the index-first raw-score candidate window, reranks only inside it, applies
every non-indexed filter only after the window is fixed, counts filtered
survivors only within that window, and derives `is_truncated` only from the
10,001st raw/index-eligible sentinel. Tests must include a selective-filter case
where `total < 10,000` while `is_truncated=true`. The ordinary integration vehicle
is the disposable PostgreSQL 18 `database` fixture in
`tests/test_archetype_rankings_v3.py`, built through
`tests.ratings_v4_pg_fixture.canonical_database`
(`tests/test_archetype_rankings_v3.py:1-7`,
`tests/test_archetype_rankings_v3.py:48-59`).

Before F4b is enabled even in Product E2E, slice 1c must also publish a
representative-scale timing receipt from that disposable PostgreSQL 18 service.
The concrete service is `localtest-pg` / container `edfinder-localtest-pg18`,
pinned to `postgres:18` (`docker-compose.localtest.yml:11-20`), and
`canonical_database` creates and force-drops a random database while refusing a
non-local validation target (`tests/ratings_v4_pg_fixture.py:10-44`).
Seed at least 1,000,000 systems into production-shaped scratch relations for
`system_search` and the **wide-row** `system_archetype` (F2d; the summary is a
view over it), expose them through the generation-pinned `v3_app` views, and
retain the real primary, spatial/region, per-key partial raw-score and
weighted-potential indexes exactly as the final `011` text defines them
(`sql/v3/migrations/004_v3_search_spatial_clusters.sql:22-54`,
`sql/v3/migrations/010_v3_system_search_body_type_counts.sql:17-35`,
`sql/v3/migrations/011_v3_system_archetype.sql:7-56`,
`sql/v3/migrations/011_v3_system_archetype.sql:132-139`). The seed must
**saturate the candidate window**: for the archetype and B floor under test, at
least 10,001 index-eligible rows (assert the count), so the offset-9950 page is
populated and the 10,001st-row sentinel is actually observed; a corpus of
mostly ineligible rows would pass every latency budget without exercising the
bounded path that motivated slice 1c. After loading and index creation and
before the warm or cold runs, run `ANALYZE` on all three underlying relations,
as the derived-data decision requires before any validation benchmark
(`docs/development/v3-search-spatial-derived-data-decision.md:350-364`);
freshly bulk-loaded relations otherwise plan from absent or stale statistics
and the recorded join order would not be the production-shaped plan. Execute the actual
page SQL and companion count SQL returned, with bound parameters, by
`build_ranked_query` and `build_count_query`
(`apps/api/src/ranking/ranking_sql.py:392-509`,
`apps/api/src/ranking/ranking_sql.py:512-574`). Record
`EXPLAIN (ANALYZE, BUFFERS)` plus wall-clock timings for the first page, a
near-ceiling page and the post-filter within-window count. The plan must
demonstrate that the raw-score index probe stops after at most 10,001 rows before
any non-indexed predicate, and that the real joins, filtering, modifier sorting
and counting touch at most the first 10,000. Include selective
region/distance/body-count cases so stable latency under warm and cold fixture
runs proves that filter selectivity cannot reopen a population scan. A
hand-written query or an EXPLAIN against one flattened scratch table does not
exercise view expansion, join order or the real indexes and **does not unblock
F4b**. This is representative-scale evidence, not a claim of full
198.5-million-row parity; failure to obtain it blocks F4b rather than weakening
the contract.

The receipt passes only if it also meets explicit latency budgets; stable but
slow timings fail. Proposed budgets for the 1,000,000-row PostgreSQL 18 fixture
(owner question 5 confirms or adjusts them; they are recorded in the receipt
and the Cypress/integration test that reads it):

| Query (selected mode, tier floor B, galaxy-wide) | Warm (median of 5 runs) | Cold (first run after `pg_ctl restart`) |
|---|---:|---:|
| first page (`offset=0`, `page_size=50`) | ≤ 300 ms | ≤ 1,500 ms |
| near-ceiling page (`offset=9950`, `page_size=50`) | ≤ 600 ms | ≤ 2,500 ms |
| post-filter within-window count | ≤ 600 ms | ≤ 2,500 ms |
| the same three with a selective region/distance/body-count filter | same budgets | same budgets |

Each timing is the server-side **statement wall time — planning plus
execution — as reported by `EXPLAIN (ANALYZE, BUFFERS)`** (the two figures are
recorded separately for diagnosis but the budget applies to their sum; the
builder-produced view/join SQL can spend real time in planning on a cold
connection, and users pay that latency on uncached statements). Not browser
round trip. Exceeding any budget blocks the
receipt and therefore F4b; the budgets may only be raised by an owner decision
recorded in this document, never by the implementing PR.

### Slice 1d future Any-tier proof

Before a later PR renders Minimum tier in Any, its disposable PostgreSQL 18
integration and scale receipt must prove a hard upper bound on work for both the
builder-produced page and count queries at S/A/B floors, including a sparse
qualifying set. The plan must show the chosen `best_colony_potential` index,
candidate window or explicit work cap prevents a scan across most of the seeded
generation, and the response must expose truthful count/truncation semantics.
Reuse the production-shaped three-relation/view/index fixture above; a unit test
that merely finds `LIMIT 10000`, or a flattened-table EXPLAIN, is not evidence of
an inspected-row bound. This proof gates only future Any-tier filtering, not the
selected-only F4b surface.

### Unit tests (Vitest)

Vitest is the app’s unit runner (`apps/web/package.json:18-20`). Add pure tests
for:

- the exact eight-key metadata inventory and label lookup;
- selected-mode tier-to-minimum-score mapping at 88/76/60, B as that mode's
  default, fail-closed C/D parsing, and Any canonicalization to null/no
  `min_development_score` while displayed result tiers remain the API's value;
- mode-specific confidence/completeness wording at missing, 0.50 and 0.80
  boundaries, including that Any-mode output never contains “fit”;
- URL parse/serialize round trips, canonical ordering, defaults, duplicate and
  unknown parameters, `page_size` default 50 and inclusive 1–50 bounds, the
  mode-independent exclusive 10,000 offset ceiling and request-size clamp
  applied before dispatch (including `offset=2000000000` on a fresh load),
  anchored Any exact totals above 10,000 displayed exactly but not navigable,
  `total_is_capped` → truncation copy only, URL correction, the raw-window
  10,001 sentinel, post-filter within-window total and independent truncation
  rules, offset/reset rules, last-valid-page calculation, Any-mode removal of
  `min-tier`, and preservation of independent `selected`/`system` plus unrelated
  parameters;
- request selection: Any → unchanged local search with no tier field, key →
  rankings, selected default B → score 60, and facade `page_size=1` → wire
  `limit=1`;
- ranking-row normalization preserving `score_kind`, selected archetype,
  overall potential, `distance_reference`, `ranking_provenance` copied from the
  response envelope onto every row (both the local-search and rankings
  shapes), page metadata, absent `best_tier` and lossless id64 handling;
- snapshot creation (`snapshotFromExplore`) carrying `ranking_provenance` from
  the `ExploreSystem` row into the persisted snapshot, and a legacy snapshot
  without it normalizing to `ranking_provenance: null`;
- persistence backward compatibility plus mode-aware scores, same-reference
  distance comparison accepting finite zero, and exclusion of legacy snapshots
  without a reference;
- default-off feature config and explicit fixture opt-in; the disabled request
  selector must make the rankings branch unreachable for a hand-authored F4 URL;
- future weight basis-point parsing behind a disabled feature flag, activated
  only with the slice-2 contract.

### Svelte component tests

Use Testing Library Svelte, which is installed in the current stack
(`apps/web/package.json:36-37`). Test:

- accessible picker name, nine radios whose accessible names are only their
  short archetype names, separately referenced descriptions announced once,
  checked state and native keyboard progression;
- minimum-tier label and request update in selected mode, and its absence in Any;
- result headline, selected fit, tier, primary/secondary and all four evidence
  wordings;
- headline tier omitted without API `best_tier` and rendered only when supplied;
- page count/range and offset navigation keep `page_size`, post-filter
  within-window total, the **filters applied within the top 10,000 by
  [Archetype] score** message, Next
  state, DOM and map synchronized; cover `total < 10,000` with
  `is_truncated=true`; a three-row fixture envelope at `page_size=1` has three
  real pages and two enabled Next transitions; also cover anchored Any with an
  exact total above 10,000 (exact count shown, Next disabled at 10,000) and
  galaxy-wide Any with `total_is_capped=true`;
- a stale/shared `offset=9950` response with `total=3` calls mocked SvelteKit
  `goto` with `replaceState: true` for the last valid page at `offset=0`, refetches
  exactly once without a hydration loop, shows the page-reset notice and never
  flashes the no-match state; a saturated unanchored Any page crossing 10,000
  uses the same correction, while `total=0` alone renders the genuine empty state;
- loading `status`, genuine-empty actions, generic 503 **Ranking temporarily
  unavailable**, readiness-reason **Ranking data not ready**, and Retry;
- focus remains on the picker during rerank/page changes, while choosing a new
  Any-mode anchor focuses the first completed result once;
- commit an anchor, switch to an archetype, edit the combobox draft without
  choosing a suggestion, then return to Any and prove the original committed
  coordinates are restored; only a suggestion commit or explicit reset may
  replace/clear the committed anchor and reset offset;
- selected row and Inspect href remain unchanged;
- rerank omission retains the selected system point and Babylon marker;
- hydration resolves a selected id64 omitted from the current page through
  `GET /api/system/{id64}`, emits one point only after validated coordinates,
  and ignores stale, missing or invalid responses;
- result and Babylon-map selection serialize `selected=<id64>` without losing
  ranking, `system` or unrelated parameters; reactive SvelteKit URL hydration
  reparses ranking and selection on Back/Forward, clears URL-owned selection when
  `selected` disappears from Explore, and refetches the restored request/page
  without a loop; `selected` alone never mounts the overlay, and closing a
  coexisting `system` overlay leaves `selected` and its marker intact;
- with the feature flag disabled, loading
  `/explore?archetype=flexible&min-tier=A&page_size=1&offset=1` strips those F4
  parameters by replacement, issues exactly today's unanchored local-search body
  `{ galaxy_wide: true, sort_by: 'development', size: 24, from: 0 }`, never calls
  rankings and renders no ranking UI;
- the Any/anchor versus selected-archetype limitation message.

### Product Cypress E2E and fixture contract

Normal Finder/Inspect behaviour, accessibility and approved screenshots belong
to Product E2E/Visual Acceptance
(`docs/development/v3-browser-validation-lanes.md:29-49`), not Review Lab. Extend
`apps/web/cypress/e2e/product-journey.cy.ts`, which already exercises keyboard
anchor selection, result/map selection, axe, screenshot and Inspect hand-off
(`apps/web/cypress/e2e/product-journey.cy.ts:32-41`,
`apps/web/cypress/e2e/product-journey.cy.ts:105-235`).

Add a Product E2E journey that:

1. starts on Any, proves the existing `/api/local/search` journey sends no
   `min_development_score`, and shows no Minimum tier control;
2. chooses Flexible Multi-Role Colony with the keyboard;
3. proves the URL contains `archetype=flexible&page_size=1` and the real
   `/api/archetypes/rankings` request uses `min_score=60`, `limit=1` and offset 0;
4. asserts the committed fixture's within-window order is V3 Lossless Reach
   (100/S), Achenar (100/S), then HD 38179 (75/B), with selected score/tier,
   Best Colony Potential, evidence wording and primary/secondary text;
5. uses Next to traverse the three committed systems as three one-row pages
   (offsets 0, 1 and 2), selects a row, reranks/pages so the new page omits it,
   proves the copied URL contains `selected=<id64>` and no `system` trigger, and
   verifies its map marker plus Inspect URL remain without a modal; then clears
   localStorage and sessionStorage and loads that copied URL as a clean session
   with the selected row still absent, waits for the real
   `GET /api/system/{id64}` hydration request, and proves the validated selected
   marker/label appears exactly once while the DOM page still omits the row and
   the Inspect href remains `/inspect?system={id64}`; then runs axe;
6. uses Back/Forward across picker and pagination commits, asserting that
   archetype, tier, offset, selection, result/map envelope and the corresponding
   local-search/rankings request are restored and refetched from each URL; the
   select → rerank/page journey retains its marker from `selected`, while an
   explicit `system` overlay can open/close independently;
7. captures approved 1280×800 and 390×844 screenshots with animation disabled.

Only after slice 1c and its representative-scale proof have landed must the
protected Product E2E bundle contain the default-hidden F4 surface. In
`.github/workflows/cypress-parity.yml`, add step-local
`VITE_FINDER_F4_ENABLED: '1'` only to **Build Svelte static bundle**, immediately
around its current plain `pnpm build`
(`.github/workflows/cypress-parity.yml:191-193`). Do not set it at job scope, on
the preview step, or in a production/release build: those builds keep the
fail-closed default `0`. The production image currently passes only
`VITE_BUILD_SHA` into its bundle build (`apps/web/Dockerfile:4-5`,
`apps/web/Dockerfile:28`); F4b's validated Finder argument defaults to `0` and
does not change that release behavior. The Chrome/Firefox matrix then exercises
the opt-in bundle (`.github/workflows/cypress-parity.yml:21-30`). In the same F4b PR,
update the repository contracts that name or inspect this workflow and add a
fail-closed assertion that the `1` opt-in is confined to that build step:
`tests/test_browser_validation_lane_contract.py:7`,
`tests/test_ci_data_invariants.py:6`,
`tests/test_ci_dependency_contract.py:46`,
`tests/test_ci_stall_detection.py:49`,
`tests/test_e2e_harness_contract.py:40-46`,
`tests/test_v3_product_journey_contract.py:9-24`, and
`tests/test_v3_python_runtime_validation.py:78-108`.

Fixture identities are Achenar, V3 Lossless Reach and HD 38179 in Product E2E,
and Review Wiring, Review Aggregate and Review Fallback in Review Lab, as cited
in the fixture inventory above. Their exact expected tiers are not committed
today, although this review's direct fixture-model run established the Flexible
B journey and order above. Add a PostgreSQL fixture-output contract alongside
`tests/test_seed_cypress_v3_generation.py` that asserts all three systems’
primary/secondary, Best Colony Potential, every selected-archetype score/tier,
confidence and completeness. Only then copy the exact expected Flexible order
and tier values into Cypress. That makes a later model change an explicit
fixture-contract update rather than a silent screenshot change.

Keep the committed Product E2E corpus at exactly those three systems. The
fixture-output contract must first prove that the selected archetype/floor admits
all three; then `page_size=1` gives three deterministic pages through the real
endpoint. The rejected alternative is a larger synthetic Product corpus: it
would expand checksum-locked source/canonical data, derived-build time and
expected-output maintenance solely to force pagination when the existing
endpoint already has a bounded page-size control.

### Review Lab

Do not add a normal archetype-picker scenario. Review Lab owns synthetic
failure, empty, fault and containment states and explicitly does not own the
normal Explore → Inspect or visual-baseline journey
(`docs/development/v3-browser-validation-lanes.md:62-103`). Its current scenarios
are synthetic wiring, API failure, empty results and renderer recovery
(`scripts/dev/review_lab/scenarios.py:6-51`); they remain unchanged and green.

Because the lane contract assigns deliberate API failure and empty states to
Review Lab, F4b **adds two F4-enabled scenarios** there instead of leaving the
ranked empty/error UI to mocked component tests alone:

- `rankings_api_failure` — the review-only middleware in
  `apps/api/src/review_main.py` (today it intercepts only
  `POST /api/local/search`, `apps/api/src/review_main.py:129-158`) gains a mode
  that answers `GET /api/archetypes/rankings` with a tagged synthetic 503
  (`x-edfinder-review-failure: rankings-api-failure`). Browser flow
  `rankingsApiFailure`: open Explore with a selected archetype in the URL,
  observe **Ranking temporarily unavailable** in the result region's
  `role="alert"`, and prove the map/selection state survives: the flow first
  establishes `selected=<REVIEW_SYSTEM.id64>` in the URL and its marker, and
  asserts that exact selection and marker are still present after the failed
  rerank.
- `rankings_empty_results` — the same middleware answers the rankings request
  with a contract-shaped empty envelope (`results: []`, `total: 0`,
  `is_truncated: false`, the normal ranking identity fields). Browser flow
  `rankingsEmptyResults`: observe the ranked empty state copy, a zero-target
  Babylon scene, and that switching back to Any issues a normal search.

Both run against the F4-enabled bundle: the Review Lab browser runner builds
`apps/web` itself with environment overrides
(`scripts/dev/review_lab/browser_runner.py:164-172`), so F4b adds
`VITE_FINDER_F4_ENABLED: '1'` to that override set — the Review Lab bundle is a
disposable diagnostic build, never a release artifact, so this does not enable
F4 anywhere else. Three of the existing four scenarios keep their behaviour
under the enabled flag (Any mode with no archetype in the URL is the default
path). The `apiFailure` flow does **not**: today it seeds the selected id only
in `localStorage` and visits `/explore` without `selected=`
(`apps/web/cypress/e2e/review-lab.cy.ts:213-226`), and under the F4 URL
contract omission of `selected` on `/explore` clears URL-owned selection, so
its preservation assertion would fail. F4b therefore updates that flow (and
writes the new `rankingsApiFailure` flow the same way) to establish a
URL-owned selection first — visit `/explore?selected=<REVIEW_SYSTEM.id64>`, wait
for the marker/last-known point — then activate the failure mode, trigger the
failing request, and assert that **exactly that** `selected` value and its
marker survive. The “if any” wording above is replaced by this exact
assertion; a vacuous check is not evidence.
Cypress does not stub either response; the backend mode does. Do not duplicate
picker, axe or visual assertions there. The current wiring check only requires
Review Wiring and Babylon readiness
(`apps/web/cypress/e2e/review-lab.cy.ts:184-205`).

### Visual validation and OpenAPI drift

F4 changes visible layout, colour and components, so visual validation is
mandatory (`CLAUDE.md:202-206`). Approved baselines belong exclusively to the
Product lane; Review Lab screenshots are diagnostic
(`docs/development/v3-browser-validation-lanes.md:90-103`). Review desktop and
mobile states for Any, a selected archetype, long names, limited evidence,
loading, empty and error; verify focus, zoom and contrast manually in addition to
axe.

Slice 1c adds selected-ranking `is_truncated`, so its API-contract PR runs
`pnpm generate:api` (`apps/web/package.json:28`) and commits both generated-client
changes. F4a/F4b then consume that landed contract. Every PR still requires the
**OpenAPI types drift check**, which regenerates both checked-in clients from a
running disposable API and fails on a diff (`.github/workflows/ci.yml:437-528`).
Any later slice-2 model change follows the same API-contract-PR rule.

## 8. Implementation plan: small PRs

Every PR must satisfy acceptance against its exact latest head and disposition
all substantive reviewer findings; green CI alone is insufficient
(`docs/development/pull-request-acceptance-policy.md:1-45`).

These PRs are code-only and fixture-validated. None authorizes production
promotion. Three API dependencies remain explicit:

- **Slice 1b — summary best tier:** project `sum.best_tier`, add `best_tier` to
  both rankings and local-search response models/builders, regenerate clients,
  and test that it is summary-owned. F4a may land first and represents the
  headline as a number without a tier; the browser never derives it.
- **Slice 1c — bounded selected ranking:** this is a hard prerequisite for every
  selected-archetype mode, including B/60. Use the existing raw-score index to
  take the raw-score window before every non-indexed filter, apply those filters
  and the modifier only inside it, and make `is_truncated` report the raw-window
  10,001st sentinel independently of the post-filter within-window `total`.
  Validate its plan and timing at representative scale. The present raw-score
  index cannot satisfy the current cross-table ordering, and the endpoint calls
  an uncapped `COUNT(*)`
  (`sql/v3/migrations/011_v3_system_archetype.sql:45-50`,
  `apps/api/src/ranking/ranking_sql.py:451-462`,
  `apps/api/src/routers/archetypes.py:348-363`).
- **Slice 1d — bounded Any tier floor:** not required for no-floor Any or the
  selected-only F4b control. It is a hard prerequisite before Minimum tier is
  offered in Any. Add a measured index/candidate access path on
  `best_colony_potential`, or an explicit bounded count/candidate-work contract;
  the current `weighted_potential` ordering index and 10,000 qualifying-row
  count limit do not bound rows inspected
  (`apps/api/src/ranking/ranking_sql.py:315-357`,
  `apps/api/src/ranking/ranking_sql.py:451-462`,
  `apps/api/src/ranking/ranking_sql.py:512-565`,
  `sql/v3/migrations/011_v3_system_archetype.sql:52-56`).
- **Optional slice-1 readiness reason:** an additive stable machine-readable
  reason such as `finder_products_not_ready` may distinguish the product-readiness
  503 at `apps/api/src/local_search.py:620-642` from ordinary database 503s at
  `apps/api/src/routers/archetypes.py:376-387`. This is a copy nicety, not an
  F4a/F4b prerequisite; without it the UI always uses generic temporary-
  unavailability copy and never branches on free-form detail.

### PR slice 1c — bounded selected ranking API (hard prerequisite for F4b)

Exact files:

- modify `apps/api/src/ranking/ranking_sql.py`
- modify `apps/api/src/ranking/profile.py`
- modify `apps/api/src/routers/archetypes.py`
- modify `apps/api/src/models.py`
- modify `tests/test_ranking_sql.py`
- modify `tests/test_ranking_profile_identity.py`
- modify `tests/test_ranking_identity_and_no_legacy.py`
- modify `tests/test_archetype_rankings_v3.py`
- create `tests/test_archetype_rankings_scale_postgres.py`
- regenerate `apps/web/src/lib/api/generated/types.gen.ts`
- regenerate `packages/api-client/src/generated/api.gen.ts`

**Slice 1c is built on the F2d wide-row schema, not on the current keyed
`011`.** The owner's 2026-10-10 capacity decision rewrites migration `011` from
eight keyed rows per system to one wide row with per-archetype score columns
(`docs/ROADMAP.md` step 4′; design PR #806), so the generic
`system_archetype_key_score (generation, archetype_key, archetype_score,
system_id64)` access path this slice was first written against will not exist.
Slice 1c therefore lands **after** F2d PR1 — and only once the owner's answer
to capacity-decision question 6 (the score-index layout) is recorded in
`docs/operations/v3-finder-capacity-decision-2026-10-10.md`, which is the
ROADMAP's stated prerequisite for the F2d code; the owner answered **yes** to
the partial layout on 2026-10-10 and the F2d design PR (#806) records it, so
that PR merges before this slice may start. Slice 1c reads, for the selected
key, the per-archetype **partial** index
`(derived_generation_id, <key>_score DESC, system_id64) WHERE <key>_score >= 60`
that F2d defines (section 3.3 there). That index keeps the deterministic
`score DESC, system_id64 ASC` order the bounded probe needs without a tie sort:
the capacity decision's first deduplicating `(generation, <key>_score DESC)`
variant would have forced an incremental sort of the boundary score group,
whose size depends on the production score distribution (integer scores tie
heavily). Measured on the disposable PG18 at 1M rows with a bell-shaped
distribution: unique-entry index — index-only scan, 10,001 rows read, 2.4 ms
warm; partial `>= 60` variant — same plan, 3.5 ms warm, 8.4 B/row;
deduplicated variant — incremental sort, 10,184 rows read, 13 ms warm but
distribution-dependent. Every selected floor F4 exposes (S/A/B ⇒ `>= 88/76/60`)
is inside the partial index's predicate, so the probe is always index-only.
The scale proof seeds and tears down production-shaped relations/views only
inside the disposable PostgreSQL 18 fixture, using the **final F2d DDL and
indexes** (not a flattened or keyed stand-in).

Because the partial index holds only rows scoring ≥ 60, the **API boundary
changes with it**: `/api/archetypes/rankings` makes `min_score` default to 60
and rejects values below 60 with 422 (today it defaults to 40 and accepts 0–100,
`apps/api/src/routers/archetypes.py:508-518`); a request below the floor would
not be bounded by the index and could force a scan/sort of the wide relation.
The tier floors S/A/B ⇒ 88/76/60 remain inside the contract, C/D were already
excluded from the initial product, and the floor rule is part of the hashed
ranking identity. The OpenAPI parameter constraint changes, so slice 1c
regenerates the typed clients.

For one pinned generation and selected archetype, the API first reads through
that key's partial index in `<key>_score DESC, system_id64 ASC` order. Apart
from generation, only `min_score` (≥ 60) may constrain this index scan because
it is a range on the indexed score column; no joined `system_search` predicate
participates in selecting the window. Probe at most
10,001 raw/index-eligible rows: the first 10,000 form the immutable candidate
window and the sentinel sets `is_truncated`.

Only inside those first 10,000 does the query join and apply region, distance,
ELW/body counts and every other supported non-indexed filter. It then orders
survivors by `<key>_score × (<key>_confidence_ppm / 1000000.0) × completeness
DESC`, distance from Sol and system id. A row outside the raw-score window cannot outrank or
re-enter it, even if its non-indexed facts or confidence/completeness modifier
would otherwise change its global position. This order of operations guarantees
a bounded scan for every selected request regardless of filter selectivity: the
index probe touches at most 10,001 selected-score rows, while joins, non-indexed
filters, modifier sorting and counting touch at most 10,000. The API rejects
`offset >= 10,000` and any request whose `offset + limit` would cross the window;
the facade's final-page clamp prevents ordinary F4 requests from reaching that
error.

The companion `total` is the exact count after filtering inside the first-10,000
window, from 0 through 10,000; `count` remains the returned page length.
`is_truncated` independently records whether a 10,001st raw/index-eligible row
existed, so a selective request may return `total=3, is_truncated=true`. Clients
then render **filters applied within the top 10,000 by [Archetype] score** rather
than claiming 10,000 filtered matches. Preserve the repeatable-read generation
pin across raw-window probe, candidate page and within-window count.

These two-stage semantics are part of ranking identity, not an implementation
detail. Add the candidate-window rule to `PROFILE_SPEC`: window size 10,000;
raw `archetype_score DESC, system_id64 ASC` order; the indexed `min_score`
exception; post-window non-indexed filters; the within-window
confidence/completeness modifier and tie-breaks; the capped-count rule (`total`
is the post-filter count within the window); and raw-window `is_truncated`.
Bump `RANKING_VERSION` **from the identity F2d PR1 lands** (planned
`v3-colony-potential-2`, because the wide-row change is itself a new ranking
identity per the capacity decision) to the next one — **`v3-colony-potential-3`**
if F2d lands as planned; the candidate-window semantics are a distinct profile
change and must never reuse or overwrite F2d's identity. Record the resulting
new `ranking_sha256`, and update the human-reviewed pinned drift-guard digest
and every response-identity assertion from the version actually on `main`. The
current identity, hash source and recorded-hash guard are at
`apps/api/src/ranking/profile.py:33`,
`apps/api/src/ranking/profile.py:132-183` and
`tests/test_ranking_profile_identity.py:37-62`; response identity assertions
that currently pin v1 are at
`tests/test_ranking_identity_and_no_legacy.py:159-162` and
`tests/test_ranking_identity_and_no_legacy.py:203-206`. Extend the SQL-builder
fail-closed binding tests so execution cannot drift from those hashed rules
(`tests/test_ranking_sql.py:686-762`). Responses then advertise an identity that
reproduces the results they return (`apps/api/src/routers/archetypes.py:392-405`).

Broader filtered selected searches outside the raw-score window are deferred.
They require a new access path, such as a denormalized
`system_archetype_search` projection that co-locates raw archetype score with
hot search predicates, workload-specific composite B-tree indexes (for example,
generation + archetype + region + raw score) and an archetype-scoped spatial
GiST candidate path for radius queries. The current separate region B-tree and
position GiST indexes cannot promise both arbitrary filter breadth and selected
raw-score order (`sql/v3/migrations/004_v3_search_spatial_clusters.sql:50-54`).

Required proof: focused SQL-builder and router tests; the ordinary disposable
PostgreSQL integration suite; OpenAPI regeneration/drift; and the production-
shaped, at-least-1,000,000-system PostgreSQL 18 timing proof specified in the
validation plan. It must execute builder-produced page/count SQL over the real
three-relation/view/index shape and include reviewed
`EXPLAIN (ANALYZE, BUFFERS)` for first/near-ceiling pages and the within-window
filtered count. A flattened-table plan is insufficient. F4b is blocked,
including its Product E2E gate opt-in, until this PR and proof have landed.

### PR slice 1d — bounded Any-mode tier API (deferred prerequisite for Any tier only)

Keep this separate from F4a/F4b. Choose and version one measured contract: an
index/access path that bounds the `best_colony_potential` floor while preserving
the advertised `weighted_potential` ranking; a fixed weighted-order candidate
window before applying the floor; or an explicit candidate/count-work cap with
truthful truncation. Prove both page and companion-count work on the same
production-shaped PostgreSQL 18 relations/views used by slice 1c. If the chosen
path adds an index or projection, trace the V3 migration-manifest and production-
promotion registration gate before adding a migration. Until this PR lands,
F4's Any state is permanently no-floor and omits `min-tier`; this deferred PR
does not block selected-only F4b.

### PR F4a — typed ranking foundation (code-only, fixture-validated)

Exact files:

- create `apps/web/src/lib/features/explore/archetypes.ts`
- create `apps/web/src/lib/features/explore/archetypes.test.ts`
- create `apps/web/src/lib/features/explore/ranking-state.ts` (including bounded
  `page_size`/offset URL state)
- create `apps/web/src/lib/features/explore/ranking-state.test.ts` (including
  1–50/default-50 coverage)
- create `apps/web/src/lib/config.ts`
- create `apps/web/src/lib/config.test.ts`
- modify `apps/web/src/lib/api/client.ts` (`page_size` → existing wire `limit`)
- modify `apps/web/src/lib/api/client.test.ts` (including `page_size=1` → `limit=1`)
- modify `apps/web/src/lib/api/query.ts` (page size in the ranking query key)
- modify `apps/web/src/lib/api/query.test.ts`
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.svelte` (complete
  disabled-gate boundary and F4-parameter stripping)
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.test.ts` (disabled
  hand-authored-archetype URL regression)
- modify `apps/web/src/lib/features/explore/ExploreWorkspaceTestHost.svelte`
- modify `apps/web/src/lib/persistence/storage.ts`
- modify `apps/web/src/lib/persistence/storage.test.ts`
- modify `apps/web/src/lib/features/explore/shortlist.ts`
- modify `apps/web/src/lib/features/explore/shortlist.test.ts`
- modify `tests/test_seed_cypress_v3_generation.py`

Deliver the default-off feature gate, canonical metadata,
URL/page-size/offset codec with selected-only tier state, tier/evidence
presentation helpers, lossless
page-envelope normalizer,
`ExploreSystem` confidence/completeness plus score/distance identity **and
`ranking_provenance`** (the facade copies `ranking_version`, `ranking_sha256`,
generation id and publication sequence from each response envelope onto every
normalized row, so `SystemActions`/`snapshotFromExplore` need only the
`ExploreSystem` they already receive), persisted snapshot shape
(`ranking_score`, `score_kind`, selected archetype, distance reference and
`ranking_provenance`), and ranking query key. Without this in F4a every
selected-fit snapshot saved before F4c would have null provenance and F4c would
exclude all of them from comparison. The facade constrains `page_size` to 1–50
(default 50), maps it to existing endpoint `limit`, and applies one exclusive
10,000 offset/window limit to every mode before dispatch, clamping request size
at its boundary and correcting the URL with SvelteKit `goto` — because page
`LIMIT`/`OFFSET` is otherwise independent of the capped count, and because the
anchor is not URL state. The envelope preserves slice 1c's post-filter
within-window total and
independent API-owned `is_truncated`; for Any it exposes
`navigable_total = min(total, 10000)` alongside the exact `total` and the
existing `total_is_capped` state from the local-search response, so an exact
anchored total is shown truthfully while no mode promises unreachable numbered
rows. A selected fit never enters generic
`archetype_score`.
The gate wraps URL hydration, request selection, URL/history effects, selected-
point F4 behavior and rendering. Its disabled-build regression loads a hand-
authored archetype/tier/page URL, proves those parameters are replace-stripped,
asserts the rankings facade is never invoked, deep-compares the local-search
body with today's `{ galaxy_wide: true, sort_by: 'development', size: 24,
from: 0 }`, and finds no ranking UI. Preserve independent `selected`, `system`
and unrelated parameters.
F4a may land without slice 1b and must then omit the headline tier. Extend the
isolated-PostgreSQL seed test to pin all three Product systems' ranking fields
before Cypress relies on exact values. The slice 1c PR owns generated changes;
F4a consumes them without hand-editing generated files. Required proof: focused
Vitest and the seed integration test; Svelte web
check/lint/format/test/build (the protected job runs these at
`.github/workflows/ci.yml:381-417`); API facade boundary tests; and OpenAPI types
drift.

### PR F4b — visible slice-1 picker and ranked cards

Exact files:

- create `apps/web/src/lib/features/explore/ArchetypePicker.svelte`
- create `apps/web/src/lib/features/explore/ArchetypePicker.test.ts`
- create `apps/web/src/lib/features/explore/FinderResultRanking.svelte`
- create `apps/web/src/lib/features/explore/FinderResultRanking.test.ts`
- modify `apps/web/src/lib/features/explore/ranking-state.ts` (last-valid-page
  normalization)
- modify `apps/web/src/lib/features/explore/ranking-state.test.ts` (positive
  out-of-range and genuine-zero cases)
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.svelte` (one
  envelope owns `page_size`, offset, list and map)
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.test.ts` (including
  three one-row pages and stale-offset replacement/refetch)
- modify `apps/web/src/lib/features/explore/ExploreWorkspaceTestHost.svelte`
- modify `apps/web/src/lib/features/explore/compare-metrics.ts` (temporarily
  suppress distance in F4 Compare table and CSV)
- modify `apps/web/src/lib/features/explore/compare-metrics.test.ts`
- modify `apps/web/src/lib/features/explore/ComparePanel.svelte`
- modify `apps/web/src/lib/features/explore/ComparePanel.test.ts`
- modify `apps/api/src/review_main.py` (review-only `rankings_api_failure` and
  `rankings_empty_results` modes for `GET /api/archetypes/rankings`)
- modify `scripts/dev/review_lab/scenarios.py` (the two new scenario
  definitions and browser flow keys)
- modify `scripts/dev/review_lab/browser_runner.py` (`VITE_FINDER_F4_ENABLED: '1'`
  in the Review Lab bundle build overrides)
- modify `apps/web/cypress/e2e/review-lab.cy.ts` (`rankingsApiFailure` and
  `rankingsEmptyResults` flows)
- modify `tests/test_review_lab_v3.py` (the module that already covers the
  review-only scenario modes and the scenario registry) for the new modes and
  scenario entries
- modify `apps/web/src/lib/components/AppShell.svelte` (reactive selection
  hydration, including independent `selected`/`system` semantics)
- create `apps/web/src/lib/components/AppShell.test.ts`
- create `apps/web/src/lib/components/AppShellTestHost.svelte`
- modify `apps/web/src/lib/spatial/explore-scene.ts`
- modify `apps/web/src/lib/spatial/explore-scene.test.ts`
- modify `apps/web/src/lib/spatial/babylon/adapter.test.ts`
- modify `apps/web/Dockerfile`
- modify `apps/web/src/app.css`
- modify `apps/web/cypress/e2e/product-journey.cy.ts` (`page_size=1`, wire
  `limit=1`, three pages)
- modify `.github/workflows/cypress-parity.yml`
- modify `tests/test_browser_validation_lane_contract.py`
- modify `tests/test_ci_data_invariants.py`
- modify `tests/test_ci_dependency_contract.py`
- modify `tests/test_ci_stall_detection.py`
- modify `tests/test_e2e_harness_contract.py`
- modify `tests/test_v3_product_journey_contract.py`
- modify `tests/test_v3_python_runtime_validation.py`

After slice 1c and its timing proof have landed, add URL-synchronized
picker/selected-only minimum tier/page-size/offset/selection navigation, keep Any
on unchanged local search with no floor and branch a key to rankings, render
normalized cards and page/count state,
reserve the weight-tools layout slot, and keep all new UI behind the default-off
build flag (including a validated Docker build argument). Change autofocus to
the explicit Any-anchor revision; split mutable combobox draft text from the
committed anchor so archetype mode cannot erase the Any query. Retain a separate
deduplicated selected point before replacing result points so reranking cannot
drop its marker, and reconstruct that point after hydration with the existing
`getSystem`/`GET /api/system/{id64}` path when it is absent from the page. Set
result and Babylon system-pick commits to write `selected=<id64>` without opening
detail. Keep `system=<id64>` exclusively for `SystemOverlay`/Inspect, and
rehydrate archetype, selected-only tier, offset and passive selection reactively
from `page.url` on every SvelteKit navigation/popstate. Back/Forward must restore
the matching request/page/map; omission of `selected` on Explore clears the
URL-owned selection, while closing `system` leaves it intact. Set
each radio's accessible name from its short label only and reference its separate
one-line description with `aria-describedby`. When a returned `total > 0` is at
or below the requested offset, or saturated unanchored Any would cross 10,000,
call SvelteKit `goto` with `replaceState: true` for the calculated last valid
page, refetch once, and show the page-reset notice; never use native History API.
Only `total === 0` enters the no-match state. Add unit and component regressions.
Until F4c lands, suppress the distance metric from both Compare table and CSV in
the F4 opt-in surface; do not compare unlike references. Set
`VITE_FINDER_F4_ENABLED: '1'` only on the protected workflow's Svelte bundle
build step and update its named workflow-contract tests; production/release
builds keep the default `0`. Product E2E enters selected mode with `page_size=1`,
chooses Flexible at B, asserts the real request sends `min_score=60` and
`limit=1`, and traverses the computed V3 Lossless Reach → Achenar → HD 38179
order at offsets 0, 1 and 2 across the unchanged three-system corpus. It also
exercises Back/Forward across picker and page commits, and loads a copied
`selected=<id64>` URL after clearing both browser storage mechanisms to prove the
marker and Inspect hand-off come from the URL without mounting the overlay.
Required
proof: focused unit/component tests; full
Svelte web checks; OpenAPI drift;
**Svelte Web E2E** in Chrome and
Firefox (the protected matrix is at `.github/workflows/cypress-parity.yml:21-30`);
axe; approved desktop/mobile screenshots; and unchanged Review Lab.

### PR F4c — mode- and reference-safe saved surfaces

Exact files:

- modify `apps/web/src/lib/features/explore/compare-metrics.ts`
- modify `apps/web/src/lib/features/explore/compare-metrics.test.ts`
- modify `apps/web/src/lib/persistence/storage.ts`
- modify `apps/web/src/lib/persistence/storage.test.ts`
- modify `apps/web/src/lib/features/explore/shortlist.ts`
- modify `apps/web/src/lib/features/explore/shortlist.test.ts`
- modify `apps/web/src/lib/features/explore/ComparePanel.svelte`
- modify `apps/web/src/lib/features/explore/ComparePanel.test.ts`
- modify `apps/web/src/lib/features/explore/WatchlistPanel.svelte`
- modify `apps/web/src/lib/features/explore/WatchlistPanel.test.ts`

Replace duplicated/underscore-derived labels with the canonical F4 metadata.
Persist overall potential alongside selected-fit identity; compare overall
potential across modes, selected fits only for the same archetype, and distances
only for one exact reference with a reference-specific label. Remove F4b's
temporary distance suppression only when this full contract lands. Referenced
snapshots accept every finite distance including `0`; a legacy snapshot without
a reference remains unknown rather than treating zero as a sentinel. Add a
regression in which same-reference distances `0` and positive render `0.00 LY`
with zero best, while a no-reference legacy zero cannot make the row eligible.
This replaces the current positive-only behavior
(`apps/web/src/lib/features/explore/compare-metrics.ts:164-167`,
`apps/web/src/lib/features/explore/compare-metrics.test.ts:43-62`,
`apps/web/src/lib/features/explore/compare-metrics.test.ts:70-95`). Preserve legacy
snapshots as unknown-mode/reference rather than guessing.
Compare currently has its own mapping and tier thresholds
(`apps/web/src/lib/features/explore/compare-metrics.ts:17-28`,
`apps/web/src/lib/features/explore/compare-metrics.ts:50-63`); remove that
browser tier calculation and show a tier only from the corresponding API field.
Preserve historical unknown keys as readable fallbacks rather than pretending
they are V3 keys.
F4c is a hard prerequisite before the default-off flag may be enabled in a
governed production/release build — but not the only one. The spatial product
contract requires Finder score breakdowns to be accessible, and this design's
only V3 explanation path is deferred (section 4, “Per-archetype explanation”).
Enablement therefore also requires **an accessible explanation path**: the F2d
design's `GET /api/archetypes/system/{id64}/explanation` (its PR3) plus a small
F4 increment that renders the per-archetype breakdown from it in the result
card/Inspect hand-off with the same evidence wording. Until both land, the flag
stays `0` in every release build; enabling it with unexplained scores would
contradict the contract.
Required proof: focused Vitest/component tests, Svelte web checks, visual review
of saved/compare rows, Product E2E and Review Lab.

### PR F4d — V3 custom weights, only after F3 slice 2

Exact F4 web files, assuming the API-contract/generated-client PR has landed
first:

- create `apps/web/src/lib/features/explore/ArchetypeWeightsPopover.svelte`
- create `apps/web/src/lib/features/explore/ArchetypeWeightsPopover.test.ts`
- modify `apps/web/src/lib/features/explore/ranking-state.ts`
- modify `apps/web/src/lib/features/explore/ranking-state.test.ts`
- modify `apps/web/src/lib/api/client.ts`
- modify `apps/web/src/lib/api/client.test.ts`
- modify `apps/web/src/lib/api/query.ts`
- modify `apps/web/src/lib/api/query.test.ts`
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.svelte`
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.test.ts`
- modify `apps/web/cypress/e2e/product-journey.cy.ts`

Wire the already-designed pop-out, only to a V3-backed `/rerank`, and add URL
weights after its allowed dimensions are contractual. Per-archetype explanation
may be a separate PR using V3 `/system/{id64}`; simulation remains separate.
Required proof: regenerated-client drift check from the upstream API PR, focused
unit/component tests, full Svelte checks, Product E2E Chrome/Firefox, new visual
baselines, and unchanged Review Lab.

## 9. Risks and open questions for the owner

### Risks

- **Scope mismatch:** switching endpoints changes available catalogue facts and
  distance semantics. Mitigation: facade normalization, explicit galaxy-wide
  selected mode, persisted `distance_reference`, reference-aware comparison and
  no claim of arbitrary-anchor ranking.
- **Misleading scores:** selected-archetype score and Best Colony Potential can
  differ. Mitigation: carry `score_kind`/selected archetype, persist the overall
  value separately, compare like with like and never use one value under both
  headings.
- **False certainty:** a high score can have thin evidence. Mitigation: always
  show confidence/completeness wording and keep classification confidence
  separate.
- **Unbounded selected query:** every floor, including B/60, may make the picked
  path sort and count a large portion of roughly 198.5 million systems without a
  precomputed cross-table ordering key (`docs/ROADMAP.md:197-214`). Mitigation:
  slice 1c is mandatory for all selected modes and takes the top-10,000
  raw-score window before any non-indexed filter, with a 10,001st raw-window
  sentinel; all joins, non-indexed filtering, modifier sorting and counting are
  bounded inside it. F4b remains disabled until its 1M-row PostgreSQL 18 timing
  proof lands.
- **Unbounded Any tier floor:** Any orders through the indexed
  `weighted_potential` path but a tier floor predicates unindexed
  `best_colony_potential`; the 10,000 qualifying-row count cap does not bound
  inspected rows. Mitigation: F4 sends no floor and hides Minimum tier in Any;
  slice 1d must add a measured index/candidate/count-work bound before enabling
  it.
- **Premature production exposure:** repository handlers exist before production
  has the required Finder products. Mitigation: default-off build gate, fixture
  validation, generic temporary-unavailability copy for 503, and enablement only
  in the governed release after publication receipts, F4c **and the accessible
  explanation path** (the F2d explanation endpoint plus the F4 increment that
  renders the breakdown — see PR F4c); only after slice 1c
  and its scale proof land does the protected Product E2E build opt in at its
  bundle step, with distance comparison suppressed until F4c, while
  production/release builds retain default `0`. This design authorizes no
  promotion. The gate covers URL hydration, request selection, history effects
  and selected-point F4 behavior as well as rendered controls; the disabled
  regression proves a hand-authored archetype URL cannot reach rankings.
- **Pagination drift:** a page may be mistaken for the full result set, diverge
  from the map, or be empty only because a shared offset outlived its result set.
  Mitigation: expose the selected mode's exact filtered-within-window total
  separately from raw-window `is_truncated`; derive Any `navigable_total`/cap
  state from local search; clamp offset plus page size to the uniform 10,000
  ceiling in every mode before dispatch (anchored exact totals are displayed,
  not navigated past 10,000); and update `page_size`,
  Next, count/truncation status, list and Finder contribution from one envelope.
  Correct positive out-of-range URLs with SvelteKit replacement navigation and
  reserve the no-match state for `total === 0`.
- **Interaction regressions:** refetch may steal picker focus or omit the selected
  marker; draft edits may erase the committed Any anchor; and store-only
  selection or one-shot hydration may break copied links and Back/Forward.
  Mitigation:
  anchor-selection-only autofocus, separate draft/committed-anchor state, a
  retained selected point contribution, and exact-system reconstruction after
  hydration; both selection handlers write passive `selected=`, `system=` remains
  an independent overlay trigger, URL hydration reacts to every SvelteKit
  navigation/popstate, and component/Product E2E cover clean-storage sharing plus
  history traversal.
- **False scale proof:** a flattened scratch table can hide view expansion, join
  order and real-index costs. Mitigation: slice 1c executes builder-produced page
  and count SQL against the production-shaped three-relation/view/index layout;
  a flattened EXPLAIN never unblocks F4b.
- **Fixture drift:** current fixture archetype outputs are generated but not
  pinned, and three rows cannot page at the default 50. Mitigation: add the
  database fixture-output contract before exact E2E assertions, retain exactly
  three systems, and exercise the computed Flexible B journey with
  `page_size=1`/wire `limit=1`.
- **Visual density:** nine choices plus tier controls can crowd narrow screens.
  Mitigation: wrap into a one-column mobile radio list and validate 390×844.
- **Legacy leakage:** generated methods exist for legacy-backed endpoints.
  Mitigation: expose only the two verified slice-1 facade methods until slice 2.

### Owner questions

The review resolves the production gate, headline-tier ownership, selected-mode
default B and no-floor Any behavior, slice 1c bounds for every selected mode,
the initial omission of C/D, mode/reference normalization, bounded browser
pagination, the fixture-output contract and Flexible B E2E journey, focus, the
beside-anchor picker with separate draft/committed state, shareable selection,
reactive history hydration and selected-marker reconstruction. The remaining
product/implementation choices are:

1. **Yes/no:** should primary/secondary classification confidence get a separate
   “clear/close fit” label in F4b, in addition to the evidence badge?
2. **Choose one:** keep future custom weights URL-only, or also remember them as a
   validated local preference after slice 2?
3. **Who owns the governed enablement decision:** after F4c has landed and made
   comparison reference-safe **and** the accessible explanation path (F2d
   explanation endpoint + breakdown rendering increment) has shipped, which
   publication and release receipts authorize changing `VITE_FINDER_F4_ENABLED`
   from its default `0` to `1` in a later immutable production/release web
   build? Neither prerequisite may be waived by this answer.
4. **Before Any gets a tier control, choose slice 1d's bounded semantics:** an
   index/access path compatible with `best_colony_potential`, a fixed
   weighted-order candidate window, or an explicit candidate/count-work cap with
   truthful truncation?
5. **Yes/no:** confirm (or adjust) the proposed slice 1c latency budgets in the
   validation plan — warm ≤ 300 ms first page, ≤ 600 ms near-ceiling page and
   within-window count; cold ≤ 1,500 / 2,500 / 2,500 ms — as the pass/fail
   line for the receipt that unblocks F4b?

### Review dispositions (2026-10-10)

1. **Expose the overall tier before requiring it** → the headline tier is now
   conditional on API `best_tier`; slice 1b exposes the summary field, while F4a
   may land with a number-only headline and no browser tier calculation.
2. **Label no-pick confidence as general evidence** → Any uses **Evidence
   confidence**, selected mode uses **Fit confidence**, and “fit” is forbidden in
   Any visible/accessibility copy.
3. **Bound the all-system selected-archetype query** → B/60 remains the UX
   default but is only a predicate, not a candidate bound. Slice 1c's candidate,
   ordering and count bounds are required for **every** selected-archetype mode;
   its raw-score window precedes every non-indexed predicate. They are no longer
   deferred to C/D. Any remains a separate no-floor path; a tier there waits for
   slice 1d.
4. **Keep F4 behind the governed production sequence** → F4a/F4b are code-only,
   fixture-validated and default-off; 503 is first-class, the outstanding
   migration/product/publication sequence remains controlling, and no promotion
   is authorized.
5. **Preserve the distance reference during normalization** →
   `distance_reference` now crosses normalized and persisted shapes; comparison
   is limited to one exact, visibly named reference.
6. **Preserve archetype identity when normalizing scores** → `ranking_score`,
   `score_kind` and `selected_archetype` are retained, selected fits never enter
   generic `archetype_score`, overall potential stays separate, and selected
   fits compare only for one archetype.
7. **Expose truncation for selected rankings** → slice 1c supplies API-owned
   `is_truncated` for the raw candidate window; the facade separately carries
   the exact post-filter count within that window plus bounded `page_size` and
   page metadata. The UI names the top-10,000 filter scope when truncated, and
   URL, offset, list/map/truncation update together.
8. **Gate result autofocus on a new anchor** → F4b uses an explicit Any-mode
   anchor-selection revision instead of result freshness and adds regression
   tests.
9. **Retain the selected system when replacing result points** → F4b preserves a
   deduplicated selected-system contribution across reranks/pages and tests the
   Babylon marker remains when the new result page omits it.
10. **Persist the selected point across share-link reloads** → the existing store
    persists only id64 (`apps/web/src/lib/persistence/stores.ts:107-112`), so F4b
    resolves an omitted hydrated selection with the existing `getSystem` facade
    and supported `GET /api/system/{id64}` route
    (`apps/web/src/lib/api/client.ts:554-566`,
    `apps/api/src/routers/systems.py:38-100`). It emits the deduplicated point only
    after matching the current selection and validating finite coordinates; the
    reload E2E waits for that request and proves the marker appears exactly once
    while the result page still omits the row.
11. **Reconcile the 10,000 offset ceiling with selected totals** → current
    rankings accept unbounded non-negative offsets and return an uncapped exact
    total (`apps/api/src/routers/archetypes.py:348-373`,
    `apps/api/src/routers/archetypes.py:508-530`). Slice 1c replaces that contract:
    navigation is limited to filtered survivors inside 10,000 candidates,
    `total` counts those survivors, and a 10,001st raw/index-eligible row sets
    `is_truncated=true` independently. The UI says **filters applied within the
    top 10,000 by [Archetype] score**, and the URL codec, request-size clamp,
    Next state, count, DOM and map stop together.
12. **Enable F4 in the protected Product E2E build** → the current workflow builds
    with plain `pnpm build` (`.github/workflows/cypress-parity.yml:191-193`), so
    after slice 1c and its timing proof land, F4b sets
    `VITE_FINDER_F4_ENABLED: '1'` on that bundle-build step only for the protected
    Chrome/Firefox lane. Production/release builds keep default `0`, and the
    workflow contract files found under `tests/` are updated in the same PR with
    a step-scope assertion.
13. **Preserve the committed anchor while archetype mode is active** → current
    input edits clear the sole anchor
    (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:401-410`,
    `apps/web/src/lib/features/explore/ExploreWorkspace.svelte:429-434`). F4b
    splits draft text from the committed anchor; only suggestion commit or
    explicit reset changes it, returning to Any restores it, and the component
    test pins anchor → archetype → edit draft → Any.
14. **Bound selected rankings before enabling the B default** → `min_score=60`
    is a predicate and cannot bound how many of roughly 198.5 million systems
    qualify. Current selected mode orders by the unindexed cross-table
    `archetype_score × confidence × completeness` product and executes an
    uncapped count on every request
    (`apps/api/src/ranking/ranking_sql.py:451-462`,
    `apps/api/src/routers/archetypes.py:348-373`). Slice 1c is therefore a
    separate API PR and a hard prerequisite for all selected modes: through the
    existing raw-score index
    (`sql/v3/migrations/011_v3_system_archetype.sql:45-50`) it takes the first
    10,000 candidates in deterministic raw-score order before non-indexed
    filters, applies those filters and the modifier only within that window,
    counts filtered survivors there, and uses the 10,001st raw candidate only
    for `is_truncated`. F4b cannot be enabled even in
    Product E2E until the disposable PostgreSQL 18 fixture and production-shaped
    1M-system three-relation/view/index timing proof have landed.
15. **Seed enough systems to exercise pagination** → the Product fixture
    deliberately publishes exactly three systems
    (`tests/test_seed_cypress_v3_generation.py:167-191`), while current Explore
    requests 24 rows (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-139`).
    Rankings already accepts wire `limit` with default 50
    (`apps/api/src/routers/archetypes.py:517-518`), so the F4 facade exposes
    bounded `page_size` 1–50 and maps it to that existing parameter. Product E2E
    uses the Flexible B journey, `page_size=1`, and `min_score=60`; it asserts
    `limit=1` and traverses V3 Lossless Reach, Achenar and HD 38179 at offsets 0,
    1 and 2 for three real pages. The committed corpus stays at three systems; a
    larger synthetic corpus was rejected because it would enlarge
    checksum-locked fixture data, derived-build runtime and expected-output
    maintenance solely to force a Next transition.
16. **Bound scans before applying non-indexed filters** → the current builder
    maps region, distance and ELW/body-count predicates onto the joined
    `system_search` row before its final `LIMIT`
    (`apps/api/src/ranking/ranking_sql.py:331-378`,
    `apps/api/src/ranking/ranking_sql.py:479-506`), so a selective request can
    inspect far beyond 10,000 rows. Slice 1c instead probes
    the selected key's partial score index first in generation, raw score
    descending and system-id ascending order; only indexed `min_score` may also
    constrain that scan. The first 10,000 rows are fixed before every
    non-indexed predicate, modifier and within-window count, and a 10,001st raw
    row alone sets `is_truncated`. This guarantees a bounded scan for every
    selected request regardless of filters. The UI says **filters applied within
    the top 10,000 by [Archetype] score** whenever the raw window truncates, even
    when the filtered `total` is small. Broader filtered selected searches are
    deferred until a denormalized `system_archetype_search` projection can add
    workload-specific composite B-tree indexes and an archetype-scoped spatial
    GiST candidate path.
17. **Choose a fixture archetype that admits all three rows** → a direct run of
    the checksum-validated Product fixture through the production Ratings encoder
    and `fit_all` model found Flexible is the only archetype whose minimum score
    across the three systems reaches B. Product E2E therefore chooses **Flexible
    Multi-Role Colony**, keeps the normal B floor (`min_score=60`) required by
    disposition 14, and expects **V3 Lossless Reach 100/S → Achenar 100/S →
    HD 38179 75/B** after the within-window modifier. Manufacturing Hub is
    rejected: its Refinery/Industrial anchors
    (`scripts/v3_system_archetype_model.py:22-30`) meet HD 38179 potentials 0/64,
    producing a 12.8 core and final score 7/D under the committed formula
    (`scripts/v3_system_archetype_model.py:85-131`). The fixture-output contract
    remains a gate before Cypress copies these exact values; no fixture-only C/D
    relaxation is needed.
18. **Version the new candidate-window ranking semantics** → the existing
    `PROFILE_SPEC` hashes score, modifier, tie-break, tiers, filters and archetype
    keys but not the two-stage window (`apps/api/src/ranking/profile.py:132-183`).
    Slice 1c adds `apps/api/src/ranking/profile.py`,
    `tests/test_ranking_profile_identity.py` and
    `tests/test_ranking_identity_and_no_legacy.py` to its exact file list. The
    spec gains window size, raw-score order, indexed-minimum exception,
    within-window filters/modifier, capped post-filter within-window count and
    raw-window truncation semantics. Because those rules change which results a
    response means, bump the advertised identity from
    the identity F2d lands (planned `v3-colony-potential-2`;
    `apps/api/src/ranking/profile.py:33` is `-1` today) to the next one
    (**`v3-colony-potential-3`** if F2d lands as planned), record its new hash and update the reviewed
    drift-guard digest (`tests/test_ranking_profile_identity.py:37-62`) plus the
    response identity assertions
    (`tests/test_ranking_identity_and_no_legacy.py:159-162`,
    `tests/test_ranking_identity_and_no_legacy.py:203-206`), so responses
    advertise an identity that reproduces the returned ranking.
19. **Report the Any-mode navigation cap** → the 10,000 URL and request ceiling
    applies to selected rankings and saturated unanchored Any responses. Local
    search passes a count cap only for `galaxy_wide`, so an anchored Any request
    (500 LY by default) can return
    an exact total above 10,000 (`apps/api/src/local_search.py:248-254`,
    `apps/api/src/local_search.py:918-923`). The Any envelope therefore exposes
    the returned `total` as `navigable_total` and retains the response's
    `total_is_capped` truncation state. That existing field is set only for a
    saturated galaxy-wide count and is absent on precise distance-bounded
    searches (`apps/api/src/local_search.py:965-970`,
    `apps/api/src/models.py:408-412`). Exact anchored results can navigate beyond
    9,999; capped galaxy-wide results clamp offset plus page size at 10,000 while
    visibly reporting the cap.
20. **Normalize offsets that exceed the returned total** → after a response with
    `total > 0` and `offset >= total`, F4b computes
    `floor((total - 1) / page_size) * page_size`, rewrites the URL with SvelteKit
    `goto(..., { replaceState: true })`, refetches that last valid page and shows
    **Page reset to the last available results.** It never turns the stale page's empty array
    into a no-match claim; only `total === 0` renders the genuine empty state.
    F4b's unit and component tests cover the clamp, replacement/refetch, notice,
    absence of a false empty state, and the real-zero case.
21. **Keep radio descriptions out of the accessible name** → every radio label
    contains only the short archetype name. Its one-line description lives in a
    separate stable-id element referenced with `aria-describedby`, so assistive
    technology receives one short name and one description rather than announcing
    the description twice. The picker component test asserts both values
    separately.

#### Round 6 — 2026-10-10 (PR #801)

1. **P1-A — Bound the Any-mode tier count before defaulting to B** → F4 now
   preserves today's no-floor Any request and makes Minimum tier selected-only.
   The review verified that Any filters `best_colony_potential`, orders/indexes
   `weighted_potential`, and stops the count only after 10,000 qualifying rows,
   so a nonzero floor can inspect most of the generation
   (`apps/api/src/ranking/ranking_sql.py:315-357`,
   `apps/api/src/ranking/ranking_sql.py:451-462`,
   `apps/api/src/ranking/ranking_sql.py:512-565`,
   `sql/v3/migrations/011_v3_system_archetype.sql:52-56`). New slice 1d must add
   a bounded Any access/candidate/count-work path before Any exposes a tier; the
   URL ignores/removes `min-tier` in the meantime.
2. **P1-B — Gate the ranking request path, not only the new controls** → the
   default-off gate now owns URL hydration/canonicalization, request selection,
   history effects, selected-point F4 behavior and rendering. A disabled build
   strips F4 parameters, preserves `selected`/`system`/unrelated parameters, cannot reach
   rankings, and issues today's unchanged local-search request
   (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:123-144`). F4a's
   exact test list includes the disabled hand-authored-archetype URL regression.
3. **P2-A — Put the selected system into the shared URL (superseded by Round 7
   disposition 1)** → Round 6 identified the store-only handler gap
   (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:468-473`,
   `apps/web/src/lib/features/explore/ExploreWorkspace.svelte:505-516`) but chose
   `system=`. Round 7 corrects that parameter to passive `selected=` because
   `system=` opens the overlay.
4. **P2-B — Rehydrate ranking state on history navigation (selection parameter
   corrected by Round 7 disposition 1)** → hydration is now
   reactive to SvelteKit `page.url` on initial load, client navigation and
   popstate. It atomically reparses archetype, selected-only tier, page size,
   offset and selection, refetches the matching branch/page, and clears URL-owned
   selection when `selected` disappears from an Explore history entry. Component
   and Product E2E cover
   Back/Forward across picker and pagination changes without URL-write loops.
5. **P2-C — Benchmark the production-shaped join plan** → slice 1c's receipt now
   executes SQL emitted by `build_ranked_query` and `build_count_query`
   (`apps/api/src/ranking/ranking_sql.py:392-509`,
   `apps/api/src/ranking/ranking_sql.py:512-574`) against scale-seeded
   production-shaped `system_search`, `system_archetype` and summary
   relations/views with their real indexes on disposable PostgreSQL 18. A
   hand-written or flattened-table EXPLAIN does not unblock F4b.

#### Round 7 — 2026-10-10 (PR #801)

1. **P1 — Separate passive selection from the detail-overlay trigger** → Round
   6 dispositions 3–4 are superseded: result and Babylon picks write
   `selected=<id64>`, which hydrates Explore selection and a validated marker
   without mounting a modal. `system=<id64>` remains exclusively the explicit
   `SystemOverlay`/Inspect trigger. The two parameters may coexist; closing the
   overlay removes only `system`, and clearing selection removes only `selected`.
   This follows the verified current behavior that `system` derives `overlayId`
   and mounts `SystemOverlay` (`apps/web/src/lib/components/AppShell.svelte:19-33`,
   `apps/web/src/lib/components/AppShell.svelte:76`), whose close path removes
   `system` (`apps/web/src/lib/components/SystemOverlay.svelte:37-44`). The clean-
   session E2E restores the marker from `selected` with no modal, and the select
   → rerank/page journey keeps that marker.
2. **P2-A — Use SvelteKit navigation for URL replacement** → canonicalization
   and stale/capped-offset correction derive their destination from reactive
   `page.url` and call `$app/navigation` `goto(..., { replaceState: true })`;
   native `history.replaceState` is forbidden. This matches the current app
   precedent (`apps/web/src/lib/components/AppShell.svelte:2-3`,
   `apps/web/src/lib/components/AppShell.svelte:54-58`) and keeps hydration plus
   Back/Forward synchronized.
3. **P2-B — Preserve measured zero-distance comparisons** → F4c accepts every
   finite distance, including `0`, when a snapshot carries the exact shared
   `distance_reference`; only legacy snapshots without a reference are unknown.
   Its regression replaces the current positive-only sentinel
   (`apps/web/src/lib/features/explore/compare-metrics.ts:164-167`) and proves
   same-reference zero renders `0.00 LY` and wins against a positive distance.
4. **P2-C — Clamp saturated galaxy-wide Any pages at 10,000** → anchored Any
   keeps its exact total and may navigate beyond 10,000. Once unanchored Any
   reports `total_is_capped=true`, F4 clamps `offset + page_size` to 10,000 and
   corrects/refetches URLs at or beyond that boundary. This is necessary because
   `local_db_search_v3` passes page size/offset to `LIMIT`/`OFFSET` independently
   of the galaxy-wide-only capped count (`apps/api/src/local_search.py:902-923`,
   `apps/api/src/ranking/ranking_sql.py:479-506`,
   `apps/api/src/ranking/ranking_sql.py:530-565`).
5. **P2-D — Make comparison reference-safe before release enablement** → F4b
   temporarily suppresses distance from both Compare table and CSV while the F4
   opt-in surface is exercised. F4c restores it only with exact-reference,
   reference-labelled and zero-safe behavior, and is a hard prerequisite before
   the default-off flag is enabled in a governed production/release build. The
   PR plan and enablement owner question record that ordering.
6. **P2-E — Do not attribute every 503 to unpublished data** → generic 503s
   show **Ranking temporarily unavailable**: “Archetype rankings are temporarily
   unavailable. Try again shortly.” Only an optional stable slice-1 reason such as
   `finder_products_not_ready` selects **Ranking data not ready**: “Archetype
   rankings are unavailable until Finder ranking data is published.” The reason
   is a non-blocking API nicety because ordinary PostgreSQL errors also become
   503 (`apps/api/src/routers/archetypes.py:365-387`); free-form detail never
   drives the copy.

#### Round 8 — 2026-10-10 (PR #801)

1. **P1 — Clamp unanchored Any offsets before issuing the request** → Round 7
   disposition 4 is superseded: the 10,000 clamp for galaxy-wide Any (and for
   selected mode, whose window is 0–10,000 by contract) is applied **before
   dispatch**, independent of any response — `offset < 10000`, wire page
   `min(page_size, 10000 - offset)`, and a URL at or beyond the boundary is
   canonicalized to the last valid page before the first request. A fresh load of
   `/explore?offset=2000000000` therefore never reaches `/api/local/search`,
   whose request model accepts `from` up to 2,147,483,647 and whose SQL forwards
   `OFFSET` unbounded (`apps/api/src/local_search.py:902-923`,
   `apps/api/src/ranking/ranking_sql.py:479-506`). Only anchored Any, whose exact
   total may exceed 10,000, is clamped to the returned `total` once known.
   `total_is_capped` drives only the truncation copy.
2. **P2-A — Preserve valid zero values in result cards** → the card rule now
   omits or says “Unknown” only for `null`/absent values and renders every finite
   zero (the anchor's own distance is `0.00 LY`), consistent with the live row's
   non-null rendering and with Round 7 disposition 3 for comparisons.
3. **P2-B — Exercise ranked failure states in Review Lab** → F4b adds two
   F4-enabled Review Lab scenarios, `rankings_api_failure` and
   `rankings_empty_results`, served by new review-only modes in
   `apps/api/src/review_main.py` for `GET /api/archetypes/rankings` (the
   existing middleware covers only `POST /api/local/search`,
   `apps/api/src/review_main.py:129-158`), with browser flows
   `rankingsApiFailure`/`rankingsEmptyResults` in `review-lab.cy.ts`; the Review
   Lab bundle build (`scripts/dev/review_lab/browser_runner.py:164-172`) sets
   `VITE_FINDER_F4_ENABLED: '1'`. The four existing scenarios stay unchanged; no
   normal picker journey is duplicated there. The F4b file list records the
   exact files.
4. **P2-C — Define pass/fail latency budgets for the scale gate** → the slice 1c
   receipt now carries explicit budgets (warm median-of-5 and cold-after-restart,
   per first page / near-ceiling page / within-window count, including the
   selective-filter cases) measured as `EXPLAIN (ANALYZE, BUFFERS)` execution
   time; exceeding any budget blocks the receipt and F4b, and budgets may only be
   raised by a recorded owner decision. The numbers are proposed and listed as
   owner question 5.
5. **P2-D — Persist ranking provenance before comparing saved scores** →
   `RankingIdentityFields` gains `ranking_provenance` (`ranking_version`,
   `ranking_sha256`, generation id, publication sequence) copied from the response
   envelope and persisted with every snapshot. Selected-fit comparison requires
   equal `score_kind`, `selected_archetype`, `ranking_version` **and**
   `ranking_sha256`; generation/sequence are displayed, not required. Snapshots
   without provenance never enter a selected-fit comparison. This also covers the
   ranking-identity change the F2d capacity design introduces.

#### Round 9 — 2026-10-10 (PR #801)

1. **P1 — Clamp unanchored Any before response metadata** → the canonical URL
   table's offset row now matches the pre-dispatch rule: for a selected archetype
   and for unanchored Any (both known from the URL alone) `offset >= 10,000` is
   rejected and canonicalized before the first request, and the wire page is
   clamped, with no dependence on `total_is_capped` or any response field; only
   anchored Any navigates an exact total beyond 10,000.
2. **P2-A — Carry ranking provenance through F4a snapshots** → F4a's deliverable
   and its test list now include copying `ranking_provenance` from each response
   envelope onto every normalized row (both response shapes) and into
   `snapshotFromExplore`'s persisted snapshot, with legacy snapshots normalizing
   to `null`; `SystemActions` keeps receiving only the `ExploreSystem`.
3. **P2-B — Update Review Lab selection setup for URL ownership** → the claim
   that all four existing scenarios are unchanged was wrong for `apiFailure`:
   it seeds selection only in `localStorage` and visits `/explore` without
   `selected=`, which the F4 URL contract treats as clearing selection. F4b
   updates that flow, and writes `rankingsApiFailure` the same way, to establish
   `selected=<id64>` and its marker first, then induce the failure and assert
   that exact selection and marker survive; the “if any” wording is removed.
4. **P2-C — Analyze the scale fixture before timing queries** → the slice 1c
   recipe requires `ANALYZE` on all three relations after load/index creation
   and before the warm and cold runs, per the derived-data decision.
5. **P2-D — Saturate the candidate window in the scale fixture** → the seed must
   provide and assert at least 10,001 index-eligible rows for the archetype and B
   floor under test, a populated offset-9950 page, and an observed 10,001st-row
   sentinel before the receipt is accepted.

#### Round 10 — 2026-10-10 (PR #801)

1. **P2-A — Encode anchors before deriving the offset policy** → resolved the
   other way: since the anchor is deliberately not URL state (section 6), an
   anchored search cannot be told apart from an unanchored one after a reload,
   so F4 applies **one** 10,000 navigation ceiling to every mode before dispatch
   (`navigable_total = min(total, 10000)`); an anchored exact total above 10,000
   is displayed exactly but is not navigable. This supersedes the anchored-Any
   exception in Rounds 7–9 and removes the mode-dependent clamp entirely.
2. **P2-B — Require provenance parity for overall scores** → Best Colony
   Potential is compared only between entries with equal `ranking_version` and
   `ranking_sha256`; otherwise omitted with the “different ranking versions”
   note. Snapshots without provenance enter no score comparison and are listed
   with an “older save” note.
3. **P2-C — Gate production enablement on score explanations** → enabling the
   flag in a release build now also requires an accessible explanation path: the
   F2d explanation endpoint (`GET /api/archetypes/system/{id64}/explanation`)
   plus a small F4 increment rendering the breakdown; F4c is a prerequisite, not
   the final one.
4. **P2-D — Preserve `system` hydration when F4 is disabled** → the `system`
   row and the `AppShell` change apply the “never creates `selected`” rule only
   in F4-enabled builds; the default-off build keeps copying `?system=` into
   `selectedSystem` as today, with a disabled-build regression test.
5. **P2-E — Represent unknown legacy score modes explicitly** → `score_kind`
   gains an `"unknown"` variant produced only by the decoder for pre-F4 snapshots
   that carry the ambiguous generic `archetype_score`; it is excluded from every
   mode-specific comparison and never written by a new save.

#### Round 11 — 2026-10-10 (PR #801)

1. **P2-A — Apply the navigation ceiling to anchored searches in the risk
   mitigation** → the stale “preserving anchored exact navigation” phrase in the
   pagination-drift risk is replaced by the uniform pre-dispatch 10,000 ceiling.
2. **P2-B — Include score explanations in the production gate** → the
   premature-exposure mitigation and owner question 3 now name the accessible
   explanation path (F2d endpoint + breakdown rendering) as a prerequisite that
   the enablement answer cannot waive.
3. **P2-C — Serialize anchor selection before resetting the URL** → choosing a
   known-star anchor is a selection commit: the offset-reset navigation carries
   `selected=<anchor id64>` in the same `goto`, so hydration cannot discard the
   anchor the user just chose.

#### Round 12 — 2026-10-10 (PR #801)

1. **P2-A — Gate on product publication instead** → the opening gate now
   requires both product-publication receipts (`publish_derived_product` for
   `system_search` and `system_archetype` on the already published
   `ratings_v4_prod_p4_parallel_v1`) and names the 2026-10-10 capacity decision
   that replaced the fresh-generation route; the generation pointer does not
   move.
2. **P1 — Rebase the scale gate on the wide-row schema** → slice 1c is rebuilt
   on the F2d wide row and lands after F2d PR1: the bounded probe reads the
   selected key's partial index `(generation, <key>_score DESC, system_id64)
   WHERE <key>_score >= 60`, which keeps the deterministic order without a tie
   sort (measured at 1M rows: index-only, 3.5 ms warm; the deduplicating variant
   needs a distribution-dependent incremental sort). The scale fixture uses the
   final F2d DDL and indexes. The F2d design (PR #806) adopts the same partial
   index, replacing its deduplicating variant.
3. **P2-B — Include planning time in the latency gate** → budgets apply to
   statement wall time (planning + execution) with both figures recorded for
   diagnosis.
4. **P2-C — Restore the committed anchor during history navigation** → every
   anchor-dependent navigation stores the committed anchor in SvelteKit history
   state; hydration reads `page.state.anchor` before falling back to unanchored,
   so Back/Forward restore offset, selection and anchor together, and no history
   entry exists whose query cannot be restored. A fresh load is unanchored, as
   its URL says.

#### Round 13 — 2026-10-10 (PR #801)

1. **P1 — Persist coordinates with restored anchors** → the history payload is
   `{ id64, name, x, y, z }`; the live request derivation enters the anchored
   branch only with numeric coordinates, so an id-only payload would have queried
   galaxy-wide under a restored anchor. Non-finite restored coordinates mean no
   anchor. The A → B → Back test asserts the request carries A's coordinates.
2. **P1 — Reject sub-B scores before relying on the partial index** → slice 1c
   changes the API boundary with the index: `min_score` defaults to 60 and
   values below 60 are 422; the floor rule is part of the hashed identity and the
   typed clients are regenerated.
3. **P1 — Wait for the owner-approved score-index layout** → the owner answered
   yes to the partial layout on 2026-10-10; the F2d design PR (#806) records it
   in the capacity decision as the ROADMAP requires, and slice 1c may start only
   after that PR has merged.
4. **P2 — Qualify empty results from a truncated candidate window** →
   `total === 0` with `is_truncated=true` uses window-qualified copy (“None of
   the top 10,000 systems by … score match these filters”) and offers
   **Clear filters**; only `is_truncated=false` is a genuine no-match.
5. **P1 — Version slice 1c after the landed F2d identity** → the bump starts
   from the identity F2d lands (planned `v3-colony-potential-2`) and goes to the
   next (`-3`), never reusing F2d's; digest and response assertions follow the
   version actually on `main`.
