# R1 Normalized V3 Real-System Bridge — Review 1

Date: 2026-08-31
Status: pre-code stage definition
Branch: `chatgpt-ed-new-ops-requests`

## 1. Goal

Validate the R1 evidence/assessment architecture against many real Elite Dangerous systems using the retained normalized V3 generation, without creating new Ratings tables and without treating legacy/V4 scores as evidence.

This is a research/shadow bridge, not production Finder integration.

## 2. Discovery that changes the bridge

The retained canonical generation `v3_gen_phase4c_full_20260827_r5` is rich in normalized physical/provenance facts but does **not** retain planet class/subtype (for example High metal content world, Water world, Earth-like world, Ammonia world).

Its `body_type_id` vocabulary distinguishes only Star / Planet / Barycentre / Belt Cluster. The generation does retain, among other things:

- system id64/name and source/loaded body counts;
- body identity keys and names;
- distance from arrival;
- landability;
- tidal lock;
- radius, gravity and surface temperature;
- atmosphere classification;
- terraformability state;
- volcanism type;
- explicit biological/geological signal rows and completeness;
- rings and reserve type;
- source/run/freshness/lifecycle provenance.

Therefore R1 must not infer planet class from atmosphere, composition, gravity, mass, or any other proxy.

## 3. Temporary research identity overlay

For this stage only, use EDSM's public `api-system-v1/bodies` endpoint as a bounded external identity overlay because it accepts exact system names and returns explicit body `type` and `subType`.

The overlay may contribute only:

- exact requested system name;
- returned system name;
- system id64 where supplied;
- body name;
- body type;
- body subtype;
- distance-to-arrival as a matching/debug aid only;
- response SHA-256/provenance.

Do **not** import EDSM landability, terraformability, signals, atmosphere, volcanism, rings, reserve, gravity, radius, temperature, or other mechanics facts into the normalized-V3 projection.

EDSM is evidence for this research validation, not a declaration that production R1 should depend on EDSM for canonical identity.

## 4. Source responsibilities

### Normalized V3 generation

Authoritative source for this stage's stored physical/provenance facts.

### EDSM identity overlay

Explicit planet/star subtype only where a deterministic body match succeeds.

### Existing R1 mechanics layer

Consumes the composed facts and preserves Unknown/ambiguous/conflicting states. It does not invent missing identity.

## 5. Matching rule

First vertical slice:

1. resolve an exact requested system name through EDSM;
2. use returned id64 to select the same system from normalized V3;
3. match bodies by exact system + exact body name;
4. allow exact normalized spelling/case normalization only if explicitly defined in Review 2;
5. no fuzzy matching;
6. distance may be used to detect a contradiction but not to force a match;
7. unmatched normalized planet => subtype Unknown;
8. unmatched EDSM body => overlay-only diagnostic, never silently inserted into the normalized inventory.

## 6. Conflict policy

- Exact type/subtype match available: identity may be used with EDSM-overlay provenance.
- Duplicate body-name match: ambiguous; withhold subtype.
- Material body-count disagreement: surface completeness warning/conflict as appropriate.
- EDSM says Planet while normalized V3 says Star (or vice versa): conflicting; withhold identity-derived claims.
- Identity source unavailable/error: subtype Unknown, not guessed.
- Atmosphere containing ammonia never upgrades a body to Ammonia World.
- Water atmosphere never upgrades a body to Water World.
- Composition never upgrades a body to HMC/metal-rich/rocky class.

## 7. Real-system corpus

Batch 1 should cover at least:

- Plaa Eurk ZR-M c7-2
- Blu Thua SU-W c2-5
- Blu Thua JS-J d9-1
- HIP 101924
- HIP 294
- HR 1188
- Brambai DL-Y g32
- Eorgh Prou AA-A h24
- HIP 70564
- Praea Euq PS-U c2-3
- Wolf 359
- Lalande 21185
- UV Ceti
- Yin Sector CL-Y d127
- Kruger 60
- 36 Ophiuchi
- Lacaille 8760
- Toolfa
- Kokary
- Omicron-2 Eridani

Then widen in further bounded batches once the bridge behaves correctly.

## 8. Mandatory regressions

1. Brambai ammonia-life gas giant must **not** become true Ammonia World.
2. Eorgh true Ammonia World must retain canonical identity.
3. HR 1188 HMC identity and geological modifier must coexist.
4. Blu Thua JS-J d9-1 ELW/WW identities must not leak into Military merely because they are valuable bodies.
5. Remote bodies remain explicit in distance/logistics rather than gaining hidden volume credit.
6. Sparse systems stay sparse; no generic fallback score manufactures value.
7. Missing subtype remains Unknown.
8. EDSM overlay cannot overwrite normalized V3 physics/provenance.
9. No plan-pair resilience is attached to the system; resilience remains candidate-plan-relative.

## 9. Non-goals

- no new database tables;
- no migrations;
- no normalized-generation mutation;
- no legacy Ratings/archetype score reuse;
- no live Finder/API ordering changes;
- no production EDSM dependency decision;
- no universal system score;
- no inference of subtype from environmental fields.

## 10. Exit criteria

Review 2 must specify:

- exact overlay and normalized-row types;
- exact read-only V3 queries and lifecycle filters;
- exact deterministic body-matching rules;
- exact identity availability/provenance states;
- source conflict precedence;
- exact golden assertions;
- bounded batch/report format;
- implementation file allow-list;
- safety rules for large-generation reads.

Only after Review 2 is accepted may the isolated composite adapter be implemented.
