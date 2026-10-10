# V3 Finder F4 archetype ranking UI design

## 1. Status

**Status: Design only; not implemented — 2026-10-10 — base `origin/main` `3b6ee91a2e4b076a97a2564cc38310411b534beb`.**

F4a and F4b are code-only increments validated against disposable fixtures.
They remain hidden behind a default-off build feature gate until the governed
production sequence has applied the pending migrations, built and validated both
Finder products, published their owning generation, and passed the separate
application-release gate (`docs/ROADMAP.md:140-179`). This design does not
authorize migration application, product build/publication, deployment or
promotion.

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
  **slice 2** means the deferred endpoint cutovers described below
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

| Surface                                        | Current implementation                                                                                                                                                                                                                                                                                                                                                         | Consequence for F4                                                                                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/local/search`                       | The route delegates to `local_db_search_v3` (`apps/api/src/routers/search.py:157-203`, `apps/api/src/routers/search.py:243-245`). That implementation reads V3 search and archetype-summary projections through the ranking query, pins one published generation, and emits ranking identity (`apps/api/src/local_search.py:843-850`, `apps/api/src/local_search.py:925-963`). | Available in code and disposable fixtures for **Any** (no selected archetype); not production-ready until the governed data gate opens. |
| `GET /api/archetypes/rankings`                 | The handler validates one of the eight V3 keys, passes it as `picked_archetype`, and reads in one repeatable-read snapshot (`apps/api/src/routers/archetypes.py:294-405`).                                                                                                                                                                                                     | Available in code and disposable fixtures for a selected archetype; production currently has no usable Finder product.                  |
| `POST /api/archetypes/rerank`                  | The handler reads `system_archetype_scores` and other legacy relations (`apps/api/src/routers/archetypes.py:535-590`).                                                                                                                                                                                                                                                         | Not usable; wait for slice 2.                                                                                                           |
| `GET /api/archetypes/system/{id64}`            | The current handler reads legacy systems/archetype/topology relations (`apps/api/src/routers/archetypes.py:635-719`).                                                                                                                                                                                                                                                          | No V3 per-system explanation drawer yet; wait for slice 2.                                                                              |
| `POST /api/archetypes/simulate`                | The current handler reads legacy `system_archetype_scores` (`apps/api/src/routers/archetypes.py:905-929`).                                                                                                                                                                                                                                                                     | Not usable; wait for slice 2.                                                                                                           |
| `GET /api/archetypes/profiles`                 | It returns static legacy preset data, including the old archetype set (`apps/api/src/routers/archetypes.py:114-171`, `apps/api/src/routers/archetypes.py:989-1005`).                                                                                                                                                                                                           | It must not populate the V3 picker.                                                                                                     |
| `/api/search/galaxy` and `/api/search/cluster` | The module deliberately leaves both on the older implementation pending slice 2 (`apps/api/src/local_search.py:574-586`).                                                                                                                                                                                                                                                      | Not part of F4a/F4b.                                                                                                                    |

Both usable ranked paths fail explicitly when the published generation lacks
READY `system_search` or `system_archetype` products, instead of presenting a
false empty result (`apps/api/src/local_search.py:602-643`).

That failure is the expected production state today: the published generation
has no Finder products, so the readiness check returns HTTP 503 before a ranked
read (`docs/ROADMAP.md:140-179`, `apps/api/src/routers/archetypes.py:365-380`).
F4 treats this as a first-class **Ranking unavailable** state, not as zero
matches. It preserves the current selection and map, offers Retry and Any mode,
and never converts 503 into an empty-state message.

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
pattern parses `?system=` in `AppShell` and copies it into the selected-system
store after hydration (`apps/web/src/lib/components/AppShell.svelte:19-52`).
Central persistence keys and validated stores live in
`apps/web/src/lib/persistence/storage.ts:6-26` and
`apps/web/src/lib/persistence/stores.ts:40-125`; there is no Finder-query key.

### Fixtures

The Product E2E corpus contains Achenar `10477373803000`, V3 Lossless Reach
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

The Review Lab corpus is separate and contains Review Wiring, Review Aggregate
and Review Fallback (`scripts/dev/build_review_lab_v3_fixture.py:37-46`); its
contract requires the committed corpus to match the Review identities
(`tests/test_review_lab_v3.py:181-191`). Its seed uses the same V3 generation
builder (`scripts/dev/seed_review_v3_generation.py:108-124`).

**Unverified:** no committed fixture expectation pins the exact archetype,
score, tier, confidence or completeness for any of those six systems. Existing
Product Cypress asserts system presence and selection, not archetype output
(`apps/web/cypress/e2e/product-journey.cy.ts:43-53`,
`apps/web/cypress/e2e/product-journey.cy.ts:105-182`). Before an E2E test names an
exact expected tier, add a fixture-output contract test that builds the committed
corpus and asserts the resulting V3 rows.

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
6. Finder query and offset state is not URL-backed or shareable.
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

## 4. API dependency map

| UI element                         | Endpoint and field available today                                                                                                                                                                                                   | Availability and design rule                                                                                                                                                                                                                                                                                                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Picker: **Any**                    | `POST /api/local/search`; no archetype request field (`apps/api/src/models.py:537-564`).                                                                                                                                             | Slice 1 code/fixtures. “Any” uses the current default ranking; the production gate still applies.                                                                                                                                                                                                                                                                                                                          |
| Picker: one of eight archetypes    | `GET /api/archetypes/rankings?archetype=…`; key validation and profile query are in `apps/api/src/routers/archetypes.py:294-364`.                                                                                                    | Slice 1 code/fixtures. Initial selected-archetype mode is explicitly galaxy/Sol-oriented, because this endpoint has no arbitrary anchor.                                                                                                                                                                                                                                                                                   |
| Selected-score tier badge          | Any: `results[].archetype_tier`; selected: `results[].tier` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:880-892`).                                                                                                    | Slice 1 code. The value is carried with `score_kind`; it is not automatically the tier for the overall headline.                                                                                                                                                                                                                                                                                                           |
| **Best Colony Potential** tier     | `system_archetype_summary.best_tier` exists, but is omitted from ranking SQL and both payloads (`sql/v3/migrations/011_v3_system_archetype.sql:22-39`, `apps/api/src/ranking/ranking_sql.py:485-501`).                               | **Slice 1b API prerequisite:** expose summary `best_tier` in rankings and local-search payloads/generated types. Until then show the headline number without a tier. Never compute an API-owned tier in the browser.                                                                                                                                                                                                       |
| Minimum tier                       | Any: `min_development_score`; selected: `min_score` (`apps/api/src/models.py:551-555`, `apps/api/src/routers/archetypes.py:508-518`).                                                                                                | Default to B (`60`), a real tier boundary, rather than the API's non-tier default `40` (`apps/api/src/ranking/profile.py:52-54`). Initially offer B/A/S only. C/D require the bounded selected-ranking prerequisite below.                                                                                                                                                                                                 |
| Selected-ranking bounds            | Picked mode orders by a cross-table score/confidence/completeness product and its count is uncapped (`apps/api/src/ranking/ranking_sql.py:451-462`, `apps/api/src/routers/archetypes.py:348-363`).                                   | **API prerequisite before C/D:** server-side candidate cap, index-backed selected-fit ordering, bounded/capped count and explicit truncation metadata. The UI never sends a floor below the API default `40` before that contract. Any already orders on indexed summary `weighted_potential` and caps galaxy-wide counts (`sql/v3/migrations/011_v3_system_archetype.sql:52-56`, `apps/api/src/local_search.py:918-923`). |
| Confidence badge                   | Both paths return `confidence` and `completeness` (`apps/api/src/models.py:264-271`, `apps/api/src/models.py:898-902`).                                                                                                              | Slice 1 code. Say **Evidence confidence** in Any and **Fit confidence** for a selected archetype; never synthesize a missing value or use “fit” in Any mode.                                                                                                                                                                                                                                                               |
| Primary/secondary                  | Both paths return `primary_archetype` and `secondary_archetype` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:886-893`).                                                                                                | Slice 1 now. Use canonical labels, not underscore replacement.                                                                                                                                                                                                                                                                                                                                                             |
| **Best Colony Potential** headline | Both paths return `overall_development_potential`, sourced from the summary's best potential (`apps/api/src/local_search.py:806-815`, `apps/api/src/routers/archetypes.py:472-482`).                                                 | Slice 1 code. In selected mode, distinguish the selected-fit `score` from the overall headline; attach a tier only after slice 1b supplies `best_tier`.                                                                                                                                                                                                                                                                    |
| Page/count state                   | Rankings accepts `limit`/any non-negative `offset` and returns an uncapped exact `total` (`apps/api/src/routers/archetypes.py:348-373`, `apps/api/src/routers/archetypes.py:389-397`, `apps/api/src/routers/archetypes.py:508-530`). | The facade preserves that exact total but clamps browser navigation to the first 10,000 rows with `navigation_limit`, `navigable_total` and explicit `navigation_is_truncated` metadata. UI names “first 10,000 of TOTAL” when applicable; URL, Next, list, map and count stop together.                                                                                                                                   |
| Weight sliders                     | Current `/api/archetypes/rerank` uses legacy relations and legacy five-weight models (`apps/api/src/routers/archetypes.py:535-590`, `apps/api/src/models.py:744-763`).                                                               | Needs slice 2. Reserve layout only; do not call it. **Unverified:** the eventual V3 weight dimensions are not defined in current code.                                                                                                                                                                                                                                                                                     |
| Per-archetype explanation          | The V3 product stores explanation data (`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:73-77`), but `/system/{id64}` is legacy today (`apps/api/src/routers/archetypes.py:635-719`).                          | Needs slice 2. Do not show legacy rationale as V3 explanation.                                                                                                                                                                                                                                                                                                                                                             |
| Rerank action                      | Intended endpoint is `POST /api/archetypes/rerank`; its current implementation is legacy (`apps/api/src/routers/archetypes.py:535-628`).                                                                                             | Needs slice 2.                                                                                                                                                                                                                                                                                                                                                                                                             |
| Simulation                         | Intended endpoint is `POST /api/archetypes/simulate`; its current handler reads legacy data (`apps/api/src/routers/archetypes.py:905-929`).                                                                                          | Needs slice 2 and is not required for the first Finder UI.                                                                                                                                                                                                                                                                                                                                                                 |

Therefore the code-only UI increment buildable against fixtures is: Any plus the
eight archetype choices; a B/A/S minimum-tier filter; normalized ranked cards;
selected and overall scores; mode-correct confidence/completeness and
primary/secondary labels; pagination/URL state; and preserved selection,
Inspect and map hand-offs. It stays hidden by default pending the governed
production sequence. Slice 1b adds the overall tier; C/D wait for the bounded
selected-ranking contract. Wired weights, per-archetype explanations, V3
reranking and simulation are later increments.

## 5. UX design

### Picker

Use a labelled `<fieldset>` with a `<legend>` and nine native radio inputs. This
provides the radio-group role and checked state without recreating keyboard
semantics. Each label includes a short name and its description; descriptions are
connected with `aria-describedby`. The first option is **Any — show the best
overall colony opportunities**.

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

The minimum-tier control is a native `<select>` labelled **Minimum tier**, with
initial options B, A and S and B selected by default. B maps to `min_score=60`,
uses a real tier threshold, and bounds candidates more tightly than the API's
raw default 40 (`apps/api/src/ranking/profile.py:52-54`,
`apps/api/src/routers/archetypes.py:508-518`). C and D are not offered until the
API has a server-side candidate cap, index-backed selected-fit ordering and a
bounded/capped count contract. “Minimum” remains explicit so the control does
not imply a non-contiguous multi-select.

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

If an optional value is absent, omit that datum or say “Unknown”; never render
zero. Missing evidence is unknown rather than absent under the product truth
contract (`docs/colonisation-redesign/spatial-platform-product-contract.md:82-98`).

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

Above the list, show **Showing _COUNT_ of _TOTAL_ (results _START_–_END_)** from
the same response page. Selected-archetype mode exposes a browser navigation
window of at most the first 10,000 rows even though the endpoint returns an
uncapped exact `total`: rankings accepts every non-negative offset and does not
cap its count (`apps/api/src/routers/archetypes.py:348-373`,
`apps/api/src/routers/archetypes.py:508-530`). The normalized envelope therefore
carries `navigation_limit: 10000`,
`navigation_is_truncated: total > navigation_limit`, and
`navigable_total: min(total, navigation_limit)` in addition to `count`, exact
`total` and request `offset`. When truncated, show **Showing results
_START_–_END_ · first 10,000 of _TOTAL_ available** and disable Next at row
10,000. Provide Previous/Next only inside that window; never imply that the
default page or the navigable window is the complete ranking. Any-mode capped
totals retain their separate API `total_is_capped` meaning
(`apps/api/src/local_search.py:918-923`).

The URL codec, facade request size, Next availability, visible range, DOM list
and Finder contribution all derive from that one normalized envelope. A page
change updates them together, as required by the spatial product contract
(`docs/colonisation-redesign/spatial-platform-product-contract.md:102-110`).

- Loading: retain `aria-busy` on the result region and a `role="status"` message,
  naming the active mode: “Ranking systems for Manufacturing Hub…” Existing
  result loading already uses those semantics
  (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:743-763`).
