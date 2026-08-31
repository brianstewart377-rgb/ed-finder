# V3 Ratings / CRE Forensic Audit — Checkpoint 06

**Date:** 2026-08-31  
**Scope:** research only. No production writes, no V3 database writes, no scoring-code changes, no migrations.

## Executive delta

This pass materially changes the confidence hierarchy for several colonisation mechanics and exposes two important provenance defects.

1. **CRE `main` knows official Frontier patch notes should be the strongest mechanics source, but its current direct extraction corpus is community-only.** `evidence/source_catalog.md` lists Frontier official guide / Trailblazers / Dodec / later patch notes as the strongest intended-mechanics sources. However `docs/source_coverage_register.md` says the rerun extraction was constrained to `reference_sources/` and directly processed only Mega Guide (`MG-0001`), Strong/Weak illustrated reference (`FW-0001`), DaftMav (`DM-0001`) and the dependency flowchart (`DD-0001`). This is a source-governance gap, not just a documentation omission: it allowed an official contradiction to remain invisible in a promoted mechanic.

2. **CRE M-0008's non-stacking rule is directly contradicted by Frontier Update 3.** Current `mechanics/M-0008-local-body-base-economies-and-modifiers.md` preserves a claim that local body modifiers do not stack with base body economies and do not stack with each other, and blocks double-counting until evidence proves stacking. Frontier's Update 3 wording explicitly states that colony economy overrides **may stack**, and gives the worked example of a High Metal Content body with organics producing Extraction + Agriculture + Terraforming. The body/economy mapping table itself remains useful; the non-stacking subclaim must be classified separately as **CONTRADICTED**.

3. **The current external planner has an explicit Dodec-weighting source/implementation mismatch.** `gaborauth/ed-colonisation-planner` says its Dodec weighting constants are verbatim official values, but current constants do not match the official 11-Nov-2025 Dodec Update. The mismatch is definite. The exact effect on its solved scores still needs one further check: whether DaftMav v3.4.1's base stat rows already encode any Dodec-era weighting, which could create a separate double-adjustment issue.

4. **Current orbital-slot evidence needs to be split into present constructibility vs legacy/historical capacity.** Gas giants are now officially one construction slot after the 1-Jul-2026 fix. Historic ring/belt bugs can leave legacy systems with anomalous extra orbitals; those observations must not become current-slot rules. Star belts and planetary rings also need separate handling.

5. **The public CRE GitHub branch is older than the later recovered research programme.** Public `main` currently ends at `e6d34cfc` (2026-07-09) with mechanics M-0001..M-0013. The user's Aug-29 recovery report describes a later local/disk programme with M-0014..M-0042, 224 candidates and adversarial review on branch `journal-observation-export-consumer-20260828`, but that branch is not visible in the public GitHub repository. Do not infer that later work is lost; treat this as an integration/provenance gap until the recovered workspace is reconciled with GitHub.

---

## 1. Formal CRE reconciliation — M-0001 through M-0013

Status vocabulary for this audit is claim-level, not mechanic-file-level:

- `CURRENT_OFFICIAL` — current intended rule directly stated by Frontier.
- `CURRENT_OBSERVED` — current live behavior directly observed, with patch/date context.
- `CURRENT_COMMUNITY` — current community model/heuristic not yet primary-sourced.
- `OFFICIAL_BUT_BUGGED` — intended rule is official but live behavior has credible contrary observations.
- `HISTORICAL_NARROW` — valid observation for one context/version; must not be universalised.
- `CONTRADICTED` — stronger evidence directly conflicts with the claim.
- `UNKNOWN` — insufficient evidence for a planner-safe conclusion.

