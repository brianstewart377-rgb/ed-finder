# V3 Ratings / CRE Forensic Audit — Checkpoint 02

**Research-only checkpoint.** No production writes, DB changes, scoring-code changes, or migrations were made.

## Executive delta from checkpoint 01

This pass concentrated on four unfinished areas: archetype/topology classifier correctness, slot-prediction provenance, independent planner/tool evidence, and evidence-lineage adversarial review.

The strongest new conclusion is that the archetype/topology layer has a deterministic internal classification divergence from `build_ratings.py`, which the topology code itself labels authoritative. The defect is large enough to move individual archetype scores by tens of points in simple fixtures. A second scoring-semantic inconsistency was found: archetype scores use a generic topology contamination value for the purity multiplier while displayed/stored purity for the selected archetype is recomputed pair-specifically. The user-visible explanation can therefore disagree with the contamination semantics that actually produced the score.

The slot investigation also changed confidence language. The 99.9568% workbook result remains extremely strong as an empirical regression result, but it is not yet a clean held-out estimate because the workbook prediction was measured on the same corpus it was developed/maintained against. Raven Colonial is not an independent confirmation: its slot model entered via a 2025 community reverse-engineering effort. The correct next step is temporal/system-held-out validation, especially around radius and exact boundary behavior.

Finally, adversarial review overturned one earlier apparent contradiction: the current `ed-colonisation-planner` Dodecahedron point values are consistent with Frontier's 13 Nov 2025 rebalance, not inconsistent with Frontier. This retraction is important evidence that the source-versioning discipline is working.

---

## A. Archetype classifier defect — now confirmed against ED-Finder's own authoritative classifier

### A1. What the lightweight classifier does

`apps/importer/src/build_topology.py::_classify_bodies_simple()` initializes global counters for `terraformable`, `bio`, `geo`, and `tidal_lock`, but almost every recognized body class increments its type and immediately `continue`s. The generic feature accumulation appears only after those branches. Therefore recognized gas giants, ELWs, WWs, ammonia worlds, rocky-ice, HMC, metal-rich, icy, and rocky bodies do not contribute those global feature counters.

The same lightweight function classifies HMCs into mutually exclusive `hmc` vs `hmc_geo` buckets.

### A2. Why this is demonstrably a divergence, not merely an alternate interpretation

`apps/importer/src/build_ratings.py::classify_bodies()` does the opposite: before any body-type `continue`, it accumulates ring count, total bio signals, total geo signals, tidal-lock count, terraformable count/weighted terraformability, and landability. HMCs always increment `hmc`; HMCs with geo/bio additionally increment `hmc_geo`.

`_classify_bodies_simple()` explicitly states that `build_ratings.py` classification is authoritative. The duplicate lightweight implementation therefore no longer preserves the authoritative semantics.

**Evidence quality:** High — direct current code comparison inside ED-Finder.

**Falsifier:** Show that archetype/topology intentionally requires mutually-exclusive HMC categories and intentionally excludes generic environmental flags for recognized body classes, with documented tests/specification matching that intent. No such evidence has been located.

### A3. Deterministic impact fixtures

These are pure function-level reconstructions of the shipped formulas, not prevalence estimates.

**Fixture 1 — one landable terraformable HMC, no tidal lock:**

- Current lightweight classification loses the terraformable flag.
- Agriculture/Terraforming archetype: approximately **39.76 -> 57.40** when the missing terraformable feature is retained, a **+17.64** change under the same clean-pair context.
- Population Capital: approximately **37.48 -> 60.68**, a **+23.20** change.
- The direct body-score delta is +12 points for Agriculture (`0.60 * 20`) and +16 for Population (`0.80 * 20`), then purity/multipliers amplify it.

**Fixture 2 — three landable HMCs, all terraformable and tidally locked:**

- Current lightweight classifier reports weak-link stability **100** because tidal locks are lost.
- Feature-correct counters produce weak-link stability **76** (`100 - 3*8`).
- Missing three terraformables removes 36 body points from Agriculture and 48 from Population before composition/multipliers.
- Under the reconstructed current formulas, both feature-correct archetype scores can reach the 100 cap while the buggy classifier remains around the mid-50s, despite tidal lock reducing pair quality.

The defect is therefore not monotonic. Missing terraformability suppresses some scores while missing tidal-lock penalties can inflate topology/pair behavior.

**Next required quantification:** Read-only prevalence analysis over V3 bodies/systems: count systems where recognized bodies carry `is_terraformable`, `is_tidally_locked`, `bio_signal_count`, or `geo_signal_count`, then estimate rank/archetype changes in a sampled corpus.

---

## B. Purity / contamination semantic inconsistency

