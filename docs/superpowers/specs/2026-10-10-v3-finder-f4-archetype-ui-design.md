# V3 Finder F4 archetype ranking UI design

## 1. Status

**Status: Design only; not implemented — 2026-10-10 — base `origin/main` `3b6ee91a2e4b076a97a2564cc38310411b534beb`.**

## 2. Goal and non-goals

### Goal

F4 gives the live Svelte application in `apps/web` a Finder archetype picker,
S/A/B/C/D tier and confidence display, primary and secondary archetype labels on
each result, and a **Best Colony Potential** headline. Ranking comes from the V3
ranking API. This is behavioural parity with the accepted V2 journey—choose an
intent, receive explained ranked results, then continue to Inspect and the
map—not numeric parity with V2 scores
(`docs/development/v3-finder-delivery-plan.md:64-76`,
`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:11-19`).

In this document:

- An **archetype** is a named colony pattern, such as Mining Hub, against which a
  system is scored.
- A **tier** is a readable band derived from a 0–100 score: S is the strongest
  band, followed by A, B, C and D
  (`apps/api/src/ranking/profile.py:52-54`).
- **Confidence** says how trustworthy the selected fit is; **completeness** says
  how much of the expected evidence is present. They are not the score and must
  not be presented as certainty
  (`apps/api/src/models.py:264-271`).
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

The dated roadmap correctly records that F4 follows F2c/F3, but its statement
that no archetype-ranking API exists is now superseded by current main: the
roadmap snapshot says the gap was gated
(`docs/ROADMAP.md:209-219`), while the handlers below prove that F3 slice 1 has
since landed.

## 3. What exists today

### API and ranking data

| Surface | Current implementation | Consequence for F4 |
|---|---|---|
| `POST /api/local/search` | The route delegates to `local_db_search_v3` (`apps/api/src/routers/search.py:157-203`, `apps/api/src/routers/search.py:243-245`). That implementation reads V3 search and archetype-summary projections through the ranking query, pins one published generation, and emits ranking identity (`apps/api/src/local_search.py:843-850`, `apps/api/src/local_search.py:925-963`). | Available now for **Any** (no selected archetype). |
| `GET /api/archetypes/rankings` | The handler validates one of the eight V3 keys, passes it as `picked_archetype`, and reads in one repeatable-read snapshot (`apps/api/src/routers/archetypes.py:294-405`). | Available now for a selected archetype. |
| `POST /api/archetypes/rerank` | The handler reads `system_archetype_scores` and other legacy relations (`apps/api/src/routers/archetypes.py:535-590`). | Not usable; wait for slice 2. |
| `GET /api/archetypes/system/{id64}` | The current handler reads legacy systems/archetype/topology relations (`apps/api/src/routers/archetypes.py:635-719`). | No V3 per-system explanation drawer yet; wait for slice 2. |
| `POST /api/archetypes/simulate` | The current handler reads legacy `system_archetype_scores` (`apps/api/src/routers/archetypes.py:905-929`). | Not usable; wait for slice 2. |
| `GET /api/archetypes/profiles` | It returns static legacy preset data, including the old archetype set (`apps/api/src/routers/archetypes.py:114-171`, `apps/api/src/routers/archetypes.py:989-1005`). | It must not populate the V3 picker. |
| `/api/search/galaxy` and `/api/search/cluster` | The module deliberately leaves both on the older implementation pending slice 2 (`apps/api/src/local_search.py:574-586`). | Not part of F4a/F4b. |

Both usable ranked paths fail explicitly when the published generation lacks
READY `system_search` or `system_archetype` products, instead of presenting a
false empty result (`apps/api/src/local_search.py:602-643`).

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

### Current `apps/web` Finder flow