- Empty: “No systems meet minimum tier B for Manufacturing Hub.” Include
  **Reset to tier B** (when the active floor is A/S) and **Choose Any** actions.
  Empty is not an error; do not offer gated C/D as an escape hatch.
- Error: HTTP 503 is a first-class **Ranking unavailable** state with
  `role="alert"`: “Archetype rankings are unavailable until Finder ranking data
  is published,” plus Retry and Choose Any actions. Retain the current
  selection/map and do not call this “no matches.” Other errors use the same
  retained-state retry pattern. Existing error state already has an
  alert and retry pattern
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
renderer-neutral scene. Inspect remains `/inspect?system={id64}`. No ranking
field enters a Babylon contract. This preserves the north star that the map is
the constant and information changes around it
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

That point must also survive a hard reload of a shared selection URL. The
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
  minimumTier: "S" | "A" | "B"; // C/D wait for the bounded API contract
  offset: number;
  weights: Readonly<Record<string, number>>; // empty until slice 2
}>;
```

Normalization also preserves semantic identity instead of flattening unlike
facts:

```ts
type DistanceReference = Readonly<{
  kind: "anchor" | "sol";
  id64: Id64;
  name: string;
}>;

type RankingIdentityFields = Readonly<{
  ranking_score: number | null;
  score_kind: "overall_potential" | "selected_fit";
  selected_archetype: ArchetypeKey | null;
  distance_reference: DistanceReference | null;
}>;
```

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

| State              | Canonical query form                                     | Rules                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------ | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Any archetype      | omit `archetype`                                         | Default. `archetype=any` canonicalizes to omission.                                                                                                                                                                                                                                                                                                                                                                                                  |
| Selected archetype | `archetype=manufacturing_hub`                            | Accept only the eight current keys. Unknown values fail closed to Any and show a non-blocking “unsupported link option” status.                                                                                                                                                                                                                                                                                                                      |
| Minimum tier       | `min-tier=A`                                             | Omit B, the default. Map S/A/B to 88/76/60. Treat C/D as unsupported until the bounded API prerequisite lands; do not accept or emit either value, and never send a floor below the API default 40.                                                                                                                                                                                                                                                  |
| Page offset        | `offset=50`                                              | Omit zero. Accept one integer `0 <= offset < 10,000` (the browser navigation-window limit); reject duplicates, fractions, negatives and values at or above the limit. The facade requests at most `10,000 - offset` rows, so even a hand-written URL cannot cross the window. Reset to zero when archetype, minimum tier or the **committed** anchor changes; draft text edits do not reset it. Map it to rankings `offset` and local-search `from`. |
| Future weights     | repeated, key-sorted `weight=<dimension>:<basis-points>` | Example only: `weight=capacity:2500`. Values are integers 0–10000 to avoid float serialization drift. Do not parse or emit until slice 2 defines allowed keys and total rules. **Unverified:** dimension identifiers.                                                                                                                                                                                                                                |
| Selected system    | existing `system=<id64>`                                 | Preserve current overlay/selection meaning (`apps/web/src/lib/components/AppShell.svelte:19-43`). It is not a ranking input.                                                                                                                                                                                                                                                                                                                         |

Serialize keys in the table's order and weights lexicographically so copying the
same state produces one stable URL. Picker and minimum-tier commits create a
history entry; offset navigation creates one entry; Reset creates one history
entry; future slider edits remain local draft state until Apply. Preserve
unrelated query parameters. The facade returns page `count`, `total`, request
`offset`, `navigable_total`, `navigation_limit` and explicit truncation/cap
metadata rather than returning a bare result array. For selected rankings,
`total` remains the endpoint's exact total while navigation and Next are clamped
to the first 10,000 results; counts and truncation copy must never be computed
independently of that envelope.

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

Comparison is mode-aware. **Best Colony Potential** remains comparable across
modes because its overall value is persisted separately. A selected-fit row is
shown or ranked only when every compared entry has `score_kind: 'selected_fit'`
for the same `selected_archetype`; otherwise it is omitted with a “different
ranking modes” note. Distance is compared only when every entry has the same
`distance_reference.kind` and id64, labelled **Distance from Sol** or
**Distance from _name_**. Mixed-reference distances are excluded rather than
silently compared.

## 7. Validation plan

### Unit tests (Vitest)

Vitest is the app’s unit runner (`apps/web/package.json:18-20`). Add pure tests
for:

- the exact eight-key metadata inventory and label lookup;
- tier-to-minimum-score mapping at 88/76/60, B as the default, and fail-closed
  C/D parsing while displayed result tiers remain the API's value;
- mode-specific confidence/completeness wording at missing, 0.50 and 0.80
  boundaries, including that Any-mode output never contains “fit”;
- URL parse/serialize round trips, canonical ordering, defaults, duplicate and
  unknown parameters, the exclusive 10,000 offset ceiling, request-size clamp,
  exact-total versus navigable-total/truncation rules, offset/reset rules, and
  preservation of unrelated parameters;
- request selection: Any → local search, key → rankings, default B → score 60;
- ranking-row normalization preserving `score_kind`, selected archetype,
  overall potential, `distance_reference`, page metadata, absent `best_tier`
  and lossless id64 handling;
- persistence backward compatibility plus mode-aware scores and same-reference
  distance comparison;
- default-off feature config and explicit fixture opt-in;
- future weight basis-point parsing behind a disabled feature flag, activated
  only with the slice-2 contract.

### Svelte component tests

Use Testing Library Svelte, which is installed in the current stack
(`apps/web/package.json:36-37`). Test:

- accessible picker name, nine radios, descriptions, checked state and native
  keyboard progression;
- minimum-tier label and request update;
- result headline, selected fit, tier, primary/secondary and all four evidence
  wordings;
- headline tier omitted without API `best_tier` and rendered only when supplied;
- page count/range and offset navigation keep exact total, the first-10,000
  truncation message, Next state, DOM and map synchronized;
- loading `status`, empty actions, first-class 503 ranking-unavailable `alert`
  and Retry;
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

1. starts on Any and proves the existing `/api/local/search` journey;
2. chooses Manufacturing Hub with the keyboard;
3. proves the URL contains `archetype=manufacturing_hub` and the real
   `/api/archetypes/rankings` request uses default `min_score=60`;
4. asserts ordered results show selected score/tier, Best Colony Potential,
   evidence wording and primary/secondary text;
5. pages with offset navigation, selects a row, reranks so the new page omits
   it, and verifies its map marker plus Inspect URL remain; then reloads that
   share URL with the selected row still absent, waits for the real
   `GET /api/system/{id64}` hydration request, and proves the validated selected
   marker/label appears exactly once while the DOM page still omits the row and
   the Inspect href remains `/inspect?system={id64}`; then runs axe;
6. captures approved 1280×800 and 390×844 screenshots with animation disabled.

The protected Product E2E bundle must actually contain the default-hidden F4
surface. In `.github/workflows/cypress-parity.yml`, add step-local
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
in the fixture inventory above. **Unverified:** their exact expected tiers are
not committed today. Add a PostgreSQL fixture-output contract alongside
`tests/test_seed_cypress_v3_generation.py` that asserts all three systems’
primary/secondary, Best Colony Potential, every selected-archetype score/tier,
confidence and completeness. Only then copy the exact expected Manufacturing
Hub order and tier values into Cypress. That makes a later model change an
explicit fixture-contract update rather than a silent screenshot change.

### Review Lab

Do not add a normal archetype-picker scenario. Review Lab owns synthetic
failure, empty, fault and containment states and explicitly does not own the
normal Explore → Inspect or visual-baseline journey
(`docs/development/v3-browser-validation-lanes.md:62-103`). Its current scenarios
are synthetic wiring, API failure, empty results and renderer recovery
(`scripts/dev/review_lab/scenarios.py:6-51`). They should remain unchanged and
green. Update a selector or message only if F4 intentionally changes the shared
empty/error DOM; do not duplicate picker, axe or visual assertions there. The
current wiring check only requires Review Wiring and Babylon readiness
(`apps/web/cypress/e2e/review-lab.cy.ts:184-205`).

### Visual validation and OpenAPI drift

F4 changes visible layout, colour and components, so visual validation is
mandatory (`CLAUDE.md:202-206`). Approved baselines belong exclusively to the
Product lane; Review Lab screenshots are diagnostic
(`docs/development/v3-browser-validation-lanes.md:90-103`). Review desktop and
mobile states for Any, a selected archetype, long names, limited evidence,
loading, empty and error; verify focus, zoom and contrast manually in addition to
axe.

F4 consumes existing generated types and does not itself change a backend
response shape. Still require the **OpenAPI types drift check**, which regenerates
both checked-in clients from a running disposable API and fails on a diff
(`.github/workflows/ci.yml:437-528`). If a later slice-2 PR changes a model, run
`pnpm generate:api` (`apps/web/package.json:28`) and commit the generated changes
in that API-contract PR.

## 8. Implementation plan: small PRs

Every PR must satisfy acceptance against its exact latest head and disposition
all substantive reviewer findings; green CI alone is insufficient
(`docs/development/pull-request-acceptance-policy.md:1-45`).

These PRs are code-only and fixture-validated. None authorizes production
promotion. Two API dependencies remain explicit:

- **Slice 1b — summary best tier:** project `sum.best_tier`, add `best_tier` to
  both rankings and local-search response models/builders, regenerate clients,
  and test that it is summary-owned. F4a may land first and represents the
  headline as a number without a tier; the browser never derives it.
- **Bounded selected ranking:** before the picker offers C or D, add a
  server-side candidate cap, index-backed selected-fit ordering, bounded/capped
  count, and explicit truncation metadata. Validate its plan at representative
  scale. The present raw-score index does not cover the cross-table ordering and
  the endpoint calls an uncapped `COUNT(*)`
  (`sql/v3/migrations/011_v3_system_archetype.sql:45-50`,
  `apps/api/src/ranking/ranking_sql.py:451-462`,
  `apps/api/src/routers/archetypes.py:348-363`).

### PR F4a — typed ranking foundation (code-only, fixture-validated)

Exact files:

- create `apps/web/src/lib/features/explore/archetypes.ts`
- create `apps/web/src/lib/features/explore/archetypes.test.ts`
- create `apps/web/src/lib/features/explore/ranking-state.ts`
- create `apps/web/src/lib/features/explore/ranking-state.test.ts`
- create `apps/web/src/lib/config.ts`
- create `apps/web/src/lib/config.test.ts`
- modify `apps/web/src/lib/api/client.ts`
- modify `apps/web/src/lib/api/client.test.ts`
- modify `apps/web/src/lib/api/query.ts`
- modify `apps/web/src/lib/api/query.test.ts`
- modify `apps/web/src/lib/persistence/storage.ts`
- modify `apps/web/src/lib/persistence/storage.test.ts`
- modify `apps/web/src/lib/features/explore/shortlist.ts`
- modify `apps/web/src/lib/features/explore/shortlist.test.ts`
- modify `tests/test_seed_cypress_v3_generation.py`

Deliver the default-off feature gate, canonical metadata, URL/offset codec,
tier/evidence presentation helpers, lossless page-envelope normalizer,
`ExploreSystem` confidence/completeness plus score/distance identity, persisted
snapshot shape (`ranking_score`, `score_kind`, selected archetype and distance
reference), and ranking query key. The codec and envelope expose the exclusive
10,000 offset/window limit, clamp request size at its boundary, preserve the
selected endpoint's exact total, and derive navigable total plus explicit
truncation from it. A selected fit never enters generic `archetype_score`. F4a
may land without slice 1b and must
then omit the headline tier. Extend the isolated-PostgreSQL seed test to pin all
three Product systems' ranking fields before Cypress relies on exact values. Do not
edit generated files because the schema already contains the operation and
fields. Required proof: focused Vitest and the seed integration test; Svelte web
check/lint/format/test/build (the protected job runs these at
`.github/workflows/ci.yml:381-417`); API facade boundary tests; and OpenAPI types
drift.

### PR F4b — visible slice-1 picker and ranked cards

Exact files:

- create `apps/web/src/lib/features/explore/ArchetypePicker.svelte`
- create `apps/web/src/lib/features/explore/ArchetypePicker.test.ts`
- create `apps/web/src/lib/features/explore/FinderResultRanking.svelte`
- create `apps/web/src/lib/features/explore/FinderResultRanking.test.ts`
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.svelte`
- modify `apps/web/src/lib/features/explore/ExploreWorkspace.test.ts`
- modify `apps/web/src/lib/features/explore/ExploreWorkspaceTestHost.svelte`
- modify `apps/web/src/lib/spatial/explore-scene.ts`
- modify `apps/web/src/lib/spatial/explore-scene.test.ts`
- modify `apps/web/src/lib/spatial/babylon/adapter.test.ts`
- modify `apps/web/Dockerfile`
- modify `apps/web/src/app.css`
- modify `apps/web/cypress/e2e/product-journey.cy.ts`
- modify `.github/workflows/cypress-parity.yml`
- modify `tests/test_browser_validation_lane_contract.py`
- modify `tests/test_ci_data_invariants.py`
- modify `tests/test_ci_dependency_contract.py`
- modify `tests/test_ci_stall_detection.py`
- modify `tests/test_e2e_harness_contract.py`
- modify `tests/test_v3_product_journey_contract.py`
- modify `tests/test_v3_python_runtime_validation.py`