`compute_archetype_score()` receives the generic topology row and uses `topology['contamination_risk']` as the archetype's purity multiplier input. Later, after the primary archetype is selected, `score_system()` recomputes `compute_contamination_risk(counts, primary_pair)` and stores/rationalizes `purity_score`, `contamination_risk`, `stable_top_two_prob`, risks, and build path from that pair-specific result.

Those two contamination models are not equivalent. The generic topology model and pair-specific model include different categories/weights.

### Concrete fixture

For a simple one-body `rocky_geo` Refinery+Industrial case:

- generic topology contamination: about **0.85**;
- pair-specific contamination: about **0.283**;
- reconstructed archetype score with the current generic-purity path: about **19.07**;
- using pair-specific contamination semantics consistently, including the affected pair-synergy path: about **25.95**.

This means a user can be shown a relatively clean pair-specific purity explanation even though the score itself was strongly reduced by a much harsher generic contamination value.

**Evidence quality:** High for the code-path mismatch; Medium for whether it is a bug vs an undocumented intentional distinction.

**Adversarial alternative:** Generic contamination may have been intended as a system-wide build-complexity penalty while pair-specific contamination is explanatory. If so, the variables and rationale need to state that distinction explicitly; current names/comments imply the same concept.

**Falsifier:** A design spec or calibration test proving that generic system contamination is deliberately supposed to drive every archetype's purity multiplier independently of target economy pair.

**Next test:** sensitivity matrix across representative body mixes, comparing rank order under generic-vs-pair-specific purity semantics.

---

## C. Surface-slot prediction — provenance and held-out caveat

### C1. Raven lineage traced

Repo: `njthomson/RavenColonialWeb`.

Commit `cd7c9d88077f4caf3885c85345d683534e1033a1` (2025-11-19), "Predict surface slots when they are unknown (#25)", introduced the prediction path. PR #25 attributes the rule to a community reverse-engineering effort and links the Frontier Forums planetary-build-slots research thread.

Current Raven `src/slot-prediction.ts` formula:

- if temp `> 700`, gravity `> 2.7`, or not landable -> 0;
- radius base `<1500 -> 1`, `<3750 -> 2`, `<6000 -> 3`, otherwise 4;
- +1 HMC;
- +1 terraformable;
- +1 volcanism OR geo;
- +2 atmosphere;
- cap 7.

Raven is therefore useful implementation evidence but **not independent confirmation** of the community research.

### C2. ed-colonisation-planner is appropriately cautious

`gaborauth/ed-colonisation-planner/src/journal/eligibility.ts` labels orbital estimates **UNVERIFIED** and uses one orbital per ordinary body only as a manual-input starting floor. Its comments state that no dependable per-body orbital formula was found and expect the user to correct counts from the in-game System Map.

Its ground-slot implementation is also community/Raven-derived. It uses `<6000` for the third radius band and exact rejection at `temperature >= 700` / `gravity >= 2.7g`, creating a boundary-semantic difference from Raven's `>700` / `>2.7` checks.

The planner also records a believed-patched historical ring/belt bug capable of producing 10+ extra orbital slots, with legacy built systems potentially retaining anomalous structures. This supports patch-version segmentation rather than a timeless orbital formula.

### C3. Workbook result remains excellent, but not yet held-out proof

Prior local analysis of `Colonization slot analysis.xlsx` found workbook `Prediction (Surface)` = **4,630 / 4,632 = 99.9568%** on landable rows, with two mismatches. That remains the strongest empirical regression result found.

However, adversarial review changes the wording: this is an in-corpus result on a workbook that may have been tuned/corrected using the same observations. It is not yet a clean estimate of future unseen-system accuracy.

There is also an unresolved threshold discrepancy:

- Raven / current planner: 1500 / 3750 / **6000** radius bands;
- earlier workbook-analysis recommendation called out 1500 / 3750 / **5500** boundary tests.

Do not pick one by authority. Test both on held-out systems.

### C4. Two workbook mismatches retained as regression targets

1. `Dryio Flyuae OZ-O d6-1381`, body 1: actual 7, workbook 6. HMC, radius ~6153.577 km, gravity ~1.1138g, temp ~627K, no atmosphere, Major Rocky Magma, geo true, bio false.
2. `DM99 4.3`, body 1: actual 6, workbook 5. HMC, radius ~5235.61 km, gravity ~0.8999g, temp ~690.06K, no atmosphere, Metallic Magma, geo true, bio false, tidally locked.

Both look like a missing +1 mechanism under the workbook prediction. Investigate raw source fields and whether volcanism/geo semantics, radius threshold, or another modifier explains them.