The client-only `/explore` route renders `ExploreWorkspace`
(`apps/web/src/routes/explore/+page.svelte:1-5`,
`apps/web/src/routes/explore/+page.ts:1-2`). The workspace holds the query,
anchor, selection and map state locally and has no archetype, tier or weight
state (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:65-113`).

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
3. No facade normalizer or query key for `/api/archetypes/rankings`.
4. `ExploreSystem` omits `confidence` and `completeness`.
5. The two slice-1 response shapes and search scopes are not reconciled.
6. Finder query state is not URL-backed or shareable.
7. Result rows omit tier, score, confidence/completeness, primary/secondary and
   Best Colony Potential.
8. Ranking loading, empty and error messages do not name the active archetype or
   explain whether the ranking service is unavailable.
9. No F4 state, component, Cypress or visual-regression coverage.
10. V3 explanations, custom reranking and simulation are still blocked on slice
    2, as the handler inventory above shows.

## 4. API dependency map

| UI element | Endpoint and field available today | Availability and design rule |
|---|---|---|
| Picker: **Any** | `POST /api/local/search`; no archetype request field (`apps/api/src/models.py:537-564`). | Slice 1 now. “Any” uses the current default ranking. |
| Picker: one of eight archetypes | `GET /api/archetypes/rankings?archetype=…`; key validation and profile query are in `apps/api/src/routers/archetypes.py:294-364`. | Slice 1 now. Initial selected-archetype mode is explicitly galaxy/Sol-oriented, because this endpoint has no arbitrary anchor. |
| Tier badge | Any: `results[].archetype_tier`; selected: `results[].tier` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:880-892`). | Slice 1 now. The facade normalizes both to one `tier` view field. |
| Minimum tier | Any: `min_development_score`; selected: `min_score` (`apps/api/src/models.py:551-555`, `apps/api/src/routers/archetypes.py:508-518`). | Slice 1 now. Translate S/A/B/C/D to 88/76/60/45/0. Explicitly send `min_score=0` for D; the rankings endpoint otherwise defaults to 40 and hides part of D (`apps/api/src/routers/archetypes.py:510-518`). |
| Confidence badge | Both paths return `confidence` and `completeness` (`apps/api/src/models.py:264-271`, `apps/api/src/models.py:898-902`). | Slice 1 now. Never synthesize a missing value. |
| Primary/secondary | Both paths return `primary_archetype` and `secondary_archetype` (`apps/api/src/models.py:238-243`, `apps/api/src/models.py:886-893`). | Slice 1 now. Use canonical labels, not underscore replacement. |
| **Best Colony Potential** headline | Both paths return `overall_development_potential`, sourced from the summary’s best potential (`apps/api/src/local_search.py:806-815`, `apps/api/src/routers/archetypes.py:472-482`). | Slice 1 now. In selected mode, distinguish the selected-fit `score` from the overall headline. |
| Weight sliders | Current `/api/archetypes/rerank` uses legacy relations and legacy five-weight models (`apps/api/src/routers/archetypes.py:535-590`, `apps/api/src/models.py:744-763`). | Needs slice 2. Reserve layout only; do not call it. **Unverified:** the eventual V3 weight dimensions are not defined in current code. |
| Per-archetype explanation | The V3 product stores explanation data (`docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md:73-77`), but `/system/{id64}` is legacy today (`apps/api/src/routers/archetypes.py:635-719`). | Needs slice 2. Do not show legacy rationale as V3 explanation. |
| Rerank action | Intended endpoint is `POST /api/archetypes/rerank`; its current implementation is legacy (`apps/api/src/routers/archetypes.py:535-628`). | Needs slice 2. |
| Simulation | Intended endpoint is `POST /api/archetypes/simulate`; its current handler reads legacy data (`apps/api/src/routers/archetypes.py:905-929`). | Needs slice 2 and is not required for the first Finder UI. |

Therefore the UI increment buildable **now** against main is: Any plus the eight
archetype choices; a minimum-tier filter; normalized ranked cards; selected and
overall scores; tier, confidence/completeness and primary/secondary labels; URL
state; and unchanged selection, Inspect and map hand-offs. Wired weights,
per-archetype explanations, V3 reranking and simulation are later increments.

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

