# V3 Finder Derived-Data Foundation (F1 + F2) — Design

**Date:** 2026-09-16
**Status:** design, pending implementation planning
**Authorities:** [`docs/ROADMAP.md`](../../ROADMAP.md), [`docs/development/v3-search-spatial-derived-data-decision.md`](../../development/v3-search-spatial-derived-data-decision.md), [`docs/development/ratings-v4-freeze/README.md`](../../development/ratings-v4-freeze/README.md), [`docs/development/v3-finder-delivery-plan.md`](../../development/v3-finder-delivery-plan.md)

## Goal

Rebuild the ED-Finder "Finder" in V3 to the capability level of the accepted V2
Finder. The full programme is the delivery plan's F0–F4. **F0 is complete**: the
Ratings V4 economy generation `ratings_v4_prod_p4_parallel_v1`
(`cfc25d36-…`) is VERIFIED and PUBLISHED on production (publication sequence 1,
2026-09-16). This spec covers the next two phases as a single design, to be
implemented as two plans:

- **F1** — the spatial search projection (`004`): `v3_derived.system_search` with
  `cube` + GiST, its chunked builder, and a coverage validator.
- **F2** — the archetype judgement + ranking layer (`005`): per-system
  named-archetype fit scores, summary projections, and a published Finder
  ranking profile.

## Product intent ("similar to V2")

"Similar to V2" means **behavioural / UX parity**, not reproduction of V2's exact
ranking numbers. The two capabilities the user named explicitly:

1. **Body-composition sliders** — adjustable min/max ranges over body counts
   (ELW, water worlds, ammonia, gas giants, terraformable, metal-rich, rings,
   bio/geo signals, landable/walkable, etc.).
2. **Archetype picker** — choose a named archetype (Paradise, Mining Hub,
   Research Hub, Stronghold, Megacomplex, Flexible/Expansion) as a first-class
   search dimension; the Finder finds and ranks systems by fit to it. Archetype
   picker and manual sliders/economy **compose** (either can be used, together or
   alone), matching V2's presets-plus-sliders model.

Ranking numbers come from the frozen **Ratings V4** model — the current scoring
authority. We are **not** chasing V2's numeric order (the decision doc §12 lists
"carrying Ratings V3.4 forward as final V3 scoring authority" as a deliberately
avoided design). A **divergence report** (V2-vs-V3 on a sample) is a low-cost
validation artifact and sanity-check, not an acceptance gate.

## Non-negotiable boundaries (inherited)

From the search/spatial/derived-data decision — this design instantiates that
architecture, it does not change it:

- Ratings V4 is the scoring authority; economy scores are never recomputed here.
- Archetype/ranking are judgement layers on top of V4 and **must not leak
  backwards** into raw economy semantics (decision doc §5).
- Exact spatial truth is Elite `x/y/z` light-year coordinates, never a grid cell.
- Search projections/archetypes/rankings are reproducible derived data, keyed by
  derived generation; a partial/failed build can never become current.
- Finder owns querying/ranking; the renderer never calculates scores/rankings.
- Application SQL uses explicit V3 relations; no `public.*`, no hidden
  `search_path`.

## Architecture

Both layers are new **generation-scoped derived data computed from the published
Ratings V4 generation**, built by the same chunked / resumable / atomically
published pipeline already proven for V4, and versioned independently
(`search_projection_version`, `archetype_version`, `ranking_version`) so any one
can be rebuilt without touching V4 or canonical data.

Mapping the two user-facing capabilities onto the layers:

- **Sliders** → body-count fields are hot, filterable columns in the F1
  `system_search` projection.
- **Archetype picker** → the F2 layer computes a per-system fit score for each
  named archetype; the primary/secondary archetype and Best Colony Potential are
  folded into `system_search` as a summary so the picker filters and ranks fast.

### F1 — `v3_derived.system_search` (`004`)

One row per system per generation (~198.5M rows). Contains only "hot" Finder /
Explore / Inspect facts so request-time queries never join back to canonical.

Columns (grouped):

- **Identity / spatial:** `derived_generation_id`, `id64`, `name`,
  `x_ly / y_ly / z_ly`, `position_ly cube` (**GiST index** for radius / KNN /
  "search around here"), `galaxy_region_id`. PK `(derived_generation_id, id64)`.
- **Slider inputs (body counts):** ELW, water world, ammonia, terraformable,
  gas giant, high-metal, metal-rich, rocky, icy, rings, bio signals, geo
  signals, landable, walkable. (Exact column list finalised against the V2
  slider set during F1 planning.)
- **Display / filter facts:** population, colony status (free / build /
  colonised), main star type, primary economy.
- **Ranking summary (populated by F2):** the seven V4 economy potentials,
  primary / secondary archetype, Best Colony Potential + tier, buildability,
  confidence / completeness.
- **Provenance / freshness fields.**

Indexes are workload-driven: spatial GiST on `position_ly`, name/autocomplete,
region, and proven hot filter/ranking fields. Heavy per-archetype detail stays
in F2's `system_archetype`, not here.

Deliverables: the migration, a **chunked/resumable builder** (V4-runner
pattern), and a **coverage validator** proving every expected system is present
before the generation can publish.

### F2 — archetype + ranking (`005`)

