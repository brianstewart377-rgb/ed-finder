# Ratings V4 harness continuation — 2026-09-08

PR #646 remains stacked on architecture PR #645. This continues the accepted
architecture and advances the harness to `4.0-candidate-2`; it does not freeze V4.0.

This note records the candidate-2 pass. The subsequent candidate-3 constraint
implementation and current remaining gates are documented in
`ratings-v4-specialisation-constraints.md`.

## Coefficients and scope

The active candidate remains native 75, modifier-only 55, native + modifier 85,
distinct strong links +/-10 with separate +/-25 caps, and the best-four system
weights 0.82 / 0.11 / 0.05 / 0.02. The older 60/45/68 table in the initial scoring
contract is the historical candidate superseded for the harness by the coefficient
calibration note.

All seven raw economies remain independent. There is no universal raw score,
cross-economy attenuation, arrival-distance adjustment or generic capacity bonus.
This change is confined to the pure Python harness, its regression data and tests.

## Input and evidence corrections

- Canonical HMC, Rocky Ice and Earthlike aliases share the same mechanics rules.
  Qualified stellar subtypes and spectral classes (including numeric subclasses)
  classify ordinary stars, brown dwarfs and exotic stars. `is_main_star` is
  retained but cannot by itself establish a stellar class.
- Journal `*Resources` reserve enums normalize to the same rules as display names.
  Missing or unrecognised reserve values remain unknown. The existing system
  reserve input remains a calibration convenience, not a production source model.
- Exotic Tourism modifiers derive from all classified stellar bodies and are
  deduplicated by rule identity, including when an explicit fixture summary is
  also supplied. Derived system evidence retains classification confidence and
  provenance.
- Body facts accept per-feature confidence/provenance overrides. The existing
  body confidence is a fallback. System features have equivalent overrides.
  Low-confidence biological evidence affects the economies that consume it;
  it does not weaken unrelated Military inheritance.
- Evidence uses the scoring contract's family weights, renormalised over relevant
  families. Identity's 0.35 is split equally between body classification and body
  inventory coverage. Relevant local modifiers share 0.25, system modifiers 0.20,
  Agriculture terraformability/tidal lock 0.10, and provenance 0.10. A caller's
  explicit body completeness remains an upper bound.
- `body_inventory_complete` defaults to false. Callers must assert complete
  inventory before reporting full coverage. Known false local facts are complete;
  `None` remains unknown. The harness's frozen cohort explicitly declares its
  inventory complete; this is not a new verification of production ingestion.
- The adapter returns coverage records for every body/economy, including economies
  without inheritance. Such records affect evidence coverage but cannot acquire
  potential, specialisation, a best-candidate identity or a depth slot. Confirmed
  absence can therefore be distinguished from missing evidence.

Coverage includes candidates outside the best four. Confidence is the mean of
known feature confidence using the evidence weights, averaged across candidate
records, then guarded by `min(source_confidence, 0.5 + 0.5 * completeness)`.
Potential itself is not multiplied by completeness or confidence.

## Determinism and explanations

Exact duplicate opportunities collapse by `(economy, candidate_id)`. Conflicting
duplicates are rejected so callers must reconcile their source observations
before scoring. Unknown economy names and nonfinite/out-of-range confidence or
completeness fail explicitly. Candidate ties use identity as a stable secondary
key.

Every weighted candidate now has a structured contribution containing eligibility,
base score, distinct positive/negative rule IDs, capped adjustments, clamped local
score, system weight, source contributors and evidence features. These records
reconstruct raw potential. The text explanation lists the same rules and all
weighted candidates, plus unknown fields from the coverage records.

## Specialisation baseline corrections

A clean-depth bonus now requires zero distinct competing economies. A candidate
with one competitor remains compatible under top-two protection but is not pure.
Water Worlds now receive their documented preferred Tourism location bonus.

All 84 raw potential values in the 12-system cohort remain unchanged. There are
21 corrected specialisation values; the other 63 are unchanged. The old values
remain in `s_candidate_1`, while `s` records the candidate-2 baseline:

| System | Changed specialisations (old → new) |
|---|---|
| Praea Euq WV-W b2-2 | Agriculture 100 → 97; Tourism 100 → 97; HighTech 95 → 92 |
| Achenar | HighTech 100 → 92; Industrial 100 → 92 |
| Alioth | HighTech 95 → 92; Industrial 95 → 92 |
| Maia | HighTech 100 → 97; Agriculture 100 → 92 |
| Borann | Military 95 → 92 |
| HD 38179 | Industrial 100 → 92 |
| Col 285 Sector BW-U c3-5 | Agriculture 100 → 92 |
| Smojoo ZE-R d4-109 | Tourism 92 → 97; Extraction 100 → 92; Military 98 → 92 |
| Thaile HW-V e2-7 | HighTech 100 → 97; Tourism 100 → 97; Agriculture 100 → 97 |
| Deriv-Dar | Industrial 95 → 92; Agriculture 100 → 97; Tourism 95 → 97 |

The changes to 92 remove unsupported clean-depth bonuses; 97 retains preferred
fit with one competitor. No coefficient was tuned to the cohort.

## Validation

Validated with CPython 3.14.7: 114 tests pass across `test_ratings_v4.py`,
`test_ratings_v4_real_systems.py` and `test_ratings_v4_evidence.py`. This includes
all 18 original synthetic contract fixtures and the complete 12-system cohort.
Ruff and whitespace checks pass for the changed Python files. No database or
production execution is part of this validation.

## Remaining gates

1. Completed in candidate 3: the separate economy-specific specialisation
   constraint component, including known/unknown usable ground opportunity for
   Refinery. See `ratings-v4-specialisation-constraints.md` for nullable quality,
   bounds, source evidence and the updated cohort baseline.
2. Retain detailed body classification and body/ring reserve evidence in canonical
   ingestion with provenance. Do not promote the synthetic system reserve scalar
   into a production schema by assumption.
3. Persist and validate features/opportunities/ratings in a disposable derived
   generation; finish the reviewed real-system and v3.4 comparison evidence.
4. Freeze the scorer/mechanics manifests only after these gates. Production derived
   data publication and archetype/Finder integration follow that freeze.
