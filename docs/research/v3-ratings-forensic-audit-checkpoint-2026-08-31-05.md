# V3 Ratings / CRE Forensic Audit — Checkpoint 05

**Research-only checkpoint.** No production writes, V3 database changes, scoring-code changes, or migrations were made.

## Executive delta from checkpoint 04

This continuation moved through the queued CRE reconciliation, Terraforming end-to-end, slot-model threshold, semantic-filter, and empirical-market-evidence work instead of stopping after one finding.

The strongest new conclusions are:

1. **CRE needs a versioned contradiction/supersession pass before V3 can treat a pinned CRE release as current mechanics authority.** Current CRE preserves a non-stacking body-override rule from Mega Guide v2.3, while Frontier Update 3 explicitly says those Colony-economy overrides may stack. A current independent planner implements the Frontier stacking rule. This is a contradiction to reconcile, not a safe timeless constant.
2. **Terraformability is not uniformly missing from ED-Finder.** Legacy v3.4 already reads explicit terraformable/state fields and uses them in Agriculture and a distance-weighted `terraforming_potential`. The serious loss is in the v4-ish topology/archetype classifier, where generic terraformable/tidal/bio/geo facts can be dropped.
3. **The Terraformable Agriculture +0.4 strong-link modifier is a textbook patch/bug/version-window mechanic.** Frontier documented it in 2025; Mar/Jun 2026 guides reported it not working; a matched real-game test on 18 Aug 2026 measured the exact +0.4 delta. CRE must model intended rule, observed implementation state, and evidence date separately.
4. **The official Agriculture tidal-lock decrease currently has contradictory live evidence.** A controlled 4 Aug 2026 test found no decrease where the official rule predicted one. This should be an explicit contradiction, not silently forced into scoring.
5. **The old 5,500 km surface-slot threshold note is almost certainly from the inferior JS heuristic, not the high-accuracy workbook model.** The workbook rows strongly support a 6,000 km radius cutoff, matching the current `ed-colonisation-planner` implementation. The two workbook exceptions remain genuine +1 anomalies rather than threshold mistakes.
6. **`ammonia_count` semantic contamination is confirmed, not hypothetical.** Existing stored/live validation includes canonical true-Ammonia positives and multiple gas-giant/ammonia-text false positives. Ratings vNext must separate true Ammonia World, ammonia atmosphere, and ammonia-life gas giant evidence.
7. **EDConstrDepot can provide a direct before/after market evidence protocol.** Its auto-snapshot path preserves the previous full Frontier Market JSON when the observed economy string changes, giving a practical route to test economy proportions against actual commodity stock/demand/prices.

---

## A. CRE official-source reconciliation: stacking is an active contradiction

### CRE current claim

Current CRE `mechanics/M-0008-local-body-base-economies-and-modifiers.md` says the committed source pack records:

- local body modifiers do not stack with base planet economies;
- local body modifiers do not stack with each other;
- planner behavior should preserve that as a caveated assumption and avoid double-counting until direct evidence says otherwise.

`mechanics/economy_rules_register.md` repeats this as `ER-0006` / `ER-0015`, explicitly marked `Needs verification`.

This is at least appropriately caveated in the rule register, but M-0008's planner blocking language is too strong for a live-current rule because primary official evidence points the other way.

### Primary official source

Frontier's Trailblazers Update 3 notes state that Colony-economy body overrides include base body type plus rings/organics/geologicals and explicitly say **“These overrides may stack.”** Frontier's example is an HMC with organics producing Extraction plus Agriculture and Terraforming.

### Current independent implementation

`gaborauth/ed-colonisation-planner` `src/domain/economyOverrides.ts` implements the official table as additive set accumulation. Its comments explicitly call the body override table stacked and keep separate strong-link boost/decrease logic.

### Adversarial review

Do **not** jump from “Frontier says stack” to “all live manifestations have always stacked correctly.” The Mega Guide/CRE non-stacking rule may encode real observed behavior that diverged from Frontier's intended design, just as the Terraformable modifier demonstrably did for months.

Correct classification now:

- **Official intended/current documented rule:** stacking.
- **Community observed/guide claim:** non-stacking exists and is evidence-bearing.
- **Current exact live behavior across body-base + rings + organics + geo:** needs a controlled post-Jul/Aug-2026 observation matrix.

### Falsifier / next test

