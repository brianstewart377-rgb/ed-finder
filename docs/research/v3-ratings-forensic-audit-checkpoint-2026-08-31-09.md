# V3 Ratings / CRE Forensic Audit — Checkpoint 09

**Date:** 2026-08-31  
**Scope:** research only. No production writes, no V3 database writes, no scoring-code changes, no migrations.

This checkpoint moves from source reconciliation back into Ratings v3.4 and identifies an exact, source-traceable mechanism behind the previously observed generic signal inflation / cross-economy bleed.

## 1. Ratings v3.4 counts **signal quantity** where the game mechanic is a **body characteristic**

Current `apps/importer/src/build_ratings.py` accumulates:

```python
bio_count = int(b.get('bio_signal_count') or 0)
geo_count = int(b.get('geo_signal_count') or 0)
counts['bio'] += bio_count
counts['geo'] += geo_count
```

Those are then consumed as if each individual signal were another unit of colonisation utility:

```text
Agriculture: +2.0 per bio signal, up to 15 signals
Industrial:  +2.0 per geo signal, up to 10 signals
High Tech:   +2.0 per geo signal +1.5 per bio signal, each capped at 10
Tourism:     +1.5 per geo signal +1.5 per bio signal, each capped at 10
Extraction:  +2.5 per geo signal, up to 10 signals
```

This does not match the shape of the official Trailblazers Update 3 mechanics.

Frontier defines these triggers as body/system predicates:

```text
On or orbiting a body with organics
On or orbiting a body with geologicals
On or orbiting a body with volcanism
On/orbiting a terraformable body
In a system with major/pristine resources
...
```

The official rule does not say that a body with 8 biological signal types gets eight independent Agriculture/HighTech/Tourism boosts, nor that 10 geological signals produce ten independent boosts.

The Mega Guide is even clearer about the intended interpretation: if a body has **any organics**, +1.0 Agriculture and +1.0 Terraforming is introduced if not already present. Its body-override examples likewise treat geologicals/rings as presence rules rather than signal-count multipliers.

## 2. Concrete distortion from one signal-rich body

Under v3.4, one body carrying 10 geological signals can contribute, through the generic `counts['geo']` accumulator alone:

- +20 raw Industrial points
- +20 raw High Tech points
- +15 raw Tourism points
- +25 raw Extraction points

before any body-type contribution, slot score, top-pair logic, attenuation, or overall aggregation.

That means **one geologically signal-rich body can inject 80 raw economy-score points across four economies** purely because the scanner reports ten signals rather than one.

Yet the official mechanics distinguish at least two very different facts:

1. **Has geologicals**
   - adds intrinsic Extraction + Industrial economy identities to a colony-type port on/orbiting that body;
   - boosts High Tech and Tourism strong links on/orbiting that body.

2. **Has volcanism**
   - boosts Extraction strong links on/orbiting that body.

Those are body-level booleans/conditions, not a count of geological signal sites/species.

## 3. v3.4 also conflates **geologicals** with **volcanism** for Extraction

`score_extraction()` says:

```text
- Geo signals (volcanism): Extraction strong link boosted
```

and implements:

```python
score += min(counts['geo'], 10) * 2.5
```

This merges two mechanics Frontier explicitly keeps separate:

- body **geologicals** -> intrinsic body override adds Extraction + Industrial;
- body **volcanism** -> Extraction strong-link boost.

The Mega Guide calls out this distinction as confusing but important and notes that geologicals and volcanism are different properties.

Therefore the v3.4 Extraction signal term is not merely an arbitrary heuristic weight. Its explanatory comment claims an official-mechanics rationale that is factually mis-mapped to the input field.

### Consequence

A body can have geological signals and no relevant volcanism condition for the strong-link rule, or vice versa depending on data semantics/current scan representation. Ratings v3.4 cannot distinguish these cases because it uses `geo_signal_count` as the Extraction-link proxy.

## 4. Similar scope mismatch exists for High Tech, Tourism and Agriculture

Official strong-link modifiers are **placement-local**:

- High Tech: boosted on/orbiting ammonia/ELW, or body with geologicals/organics.
- Tourism: boosted on/orbiting ammonia/ELW/WW or body with geologicals/organics, plus system BH/WD/NS.
- Agriculture: boosted on/orbiting ELW, terraformable, or body with organics; decreased on icy and relevant tidal-lock chains.

Ratings v3.4 collapses those into **system-wide totals**. A bio-rich moon at 250,000 Ls can add to the system Agriculture/HighTech/Tourism score even when it is not the same placement body as the candidate port/facility configuration that would need the modifier.

Distance weighting was added for some body-count fields in v3.1, but these `bio` / `geo` totals are not placement-aware and the shown scoring functions consume the unweighted totals directly.

This is a deeper flaw than simply tuning coefficients: the model is aggregating a **local topology mechanic** as a **global abundance statistic**.

