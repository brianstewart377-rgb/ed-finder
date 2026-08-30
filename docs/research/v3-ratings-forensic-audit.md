# ED-Finder V3 Ratings / CRE Forensic Audit

Status: active research checkpoint — **not a completed design**.

Last research checkpoint: 2026-08-31.

## Scope and safety boundary

Research only. Do not change production, write to the V3 database, change scoring code, or create/apply migrations. The aim is to establish a mechanics/evidence model that can survive adversarial review before any Ratings vNext implementation or mass rerating.

Evidence classes used here: official mechanic; direct observation; maintained implementation; strong inference; heuristic/prior. Multiple tools copied from the same upstream source count as one evidence lineage, not independent corroboration.

## Executive risk picture

The present player-facing archetype/topology path has several high-severity evidence and implementation risks:

1. **A direct classifier control-flow defect can zero feature counts for recognized body classes.** This can propagate into topology modifiers, standout logic and archetype scoring.
2. **Current ground- and orbital-slot estimators perform very poorly against the available observed corpus**: about 19.1% and 29.7% exact respectively.
3. **The pair-synergy/topology layer contributes up to 40 raw archetype points while important inputs are hand-tuned or heuristic.** Pair constants do not currently have auditable quantitative calibration.
4. **Ratings/scoring still has split historical semantics**: legacy v3.4, its public/documented intent, and the newer archetype/topology engine are not semantically aligned.
5. **Source lineage is easy to overcount.** BGS-Tally consumes Raven; other planners import DaftMav/Dubior/Raven data. Agreement among them is not automatically independent evidence.

These findings are sufficient to justify continued forensic work, not sufficient to prescribe the replacement model yet.

---

## P0 finding — `_classify_bodies_simple()` feature-count control-flow defect

Direct code inspection of `apps/importer/src/build_topology.py::_classify_bodies_simple()` found this ordering:

- recognized body types (ELW, Water, Ammonia, HMC, Metal-rich, Icy, Rocky-Ice, Rocky, gas giants, stars) increment their type counter and then `continue`;
- the global feature counters for `terraformable`, `tidal_lock`, `bio`, and `geo` are incremented only **after** those type branches.

Therefore those feature counters are accumulated only for fallback/unrecognized body types, not the recognized planet classes that matter most.

### Propagation

`build_archetype_scores.py` calls `_classify_bodies_simple(body_rows)` directly. The returned counts feed topology and archetype features, including:

- `terraformable_count` / terraforming coefficient;
- tidal-lock risk;
- Agriculture+Tourism pair modifiers using terraformable/bio state;
- standout/rationale logic and later archetype scoring.

No compensating recomputation was observed in the fetched scoring path.

### Evidence class

**Direct implementation defect**, subject to impact quantification.

### Adversarial challenge / falsifier

The defect would be downgraded if another production path recomputes these feature counts before scoring, or if current player-facing scoring does not consume this classifier output. Current code inspection points the other way, but the next run must trace every consumer and produce deterministic fixtures plus score/rank deltas.

I did not find a direct regression test for this helper in repository search. That is not proof none exists; perform a fuller test-tree audit.

---

## Surface-slot prediction — corrected evidence picture

### Original observed workbook

The source workbook is `Colonization slot analysis` / `Colonization slot analysis.xlsx`.

Main landable test population: **4,632 bodies**.

Workbook `Prediction (Surface)` performance:

- **4,630 / 4,632 exact = 99.9568%**;
- only two mismatch rows remain.

The workbook also contains an `Error correction expedition` sheet with 84 confirmed-slot rows, useful for provenance/history but not perfectly internally timeless: at least one expedition-era confirmed value differs from the final main sheet, reinforcing the need to store observation date/game version.

### Current Raven implementation — correction to the previous checkpoint

The previous checkpoint incorrectly associated Raven's current predictor with the older ~96.37% JS heuristic. That is now superseded.

Repository: `njthomson/RavenColonialWeb`  
File: `src/slot-prediction.ts`  
Introduced: commit `cd7c9d88077f4caf3885c85345d683534e1033a1`, 2025-11-19, `Predict surface slots when they are unknown (#25)`.

Current Raven formula:

- 0 if temperature > 700 K, gravity > 2.7 g, or non-landable;
- radius base: `<1500 => 1`, `<3750 => 2`, `<6000 => 3`, otherwise 4;
- +1 HMC;
- +1 terraformable;
- +1 if volcanism OR geo;
- +2 atmosphere;
- cap at 7.

