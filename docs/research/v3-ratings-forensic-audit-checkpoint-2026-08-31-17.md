# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 17

Date: 2026-08-31
Status: active research checkpoint; research-only; no production, database, migration, scoring-code, or runtime changes.

This checkpoint continues checkpoint 16 and deliberately pushes toward a research stop gate rather than opening new low-value rabbit holes. Where it contradicts older checkpoints, this checkpoint wins for the specific claims called out below.

## Executive result

The highest-value finding in this iteration is that the main near-term Ratings risk is no longer legacy v3.4 calibration. The current player-facing search path has already cut over toward the archetype model, and that archetype model consumes a topology/classification layer with several deterministic structural defects and stale semantic proxies.

This gives us a practical stopping strategy: fix/replace the small number of structural inputs, run a bounded read-only ranking sensitivity/golden-corpus validation, then stop researching and design Ratings vNext. Exact commodity throughput and rare edge mechanics can remain versioned follow-up research unless they can change that design decision.

## Correction 1 — current-version production did not top out at 96

An earlier checkpoint/progress note said current-version v3.4 rows topped out at 96. That was wrong.

The read-only production audit of deployed revision `565e105e09e0670bc11cfc777f8e0b067b4145dc` (commit date 2026-06-25) found:

- score 95: v3.4 = 415; NULL = 95
- score 96: v3.4 = 122; NULL = 46
- score 97: v3.4 = 29; NULL = 28
- score 98: v3.4 = 0; NULL = 2
- score 99/100: 0

So the factual historical statement is: in that June-25 production snapshot, current-version v3.4 reached 97, while the only 98s were unversioned legacy rows.

The current formula can theoretically reach 100 because its raw overall is `best_pair * 0.60 + top3_avg * 0.35 + strategic_bonus`, with strategic bonus up to 7 before the 100 cap. The observed 95–97 pile-up is empirical saturation/compression, not a hard-coded 96 ceiling.

Evidence class: direct historical production observation + current source inspection.

Falsifier: a newer bounded production snapshot can supersede the June-25 distribution; it cannot make the June-25 snapshot itself false.

## P0 provenance finding — `v3.4` is not an immutable formula identity

Git history shows a semantic collision inside the human label `v3.4`.

### 2026-05-08 commit `e4ea1ff8e6312b26b3f9371af140f4973495d6f7`

Commit message: `feat(ratings): v3.4 + public explanation page`.

The message claims formula changes including:

- remove Refinery+Industrial from complementary pairs;
- add Refinery+Agriculture and Extraction+Industrial;
- add population-tier standout weighting;
- add slot-floor gating for <10 / 10–19 / 20+ slots;
- add a Rocky/HMC bio bonus.

Adversarial file-list inspection shows the commit changed the public `frontend-v2/public/ratings.html` explainer and a SearchForm link. It did **not** change `build_ratings.py`. The explainer nevertheless labelled itself `build_ratings.py v3.4`.

### 2026-07-08 commit `ca786e5d85dcf8b0018b61d6b25646f5c391f89e`

This later commit changed the scorer header/startup text from the v3.0 lineage to `Canonical scorer: Ratings v3.4 Best-Build Potential` and updated the current contract. The score functions themselves were not changed by that patch.

The contract describes the lineage as v3.0 baseline, v3.1 enrichment, v3.2 pair-aware overall, v3.3 pair tie-break, and v3.4 cross-economy attenuation plus explicit `rating_version`.

### Consequence

A row containing only `rating_version = '3.4'` is not sufficient provenance for exact formula semantics across source history. Future scoring evidence should carry an immutable model revision in addition to a friendly version label, ideally including:

- semantic model id;
- formula revision/hash;
- source commit SHA;
- effective-from/effective-to dates;
- data-schema/input revision.

Evidence class: direct Git history / implementation provenance.

Adversarial challenge: an unseen scorer change in the May-08 commit would weaken this. The fetched commit file list was explicitly searched for `build_ratings.py`; the only occurrence was prose inside the new HTML page, not a changed scorer file. A later commit could have implemented similar rules, but that would reinforce rather than remove the need for immutable formula identity.

## Current product authority — archetypes, not the legacy economy columns

Commit `e6dcffd92e715d9f4e93cab87808dc63c13ec89f` (2026-08-15) removed legacy economy-score reconstruction from API responses and explicitly states that the archetype scoring model is the canonical source for player-facing scoring decisions.

Current `apps/api/src/search_economies.py` maps economy searches to archetype columns:

- Agriculture -> `score_agriculture_terraforming`
- Refinery/Industrial -> `score_refinery_industrial`
- HighTech/Tourism -> `score_hitech_tourism`
- Military -> `score_military_industrial`
- Extraction -> `score_extraction_refinery`
- no economy filter -> `overall_development_potential`

