# ED-Finder V3 Ratings / CRE Forensic Audit

Status: active research checkpoint — do not treat this document as a completed design.

## Scope and safety boundary

This audit is research-only. It must not change production, write to the V3 database, change scoring code, or create/apply migrations. The purpose is to establish a defensible mechanics/evidence model before any redesign or full re-rating.

Every material conclusion should be tagged mentally as one of: official mechanic, direct observation, maintained implementation, strong inference, or heuristic. Apparent corroboration from multiple derivative tools does not count as independent evidence.

## Current priority finding: scoring has split sources of truth

There are presently at least three materially different scoring/mechanics representations in the repository:

1. `apps/importer/src/build_ratings.py` — canonical legacy Ratings v3.4 Best-Build Potential scorer (`RATING_VERSION='3.4'`).
2. The v3.4 public explanation / commit intent from commit `e4ea1ff8e6312b26b3f9371af140f4973495d6f7`.
3. The v4 archetype/topology path: `build_topology.py`, `build_archetype_scores.py`, `sql/012_topology_tables.sql`, now used by player-facing Finder scoring.

These are not semantically aligned.

### Refinery + Industrial contradiction

Current `build_ratings.py` still includes `('Refinery','Industrial')` in `COMPLEMENTARY_PAIRS`.

But commit `e4ea1ff8e6312b26b3f9371af140f4973495d6f7`, labelled v3.4, explicitly said to *drop* Refinery+Industrial because Mega Guide Appendix D described market cannibalisation, and its public ratings page says the pair is deliberately not complementary.

The v4 topology migration goes the other way again: `sql/012_topology_tables.sql` seeds Refinery+Industrial at `base_synergy=0.95`, labels it Tier S / near-perfect, and says Rocky-Ice gives very clean stacking. No quantitative provenance for 0.95 was found.

Post-22-Aug-2025 top-two economy protection could materially improve this pair, so the old anti-pair conclusion itself may now be stale. What is not defensible is treating either 0.95 or the old exclusion as timeless truth without a dated observed-market test.

### Archetype cutover increases severity

Commit `e6dcffd92e715d9f4e93cab87808dc63c13ec89f` (2026-08-15) removed the legacy economy-score columns from player-facing API response construction and states that the archetype model is now canonical for scoring decisions.

Current `apps/api/src/search_economies.py` maps:

- Refinery -> `score_refinery_industrial`
- Industrial -> `score_refinery_industrial`
- Agriculture -> `score_agriculture_terraforming`
- HighTech -> `score_hitech_tourism`
- Tourism -> `score_hitech_tourism`
- Military -> `score_military_industrial`
- Extraction -> `score_extraction_refinery`

This means topology/archetype errors are not merely experimental; they can change current Finder ordering.

There is also a naming/semantic mismatch in `build_archetype_scores.py`: the `agriculture_terraforming` archetype actually sets `economy_pair=('Agriculture','Tourism')` rather than Agriculture+Terraforming.

## Surface-slot prediction

The prior analysis of `Colonization slot analysis.xlsx` established a much stronger empirical ground-slot model than the current topology estimator:

- Charts/landable population: 4,630 / 4,632 exact = **99.9568%**.
- Body-data all rows: 8,106 / 8,108 exact = **99.9753%**.
- Only two workbook-prediction mismatches remain.
- A later simplified JS heuristic achieved only 4,464 / 4,632 = 96.3731% and should not replace the workbook model.

The two known workbook exceptions are retained in `surface_slot_workbook_prediction_mismatches.csv`; the simplified-formula failures are in `surface_slot_latest_formula_mismatches.csv`.

Observed predictor boundaries/features include temperature 700 K, gravity 2.7 g, landability, radius thresholds 1500/3750/5500 km, HMC bonus, terraformability, geo-or-volcanism, bio, atmosphere +2/+1, and cap 7.

### Current topology estimator is materially weaker by construction

`apps/importer/src/build_topology.py::estimate_body_slots()` uses coarse body-type/radius rules and omits temperature, gravity, atmosphere, terraformability, geo and bio. Those omitted variables are exactly the variables implicated by the validated 99.9568% model.

