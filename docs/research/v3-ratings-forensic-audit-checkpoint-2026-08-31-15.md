# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 15

**Date:** 2026-08-31  
**Branch:** `chatgpt-ed-new-ops-requests`  
**Mode:** research/documentation only

## Safety boundary

This checkpoint records research only. No production state was changed. No V3 database writes were performed. No scoring code was changed. No migrations were created or applied.

## 1. Material correction: the 99.9568% workbook model appears to be the 6000-km / no-bio family

The Library analysis memo for `Colonization slot analysis.xlsx` remains the empirical benchmark:

- `Charts`: 4,630 / 4,632 landable bodies correct = **99.9568%**;
- `Body data`, all rows: 8,106 / 8,108 correct = **99.9753%**;
- only two workbook-prediction mismatches remained.

The same memo separately reports a later supplied JS heuristic at only 4,464 / 4,632 = **96.3731%**, with 168 mismatches. Its recommendation section mentions 1500 / 3750 / 5500 radius boundaries and a bio bonus. Those recommendation bullets must not be conflated with the almost-perfect workbook column.

Adversarial reconstruction from the mismatch exports and discriminating rows instead makes the workbook's high-accuracy column look structurally equivalent to this family:

```text
if not landable OR temperature > 700 K OR gravity > 2.7 g:
    0
else:
    radius < 1500 km  -> base 1
    radius < 3750 km  -> base 2
    radius < 6000 km  -> base 3
    otherwise         -> base 4

+1 High Metal Content
+1 terraformable
+1 if geologicals OR volcanism
+2 if atmosphere
cap at 7
```

Crucially, this reconstruction has **no independent bio bonus**.

Useful discriminators already present in the exported mismatch evidence include bodies in the 5,500–6,000 km band where the later heuristic is one high but the workbook is correct, and bodies with bio where the later heuristic is one high but the workbook remains correct. Atmosphered terraformable HMC examples also fit `+2 atmosphere` rather than a weaker atmosphere increment.

This is a correction to earlier checkpoint wording that associated the 99.9568% result with the 5,500-km/bio-bonus heuristic.

### What is still not proved

The original `.xlsx` formula cells have **not yet been directly recovered** in the current Library search. Therefore exact equality semantics at 1500, 3750, 6000, 700 K and 2.7 g remain to be verified from formula cells or exact-boundary observations. The evidence pack documentation says formula-cell exports are preserved for source workbooks in that pack, so recovering the direct formula remains a high-priority provenance task rather than guessing from outputs.

### Falsification test

This reconstruction is falsified if the original workbook formula cells show materially different thresholds/bonuses, or if a controlled set of workbook predictions near 5,500–6,000 km / bio-only cases cannot be reproduced by the formula above.

## 2. Raven's public fallback predictor is essentially the same formula family

Current public `RavenColonialWeb/src/slot-prediction.ts` uses:

- zero if `temp > 700`, `gravity > 2.7`, or not landable;
- radius bases `<1500 = 1`, `<3750 = 2`, `<6000 = 3`, otherwise `4`;
- `+1` for HMC;
- `+1` terraformable;
- `+1` for volcanism **or** geologicals;
- `+2` atmosphere;
- cap at 7;
- no biological bonus.

Its November 2025 PR describes the predictor as community reverse-engineering and points to the Frontier forum thread *Studying planetary build slots*. Dubior's guide independently names CMDR Nyatto as spearheading the ground-slot formula work and credits Grinning2001 for Raven/SrvSurvey, reinforcing that this is a shared community research lineage rather than an official Frontier rule.

This substantially reduces the apparent mathematical disagreement between Raven's fallback and the high-accuracy workbook prediction. It does **not** provide independent corroboration if both descend from the same Nyatto/Flynnvali/community observations.

### Evidence class

- Raven source code: **high confidence implementation fact**.
- Match to live game: **community empirical heuristic**, not an official rule.
- Independence from the workbook research lineage: **not established; likely materially shared**.

## 3. New provenance finding: a Raven stored slot count is not automatically an observed ground truth

Inspection of current `RavenColonialWeb` changes how Raven slot evidence must be classified.

The system UI reads a stored slot map for each body. For surface slots, Raven only calls `predictSurfaceSlots()` when the stored surface value is unknown/negative; otherwise it displays the stored number. The editor allows users to manually set orbital and surface slot counts, and the system save payload persists that slot map back through the Raven API.

Therefore a statement such as **"Raven says this body has 5 slots" is ambiguous**. It can mean at least:

1. Raven fallback prediction;
2. a stored Raven value originating from some import/server path;
3. a manually corrected value entered by a user.

The UI does not by itself prove which provenance applies to a stored value.

This is important for validation design: comparing our model to Raven stored values without provenance can produce falsely impressive accuracy if those stored values have already been manually corrected from Architect/System Map observations.

### Required golden-corpus fields

For slot validation, keep these as distinct observations:

- `raven_fallback_prediction`;
- `raven_stored_slot_value`;
- `raven_stored_provenance` / `raven_observation_source` if known;
- `workbook_prediction`;
- direct current-patch Architect/System Map observation;
- observation date/game patch;
- build/demolition state because Frontier fixed Architect slot reporting after demolition in July 2026.

### Falsification test