Current `local_search.py` uses `COALESCE(archetype_score, legacy_ratings_score)` as the Finder score expression.

Therefore legacy v3.4 remains important for historical data cleanup, model lineage and old production comparisons, but tuning its coefficients is no longer the primary Ratings design target.

Evidence class: direct current implementation + commit history.

Falsifier: a later product path that bypasses these mappings or reinstates legacy score columns as primary ranking would change the priority. No such current branch path was found in this pass.

## P0 archetype defect — the shared classifier discards terraformable/tidal aggregate state

`build_archetype_scores.py` directly imports and calls `build_topology._classify_bodies_simple(bodies)`.

In `_classify_bodies_simple`, recognised stars/planets increment their body-type buckets and `continue`. The generic counters for:

- `terraformable`;
- `tidal_lock`;
- aggregate `bio`;
- aggregate `geo`;

are incremented only after those recognised-type branches.

Examples inspected directly include gas giants, ELW, rocky ice and HMC branches, each of which exits before the generic block. HMCs, for example, increment `hmc` or `hmc_geo`, landable counts, then `continue`.

The result is not just a display defect. Terraformable count is a direct archetype scoring input.

### Deterministic static sensitivity

The archetype engine's first three qualifying bodies contribute `count * weight * 20` before the diminishing-return tail and cap.

- Agriculture / Terraforming gives Terraformable weight 0.60 -> **12 body points per Terraformable** for the first three.
- Population Capital gives Terraformable weight 0.80 -> **16 body points per Terraformable** for the first three.

Therefore three recognised Terraformable bodies can be understated by **36 raw body points** in Agriculture/Terraforming and **48 raw body points** in Population Capital before purity/diversity multipliers.

There is a second-order gate: `overall_development_potential` treats `terraformable >= 5` as a standout condition. If Terraformables are the only standout source, losing that count can make the system fail the standout test and trigger the ODP no-standout cap at 82.

This is already severe enough to justify correction before calibrating archetype thresholds.

Evidence class: direct deterministic implementation defect + static sensitivity.

Falsifier: a production path that supplies precomputed corrected counts instead of `_classify_bodies_simple` would remove the impact. Current `build_archetype_scores.py` explicitly calls the helper on fetched bodies.

## Tidal-lock state is doubly lost

Even if the classifier control flow were reordered, the archetype worker query currently does not select `is_tidal_lock`, while the helper asks for a differently named key, `is_tidally_locked`.

The topology worker also does not provide the helper with the body's actual tidal-lock field in the inspected path.

As a result, tidal-lock penalties/stability logic should currently be treated as effectively unverified/dead until a direct fixture proves otherwise.

This matters because Frontier's Trailblazers Update 3 explicitly says tidal locking can decrease **Agriculture strong-link performance**.

Evidence class: direct implementation + official mechanic.

Falsifier: another data-enrichment step injecting `is_tidally_locked` into these body dictionaries before classification. None was found in the fetched worker paths.

## P0 semantic defect — `weak_link_stability` models a strong-link modifier

`build_topology.py` computes `weak_link_stability` by penalising tidal-lock and icy-body counts.

Frontier's Trailblazers Update 3 states the opposite semantic boundary:

- environmental body/system boosts and decreases affect **strong links**;
- **weak links are unaffected** by that modifier mechanic.

Icy and tidal-lock penalties are Agriculture strong-link performance modifiers, not a general weak-link stability mechanic.

Therefore this field is not merely an approximate coefficient; its label/concept conflicts with the official link model.

Evidence class: official primary rule + direct implementation contradiction.

Falsifier: later Frontier patch notes explicitly changing weak links to inherit these environmental modifiers. No such later change has been found in the current chronology.

## P0/P1 topology issues still present in current source

### Surface slot estimator is obsolete

Current `estimate_body_slots()` uses body-class/radius bands such as Rocky >5000 km -> 6 ground slots and HMC >4000 km -> 5. It does not implement the validated community/Raven family:

- eligibility: landable, <=700 K, <=2.7 g;
- radius bases <1500 / <3750 / <6000 / >=6000 -> 1/2/3/4;
- +1 HMC;
- +1 Terraformable;
- +1 Volcanism OR Geo;
- +2 atmosphere;
- cap 7.

The observed workbook validates its reference prediction at 4,630 / 4,632 = 99.9568%, with two retained +1 residuals.

### V3 already stores the needed fields

The current `bodies` schema contains `surface_temp`, `gravity`, `atmosphere_type`, `volcanism`, `is_terraformable`, `is_landable`, bio and geo signals. The topology worker simply does not select/use several of them.

Therefore replacing the surface estimate does **not** require a new source/schema migration in principle; coverage quality still needs a read-only audit.

### Gas giants remain stale