Therefore `system_slot_topology.estimated_ground_slots` should currently be treated as an unvalidated heuristic, not the best available slot prediction. Next work should benchmark it directly against the workbook corpus and the two regression exceptions.

## Topology semantic issues requiring adversarial tests

Current `build_topology.py` contains several constructs that should not be accepted as mechanics-grounded until tested:

- `weak_link_stability = 100 - tidal_lock*8 - icy*4`. Frontier Update 3 explicitly says body/system boost/decrease mechanics affect strong links and weak links are unaffected. This metric appears to conflate body modifier quality with weak-link mechanics.
- `strong_link_potential` is a body-type weighted score. Strong-link existence, however, is driven by same-local-body port/facility placement and link priority. Body properties modify the linked facility's economy strength; they do not by themselves establish a strong link.
- `has_ringed_gas_giant` currently derives from `rocky_rings > 0`, which does not logically establish a ringed gas giant.
- `has_deep_orbital_anchor` currently derives from `gas_giant > 0`, while the schema comment describes a body with >=6 orbital slots. Those are not equivalent.

These may be naming shortcuts or real bugs; validate each with unit fixtures and known systems before deciding.

## Ratings v3.4 findings

Current `build_ratings.py` uses `RATING_VERSION='3.4'`.

Its cross-economy attenuation sorts the seven raw economy scores, leaves the top two unchanged, multiplies the third by 0.85, and the fourth-plus by 0.70. This is a bespoke anti-saturation/ranking regularizer. It should not be described as a direct implementation of Frontier's Aug-2025 top-two market protection rule, which protects produced goods from consumption/cannibalisation rather than applying fixed score discounts.

The overall score still uses the pair-aware structure `best_pair*0.60 + top3_avg*0.35 + strategic_bonus` before rarity/slot adjustments.

Production audit previously found mixed scoring generations: current v3.4 rows coexist with `rating_version IS NULL` rows. The unversioned bucket spans historical generations and cannot safely be classified row-by-row. Notably, the only live 98 scores observed were NULL-version legacy rows. A full rebaseline is a separate future operational decision and is explicitly out of scope for this research audit.

## Official mechanics chronology now anchored

### 30 Apr 2025 — Trailblazers Update 3

Frontier's Apr-25 developer post for the Apr-30 release documents the economy/population rewrite. Key mechanics:

- same-local-body port/facility = strong link;
- facilities on different bodies in the same system = weak link;
- strong links receive body/system boost/decrease modifiers;
- weak links are explicitly unaffected by that modifier mechanic;
- planetary facilities prefer the planetary port; economy then passes onward to orbital ports by priority;
- facility-to-facility links do not exist;
- body economy overrides stack (Rocky=Refinery, Rocky-Ice=Industrial+Refinery, HMC/MR=Extraction, Icy=Industrial, ELW=Agri/HiTech/Military/Tourism, WW=Agri/Tourism, etc.).

Primary source: Frontier forum developer post for System Colonisation Update 3, published 2025-04-25 for release 2025-04-30.

### 22 Aug 2025 — Vanguards Patch 1

Patch notes state that goods produced by the **top two economies** are no longer consumed by ports/settlements linked to those economies. This was specifically described as addressing market “cannibalize” behaviour. This is rank protection for final market behaviour; do not translate it into fixed 15%/30% potential-score attenuation without calibration.

### 11 Nov 2025 — Dodec Update / end of colonisation beta

The Dodec update retrospectively reweighted system-stat contribution:

- Initial Starport: Development +20%, Security +40%, Standard of Living +40%, Tech +20%, Wealth +40%.
- Subsequent facilities: Development -60%, Security -20%, Standard of Living -52%, Tech -66%, Wealth -70%.

Any Ratings/CRE logic that uses pre-Dodec additive facility-stat assumptions is version-stale.

## Source-lineage cautions

- `gaborauth/ed-colonisation-planner` is explicitly based on CMDR Dubior's guide, so matching conclusions are not independent evidence unless the repository adds its own observations/tests.
- CRE's source-authority/provenance framework is good, but current machine-extracted mechanics appear concentrated around Mega Guide / DaftMav / OASIS / Dubior. Evidence breadth must be increased, particularly with dated official patch notes and direct observed colony outcomes.
- Community reports after Update 3 show final station/service/market outcomes can also be affected by legacy BGS/faction state. Official colonisation notes are authoritative for the colonisation layer but are not necessarily a complete predictor of every observed station outcome.

