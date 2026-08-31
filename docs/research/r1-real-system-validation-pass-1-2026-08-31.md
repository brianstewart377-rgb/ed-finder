# ED-Finder R1 — Real-System Validation Pass 1

Date: 2026-08-31  
Branch: `chatgpt-ed-new-ops-requests`  
Status: read-only evidence validation; no live Finder/rating/database changes.

## 1. Purpose

Exercise the new R1 evidence/assessment semantics against as many **real named systems** as are defensibly available in the current environment.

This is **not** a fresh production-database snapshot run. The current environment cannot reach the Hetzner PostgreSQL instance. Instead this pass uses:

1. archived ED-Finder read-only stored-data/live-API audit evidence already retained in the project handoffs/research corpus;
2. independently indexed EDSM/EDAstro material where available;
3. the already-tested R1 bridge invariants as the interpretation contract.

Every conclusion below is therefore version-bound. A later production read-only snapshot remains the authority for current canonical field values, freshness and slot predictions.

## 2. Validation rule

This pass does **not** ask whether the old score for a system was correct.

It asks whether the new R1 representation behaves correctly when confronted with the known real-system facts:

- base identity remains separate from modifiers;
- exact body identity beats substring/aggregate leakage;
- per-body distance remains visible;
- raw body surplus is not automatically a score;
- stale legacy ratings do not become R1 evidence;
- system capability is separate from candidate-plan resilience;
- missing field provenance remains Unknown rather than being guessed.

Outcome vocabulary:

- **Direct semantic pass** — archived body/stored-data evidence directly exercises an R1 rule.
- **Structural pass** — available real-system evidence confirms the new architecture avoids a known legacy failure mode, but a fresh full canonical rowset is still needed for detailed projection.
- **Regression-sample pass** — archived bounded stored/live validation provides a known true/false identity case.
- **Sparse-control pass** — confirms the redesigned model must tolerate real low-information/low-capability systems without inventing universal value.
- **Needs fresh canonical snapshot** — no contradiction found, but current field-level projection/slot prediction cannot be asserted from available evidence.

## 3. Primary golden/control systems

| # | System | Archived real evidence | R1 validation | Result |
|---:|---|---|---|---|
| 1 | Plaa Eurk ZR-M c7-2 | 3 ELW plus terraformable/HMC/landable evidence; old model leaked this into Military | ELW/civilian facts do not create a Military recommendation merely by existing | **Structural pass** |
| 2 | Blu Thua SU-W c2-5 | nearby civilian bodies plus remote B-side material cluster around 113k–115k ls | per-body distance is retained; remote material volume cannot silently equal compact support | **Structural pass** |
| 3 | Blu Thua JS-J d9-1 | 4 ELW + 4 WW + 7 terraformables in archived audit; independently indexed EDSM/GEC corroborates 4 ELW + 4 WW and terraformable WWs | exact civilian identities and Terraformable facts survive without military/material cross-contamination | **Direct semantic pass** |
| 4 | HIP 101924 | about 14 clean rocky + 15 HMC; extreme D-side components 450k+ ls | HMC remains HMC; distance remains local evidence instead of system-wide undifferentiated volume | **Structural pass** |
| 5 | HIP 294 | 3 nearby WW plus companion around 266k ls; old stored rating explicitly stale/null-version | stale rating/suggestion is excluded from R1 factual evidence; WW identity remains factual | **Structural pass** |
| 6 | HR 1188 | 11 HMC + 1 metal-rich + 2 geo; old Extraction 100 reconstructed as 84 + 12 + 5 = 101 clamp | HMC identity and geological modifier compose instead of replacing each other; canonical Extraction sources are positive | **Direct semantic pass** |
| 7 | Brambai DL-Y g32 | BH + NS + **gas giant with ammonia-based life**, not a true Ammonia World; archived old ammonia false-positive | exact Ammonia identity rejects ammonia-life gas giant | **Direct semantic pass** |
| 8 | Eorgh Prou AA-A h24 | true Ammonia World plus BH/brown dwarfs/terraformable evidence | exact `Ammonia world` remains a true positive | **Direct semantic pass** |
| 9 | HIP 70564 | 20 clean rocky, 32 landables, large generic inventory; ammonia pollution also observed/likely in prior bounded work | body volume is inventory/reserve evidence, not automatic fixed-plan fit; broad ammonia match must not be used | **Structural pass; ammonia detail needs fresh row snapshot** |
| 10 | Praea Euq PS-U c2-3 | 8 clean rocky, 27 landables; remote C-side bodies contribute to old score | per-body distance and allocation replace raw system-volume reward | **Structural pass** |

## 4. Sparse real-system controls

These were recovered in the earlier bounded Finder audit as genuine low-end real systems (the synthetic `Test` row is deliberately excluded):

| System | Historical observed old score | R1 role |
|---|---:|---|
| Wolf 359 | 18 | sparse-control; no universal value should be invented |
| Lalande 21185 | 3 | sparse-control; Unknown/limited capability remains legitimate output |
| UV Ceti | 3 | sparse-control |
| Yin Sector CL-Y d127 | 3 | sparse-control |

All four are **Sparse-control passes**. Their purpose is not to preserve the numerical legacy scores; it is to prevent the redesigned Finder from only understanding high-body-count systems.

