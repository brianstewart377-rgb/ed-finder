# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 18

Date: 2026-08-31  
Status: final bounded forensic-research iteration before Ratings redesign; research/docs only. No production, database, migration, scorer, or runtime changes.

This checkpoint continues checkpoint 17. It applies the agreed research stop gate rather than opening new low-value mechanics threads.

## Executive decision

**STOP broad mechanics research after this checkpoint and move to Ratings vNext/R1 design.**

The final bounded pass did find one more category-level defect, but it is architectural rather than a reason to keep searching for more external mechanics: the current archetype classifier collapses composable body properties into mutually exclusive buckets. In several cases, adding a beneficial in-game modifier can make a body worth *less* to the archetype scorer or even make it disappear from the relevant archetype body weights.

The remaining unknowns — exact commodity throughput, rare orbital-slot edge cases, the two surface-slot residuals, independent post-Operations Terraformable-Agriculture magnitude — are now better treated as explicit versioned uncertainty/backlog. None requires more broad research before defining a defensible Ratings contract.

## 1. Final sensitivity result: Terraformables are effectively lost for recognised planet classes

`build_archetype_scores.py` calls `build_topology._classify_bodies_simple(bodies)` directly.

In `_classify_bodies_simple`, `terra = is_terraformable` is read for each body, but every recognised star/planet class (`gas giant`, ELW, WW, ammonia, rocky ice, HMC, metal-rich, icy, rocky) executes `continue` before the generic block that increments `counts['terraformable']`.

Therefore the Terraformable counter is not merely slightly incomplete. For normal recognised planet classes it is effectively absent; only bodies that fall through all recognised subtype branches can reach the Terraformable increment.

### Deterministic score sensitivity

Current archetype body weights give:

- Agriculture/Terraforming: Terraformable weight 0.60.
- Population Capital: Terraformable weight 0.80.

For the first three qualifying bodies, the body-composition formula is `count × weight × 20`.

So, holding topology/purity/synergy fixed:

- one lost Terraformable = **12 raw body points** in Agriculture/Terraforming and **16** in Population Capital;
- three lost Terraformables = **36** and **48** raw body points respectively.

The archetype body component caps at 60, so this is large enough by itself to move a system from weak/moderate to near-cap body composition.

There is also a gate effect: `overall_development_potential` treats `terraformable >= 5` as a standout. Five real recognised Terraformables can therefore be represented as zero and fail that standout test. If no other standout is present and the raw ODP would exceed 82, the system is then capped at 82.

Evidence class: direct implementation + deterministic static sensitivity.

Falsifier: an enrichment layer adding Terraformable counts after `_classify_bodies_simple`. `score_system()` consumes the helper output directly; no such enrichment appears in the inspected path.

## 2. New category-level defect: composable properties are represented as mutually exclusive replacement classes

This is broader than the Terraformable early-continue bug.

Elite's colonisation mechanics often compose a base body identity with one or more modifiers: e.g. an HMC can also have geologicals; a rocky body can also have rings and geologicals/organics. The classifier instead frequently chooses one exclusive bucket.

### 2.1 Geological HMC can score lower than clean HMC

The classifier does:

- geo-positive HMC -> `hmc_geo += 1`
- otherwise -> `hmc += 1`

It does **not** retain `hmc += 1` for the geo-positive body.

The Extraction/Refinery archetype weights are:

- `hmc`: 1.00
- `hmc_geo`: 0.80

For the first three bodies that means:

- clean HMC body contribution = 1.00 × 20 = **20**;
- geological HMC contribution = 0.80 × 20 = **16**.

So adding geologicals to an HMC can reduce its archetype body contribution by **4 points per body** (12 across the first three), even though geologicals are an Extraction/Industrial-positive body condition in Frontier's economy model.

This is a monotonicity violation and a direct sign that the data representation is wrong for composable mechanics.

It is worse for archetypes that weight `hmc` but not `hmc_geo`. Expansion Capital, for example, weights `hmc` 0.55; Trade/Logistics weights `hmc` 0.45. A geological HMC can therefore cease contributing as an HMC at all to those body-composition terms.

Evidence class: direct current implementation + official direction of geological body override.

Falsifier: an explicit product requirement that geo-positive HMCs should be less suitable than otherwise identical clean HMCs. No such requirement exists, and it would conflict with treating geologicals as a positive Extraction/Industrial modifier.

### 2.2 Multi-modifier rocky bodies can disappear from relevant body weights

Rocky bodies are classified exclusively into `rocky_clean`, `rocky_geo`, `rocky_bio`, `rocky_rings`, or `rocky_mixed`.