| CRE mechanic | Reconciled status | What survives | What must change / remain caveated | Falsifier / next test |
|---|---|---|---|---|
| M-0001 Water Worlds no surface slots | `CURRENT_OBSERVED`, high confidence | Planner must not invent WW ground slots; Wregoe evidence is strong operationally. | Current `100%` framing is observation-led rather than official-formula-led. Tie it to current slot observations and patch date rather than timeless certainty. | Any current post-Jul-2026 Architect/System Map showing a genuine buildable WW surface slot. |
| M-0002 Station economy not manually chosen | `CURRENT_OFFICIAL` core | Economy is shaped indirectly; no free manual final-economy selector. | Replace Wregoe-first provenance with Frontier Update 3 as primary support; retain Wregoe as observation. | A current Architect control that directly sets final colony-port economy independently of body/link context. |
| M-0003 One weak Refinery link failed to restore metals | `HISTORICAL_NARROW` | Exact Wregoe negative result is valuable and correctly non-universalised. | Add exact game build/date/economy state when available; do not use it as a universal weak-link threshold. | A later patch retest can supersede applicability, but does not invalidate the historical observation. |
| M-0004 CP / facility tiers | `CURRENT_COMMUNITY` / empirical | Tier-vs-CP separation, current-vs-projected-buildability distinction are useful. | Exact CP formulas/exceptions need current live/Architect validation and patch versioning. | Current Architect allowing/denying builds inconsistent with model under fully known CP ledger. |
| M-0005 Colony-type vs specialised ports | `PARTLY_CURRENT`, inferred taxonomy | Ports vs Supporting Facilities is official; station class is not final economy. | The finer `colony-type vs specialised inherent baseline` taxonomy is community/inferred, not fully official. | Controlled same-body same-links comparison showing a supposedly specialised baseline does not persist. |
| M-0006 Strong/weak link routing | `CURRENT_OFFICIAL` core + empirical edges | Same-body strong / cross-body weak distinction and modifier scope are official. | Numeric 40/80/120 strong contribution and flat 5 weak contribution are not official; main-port forwarding/display aggregation edges remain empirical/community. | Current controlled build with exact StationEconomies/MarketLinks inconsistent with routing model. |
| M-0007 Colony-port economy inheritance | `CURRENT_OFFICIAL` core | Body override + links shape colony-port economies; final commodity translation remains downstream. | Promote Frontier Update 3 to primary provenance; exact %→commodity behavior stays unknown. | Controlled port with known body/link graph whose economy lines violate all predicted inputs. |
| M-0008 Local body base economies & modifiers | `CURRENT_OFFICIAL` mapping + **`CONTRADICTED` non-stacking** | Body override table is strongly supported by Update 3. | Delete/demote blocking non-stacking rule as current truth. Frontier explicitly says overrides may stack. Keep individual modifier live-bug cases separately versioned. | A current official correction/patch explicitly reversing stacking, or systematic current observations proving the official rule is bugged for a defined modifier. |
| M-0009 Prerequisites / port escalation | `CURRENT_COMMUNITY` | Explicit prerequisite graph and escalating high-tier port-cost concept are useful. | Exact formulas and branch-specific prerequisite edges remain community-sourced / live-test-sensitive. | Current Architect prerequisite/cost sequence that diverges under fully known state. |
| M-0010 Rank protection / cannibalisation | `CURRENT_OFFICIAL` core + community detail | Vanguards Patch 1 officially protects produced goods of the top two economies from same-economy linked consumption. | Tie ordering, third+ interaction details and Appendix-D pair tables remain community/empirical. | Current market with known top-two rank whose own produced goods are cannibalised contrary to post-patch rule. |
| M-0011 Facility stats / service activation | `CURRENT_OFFICIAL` TL35 system floor + empirical deeper stats | Update 3.1 provides a minimum Tech Level 35 for colonised systems with only a single T2/T3 port, enabling Shipyard/Outfitting availability. | Current wording `T2/T3 ports grant TL35 immediately` is too facility-centric; official statement is a system-level minimum condition. Development soft-cap, Wealth and SoL effects stay empirical. | Single T2/T3 current system below TL35 after patch, absent a documented exception. |
| M-0012 Population growth/output | `CURRENT_OFFICIAL` qualitative + empirical quantitative | Facility population drives output; weekly maintenance growth curve, rapid first month then slowing, higher cap are official. | Exact 14-tick transition, logistic parameters and sqrt(output) are community/empirical and need separate evidence records. | Time-series facility population/output data showing a different quantitative relationship. |
| M-0013 System score/payments/caveats | `PATCH_SENSITIVE`; exact current form unresolved | Per-facility score/payout observations remain valuable; bug caveats should be retained. | Dodec made retrospective weighting changes to five stats. Any deterministic score table needs effective patch window and raw-vs-weighted semantics. | Recompute controlled current colonies from facility list and compare Architect score/dividend. |

### Adversarial conclusion

The main defect is **not** that CRE contains community evidence. That is legitimate research material. The defect is that community-derived mechanics can currently look like one coherent mechanic with one confidence number even when one subclaim is official, another is empirical, another is contradicted, and another is known-bug-sensitive. Ratings vNext should consume **claim-level evidence states**, never a single mechanic-file confidence as if it were a scalar truth value.

---

## 2. Dodec score-weighting contradiction in `gaborauth/ed-colonisation-planner`