Reproduced against the workbook corpus:

- versus workbook `Prediction (Surface)`: **4,631 / 4,632 = 99.9784%**;
- versus observed `Actual`: **4,629 / 4,632 = 99.9352%**.

The workbook `Stats` model3 result is also ~99.935%, with a minor denominator/header difference.

Correct lineage is therefore:

- workbook prediction column: ~**99.9568%** exact vs observed;
- current Raven/model3 pure formula: ~**99.9352%** exact vs observed;
- older supplied JS heuristic: **96.3731%** exact vs observed.

Raven is an excellent implementation comparator, but held-out independence remains unproven because the workbook/model and community research may share ancestry. A recent independent post-Nov-2025 validation set is still required.

### Two known workbook exceptions

Retain `surface_slot_workbook_prediction_mismatches.csv` as the regression seed. Known examples include:

- `Dryio Flyuae OZ-O d6-1381 1`: observed 7, current Raven-style formula 6;
- `DM99 4.3 1`: observed 6, current Raven-style formula 5.

These are especially valuable because a model that only reproduces the common rule can still miss rare upper-bound behavior.

---

## P0 finding — ED-Finder slot estimators fail the observed corpus

### Ground slots

Benchmarked `apps/importer/src/build_topology.py::estimate_body_slots()` against all 4,632 landable workbook rows:

- exact: **884 / 4,632 = 19.0846%**;
- mean absolute error: **1.38687 slots**;
- under-predictions: 2,753;
- over-predictions: 995;
- exact: 884.

Observed distribution:

`0=229, 1=1452, 2=1548, 3=685, 4=191, 5=328, 6=158, 7=41`.

Estimator distribution:

`0=1868, 2=1700, 3=754, 4=60, 5=218, 6=32`.

The current estimator never predicts 1 or 7 in this corpus.

Approximate subtype exact / MAE:

- Icy: 11.97% / 1.548;
- Rocky: 30.12% / 0.814;
- HMC: 31.19% / 1.476;
- Rocky-Ice: 1.11% / 1.433;
- Metal-rich: 0% / 3.0.

This is too weak to treat as a physical-feasibility ranker without redesign.

### Orbital slots

The workbook has **4,275 numeric observed orbital-slot rows**.

Observed distribution:

`0=669, 1=1900, 2=1329, 3=362, 4=15`.

Current ED-Finder orbital estimator:

- exact: **1,268 / 4,275 = 29.6608%**;
- MAE: **0.896608 slots**;
- over-predictions: 2,665;
- under-predictions: 342.

Approximate subtype exact / MAE:

- Icy: 28.58% / 0.899;
- Rocky: 32.37% / 0.829;
- HMC: 31.69% / 0.909;
- Rocky-Ice: 10.71% / 1.524;
- Metal-rich: 38.89% / 0.667.

### Adversarial caveat

The workbook mixes observations from a mechanic that has changed over time, and orbital slots are especially vulnerable to historical bugs/rebalances. That argues for **version-segmenting the corpus**, not for retaining a 19–30% exact estimator. The next stage must separate current-era observations from historical anomalies before fitting orbital rules.

---

## Pair synergy and topology — large score mass, weak calibration

`sql/012_topology_tables.sql` seeds 15 pair constants, including examples:

- Refinery+Industrial: synergy 0.95 / risk 0.12;
- Agriculture+Tourism: 0.91 / 0.08;
- HighTech+Tourism: 0.88 / 0.15;
- Extraction+Refinery: 0.82 / 0.22;
- Agriculture+HighTech: 0.79 / 0.18;
- HighTech+Military: 0.76 / 0.20;
- Industrial+Military: 0.74 / 0.18;
- Refinery+Military: 0.58 / 0.30;
- Extraction+Industrial: 0.55 / 0.35;
- Agriculture+Refinery: 0.28 / 0.72.

The migration describes these as derived from 2025 Trailblazers colonisation research, but no observation table, fitted model, source URLs, uncertainty, or calibration procedure was found. Treat them as **hand-tuned priors/heuristics** until provenance is established.

`build_archetype_scores.py` raw weighting is approximately:

- viability 35;
- slots 20;
- topology 25;
- pair synergy 15;
- bonus 5;
- then purity multiplier.

