# V3 Ratings / CRE Forensic Audit — Checkpoint 10

**Date:** 2026-08-31  
**Scope:** research only. No production writes, no V3 database writes, no scoring-code changes, no migrations.

This checkpoint completes the next v3.4 comment-vs-input audit slice and finds an even more fundamental issue than the signal-count problem: the stored/displayed **slot-capacity dimension does not calculate construction slots at all.**

## 1. `compute_slot_score()` is body-count scoring mislabeled as slot capacity

Current `apps/importer/src/build_ratings.py` says:

```python
def compute_slot_score(counts):
    """Score the system's slot capacity (0-100)."""
```

but computes:

```python
landable = counts['landable']
orbital = (
    gas_giant + elw + ww + ammonia + rocky_clean + rocky_rings +
    rocky_bio + rocky_geo + rocky_ice + icy + hmc + metal_rich
)
```

It then maps **number of landable bodies** to a `surface_score` and **number of bodies** to an `orbital_score`:

```text
surface:
0 -> 0
1-2 -> 25
3-5 -> 50
6-10 -> 75
>10 -> 100

orbital/body count:
<=2 -> 20
3-5 -> 50
6-10 -> 75
>10 -> 100
```

and calls the result slot capacity.

No ground-slot formula, observed ground-slot count, orbital-slot observation, body slot class, gas-giant one-slot rule, ring/belt exception, or Architect slot state is used.

## 2. This is now demonstrably incompatible with known slot mechanics

### Surface side

Our validated empirical model predicts **surface slots per body** from:

- landability
- temperature
- gravity
- radius band
- atmosphere
- HMC class
- terraformability
- geo/volcanism-related feature term
- cap 7

and validated at **4,630 / 4,632 landable bodies = 99.9568%** in the workbook test set.

A landable body is therefore not equivalent to one surface slot, nor even to guaranteed nonzero colonisation surface capacity under every edge condition. `compute_slot_score()` discards almost all of the information needed to estimate surface construction capacity.

### Orbital side

Current evidence is even more decisive:

- Frontier fixed gas giants to **one construction slot** on 1-Jul-2026.
- ordinary bodies exhibit varying orbital capacity; no exact current universal formula has yet been recovered.
- star asteroid belts can represent dedicated Asteroid-Base-only constructible locations.
- planetary rings must not be naively counted as one additional orbital per ring.
- historical ring/belt bugs can leave legacy systems with anomalous capacity.

Yet v3.4 sets `orbital` equal to a body count. A gas giant, water world, HMC, icy body and rocky body each contribute exactly one unit to this so-called orbital capacity regardless of actual observed/predicted orbital slots.

## 3. `slots` can saturate without high construction capacity

A system with >10 counted bodies gets `orbital_score = 100` even if those bodies have poor or unknown actual orbital capacity.

A system with >10 landable bodies gets `surface_score = 100` even if the bodies individually have low surface-slot counts or fail important eligibility thresholds.

With both conditions, the function returns:

```text
0.5*100 + 0.35*100 + 15 mix bonus = 100
```

Thus the `slots` dimension can be **fully saturated at 100 from body abundance alone**.

This offers another direct explanation for the high-band compression already seen in production: the overall scorer often receives a perfect `slots` input that is not measuring the quantity its label claims.

## 4. Why this matters more than a coefficient error

This cannot be repaired by changing thresholds such as `>10` to `>15`.

The mathematical object is wrong:

```text
current:
body_count -> "slot score"

needed:
body-local observed/predicted constructible capacity
+ location constraints
+ slot type
+ current/legacy state
-> feasible build topology / capacity
```

A Ratings vNext system should distinguish at minimum:

```text
observed_ground_slots
predicted_ground_slots + confidence/model_version
observed_orbital_slots
orbital_slots_unknown
special_location_type = ordinary | star_belt | planetary_ring | legacy_anomaly
allowed_facility_classes
post_patch_constructible_capacity
legacy_existing_capacity
```

## 5. Adversarial review

### Could body count be a useful proxy?

Yes. More bodies generally create more potential locations, so body count can be a low-cost **exploration prior**.

