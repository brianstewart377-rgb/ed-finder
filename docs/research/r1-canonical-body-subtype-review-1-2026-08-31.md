# R1 Canonical Body Subtype — Review 1

Date: 2026-08-31
Status: pre-code / pre-generation design review 1
Branch: `chatgpt-ed-new-ops-requests`

## Purpose

Define the upstream canonical correction required before the first galaxy-wide R1 capability generation can be built honestly.

The retained normalized generation `v3_gen_phase4c_full_20260827_r5` contains rich body physics/signals/rings/provenance but does not retain the explicit body subtype/class needed for identities such as High metal content world, Water world, Earth-like world, Ammonia world and specialist stellar identities.

R1 must not infer those identities from atmosphere, composition, mass, temperature, signal counts or any scoring/mechanics model.

## Key finding

The subtype is not unknowable. Existing explicit source paths already carry it:

- Frontier Journal `Scan` exposes `PlanetClass` for planets;
- the current Journal normaliser preserves `planet_class` explicitly;
- Spansh galaxy records expose `subType` / `subtype` explicitly;
- the existing Spansh importer currently stores that value in the legacy/public `bodies.subtype` field.

Therefore the normalized-V3 omission is a schema/build omission, not a reason to create a heuristic R1 identity classifier.

## Core decision

Body subtype belongs in canonical normalized V3, not in R1.

The next immutable canonical generation should add:

1. `v3_vocab.body_subtype` — stable explicit subtype vocabulary;
2. nullable `body_subtype_id` on that generation's `bodies` relation;
3. source/provenance-aware mapping from explicit upstream classification values only.

The retained `v3_gen_phase4c_full_20260827_r5` generation must not be altered in place.

## Source hierarchy / evidence policy

Allowed identity inputs are explicit classification fields only.

Initial accepted source classes:

1. Frontier Journal `Scan.PlanetClass` / explicit Frontier stellar identity where available;
2. Spansh dump `subType` / `subtype` where explicitly supplied;
3. other explicit source subtype fields only after their lineage is documented.

Research-only overlays such as EDSM may remain useful for bounded validation but must not silently become the production canonical dependency.

Forbidden inference examples:

- ammonia atmosphere -> Ammonia World;
- water atmosphere/composition -> Water World;
- high metal percentages -> HMC;
- gravity/radius/mass combination -> planet class;
- geological signals -> volcanism or body type;
- star spectral properties -> a body subtype unless the canonical source contract explicitly defines that mapping as identity rather than inference.

## Conflict policy

If two explicit source classifications for the same stable body identity disagree:

- do not pick one silently;
- preserve the competing source values/provenance;
- canonical `body_subtype_id` remains NULL/Unknown unless the source-precedence contract resolves the conflict legitimately;
- emit a reconciliation/conflict artifact;
- R1 capability generation treats that body subtype as Unknown until resolved.

A newer source record is not automatically more authoritative solely because it is newer.

## Vocabulary contract direction

Logical shape:

```text
v3_vocab.body_subtype
  body_subtype_id  SMALLINT PK
  body_type_id     SMALLINT NOT NULL FK -> v3_vocab.body_type
  public_code      TEXT NOT NULL UNIQUE
  display_name     TEXT NOT NULL
  source_aliases   JSONB or equivalent explicit mapping contract
  active           BOOLEAN NOT NULL DEFAULT TRUE
```

`public_code` is stable machine identity; display text may change.

The final Review 2 must decide whether aliases belong relationally or in version-controlled code/config rather than prematurely choosing JSON storage.

## Body relation direction

The next canonical generation's body relation gains:

```text
body_subtype_id SMALLINT NULL
```

with type/subtype consistency enforced so, for example, a planet subtype cannot be attached to a Star body type.

Generation-local `body_pk` identity semantics remain unchanged.

## R1 consequences

Once subtype exists canonically, the R1 capability builder can compute exact context-free counts such as:

- HMC count;
- metal-rich body count;
- rocky / rocky-ice / icy counts;
- Water World count;
- Earth-like World count;
- true Ammonia World count;
- gas giant count;
- neutron star / black hole / white dwarf counts where the final canonical subtype contract uses subtype for those identities.

Modifiers remain independent and composable:

- HMC + geological stays HMC AND geological;
- HMC + terraformable stays both;
- ringed + geological + biological all coexist;
- exact subtype identity never gets replaced by a modifier bucket.

## Unknown policy

`body_subtype_id IS NULL` means Unknown, not Other and not zero-value evidence.

At system-capability aggregation time:

- known subtype counts include only explicit known subtype rows;
- `body_subtype_unknown_count` records unresolved/absent subtype rows;
- a zero HMC count is a known negative only when body inventory/subtype completeness supports that interpretation;
- Finder must not present incomplete subtype inventory as a proven absence.

## Generation strategy

Do not patch ~598M retained body rows in place.

Preferred direction:

```text
explicit source classification
        ↓
normalised subtype vocabulary mapping
        ↓
new immutable canonical generation build
        ↓
validation / conflict receipts
        ↓
publication through existing v3_meta generation machinery
```

This keeps rollback and provenance aligned with normalized V3's immutable-generation model.

## Validation corpus

Review 2 must bind exact tests using real systems, including at minimum:

- HR 1188 — HMC + geological composability;
- Brambai DL-Y g32 — true Ammonia World positive control;
- Eorgh Prou AA-A h24 — ammonia-related false-positive control;
- HIP 70564;
- HIP 294;
- Plaa Eurk ZR-M c7-2;
- sparse negatives Wolf 359 / Lalande 21185 / UV Ceti;
- additional Water World and Earth-like systems from the existing golden/real-system corpus.

Required regression classes:

1. exact HMC identity survives geo/bio/TF/ring modifiers;
2. `Ammonia world` exact source value maps to true Ammonia subtype;
3. ammonia atmosphere on another subtype does not map to Ammonia World;
4. source missing subtype -> NULL/Unknown;
5. conflicting explicit subtypes -> unresolved, not guessed;
6. vocabulary alias mapping is deterministic/versioned;
7. repeated generation build gives byte/digest-stable subtype projection for identical source inputs.

## Non-goals

This stage does not authorise:

- mutation of retained `v3_gen_phase4c_full_20260827_r5`;
- first R1 capability generation;
- 198M-system capability backfill;
- Finder publication/cutover;
- legacy Ratings deletion;
- inferred planet classification;
- permanent dependence on EDSM;
- programme/Plan Fit scoring changes.

## Review-2 questions to resolve

1. exact normalized body columns currently available for star identity so we avoid redundant subtype storage;
2. exact vocabulary rows/public codes/aliases needed for all observed Spansh/Frontier values;
3. whether alias mapping is relational or version-controlled build config;
4. exact source-precedence/conflict rules between Frontier Journal and Spansh explicit subtype evidence;
5. how completeness is represented so absence is distinguishable from missing source classification;
6. exact new-generation build/test package and file allowlist;
7. bounded real-source distribution audit before any full rebuild;
8. acceptance thresholds for unknown/unmapped subtype rates.

## Review-1 conclusion

Proceed to a bounded metadata/source audit, then Review 2.

The expected result is an explicit canonical subtype field in the next immutable V3 generation. R1 consumes it; R1 does not own or infer body identity.