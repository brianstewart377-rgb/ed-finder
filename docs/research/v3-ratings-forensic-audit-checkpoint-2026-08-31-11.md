# ED-Finder V3 Ratings / CRE Forensic Audit — Checkpoint 11

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`
Scope: research/documentation only. No production changes, V3 database writes, scoring-code changes, or migrations.

## Executive delta

This pass found and corrected a material error in checkpoint 10, then continued into Ratings v3.4 semantic classification, CRE provenance/versioning gaps, shared-source lineage, and the two residual surface-slot prediction mismatches.

The most important correction is chronology: the severe Dodec system-development weighting published on 2025-11-11 was superseded the following day. The current `ed-colonisation-planner` values are consistent with the 2025-11-12 Frontier balancing update, not an unexplained community softening. Therefore the checkpoint-10 claim that the current planner overstates later positive facility contributions by roughly 2.2–2.5x is RETRACTED.

## 1. Dodec/system-development chronology — correction to checkpoint 10

### 2025-11-11 Dodec Update

Frontier's Dodec patch introduced:

Initial Starport weighting:
- Development +20%
- Security +40%
- Standard of Living +40%
- Technology +20%
- Wealth +40%

Subsequent-facility weighting:
- Development -60%
- Security -20%
- Standard of Living -52%
- Technology -66%
- Wealth -70%

The patch said the change applied retrospectively.

### 2025-11-12 balancing response; applied in following maintenance

Frontier then announced a corrective balancing update after observing a larger-than-intended effect, especially the drop in available market commodities from Development. The replacement values were:

Initial Starport weighting:
- Development +40% (was +20%)
- Security +40%
- Standard of Living +40%
- Technology +20%
- Wealth +40%

Subsequent-facility weighting:
- Development -10% (was -60%)
- Security -10% (was -20%)
- Standard of Living -20% (was -52%)
- Technology -25% (was -66%)
- Wealth -25% (was -70%)

Evidence found in the Frontier forum update mirrored verbatim in the contemporaneous Reddit thread `Update on balancing changes to system development` and independently echoed by Inara posts on 2025-11-13. The original Frontier forum thread is `elite-dangerous-update-on-balancing-changes-to-system-development.643111`.

### Correction

Checkpoint 10 stopped at the 2025-11-11 values and therefore incorrectly treated the gentler current planner values as a mismatch. That conclusion is withdrawn.

The correct CRE representation is a temporal chain, not one timeless rule:

- Dodec weighting v1: effective 2025-11-11 until the corrective maintenance.
- Dodec weighting v2: announced 2025-11-12 and intended to replace v1 in the next scheduled maintenance.
- any later changes: still require a supersession search before v2 is labelled current forever.

### Adversarial challenge / falsifier

A later Frontier patch, controlled current-system measurement, or authoritative live-data fixture that changes these percentages would supersede v2. The one-day lifetime of v1 is itself evidence that CRE must not infer current truth from the newest source it happened to ingest.

## 2. Current external planner provenance and freshness

Repository reviewed: `gaborauth/ed-colonisation-planner`.

`src/data/buildings.ts` states that the building table was refreshed 2026-07-23 from DaftMav Colonization Construction v3 spreadsheet v3.4.1 and is intended to cover Dodec plus Trailblazers Update 3. Its Dodec weighting matches the 2025-11-12 corrective values above.

The planner also has a separate `system_score` treatment, with comments saying it was verified 2026-08-10 across four systems and appears flat/unweighted compared with the five weighted development variables. That is useful observational evidence but is not yet enough to call the rule universal.

The planner's `CLAUDE.md` exposes important lineage:
- Raven imports trust Raven-provided slot counts and built-facility lists.
- Raven body physical attributes are deliberately ignored in favour of other body data.
- Raven build-type mapping was sourced from SrvSurvey `colonization-costs2.json`.
- only a small mapping subset was cross-checked against a real Raven export; the remainder is best-effort.
- Spansh supplies body data.

Conclusion: the planner is useful and fairly current, but much of its mechanics/data vocabulary is derivative. It cannot be counted as an independent vote against DaftMav/SrvSurvey/Raven when all paths share the same upstream evidence.

## 3. Source-lineage rule for Ratings/CRE evidence

Do not count apparent corroboration by tool count. Evidence must be grouped by lineage.

Likely shared/partly shared lineage cluster:
- DaftMav spreadsheet
- Mega Guide material that cites/adopts DaftMav measurements
- SrvSurvey
- Raven Colonial
- `ed-colonisation-planner`

Potentially more independent strands:
- official Frontier patch/update statements
- controlled current in-game experiments
- Journal/CAPI observations
- market snapshots over time
- independently implemented tools only where their source chain is demonstrably separate

BGS-Tally and ED Colonisation Assistant remain promising observational acquisition tools, but their observations are evidence records, not mechanics authority.

## 4. CRE coverage audit

Repository reviewed: `brianstewart377-rgb/elite-dangerous-research-engine`.

The current source coverage register's processed first-class set is deliberately narrow and reference-source oriented: Mega Guide, illustrated strong/weak reference, DaftMav extracts, and a dependency flowchart.

Important current mechanics/provenance sources are not yet represented as first-class, versioned source/evidence records, including:
- Frontier Trailblazers Update 3 strong/weak-link and environmental semantics
- Frontier 2025-11-11 Dodec weighting
- Frontier 2025-11-12 corrective balancing update
- Frontier July 2026 gas-giant one-slot and Architect slot-display fixes
- current SrvSurvey/Raven fixtures
- `ed-colonisation-planner` implementation/observation notes
- BGS-Tally / ED Colonisation Assistant event traces where useful
- EDGalaxyData historical EDDN observations

This is a meaningful risk: a knowledge engine can be internally well-provenanced yet still reach stale conclusions if the source set omits superseding evidence.

## 5. CRE schema gap: validity intervals and intended-vs-live state

The mechanic schema already has useful fields such as status, last verified version/date, patch sensitivity, evidence and contradictions. The claim schema has patch context. The knowledge-versioning document handles releases and drift.

What is still missing for these mechanics is an explicit machine-readable temporal/semantic layer. Recommended research-model fields:

- `effective_from`
- `effective_to`
- `supersedes`
- `superseded_by`
- `official_intent`
- `observed_live_state`
- `known_bug_state`
- `fixed_observed_at` / fix evidence

The Nov-11 -> Nov-12 Dodec reversal is a direct validity-interval example. The terraformable-Agriculture issue is the intended-vs-live example.

## 6. Terraformable Agriculture: keep intent and observed implementation separate

Frontier Trailblazers Update 3 describes terraformability as an Agriculture strong-link boost.

A controlled player report dated 2025-07-31 measured two stations and found the +0.4 terraformable Agriculture boost absent; the reported actual values matched the calculation without that boost. The report linked Frontier Issue Tracker 77445. Mega Guide v2.3 likewise marked the effect as presently bugged/not working.

This pass did not locate authoritative evidence that the bug has since been fixed. Therefore the current state must NOT be recorded as `still broken in 2026`; that would exceed the evidence.

Correct CRE semantics:
- official intended mechanic: terraformable boosts Agriculture strong link
- observed live state in July/Oct 2025 evidence: not functioning
- current fix status: unresolved pending later patch note or controlled current fixture

Falsifier: a later official fix note or controlled current-market test demonstrating the expected boost.

## 7. Ratings v3.4 semantic classification

Code reviewed: `apps/importer/src/build_ratings.py`.

### Official-mechanic foundation, but often implemented at wrong scope/shape

- body/environment economy identities
- strong/weak-link concept
- environmental modifiers

These are legitimate mechanic families, but the current rating often aggregates them system-wide instead of preserving body placement and local-link topology.

### Wrong field

Extraction uses geological-signal totals under a rationale/variable concept of volcanism. Frontier distinguishes geologicals from volcanism: geological presence can affect body economy identity, while volcanism is a separate environmental condition/modifier. Signal count is also not equivalent to boolean body presence.

### Wrong scope

`bio_signals` and `geo_signals` are summed over the whole system and then converted to points across several economy scorers. Official mechanics are body-/placement-local. One body with many signals can therefore inject repeated system-wide score even though the mechanic is not `N signals = N independent boosts`.

### Mislabelled physical feasibility

`compute_slot_score()` does not calculate construction slots. Its surface term is essentially landable-body abundance; orbital capacity is estimated by counted body classes. It does not use observed ground slots, the validated surface-slot predictor, observed orbital slots, gas-giant one-slot limits, ring/belt constraints, or Architect state.

`slots` can therefore reach 100 without establishing real build capacity.

### Surfaced but not part of overall score

`slot_score`, `strategic_score`, and `safety_score` are computed/surfaced, but the overall score formula does not use them directly. This creates semantic/UI ambiguity when users reasonably infer those components contribute to the number.

### Unsupported/subjective heuristics

These may still be useful product choices, but they are not Frontier mechanics and must be labelled/tuned/validated as preference functions:
- cross-economy attenuation (top 2 full, 3rd x0.85, 4th+ x0.70)
- fixed complementary-economy pair list and pair weights
- overall 60% best pair + 35% top-three average + strategic bonus blend
- rarity/standout gate that caps otherwise strong systems
- arbitrary compactness/safety/star bonuses and thresholds

### Confidence is freshness, not model confidence

`compute_confidence()` principally measures freshness/report-count behaviour. Missing update time receives a relatively high default and small report-count bonuses can lift it further. It does not express model correctness, source version, slot-observation reliability, body-field completeness, or independent provenance.

This explains why stale/NULL-rating-version high-band rows can display High confidence. The UI/data name should be treated as semantically hazardous until separated into dimensions such as freshness, completeness, provenance and model/applicability confidence.

### Metadata drift

The file/docstring still references an earlier ratings version while the constant is v3.4. Small, but further evidence that version provenance should be data-driven/test-enforced rather than prose-only.

### Overall conclusion

Ratings v3.4 is best described as a mechanic-inspired system desirability heuristic. It is not a physical colonisation feasibility model and not an economic simulator. Ratings vNext should preserve that distinction explicitly.

## 8. Surface-slot residuals: do not overfit two exceptional rows

The validated workbook predictor remains 4,630 / 4,632 correct on landable bodies = 99.9568%.

Only two workbook mismatches remain:

1. Dryio Flyuae OZ-O d6-1381, body 1
   - actual 7; workbook/latest predictor 6
   - HMC, landable, radius ~6154 km, gravity ~1.11 g, temperature ~627 K
   - airless, non-terraformable, Major Rocky Magma, geo present, bio absent

2. DM99 4.3, body 1
   - actual 6; workbook/latest predictor 5
   - HMC, radius ~5236 km, gravity ~0.90 g, temperature ~690 K
   - airless, non-terraformable, Metallic Magma, geo present, bio absent, tidally locked

Both are exactly +1 actual versus prediction and both are relatively hot, airless, volcanic/geological HMCs.

Adversarial caution: Frontier later acknowledged Architect available-slot display bugs, particularly around demolition/state changes. The two residuals should therefore be re-observed under a current client/state before adding a bespoke +1 rule. With only two residuals in 4,632, overfitting is a larger immediate risk than underfitting.

## 9. Latest Library Mega Guide freshness

The latest Library copy reviewed is Mega Guide v2.3.0, dated 2025-10-31 and targeting game version 4.2.1.2. It predates both the November 2025 Dodec weighting sequence and the July 2026 gas-giant/Architect slot fixes.

It remains valuable for experimental mechanics and worked examples, but CRE must attach version/effective-date applicability rather than treating the guide as current for all colonisation rules.

## 10. Ratings high-band context retained

The prior exact live audit remains useful context:
- score 96: 168 total; 122 v3.4 and 46 NULL version
- score 97: 57
- score 98: 2, both legacy/NULL-version in the earlier audit
- score 99/100: none
- 95th percentile discrete boundary around 75; score 96 is therefore vastly beyond the literal top-5% edge
- sampled current v3.4 score-96 systems commonly saturated top pair plus several 100-valued components

The new semantic audit strengthens the explanation for compression: several inputs are capped heuristic proxies, and some 100-valued displayed components do not actually feed the final overall number.

## 11. Research hypotheses to test read-only against V3 data

No production write is required for these tests.

H1. Replacing total `geo_signals`/`bio_signals` scoring with body-local boolean/predicate features will materially reorder refinery/industrial/high-tech/extraction high-band systems, especially systems with a few bodies carrying many signals.

H2. Replacing fake `slots` with observed-or-predicted construction capacity will expose a distinct class of body-abundant but build-poor systems currently displayed as 100-slot candidates.

H3. Separating freshness confidence from completeness/version/provenance confidence will sharply reduce the apparent certainty of NULL-version and sparse-data high scorers without changing their raw preference score.

H4. Version-aware mechanic application will change outcomes for systems/facilities observed across the Nov-2025 Dodec transition and Jul-2026 gas-giant/Architect transition.

H5. A body-local graph model of strong/weak links will discriminate between superficially similar systems that aggregate-count scoring currently ties.

## 12. Evidence-quality / adversarial review

High confidence:
- Nov-11 severe Dodec values were superseded by the announced Nov-12 correction.
- current external planner matches the Nov-12 values.
- Ratings v3.4 fake `slots`, system-wide signal aggregation, unused displayed dimensions, and freshness-only confidence are direct code facts.
- CRE lacks first-class ingestion of several important later official/community evidence streams.

Medium-high:
- external planner/DaftMav/SrvSurvey/Raven constitute substantially shared evidence lineage; exact degree varies per mechanic and should be recorded per claim rather than blanket-labelled.

Medium:
- `system_score` flat/unweighted behaviour, based on four planner-verified systems; expand fixture count.

Unresolved:
- whether terraformable Agriculture was fixed after the 2025 reports.
- exact SrvSurvey/Raven current slot algorithm and whether the 99.9568% workbook formula shares code/data ancestry with it.
- whether the two slot residuals are true mechanics exceptions or bad/historical Architect observations.
- precise post-July-2026 orbital-slot rules for every body/ring/belt class.

## 13. Newly useful source/discovery set

- Frontier/official Dodec patch chronology, including the 2025-11-12 corrective forum update
- contemporaneous Reddit mirror of that Frontier update
- Inara 2025-11-13 quotation of replacement subsequent-facility weights
- `gaborauth/ed-colonisation-planner` current implementation and provenance comments
- `njthomson/SrvSurvey` repo as the upstream Raven mapping/colonisation-data target for the next pass
- CRE's own source coverage/versioning/schema documents
- existing workbook mismatch corpus for regression rather than formula overfitting

## 14. Next persistent queue

Continue, do not treat this checkpoint as completion:

1. Trace the exact SrvSurvey/Raven colonisation slot implementation and data lineage; compare against the workbook formula rather than assuming independence.
2. Search for a post-2025 fix or current controlled fixture for terraformable Agriculture.
3. Find or construct a controlled Journal/Docked/market fixture that isolates same-body strong links, cross-body weak links, distinct-economy stacking, and same-economy overlap.
4. Design a read-only v3.4 sensitivity experiment: signal totals -> body predicates; fake slots -> observed/predicted capacity; retain old scores side-by-side only for analysis.
5. Build a golden corpus partitioned by patch epoch, including pre/post Dodec and pre/post July-2026 gas-giant/Architect observations.
6. Continue EDGalaxyData historical-market investigation for commodity/system-development validation.
7. Build a post-July-2026 orbital-slot corpus with observation date, client version, demolition/build state and evidence source.
8. Expand CRE first-class source records and temporal semantics as research recommendations only; do not alter production mechanics until evidence/fixtures are sufficient.