| Key | Display name | One-line description |
|---|---|---|
| `paradise` | Paradise World | Agriculture and Tourism working together for a habitable destination. |
| `mining_hub` | Mining Hub | Extraction and Refinery strength for a resource-processing centre. |
| `manufacturing_hub` | Manufacturing Hub | Refinery and Industrial strength for sustained production. |
| `megacomplex` | Megacomplex | A complete Extraction, Refinery and Industrial chain. |
| `research_hub` | Research Hub | High Tech potential supported by Industrial capacity. |
| `stronghold` | Stronghold | Military and Industrial strength for a defended base. |
| `population_capital` | Population Capital | Agriculture and High Tech supporting a large population centre. |
| `flexible` | Flexible Multi-Role Colony | Several viable economies rather than one narrow specialism. |

The minimum-tier control is a native `<select>` labelled **Minimum tier**, with
options “Any tier (D or better)”, C, B, A and S. “Minimum” is explicit so the
control does not imply a non-contiguous multi-select that neither slice-1
endpoint supports.

When the user chooses an archetype while a known-star anchor is active, F4b must
not pretend the archetype results are centred on that star. The initial design
switches the result heading to **Galaxy-wide [Archetype] ranking**, keeps the
anchor text in the input as an inactive draft, and displays: “Archetype ranking
is galaxy-wide today; choose Any to search around [star].” Returning to Any
restores the anchored query. This behaviour is removable when the API accepts a
picked archetype and arbitrary reference coordinates.

### Result row/card anatomy

Each result remains one native `<li>` containing the existing selection button,
Inspect link and actions. Inside the selection button, render items 1–5 in this
order; keep item 6 after the button as it is today:

1. System name and id64.
2. **Best Colony Potential: _N_ · _tier_ tier**. This is the headline overall
   value, not a locally calculated score.
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

| Tier | Proposed token | Intended colour |
|---|---|---|
| S | `--color-tier-s` | bright orange, based on `--color-signal` |
| A | `--color-tier-a` | cyan, based on `--color-cyan` |
| B | `--color-tier-b` | accessible green |
| C | `--color-tier-c` | accessible amber |
| D | `--color-tier-d` | muted neutral, based on `--muted` |

The badge uses a visible border, tier letter and full accessible name. Do not
use star icons or colour alone to encode order. Preserve the existing global
focus ring (`apps/web/src/app.css:41-44`). Exact B/C hues are a visual-validation
decision, not a domain contract.

### Honest uncertainty

Display one evidence badge derived only from the API’s selected-fit `confidence`
and `completeness` fields:

| Condition | Wording |
|---|---|
| either value missing | **Evidence unknown** |
| either value below 0.50 | **Limited evidence** |
| both values at least 0.80 | **Strong evidence** |
| otherwise | **Moderate evidence** |

Its accessible description gives both raw percentages: “Fit confidence 82%;
evidence 64% complete.” The thresholds above are a presentation decision and
must be unit tested; they do not alter ranking. `archetype_confidence` has a
different meaning—the separation between the primary and secondary
classification—and may be shown separately as **Clear primary fit** or **Close
alternative**, but must not be folded into the evidence badge
(`apps/api/src/routers/archetypes.py:433-459`).

### Loading, empty and error states

