# V3 Ratings / CRE Forensic Audit — Checkpoint 04

**Research-only checkpoint.** No production writes, V3 database changes, scoring-code changes, or migrations were made.

## Executive delta from checkpoint 03

This continuation closed two follow-up questions and corrected one over-broad statement from checkpoint 03:

1. CRE is not merely old relative to July 2026: its current `main` has a **9 July 2026** commit, yet the 1 July Operations Update gas-giant slot correction still was not promoted into its mechanic/source layer. This strengthens the conclusion that patch ingestion is not systematic enough for a canonical live-mechanics source.
2. EDConstrDepot's market snapshots are much more useful than prospective speculation: the code explicitly saves full `market.json` snapshots, preserves station economy proportions, timestamp, station/system identity, and commodity `Items`, and can retain multiple numbered snapshots per market. That is a concrete empirical corpus format for before/after economy and commodity validation.
3. The runtime strong-link numbers `0.4/0.8/1.2` and weak-link `0.05` are not provenance-free after all. They map directly to the Mega Guide/community model. However, CRE itself labels the exact numeric strong-link behavior as needing live verification. The corrected conclusion is: **known secondary provenance, unverified exact live calibration**, not “no provenance”.

---

## A. CRE freshness failure is now patch-era, not just historical

Git history of `brianstewart377-rgb/elite-dangerous-research-engine` shows current `main` HEAD:

- `e6d34cfc20b91bec2e249dfd05cca400a47e1493`
- commit date: **2026-07-09**
- message: `Add B2a Agriculture negative test evidence`

Frontier's **1 July 2026 Operations Update** fixed:

- multiple Orbital Installations/Outposts being constructible around gas giants **despite the gas giant having only 1 construction slot**;
- incorrect reporting of available colonisation slots, especially after demolition.

Yet searches of current CRE mechanics/source material do not surface this patch rule. CRE's source-review/catalogue remains centered on the Jun 2026 source assessment and the claim extraction pack described in checkpoint 03.

### Implication

A canonical research engine for a live game needs more than confidence decay; it needs a patch-watch/update path that can:

1. ingest new official patch notes;
2. identify affected mechanics/claims;
3. supersede or downgrade old rules;
4. enqueue regression/live-verification work;
5. expose effective game-version/date in release artifacts.

The July gas-giant rule is an ideal regression fixture for this pipeline because the old community/observed state could genuinely differ from the post-patch intended state.

**Evidence quality:** High — current CRE commit history plus dated Frontier patch notes.

**Adversarial caveat:** CRE may not have been intended to auto-ingest every patch immediately. That does not make the repository wrong as research notes, but it does block treating its current exports as automatically current canonical truth for V3 scoring.

**Falsifier:** Locate a post-1-Jul CRE claim/mechanic/source record encoding the gas-giant one-slot rule and superseding older observations; current searches did not find one.

---

## B. Strong/weak link numeric provenance — corrected and sharpened

Checkpoint 03 said runtime link constants were too coarse to trace at rule granularity. That was too broad for this particular family.

### Runtime constants

`apps/api/src/mechanics/link_rules.py` has:

- T1 strong link = `0.4`
- T2 strong link = `0.8`
- T3 strong link = `1.2`
- weak link = `0.05`
- positive/negative strong-link modifiers approximately ±0.4 with a floor.

### Secondary source match

The current web Mega Guide states:

- strong links generally vary around 0.35–0.80 before modifiers;
- T1/T2/T3 base strengths are presented as 0.4 / 0.8 / 1.2 in community summaries derived from the guide;
- weak links fixed at 0.05 and unaffected by modifiers;
- a boosting modifier appears to add +0.4 and a decreasing modifier -0.4, floor 0.1;
- the guide explicitly says additional research is necessary for precise strong-link values.

CRE's own `experiments/live_verification_register.md` contains **LV-0006**, asking whether strong-link boosts/penalties really are additive ±0.4 with a 0.1 floor. Its confidence says the approximate rule is plausible but exact live numbers are not nailed down.

### Correct classification for Ratings/CPE

- weak link = 0.05: **strong community consensus / direct observations exist, but not an official numeric disclosure**;
- T1/T2/T3 0.4/0.8/1.2: **community model with observed support; not official canonical numeric truth**;
- ±0.4 link modifiers/floor 0.1: **community inferred, explicitly pending live verification in CRE**.

Therefore these numbers can be used as calibrated hypotheses in a simulator, but Ratings vNext should not silently treat them as exact mechanics constants without uncertainty/version metadata.

**Evidence quality:** Medium-high for the community model; lower than official qualitative link semantics.

**Falsifier:** sufficiently broad post-patch Journal/market observations demonstrating different numeric link strengths or tier behavior.

---

## C. EDConstrDepot market snapshots are a concrete empirical validation format

Repo: `CMDR-Squedie/EDConstrDepot`.

### What the code captures

`DataSource.pas` defines `TMarket` with:

