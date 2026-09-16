# V3 Finder F2 — Archetype Judgement + Ranking Layer — Design

**Date:** 2026-09-16
**Status:** design, pending implementation planning
**Authorities:** [`docs/ROADMAP.md`](../../ROADMAP.md), [`docs/development/v3-search-spatial-derived-data-decision.md`](../../development/v3-search-spatial-derived-data-decision.md) (§5 archetypes, §6 ranking), [`docs/development/ratings-v4-freeze/README.md`](../../development/ratings-v4-freeze/README.md), [`docs/development/ratings-v4-data-contract.md`](../../development/ratings-v4-data-contract.md) (§8 archetype boundary), [`docs/development/v3-finder-delivery-plan.md`](../../development/v3-finder-delivery-plan.md) (phase F2), and the F1+F2 foundation spec [`2026-09-16-v3-finder-derived-foundation-design.md`](2026-09-16-v3-finder-derived-foundation-design.md).

## Goal

Phase **F2** of the V3 Finder rebuild: a new **archetype judgement + ranking**
layer computed from the published Ratings V4 generation. It gives every system a
per-archetype *fit* score, a headline **Best Colony Potential**, and a published
**ranking profile** the Finder API uses to order results — reproducing the V2
Finder's *behaviour* (named archetypes you can pick, S/A/B/C/D tiers,
primary/secondary, `COALESCE(archetype_score, economy_score)` ranking) on V4's
cleaner inputs. F1 (`system_search` + body-type counts) is merged; F2 builds on
it and computes independently from V4.

## Decisions (settled in brainstorming)

1. **Lean, V4-native fit model** — not a reconstruction of v3.4's topology /
   pair-synergy / strategic tables (which V4 deliberately dropped). Fit is
   computed from V4 per-economy `potential_score` + `specialisation_quality` +
   `economy_opportunity` (buildable capacity), a defined per-archetype synergy
   rule, gated by `confidence`/`evidence_completeness`.
2. **8 archetypes** — the 7 from the foundation spec **plus Population Capital**.
   AX Forward Base deliberately excluded (niche/Thargoid-war themed; tunable to
   add later). Set + coefficients are versioned config (decision doc §13), not
   architecture.
3. **Behavioural parity, not numeric** — V4 is the scoring truth; a divergence
   report vs the retained V2 archetype outputs is a sanity-check, not a gate.
4. **Stored as a derived product** (like `system_search`), migration `011`, with
   a **separate summary table** so F1's `system_search` is not re-versioned.
5. **Tier thresholds** start at V2's S≥88 / A≥76 / B≥60 / C≥45 / D (tunable).

## The 8 archetypes

| key | name | anchor economies | lifting evidence |
|---|---|---|---|
| `paradise` | Paradise | Agriculture + Tourism | ELW / water worlds / terraformable |
| `mining_hub` | Mining Hub | Extraction + Refinery (both required) | reserves, rings, metal-rich |
| `manufacturing_hub` | Manufacturing Hub | Refinery + Industrial | reserves + build capacity |
| `megacomplex` | Megacomplex | Extraction + Refinery + Industrial (all three) | full vertical chain |
| `research_hub` | Research Hub | High-Tech (+ Industrial) | High-Tech potential + capacity |
| `stronghold` | Stronghold | Military + Industrial | Military potential + capacity |
| `population_capital` | Population Capital | Agriculture + High-Tech | feed-a-high-tech-population hub |
| `flexible` | Flexible / Expansion | broad multi-economy | many economies viable at once |

`v3-archetype-1` validates against V4 that these surface distinct candidate sets
(esp. the Mining/Manufacturing/Megacomplex chain); merge/adjust is config, not a
schema change.

## Fit model (per system per archetype → `archetype_score` 0–100)

Inputs, all from the pinned V4 generation keyed by `(derived_generation_id, system_id64)`:
`v3_derived.system_economy_rating` (per-economy `potential_score`,
`specialisation_quality`, `evidence_completeness`, `confidence`) and
`v3_derived.economy_opportunity` (per eligible body×economy: `native`,
`modifier`, `local_score`).

For an archetype with anchor economies `A` (1–3):

1. **Economy core** — combine the anchors' `potential_score` with a
   **weakest-link bias** so all anchors must be viable: e.g.
   `core = α·min(pot[a]) + (1-α)·mean(pot[a])` (α ≈ 0.6). A single weak anchor
   caps the archetype.
2. **Specialisation factor** — the anchors' `specialisation_quality` (V4's honest
   successor to V2 purity/top-two): scales `core` toward its ceiling when the
   anchors can be made dominant. Where `specialisation_quality` is NULL (bounded
   min<max), use the midpoint and lower confidence — never invent a penalty.
3. **Synergy bonus** — a small bounded bonus (F2-defined per archetype, since V4
   has no synergy table) when *all* anchors clear a threshold together.
4. **Buildable-capacity factor** — from `economy_opportunity`: eligible
   opportunity count + mean `local_score` for the anchor economies scales the
   score down when capacity is thin (few/weak buildable bodies).
5. **Gating / confidence** — `min(confidence[a])` and
   `min(evidence_completeness[a])` produce the archetype's output `confidence`;
   low completeness widens uncertainty, it does not fabricate a score penalty
   (unknown ≠ absent).

