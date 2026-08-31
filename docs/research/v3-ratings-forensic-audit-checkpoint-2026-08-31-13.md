# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 13

Date: 2026-08-31
Scope: research only. No production writes, V3 database writes, scoring-code changes, or migrations.

## This iteration

This pass continued from checkpoint 12 and deliberately moved through multiple unfinished items:

1. corrected checkpoint 12's statement that Raven's public web frontend did not expose the surface-slot predictor;
2. located and audited Raven Colonial Web's actual public surface-slot predictor and its commit/PR provenance;
3. compared that predictor with the previously validated 99.9568% workbook model and the two residual cases;
4. audited `gaborauth/ed-colonisation-planner`'s slot heuristic and established that it is the same community/Raven lineage, not independent corroboration;
5. located and audited Raven Colonial Web's current economy calculation implementation, including strong/weak links and body modifiers;
6. adversarially re-checked the post-Operations terraformable-Agriculture claim against Raven's current code/history;
7. identified EDData API as another current EDDN-backed cross-sectional market source, while finding no documented longitudinal-history endpoint in its published API overview.

## Important correction: Raven's surface-slot predictor is public

Checkpoint 12 said the obvious Raven web frontend paths inspected did not surface the slot algorithm. That was incomplete and is now corrected.

The public repository `njthomson/RavenColonialWeb` contains:

`src/slot-prediction.ts`

Current source:
https://github.com/njthomson/RavenColonialWeb/blob/main/src/slot-prediction.ts

The current function is short and explicit:

- unknown body type -> `-1`;
- temperature > 700 K -> 0;
- gravity > 2.7 g -> 0;
- non-landable -> 0;
- base slots by radius: `<1500 km = 1`, `<3750 km = 2`, `<6000 km = 3`, otherwise 4;
- HMC +1;
- terraformable +1;
- volcanism OR geologicals +1;
- atmosphere +2;
- cap at 7.

There is **no biological-signal bonus** in this current Raven function.

This is directly inspectable code, not an inferred behavior.

### Provenance and freshness

The file's path history contains one introducing commit, merged on **19 November 2025**:

`cd7c9d88077f4caf3885c85345d683534e1033a1` — `Predict surface slots when they are unknown (#25)`

PR #25 states explicitly that the slot assignment logic was reverse engineered in a community effort and links the Frontier forum thread:

https://forums.frontier.co.uk/threads/studying-planetary-build-slots.642609/

PR:
https://github.com/njthomson/RavenColonialWeb/pull/25

No later commit on the `slot-prediction.ts` path surfaced in the repository history inspected in this pass. Therefore the public Raven predictor should currently be treated as a **November-2025 community-derived implementation unless separately demonstrated to have changed elsewhere**.

This is materially stronger provenance than the previous vague `Nyatto / Flynnvali / community -> Raven` lineage: we now have a specific merged implementation and a specific source thread.

## Raven vs the validated workbook: they are not the same implementation

The previously analysed `Colonization slot analysis.xlsx` remains the strongest empirical asset available to this audit: its own `Prediction (Surface)` matched 4,630 / 4,632 landable bodies (99.9568%), with only two residuals.

The analysis report identified threshold/behavior areas including radius boundaries at 1500 / 3750 / 5500, a biological term, and atmosphere +2/+1 behavior. Raven's current public code instead uses a 6000 km third radius breakpoint, contains no biological bonus, and applies atmosphere +2 unconditionally.

Do **not** infer from this alone that Raven is wrong: the workbook's exact formula needs to be recovered/re-materialized rather than reconstructed from the audit memo. But it is now proven that the current Raven source is not safely interchangeable with the high-accuracy workbook model.

### The two workbook residuals are not explained by Raven

Using the stored residual-body fields:

- `Dryio Flyuae OZ-O d6-1381 1`: HMC, radius 6153.577 km, no atmosphere, non-terraformable, geo/volcanism present. Raven -> base 4 + HMC 1 + geo/volcanism 1 = **6**, while observed was 7.
- `DM99 4.3 1`: HMC, radius 5235.61 km, no atmosphere, non-terraformable, geo/volcanism present. Raven -> base 3 + HMC 1 + geo/volcanism 1 = **5**, while observed was 6.

