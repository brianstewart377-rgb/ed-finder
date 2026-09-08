# Ratings V4 Scoring Contract

**Status:** proposed V4 scoring authority; review and freeze before implementation
**Depends on:** `ratings-v4-mechanics-evidence.md`
**Scope:** seven raw economy-potential scores, specialisation quality, evidence completeness/confidence, explanation output, and system-level roll-up

## 1. Purpose

Ratings V4 separates mechanics evidence from ED-Finder judgement and from Finder ranking.

The scoring pipeline is:

```text
canonical V3 facts
  -> versioned mechanics features
  -> local economy opportunities
  -> system economy potential + specialisation quality
  -> archetype judgement
  -> Finder ranking
```

Raw V4 economy scores answer only:

> **How naturally and strongly can the known system support this economy under the documented colonisation mechanics?**

They do not answer whether the system is globally excellent, strategically well placed, compact, close to arrival, convenient for a particular commander, or part of a good multi-economy build. Those belong to later layers.

## 2. Absolute score semantics

Scores are absolute mechanics-based values, never percentiles.

| Score | Meaning |
|---:|---|
| 0 | No known mechanics-supported opportunity |
| 1-24 | Weak / marginal opportunity |
| 25-49 | Viable but limited |
| 50-69 | Strong |
| 70-84 | Excellent |
| 85-94 | Exceptional |
| 95-100 | Near-ideal mechanics support with depth |

A score has the same meaning after the next canonical data import. Galaxy percentile/rank is a separate Finder concern.

## 3. Unknown is not zero

Every economy result carries three distinct values:

- `potential_score` 0-100
- `evidence_completeness` 0-1
- `confidence` 0-1

Missing ring, biological, geological, reserve, terraformability, or other source-sensitive evidence is not converted to absence.

The potential score is computed only from known positive/negative evidence. Completeness says how much of the expected evidence set was actually known. Confidence expresses trust in the available evidence/provenance.

A score of 82 at 0.58 completeness is materially different from 82 at 0.99 completeness.

## 4. Mechanics evidence classes

V4 does not treat all body/economy associations as equal.

For economy `E` and candidate local body/location `B`, evidence is classified as:

1. **Native inheritance** — the body directly inherits economy `E`.
2. **Modifier inheritance** — a local feature such as rings, organics or geologicals adds economy `E`.
3. **Strong-link positive** — a documented body/system condition strengthens an existing strong link for `E`.
4. **Strong-link negative** — a documented condition weakens an existing strong link for `E`.
5. **Preferred specialisation fit** — guide/research evidence says this is a particularly clean/effective location for specialising `E`; this affects specialisation, not raw eligibility.

The mechanics ruleset records provenance and version for every rule.

## 5. Local opportunity score

Each economy is first evaluated per viable local body/location. This avoids turning one giant body-count formula into the mechanics model.

### 5.1 Native opportunity base

A candidate location starts with a native opportunity base according to the strongest known eligibility evidence:

| Evidence | Base local opportunity |
|---|---:|
| Native inheritance | 60 |
| Modifier inheritance only | 45 |
| Both native + modifier inheritance | 68 |
| No inheritance evidence | 0 |

These are ED-Finder V4 judgement coefficients, not claimed Frontier percentages. They are versioned and may be recalibrated without schema change.

### 5.2 Strong-link adjustment

Documented strong-link conditions modify the local opportunity after inheritance is established.

Default V4 rule:

- each distinct supported positive strong-link mechanic: `+10`
- each distinct supported negative strong-link mechanic: `-10`
- cap total positive strong-link adjustment at `+25`
- cap total negative strong-link adjustment at `-25`
- local opportunity remains within `0..100`

Same-economy duplicate evidence is deduplicated by mechanics rule identity; repeated observations of the same mechanic do not stack without an explicit rule permitting it.

### 5.3 System-level strong-link conditions

Conditions such as system reserve level or presence of exotic stars may apply to every eligible local opportunity for the relevant economy. They are applied once per candidate opportunity through the mechanics feature layer, not repeatedly for every source record.

### 5.4 No unsupported convenience modifiers

Local opportunity does **not** receive raw-economy points for:

- distance from arrival;
- generic body diversity;
- generic slot count;
- compactness;
- generic strategic value;
- complementary-economy strength;
- generic scientific interest;
- nearby population/geography.

## 6. Economy-specific mechanics inputs

The exact rules and provenance live in `ratings-v4-mechanics-evidence.md`. V4 consumes them as follows.

### Agriculture

Eligibility/evidence:
- ELW native Agriculture
- Water World native Agriculture
- organics/biologicals add Agriculture
- documented Agriculture strong-link positives/negatives
- terraformability is an amplifier only, not standalone Agriculture inheritance

### Refinery

Eligibility/evidence:
- Rocky native Refinery
- Rocky-Ice native Refinery
- reserve-level Refinery strong-link modifier

Ground/surface capacity does not inflate raw Refinery potential. It contributes to `specialisation_quality` / buildability because Refinery Hub placement is planetary.

