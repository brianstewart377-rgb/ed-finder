# V3 Ratings / CRE Forensic Audit — Checkpoint 08

**Date:** 2026-08-31  
**Scope:** research only. No production writes, no V3 database writes, no scoring-code changes, no migrations.

This checkpoint adversarially corrects an over-broad conclusion from Checkpoint 06/07 about M-0008 modifier stacking. The underlying source conflict is real, but it is **semantic rather than a simple true/false contradiction**.

## 1. The critical distinction: economy-type stacking vs same-economy strength stacking

Frontier Update 3 says colony body overrides **may stack** and gives the example:

> HMC + organics => Extraction + Agriculture + Terraforming.

That establishes that **distinct economy identities from multiple applicable override rules combine**. It does **not** say that two rules which both yield the same economy produce 2.0 rather than 1.0 of intrinsic economy strength.

The current Mega Guide resolves the ambiguity explicitly.

### Mega Guide semantics

The guide first says a colony-type port's economy is replaced by the **combination** of:

1. the base inheritable economy/economies of the local body; and
2. applicable base economy modifiers.

It then states that local body modifiers “do NOT stack” and illustrates exactly what this means numerically:

- Icy body intrinsic Industrial + geologicals' Industrial still gives **Industrial 1.0 / 100%**, not 2.0 / 200%.
- HMC intrinsic Extraction + rings' Extraction + geologicals' Extraction still gives **Extraction 1.0 / 100%**, not 3.0 / 300%, nor 2.0 / 200% from the two modifiers.

At the same time, the guide's later case studies clearly treat **different** economy identities as cumulative. Examples include:

- Rocky + biologicals => Refinery + Agriculture + Terraforming.
- Rocky + geo + bio => Refinery + Agriculture + Terraforming + Industrial + Extraction.
- Rocky Ice + geo => Industrial + Refinery + Extraction.

Therefore the word `stack` is overloaded:

```text
A. categorical / set stacking:
   distinct economy identities from different rules combine
   e.g. HMC + bio => {Extraction, Agriculture, Terraforming}

B. duplicate-strength stacking:
   overlapping sources of the same intrinsic economy do not add 1.0 + 1.0 + ...
   e.g. HMC + ring + geo => Extraction remains 1.0 intrinsic, not 3.0
```

Frontier's official statement proves A. The Mega Guide's empirical model claims B does not occur.

## 2. Revised verdict on CRE M-0008

M-0008 currently says:

- “local body modifiers do not stack with base planet economies”
- “local body modifiers do not stack with each other”
- planner should not double-count rings, organics or geological features without direct evidence.

Read literally as **economy identity suppression**, this would contradict Frontier. Read in the source context from which it was copied, it is a shorthand for **duplicate numeric strength overlap**.

### Revised claim-level status

| M-0008 subclaim | Status | Evidence |
|---|---|---|
| body class contributes the listed inheritable economy identities | `CURRENT_OFFICIAL` | Frontier Update 3 |
| ring / organics / geological rules contribute listed additional identities | `CURRENT_OFFICIAL` | Frontier Update 3 |
| distinct applicable identities combine | `CURRENT_OFFICIAL` | Frontier explicitly says overrides may stack; HMC+organics example |
| duplicate sources of the same intrinsic economy do not add extra 1.0 strength | `CURRENT_COMMUNITY/EMPIRICAL`, strong but not official-explicit | Mega Guide 1.0-vs-2.0/3.0 examples; current executable planner follows same set semantics |
| exact numeric intrinsic strength 1.0 for every body override | `CURRENT_COMMUNITY/EMPIRICAL` | Mega Guide; requires direct current fixture validation for planner-safe exact percentages |
| numeric stacking of **strong-link boost/decrease modifiers** | **separate mechanic; do not infer from body override stacking** | current planner cites community EconomicEffects research; official Update 3 only says strong links are boosted/decreased, not the exact additive magnitude behavior |

### What was wrong in the earlier audit wording

Checkpoint 06 said M-0008's “non-stacking rule is directly contradicted by Frontier Update 3.” That is too broad.

Corrected version:

**Frontier contradicts any interpretation of M-0008 that prevents distinct body/modifier economy identities from combining. Frontier does not contradict the narrower Mega-Guide claim that overlapping sources of the same intrinsic economy do not add their numeric strength.**

The defect in CRE is primarily **semantic compression**: one sentence named “non-stacking” merges two very different concepts and therefore is unsafe for downstream code or ratings unless the claim is split.

## 3. Current external planner handles this distinction better than CRE prose

`gaborauth/ed-colonisation-planner/src/domain/economyOverrides.ts` currently:

