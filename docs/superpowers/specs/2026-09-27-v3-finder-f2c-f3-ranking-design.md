# V3 Finder F2c (ranking profile) + F3 (API cutover) — Design

**Date:** 2026-09-27
**Status:** design, pending implementation planning
**Authorities:** [`docs/ROADMAP.md`](../../ROADMAP.md), [`docs/development/v3-search-spatial-derived-data-decision.md`](../../development/v3-search-spatial-derived-data-decision.md) (§6 ranking), [`docs/development/v3-finder-delivery-plan.md`](../../development/v3-finder-delivery-plan.md) (phases F2c/F3), the F2 design [`2026-09-16-v3-finder-f2-archetype-ranking-design.md`](2026-09-16-v3-finder-f2-archetype-ranking-design.md), and the frozen Ratings V4 mechanics [`ratings-v4-freeze/README.md`](../../development/ratings-v4-freeze/README.md).

## Goal

Make the V3 Finder actually rank systems from the V3 derived projections. F2b (merged, #771) computes the archetype fits (`v3_derived.system_archetype` + `system_archetype_summary`); F1 (#734) built `system_search` (facts + body-type counts). **F2c** defines the single, versioned **ranking profile** that turns those projections into an ordering; **F3** repoints the Finder API off the legacy V2 relations onto those projections through the profile. Together they unblock the Finder UI (F4).

## Principle: V3-native ranking, not a V2 copy

This is **behavioural parity, not numeric parity**. We keep the *interaction* users know — pick an archetype (or economy, or neither) → ranked results with S/A/B/C/D tiers, primary/secondary archetype, a headline "Best Colony Potential" — but the ranking is computed from V4's honestly-better signals, not V2's `mv_archetype_rankings` columns:

- ranks over the **redesigned V4 fit model** (F2b: weakest-link economy core, `specialisation_quality` — V4's honest successor to V2's "top-two purity" hack, bounded synergy);
- **honest uncertainty is first-class**: `confidence` and `evidence_completeness` modify the ranking (unknown ≠ absent) — V2 had no honest uncertainty, so a thinly-observed system could masquerade as a top result;
- **8 V3-native archetypes** + `best_colony_potential`, not V2's 10 legacy score columns.

The retained V2 numeric outputs are **not** the target; a divergence report against them is a deferred, non-gate sanity check (see below).

## F2c — the ranking profile

### Identity & storage (decided)

The ranking profile is a **versioned code definition**, not a DB row. Rationale: ranking is an algorithm (order-by expression + hard-filter order + modifiers) plus a few parameters — a DB row could only hold the parameters and would split logic (code) from params (DB), inviting the desync class of bug seen elsewhere (a manifest field-policy drifting from the actual computation). Instead we follow the codebase's proven governance pattern (`code_identity`, manifest sha):

- `ranking_version = "v3-colony-potential-1"`.
- The profile's canonical definition (its ordered ranking spec — selected-score resolution, modifier, tie-break, hard-filter list, and the parameter values) is hashed into a **recorded profile sha** (`ranking_sha256`).
- Every ranked response and any receipt records `{ranking_version, ranking_sha256, derived_generation_id, publication_sequence}` so an ordering is reproducible and auditable from identity alone.
- A **drift-guard test** asserts the recorded `ranking_sha256` equals the sha recomputed from the live profile definition — so the version can never silently diverge from its identity.
- **Forward-compatibility:** if operator/non-engineer live-tuning is ever needed, a `ranking_version` can later resolve to a governed DB row *behind the same identity interface* — callers and the reproducibility contract don't change. We start with pinned code because ranking is product behaviour that should go through review/CI/deploy.

The profile lives in a dedicated module under `apps/api/src/` (e.g. `apps/api/src/ranking/`), exposing a small interface the routers call. **Routers select a `ranking_version` and pass query params; they never hand-write `ORDER BY`** (decision doc §6 boundary #6).

### The `v3-colony-potential-1` definition

Applied query-time over the published `v3_app.*` views (`system_search`, `system_archetype`, `system_archetype_summary`), generation-pinned exactly like `ratings_v4.py`/`map.py` (single join to `v3_meta.current_derived_generation`; the `v3_app.*` views already embed it).

**1. Hard filters, applied first** (a system is a candidate or it isn't):
- F1 body-count sliders / feature requirements (`elw_count`, `ww_count`, `terraformable_count`, `landable_count`, `has_rings`, bio/geo signal minima, etc.) from `system_search`;
- `min_development_score` floor;
- distance bound (from a reference system) and region filter.

**2. Primary score selection** (the V2-shape COALESCE, over V3 signals):
- **archetype picked** → that archetype's `system_archetype.archetype_score`;
- **economy picked** → that economy's V4 `potential_score` (from the rating vector);
- **neither** → `system_archetype_summary.best_colony_potential`.

**3. Uncertainty as a soft modifier** (the V3 signature — decision: soft, not a hard gate):
- multiply the primary score by an uncertainty factor derived from `confidence × completeness` (archetype `confidence` when an archetype is picked; `system_search.completeness`/`confidence` for the system generally) so that, at equal raw score, better-observed systems rank higher — **nothing is filtered out for being under-observed** (unknown ≠ absent). The exact factor curve is a profile parameter, benchmark-tuned (like the F2b coefficients), and part of the hashed identity.

**4. Tie-break:** distance from the reference (ascending), then `system_id64` for determinism.

**5. Payload:** each result carries `archetype_score`/`best_colony_potential`, `tier` (S≥88/A≥76/B≥60/C≥45/D — from the projection), `primary_archetype`/`secondary_archetype`, and a **confidence badge** (`confidence`, `completeness`) so the UI can show honest uncertainty. The response echoes the ranking identity block from §Identity.

### Divergence report — deferred (non-gate)

The F2 design's V2 divergence report is a **non-gate sanity check** and V2 is decommissioned (its reference relations — `mv_archetype_rankings`, `system_archetype_scores`, and the `build_archetype_scores.py` inputs `bodies`/`ratings`/`system_slot_topology` — live only in the offsite dump / a lab, not in prod). Since V3 is *intentionally* divergent from V2, a numeric diff now is low value and would gate on unavailable data. **F2c ships the ranking profile; the divergence report is a deferred follow-up** to run against the offsite/lab V2 data if a sanity check is wanted. This is recorded here so it is not silently dropped.

## F3 — repoint the Finder API (sliced)

Move the Finder read surface off the legacy V2 relations (`systems`, `ratings`, `mv_archetype_rankings`, `system_archetype_scores`, `system_archetype_traits`, `cluster_summary`) onto the V3 `v3_app.*` projections through the ranking profile, generation-pinned like the reference implementations (`ratings_v4.py`, `map.py`). Ranking logic moves into the profile module; routers become thin (select version + params, shape the response).

Delivered in slices so it stays shippable and unblocks the UI early:

- **Slice 1 (unblocks the Finder UI):**
  - `POST /api/local/search` — the main ranked search: hard filters + `v3-colony-potential-1` ordering over `v3_app.system_search` + `system_archetype(_summary)`, generation-pinned. Retire the `systems`/`ratings`/`mv_archetype_rankings` joins and the legacy `finder_score_expr` from `local_search.py`.
  - `GET /api/archetypes/rankings` — rank-by-selected-archetype: repoint from `mv_archetype_rankings` to `v3_app.system_archetype` for the selected key via the profile.
- **Slice 2+ (follow-on, not blocking the UI):** `POST /api/archetypes/rerank` (slider weights over V3 fields), `GET /api/archetypes/system/{id64}` (per-archetype detail from `system_archetype` + `explanation`), `POST /api/search/cluster`, `POST /api/archetypes/simulate`, `POST /api/search/galaxy`.

Each slice: generation-pinned reads, no `public.*`/legacy relation, ranking via the profile, the ranking-identity block on responses, and contract tests. Endpoints for which the V3 projection has no equivalent yet (e.g. topology/slot detail used by `/system` and `/simulate`) are explicitly flagged in that slice rather than silently degraded.

## Data available (from the merged projections)

- `v3_app.system_archetype`: per `(system, archetype_key)` → `archetype_score` (0–100), `tier`, `confidence` (0–1), `explanation` jsonb.
- `v3_app.system_archetype_summary`: per system → `primary_archetype`, `secondary_archetype`, `best_colony_potential`, `best_tier`, `archetype_confidence`.
- `v3_app.system_search`: coords + `position_ly` (GiST), region, `main_star_class`, body/station counts, `has_*` flags, per-body-type counts, `completeness`, `confidence`.
- Per-economy `potential_score`/`specialisation_quality` via the rating vector (`ratings_v4.py`).
- Generation resolution: the `v3_app.*` views join `v3_meta.current_derived_generation` (published generation, seq); the published generation is `ratings_v4_prod_p4_parallel_v1` (seq 1). **Note:** the archetype product is not yet *built* in prod (F2b builder merged as code; the governed build/publish is a separate op) — so slice-1 in prod returns archetype fields only once that build runs; against the disposable PG18 fixture it works today.

## Testing

- **Profile unit tests** (no DB): the ordering expression, hard-filter precedence, the uncertainty modifier, tie-break, and tier mapping produce the specified order on constructed inputs; the drift-guard test (recorded `ranking_sha256` == recomputed).
- **API contract tests** (disposable PG18 fixture, the `canonical_database` + ratings/search/archetype build path used by `test_ratings_v4_system_search.py`): each repointed endpoint returns generation-pinned results ordered per the profile, carries the ranking-identity block, reads no legacy/`public.*` relation, and honours hard filters. Reuse the F2b builder to populate `system_archetype` in the fixture.
- **No-legacy assertion:** a test that the repointed router modules contain no `mv_archetype_rankings`/`system_archetype_scores`/`public.` read in the F3-migrated paths.

## Out of scope

- **F4** — the `apps/web` Finder UI (archetype picker + weight sliders + tiers). Unblocked by F2c + F3 slice 1.
- The **governed production build/publish** of the `system_archetype` product (an operator op) and the **coefficient-calibration probe** (authorized read-only prod sample) — pre-existing follow-ups, not part of F2c/F3.
- The **divergence report** run (deferred, non-gate, needs V2 reference data).

## Open items to resolve in planning

1. The exact **uncertainty-modifier curve** (how strongly `confidence × completeness` scales the score) — a benchmark-tuned profile parameter; start conservative and fold into the hashed identity.
2. Whether `GET /api/archetypes/system/{id64}` and `/simulate` need any topology/slot data the V3 projections don't yet expose — if so, flag as a data gap for a later derived product rather than keeping a legacy join.
3. Response-model shape: extend the existing `SearchResponse`/`ArchetypeRankingsResponse` with the ranking-identity block + confidence badge vs. new models (prefer extending, per the generated-facade contract).
