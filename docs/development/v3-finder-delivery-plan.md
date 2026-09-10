# V3 Finder delivery plan

**Status:** plan, not authority. Authorities are
[the roadmap](../ROADMAP.md),
[the search/spatial/derived-data decision](v3-search-spatial-derived-data-decision.md),
[the Ratings V4 freeze](ratings-v4-freeze/README.md) and
[the derived-data completion plan](v3-derived-data-completion-plan.md).

## What "Finder working on V3" means

A user can ask a question in the V3 browser application and get ranked systems
back, with the ranking explained, computed from the V3 canonical generation
rather than from the retired `public.*` schema.

## Current state, verified 2026-09-10

| Layer | State |
|---|---|
| Ranking data | **Absent in production.** No `v3_derived` schema exists there and no derived generation has ever been built. The Ratings V4 storage is written in `003` and unapplied. |
| Search projection | **Not written.** `v3_derived.system_search` with `cube` + GiST is specified in the decision and does not exist as SQL. |
| API | **Split.** `apps/api/src/routers/search.py` exposes `POST /api/local/search`, `/api/search/galaxy` and `/api/search/cluster`. A V3-aware module (`ratings_v4.py`) already reads derived generations, while the older search paths in `local_search.py` and `store.py` still query the V2 schema that production does not have. |
| Browser app | **No Finder.** `apps/web` has `explore`, `inspect` and `spatial-foundation` routes. Finder appears only as an eyebrow label in the Explore workspace. |
| Behaviour to port | The accepted V2 Finder is parity evidence, not the V3 target. Issue #581 ("Svelte product slice: auth, Finder, saved systems and Inspect") tracks the port and is open. |

## Four workstreams

### 1. Ranking data

Apply `003`, then build the search and ranking layer:

- `v3_derived.system_search` — coordinates, `position_ly cube` with a GiST index,
  region and hot facts, keyed by derived generation and `id64`;
- archetype judgement and the summary projections;
- published ranking profiles, per the agreed approach: precomputed values under
  an explicit profile identity as the primary path, query-time adjustment on top.

This is ~198.5M systems. Builds must be chunked, resumable and published
atomically through the lifecycle already designed in `003`.

### 2. Build pipeline

The rating generation runner exists. The search-projection, pyramid and ranking
builders do not, and neither do the per-domain validators that prove every
expected system was covered before publication.

### 3. API

Point the Finder surface at the V3 projections:

- extend the pattern already in `ratings_v4.py`, which reads derived generations;
- retire the V2 `public.*` queries behind the existing search routes rather than
  adding a parallel implementation — the code comment in `search.py` already
  warns about exactly that;
- keep ranking logic out of router SQL; the endpoint selects a published profile
  and applies query-time adjustment, and does not invent ranking expressions.

### 4. Browser application

Add a Finder route to `apps/web` alongside `explore` and `inspect`, preserving the
accepted V2 journey behaviour (query, ranked results, explanation, hand-off into
Inspect and the map) while replacing the implementation. React/R3F is parity
evidence only.

## Sequencing

| Phase | Work | Depends on |
|---|---|---|
| F0 | Reviewed production migration operation; apply `003` and publish a first economy generation | derived-data plan P0/P1 |
| F1 | `004` search projection with GiST; builder and coverage validator; publish | F0 |
| F2 | Archetype judgement, summary projections and published ranking profiles (`005`) | F1 |
| F3 | API search endpoints served from the V3 projections; V2 search SQL retired | F2 |
| F4 | Finder route in `apps/web`, ported behaviour, end-to-end tests | F3 |

A useful property of this order: from F1 onward the API can return real ranked
systems even before the UI exists, so the data can be verified against the
accepted V2 results before any interface work begins.

## Open items

1. **Cluster ownership** — one run per domain, or a shared run with domain
   outputs? The decision allows different domains to publish different cluster
   sets, and Finder ranking does not depend on the answer, but the map does.
2. **Search projection scope** — which facts are "hot" enough to sit in
   `system_search` rather than being joined from the canonical generation.
   Deliberately driven by measured workloads, not guessed.
3. **Parity bar** — how closely Finder must reproduce accepted V2 rankings before
   the port is considered done, and on which sample of systems.

## Acceptance bar

Finder is working on V3 when, against a published derived generation on
production:

- a query returns ranked systems with an explanation;
- results are reproducible from the generation and profile identity alone;
- the app hands off to Inspect and the map with selection continuity;
- no Finder request touches the retired `public.*` schema; and
- the coverage validator proves every expected system was included in the build.