**Next test:** system-grouped and preferably time-sliced held-out validation comparing workbook model, Raven model, 5500-vs-6000, and exact 700/2.7 boundary semantics.

---

## D. Economy stacking semantics — apparent contradiction reconciled

Frontier Update 3 mechanics say body/environment overrides **may stack**; e.g. a High Metal Content body with organics can carry Extraction plus Agriculture and Terraforming effects. The Mega Guide phrase that influences "do NOT stack" is not contradictory when read in context: duplicate contributions to the **same economy** do not sum to 200% etc.; different economy types coexist.

The safest model interpretation is therefore:

- economy types introduced by independent modifiers combine as a set/union;
- duplicate strength contributions for the same economy use the applicable strongest/base strength semantics rather than naive additive duplication, unless a later primary source proves otherwise.

**Evidence quality:** High for multi-economy coexistence/Frontier override stacking; Medium for exact numeric duplicate-resolution behavior because community guide wording is doing some interpretive work.

**Next test:** build a table of official modifier examples and observed markets to distinguish `union/max` from any additive numeric edge cases.

---

## E. Dodecahedron chronology — explicit retraction of prior false contradiction

A prior checkpoint treated current `ed-colonisation-planner` Dodecahedron/system-development point values as inconsistent with Frontier's Dodecahedron launch post. That conclusion was version-blind and is retracted.

Frontier's initial 11 Nov 2025 values were rapidly rebalanced. Frontier staff posted the intended changes on 12 Nov and the 13 Nov patch applied the revised values, including the current-style first-station bonuses and subsequent-facility penalties. The planner is consistent with the post-rebalance values.

**Lesson for CRE/Ratings:** mechanic records need `effective_from`, ideally `effective_to`, source/version, and supersession links. A primary source can still be wrong for the current game if it is an older primary source.

---

## F. Golden-system corpus seed discovered in ed-colonisation-planner

`gaborauth/ed-colonisation-planner/src/realSystems.test.ts` says its `jsons/*.json` fixtures are real, played-out in-game systems and runs them through the full solver/build-order/link/placement pipeline. Comments state these fixtures exposed several real bugs before the regression suite existed:

- T2/T3 port-cost escalation conflation;
- free-slot / asteroid-eligible under/overcounting;
- port-unaware economy-synergy boost;
- already-present facilities dropped from solved links.

Current committed fixture names include:

- `col-285-sector-si-j-c9-30.json`
- `swoilz-aw-c-d114.json`
- `swoilz-aw-c-d52.json`
- `swoilz-cd-e-c1-1.json`
- `swoilz-eg-i-b2-3.json`
- `wregoe-yl-w-b56-4.json`

These are excellent **golden-corpus seeds for feasibility, placement, link topology, and build-order regression**.

Adversarial caveat: they are not automatically independent truth for economy percentages because the planner itself incorporates DaftMav/Raven/community logic. Use observed physical layouts as evidence; treat predicted economy outputs as implementation comparison unless backed by recorded in-game market snapshots.

---

## G. Additional evidence-lineage findings

### G1. ed-colonisation-planner explicitly embeds upstream data

The repo includes `DaftMav-v3.4.1.ods` and Raven import/export adapters. Its agent notes explicitly distinguish best-effort guesses from confirmed game behavior. Its Raven layout mapping is sourced from SrvSurvey's community-maintained `colonization-costs2.json`; only a small subset is cross-checked against a real Raven export and the rest is labeled best-effort/unverified.

This reinforces a provenance graph such as:

community reverse engineering / DaftMav / SrvSurvey -> Raven -> planner/guide-derived implementations

These projects are highly valuable, but repeated agreement across them must not be counted as repeated independent observations.

### G2. Mega Guide freshness trap

The Library copy of Mega Guide v2.3.0 has a recent upload timestamp but content release date 31 Oct 2025 and explicitly predates/incorporates neither the later Dodecahedron-era changes nor all subsequent patches. File upload/modified timestamps are not mechanic freshness.

### G3. EDConstrDepot is a promising empirical observation source

Current repository lineage points to `CMDR-Squedie/EDConstrDepot`. Its documented feature set includes:

- colony market-history snapshots;
- comparing snapshots of the same market, including after strong/weak links were added;
- planned construction economy effects;
- inherent body economies;
- station economies and strong/up-links.

If its snapshot persistence format can be extracted, this is potentially much stronger validation evidence than comparing formula-driven planners to each other: observed before/after market snapshots could test link effects and commodity/economy outcomes directly.

**Next task:** inspect Delphi persistence/data structures and any sample/user-export formats; determine whether snapshot data can be transformed into a CRE observation table.

---

## H. Archetype/topology engine provenance and staleness risk

