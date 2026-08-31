# V3 Ratings / CRE Forensic Audit — Checkpoint 03

**Research-only checkpoint.** No production writes, V3 database changes, scoring-code changes, or migrations were made.

## Executive delta from checkpoint 02

This pass moved from classifier/slot provenance into the cross-repo CRE↔ED-Finder knowledge contract. It found three high-impact issues:

1. **Terraforming is a real colonisation economy in the schema and official mechanics, but current Ratings/archetype scoring does not score it as an economy.** Worse, the archetype named `agriculture_terraforming` actually targets `('Agriculture', 'Tourism')`.
2. **The archetype/topology pair-synergy priors look like uncalibrated tuning constants rather than evidenced mechanics.** At least one stated rationale and one modifier conflict with Frontier's Update 3 body-economy table: gas giants are HighTech+Industrial, not HighTech+Tourism.
3. **CRE contains a direct unresolved contradiction with its own source-authority policy.** CRE knows Frontier Update 3 is the strongest official source and says official intended rules outrank community interpretation, yet M-0008/ER-0006/ER-0015/U-0007 preserve Mega Guide non-stacking as unresolved. Frontier explicitly says body overrides **may stack** and gives HMC+organics = Extraction + Agriculture + Terraforming as an example.

The root cause appears structural: CRE's latest direct claim-extraction pass was constrained to its committed `reference_sources/` pack (Mega Guide, DaftMav, illustrated link reference, dependency diagram), while official Frontier Update 3 was catalogued in a source-review document but was not included in the claim-level canonical extraction pack. This allowed a lower-authority community interpretation to survive against a known higher-authority official rule.

---

## A. Terraforming economy is missing/mislabeled in Ratings and archetypes

### Direct code/schema evidence

- `sql/001_schema.sql` defines `Terraforming` in `economy_type`.
- Frontier Update 3 explicitly says organics add **Agriculture + Terraforming**, and that overrides may stack.
- `build_ratings.py` stores economy scores for Agriculture, Refinery, Industrial, HighTech, Military, Tourism, and Extraction, plus a `terraforming_potential` feature — but **no `score_terraforming` economy score**.
- `build_archetype_scores.py` defines an archetype key/label `agriculture_terraforming` / “Agriculture / Terraforming Colony”, but its target `economy_pair` is **`('Agriculture', 'Tourism')`**.
- `ECONOMY_PAIRS` and `pair_synergy_constants` contain no Terraforming pair.

### Why this matters

An organics-rich or terraformable body can be genuinely useful for Agriculture/ Terraforming planning. Current archetype naming can tell the user it is assessing Agriculture/ Terraforming while the pair engine is actually evaluating Agriculture/ Tourism. That can alter body selection, facility recommendations, contamination reasoning, and the explanation layer.

### Adversarial alternative

Perhaps “Agriculture / Terraforming” was intentionally implemented as an Agriculture+Tourism strategic proxy. If so, it must be explicitly named/documented as a proxy and calibrated as such. No such rationale was found, and official mechanics treat Terraforming as its own economy.

### Falsifier

A design/calibration document demonstrating that Agriculture+Tourism is intentionally a validated predictor of desired Terraforming outcomes and that users are never meant to interpret the archetype label literally.

**Confidence:** High that the taxonomy mismatch exists; impact prevalence still needs measurement.

---

## B. Pair-synergy baselines are hypotheses, not mechanics constants

`sql/012_topology_tables.sql` and `build_topology.py` seed/fallback numerical pair priors such as:

- Refinery+Industrial 0.95
- Agriculture+Tourism 0.91
- HighTech+Tourism 0.88
- Extraction+Refinery 0.82
- ...down to Tourism+Refinery 0.22

The migration describes these as derived from “Trailblazers colonisation mechanics research (2025)”, but the repository search found no calibration dataset, regression, sample size, uncertainty interval, or direct observation table behind those exact numbers.

### Specific contradiction: gas giants and HighTech+Tourism

The migration rationale says HighTech+Tourism is strong because “Gas Giants and exotic star systems serve both.” Current `PAIR_MODIFIERS` also adds `+0.06` for gas giants to HighTech+Tourism, and the `hitech_tourism` archetype gives gas giants substantial body weight.

Frontier Update 3 says:

- Gas giant base overrides: **HighTech + Industrial**.
- Tourism strong-link boosts: ammonia world, black hole, ELW, geologicals, organics, WW, WD, neutron star.
- Gas giant is **not** listed as a Tourism boost.

A gas giant can still contribute strategically to a broader HighTech/Tourism system, but the direct “serves both” mechanic rationale is not supported by the official table.

### Consequence

Treat `pair_synergy_constants` and `PAIR_MODIFIERS` as **model priors / hypotheses requiring calibration**, not as known colonisation mechanics. CRE should eventually carry provenance/confidence per prior rather than one broad “mechanics research” label.