- Loading: retain `aria-busy` on the result region and a `role="status"` message,
  naming the active mode: “Ranking systems for Manufacturing Hub…” Existing
  result loading already uses those semantics
  (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:743-763`).
- Empty: “No systems meet minimum tier B for Manufacturing Hub.” Include
  **Show all tiers** and **Choose Any** actions. Empty is not an error.
- Error: `role="alert"`, “Archetype rankings are unavailable,” a Retry button,
  and the current selection/map retained. Existing error state already has an
  alert and retry pattern
  (`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:764-780`).
- Stale transition: keep previous rows visibly marked “Updating…” while the new
  query is in flight; never relabel old rows as the newly selected archetype.

### Keyboard and screen readers

The native radio group supports Tab into the group and arrow-key choice; the
native select supports ordinary platform keyboard behaviour. On a committed
choice, keep focus on the changed control and announce the loading/result count
through a polite `role="status"` live region. Do not move focus to the first row
for a picker-only rerank; the existing automatic first-result focus is limited to
completion of a newly chosen anchor
(`apps/web/src/lib/features/explore/ExploreWorkspace.svelte:389-399`).

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
  archetype: 'any' | ArchetypeKey;
  minimumTier: 'S' | 'A' | 'B' | 'C' | 'D';
  weights: Readonly<Record<string, number>>; // empty until slice 2
}>;
```

The URL is the source of truth for shareable ranking state:

| State | Canonical query form | Rules |
|---|---|---|
| Any archetype | omit `archetype` | Default. `archetype=any` canonicalizes to omission. |
| Selected archetype | `archetype=manufacturing_hub` | Accept only the eight current keys. Unknown values fail closed to Any and show a non-blocking “unsupported link option” status. |
| Minimum tier | `min-tier=B` | Omit D, the default. Map S/A/B/C/D to 88/76/60/45/0. Reject repeated or unknown values rather than guessing. |
| Future weights | repeated, key-sorted `weight=<dimension>:<basis-points>` | Example only: `weight=capacity:2500`. Values are integers 0–10000 to avoid float serialization drift. Do not parse or emit until slice 2 defines allowed keys and total rules. **Unverified:** dimension identifiers. |
| Selected system | existing `system=<id64>` | Preserve current overlay/selection meaning (`apps/web/src/lib/components/AppShell.svelte:19-43`). It is not a ranking input. |

Serialize keys in the table’s order and weights lexicographically so copying the
same state produces one stable URL. Picker and minimum-tier commits create a
history entry; Reset creates one history entry; future slider edits remain local
draft state until Apply. Preserve unrelated query parameters.

The initial archetype mode is intentionally galaxy-wide. The current anchor is
not added to this new contract because its exact shared reconstruction and its
combination with selected-archetype ranking are not supported by the slice-1 API.
**Unverified:** a future unified request may add `near=<id64>` after a V3 exact
system lookup and arbitrary-reference archetype ranking exist.

Do not persist ranking state separately in local storage: the URL is sufficient
and avoids a hidden preference overriding a shared link. Continue to persist only
the selected system through the existing validated store
(`apps/web/src/lib/persistence/stores.ts:107-112`). If the owner later chooses to
remember Finder defaults across sessions, add a named key, versioned codec and
context-provided store following the central pattern
(`apps/web/src/lib/persistence/storage.ts:84-110`,
`apps/web/src/lib/persistence/context.ts:7-20`); never access `localStorage`
directly from the component.

## 7. Validation plan

### Unit tests (Vitest)

Vitest is the app’s unit runner (`apps/web/package.json:18-20`). Add pure tests
for:

- the exact eight-key metadata inventory and label lookup;
- tier-to-minimum-score mapping at 88/76/60/45, while displayed result tiers
  remain the API's value;
- confidence/completeness wording at missing, 0.50 and 0.80 boundaries;
- URL parse/serialize round trips, canonical ordering, defaults, duplicate and
  unknown parameters, and preservation of unrelated parameters;
- request selection: Any → local search, key → rankings, D → explicit score 0;
- ranking-row normalization (`score` → selected score,
  `distance_to_sol` → distance) and lossless id64 handling;
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
- loading `status`, empty actions, error `alert` and Retry;
- focus remains on the picker during rerank;
- selected row and Inspect href remain unchanged;
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
   `/api/archetypes/rankings` request uses `min_score=0`;
4. asserts ordered results show selected score/tier, Best Colony Potential,
   evidence wording and primary/secondary text;
5. selects a row, verifies the same map target and Inspect URL, runs axe, reloads
   the share URL, and repeats the state assertion;
6. captures approved 1280×800 and 390×844 screenshots with animation disabled.

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

### PR F4a — typed ranking foundation (buildable against main today)

Exact files:

- create `apps/web/src/lib/features/explore/archetypes.ts`
- create `apps/web/src/lib/features/explore/archetypes.test.ts`
- create `apps/web/src/lib/features/explore/ranking-state.ts`
- create `apps/web/src/lib/features/explore/ranking-state.test.ts`
- modify `apps/web/src/lib/api/client.ts`
- modify `apps/web/src/lib/api/client.test.ts`
- modify `apps/web/src/lib/api/query.ts`
- modify `apps/web/src/lib/api/query.test.ts`
- modify `tests/test_seed_cypress_v3_generation.py`

Deliver the canonical metadata, URL codec, tier/evidence presentation helpers,
lossless rankings facade normalizer, `ExploreSystem` confidence/completeness and
the ranking query key. Extend the isolated-PostgreSQL seed test to pin all three
Product systems' ranking fields before Cypress relies on exact values. Do not
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
- modify `apps/web/src/app.css`
- modify `apps/web/cypress/e2e/product-journey.cy.ts`

Add URL-synchronized picker/minimum tier, branch Any to local search and a key to
rankings, render the normalized card, reserve the weight-tools layout slot, and
leave the map/Inspect plumbing unchanged. Required proof: focused component
tests; full Svelte web checks; OpenAPI drift; **Svelte Web E2E** in Chrome and
Firefox (the protected matrix is at `.github/workflows/cypress-parity.yml:21-30`);
axe; approved desktop/mobile screenshots; and unchanged Review Lab.

### PR F4c — consistent archetype labels in saved surfaces

Exact files:

- modify `apps/web/src/lib/features/explore/compare-metrics.ts`
- modify `apps/web/src/lib/features/explore/compare-metrics.test.ts`
- modify `apps/web/src/lib/features/explore/WatchlistPanel.svelte`
- modify `apps/web/src/lib/features/explore/WatchlistPanel.test.ts`

Replace duplicated/underscore-derived labels with the canonical F4 metadata.
Compare currently has its own mapping and tier thresholds
(`apps/web/src/lib/features/explore/compare-metrics.ts:17-28`,
`apps/web/src/lib/features/explore/compare-metrics.ts:50-63`); preserve historical
unknown keys as readable fallbacks rather than pretending they are V3 keys.
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
  selected mode, and no claim of arbitrary-anchor ranking.
- **Misleading scores:** selected-archetype score and Best Colony Potential can
  differ. Mitigation: label both and never use one value under both headings.
- **False certainty:** a high score can have thin evidence. Mitigation: always
  show confidence/completeness wording and keep classification confidence
  separate.
- **Incomplete D results:** the rankings endpoint’s default floor is 40.
  Mitigation: explicitly request zero for minimum tier D.
- **Fixture drift:** current fixture archetype outputs are generated but not
  pinned. Mitigation: add the database fixture-output contract before exact E2E
  assertions.
- **Visual density:** nine choices plus tier controls can crowd narrow screens.
  Mitigation: wrap into a one-column mobile radio list and validate 390×844.
- **Legacy leakage:** generated methods exist for legacy-backed endpoints.
  Mitigation: expose only the two verified slice-1 facade methods until slice 2.

### Owner questions

Answer each with **yes/no** or one listed choice:

1. **Choose one:** ship F4a/F4b now on slice 1 with selected archetypes explicitly
   galaxy-wide; or wait until `/api/local/search` accepts an archetype plus an
   arbitrary reference point?
2. **Yes/no:** should the UI always show a tier when evidence is limited, provided
   it also shows **Limited evidence** and never hides confidence/completeness?
3. **Choose one:** should the archetype picker sit beside the existing known-star
   anchor (recommended by this design), or replace the anchor while an archetype
   is active?
4. **Choose one:** use a single **Minimum tier** control supported by slice 1, or
   defer tier filtering until the API supports arbitrary tier sets?
5. **Yes/no:** should exact Cypress archetype outputs become a committed
   fixture-contract gate before F4b merges?
6. **Choose one:** land F3 slice 2 after the first visible UI PR (this design), or
   require it before any F4 UI work?
7. **Yes/no:** should primary/secondary classification confidence get a separate
   “clear/close fit” label in F4b, in addition to the evidence badge?
8. **Choose one:** keep future custom weights URL-only, or also remember them as a
   validated local preference after slice 2?
