# V3 Ratings / CRE Forensic Audit — Checkpoint 07

**Date:** 2026-08-31  
**Scope:** research only. No production writes, no V3 database writes, no scoring-code changes, no migrations.

This checkpoint continues directly from Checkpoint 06 and records two adversarial corrections plus a stronger end-to-end Dodec finding.

## 1. Adversarial correction: the Aug-29 CRE promotion bundle does not supersede colonisation M-0001..M-0013

Checkpoint 06 correctly identified that public CRE `main` is older than a recovered local research programme, but the first wording was too broad about potential supersession.

The recovered programme is explicitly titled **“CRE Codex/Exobiology Mechanic Promotion Session”**. Its lane evidence includes exobiology-temperature work such as Nebulus 20–21 K and Tectonicas temperature constraints. It produced mechanics M-0014..M-0042, 224 candidates and 37 adversarially reviewed promotion groups, but nothing retrieved so far shows that those later mechanics were a colonisation-economy rewrite of M-0001..M-0013.

Therefore the safe conclusion is:

- public GitHub `main` is **not the complete latest CRE research state overall**;
- the Aug-29 local package is a valid later knowledge programme and must be reconciled before any global CRE release decision;
- **but it must not be assumed to fix, replace, or supersede colonisation M-0001..M-0013** merely because its mechanic IDs are numerically later;
- the official-vs-community contradictions found in colonisation M-0008 and related files remain live findings until a later colonisation-specific artifact is actually found.

This is an important provenance lesson for Ratings vNext: mechanic ID sequence is not domain/version authority.

Source: user Library `RECOVERY_REPORT.md`, dated 2026-08-29. It verifies 23 lanes plus adversarial lane, 224 candidates, M-0014..M-0042, and a complete release package, while explicitly naming the mission Codex/Exobiology.

---

## 2. Dodec weighting: the external planner's final-stat error is now much more certain

Checkpoint 06 left one deliberate caveat: perhaps DaftMav v3.4.1's base rows were already Dodec-weighted, in which case the planner might have a complicated double-adjustment issue rather than a simple wrong multiplier.

The Library contains `daftmav_facility_bonus_reference.csv`, which resolves most of that caveat.

### 2.1 DaftMav stores primary and subsequent starport stat rows with the same raw stat values

The reference contains paired rows such as:

```text
Orbital - Starport - Dodecahedron (Primary)
Security -6, Tech -4, Wealth +8, SoL +9, Development +10

Orbital - Starport - Dodecahedron
Security -6, Tech -4, Wealth +8, SoL +9, Development +10
```

Likewise Coriolis, Asteroid Base, Ocellus, Orbis and the orbital outposts have matching system-stat columns between `(Primary)` and ordinary variants. What differs between the primary/non-primary rows is primarily build context/cost metadata, not a pre-applied first/subsequent Dodec stat multiplier.

**Implication:** the DaftMav facility-stat table is acting like a raw/base contribution table. The planner is right in principle to apply a separate first-vs-subsequent weighting stage. The problem is that its weighting constants are wrong.

### 2.2 The planner definitely applies its constants as multipliers to those raw sums

Current `src/domain/currentSystemScores.ts` states that this reweighting is an always-applicable Dodec Update rule and calculates:

```text
first contribution      = firstRaw * (1 + bonus)
subsequent contribution = subsequentRaw * (1 - reduction)
```

The current constants previously inspected are:

```text
FIRST_STATION_BONUS
Development +40%
Security    +40%
SoL         +40%
Tech        +20%
Wealth      +40%

SUBSEQUENT_FACILITY_REDUCTION
Development -10%
Security    -10%
SoL         -20%
Tech        -25%
Wealth      -25%
```

### 2.3 Official Dodec Update values are materially different

Frontier, 11-Nov-2025:

```text
Initial Starport
Development +20%
Security    +40%
SoL         +40%
Tech        +20%
Wealth      +40%

Subsequent facilities
Development -60%
Security    -20%
SoL         -52%
Tech        -66%
Wealth      -70%
```

The update says the change applies retrospectively to all existing colonised systems.

Primary-source mirror: https://steamdb.info/patchnotes/20709049/

### 2.4 Error magnitude implied by the current planner constants

If the official wording is applied in the same raw-contribution manner that the planner itself claims to implement, the effective multipliers are:

| Stat | Official first | Planner first | Official subsequent | Planner subsequent | Planner / official subsequent contribution |
|---|---:|---:|---:|---:|---:|
| Development | 1.20 | 1.40 | 0.40 | 0.90 | **2.25×** |
| Security | 1.40 | 1.40 | 0.80 | 0.90 | **1.125×** |
| Standard of Living | 1.40 | 1.40 | 0.48 | 0.80 | **1.667×** |
| Tech Level | 1.20 | 1.20 | 0.34 | 0.75 | **2.206×** |
| Wealth | 1.40 | 1.40 | 0.30 | 0.75 | **2.50×** |

So for a mature colony with many supporting facilities, this is not a rounding issue. Under the planner's current constants, later facilities can contribute roughly **2.25 times too much Development**, **2.2 times too much Tech**, and **2.5 times too much Wealth** relative to the literal official Dodec percentages, before rounding.