**Named archetype set** (anchored on V4 economies; evidence lifts fit):

| Archetype | Anchor economies | Lifting evidence |
|---|---|---|
| Paradise | Agriculture + Tourism | ELW / water worlds / terraformable |
| Mining Hub | Extraction **+ Refinery (both required)** | reserves, rings, metal-rich bodies |
| Manufacturing Hub | Refinery + Industrial | reserves + build capacity |
| Megacomplex | Extraction + Refinery + Industrial (**all three**) | full vertical chain: reserves + rings + build capacity |
| Research Hub | High-Tech (+ Industrial) | High-Tech potential + capacity |
| Stronghold | Military + Industrial | Military potential + capacity |
| Flexible / Expansion | broad multi-economy | many economies viable at once |

**Fit computation** (all inputs exist in published V4 data):

- relevant V4 `potential_score`s + `specialisation_quality`,
- an explicit synergy rule for the archetype's economy pair,
- buildable capacity from V4 eligible-opportunities data,
- gated by `confidence` / `evidence_completeness` (unknown ≠ absent).

Each system gets, per archetype, an `archetype_score` (0–100) and **tier
S/A/B/C/D** (initial thresholds S≥88 / A≥76 / B≥60 / C≥45 / D else — tunable
config per decision doc §13, not architecture). **Best Colony Potential** = the
highest-scoring archetype, named (headline judgement, decision doc §5).

Storage: `v3_derived.system_archetype` (one row per system per archetype, with
`archetype_version`, score, confidence, explanation JSONB). A summary
(primary / secondary / best) is folded into `system_search`.

**Ranking profile** (`ranking_version`, decision doc §6) — a published profile,
not ad-hoc router SQL. Default profile reproduces V2 feel:

- archetype selected → rank by that archetype's fit, distance tie-break;
- economy selected → rank by that economy's V4 potential;
- neither → rank by Best Colony Potential;
- distance / confidence / completeness as modifiers; sliders are hard filters
  applied first.

This is V2's `COALESCE(archetype_score, economy_score)` semantics expressed as a
versioned profile the API selects.

## Build / validate / publish pipeline

Extends the V4 machinery, following the pipeline order in decision doc §10:
build search features → archetype judgement → summary projections → ranking
profile → **validate** (full ~198.5M coverage, coordinate invariants, score
ranges, reproducibility samples, and query-plan / latency evidence for radius,
KNN and autocomplete) → manifest + receipt → READY → **atomic publish** of the
derived-generation pointer → retain previous generation for rollback. A partial
build can never publish.

Two migrations: `004` (search projection) and `005` (archetype + ranking).

## Validation & parity sanity-check

- **Coverage validator** (hard gate): every expected system present in
  `system_search`; F2 summary present for every system row.
- **Score-range / invariant checks** (hard gate): scores in 0–100, tiers
  consistent, coordinates equal canonical truth, no `public.*` reads.
- **Query-plan / latency evidence** (hard gate): radius, KNN and autocomplete
  use indexes and meet Search budgets.
- **Divergence report** (non-gate): sample of representative anchor + filter +
  archetype queries compared V2-vs-V3, showing where/why order differs. Requires
  a V2 reference source (retained V2 ratings dump, `build_ratings.py` output, or
  captured V2 query results) — **resolved during F2 planning**; not a blocker.

## Out of scope (later phases)

- **F3** — pointing the search API (`/api/local/search`, `/api/search/cluster`,
  autocomplete) at these V3 projections and retiring the dead V2 `public.*` SQL.
- **F4** — the `apps/web` Finder route: the sliders, archetype picker, presets,
  explained result cards, and Inspect/map/save hand-offs.
- Region/cluster search internals beyond what F1 already enables.
- Spatial map pyramid (decision doc §7) and cluster runs (§8) — separate
  derived products.

## Implementation plans (split)

1. **Plan F1** — `004` migration, `system_search` builder, coverage validator,
   query-plan/latency evidence. Buildable and verifiable before F2.
2. **Plan F2** — `005` migration (`system_archetype` + ranking profile),
   archetype builder, summary fold-in to `system_search`, ranking-profile
   definition, divergence report.

F1 is planned and built first because F2's summary columns ride on the
`system_search` row.

## Open items to resolve in planning

1. **Exact slider column set** — reconcile the V2 18-slider list against V4 body
   mechanics inputs to finalise `system_search` body-count columns.
2. **Archetype coefficients / synergy rules** — concrete formulas and tier
   thresholds (config, benchmark-driven; not architecture).
2a. **Archetype set validation** — confirm against real V4 output that each
    archetype surfaces meaningfully distinct systems. The industrial chain is
    modelled as three rungs: "Mining Hub" (Extraction+Refinery, both required —
    never a mining-only system), "Manufacturing Hub" (Refinery+Industrial), and
    "Megacomplex" (Extraction+Refinery+Industrial, all three — the rare full
    vertical chain). Confirm these three surface distinct candidate sets; a true
    Megacomplex system is expected to also score well as Mining Hub and
    Manufacturing Hub, with Best Colony Potential surfacing "Megacomplex" as the
    headline for it.
3. **V2 reference source** for the divergence report.
4. **Search-projection hot-vs-joined boundary** — confirm which summary fields
   live in `system_search` vs `system_archetype` under measured workloads.