But it is not `slot capacity`, and current v3.4 does not label it as a proxy or assign uncertainty. It stores the result in the rating `slots` field, describes it as slot capacity, and then feeds it to the overall rating as if physical build capacity had been measured.

A proxy could survive in vNext under an explicit name such as `location_abundance_prior`, but it must not compete with observed/predicted physical slot counts.

### Could surface landable count correlate strongly enough?

Correlation is not enough for high-end ranking because colonists care about the tails. The 99.9568%-validated surface formula exists precisely because radius/atmosphere/HMC/terraformability/etc create large differences among landable bodies. Ranking the best systems is where those differences matter most.

### Falsifier

The finding itself is code-level and not probabilistic: current `compute_slot_score()` does not read slots. What can be falsified is the downstream-impact hypothesis. A read-only rerank sample could show that replacing the body-count proxy with real/predicted slot capacity barely changes rank. That is testable and should be measured before assigning final impact severity.

## 6. Additional scorer-comment audit findings

The same code slice contains several terms that are strategic heuristics rather than official mechanics, despite the module header presenting v3.4 as based on actual colonisation utility:

- Agriculture gets +8 for a scoopable main star because it supposedly supports population growth/trade routes. No Frontier colonisation rule found ties scoopability to Agriculture economy strength or population growth.
- Military gets points for generic landable-body count, gas giants as “useful for orbital Military facilities”, rocky bodies, and exotic-star “prestige”. These are placement/strategic heuristics, not body-to-Military economy rules. Gas-giant utility is additionally weakened by the current one-slot rule.
- `compute_strategic_score()` gives +15 to scoopable main stars and signal-count bonuses as generic strategic value. Those may be player convenience/exploration preferences but are not the same thing as colonisation mechanics.
- `compute_safety_score()` invents numeric hazard penalties for white dwarfs/neutrons/black holes. These can be defensible UX heuristics, but they need to be declared preference weights, not evidence-derived colony mechanics.

The design error is not that heuristics exist. It is that **official mechanic, observed feasibility, player convenience, and arbitrary preference weight are mixed in one scalar without provenance.**

## 7. Ratings vNext should separate four dimensions before recombining

A safer architecture is:

1. **Physical feasibility**
   - actual/predicted slots, buildability, surface/orbital restrictions.
2. **Mechanic-derived economic potential**
   - body override identities, strong/weak link opportunities, environmental modifiers.
3. **Strategic/player convenience**
   - arrival distance, scoopable star, hazards, route convenience.
4. **Preference/archetype fit**
   - desired economy mix, self-sufficiency goal, specialist vs mixed-market preference.

Only after those are independently visible and provenance-tagged should an overall ranking combine them.

## 8. Golden tests added to queue

### Slot-proxy adversarial pair

- System A: many landable bodies but low predicted ground slots per body / poor orbital evidence.
- System B: fewer bodies but high validated ground-slot totals and observed orbitals.

v3.4 can prefer A by body count; vNext should prefer B for build capacity.

### Gas-giant abundance pair

- many gas giants under current one-slot rule;
- matched system with fewer bodies but known multi-slot ordinary locations.

Test how much v3.4's body-count slot score and economy scores inflate the gas-giant-heavy system.

## 9. Updated queue

### P0 next

1. Finish the remaining v3.4 scorer-to-source classification into `official mechanic`, `valid proxy`, `wrong field`, `wrong scope`, `unsupported preference`, and `stale rule`.
2. Quantify rank sensitivity of the two now-exact structural defects: signal totals and body-count `slots`.
3. Continue controlled intrinsic override and Dodec golden-colony fixture search.

### P1

4. Build post-Jul orbital observation corpus.
5. EDGalaxyData/EDDN market timeline calibration.
6. Convert the growing forensic findings into a proposed Ratings vNext evidence contract and golden-corpus schema — still docs/research only, no implementation.

## Checkpoint decision

The audit has now found three distinct wrong-object failures in v3.4: **signal count instead of body predicate, system aggregate instead of placement-local condition, and body count instead of construction-slot capacity.** This substantially strengthens the case for replacing the scoring primitive model rather than tuning v3.4 weights.