So Raven reproduces the workbook's residual predictions rather than resolving them. This strengthens the existing decision **not** to invent a broad +1 rule from two exceptional observations.

Adversarial caveat remains important: Frontier's July 2026 Operations update fixed erroneous Architect slot reporting in some states, especially after demolition. Re-observe these bodies under current patch state before treating their historical `actual` values as formula truth.

## `ed-colonisation-planner` is another derivative of the same slot lineage

Current source:
https://github.com/gaborauth/ed-colonisation-planner/blob/main/src/journal/eligibility.ts

Its header is unusually honest and useful. It explicitly says the Journal does not report real slot counts, labels the output **UNVERIFIED**, attributes the ground-slot research to **CMDR Nyatto, Flynnvali and others**, and points users to Raven for the most up-to-date algorithm.

Its ground-slot implementation matches the current Raven family closely:

- 700 K cutoff;
- 2.7 g cutoff;
- radius 1500 / 3750 / 6000;
- atmosphere +2;
- terraformable +1;
- HMC +1;
- geological +1;
- cap 7.

Its orbital estimate is explicitly only **one orbital slot per star/planet as a starting floor**, not a real per-body orbital formula. It tells users to correct it against the System Map.

Therefore Raven + this planner do not constitute independent corroboration of slot mathematics. They share named upstream research and essentially the same implementation shape.

**Evidence-lineage conclusion:** count this as one community algorithm family until independent raw observations demonstrate otherwise.

## High-value threshold corpus now has precise targets

The Raven/workbook divergence tells us exactly where to spend current in-game observation effort:

- radii immediately around 5,500 km and 6,000 km;
- bodies with biologicals but no geo/volcanism and otherwise matched properties;
- different atmosphere states where the workbook appears to distinguish +2/+1 behavior;
- HMC vs non-HMC matched pairs;
- terraformable vs non-terraformable matched pairs;
- 700 K and 2.7 g boundary cases;
- the two historical residual HMCs.

For each observation record: patch/build date, System Map/Architect state, whether any construction/demolition occurred, source of `actual`, full body fields, Raven prediction, workbook prediction, and observed slot count.

This is a better golden corpus than random systems because it maximizes formula discrimination.

## Raven's economy implementation is also public and much richer than assumed

The current `RavenColonialWeb` repository contains `src/economy-model2.ts` with `useNewModel = true`.

Current source:
https://github.com/njthomson/RavenColonialWeb/blob/main/src/economy-model2.ts

### Intrinsic/body economy identities

The code implements the expected Update-3 body inheritance family:

- BH/NS/WD -> High Tech + Tourism;
- ordinary stars -> Military;
- ELW -> Agriculture + High Tech + Military + Tourism;
- WW -> Agriculture + Tourism;
- Ammonia -> High Tech + Tourism;
- gas/water giants -> High Tech + Industrial;
- HMC/MR -> Extraction;
- rocky ice -> Industrial + Refinery;
- rocky -> Refinery;
- icy -> Industrial;
- asteroid -> Extraction.

It then adds distinct modifier identities for rings, biologicals and geologicals while deliberately suppressing duplicate same-economy additions for body classes that already provide that economy.

This code is consistent with the interpretation developed earlier in the audit: **distinct economy identities can coexist/stack, while duplicate sources of the same intrinsic economy do not simply sum into multiple 1.0 copies.**

### Strong and weak links

Raven currently models:

- T1 strong link: +0.4;
- T2 strong link: +0.8;
- T3 strong link: +1.2;
- weak link: +0.05 per applicable facility/economy;
- colony-type ports can pass intrinsic economies through link topology;
- supporting-port/sub-strong-link behavior is explicitly modeled.

These values are community/empirical model inputs, not all official Frontier numbers. They should be treated as testable implementation claims rather than promoted wholesale into CRE.

### Important default-risk: missing reserve level becomes Pristine

Both the strong-link boost logic and general buff logic contain:

`const reserveLevel = site.sys.reserveLevel ?? 'pristine';`