This conclusion would be weakened if Raven's server/API can prove that all persisted slot values are cryptographically or structurally tied to direct game observations and user edits are stored separately. Current public UI/API types do not demonstrate that separation.

## 4. The two historical workbook residuals remain re-observation targets, not a new rule

The two workbook residuals previously isolated are both HMC bodies where actual exceeded workbook prediction by exactly one:

- `Dryio Flyuae OZ-O d6-1381 1`: actual 7, workbook 6;
- `DM99 4.3 1`: actual 6, workbook 5.

The Raven public fallback produces the same lower predictions for their known properties, so Raven does not explain them. With only two residuals among 4,632 landable bodies—and with Frontier later acknowledging Architect slot-reporting defects—adding a special hot/volcanic-HMC `+1` would be overfitting.

Keep both as golden **fresh-reobservation** targets under the post-July-2026 game before changing the model.

## 5. Second adversarial subtask: Raven silently converts unknown reserve level into `Pristine`

Current `RavenColonialWeb/src/economy-model2.ts` contains this explicit default in both strong-link boosting and general buffs:

```text
const reserveLevel = site.sys.reserveLevel ?? 'pristine';
```

Raven then applies `+0.4` to Extraction, Industrial and Refinery when reserve level is Major or Pristine; Low/Depleted can instead receive `-0.4` in the relevant paths.

This means **missing information is not neutral**. An unknown reserve value is transformed into the most favorable reserve category for three economy families.

That is dangerous as an inference pattern for CRE / Ratings even if it was a pragmatic Raven UI decision. ED-Finder should retain `unknown` as a first-class state and, if a scenario calculation elects to assume Pristine, mark the assumption explicitly and keep it out of evidence-backed truth.

### Impact still to quantify

The public ED-Finder repository search did not surface a clear canonical `reserve_level` field or coverage audit in this pass, so I am not claiming how many V3 systems are affected. Quantifying V3 reserve-data completeness remains a read-only analysis task.

### Falsification test

The practical-risk hypothesis is falsified if V3 has near-complete trustworthy reserve-level coverage for every candidate used by Ratings, or if reserve level cannot change ordering/results in the vNext mechanic calculation. The Raven implementation fact itself is directly visible in current source.

## 6. Evidence-lineage update

Slot-source corroboration must be counted by lineage, not by application count.

Current working graph:

```text
Nyatto / Flynnvali / community observation work
          |
          +--> Raven fallback implementation
          |
          +--> planner implementations / guides that cite Raven or the same research
          |
          +--> likely overlap with the workbook research corpus
```

A Raven/workbook agreement is valuable for implementation compatibility but cannot automatically be counted as two independent observations of live game behavior.

Stored Raven values are a separate evidence class again because they may be manually corrected or server/import supplied.

## 7. CRE implication: prediction provenance needs more structure

In addition to the already identified temporal fields (`effective_from`, `effective_to`, `supersedes`, known bug epoch), CRE should be able to distinguish:

- direct game observation;
- community empirical observation;
- derived heuristic prediction;
- manually corrected/curated value;
- imported third-party stored value of unknown ancestry;
- default/assumption used because a field was missing.

For each value/rule, source lineage should identify the upstream research ancestor where known so that Raven + planner + guide citations do not masquerade as three independent confirmations.

## 8. Evidence quality / adversarial status

**High confidence implementation facts**

- Raven fallback formula as currently published;
- Raven's unknown-reserve -> Pristine default;
- Raven's UI supports manual slot editing and persists system slot maps;
- workbook validation counts in the saved analysis memo.

**Strong inference, not yet direct formula proof**

- the 99.9568% workbook prediction column uses the same 6000/no-bio formula family as Raven.

**Still unresolved**

- exact workbook formula cells and equality boundaries;
- upstream provenance of each Raven stored slot value;
- whether current SrvSurvey upload paths omit slots (previous finding needs a clean current-tree re-verification);
- whether the two workbook residual `actual` values were true physical slots or affected by then-current Architect reporting;
- V3 reserve-level coverage and sensitivity.

## 9. Next research queue

Continue rather than close the audit:

1. Recover the exact `Colonization slot analysis.xlsx` formula cells or transformed formula-cell export.
2. Build a deliberately discriminating slot corpus around 1500 / 3750 / 6000 km, exact 700 K and 2.7 g boundaries, bio-only cases, atmosphere variants, HMC, terraformability and geo/volcanism.
3. Freshly re-observe the two historical workbook residuals under the post-July-2026 client.
4. Trace Raven stored-slot provenance through API/import/server and re-verify current SrvSurvey upload behavior.
5. Quantify V3 reserve-level missingness and run a read-only Raven-default sensitivity test: unknown vs Pristine/Major/Low/Depleted.
6. Obtain an independent post-Operations terraformable-Agriculture fixture.
7. Build controlled top-two / rank-three commodity cannibalisation fixtures.
8. Continue EDGalaxyData/EDDN/EDCAS historical-market feasibility work.
9. Build a post-July orbital-slot corpus with observation epoch and demolition/build state.
10. Run a read-only V3 sensitivity experiment replacing signal-count proxies and fake body-abundance `slots` with body-local predicates plus actual/predicted physical construction capacity.
11. Promote only after adversarial review into a versioned CRE model that preserves source lineage, temporal validity and assumptions.