Thus a 0.95 pair prior contributes **14.25 raw points**, while topology + pair together can account for **40 raw points**. This makes weakly evidenced topology assumptions capable of materially changing rank.

### Adversarial falsifier

Run archetype sensitivity tests on a golden-system corpus with pair priors neutralized, widened/narrowed, and evidence-derived alternatives. If rankings remain stable, practical severity drops. If many top-N inversions occur, this becomes a direct ranking-quality blocker.

---

## Refinery + Industrial — objective-conditioned, not a timeless yes/no pair

Evidence that initially looks contradictory resolves partly by objective:

- Mega Guide material treats Rocky-Ice as a strong combined Refinery+Industrial target.
- OASIS warns that for a **pure Refinery objective**, Icy/Rocky-Ice/geo effects can introduce Industrial and dilute pure Refinery production.
- Frontier's later top-two market protection changes final-market cannibalisation semantics again.

So “R+I is good” and “R+I contaminates Refinery” can both be true under different objective functions.

This is a design warning for Ratings vNext: one scalar pair-synergy constant cannot cleanly represent both **pure economy maximization** and **blended/self-sufficient colony utility**.

The current 0.95 value remains uncalibrated until checked against observed completed colonies and commodity outcomes.

---

## Source-lineage map — do not count derivatives as corroboration

### Raven / BGS-Tally

`aussig/BGS-Tally` directly calls the RavenColonial API and maps Raven slot/economy data. BGS-Tally agreement with Raven is therefore the **same evidence lineage** for those results, not independent confirmation.

### ed-colonisation-planner

`gaborauth/ed-colonisation-planner` contains DaftMav/Dubior-related source material and Raven/Spansh fixtures. It is useful as an implementation and test corpus, but some mechanics values need independent verification.

A notable warning: its building/stat weighting appears inconsistent with Frontier's post-Dodec rebalance. The planner appears to encode first-station values around +40 Development/+40 Security/+40 Living/+20 Tech/+40 Wealth and much milder subsequent reductions, whereas the official Dodec rebalance records first starport Development +20, Security +40, Standard of Living +40, Tech +20, Wealth +40 and subsequent-facility reductions of 60/20/52/66/70 percent respectively. Treat the planner as a source lead, not authority, until this discrepancy is resolved.

The repo also claims four `system_score` examples as “real-game-verified 2026-08-10”. Locate the underlying observations and independently validate them next.

### EDConstrDepot

`web-inkoder/EDConstrDepot` is a promising **direct-observation lead** rather than merely a planner. Its code contains market-history/snapshot concepts (`TMarketHistStore`, `CreateMarketSnapshot`, deletion/history paths) and tooling around visited colony markets, free/construction slots, economy influence, inherent economies and links.

Next work should inspect the newer/active repo lineage, persistence/export schema, timestamp fields and whether before/after market snapshots can be transformed into versioned CRE evidence records.

---

## Ratings v3.4 / archetype split

Legacy `build_ratings.py` still uses `RATING_VERSION='3.4'` and a pair-aware overall form. Its cross-economy attenuation preserves top two raw economies, multiplies third by 0.85, and fourth+ by 0.70. That is a bespoke scoring regularizer, not Frontier's literal top-two commodity-consumption mechanic.

Historical production contains mixed scoring generations (`rating_version='3.4'` and `NULL`). The only observed live score-98 rows in the prior audit were stale/null-version rows. Version contamination must remain separate from mechanics redesign.

Commit `e6dcffd92e715d9f4e93cab87808dc63c13ec89f` (2026-08-15) moved player-facing scoring toward the archetype model, increasing the severity of topology defects.

There is also a semantic naming mismatch: `agriculture_terraforming` currently uses `economy_pair=('Agriculture','Tourism')`. Audit all archetype names/pairs against intended user-facing meaning.

---

## Official mechanics chronology — current anchors

### 30 Apr 2025 — Trailblazers Update 3

Frontier documented the strong/weak-link economy rewrite:

- same-local-body port/facility = strong link;
- different bodies in same system = weak link;
- strong links receive body/system boost/decrease modifiers;
- weak links are unaffected by that modifier mechanic;
- planetary facility preference/priority determines economy flow;
- body economy overrides stack by body properties/types.

### 22 Aug 2025 — Vanguards Patch 1

Frontier stated that goods produced by the **top two economies** are no longer consumed by linked ports/settlements for those economies, addressing market cannibalisation. This is commodity-market behavior, not evidence for fixed 15%/30% potential-score penalties.