So if Raven lacks a reserve level, it defaults to **Pristine**, which can add +0.4 to Extraction/Industrial/Refinery calculations.

That is a potentially material optimistic bias for incomplete source data. CRE/ED-Finder should not copy this behavior silently; unknown resource level should remain unknown or carry an explicit assumption/confidence penalty.

**Falsification test:** select systems where reserve level is missing in the input but known in-game and compare Raven output before/after explicitly setting the correct reserve level.

## Terraformable Agriculture: Raven is currently internally split and likely stale on one path

This pass makes the post-Operations issue much more precise.

Raven's `applyBuffs()` currently gives Agriculture +0.4 when the body has **BIO OR TERRAFORMABLE** (and otherwise ELW/WW), so terraformability is recognized in one current code path.

However, `applyStrongLinkBoost()` contains a deliberately disabled new-model branch:

`if (useNewModel && false) { ... TERRAFORMABLE ... }`

and the active fallback only boosts Agriculture for **ELW/WW or BIO**, with a source comment explicitly questioning terraformable support.

The file history is also revealing:

- **19 May 2026** commit: `Stop honouring AGRI boost due to Terraformable`;
- **20 May 2026**: tidal/display work;
- **15 August 2026**: black-hole double-count correction;
- no explicit July/August commit surfaced that says terraformable Agriculture was re-enabled after Operations.

Therefore the safe conclusion is **not** “Raven ignores terraformability.” It is:

> Current Raven source applies terraformability in the general body-buff path but still deliberately excludes it from the strong-link-boost path, and its history contains no explicit post-Operations re-enable commit. This is a plausible current inconsistency/stale branch of the model.

This strengthens the priority of a controlled post-Operations live fixture. A Raven/current-guide agreement is not enough because the implementation itself has two different paths.

## Other Raven model details that deserve adversarial fixtures

Several implementation choices should be tested rather than trusted by authority:

- unknown reserve level defaults to Pristine;
- Tourism applies separate +0.4 system boosts for the presence of a black hole, neutron star and white dwarf type;
- Odyssey settlement High Tech buffs can stack BIO and GEO separately in the `useNewModel` path, while non-settlement behavior uses a combined condition;
- numeric adjustment never falls to zero: values <= 0 are floored to 0.1;
- colony-to-colony/sub-strong-link propagation contains special-case logic that needs live fixtures.

These are excellent CRE candidates for `implementation_claim` / `community_model` status with targeted falsification tests.

## New current-market source: EDData API

A public project `EDDataAPI/eddata-api` exposes an EDDN-backed REST API and documents system, station and commodity/trade endpoints:

https://github.com/EDDataAPI/eddata-api
https://github.com/EDDataAPI/eddata-api/blob/main/API_OVERVIEW.md

Its documented API supports current/recent market queries and age filters (for example commodity imports/exports with `maxDaysAgo`, and system market/commodity endpoints). The published overview does **not** expose a clear longitudinal per-market history endpoint.

So classify it as:

- useful **cross-sectional/current market validation source**;
- potentially useful for rapidly locating golden markets;
- **not yet a substitute for EDGalaxyData's archived EDDN messages** for before/after facility construction timelines.

This is an additional source to test, not a replacement for the history queue.

## Adversarial review

### Evidence quality

- **High:** exact Raven slot/economy source code and Git commit/PR history; exact `ed-colonisation-planner` source comments and constants.
- **High for provenance / medium for mechanics truth:** Raven PR #25 explicitly traces the slot code to the community reverse-engineering thread. That proves ancestry, not that the formula is still correct in August 2026.
- **High:** current code demonstrates Raven's reserve-level default and split terraformable-Agriculture logic.
- **Medium:** the workbook-vs-Raven structural comparison until the original workbook itself is re-materialized and the exact workbook formula extracted.
- **Medium-low:** the two historical residual `actual` counts until re-observed under a post-July-2026 clean Architect state.

### Circular-sourcing correction

The evidence graph is now more concrete:

`Frontier/community 'Studying planetary build slots' thread -> Hao Hu PR #25 / Raven slot-prediction.ts -> Raven UI/API consumers`

and independently at the application layer:

`Nyatto/Flynnvali/community slot research -> ed-colonisation-planner eligibility.ts`, with the planner explicitly pointing back to Raven.

This is one research lineage with multiple implementations/clients, not multiple independent experiments.

### What would falsify the main conclusions

- A newer Raven slot source path or server-side override that is actually used instead of `slot-prediction.ts` would invalidate the assumption that this file represents current fallback prediction behavior.
- A full current Architect threshold corpus matching Raven at the 6000 km / no-bio / atmosphere+2 rules and contradicting the workbook model would show the workbook is stale despite its historical accuracy.
- A controlled post-Operations Agriculture fixture showing terraformability has no effect would falsify the current-guide claim that the bug was fixed.
- A controlled fixture showing Raven's strong-link result includes terraformability despite the disabled code path would indicate another path/model layer is supplying the effect.

## Hypotheses to test against V3 / read-only analysis

1. The 5,500–6,000 km radius band will be disproportionately informative for distinguishing the validated workbook predictor from the November-2025 Raven family.
2. Current Raven will not resolve the two workbook residuals because its published formula produces the same 6 and 5 predictions on those bodies.
3. Treating Raven/planner agreement as independent confidence currently overstates evidence confidence in CRE.
4. Systems with missing resource-level data can receive optimistic economy estimates in Raven due to the `?? 'pristine'` default; an ED-Finder model that preserves Unknown should be better calibrated.
5. Raven's partial/stale terraformable-Agriculture paths can create location/build-dependent disagreements after Operations; this should be visible in carefully chosen current colonies.
6. A vNext mechanics layer should carry the **source implementation version and effective game epoch**, not merely a rule label, because Raven's May-2026 bug workaround remains visible in August-2026 code.

## Unresolved questions

- Can the original `Colonization slot analysis.xlsx` workbook be recovered/materialized again so its exact formula can be extracted rather than inferred from the audit memo?
- What raw observations and exact formula derivation are contained in Frontier forum thread 642609, and which commanders supplied each threshold?
- Is Raven's `slot-prediction.ts` definitely the fallback path used by the live August-2026 web UI for unknown slots, or is there a server-returned value that supersedes it first?
- Has anyone independently re-tested the 5,500/6,000 km boundary after July 2026?
- Does live Raven currently produce a terraformability Agriculture strong-link boost on a clean fixture despite the disabled `applyStrongLinkBoost` branch?
- Which reserve-level values are commonly missing in Raven/Spansh imports, and how often would the Pristine default change the predicted primary/secondary economy ordering?
- Can EDData API expose historical trade rows from its underlying data even though no documented history endpoint is present?

## Next queue — continue, do not treat this checkpoint as completion

1. Recover/materialize the original slot-analysis workbook if possible and extract the exact 99.9568% formula cell-by-cell; compare it programmatically with Raven's current function.
2. Build the discriminating threshold corpus: 5,500/6,000 km, bio-only, atmosphere variants, 700 K, 2.7 g, HMC, terraformable, plus both residuals.
3. Inspect Raven UI/system-model call paths to prove exactly when local `predictSurfaceSlots()` is used versus server-returned observed slots.
4. Trace the Frontier forum 642609 reverse-engineering thread through accessible mirrors/search snippets/quoted references and recover raw derivation evidence.
5. Build a post-Operations terraformable-Agriculture golden fixture and test Raven, guide prediction and live market side-by-side.
6. Quantify Raven's `unknown reserve -> pristine` exposure on imported systems and test how often it changes economy ranking.
7. Continue controlled top-two/rank-three commodity fixtures and EDGalaxyData archive feasibility; use EDData API/EDCAS as current-market locators.
8. Continue post-July-2026 orbital-slot corpus with patch/date/Architect/demolition provenance.
9. Run the planned read-only V3 sensitivity analysis replacing system-wide signal counts/fake slots with body-local predicates + observed/predicted physical capacity.
10. Extend CRE design recommendations with `source_lineage`, `implementation_version`, `effective_from/effective_to`, `intended_rule`, `observed_live_behavior`, `known_bug_state`, `assumption/default`, and falsification-test fields.