If two or more of geo/bio/ring are present, the body becomes only `rocky_mixed`.

But major archetypes do not consistently weight `rocky_mixed`:

- Refinery/Industrial weights clean, ice, icy, rings, HMC, geo and bio — but **not `rocky_mixed`**.
- Extraction/Refinery weights HMC, metal-rich, rocky rings, HMC geo and rocky geo — but **not `rocky_mixed`**.

Thus a ringed+geological rocky body can contribute zero to a body-composition path where *both* of its actual modifiers are individually relevant.

The contamination model does recognise `rocky_mixed`, so the same body can simultaneously lose positive body contribution while retaining a high contamination penalty. That creates a double penalty caused by representation, not by a documented mechanic.

Evidence class: direct current implementation.

Falsifier: evidence that Frontier makes ring/geological/organic effects mutually exclusive on the same body. Existing official/community stacking evidence points the other way: distinct body overrides can coexist.

## 3. Final V3 field-path completeness result

The body schema/repository history contains or has previously exposed several fields needed for the validated surface-slot and environmental-modifier models, but the **current scoring worker SELECTs do not carry them into the topology/archetype calculations**.

### Topology worker currently selects

- `is_landable`
- `is_terraformable`
- bio/geo signal counts
- distance
- radius
- gravity
- ring existence
- synthetic system main-star metadata

It does **not** select the fields required to implement the validated surface-slot model for:

- surface temperature;
- atmosphere presence/type;
- volcanism;
- tidal-lock state.

The current stale slot estimator therefore cannot express the validated `<=700 K`, atmosphere +2, or volcanism/geo +1 logic even if the helper were changed locally.

### Archetype worker currently selects

- `is_landable`, `is_terraformable`;
- bio/geo signal counts;
- distance, radius, gravity;
- ring existence.

It also omits surface temperature, atmosphere, volcanism and tidal-lock state, and does not fetch star main/secondary metadata used by the shared helper.

This means:

- Terraformable is selected but then discarded for recognised types by control flow;
- tidal-lock is unavailable to the worker and the helper asks for `is_tidally_locked`, so current tidal logic is effectively dead/unverified;
- volcanism cannot be distinguished from geologicals in this scorer path;
- the validated surface-slot model cannot be reconstructed from the archetype worker's fetched body dictionaries;
- star classification is caller-dependent as documented in checkpoint 17.

This is enough for the Ratings design contract. A galaxy-wide null/coverage percentage would be nice operationally, but it is no longer necessary to decide the architecture: the current worker path demonstrably does not consume these fields.

Evidence class: direct current worker queries and classifier source.

## 4. Golden-corpus pass: what can be locked now

The user's Library already contains a stable control corpus that is sufficient to define acceptance behavior for the redesign:

- Plaa Eurk ZR-M c7-2 — civilian ELW/Military-cross-contamination control.
- Blu Thua SU-W c2-5 — remote material-cluster/distance control.
- Blu Thua JS-J d9-1 — sensible civilian ELW/WW/terraformable positive control.
- HIP 101924 — legitimate materials plus extreme-distance contamination.
- HIP 294 — stale-row / nearby-WW control.
- HR 1188 — Extraction specialist positive control.
- Brambai DL-Y g32 — ammonia-life gas giant vs true Ammonia World semantic regression.
- Eorgh Prou AA-A h24 — true Ammonia World positive regression.
- HIP 70564 — generic-cap/material-volume saturation control.
- Praea Euq PS-U c2-3 — distributed materials / distance-stacking control.
- sparse lower-tail controls: Wolf 359, Lalande 21185, UV Ceti, Yin Sector CL-Y d127.

This corpus already spans the main failure modes we need the next design to resist: semantic false positives, generic-body leakage, distance stacking, stale provenance, civilian/military cross-contamination, specialist positives and sparse negatives.

We do **not** need a galaxy-perfect golden corpus before designing the next model. Add new fixtures only when they represent a new mechanic class or a demonstrated regression.

## 5. Adversarial check against prior assumptions

### Correction: replacing physical slot estimates alone is not the current ranking cure

For legacy v3.4, the displayed `slots` component is not a direct `raw_overall` input.

For the current archetype engine, physical `estimated_total_slots` is propagated to traits/tags, while archetype topology points and `slot_efficiency` are driven primarily by `ground_synergy` / `orbital_synergy` body-count proxies.

Therefore fixing the physical slot estimator is important for truthfulness/buildability, but **it does not by itself repair the recommendation model**. The vNext contract must decide explicitly where physical feasibility belongs rather than assuming a better slot formula will automatically fix ranking.