- describes the body override table as `stacked on top`;
- independently evaluates all applicable body rules;
- collects resulting economy identities into a `Set`.

That behavior means:

- HMC + organics correctly yields Extraction + Agriculture + Terraforming;
- HMC + ring + geologicals does not create three separate Extraction identities;
- Icy + geologicals does not duplicate Industrial identity.

So on **intrinsic body-override identity semantics**, the current planner is a better executable representation of the combined Frontier + Mega Guide evidence than CRE M-0008's ambiguous prose.

However the same file later models additive strong-link boost/decrease magnitudes from community `EconomicEffects.ods` research. That is a different rule family and should remain independently versioned and validated.

## 4. Provenance chain explaining how ambiguity propagated

We can now trace the lineage clearly:

```text
Frontier Update 3
  -> official: distinct overrides may combine

Mega Guide
  -> reproduces official table
  -> adds empirical interpretation:
       duplicate SAME-economy intrinsic strengths overlap at 1.0, not 2.0/3.0
  -> uses shorthand “modifiers do NOT stack”

CRE M-0008
  -> copies the shorthand without preserving the 1.0-vs-2.0 examples
  -> says do not double-count modifiers

ED-Finder R1 brainstorming ledger
  -> consumes “non-stacking” as a single canonical rule
```

This is exactly the kind of evidence-lineage failure the Ratings audit is meant to catch. A correct source can become unsafe downstream when its **scope-defining examples are removed**.

## 5. Product / Ratings implication

Any Ratings vNext body-economy feature must represent intrinsic overrides as at least:

```text
body_override_economies: set[economy]
intrinsic_strength_by_economy: value + provenance
```

not as a simple list of additive bonuses.

For example:

```text
HMC + rings + geo + bio

identity set:
Extraction
Industrial
Agriculture
Terraforming

NOT:
Extraction x3
Industrial x1
Agriculture x1
Terraforming x1
```

unless a current controlled observation later demonstrates different strength semantics.

This matters to Ratings because a naive additive feature model would systematically overrate bodies with overlapping same-economy triggers (especially HMC/ring/geo Extraction and Icy/geo Industrial), while a naive non-stacking model that suppresses distinct identities would underrate mixed-economy bodies.

## 6. Adversarial evidence quality

### Strong evidence

- Frontier's current intended identity-stacking rule is explicit and includes a worked example.
- Latest Library Mega Guide version (uploaded 2026-06-29) explicitly gives 100%-not-200/300 duplicate-strength examples.
- Current external planner's code independently preserves the semantic distinction using a set of economy identities.

### Still not proven to official-grade

- Exact intrinsic base strength of 1.0 in every body/port case.
- Whether any later patch changed duplicate-strength overlap.
- Whether specialized ports and colony-type ports ever have undocumented body interactions.
- Exact numeric additive behavior when multiple strong-link environmental boost/decrease conditions hit the same economy.

### Falsifiers

The Mega Guide duplicate-strength model would be falsified by a current colony-type port, with no links or other contributors, where two overlapping body rules for the same economy produce a measured intrinsic economy strength greater than the single-rule intrinsic value.

The categorical stacking model would be falsified by a current controlled HMC+bio (or similarly multi-rule) colony-type port that fails to expose the distinct economy identities Frontier says should coexist, after ruling out a documented live bug.

## 7. Updated queue

### P0 next

1. **Find a controlled body-override golden fixture** with minimal/no links for HMC+ring+geo and/or HMC+bio, ideally current Architect/market evidence. Use it to test identity-set and duplicate-strength semantics independently.
2. **Continue Dodec golden-colony search** for exact facility inventory + current Architect five-stat readings; the planner constants remain a high-confidence source/implementation mismatch.
3. **Trace strong-link numeric modifier stacking** separately from intrinsic override stacking. Audit Mega Guide, EconomicEffects lineage, Raven/SrvSurvey and current planner code for exact +0.4/-0.4 semantics and seek live controls.

### P1

4. Quantify Ratings v3.4/V3 sensitivity to body identity-set modeling vs additive trigger counting.
5. Continue post-1-Jul orbital-slot corpus; do not invent an ordinary-body deterministic formula.
6. Use EDGalaxyData/EDDN before-after market timelines for commodity/output validation.

## Checkpoint decision

The correct governance rule is now sharper: **do not ingest words like `stack`, `boost`, `override`, or `link` into Ratings without preserving the exact mathematical scope they refer to.** The same word can refer to economy identity union, intrinsic strength addition, or link-strength modification, and collapsing those is enough to create materially wrong rankings.