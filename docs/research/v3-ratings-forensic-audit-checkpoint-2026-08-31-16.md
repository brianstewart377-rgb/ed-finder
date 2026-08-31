# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 16

**Date:** 2026-08-31  
**Branch:** `chatgpt-ed-new-ops-requests`  
**Mode:** research/documentation only

## Safety boundary

Research only. No production changes, V3 database writes, migrations, or scoring-code changes were made.

## 1. Post-Operations community evidence still points to the 6000-km / no-bio surface-slot formula family

A current community discussion dated **17 August 2026**, therefore after the 1 July 2026 Operations update, states the then-current believed surface-slot rule as:

- temperature below 700 K;
- gravity below 2.7 g;
- radius breakpoints 1500 / 3750 / 6000 corresponding to base 1 / 2 / 3 / 4 slots;
- HMC +1;
- terraformable +1;
- volcanism +1;
- atmosphere +2.

The same discussion explicitly says an older 600–700 K penalty was outdated. It does not identify a biological-signal bonus.

This is useful because it is a **post-Operations** statement of current community consensus and agrees with Raven's published fallback and with the reconstructed 99.9568%-accurate workbook family from checkpoint 15.

### Evidence caveat

This is not independent laboratory confirmation. The discussion is part of the same highly connected colonisation-research community and may itself descend from Nyatto/Flynnvali/Raven research. Treat it as **freshness corroboration of the community model**, not a second independent experimental lineage.

## 2. Exact Raven boundary semantics are now explicit and should become golden tests

Current Raven source uses strict comparisons:

```text
if temp > 700        => zero
if gravity > 2.7     => zero
radius < 1500        => base 1
radius < 3750        => base 2
radius < 6000        => base 3
otherwise            => base 4
```

Therefore Raven specifically predicts:

- exactly 700 K remains eligible;
- exactly 2.7 g remains eligible;
- exactly 1500 km enters the base-2 band;
- exactly 3750 km enters the base-3 band;
- exactly 6000 km enters the base-4 band.

These are implementation facts, not yet proved game mechanics. A discriminating regression corpus should include values immediately below, exactly at, and immediately above every threshold.

## 3. The original almost-perfect workbook formula remains the missing primary artifact

Library search still surfaces the analysis memo and mismatch exports, but not a directly inspectable copy of the original `Colonization slot analysis.xlsx` formula cells in this run.

The evidence-pack README states that normalized source packs preserve `formula_cells/*.csv` separately from raw values and recommends checking the original workbook for formula relationships. This means exact formula recovery is still plausible, but it has not been achieved here.

Do not silently substitute the Raven source formula for the workbook formula simply because observed outputs strongly suggest equivalence. The correct evidence statement remains:

> the workbook's 99.9568% prediction is strongly reconstructed as the same 6000/no-bio family, pending direct formula-cell recovery.

## 4. Terraformable Agriculture: still one strong current lineage, not independent replication

Fresh search again found Dubior's 28 July 2026 updated-guide announcement stating that the Terraforming modifier now applies to all terraformable and Earth-like bodies as of the Operations update.

The same current community ecosystem contains August discussions that explicitly say some Raven behavior is still wrong or incomplete, including terraformable and tidal-locking mechanics. That strengthens the case that Raven should not be used as the adjudicator for this question.

However, this pass did **not** find a clean independent post-Operations controlled experiment with a before/after market or link measurement that isolates terraformability while holding other body modifiers constant.

So current evidence status should be:

- pre-Operations official intended rule: terraformability should affect Agriculture;
- pre-Operations observed bug: multiple community tests/guides said it did not;
- post-Operations current-guide claim: fixed / now applies;
- independent current experimental replication: **still missing**.

This remains a priority golden fixture rather than a settled mechanic promoted solely from one expert lineage.

## 5. Current commodity-planning discussion reinforces per-port top-two interpretation, but also exposes tool dependence

A 16 August 2026 community thread about top-two economies describes protection as evaluated from the economy bars for each port and discusses Raven's commodity estimator. Replies warn that some commodities can still be consumed when the producing economy is not protected in the top pair, and that Raven is not correct for every construction/economy interaction (notably Odyssey settlement link behavior according to the current guide author).

This is useful for test design: a golden commodity fixture should capture **one port at a time**, its ranked economies, linked constructions, actual market stock/supply/demand, and system state. Whole-system economy labels are insufficient to validate top-two protection.

Again, this is community evidence, not an official full mathematical specification. Frontier's Vanguards patch remains the primary authority for the existence of top-two supply protection; community observations are needed for tie/order and detailed netting semantics.

## 6. Adversarial downgrade: prior SrvSurvey slot-upload detail is not re-confirmed in this pass

Earlier work recorded that SrvSurvey's Raven `SitesPut` upload deliberately omitted slot counts. This run attempted to recover that exact current-tree implementation from the public `njthomson/SrvSurvey` repository, but GitHub search/tree inspection did not cleanly surface the earlier class/path in a way that supports a fresh citation.

Therefore that narrow implementation claim is downgraded to **pending re-verification** instead of being repeated as settled fact.

This does not alter the stronger Raven-Web finding from checkpoint 15: Raven's public UI allows manual slot editing and persists stored slot maps, so stored Raven values still cannot automatically be classified as direct game observations.

## 7. Evidence status after adversarial review

### High-confidence implementation facts

- Raven current fallback uses 1500 / 3750 / 6000, 700 K, 2.7 g, HMC, terraformable, geo/volcanism, atmosphere +2, cap 7, no bio.
- Raven exact comparison operators define equality behavior as above.
- Raven stored slot values can be manually edited/persisted in its public Web UI.
- Raven economy model turns missing reserve level into `Pristine`.
- workbook analysis measured 99.9568% accuracy on 4,632 landable bodies with only two residuals.

### Strong inference

- the workbook's almost-perfect prediction is the same 6000/no-bio family.

### Community-current but not independently replicated

- post-Operations terraformable Agriculture fix.
- current surface-slot formula consensus after Operations.

### Pending / unknown

- exact workbook formula cells and boundary equality semantics;
- provenance of Raven stored values;
- current SrvSurvey slot-upload behavior;
- fresh current-patch reobservation of the two workbook residuals;
- V3 reserve-level coverage and ranking sensitivity;
- independent post-Operations terraformable-Agriculture controlled fixture.

## 8. Next queue

Continue directly with the next unfinished work:

1. Recover exact workbook formula cells from the original workbook/evidence pack if available.
2. Build threshold golden tests immediately below/at/above 1500, 3750, 6000 km, 700 K and 2.7 g plus bio-only, atmosphere, HMC, terraformable, and geo/volcanism discriminators.
3. Fresh-reobserve the two historical residual bodies post-July-2026.
4. Trace Raven stored-slot ancestry/API import paths and re-verify current SrvSurvey uploader behavior.
5. Quantify V3 reserve-level completeness and read-only sensitivity to Raven's unknown→Pristine assumption.
6. Find an independent controlled post-Operations terraformable-Agriculture experiment.
7. Build per-port top-two/rank-three commodity fixtures from current markets.
8. Continue EDGalaxyData/EDDN/EDCAS history feasibility for before/after construction analysis.
9. Build the post-July orbital-slot corpus including demolition/build state.
10. Run the planned read-only V3 rating sensitivity experiment using body-local modifiers and real/predicted physical capacity instead of signal-count and fake-slot proxies.