### Correction: broad research is no longer the bottleneck

At this point the biggest defects are known implementation/representation problems:

- facts and modifiers collapsed into mutually exclusive buckets;
- important selected facts discarded by control flow;
- important schema facts not fetched by scorer workers;
- heuristic topology labels presented with mechanical language;
- body-count proxies standing in for actual build/link plans;
- temporal/provenance state not sufficiently bound to score semantics.

More Reddit/forum archaeology will not solve those. They require an explicit evidence contract and a redesigned feature representation.

## 6. Newly inspected external/tooling source: BGS-Tally

Current `aussig/BGS-Tally` directly consumes Journal-native colonisation events including system claim, construction depot, contribution, docking/completion, Market and Cargo events; it stores project/MarketID/build linkage plus required/delivered progress.

That makes BGS-Tally useful as an observational schema reference for future CRE ingestion of actual build outcomes and construction progress.

Adversarial caveat: BGS-Tally also integrates Raven and imports EDSM/Spansh data, so its derived mechanics are not automatically independent corroboration. Journal-native construction events are the valuable first-party observation lineage.

This remains a future validation/input stream, not a blocker for the Ratings design.

## 7. Evidence-quality summary

### High confidence / direct implementation

- Current archetype worker directly uses `_classify_bodies_simple`.
- Recognised body classes skip the generic Terraformable/tidal/bio/geo aggregate block.
- Geo-positive HMC replaces `hmc` with `hmc_geo` rather than composing both.
- Multi-modifier rocky bodies replace individual modifier buckets with `rocky_mixed`.
- Major archetypes omit `rocky_mixed` and some omit `hmc_geo`.
- Topology/archetype worker SELECTs omit temperature, atmosphere, volcanism and tidal-lock inputs.
- Current physical slot estimate is stale and not the primary archetype topology/ranking input.

### Official/current mechanics supporting the challenge

- Distinct body economy overrides/modifiers can coexist; same-economy duplicate strength not simply additive.
- Geologicals and volcanism are distinct concepts.
- Strong vs weak links depend on completed construction placement; environmental modifiers affect strong links, not generic weak-link stability.
- Gas giants have one construction slot after the July-2026 correction.

### Strong inference

- Correcting the feature representation will materially reorder Agriculture/Population and some material archetypes. The exact galaxy-wide inversion count remains unmeasured because a safe body-level DB snapshot was not available in this run.

### Remaining unknowns accepted for backlog

- exact cause of the two surface-slot +1 residuals;
- exact post-Operations Terraformable-Agriculture live magnitude;
- exact commodity throughput/population/wealth coefficients;
- rare orbital-slot edge rules;
- galaxy-wide null-rate percentages for every environmental field.

## 8. What would falsify the stop decision?

Reopen broad mechanics research only if one of these happens:

1. a primary Frontier patch materially changes colonisation mechanics again;
2. a bounded R1/golden test exposes a new category-level contradiction that cannot be handled as Unknown;
3. production data shows a supposedly minor deferred mechanic dominates ranking order;
4. a high-quality independent dataset disproves one of the locked core rules (e.g. surface-slot model or body override semantics).

Absent one of those triggers, additional broad source hunting should be considered diminishing-return research.

## 9. Stop/no-stop decision

**STOP.**

The forensic research phase has enough evidence to begin the next stage.

The next work item is **Ratings vNext/R1 evidence-contract and model design**, not another broad research iteration.

The design should start from these non-negotiables:

1. represent base body identity and modifiers as independent/composable facts, not replacement buckets;
2. preserve Unknown vs False/Absent;
3. separate official mechanics, direct observation, prediction and product preference;
4. bind every materialised recommendation to immutable model revision + source/patch provenance;
5. separate physical feasibility/capacity from economic mechanics from strategic/player preference;
6. use actual body placement/locality for strong/weak-link reasoning rather than system-wide body-count proxies;
7. use the validated surface-slot model as a feasibility fact with two documented historical residuals;
8. do not let stale-version rows silently participate as current recommendations;
9. calibrate scores/ranks against the golden/control corpus and population distributions rather than treating formula clamps as rarity;
10. keep deferred mechanics explicit in confidence/uncertainty rather than inventing defaults.

### Next queue item

**Begin Ratings vNext/R1 design and calibration contract.**

The first design pass should specify feature schema, evidence/provenance fields, mechanic-vs-preference boundaries, candidate archetypes/assessment dimensions, confidence semantics, golden-corpus acceptance tests and a shadow-evaluation plan. No production implementation should begin until that contract is reviewed.