Use matched Colony ports around bodies where exactly one, two, then three override categories overlap. Compare `StationEconomies` after activation. A single post-patch body showing only one mutually exclusive override where Frontier predicts three would falsify unconditional live stacking.

---

## B. CRE patch reconciliation gaps are broader than gas giants

Checkpoint 04 established that CRE `main` was updated after the 1 Jul 2026 gas-giant one-slot patch without promoting that rule.

This pass found three more rule families that belong in the contradiction/supersession layer:

1. **Body override stacking:** official “may stack” versus CRE/Mega Guide v2.3 non-stacking.
2. **Construction Point schedule:** old extracted guide schedule is not safe as current truth; newer planner/current observation uses sequential T2 3,5,7… and T3 6,12,18… with the primary excluded.
3. **Agriculture tidal-lock decrease:** official documented decrease versus 4 Aug 2026 matched observation showing no decrease.
4. **Terraformable Agriculture modifier:** official documented +0.4-style boost; reported broken through Mar/Jun 2026; matched Aug 2026 evidence shows it now works.

The current CRE contradiction register does not yet capture this full patch/current-behavior matrix.

### Required CRE model change (research conclusion, not implementation)

Mechanic claims need at least:

`claim_id, semantic_rule, source_lineage, source_version, documented_effective_date, observed_from, observed_to, status(intended/observed/bugged/superseded), contradiction_ids, verification_fixture`

A confidence percentage alone cannot represent “officially specified, live-bugged for months, then later starts working.”

---

## C. Terraforming end-to-end: legacy v3.4 is better than the v4 topology path

### Legacy v3.4

`apps/importer/src/build_ratings.py` already:

- reads `terraformable` / `is_terraformable`;
- falls back to recognized `terraforming_state` values;
- counts terraformables for relevant economy logic;
- accumulates a distance-weighted terraformability quality signal;
- publishes `terraforming_potential` separately from the seven legacy economy bars.

So the correct statement is **not** “ED-Finder loses Terraforming everywhere.”

### v4-ish topology/archetype

The serious problem remains the lightweight topology classifier documented in earlier checkpoints: early `continue` paths can prevent generic terraformable/tidal/bio/geo counters from being reached, and the topology worker does not consistently provide every needed field. Archetypes then weight topology/classifier outputs, so an apparently more sophisticated engine can be less faithful to canonical body evidence than the legacy scorer.

### V3 architecture fit

Latest V3 Masterplan v3.9 is compatible with fixing this correctly rather than copying V2 bugs:

- body physical/orbital state authority is Frontier-direct + primary aggregate with stable-physical reconciliation;
- CRE/DaftMav are domain-scoped curated mechanics/reference, not galaxy physical truth;
- ratings/clusters/topology/archetypes are deterministic generated products with pinned canonical input generations;
- ratings, topology, and archetypes are explicitly marked **REIMPLEMENT FROM BEHAVIOUR + TESTS**, not clone-V2 implementation.

This is exactly the boundary Ratings vNext needs.

---

## D. Terraformable Agriculture +0.4 has a real implementation timeline

### Official intent

Update 3 documents Terraformable as an Agriculture strong-link boost condition.

### Historical observed bug

Current Library copies of Dubior/Mega Guide record that, as of Mar/Jun 2026, the Terraformable Agriculture boost was believed not to work in-game.

### Current controlled observation

The current `ed-colonisation-planner` engineering notes preserve a matched real-game test dated **2026-08-18**:

- target: terraformable HMC, Hoey Enterprise;
- control: otherwise-matched non-terraformable HMC, Chawla Point;
- both received identical `Space_Farm` + generic Outpost pairs;
- Agriculture read **0.9** on the terraformable body versus **0.5** on the control;
- exact delta **+0.4**.

That directly falsifies the older blanket “Terraformable boost has no observable effect” claim for the current patch state.

### Confidence

High for the narrow matched case. Do not yet universalize across every body hierarchy or link-routing configuration.

### Falsifier

Repeat on at least three independent systems/body classes with the same controlled one-variable delta; also test surface vs orbital strong links.

---

## E. Tidal-lock Agriculture penalty is now explicitly contradictory

The same planner notes preserve a **2026-08-04** controlled test on three matched moons with identical Small Agricultural Settlement + cheap Outpost pairs. The observed `StationEconomies` Agriculture contribution was identical whether or not the tidal-lock chain to the star was present; it matched the no-decrease prediction down to the 0.05 weak-link granularity.