Add URL-synchronized picker/minimum tier/offset navigation, branch Any to local
search and a key to rankings, render normalized cards and page/count state,
reserve the weight-tools layout slot, and keep all new UI behind the default-off
build flag (including a validated Docker build argument). Change autofocus to
the explicit Any-anchor revision; split mutable combobox draft text from the
committed anchor so archetype mode cannot erase the Any query. Retain a separate
deduplicated selected point before replacing result points so reranking cannot
drop its marker, and reconstruct that point after hydration with the existing
`getSystem`/`GET /api/system/{id64}` path when it is absent from the page. Set
`VITE_FINDER_F4_ENABLED: '1'` only on the protected workflow's Svelte bundle
build step and update its named workflow-contract tests; production/release
builds keep the default `0`.
Required proof: focused component tests; full Svelte web checks; OpenAPI drift;
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
only for one exact reference with a reference-specific label. Preserve legacy
snapshots as unknown-mode/reference rather than guessing.
Compare currently has its own mapping and tier thresholds
(`apps/web/src/lib/features/explore/compare-metrics.ts:17-28`,
`apps/web/src/lib/features/explore/compare-metrics.ts:50-63`); remove that
browser tier calculation and show a tier only from the corresponding API field.
Preserve historical unknown keys as readable fallbacks rather than pretending
they are V3 keys.
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
- **Unbounded selected query:** low floors can make the picked path sort and
  count a large portion of roughly 198.5 million systems without a precomputed
  cross-table ordering key (`docs/ROADMAP.md:197-214`). Mitigation: default B/60,
  offer only B/A/S, and gate C/D on the bounded API prerequisite. Any uses its
  indexed `weighted_potential` path.