### Falsifier

A live observational corpus showing gas-giant placement independently raises Tourism strength, or a later Frontier rule superseding Update 3.

**Confidence:** High for missing provenance and official-table mismatch; Medium for net ranking impact until sensitivity testing.

---

## C. `weak_link_stability` encodes the opposite of the official modifier rule

`compute_topology_metrics()` currently computes:

- `weak_link_stability = 100 - tidal_lock*8 - icy*4`

with a comment describing resistance to weak-link degradation.

Frontier Update 3 explicitly says host body/system boosts and decreases apply to **strong links**, while **weak links are unaffected by this mechanic**. Icy and tidal locking are specifically listed as Agriculture strong-link decreases.

So the current metric uses strong-link environmental penalties to reduce something named weak-link stability. That is not just uncertain numeric tuning; the named mechanic conflicts with official semantics.

### Adversarial alternative

The metric might have been intended as a generic “system economy stability” heuristic rather than literal weak-link mechanics. If so, the name/comment and downstream use are misleading and should not be presented as weak-link behavior.

### Falsifier

Later official or broad live evidence showing icy/tidal body attributes directly weaken cross-body weak-link strength.

**Confidence:** High.

---

## D. CRE source-authority contradiction — higher-authority official rule was known but not promoted

### CRE governance says the right thing

`elite-dangerous-research-engine/evidence/source_authority_register.md`:

- SA-0001: official Frontier mechanics/patch notes are primary for intended rules.
- SA-0002: Mega Guide, DaftMav, Raven etc. are interpretation, not canonical truth.
- SA-0003: current live evidence outranks secondary references when implementation differs.

`evidence/colonisation_ai_data_sources_review.md` (2026-06-28) explicitly catalogs Frontier Update 3 (`4.1.2.0`) as **the single most important official source for market-link reasoning and economy inheritance logic**, trust High.

### But CRE mechanics preserve the opposite rule

`mechanics/M-0008-local-body-base-economies-and-modifiers.md` preserves the Mega Guide-derived claim that:

- local body modifiers do not stack with base planet economies;
- local body modifiers do not stack with each other.

It says no contradiction is recorded and gives working confidence 79%.

`mechanics/economy_rules_register.md` carries this into:

- ER-0006 “Modifier stacking remains unverified”;
- ER-0015 “Inheritable modifiers do not stack with each other”.

`docs/unknowns_register.md` carries it as U-0007, still asking whether rings/organics/geological activity stack.

### Official source resolves at least the economy-type stacking question

Frontier Update 3 states that these overrides **may stack**, with the explicit example:

- HMC + organics -> Extraction + Agriculture + Terraforming.

Therefore “does body override/modifier economy-type stacking occur?” is **not an unresolved unknown** under the Update 3 intended mechanic. What may remain unknown is exact numeric strength/duplicate-resolution when multiple effects contribute to the same economy.

### Likely ingestion failure mode

`docs/source_coverage_register.md` says the latest direct extraction pass was constrained to `reference_sources/`, whose active canonical extraction set is:

- MG-0001 Mega Guide;
- FW-0001 illustrated strong/weak reference;
- DM-0001 DaftMav extracts;
- DD-0001 dependency flowchart.

The official Frontier Update 3 source is catalogued in the broader source review, but it is absent from the claim-level canonical `reference_sources` extraction set. This can systematically let community interpretations outrank known official source material despite SA-0001.

**This is a CRE pipeline/governance issue, not just one stale claim.**

### Falsifier

Show a newer official patch explicitly rescinding override stacking, or live evidence proving current implementation no longer stacks and is intentionally different. In that case CRE should record “official intended rule vs current live implementation” as a contradiction, not silently preserve the Mega Guide rule as unresolved.

**Confidence:** High.

---

## E. ED-Finder source-priority document is now stale against CRE canonicity

`ed-finder/docs/reference/colonisation/source-priority.md` (created May 31; recovered July 8) currently ranks:

1. Mega Guide as primary mechanics authority;
5. Frontier/Fandom/forum posts as secondary clarification.

But the later Aug 10 CRE↔ED-Finder reconciliation says CRE becomes canonical and summarizes CRE SA-0001 as official mechanics/patch notes primary, with community guides SA-0002 interpretation.

This is a **documentation-level authority inversion inside ED-Finder**. The older source-priority file can still instruct future work to choose Mega Guide over Frontier, while the later CRE contract says the opposite.

No file was changed in this audit; record this for the future authorized integration/cleanup stage.

**Confidence:** High.

---

## F. Runtime mechanics metadata is too coarse for adversarial auditing