## 5. Why this produces the observed v3.4 compression

The earlier forensic audit established that many economy scorers reach 100 with modest body counts and the overall formula then saturates best-pair/slot/safety dimensions.

The signal-count bug adds another compression route:

```text
one body with many geo/bio signals
-> several economy scores receive large simultaneous bonuses
-> top pair reaches/crosses saturation sooner
-> v3.4 attenuation only applies after raw scores are already inflated
-> many systems collapse into the same high-score bands
```

This specifically explains why visually ordinary systems with abundant generic HMC/icy/landable/signal data can appear elite despite lacking a coherent buildable colony topology.

## 6. Adversarial review

### Could signal count still be a useful heuristic?

Possibly, but only for a different claim. A larger number of biological/geological signals may correlate with interesting bodies or exploration value. It may even correlate with the chance that **more bodies** have useful attributes.

However v3.4 does not count **bio-bearing bodies** or **geo-bearing bodies** here. It counts the total number of signals. Thus:

```text
1 body with 10 bio signals == 10 bodies with 1 bio signal each
```

for the relevant score term, even though colonisation topology is radically different. Ten separate constructible bodies can supply ten placement opportunities; one body cannot.

So signal quantity could survive as an optional exploration/diversity feature, but it is not a faithful implementation of body-local economy/link mechanics.

### Could Frontier secretly scale boosts by signal count?

No primary evidence found. Frontier consistently uses presence language (“a body with geologicals/organics”) and gives no quantity multiplier. Mega Guide and current community implementations treat these triggers as boolean for economy inheritance/link rules.

**Falsifier:** controlled current observations showing that otherwise-identical colony ports on bodies with different numbers of bio/geo signals receive systematically different intrinsic economy/link strength proportional to signal count.

Until such evidence exists, Ratings should not claim signal count is an official colonisation multiplier.

## 7. Ratings vNext data primitive should be body-local predicates, not system totals

For each body, retain at least:

```text
has_bio
has_geo
has_volcanism
is_terraformable
is_tidal_locked
parent_tidal_chain_to_star
has_rings
body_type
landable
surface_slot_estimate / observed_surface_slots
observed_orbital_slots
arrival_distance
```

Then evaluate candidate placement topology/body archetypes from those body-local facts.

System aggregates can still be materialized for search, but they should be derived as interpretable quantities such as:

```text
bio_body_count
geo_body_count
terraformable_body_count
usable_bio_body_count_with_slots
usable_geo_body_count_with_slots
clean_rocky_candidate_count
HMC_geo_candidate_count
...
```

rather than reusing `bio_signal_total` / `geo_signal_total` as direct economic strength.

## 8. New golden tests for Ratings vNext

Add adversarial pairs where the old score should fail:

### Pair A — signal concentration vs topology

- System A: one landable HMC with 10 geo signals, few/no other useful bodies.
- System B: ten landable HMC/rocky bodies each with one geo signal and usable slots.

v3.4 treats geo quantity similarly; vNext should strongly distinguish build topology/capacity.

### Pair B — geologicals vs volcanism

- same body class/slots, one with geologicals but no relevant volcanism state;
- another with volcanism in the exact strong-link sense.

Extraction-link potential must not be inferred from the wrong field.

### Pair C — local vs remote signal-rich body

- same total bio/geo counts;
- useful signals on the intended port body vs only on remote/non-constructible bodies.

Placement-aware score should diverge.

### Pair D — body-level count vs signal count

- one body with 5 bio signals;
- five bodies with 1 bio signal each, otherwise matched as closely as possible.

If slots/topology permit, the latter should generally offer more independent build options even though total signal count is equal.

## 9. Updated queue

### P0 next

1. Audit all v3.4 scorer comments against the exact Frontier modifier table and classify each term as correct, heuristic, wrong-field, wrong-scope, or unsupported. The geo/volcanism mistake suggests more comment-vs-input errors may exist.
2. Search for a current controlled body-override fixture (HMC+ring+geo and HMC+bio preferred) to validate intrinsic identity-set and duplicate-strength semantics.
3. Continue Dodec golden-colony fixture search and quantify current planner output against official weights.

### P1

4. Quantify how many current high-band v3.4 systems derive material score from `bio_signal_total` / `geo_signal_total` rather than distinct usable bodies, using a bounded read-only V3 sample when safe/available.
5. Continue post-Jul orbital-slot corpus and gas-giant inflation sensitivity.
6. Build EDGalaxyData/EDDN before-after market timelines for commodity/output calibration.

## Checkpoint decision

This finding strengthens the prior conclusion that v3.4 is not safely patchable by coefficient tuning alone. Several terms encode the wrong **mathematical object**: a count where the mechanic is a predicate, a system aggregate where the mechanic is local, and geological signals where the mechanic requires volcanism. Ratings vNext should rebuild from body-local candidate topology rather than retune those totals.