`flexible` is the special case: no fixed anchors → score rewards **breadth**
(count of economies with `potential_score` and `specialisation_quality` above a
threshold), the V4-native analogue of V2's `flexible_multirole` diversity.

Outputs per system per archetype: `archetype_score` (0–100), **tier**
(S≥88/A≥76/B≥60/C≥45/D), `confidence`, and an `explanation` JSONB (which anchors
drove it, the component values). **Best Colony Potential** = the highest
`archetype_score`, with the winning archetype named; `archetype_confidence`
follows V2's separation idea: `min((score1−score2)/max(score1,1)·2, 1)`.

Exact coefficients (α, synergy sizes, capacity curve, thresholds) are
benchmark-driven config resolved in planning, not architecture.

## Architecture (instantiates decision doc §5/§6, mirrors the `system_search` product)

### Migration `011` — `011_v3_system_archetype.sql`

- `v3_derived.system_archetype` — PK `(derived_generation_id, system_id64,
  archetype_key)`; `archetype_version text`, `archetype_score smallint CHECK 0–100`,
  `tier text CHECK IN (S,A,B,C,D)`, `confidence double precision 0–1`,
  `explanation jsonb`, `computed_at timestamptz`. FK to
  `system_rating_vector(derived_generation_id, system_id64)` deferrable.
- `v3_derived.system_archetype_summary` — one row per system: `primary_archetype`,
  `secondary_archetype`, `best_colony_potential smallint 0–100`, `best_tier`,
  `archetype_confidence double precision`. The hot Finder read.
- `v3_derived.archetype_build_chunk` — per-chunk build receipt (mirrors
  `search_build_chunk`), for resumable chunked builds + coverage validation.
- Insert-only write guards on the new relations (same pattern as `004`/`006`).
- `v3_app.system_archetype` and `v3_app.system_archetype_summary` published views
  (resolve `current_derived_generation`).
- Migration ships as a committed file; its **manifest declaration + authority
  refresh is deferred to the governed migration operation** (same rule F1's `010`
  followed — declaring it changes the reviewed desired-schema identity).

### Builder — `scripts/v3_system_archetype.py` (product `system_archetype`, `archetype_version = v3-archetype-1`)

Mirrors `scripts/v3_system_search.py`: `register_product` → `build_available`
(consume committed Ratings chunks lacking an archetype receipt; per chunk read
`system_economy_rating` + `economy_opportunity`, compute all 8 archetype fits per
system, write `system_archetype` rows + the summary row, seal the chunk) →
`validate_product` (coverage, score-range/tier invariants, reproducibility) →
publish through the `006` product gate. Never publishes on its own; the full
build/publish is a governed operator op like F1/V4.

### Ranking profile — `ranking_version`

A published profile the API selects (decision doc §6), reproducing V2's default:
- **archetype picked** → order by that `archetype_score` (from `system_archetype`),
  distance tie-break;
- **economy picked** → order by that economy's V4 `potential_score`;
- **neither** → order by `best_colony_potential`;
- distance / confidence / completeness as modifiers; **slider filters (F1 body
  counts) are hard filters applied first**.

Ranking logic lives in the profile definition, not scattered router SQL
(delivery plan §3, decision doc §6).

## Validation & parity

- **Coverage** (hard gate): every system has all 8 `system_archetype` rows and
  one `system_archetype_summary`; summary's `best_*` matches the max archetype row.
- **Invariants** (hard gate): scores 0–100, tiers consistent with thresholds,
  no `public.*` reads, reproducible from the generation + `archetype_version`.
- **Divergence report** (non-gate): diff V3 primary-archetype / tier / top-N
  ordering against the retained V2 archetype outputs
  (`system_archetype_scores` / `mv_archetype_rankings` or a re-run of
  `apps/importer/src/build_archetype_scores.py`) on a representative sample —
  surfaces where the V4-native model legitimately disagrees with v3.4. V2
  reference source resolved in planning.

## Out of scope (later phases)

- **F3** — point the Finder search/ranking API at these V3 projections and the
  ranking profile; retire the dead V2 `public.*` SQL.
- **F4** — the `apps/web` Finder UI (archetype picker + pop-out sliders + explained
  result cards + hand-offs).
- The governed production build/publish of the archetype product.

## Implementation plans (split)

1. **Plan F2a** — migration `011` (schema + product registration + guards +
   app views) with a schema/lifecycle test.
2. **Plan F2b** — `scripts/v3_system_archetype.py`: the fit model, chunked
   build/validate, summary, coverage — TDD on the disposable PG18 fixture.
3. **Plan F2c** — the ranking profile definition + the divergence report.

F2a first (schema underpins the builder); F2b then F2c. All computed from the
published Ratings V4 generation; F1's `system_search` is unchanged.

## Open items to resolve in planning

1. **Fit coefficients** — α, synergy sizes, capacity curve, breadth thresholds
   (benchmark-driven config; validate archetype separation against V4 output).
2. **V2 reference source** for the divergence report (retained legacy schema vs
   re-running `build_archetype_scores.py`).
3. **Ranking profile storage** — a `v3_meta`/`v3_derived` profile row vs a code
   constant selected by `ranking_version`; confirm against the decision doc's
   "published ranking profiles" intent during F2c planning.