### 11 Nov 2025 — Dodec Update

The colonisation-beta balancing was changed retrospectively. Current working values from the official note:

- initial starport: Development +20%, Security +40%, Standard of Living +40%, Tech +20%, Wealth +40%;
- subsequent facilities: Development -60%, Security -20%, Standard of Living -52%, Tech -66%, Wealth -70%.

Any pre-Dodec stat model must be version-tagged.

Continue chronology search through Aug-2026; do not assume Dodec is the last mechanic-affecting patch.

---

## CRE implications emerging from this audit

CRE should not store a mechanics claim as merely `value + source count`. It needs enough provenance to distinguish:

- source observation date and game version;
- official rule vs direct observation vs implementation vs inference;
- upstream evidence lineage / derivative source;
- scope/objective (pure economy, blended economy, self-sufficiency, market outcome, system-stat outcome, slot feasibility);
- contradiction set and supersession;
- confidence and falsification test;
- raw observation artifact where available.

Slot counts in particular should distinguish **observed Architect count** from predicted count, prediction algorithm/version, and observation era. Observed current-era values should override estimates.

---

## Adversarial review status

### Findings that survived this pass strongly

- Current surface-slot estimator is not competitive with the observed workbook model: direct benchmark gap is enormous.
- Current orbital estimator is also weak on the historical observed corpus.
- `_classify_bodies_simple()` has a real control-flow problem for global feature counters on recognized body classes.
- Pair-synergy values are materially weighted and presently lack auditable calibration evidence.
- BGS-Tally is downstream of Raven for relevant colonisation calculations; it is not independent corroboration.

### Findings deliberately kept provisional

- Exact real-world ranking impact of the classifier defect: not yet quantified.
- Current orbital-slot formula: historical corpus needs version segmentation first.
- Whether R+I deserves a very high blended-colony utility score: plausible, but 0.95 is not calibrated.
- Whether Raven's ~99.94% accuracy generalizes to current held-out systems: needs independent recent observations.
- Whether the ed-colonisation-planner's Dodec mismatch is a stale implementation, different interpretation, or already-fixed branch issue: inspect commit history/issues before judging.

---

## Persistent next-run queue

1. **P0 quantify classifier defect:** deterministic fixtures; trace every consumer; estimate prevalence; measure archetype score/rank inversions; audit tests.
2. **Surface-slot held-out validation:** build a post-Nov-2025 / current-era independent corpus; inspect Raven BodyFeature mapping and rare upper-bound exceptions.
3. **Orbital-slot version segmentation:** partition the 4,275 labels by observation era where possible; reconstruct official/community chronology of slot bugs/rebalances before fitting.
4. **Pair-prior sensitivity:** neutralize/perturb `pair_synergy_constants`; measure top-N ranking inversions and identify which archetypes are most fragile.
5. **Pair-prior provenance:** trace each numerical constant to source observations or downgrade it explicitly to a tunable prior.
6. **EDConstrDepot:** locate newest active repo, snapshot/export format, timestamps and directly observed before/after market data; assess CRE ingestion feasibility.
7. **ed-colonisation-planner:** locate the four “real-game-verified 2026-08-10” systems and independently reconstruct the evidence; resolve Dodec weighting discrepancy.
8. **Official chronology Nov-2025→Aug-2026:** economy/link/slot/population/facility changes, fixes and known regressions.
9. **Completed colony outcomes:** seek post-Aug-2025 R+I and control colonies with before/after commodity markets and economy ordering.
10. **Archetype audit:** intended user meaning vs pair definitions, purity penalties, standout logic and topology contribution.
11. **CRE provenance/coverage/contradiction schema:** source lineage, version, observation artifact, supersession and confidence.
12. **V3 input-field completeness:** determine whether all body/build/market fields required by a replacement model exist and at what coverage.
13. **Commodity-level self-sufficiency:** model construction supply and market outcomes separately from generic economy strength.
14. **Golden-system/golden-colony corpus:** versioned acceptance dataset spanning slots, strong/weak links, body modifiers, market rank protection, R+I, rings/belts, pre/post-Dodec and BGS anomalies.

## Next checkpoint target

Begin with the classifier-defect impact test rather than assuming the code defect equals ranking catastrophe. After the deterministic/control-path check, move directly into held-out slot evidence and pair-prior sensitivity so the overall audit continues rather than closing after one finding.