- `Economies` from dock/StationEconomies;
- `MarketEconomies` from market visit;
- `Stock`;
- station/system/body/market identity and timestamps.

`MarketFromJSON()` parses full Frontier `market.json` data and the `Items` commodity array. It records positive stock and retains the original JSON as market status.

### Snapshot implementation

`CreateMarketSnapshot(mID)`:

- copies `markets/<MarketID>.json`;
- allocates numbered snapshot IDs (`MarketID.1`, `.2`, ...);
- injects `sEconomies` containing the observed station economy proportions;
- writes `markets/<snapshotID>_snapshot.json`;
- reloads it as a snapshot object.

Because the original `market.json` is copied, the snapshot retains the complete commodity `Items` array (including the market data Frontier emits) while adding observed economy proportions.

### Why this is high-value for CRE/Ratings

A shared snapshot series can create rows like:

`market_id, system, station, body, observed_at, station_economies, commodity, stock, demand, prices, facility_layout_state, source_file_hash`

With snapshots before and after a facility/link change, we can directly test:

- economy rank/strength movement;
- strong/weak link quantitative effects;
- commodity appearance/disappearance;
- cannibalisation/top-two protection claims;
- whether a facility changes only proportions or actual useful construction-material coverage.

This is much stronger evidence than comparing two formula-driven planners.

### Limitation

The public repo does **not** contain a corpus of users' snapshot files. The code establishes the format and collection capability, not a ready-made dataset. We would need voluntarily shared snapshots, user-owned files, or another public archive.

**Evidence quality:** High for the snapshot mechanism; prospective for population-scale validation.

**Falsifier:** none for the code behavior; empirical usefulness depends on obtaining adequately versioned before/after snapshots.

---

## D. EDConstrDepot independently preserves Terraforming as a first-class economy

`DataSource.pas` defines `TEconomy` with separate entries including:

- Agricultural
- Extraction
- Hightech
- Industrial
- Military
- Refinery
- Service
- Tourism
- **Terraforming**
- Colony
- Inherent

This is additional implementation evidence that treating Terraforming only as `terraforming_potential` while omitting it from ED-Finder's pair/economy scorer is a real taxonomy gap, not merely wording from Frontier.

Adversarial lineage note: this is still community code and may share Mega Guide/Raven understanding. It corroborates taxonomy, not mechanics weighting. Frontier remains the primary source that organics introduce a Terraforming economy override.

---

## E. Updated evidence hierarchy for link/economy calibration

For Ratings vNext / future CPE, separate three levels that current code sometimes blends:

1. **Official qualitative mechanic:** strong vs weak routing; same-body vs cross-body; weak links unaffected by body modifier mechanic; body economy override table; overrides may stack.
2. **Community numeric model:** weak=0.05, T1/T2/T3 strong≈0.4/0.8/1.2, modifiers≈±0.4, floor≈0.1.
3. **Observed calibration corpus:** market/journal snapshots before/after controlled facility changes; this is what should confirm or revise level 2.

A good Ratings score can use level 2 while clearly marking it model-derived, but should not present level 2 as if Frontier published those exact constants.

---

## Updated immediate queue

### P0 — continue next

1. **CRE official-source reconciliation sweep:** identify every current CRE claim contradicted/superseded by official sources already known or published through Jul 2026. Include Update 3 stacking/weak-link immunity/body table, Dodec-era balance, Jul gas-giant slots and demolition slot-reporting caveat.
2. **Terraforming end-to-end inventory:** trace schema, Ratings, archetypes, API, frontend, planner/simulator and CRE exports; distinguish economy score vs environmental potential.
3. **Raw V3 feature prevalence:** read-only quantify classifier-loss exposure (`terraformable`, tidal, bio, geo) and sampled score deltas.
4. **Held-out slot model validation:** workbook vs Raven; 5500/6000 and exact 700K/2.7g boundaries; inspect the two workbook exceptions.
5. **Topology/archetype freshness:** verify whether a full rebuild occurred after the Aug 5 dirty-gate fix before trusting persisted ranking distributions.

### P1

6. **Empirical market corpus design:** define an import spec for EDConstrDepot snapshot JSON + Journal/market observations + source/version hashes; seek public/shared examples.
7. **Strong-link calibration:** compare Mega Guide numeric model against observed market proportions in controlled systems.
8. **Pair-prior sensitivity:** neutralize/recalibrate unverified priors in offline fixtures and measure archetype rank movement.
9. **Golden systems:** add real-system planner fixtures, Wregoe direct evidence, and any EDConstrDepot/Journal snapshot sequences with observed vs predicted separation.

## Next checkpoint handoff

Resume with P0 #1. Treat CRE as a valuable structured research repository, but **not yet self-updating canonical live truth**: official-source promotion and patch supersession are now demonstrated weak points. In parallel, preserve EDConstrDepot snapshot JSON as a candidate first-class observation type for the future CRE evidence model.