## Current P0/P1 research risks

**P0 — player-facing archetype scoring may be built on stale/unvalidated topology assumptions.**

**P0 — contradictory Refinery+Industrial semantics exist across current scoring code, v3.4 documentation, and v4 pair constants.**

**P0 — current ground-slot topology estimator ignores variables used by a 99.9568%-validated model.**

**P1 — v3.4 fixed-rank attenuation risks being mistaken for a game mechanic rather than a regularizer.**

**P1 — pair synergy constants are numerical priors without auditable quantitative provenance.**

**P1 — current archetype naming/pair mappings contain semantic mismatches that can mislead both scoring and UI explanations.**

## Adversarial falsification tests

Do not accept the P0 findings solely from code inspection. Next validation should try to prove them wrong:

1. Benchmark `estimate_body_slots()` against the full 4,632-body workbook corpus. If it unexpectedly approaches the workbook accuracy, downgrade the slot concern; otherwise quantify error by subtype/atmosphere/radius/temperature.
2. Find post-Aug-2025 observed colonies deliberately built as Refinery+Industrial and compare commodity supply/demand, inherited economies, and leader order against Extraction+Refinery / Industrial+Military controls. This determines whether R+I is now viable and whether 0.95 is remotely calibrated.
3. Construct same system/body fixtures where only tidal lock/icy status changes while the build is weak-linked. Official mechanics predict no strong-link modifier effect on weak links; observed economy percentages should be the falsifier.
4. Compare archetype rankings with and without topology contribution on a golden-system corpus. If ordering is stable, topology defects may have small practical impact; if not, severity increases.
5. Trace every `pair_synergy_constants` value to an observation/source. A number without provenance should be treated as a tunable prior, not evidence.

## Golden corpus required before Ratings vNext

Build a versioned validation corpus containing, at minimum:

- known observed slot counts, including the two slot-prediction exceptions;
- clean single-economy parent bodies;
- strong vs weak link controls;
- same-body planetary+orbital priority controls;
- top-two economy rank protection / third-economy contamination controls;
- Refinery+Industrial post-Aug-2025 examples;
- Rocky+Geo, Rocky+Bio, Rocky-Ice, HMC+Geo, ELW, WW, ammonia, ring/belt examples;
- pre-/post-Dodec system-stat observations where available;
- BGS/faction/service anomalies kept separately from pure colonisation mechanics.

Expected record shape: system/body IDs, build topology, facility build order, observation date/game version, input body properties, observed economy percentages/markets/services/slots, source URLs/evidence artifacts, and confidence/provenance lineage.

## Persistent research queue

1. Quantitatively benchmark current `build_topology.py::estimate_body_slots()` against `Colonization slot analysis.xlsx`.
2. Reconstruct the exact workbook surface-slot formula, including why the two exceptions differ.
3. Audit orbital-slot prediction separately; do not assume the surface formula solves orbitals.
4. Trace current `pair_synergy_constants` and `PAIR_MODIFIERS` to evidence; test whether any are merely hand-tuned.
5. Search post-Aug-2025 observed Refinery+Industrial colony data and commodity-market examples.
6. Verify all later Frontier patch notes after Dodec for economy, links, slots, population and facility changes through Aug-2026.
7. Audit every archetype definition against current mechanics and intended user meaning.
8. Quantify how much topology/pair-synergy contributes to live archetype ranks; identify ranking inversions caused by suspect fields.
9. Expand CRE source coverage: Frontier primary notes, direct-observation datasets, Raven/SRVSurvey, BGS-Tally, EDConstrDepot, planners/repos, issue trackers and forum experiments.
10. Audit V3 field completeness for the inputs required by a replacement model.
11. Model commodity-level outcomes and realistic construction self-sufficiency separately from generic economy “strength”.
12. Define a golden-system / golden-colony validation corpus and acceptance thresholds before any Ratings vNext implementation.

## Next checkpoint target

Next iteration should begin with the quantitative slot-estimator benchmark, then continue directly into orbital-slot evidence and pair-synergy provenance rather than treating the slot subtask as completion of the overall audit.