### Industrial

Eligibility/evidence:
- Icy native Industrial
- Rocky-Ice native Industrial
- Gas Giant native Industrial
- geologicals add Industrial
- reserve-level Industrial strong-link modifier

Extraction or Refinery strength does not inflate raw Industrial potential.

### High Tech

Eligibility/evidence:
- ELW native High Tech
- Ammonia native High Tech
- Gas Giant native High Tech
- Black Hole / Neutron / White Dwarf native High Tech
- documented High-Tech strong-link modifiers

Generic scientific interest is archetype evidence, not raw High-Tech evidence.

### Military

Eligibility/evidence:
- main-sequence stars / Brown Dwarfs native Military
- ELW native Military

No generic strategic, Industrial, capacity or geography bonuses are included. With no established environmental strong-link modifiers, Military is intentionally conservative.

### Tourism

Eligibility/evidence:
- ELW native Tourism
- Water World native Tourism
- Ammonia native Tourism
- Black Hole / Neutron / White Dwarf native Tourism
- documented Tourism strong-link modifiers

Generic diversity and rings are not raw Tourism mechanics unless a later mechanics rule establishes them.

### Extraction

Eligibility/evidence:
- HMC native Extraction
- Metal Rich native Extraction
- rings / asteroid belts add Extraction
- geologicals add Extraction
- reserve-level Extraction strong-link modifier
- volcanism is a strong-link amplifier, not inheritance

## 7. System potential roll-up: quality first, depth second

For each economy, calculate local opportunity scores for all eligible candidate locations and sort descending:

```text
s1 >= s2 >= s3 >= s4 ...
```

The system potential is:

```text
potential = round(
    0.82*s1
  + 0.11*s2
  + 0.05*s3
  + 0.02*s4
)
```

Only the best four opportunities contribute.

Consequences:

- one perfect site scores 82: already excellent;
- two perfect sites score 93;
- three perfect sites score 98;
- four perfect sites score 100;
- the twentieth mediocre body cannot swamp one genuinely exceptional site;
- system depth matters, but quality dominates.

This diminishing-return curve is an ED-Finder judgement rule, not a Frontier mechanic, and is versioned with the scorer.

### 7.1 Why four opportunities

Four is sufficient to distinguish shallow vs deep systems while preventing very large systems from winning by catalogue size alone. It is a scorer coefficient and can be changed in a later V4.x ruleset without schema change if validation demonstrates a better curve.

## 8. Specialisation quality

`specialisation_quality` answers:

> **How cleanly can this system make the target economy one of the protected dominant/top-two economies without unwanted local inherited pressure?**

It is distinct from raw potential.

For each candidate location:

1. Start at `100`.
2. Count **distinct competing inheritable economies** created by the same local body/modifiers.
3. Apply a competition penalty:
   - 0 competitors: `0`
   - 1 competitor: `-8`
   - 2 competitors: `-20`
   - 3+ competitors: `-35`
4. Apply documented preferred-location evidence: `+5`, capped at 100.
5. Apply documented buildability constraints relevant specifically to specialising that economy (for example absence/unknown ground opportunity for a Refinery strategy) as a separate `specialisation_constraint` component, never as invented raw mechanics.

System `specialisation_quality` uses the best eligible candidate location, with a small depth bonus:

```text
specialisation = min(100, best_candidate_quality + min(10, 3 * additional_clean_candidates))
```

The August 2025 top-two-economy protection is respected: one competing economy is only a modest penalty, not a reason to crush the score.

### 8.1 Mandatory constraints and unresolved quality

The candidate-3 harness implements the separate constraint component using
three-state evidence. A confirmed satisfied requirement preserves the intrinsic
competition/preferred-fit quality; a confirmed failed mandatory requirement
blocks that candidate's specialisation; an unknown requirement leaves its quality
unresolved. Refinery's required local usable-ground opportunity defaults to
unknown, including for low-level scorer callers.

Evaluate the system specialisation roll-up over confirmed usable candidates for
the minimum, and over all candidates not confirmed blocked for the maximum.
Expose `specialisation_quality_min` and `specialisation_quality_max`. When these
agree, `specialisation_quality` is the exact value; otherwise it is null. Bounds
are conditional on currently known inheritance/modifier evidence and describe
unresolved constraints, not a probabilistic confidence interval. Raw potential,
its completeness/confidence and its best candidate remain independent.

Retain every candidate's constraints, source evidence and intrinsic/constrained
quality. `best_specialisation_candidate_id` separately identifies a confirmed
site supporting an exact positive specialisation result. See
`ratings-v4-specialisation-constraints.md` for the implementation and cohort
validation. No ground or generic capacity value adds raw economy points.

## 9. Potential and specialisation examples

### Example A: clean Rocky Refinery system

A clean Rocky body with Refinery inheritance and favourable reserves may have:

```text
local Refinery opportunity = 70-85
local specialisation = 100
```