### Official Frontier values — 11 Nov 2025

Frontier's Dodec Update says:

Initial Starport weighting:
- Development level **+20%**
- Security **+40%**
- Standard of Living **+40%**
- Tech Level **+20%**
- Wealth **+40%**

Subsequent facilities:
- Development level **-60%**
- Security **-20%**
- Standard of Living **-52%**
- Tech level **-66%**
- Wealth **-70%**

It explicitly says the change applies retrospectively to existing colonised systems.

Primary source lineage: Frontier announcement mirrored through Steam/SteamDB, Dodec Update, 2025-11-11.  
Reference: https://steamdb.info/patchnotes/20709049/

### Current planner constants

Current `src/data/buildings.ts` on `development` says the constants are `official, verbatim per-score percentages`, but contains:

```text
FIRST_STATION_BONUS
Development  +40%
Security     +40%
SoL          +40%
Tech         +20%
Wealth       +40%

SUBSEQUENT_FACILITY_REDUCTION
Development  -10%
Security     -10%
SoL          -20%
Tech         -25%
Wealth       -25%
```

`src/solver/solve.ts` actually applies these constants multiplicatively to the first-station contribution and the remainder of system contributions, so this is not merely stale prose.

### Verdict

**CONFIRMED SOURCE/IMPLEMENTATION MISMATCH.** At minimum:
- initial Development is wrong (+40 vs official +20), and
- all five subsequent-facility reductions are materially wrong versus official patch notes.

### Adversarial caveat before claiming exact score error

The planner's building rows are stated to be refreshed from DaftMav v3.4.1 `Stats`. We still need to determine whether those raw rows are truly unweighted base facility effects or whether DaftMav already incorporated some Dodec-era weighting. If the rows are pre-adjusted, the planner could have a double-adjustment problem in addition to wrong constants. Until that is checked, the implementation/source mismatch is certain but the exact numerical deviation of final solved scores is not yet fully quantified.

### Additional useful observation from planner issue #124

The same planner recently discovered that its prior derived `system_score_beta` model was wrong and replaced it with a real per-building `system_score` field after four current real-system checks matched 125/125, 45/45, 75/75 and 3/3. That is good evidence discipline and also a warning: apparently plausible stat formulas in community tools can survive until direct live calibration falsifies them.

---

## 3. Orbital-slot audit — current constructibility vs historical capacity

### Evidence hierarchy

| Case | Current audit status | Evidence | Planner implication |
|---|---|---|---|
| Gas giant | **1 current construction slot — `CURRENT_OFFICIAL`** | Frontier Operations Update, 1 Jul 2026, says multiple Orbital Installations/Outposts around gas giants were fixed because a Gas Giant only has 1 construction slot. | Any ED-Finder 3/5 gas-giant slot topology is stale for current constructibility. |
| Architect slot display after demolition / older state | **known reporting bug — `HISTORICAL_CAVEAT`** | Same Frontier update fixed incorrectly reported available colonisation slots, particularly after demolition. | Old screenshots/observations need date/state provenance before use as slot truth. |
| Ordinary stars/planets/moons | **exact orbital formula `UNKNOWN`** | Current community planner explicitly says no per-body formula was located; defaults to 1 orbital only as an editable floor. Dubior guide says most bodies 0-3 space slots, sometimes 4 with initial station. | Do not turn `1` floor or `0-3` distribution into a deterministic formula. |
| Star asteroid belts | **one dedicated Asteroid-Base-only slot per belt — `CURRENT_OBSERVED` community** | Planner issue #28 / #77 plus current source: star belts become synthetic one-slot bodies; issue #77 says in-game confirmed belt slot only accepts Asteroid Base. | Treat belt location separately from the star's ordinary orbit. Seek independent current validation before calling official. |
| Planet/moon rings | **asteroid eligibility of body's orbital location is `CURRENT_COMMUNITY`; multiple-ring capacity `UNKNOWN`** | Current planner deliberately does not generalise star-belt behavior to planetary rings; source comments say multiple rings unlocking >1 Asteroid Base remains unconfirmed. | Never count one extra orbital per planetary ring without observation. |
| Legacy ring/belt 10+ slots | **`HISTORICAL_BUG` / legacy-built state** | Dubior/current planner note old bug could create 10+ free slots and is believed patched; legacy systems can retain abnormal state. | Preserve as observed legacy capacity, never as current construction-rule prediction. |
| Initial station creates/permits fourth orbital | **`CURRENT_COMMUNITY`, post-Jul verification needed** | Dubior/community reports; current planner notes most 0-3 and `4 if initial station is built on that body`, but its estimator does not implement as a formula. | Build controlled post-Jul samples before using in Ratings feasibility. |
| ELW / WW orbital bias | **`CURRENT_COMMUNITY`, exact rule unknown** | Dubior says orbital-slot rework biased toward ELW/WW, but no current deterministic rule recovered. | Use observations, not class bonus constants, until tested. |