`apps/api/src/mechanics/versions.py` exposes one broad `MECHANICS_VERSION = 'colonisation-engine-v2.1'` and four generic source labels (Mega Guide, DaftMav v3, Frontier link explanation, community catalogue).

Numeric runtime constants in `economy_rules.py`, `link_rules.py`, and `scoring_rules.py` do not carry per-rule source IDs, effective dates, last verified game version, contradiction counts, or uncertainty bands.

This is expected to some degree because the Aug 10 reconciliation explicitly says full runtime CRE consumption is deferred. But it means **today's runtime mechanics constants cannot be forensically traced back to CRE at rule granularity**, so values such as:

- STRONG_LINK_BY_TIER = 0.4 / 0.8 / 1.2;
- link modifier deltas;
- economy-stack fit scores;
- body-selector point weights;

should be treated as implementation/model constants unless independently traced, not assumed to be CRE-verified mechanics.

CRE's own confidence design already specifies the desired future mechanic fields: confidence score/band, last verified version/time, contradiction and negative-evidence counts, patch sensitivity, decay state.

**Confidence:** High for provenance gap; no claim that every constant is wrong.

---

## G. Observational evidence supports Terraforming as a first-class market economy

Independent community observation in the Frontier Update 3 era records journal station economy mixes containing a distinct Terraforming value alongside Agriculture, Industrial, HighTech, Military, Extraction, Tourism, and Refinery. A May 1 2025 Frontier-thread report similarly shows a station with Terraforming at 100% among several economy percentages.

This is useful corroboration of the official taxonomy, not a substitute for Frontier's rule.

**Evidence quality:** Medium as live/community observation; official mechanic remains primary.

---

## Updated adversarial register

| Finding | Confidence | Main challenge / falsifier |
|---|---:|---|
| Terraforming omitted as a scored economy | High | Documented intentional proxy/calibration showing no separate score is required |
| `agriculture_terraforming` actually targets Agriculture+Tourism | High | None for code fact; only rationale could change interpretation |
| Pair-synergy constants lack visible calibration provenance | High | Locate hidden/older calibration dataset and methodology |
| Gas giant directly serves HT+Tourism | Low/contradicted | Later official/live evidence of Tourism boost from gas giant |
| `weak_link_stability` semantics conflict with Update 3 | High | Later evidence that body modifiers actually alter weak-link strength |
| CRE stacking unknown is stale vs official Update 3 | High | Later official rescission or current live divergence documented as a patch-era contradiction |
| CRE extraction pack structurally underweights official sources | High | Show official Update 3 claims are already ingested into claim/mechanic registers with precedence despite current M-0008 state |
| ED-Finder source-priority doc is stale vs Aug 10 CRE contract | High | Newer authoritative document superseding reconciliation |
| Runtime mechanics constants lack rule-level CRE traceability | High | Existing per-rule provenance map not yet located |

---

## Immediate next queue

### P0

1. **CRE official-source reconciliation audit:** enumerate all mechanics where official Frontier material already catalogued by CRE contradicts community-derived canonical claims. Start with Update 3 stacking, weak-link modifier immunity, body-economy table, then post-Dodec changes and Jul 2026 gas-giant slot patch.
2. **Terraforming end-to-end inventory:** ED-Finder schema/API/frontend/ratings/archetypes/simulator/CRE exports; identify where Terraforming is represented, omitted, aliased, or misnamed.
3. **Pair-prior sensitivity:** quantify ranking/archetype movement if uncalibrated pair constants and gas-giant HT+Tourism modifier are neutralized/recalibrated.
4. **Held-out slot validation:** continue workbook-vs-Raven, especially 5500 vs 6000 radius threshold and the two workbook exceptions.
5. **Raw-body classifier prevalence:** quantify how many V3 systems lose terraformable/tidal/bio/geo features under `_classify_bodies_simple()`; do not trust stale persisted archetype rows until rebuild freshness is established.

### P1

6. Trace `STRONG_LINK_BY_TIER` and all numeric link modifier deltas to evidence or mark them as model priors.
7. EDConstrDepot observed-market snapshot extraction path.
8. Golden real-system corpus: planner fixtures + Wregoe + public journal/market observations, with formula-derived expectations separated from observations.
9. Orbital-slot chronology pre/post Jul 1 2026 and legacy ring/belt anomalies.

### P2

10. CRE release-artifact provenance/contradiction/patch-decay audit.
11. Commodity-level self-sufficiency/cannibalization validation.
12. Define release-gate metrics for Ratings vNext against the golden corpus.

## Next checkpoint handoff

Start with P0 #1 and #2. The most urgent governance finding is not merely “one source was wrong”; it is that CRE already knew Update 3 was high-authority but its claim-extraction path did not promote that official source into the canonical mechanic layer. Test whether that pattern repeats across other patch-era mechanics before trusting CRE exports as a scoring source.