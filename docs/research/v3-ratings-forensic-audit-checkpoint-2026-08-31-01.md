# ED-Finder V3 Ratings / CRE Forensic Audit — Supplemental Checkpoint 2026-08-31 01

Status: research-only checkpoint. No production changes, database writes, scoring changes, or migrations were made.

## Executive corrections from this pass

- **Current gas-giant slot assumption in `build_topology.py` is stale.** Frontier's Operations Update notes state that Gas Giants have only **1 construction slot**, fixing a bug that had allowed multiple orbital installations/outposts. Current ED-Finder estimates 3 orbital slots for an unringed gas giant and 5 for a ringed gas giant.
- **Architect slot observations need date/state provenance.** The same Operations-era notes also acknowledge incorrect reporting of available colonisation slots, especially after demolition. Historical observed values should therefore be tagged with patch/version and whether demolition/rebuild activity occurred.
- **The November 2025 Dodecahedron development weights changed almost immediately after rollout.** The initial release values should not be treated as current. Frontier's balancing update revised the primary station factors to Development/Security/Standard-of-Living/Tech/Wealth = **1.4/1.4/1.4/1.2/1.4**, and subsequent facilities to **0.9/0.9/0.8/0.75/0.75**, retroactively. Current EDConstrDepot code independently implements those revised factors.
- **`_classify_bodies_simple()` drops important modifiers for almost every recognized planet type.** `terraformable`, `tidal_lock`, raw `bio`, and raw `geo` increments occur after branches that `continue` for ELW, WW, ammonia, rocky ice, HMC, metal-rich, icy, rocky, and gas giants. Those variables therefore rarely reach topology/archetype scoring.
- **`has_ringed_gas_giant` is currently wired to `rocky_rings`.** The classifier never preserves gas-giant ring state, while the topology flag is set by `counts['rocky_rings'] > 0`; a ringed rocky body can therefore masquerade as a ringed gas giant.
- These classifier bugs directly affect scored concepts that Frontier now explicitly documents as mechanically meaningful: terraformability, tidal locking, geological signals, organics, body type, and same-body strong links.

## 1. Frontier mechanics now give us a stronger primary model than generic heuristics

Trailblazers Update 3 documents a clear structure:

- completed ports and supporting facilities automatically create economic links;
- **strong links** are local to the same body/object and provide larger boosts;
- **weak links** span different bodies and are weaker;
- supporting facilities do not link to one another;
- a port can contain multiple economy types, with linked economies proportionally introducing trade commodities;
- strong-link output is modified by host-body/system traits, while weak links are not;
- population determines output strength and grows weekly as the colony matures.

Frontier's documented environmental modifiers include, among others:

- Agriculture: boosted by ELW, terraformability, and organics; penalized by icy/tidal-lock circumstances.
- Extraction: boosted by major/pristine resources and volcanism; penalized by low/depleted reserves.
- High Tech: boosted by ammonia worlds, ELWs, geological signals, and organics.
- Industrial/Refinery: boosted by resource abundance and penalized by depleted resources.
- Tourism: boosted by ammonia worlds, black holes, ELWs, geological/organic signals, water worlds, white dwarfs, and neutron stars.

Frontier also documents body/object economy overrides/inheritance (ELW, WW, ammonia, gas giant, HMC/MR, rocky ice, rocky, icy, rings/belts, organics, geologicals) and states that overrides may stack.

### Rating consequence

A future self-sufficiency/development rating should not reduce this to `economy present = true`. At minimum it should model:

1. body-inherited economies;
2. same-body strong-link topology;
3. cross-body weak links;
4. environmental modifiers on strong links;
5. population/maturity;
6. actual commodity-market observations where available.

This is a research conclusion only; no implementation has been attempted.

## 2. Current topology/archetype code defects and likely score impact

### `_classify_bodies_simple()` control-flow defect

Recognized body branches `continue` before these generic counters are reached:

- `terraformable`
- `tidal_lock`
- aggregate `bio`
- aggregate `geo`

This creates systematic undercounting, not random missing data.

### Archetype amplification

Current archetype weights include:

- `agriculture_terraforming`: terraformable weight 0.60;
- `population_capital`: terraformable weight 0.80.