### Important refinement to issue #28

Issue #28's body text broadly says multiple belts/rings each grant their own orbital slot. Current source is more cautious and should control the interpretation:

- **Star belts:** each named belt is represented as its own dedicated synthetic constructible location. This is the stronger observed case.
- **Planet/moon rings:** ring presence makes that body's ordinary orbital slot asteroid-base eligible; current source explicitly says it is still unconfirmed whether all ring classes qualify and whether multiple rings add more Asteroid-Base capacity.

Therefore `multiple belts/rings -> N extra orbital slots` is **not** a safe universal rule.

---

## 4. Ground-slot model cross-check against current community code

The current `gaborauth/ed-colonisation-planner` `src/journal/eligibility.ts` independently implements the same leading empirical structure as our validated workbook:

- landable required
- temperature < 700 K
- gravity < 2.7 g, correctly converted to 26.477955 m/s² for Journal data
- radius bands `<1500 km = 1`, `<3750 km = 2`, `<6000 km = 3`, otherwise 4
- +2 atmosphere
- +1 terraformable
- +1 HMC
- +1 geological signals
- cap 7

This is **corroboration of the model lineage, not independent proof**: the planner itself says this is community research associated with Nyatto/Flynnvali/Raven and marks its estimate unverified. It nevertheless strengthens the conclusion that our current 6000-km leading threshold is not an accidental local spreadsheet artefact.

Our workbook remains much stronger empirically because it was validated directly against 4,632 landable bodies at **99.9568%**, with only two mismatch rows. The planner has not published equivalent validation coverage.

The two workbook exceptions therefore remain priority regression cases rather than a reason to discard the model.

---

## 5. CRE source-governance finding

### What CRE says it wants

`evidence/source_catalog.md` correctly ranks:
- Frontier official System Colonisation Guide,
- Trailblazers launch/balance notes,
- Dodec and later patch notes,
- official Journal manual

as the strongest sources for intended mechanics, patch drift and terminology.

### What current `main` actually extracted

`docs/source_coverage_register.md` says the direct extraction pass used only:
- `MG-0001` Mega Guide,
- `FW-0001` strong/weak illustrated reference,
- `DM-0001` DaftMav,
- `DD-0001` dependency flowchart.

That means the source authority policy and source ingestion reality diverge.

### Consequence already observed

M-0008 preserved a community non-stacking rule with 79% confidence and `Contradictions: None`, even though the official Update 3 rule says the exact opposite.

This is a concrete failure mode for Ratings vNext if it reads CRE summaries without resolving source lineage.

### Required CRE schema behavior for Ratings consumption

A mechanic/claim needs at least:

```text
claim_id
mechanic_id
source_lineage_id
source_authority_class
evidence_kind = intended_rule | direct_observation | inferred_rule | heuristic
observed_at / captured_at
effective_from_game_update
effective_to_game_update
status = current | historical | official_but_bugged | contradicted | unknown
contradiction_ids[]
falsifier
last_verified_at
```

A single mechanic-level confidence percentage is not enough.

---

## 6. Public CRE state vs later recovered research programme

Public GitHub `brianstewart377-rgb/elite-dangerous-research-engine`:
- `main` HEAD: `e6d34cfc20b91bec2e249dfd05cca400a47e1493`
- commit date: 2026-07-09
- mechanics visible on `main`: M-0001 through M-0013

User Library recovery report dated 2026-08-29 records a later local programme:
- local branch: `journal-observation-export-consumer-20260828`
- local HEAD: `8307934bab41d9f46318df67989c32ea7334b4a1`
- mechanics M-0014..M-0042
- 224 candidates
- adversarial review of 37 promotion groups
- release bundle validation complete

That branch is not currently visible in the public GitHub branch list (`main`, `CRE`, `docs/d1c-mechanics-index-count` were visible).

**Verdict:** the public repo cannot be assumed to represent the latest CRE knowledge. The recovered programme cannot be assumed canonical for Ratings until the local artifact/branch is reconciled. This is a provenance/integration problem, not evidence that either side should be discarded.

---

## 7. Newly discovered / elevated sources this pass