- **Premature production exposure:** repository handlers exist before production
  has the required Finder products. Mitigation: default-off build gate, fixture
  validation, first-class 503 state, and enablement only in the governed release
  after publication receipts; the protected Product E2E build alone opts in at
  its bundle step while production/release builds retain default `0`. This design
  authorizes no promotion.
- **Pagination drift:** a page may be mistaken for the full result set or diverge
  from the map, or an exact selected-ranking total may advertise rows beyond the
  URL ceiling. Mitigation: preserve exact total but expose one first-10,000
  navigation window and update Next, count/truncation status, list and Finder
  contribution from one page envelope.
- **Interaction regressions:** refetch may steal picker focus or omit the selected
  marker; draft edits may also erase the committed Any anchor. Mitigation:
  anchor-selection-only autofocus, separate draft/committed-anchor state, a
  retained selected point contribution, and exact-system reconstruction after
  hydration, each covered by component/spatial regression tests.
- **Fixture drift:** current fixture archetype outputs are generated but not
  pinned. Mitigation: add the database fixture-output contract before exact E2E
  assertions.
- **Visual density:** nine choices plus tier controls can crowd narrow screens.
  Mitigation: wrap into a one-column mobile radio list and validate 390×844.
- **Legacy leakage:** generated methods exist for legacy-backed endpoints.
  Mitigation: expose only the two verified slice-1 facade methods until slice 2.