Git history shows the additive "Archetype Engine — Phase 1-3 (v4.0)" landed on 10 May 2026 (`04f675b35f20ca3bf0474fe0025215269f498a55`). The commit explicitly labeled slot counts as estimates because Frontier exposes no direct slot data.

Several same-day follow-up commits fixed runtime/schema assumptions in the new scripts, including wrong call signatures, heartbeat wiring, non-existent body columns, and a ring heuristic. This does not invalidate the design, but it is evidence that the layer was experimental and deserves fresh calibration rather than inherited trust.

More importantly, an Aug 5 2026 fix (`c84f9417f3ef0e9abac26dc53761eaca49f58f2a`) says the topology dirty gate had queried `rating_dirty` from the wrong table since May. The nightly topology rebuild was therefore silently skipped for rating-dirty systems for roughly three months except for the separate missing-topology-row path.

**Implication:** persisted archetype/topology rows can have two separate classes of risk:

1. formula/model defects;
2. historical recomputation staleness.

Before comparing production archetype distributions, first verify rebuild version/completeness and determine whether a full post-Aug5 refresh occurred.

---

## Evidence confidence / adversarial register

| Finding | Confidence | Main adversarial challenge / falsifier |
|---|---:|---|
| Lightweight classifier loses generic environmental features | High | Intentional-spec evidence showing these features must be excluded in archetypes/topology |
| Lightweight HMC semantics diverge from authoritative classifier | High | Design tests documenting mutually exclusive HMC/HMC-geo requirement |
| Score/explanation use different contamination semantics | High for mismatch, Medium for bug label | Spec showing generic purity is intentionally score-wide while pair-specific purity is explanatory |
| Workbook surface model 99.9568% in its corpus | High | None for measured corpus; does not establish unseen-system accuracy |
| Raven surface model derives from community reverse engineering | High | Independent pre-existing source proving equivalent formula was separately derived |
| 5500 vs 6000 radius threshold remains unresolved | High | Held-out observed data should resolve |
| Dodec planner discrepancy was false | High | Frontier 13 Nov source/version chronology |
| Economy overrides stack across different economy types | High | Later primary patch notes superseding Update 3 |
| Golden planner fixtures are real played-out systems | Medium-High | Fixture provenance not independently checked yet; their outcomes may still mix observation with planner inference |
| EDConstrDepot snapshots can become empirical validation corpus | Medium / prospective | Need actual persisted snapshot schema and sufficient observed data |
| Archetype persisted population may have staleness history | High for prior dirty-gate failure | Verify a later full refresh made current persisted rows uniform/current |

---

## Updated unfinished queue

### P0 — do next

1. **Quantify V3 prevalence of the classifier defect** read-only: how many recognized bodies/systems have terraformable/tidal/bio/geo data that `_classify_bodies_simple()` discards; sample score/rank deltas.
2. **Held-out surface-slot validation:** system-grouped/time-sliced comparison of workbook vs Raven; explicitly test 5500 vs 6000 and exact 700K / 2.7g semantics; investigate the two workbook mismatches.
3. **Orbital-slot version segmentation:** build a rule/evidence chronology around pre/post 1 Jul 2026 gas-giant fix and ring/belt legacy anomalies. Do not seek one timeless generic orbital formula.
4. **Verify topology/archetype recomputation freshness:** establish whether all persisted topology/archetype rows were fully rebuilt after the Aug 5 dirty-gate fix.

### P1

5. **Pair-prior provenance and sensitivity:** locate origin/calibration for `pair_synergy_constants`; test ranking sensitivity and generic-vs-pair-specific contamination semantics.
6. **EDConstrDepot empirical path:** inspect snapshot storage/export; search for shareable before/after market examples.
7. **Golden corpus:** ingest/specify the real-system fixtures plus user-confirmed Wregoe systems, separating observed facts from formula-derived expectations.
8. **Official chronology:** continue dated mechanic timeline Nov 2025-Aug 2026, with supersession metadata.
9. **Completed-colony outcomes:** collect market/economy snapshots and facility layouts with effective dates.

### P2

10. Full archetype audit against current official mechanics and empirical outcomes.
11. CRE schema/provenance audit: evidence lineage, independent-observation count, version validity, contradictions, uncertainty.
12. V3 field-completeness audit for every candidate scoring feature.
13. Commodity-level self-sufficiency and cannibalization validation.
14. Expand golden-system/golden-colony corpus and define release-gate metrics.

---

## Next checkpoint handoff

Start with **P0 #1**. Do not score prevalence using persisted archetype outputs until recomputation freshness is known; query raw body features and reproduce both classifiers read-only. Then move directly to held-out slot validation. Preserve observed/predicted provenance separately and continue adversarial source-lineage checks.