## 5. Exact-Ammonia bounded regression sample

The earlier read-only stored/live audit found a strong broad-match failure pattern around the bubble. The new bridge's exact subtype rule is specifically designed to eliminate it.

### Confirmed/validated true-positive side

| System | Archived result | R1 expectation |
|---|---|---|
| Eorgh Prou AA-A h24 | canonical true Ammonia World | true positive |
| Kruger 60 | true-positive hit in bounded sample | true positive when exact body identity is `Ammonia world` |
| 36 Ophiuchi | mixed: one true and one non-true ammonia-style hit | classify **per body**, retaining the exact true Ammonia body while rejecting the non-Ammonia identity |

### Archived false-positive side

| System | Archived bounded result | R1 expectation |
|---|---|---|
| Brambai DL-Y g32 | ammonia-life gas giant, not true AW | reject true-Ammonia identity |
| Lacaille 8760 | false positive | reject unless exact canonical subtype is `Ammonia world` |
| Toolfa | false positive | same |
| Kokary | false positive | same |
| Omicron-2 Eridani | false positive | same |
| G 99-49 | false positive | same |
| LP 816-60 | false positive | same |
| G 89-32 | false positive | same |
| Saktsak | false positive | same |
| HIP 70564 | prior audit marked ammonia pollution likely/observed in the broader sample | do not promote without exact canonical body identity; fresh row snapshot required for final current verdict |

This is a **Regression-sample pass at the rule level**: unlike the legacy substring path, R1 has no code path by which the phrase `ammonia-based life` can itself create a true Ammonia World identity.

A fresh canonical row snapshot is still required to re-certify the current database rows for every named system.

## 6. Unique real systems exercised

This first pass covers **24 unique named real systems**:

1. Plaa Eurk ZR-M c7-2
2. Blu Thua SU-W c2-5
3. Blu Thua JS-J d9-1
4. HIP 101924
5. HIP 294
6. HR 1188
7. Brambai DL-Y g32
8. Eorgh Prou AA-A h24
9. HIP 70564
10. Praea Euq PS-U c2-3
11. Wolf 359
12. Lalande 21185
13. UV Ceti
14. Yin Sector CL-Y d127
15. Kruger 60
16. 36 Ophiuchi
17. Lacaille 8760
18. Toolfa
19. Kokary
20. Omicron-2 Eridani
21. G 99-49
22. LP 816-60
23. G 89-32
24. Saktsak

## 7. What this pass demonstrates

### A. Exact identity is materially safer

Brambai/Eorgh and the bounded ammonia sample are a strong real-data reason to retain exact identity and composable modifier facts. A system-level `ammonia_count` is not safe evidence for a true-Ammonia search if its lineage is broad-match legacy logic.

### B. Distance must remain local

Blu Thua SU-W c2-5, HIP 101924, HIP 294 and Praea Euq PS-U c2-3 all contain the kind of very remote components that made legacy system-wide volume misleading. R1's body-local representation preserves the information needed to distinguish compact usable support from remote surplus.

### C. Generic body volume must not be the rating model

HIP 70564 and Praea Euq are direct controls against rewarding the seventh, tenth or twentieth generic body as though it made the same fixed programme progressively better. Reserve/expansion can improve while fixed-plan fit plateaus.

### D. Positive specialist evidence still survives

R1 is not merely conservative. HR 1188 remains obviously interesting for Extraction because its actual HMC/metal-rich/geological evidence survives as independent positive facts. The redesign removes the false certainty of `100`; it does not erase genuine specialist capability.

### E. Plan resilience is correctly deferred

None of these system facts by itself proves that a future arbitrary build will maintain an Extraction/Refinery, Tourism/Agriculture or other top-two outcome. Candidate-plan resilience is intentionally evaluated after ED-Finder generates/receives an explicit plan.

## 8. What remains untested without a fresh production snapshot

For these real systems this pass **cannot** newly certify:

- current canonical `bodies` row freshness;
- source-confirmed negative vs importer-default `is_landable=false`;
- source-confirmed zero bio/geo vs missing scan evidence;
- current `body_rings` provenance and association state;
- exact per-body atmosphere/volcanism/tidal/temperature/gravity/radius coverage;
- exact surface-slot predictions on the named systems;
- current gas-giant orbital rows;
- current Evidence Store provenance linkage;
- generated candidate-plan resilience;
- calibrated Plan Fit or production ranking.

Those are precisely the reasons the bounded operator snapshot loader exists.

## 9. Independent public corroboration

As an external sanity check rather than canonical authority, currently indexed EDSM/GEC records describe Blu Thua JS-J d9-1 as a four-Earth-like/four-Water-World system; the GEC entry additionally notes two Water Worlds are terraformable. This is consistent with the archived ED-Finder civilian-positive control and provides no evidence against the new representation.

External public material is corroboration only. It does not replace the future Hetzner read-only snapshot.

## 10. Decision

**No category-level contradiction found in the first 24 real systems.**

The real-system evidence strongly supports continuing with:

- composable body facts;
- exact identity semantics;
- per-body locality/distance;
- explicit Unknown;
- reserve separate from fixed-plan fit;
- plan-relative resilience.

The next highest-value action remains a production **read-only canonical snapshot** of the golden systems and then a wider bounded sample using the operator loader already implemented. No live Finder cutover is justified yet.