The body contribution formula gives each of the first three matching bodies `weight * 20` points before the body-score cap. Therefore one missed terraformable can represent roughly **12 raw body points** for Agriculture/Terraforming or **16 raw body points** for Population Capital; three can represent 36/48 raw points before caps/multipliers. Missed tidal-lock penalties can distort scores in the opposite direction, so the bug can both overrate and underrate systems.

### Ringed-gas-giant defect

`has_ringed_gas_giant = counts.get('rocky_rings', 0) > 0` is semantically wrong. Gas-giant rings are not preserved by the lightweight classifier. This should be treated as a data-model defect in research until corrected in a future implementation stage.

## 3. Gas-giant slot rule invalidates a major part of current topology scoring

Current `estimate_body_slots()` assigns:

- gas giant, no rings: 3 orbital slots;
- ringed gas giant: 5 orbital slots.

Frontier's July 2026 Operations Update explicitly describes Gas Giants as having **1 construction slot**, while fixing an issue that had allowed multiple orbital facilities.

This affects more than raw slot count because current topology also rewards gas giants via:

- `strong_link_potential`;
- orbital synergy;
- nesting potential;
- `has_deep_orbital_anchor`;
- some archetype body weights.

So gas-giant-heavy systems may be structurally overrated even if the final score does not display the slot estimate directly.

### Adversarial challenge

The one-slot interpretation should be falsified if an untouched, ordinary, post-fix gas giant can currently support more than one simultaneous independent construction slot in Architect Mode. Historical observations made during the multiple-slot bug should not be treated as current-rule validation.

## 4. Slot-data provenance rules need tightening

The user workbook remains the strongest measured surface-slot model found so far:

- 4,630 / 4,632 landable bodies correct = **99.9568%**;
- only two workbook mismatch rows remain in the saved regression set.

But it must still be validated out-of-sample against post-patch bodies and patch-state changes. Frontier has acknowledged slot-reporting defects, especially around demolition, so observed Architect slot counts should carry:

- observation date/game version;
- source method (Architect UI, journal, API, community import);
- demolition/rebuild state if known;
- confirmed vs inferred/predicted status.

Observed values should override prediction only when the observation itself is trustworthy for the current mechanics state.

## 5. Dodecahedron / development-factor chronology

Do not use the initial November 2025 rollout figures as current values.

The later Frontier balancing update revised effects to approximately:

| Context | Dev | Security | Standard living | Tech | Wealth |
|---|---:|---:|---:|---:|---:|
| Initial starport | 1.40 | 1.40 | 1.40 | 1.20 | 1.40 |
| Subsequent facilities | 0.90 | 0.90 | 0.80 | 0.75 | 0.75 |

The change was retroactive and Frontier stated that facility effects on economy attribution itself were not changed. EDConstrDepot's current Pascal source independently implements the same revised multipliers, which is useful corroboration but not a replacement for the Frontier source.

## 6. EDConstrDepot: useful implementation evidence, not primary truth

`CMDR-Squedie/EDConstrDepot` is active and encodes:

- body/economy inheritance sets broadly consistent with Frontier's documented rules;
- detailed facility construction requirements;
- revised development factors;
- local market/economy snapshots.

Use it as implementation corroboration and as a source of hypotheses/tests. Do not treat its static JSON lists as authoritative without comparing them to live/primary observations, especially because construction requirements and colonisation balancing can change.

## 7. Primary/live construction-requirement evidence exists

Frontier's Companion API and Journal can provide higher-provenance construction observations than static community lists.

The Journal `ColonisationConstructionDepot` event includes:

- MarketID;
- construction progress/completion/failure;
- ResourcesRequired;
- required/provided amounts and payment data per commodity.

Operations-era Companion API market data also exposes construction information, although later access restrictions mean details are visible only in certain ownership/docked contexts.

### CRE implication

A future CRE ingestion design should retain observed construction requirements with source, timestamp/game version, facility/MarketID identity, and observation context. Because CAPI visibility is limited, the resulting corpus will be crowdsourced/partial rather than complete.

## 8. Historical commodity-market evidence: EDGalaxyData is promising

Official EDDN documentation makes an important distinction: EDDN itself is a live relay and does **not** retain historical data. It points users toward EDGalaxyData archives, which capture EDDN messages over long periods.

This creates a possible empirical validation path for commodity outcomes:

- identify a player-built market/facility and completion window;
- retrieve market commodity messages before/after completion where archive coverage exists;
- compare supply/demand/economy changes with model predictions;
- use many such cases to build a golden observed-outcome corpus.

### Adversarial caveat

EDDN archive coverage is visit-triggered and non-random. Missing messages do not prove no market change. Any longitudinal result needs observation-density and timestamp checks rather than treating archives as continuous telemetry.

## 9. EDData's ~30M trade rows are not market history

Inspection of `EDDataAPI/eddata-collector` shows the trade table is keyed by `(market_id, commodity_id)` and commodity messages update/delete current state. A large row count therefore represents a broad current-state market corpus, not an append-only longitudinal history.

Use it for current-state coverage/cross-checking, not before/after causal inference.

## 10. Raven/SrvSurvey source-lineage caution

SrvSurvey publicly instantiates a Raven Colonial client/integration, but the searched public SrvSurvey repository exposes call sites rather than the underlying Raven colony calculation implementation. This means SrvSurvey should not automatically be counted as an independent confirmation of Raven's algorithm.

Likewise, BGS-Tally and multiple community planners use or reference Raven/DaftMav/Dubior inputs. Corroboration must be counted by **evidence lineage**, not by number of front ends.

## 11. Mega Guide version hygiene

A stale public mirror still exposes an old v1.3.x-era guide, while the author announced Colonization Mega Guide v2.0.0 in October 2025. Current research should use the newest live/user-library copy and trace claims to revision date. Web mirrors are not safe evidence of current mechanics simply because they rank highly in search.

## Adversarial review / falsification tests queued

- **Gas giant = 1 slot:** seek current post-July-2026 ordinary gas-giant Architect observations that contradict it.
- **Dodec revised factors:** seek later Frontier patch/balance changes or current observed development screens inconsistent with the 1.4/0.9 family.
- **Surface slot workbook:** validate against bodies not used to derive the workbook and specifically against post-patch observations; retain the two known exceptions as regression cases.
- **Classifier bug impact:** read-only recomputation should measure archetype rank flips after correctly counting terraformable/tidal/bio/geo rather than assuming the theoretical effect translates linearly to final ranks.
- **EDGalaxyData market histories:** verify archive/index accessibility and sample density before claiming it can support causal before/after analysis.
- **Community JSON requirements:** compare static values with Journal/CAPI observations and patch dates before CRE ingestion.

## Read-only V3 hypotheses worth testing

1. Re-benchmark the topology slot estimator after replacing gas-giant 3/5 assumptions with the current one-slot rule, separately from the high-accuracy surface model.
2. Measure how many V3 bodies have terraformable/bio/geo/tidal data that `_classify_bodies_simple()` currently ignores.
3. Recompute a sample of archetype scores with classifier counters repaired and measure rank/label flips, especially Agriculture/Terraforming and Population Capital.
4. Identify high-ranked gas-giant-heavy systems and quantify how much of their topology/archetype score comes from obsolete slot abundance assumptions.
5. Preserve the workbook model and its two mismatch cases as a regression suite; add new post-patch independent observations.
6. Build a small EDGalaxyData before/after market experiment around known colony facility completions.
7. Compare EDConstrDepot/static construction requirements against observed Journal/CAPI requirement payloads.
8. Validate revised Dodec/system-development factors against contemporary observed systems.

## Persistent queue for next research passes

1. Trace Raven Colonial's current slot/economy implementation or API behavior as far upstream as publicly obtainable; do not count SrvSurvey/BGS-Tally as independent if they share Raven lineage.
2. Inspect EDGalaxyData archive/index format and attempt a concrete colony-market timeline.
3. Locate and version-check the newest Mega Guide v2.x in the user's Library/live source; compare key tables against Frontier and current community implementations.
4. Audit CRE provenance, contradictions, freshness/versioning, and missing evidence types.
5. Audit V3 field completeness for all variables Frontier says affect strong links and body inheritance.
6. Build commodity outcome/self-sufficiency evidence matrix from official rules plus observed markets.
7. Expand golden-system/golden-colony validation corpus, with explicit source/version tags.
8. Validate orbital-slot rules by body type separately from the high-accuracy surface-slot workbook.
9. Continue adversarial review of archetype/topology hand-tuned weights and saturation/compression behavior.
10. Trace every apparent corroborating source to upstream lineage to avoid circular validation.