Current topology source still returns 3 orbital slots for an unringed gas giant and 5 for a ringed one. Frontier's 2026-07-01 Operations update explicitly corrected multiple-build behaviour because a gas giant has **one construction slot**.

### Ringed-gas flag is directly wrong

`has_ringed_gas_giant` is currently assigned from `counts['rocky_rings'] > 0`, so a ringed rocky body can set the ringed-gas-giant flag even when no ringed gas giant exists.

Evidence class: direct implementation; gas-giant correction additionally supported by official current patch notes.

## Same helper, different caller -> inconsistent star classification

The topology worker injects system main-star metadata by joining a one-row system-derived object `ON TRUE`, causing every star row in that worker's body list to receive `is_main_star = TRUE` and the system main-star spectral class. Secondary stars can therefore be classified as main stars in that path.

The archetype worker, by contrast, fetches bodies without `is_main_star` or spectral-class fields. `_classify_bodies_simple` then defaults `is_main_star` to false, so every star presented by that path appears secondary to the helper.

Thus the same classifier is caller-dependent for star/main-secondary state.

Immediate score impact appears smaller than the Terraformable defect, but topology flags and orbital estimates cannot be treated as trustworthy until this is normalised.

Evidence class: direct implementation.

Falsifier: a DB adapter that adds the fields after these SELECTs. No such transformation appears between fetch and `dict(row)` in the inspected workers.

## Strong-link and buildability proxies are mislabeled as mechanics

Current `strong_link_potential` is constructed from body counts (ELW, WW, ammonia, gas giants, rings, exotic stars, etc.). Frontier defines a strong link as a relationship created by **completed constructions on/around the same local body**, not as a property produced by simply owning those body types.

The archetype buildability score then uses `strong_link_potential` directly as its T3-scaling proxy.

This can still be useful as a product prior for "how promising might a future build be?", but it should be named and calibrated as a heuristic potential proxy, not as observed strong-link mechanics.

Likewise archetype "slot_efficiency" does not use physical slot counts. It blends `ground_synergy` and `orbital_synergy`, both body-count formulas. The stale `estimated_total_slots` is mainly propagated as data/tags rather than directly driving the primary archetype topology contribution.

This is an important correction to earlier wording: stale physical slot estimation is a serious displayed/buildability-data defect, but current archetype score topology points come from body-count synergies, not from the estimated slot total itself.

Evidence class: direct implementation + official mechanic boundary.

## Legacy v3.4 input classification — now sufficiently complete for design purposes

The remaining legacy v3.4 terms can now be classified at the level needed to stop tuning that model:

### Mechanic-derived facts used through heuristic weights

- body economy identities: ELW, WW, ammonia, gas giant, HMC/metal-rich, rocky/rocky-ice/icy, rings;
- Terraformable / organics / geologicals / volcanism / tidal-lock / resource-state strong-link modifiers;
- exotic-star HighTech/Tourism and normal-star Military identity.

The existence/direction of many of these is official; their ED-Finder point weights and system-wide additive aggregation are product heuristics.

### Wrong scope / over-counted

The legacy scorer treats **signal counts** as repeated system-level bonuses. Official Trailblazers Update 3 language is body/placement-local: "on or orbiting a body with geologicals/organics".

A single body with 10 geo signals can currently inject, before cross-economy attenuation:

- +20 Industrial;
- +20 HighTech;
- +15 Tourism;
- +25 Extraction;

= **80 raw economy points across four scores** from one body's ten geological signals.

Ten bio signals on one body can add another +50 across Agriculture, HighTech and Tourism. Maximum capped bio+geo signal contributions sum to roughly **140 raw points across the legacy economy scorers**.

This can change which economies occupy the top two/three, so the distortion is nonlinear after attenuation and best-pair selection.

### Wrong field

Extraction's geo-signal term is described in code as volcanism even though Frontier distinguishes:

- geologicals -> economy overrides (Extraction + Industrial);
- volcanism -> Extraction strong-link performance boost.

### Product heuristics, not Frontier mechanics

- cross-economy 1.00 / 0.85 / 0.70 attenuation;
- the fixed complementary-pair list and pair averages;
- rarity/standout ceiling rules;
- scalar 60/35 overall blend;
- distance/scoopability/safety bonuses;
- arbitrary per-body point coefficients.

These may be valid product choices but require empirical ranking validation, not "mechanics accuracy" claims.

### Misleading display proxy

Legacy `slots` is a body-abundance proxy, not a physical construction-slot calculation. It should not be carried into vNext under the word "slots".

## Production compression — historical result remains useful, but it is not the current archetype calibration dataset

The June-25 read-only production audit found:

- 187,446,543 rated rows in the all-rated cohort;
- only 735 rows at 95–97 and 2 at 98–100;
- current-version score >=90: 10,547 rows in the bounded high-band split;
- economy-score saturation was common: `score_refinery = 100` on 4,414,397 rows and `score_industrial = 100` on 8,292,262 rows.