A second good Rocky body increases system potential/depth without materially changing purity.

### Example B: geological HMC Extraction site

An HMC has native Extraction. Geologicals also add Extraction + Industrial; volcanism may further strengthen Extraction.

Result can correctly be:

```text
Extraction potential: very high
Extraction specialisation: lower than potential
```

because Industrial pressure exists without making Extraction itself weaker.

### Example C: ELW

ELW provides inherited Agriculture, High Tech, Military and Tourism. Additional strong-link evidence can raise Agriculture/High Tech/Tourism local opportunity. Military receives inheritance evidence but no invented environmental bonus.

Therefore V4 will not flatten the ELW into four equal economy scores.

## 10. Evidence completeness

Completeness is economy-specific. It measures whether the inputs that could materially change that economy score are known.

Each expected evidence family has a weight. Initial V4 weighting:

| Evidence family | Weight |
|---|---:|
| Body identity/type/classification coverage | 0.35 |
| Relevant local modifier coverage (rings/bio/geo/volcanism) | 0.25 |
| Relevant system modifier coverage (for example reserves) | 0.20 |
| Relevant terraformability/tidal-lock or other economy-specific facts | 0.10 |
| Provenance/freshness needed to interpret those facts | 0.10 |

Only families relevant to the economy are included, and their weights are renormalised to 1.0.

Known absence counts as complete evidence. Unknown does not.

## 11. Confidence

Confidence is not a freshness proxy alone. It is derived from source/provenance quality of the evidence actually used.

Initial V4 rule:

```text
confidence = weighted_mean(source_confidence_of_used_features)
```

Then apply a conservative completeness guard:

```text
reported_confidence = min(confidence, 0.5 + 0.5*evidence_completeness)
```

This prevents a small amount of high-quality evidence from yielding `0.99` confidence when much of the relevant system evidence is still unknown.

Confidence and completeness remain separate API fields.

## 12. Explanation contract

Every economy rating must be explainable from stored components.

Minimum output:

```text
economy
potential_score
specialisation_quality
evidence_completeness
confidence
best_candidate_location
contributors[]
constraints[]
mechanics_ruleset_version
scorer_version
```

Each contributor records at least:

```text
feature_type
body/system identity where applicable
mechanic_class: NATIVE_INHERITANCE | MODIFIER_INHERITANCE | STRONG_LINK_POSITIVE | STRONG_LINK_NEGATIVE
contribution
rule_id
provenance/evidence grade
```

UI rationale is generated from these components; it is not a separate opaque scoring input.

## 13. No universal headline score in the raw ratings layer

The raw Ratings V4 layer does not manufacture one universal `overall_score` from the seven economies.

Instead it exposes seven independent economy results.

A later archetype layer may produce:

- archetype-specific score(s);
- best colony potential / best archetype;
- complementary-economy synergy;
- buildability and practicality dimensions.

Finder then ranks according to an explicit query/profile.

This prevents an apparent universal score from hiding the question being answered.

## 14. V3.4 relationship

Ratings v3.4 remains historical/regression evidence only.

V4 deliberately rejects or relocates these v3.4 behaviours:

- global cross-economy attenuation -> removed;
- generic compactness/distance/strategic/safety mixing into economy suitability -> archetype/Finder only;
- one giant ratings row as the entire judgement model -> split into mechanics features, economy ratings, archetypes and ranking profiles;
- missing evidence treated optimistically or implicitly -> explicit completeness/confidence.

V3.4 should be run side-by-side during V4 validation to identify unexpected regressions, not to constrain V4 semantics.

## 15. Validation fixtures before freeze

Before implementation authority is granted, validate at least these deterministic systems:

1. pure Rocky Refinery specialist;
2. Rocky + geo/bio/ring contamination case;
3. pure Icy Industrial specialist;
4. HMC/Metal-Rich Extraction specialist with reserve variants;
5. Water-World Agriculture/Tourism system;
6. ELW mixed-economy system;
7. Ammonia High-Tech/Tourism system;
8. exotic-star High-Tech/Tourism system;
9. main-sequence/Brown-Dwarf Military system;
10. deep multi-body system proving diminishing returns;
11. sparse-data system proving unknown != zero;
12. same mechanics with high vs low/depleted reserves;
13. top-two mixed-economy case proving no v3.4-style global attenuation.

For each fixture, record expected ordering and score-band expectations before tuning exact coefficients against real systems.

## 16. Freeze criteria

Ratings V4 is ready to freeze when:

1. mechanics rules and provenance are accepted;
2. every required canonical V3 source field is mapped or explicitly unavailable;
3. local-opportunity coefficients and system roll-up curve pass the fixture suite;
4. specialisation behaviour matches the top-two economy model;
5. unknown/coverage behaviour is demonstrated;
6. representative real systems produce believable orderings against expert judgement;
7. v3.4 regression comparison has no unexplained major reversals;
8. the resulting database table design can represent all scoring components without schema changes for coefficient-only V4.x updates.