- **Frontier / SteamDB Dodec Update, 11 Nov 2025** — primary intended-mechanics authority for retrospective stat weighting. High authority.
- **`gaborauth/ed-colonisation-planner` current development branch** — very useful executable community model with unusually good comments, explicit uncertainty and real-game issue traces; lineage frequently DaftMav/Raven/Mega Guide, so not independent by default.
- **Planner issue #124** — four-system real-game validation that falsified its old derived system-score formula; valuable direct-observation methodology.
- **Planner issues #28 and #77** — current star-belt slot behavior / asteroid-base-only eligibility; useful direct community observation, needs independent corroboration.
- **CRE public GitHub repo** — exposed the gap between source authority policy and directly processed canonical corpus.

---

## 8. Adversarial challenges / what could change these conclusions

1. **Dodec weighting:** if DaftMav v3.4.1's stored `Stats` rows are already transformed values rather than raw facility contributions, the external planner's final error shape could differ from a simple constant mismatch. The source/implementation claim is still wrong, but final score error must be measured rather than assumed.
2. **M-0008 stacking:** Frontier says overrides may stack, which establishes intended mechanics. A live bug could still make one or more specific modifiers fail to stack. Those cases should become `OFFICIAL_BUT_BUGGED` subclaims, not revive a universal non-stacking rule.
3. **Star-belt slots:** issue evidence is direct but community-controlled. One independent post-Jul-2026 Architect observation should be added before marking it planner-hard truth.
4. **Planetary rings:** do not infer from star belts. Current evidence explicitly leaves multi-ring capacity unresolved.
5. **CRE `main`:** it may intentionally lag a later local branch. We need reconcile the Aug-29 release/recovery artifacts before treating July `main` as the true knowledge state.

---

## 9. Hypotheses to test against V3 data

1. **Gas-giant inflation:** quantify systems whose current Ratings/topology gains materially from obsolete 3/5 gas-giant orbital assumptions; compare their rank after forcing current 1-slot feasibility.
2. **Ring/belt inflation:** identify high-rated ring/belt-heavy systems and split `legacy anomalous capacity` from `current constructible capacity`.
3. **Classifier loss sensitivity:** rerun a bounded sample with terraformable/tidal/bio/geo fields preserved and measure economy/archetype rank movement, not just score deltas.
4. **Stacking assumption contamination:** find any Ratings/CRE-derived logic that effectively caps body override types as mutually exclusive and quantify affected systems (especially HMC+bio, HMC+geo, ring+bio/geo combinations).
5. **Dodec weighting golden colonies:** select colonies with fully known built-facility lists and current Architect stat readings; compare official weighting, DaftMav values and community-planner output.
6. **Slot model regression:** maintain the two workbook ground-slot exceptions as explicit golden failures while seeking the hidden discriminating property rather than weakening the 99.9568% model.

---

## 10. Updated immediate queue

### P0 — continue immediately

1. **Reconcile the Aug-29 CRE recovery bundle with public GitHub.** Locate the durable M-0014..M-0042 release/promoted files and source/contradiction registers; determine which claims supersede July `main` and whether official patch notes were ingested in that later programme.
2. **Validate Dodec weighting end-to-end.** Inspect DaftMav v3.4.1 row semantics / history, then calculate expected stats for one or more real fully enumerated colonies using official +20/+40/+40/+20/+40 and -60/-20/-52/-66/-70 weighting; compare external planner and current observations.
3. **Build a current post-Jul orbital-slot observation corpus.** Priority strata: ordinary star, ordinary HMC/rocky/icy, WW, ELW, ammonia world, gas giant, one-ring planet, multi-ring planet, one-belt star, multi-belt star, and a first-station-on-body case. Record game build, Architect/System Map state and demolition history.

### P1

4. Use EDGalaxyData / EDDN history and EDConstrDepot market snapshots to reconstruct before/after colony-market timelines for commodity-output validation.
5. Version-check current CP escalation and prerequisite chains against direct Architect/Journal observations instead of relying on a single community table lineage.
6. Map exactly which Ratings v3.4 and V3 derived fields depend on CRE/community assumptions, and build a patch-aware golden-system / golden-colony corpus for Ratings vNext.

---

## Checkpoint decision

Do **not** start changing scoring from these findings yet. The research now has enough evidence to reject several stale or over-broad assumptions, but the correct next step remains a versioned evidence reconciliation and bounded golden-corpus validation. In particular, do not replace the old gas-giant rule with a guessed universal orbital formula; use known official constraints plus observed slot values until the current formula is established.