The initial-starport mismatch is narrower but still real: Development uses 1.40 instead of official 1.20; the other four first-station multipliers match the official announcement.

### 2.5 Worked minimal example

A raw Dodecahedron has Development +10 in the DaftMav reference.

- Official first-station weighting: `10 × 1.20 = 12`
- Current planner: `10 × 1.40 = 14`

A later facility with raw Development +10 would contribute:

- Official subsequent weighting: `10 × 0.40 = 4`
- Current planner: `10 × 0.90 = 9`

The sign behavior should still be checked on negative raw contributions against a live known colony, because “less weight” on a negative stat could interact with rounding/display semantics. But the positive-contribution mismatch is already unambiguous under the planner's own stated model.

### 2.6 Adversarial caveat that remains

We still need one or more current in-game systems with fully enumerated facilities and Architect system-stat readings to test whether Frontier's patch-note percentages map exactly to the simple multiplicative formula used by the planner, especially around:

- negative contributions;
- rounding order;
- whether the primary port is always the originally claimed station after upgrades/replacements;
- temporary BGS-state effects on displayed/current stats;
- any later undocumented rebalance.

But the planner can no longer be treated as a trustworthy independent implementation of the Dodec weighting merely because its comments say “official, verbatim.” Its source annotation and constants conflict directly with the official release note.

---

## 3. Why this matters to Ratings / CRE

Ratings vNext does not necessarily need to score Security/Tech/Wealth/SoL/Development numerically in its first release, but these values matter to any claim about:

- service-hub potential;
- outfitting/shipyard quality;
- commodity supply/demand volume;
- BGS resilience or state-shaping;
- colony-development quality;
- Architect dividend/system-score modeling if later coupled to these stats.

Therefore external-planner outputs should be ingested as **observations or hypotheses with lineage**, not as authoritative calculated truth.

The stronger design pattern is:

```text
raw facility observations / table
+ patch-versioned transformation rule
+ current colony fixture
= validated derived stat
```

not:

```text
community tool output
= fact
```

---

## 4. CRE colonisation contradiction remains stronger after the recovery review

The recovered Aug-29 M-0014..M-0042 package is a Codex/Exobiology programme, so it does not presently provide a reason to soften the M-0008 finding.

Current colonisation chain still appears to be:

1. CRE `main` M-0008 says body/economy modifiers do not stack and instructs planner logic not to double-count without direct evidence.
2. A prior ED-Finder scoring brainstorming ledger consumed that same CRE conclusion and explicitly said `Apply non-stacking once in the model`.
3. Frontier Update 3 explicitly says the colony economy overrides **may stack** and provides an HMC + organics worked example.

That is a real evidence-propagation failure: one community-derived claim crossed from CRE into product-design reasoning because official patch text had not been directly reconciled.

For Ratings vNext, the audit should treat this as a golden governance test: **a lower-authority claim must not block behavior when a higher-authority current official rule directly contradicts it.**

---

## 5. New evidence-quality decisions

| Finding | Evidence status | Confidence |
|---|---|---|
| Frontier Dodec percentages | `CURRENT_OFFICIAL` intended rule, effective 2025-11-11 and retrospective | Very high |
| DaftMav facility table contains raw-looking equal primary/non-primary stat rows | `COMMUNITY_DATASET` directly inspected | High for table semantics; still not official |
| External planner applies separate first/subsequent multipliers | `CODE_CONFIRMED` | Very high |
| External planner constants disagree with official patch notes | `CONTRADICTED_IMPLEMENTATION` | Very high |
| Exact in-game arithmetic/rounding equals simple multiplier model | `UNKNOWN_CURRENT_LIVE_DETAIL` | Medium hypothesis until controlled fixture |
| Aug-29 M-0014..M-0042 replaces colonisation M-0001..13 | **Rejected inference** | High confidence rejection based on mission domain title/context |

---

## 6. Updated queue — keep moving

### P0 next

1. **Find/construct a Dodec golden-colony fixture.** Search user Library, planner issues, screenshots/logs and public reports for a colony with exact facility inventory plus current Architect Security/Tech/Wealth/SoL/Development. Recalculate with official weights and compare.
2. **Trace Frontier Update 3 modifier stacking into current community implementations.** Compare `gaborauth/ed-colonisation-planner` `economyOverrides.ts`, Mega Guide/OASIS/Dubior, Raven/SrvSurvey where accessible, and CRE M-0008. Separate intended stacking from known live-bug exceptions such as terraformable/tidal modifiers.
3. **Continue orbital-slot observation corpus.** Current exact orbital formula remains unknown; collect post-1-Jul-2026 direct observations rather than filling the gap with a guessed deterministic formula.

### P1 after those

4. Quantify V3 rating sensitivity to corrected gas-giant capacity, preserved terraformable/tidal/bio/geo classifier fields, and stacking-capable body archetypes.
5. Build EDGalaxyData/EDDN before-after market timelines for real colonised ports to calibrate commodity-output and self-sufficiency claims.
6. Version current CP/prerequisite mechanics and add golden colonies/systems that deliberately falsify simplistic “high score = good colony” assumptions.

## Checkpoint decision

No scoring implementation change is authorised from this checkpoint. The strongest immediate action is to finish the golden-fixture validation and then use the results to define a patch-aware, claim-level Ratings evidence contract.