So there are two distinct facts:

1. **overall 95+ was globally extremely rare** in that snapshot;
2. **component/economy saturation was very common**, flattening differentiation among elite systems.

Because the production audit deployed revision is 2026-06-25 and the explicit archetype API cutover commit is 2026-08-15, this dataset must be treated as a historical v3.4 calibration snapshot, not proof of the current archetype score distribution.

Evidence class: direct historical production observation, version-bounded.

## CRE / provenance requirements strengthened by this pass

CRE and future score materialisations should preserve at least:

- friendly mechanic/model version;
- immutable formula/model revision or hash;
- code commit SHA;
- effective-from/effective-to;
- official intended rule vs observed live behaviour vs known bug state;
- source lineage/upstream parent;
- observation date/game patch;
- direct observation vs prediction vs manual correction vs default assumption;
- falsifier / unresolved contradiction.

The `v3.4` label collision is now a concrete regression fixture demonstrating why this is necessary.

Reserve level remains a separate missing-data issue. Raven currently substitutes Pristine when reserve level is unknown; no first-class `reserve_level` field was found in the current ED-Finder schema/repo search. ED-Finder should keep this unknown rather than copy Raven's optimistic default.

## Evidence-quality assessment

### High confidence / direct

- current API/search archetype cutover;
- May-08 v3.4 commit/document-vs-code mismatch;
- July-08 relabelling/history ambiguity;
- `_classify_bodies_simple` control-flow defect;
- Terraformable static score sensitivity;
- stale slot estimator and ringed-gas flag;
- body schema contains the necessary surface-slot input fields;
- weak-link-stability semantic contradiction with Frontier Update 3;
- June-25 production high-band/version counts.

### High confidence official mechanic

- strong vs weak link placement rules;
- weak links unaffected by environmental strong-link modifiers;
- HighTech boost from geologicals/organics, Agriculture tidal/icy penalties, Extraction volcanism/resource modifiers;
- body economy overrides and stacking of distinct economy identities;
- July-2026 gas giant one-slot correction.

### Strong inference / needs bounded validation

- exact rank movement after classifier/topology correction;
- prevalence/coverage of surface temperature/atmosphere/volcanism in the current V3 body population;
- magnitude of current archetype high-band compression.

### Still provisional / defer unless design-sensitive

- exact post-Operations Terraformable Agriculture live magnitude;
- exact commodity throughput/population/wealth coefficients;
- rare orbital-slot edge rules beyond the current post-July corpus;
- the two surface-slot +1 residual causes.

## Hypotheses worth testing against V3 next

1. Correcting Terraformable counting will materially reorder Agriculture/Population archetypes and release some systems incorrectly capped at ODP 82.
2. Correcting tidal-lock state will selectively demote Agriculture candidates currently treated as clean.
3. Replacing body-count "slot efficiency" labels with actual/predicted physical capacity will change player-facing buildability interpretation even if archetype rank movement is smaller than expected.
4. Replacing signal totals with body-local predicates will mostly affect legacy v3.4 history, but provides a useful sanity comparison against archetype results and may explain several historical high-band outliers.
5. Normalising strong-link terminology/proxies will expose systems that look mechanically "T3 scalable" only because body counts are standing in for an actual build plan.

## Research stop gate

The audit is now close enough to a stop that further work should be explicitly bounded.

### One final high-value research iteration before design

Perform a **read-only sensitivity / golden-corpus pass** against the current archetype model:

- construct a small representative candidate set including Terraformable-rich, tidally locked Agriculture, rocky/HMC mining/refinery, WW/ELW, gas-giant-heavy, exotic-star, and low-slot controls;
- compute current archetype outputs vs corrected classifier state and corrected physical surface-slot capacity without writing any DB rows;
- record top-N inversions and score deltas;
- verify a small set against direct/official/community golden fixtures;
- decide which uncertain mechanics can be deferred safely.

If that pass confirms material but understandable movement and reveals no new category-level mechanic contradiction, **stop research and move to Ratings vNext design/implementation planning**.

Do not hold the first redesign for exact commodity-throughput equations, a perfect orbital-slot formula, or explanations for the two 99.9568% surface-slot residuals. Those become post-design validation/backlog items unless the final sensitivity pass shows they alter the ranking architecture.

## Next queue item

1. Read-only current-archetype sensitivity / golden-corpus pass (primary).
2. Quantify V3 field coverage for `surface_temp`, `atmosphere_type`, `volcanism`, Terraformable and tidal state if a safe read-only source is available.
3. Produce a stop/no-stop decision and a concise Ratings vNext evidence contract.
4. Only if a design-critical gap remains: targeted evidence search; otherwise close the forensic research phase.