### Owner questions

The review resolves the production gate, headline-tier ownership, default B
floor, C/D prerequisite, mode/reference normalization, bounded browser
pagination, focus, the beside-anchor picker with separate draft/committed state,
and selected-marker hydration behaviour. The remaining product choices are:

1. **Yes/no:** should exact Cypress archetype outputs become a committed
   fixture-contract gate before F4b merges?
2. **Yes/no:** should primary/secondary classification confidence get a separate
   “clear/close fit” label in F4b, in addition to the evidence badge?
3. **Choose one:** keep future custom weights URL-only, or also remember them as a
   validated local preference after slice 2?
4. **Choose one:** what reviewed server cap and saturated-total wording should
   the bounded selected-ranking API expose before C/D are enabled?
5. **Who owns the governed enablement decision:** which publication and release
   receipts authorize changing `VITE_FINDER_F4_ENABLED` from its default `0` to
   `1` in a later immutable web build?

### Review dispositions (2026-10-10)

1. **Expose the overall tier before requiring it** → the headline tier is now
   conditional on API `best_tier`; slice 1b exposes the summary field, while F4a
   may land with a number-only headline and no browser tier calculation.
2. **Label no-pick confidence as general evidence** → Any uses **Evidence
   confidence**, selected mode uses **Fit confidence**, and “fit” is forbidden in
   Any visible/accessibility copy.