This contradicts Frontier's documented tidal-lock Agriculture decrease and the older guide assumption.

### Classification

- Official documented mechanic: decrease exists.
- Current bounded observation: no effect in the tested hierarchy.
- General live predicate: **Unknown**.

Possible explanations include a live bug, narrower tidal-lock predicate, hierarchy-specific behavior, or source/UI interpretation mismatch.

Do not put a universal tidal penalty into Ratings vNext until the predicate is mapped with controls.

---

## F. Surface-slot model: 6,000 km is now the leading threshold

The prior analysis report listed radius bands using **5,500 km** in its mismatch discussion, while the current `ed-colonisation-planner` uses:

- <1500 km = 1 base ground slot
- <3750 km = 2
- <6000 km = 3
- >=6000 km = 4
- +2 atmosphere
- +1 terraformable
- +1 HMC
- +1 geo
- cap 7
- eligibility requires landable, temperature <700 K, gravity <2.7g

The high-accuracy workbook mismatch dataset strongly supports **6000**, not 5500. Examples where workbook prediction is correct:

- icy bodies at 5.60–5.99k km with thin atmosphere repeatedly predict 5 slots, which is `3 base + 2 atmosphere` under 6000; a 5500 threshold would predict 6 and be wrong;
- rows at ~6.35k+ move to the four-base band as expected.

Therefore the old 5500 note appears to belong to the inferior later JS heuristic / analysis bucketing rather than the workbook's near-perfect model.

### Two true workbook exceptions

Only two rows remain:

1. `Dryio Flyuae OZ-O d6-1381 1`: actual 7, workbook 6; HMC, radius 6153.577 km, no atmosphere, geo/volcanism, not terraformable.
2. `DM99 4.3 1`: actual 6, workbook 5; HMC, radius 5235.61 km, no atmosphere, geo/volcanism, not terraformable.

Both are **actual = model +1**, both are HMC + geologically active/volcanic, but that pattern is not enough to invent a new rule because many other geo/volcanic HMCs do not form workbook mismatches.

### Adversarial conclusion

Do not overfit two anomalies. First re-verify those Architect slot counts post-Jul-2026, because Frontier also fixed incorrect available-slot reporting after demolition. If confirmed, inspect hidden attributes / reserve/resource state / atmosphere representation / body history before adding a factor.

---

## G. `ammonia_count` is confirmed semantic leakage

Existing read-only source/live validation already established:

- importer canonical ammonia detection uses exact `sub_type == 'Ammonia world'` or dedicated flag;
- legacy scorer/classifier broadens with an `ammonia` subtype-text fallback;
- stored/live rows include non-canonical bodies in `ammonia_count`.

Validated examples include:

- true positives: Eorgh Prou AA-A h24, Kruger 60, one 36 Ophiuchi hit;
- false positives: Brambai DL-Y g32 (ammonia-life gas giant), Lacaille 8760, Toolfa, Kokary, Omicron-2 Eridani, G 99-49, LP 816-60, G 89-32, Saktsak, and one mixed 36 Ophiuchi hit; HIP 70564 remains a likely polluted case.

This is important because legacy HighTech/Tourism scoring and a Finder slider can make `ammonia_count` look like “Ammonia Worlds”.

### V3/Ratings boundary

Use separate canonical facts:

- true Ammonia World;
- ammonia atmosphere/composition where useful;
- gas giant with ammonia-based life;
- unknown/ambiguous.

Only true body type should drive a specialist “Ammonia World” bonus unless a different mechanic explicitly names the other phenomenon.

---

## H. EDConstrDepot AutoSnapshots: direct market-transition evidence path

Further source inspection sharpened checkpoint 04.

`CMDR-Squedie/EDConstrDepot` tracks:

- dock-observed station economies;
- market-visit economy string;
- Market JSON / commodity items;
- Market ID, system/station identity, update times;
- numbered snapshots.

The update path can automatically snapshot the **previous** market JSON when the newly observed economy string differs from the economy associated with the previous market visit. `CreateMarketSnapshot` copies the old full `markets/<MarketID>.json`, injects the previous observed economy string/proportions, then loads the numbered snapshot.

### Why it matters

With voluntary/user-owned files, this can produce direct paired observations suitable for CRE evidence rather than planner-vs-planner comparison:

`market_id + timestamp + economy proportions + commodity supply/demand/prices + facility/link state + BGS/population`

### Adversarial limitations

- Snapshot trigger is economy-string change, not every facility completion.
- Commodity changes can happen without an economy-label change and then will not be automatically captured by this trigger.
- BGS state, wealth, population, weekly tick timing, and concurrent builds can confound before/after causality.
- Public repo proves the collection mechanism, not a public population-scale dataset.

### Proposed evidence protocol

For a usable controlled pair require:

1. before Market JSON hash/time;
2. after Market JSON hash/time;
3. StationEconomies before/after;
4. exact build activated/demolished and completion time;
5. local body canonical features;
6. Market Links before/after where available;
7. BGS state, population, wealth/dev/security at both observations;
8. game build / rule-window version;
9. commodity-level delta table.

---

## I. Commodity/supply guide claims: promote to hypotheses for empirical testing

Dubior's current guide provides useful quantitative hypotheses, but several are explicitly approximate/believed rather than proven constants:

- supply depends on production/consumption proportions, local-body station population, and wealth;
- T3 Orbis/Ocellus roughly ~6x Coriolis supply;
- WW roughly ~4x supply multiplier;
- ELW roughly ~6x;
- Dodec roughly ~1.5–2x other T3;
- T1 surface port roughly ~4–5x equivalent Coriolis;
- wealth relationship appears roughly linear above a major zero/nonzero discontinuity, exact function unknown.

These should become **test hypotheses** for the direct market corpus, not fixed Ratings constants.

---

## J. Updated evidence hierarchy / decision rule

For each mechanic, store and reason across four layers:

1. **Official documented intent** — qualitative/explicit Frontier rule.
2. **Community model** — guide/planner inferred formula and numeric constants, with lineage deduplication.
3. **Controlled live observation** — matched before/after game evidence.
4. **Population corpus** — many naturally occurring observations used to test scope and calibrate distributions.

A conflict between layer 1 and layer 3 is not automatically solved by choosing one. It becomes a versioned contradiction with a patch/build window and a regression fixture.

This is especially important for Terraformable Agriculture and tidal locking.

---

## Updated immediate queue

### P0 — next continuation

1. **Formal CRE reconciliation table:** enumerate current CRE mechanics/claims against official Update 3, Nov-2025/Dodec-era changes, Jul-2026 Operations Update, and current controlled observations. Assign `CURRENT / HISTORICAL / OFFICIAL-BUT-BUGGED / CONTRADICTED / UNKNOWN` rather than merely confidence.
2. **Orbital slot audit:** post-Jul-2026 rules for stars, ordinary planets, WW/ELW/ammonia, belts, ringed bodies, starting-station extra capacity, historic ring/belt bug, and Architect demolition-reporting caveat. Separate observed legacy-built capacity from current constructibility.
3. **Slot model exception audit:** re-verify Dryio Flyuae OZ-O d6-1381 1 and DM99 4.3 1 against any current Architect/Raven/Journal/community records; do not overfit before re-verification.
4. **Market-transition corpus:** locate actual EDConstrDepot snapshot examples, user-owned snapshots, or EDGalaxyData/EDDN histories for at least 3–5 colony markets and construct confounder-aware before/after deltas.
5. **Golden colony corpus expansion:** preserve existing golden systems and add controlled economy-link fixtures (Terraformable +0.4 positive, tidal no-effect contradiction, stacking multi-feature body, gas-giant one-slot, true/false Ammonia).

### P1

6. Quantify v3.4 score inflation from false-ammonia hits and remote bodies in a read-only fixture/sample path when authorized data access is available.
7. Rebuild a canonical surface-slot predictor from the 6000-band workbook logic and keep the two confirmed exceptions as regression fixtures, not magic corrections.
8. Audit current v4 archetype weights against canonical feature availability and remove dependency on broken topology summaries in future design.
9. Test Dubior supply/population/wealth multipliers against direct market histories.
10. Trace CRE release packaging so V3's `CRE release pin` can include effective game-window metadata and contradiction/supersession receipts.

## Next checkpoint handoff

Resume with P0 #1, but immediately move on to orbital slots and market-transition evidence once the reconciliation table is bounded. The working design principle is now stronger: **Ratings vNext should be generated from canonical physical evidence plus versioned mechanics, with official intent and observed live behavior stored separately whenever they disagree.**