3. **Bound the all-system selected-archetype query** → B/60 is the default,
   initial choices are B/A/S, and C/D wait for candidate, ordering and count
   bounds; the indexed Any path is called out separately.
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
7. **Expose truncation for selected rankings** → the facade carries page
   metadata, the UI shows count/total/range with offset navigation, URL state
   includes offset, and list/map/truncation update together.
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
11. **Reconcile the 10,000 offset ceiling with selected totals** → selected
    rankings accept unbounded non-negative offsets and return an uncapped exact
    total (`apps/api/src/routers/archetypes.py:348-373`,
    `apps/api/src/routers/archetypes.py:508-530`). F4 preserves that total but
    exposes only the first 10,000 rows: the facade carries the limit, navigable
    total and truncation flag, the UI says **first 10,000 of TOTAL**, and the URL
    codec, request-size clamp, Next state, count, DOM and map all stop together.
12. **Enable F4 in the protected Product E2E build** → the current workflow builds
    with plain `pnpm build` (`.github/workflows/cypress-parity.yml:191-193`), so
    F4b sets `VITE_FINDER_F4_ENABLED: '1'` on that bundle-build step only for the
    protected Chrome/Firefox lane. Production/release builds keep default `0`,
    and the workflow contract files found under `tests/` are updated in the same
    PR with a step-scope assertion.
13. **Preserve the committed anchor while archetype mode is active** → current
    input edits clear the sole anchor
    (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:401-410`,
    `apps/web/src/lib/features/explore/ExploreWorkspace.svelte:429-434`). F4b
    splits draft text from the committed anchor; only suggestion commit or
    explicit reset changes it, returning to Any restores it, and the component
    test pins anchor → archetype → edit draft → Any.
