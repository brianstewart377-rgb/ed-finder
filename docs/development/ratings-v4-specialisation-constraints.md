# Ratings V4 specialisation constraints — candidate 3

This continues PR #646 on architecture PR #645. The scorer version is now
`4.0-candidate-3`; all raw coefficients and the mechanics version are unchanged.
The separate specialisation constraint component required by scoring contract
section 8 is implemented in the pure Python harness.

## Refinery requirement

Refinery specialisation requires a usable local ground opportunity because the
Refinery Hub is planetary. The harness accepts an explicit, three-state
`BodyFact.usable_ground_opportunity` fact. It does not infer this fact from a Rocky
classification, an unrelated body's surface, generic slot totals, current
population or occupied slots.

The adapter supplies a `SpecialisationConstraint` with rule ID
`refinery-usable-ground-opportunity`. It records the requirement's state, feature
name, source confidence and provenance. The low-level opportunity scorer adds
this requirement as unknown if a caller omits it; using the lower-level API does
not bypass the requirement.

| Requirement evidence | Local specialisation quality | Bounds for a clean candidate |
|---|---|---|
| Confirmed usable ground | Existing competition/preferred-fit quality | 100..100 |
| Confirmed no usable ground | 0 for this specialisation strategy | 0..0 |
| Unknown | `null` | 0..100 |

These are feasibility states, not invented numeric penalties. Unknown is neither
successful placement nor confirmed absence. Raw potential and its local scores,
contributors, evidence completeness, confidence and best-candidate identity are
unchanged by the constraint. Constraint confidence/provenance are retained
separately in the specialisation trace.

## System judgement

Each inherited candidate exposes a `CandidateSpecialisation` containing:

- candidate identity;
- intrinsic competition/preferred-fit quality;
- constrained quality, nullable when unresolved;
- minimum and maximum constrained quality;
- competing economies and preferred-fit evidence;
- deduplicated constraints and their source evidence.

All eligible candidates participate, including candidates outside the four raw
score contributors. The system evaluates the existing specialisation roll-up
twice: once over confirmed usable candidates, and once over all candidates that
are not confirmed blocked. Only a usable candidate in the relevant evaluation
can supply clean depth. A known failed requirement blocks that candidate even
when another requirement remains unknown.

The resulting `specialisation_quality_min` and `specialisation_quality_max` bound
the result over those constraint states, conditional on the currently known
inheritance/modifier evidence. They are not probability or confidence intervals.

When the bounds agree, `specialisation_quality` is that value. Otherwise it is
`null`. This preserves a proven 100 when another site has unknown ground, but
reports 92..100 when the best confirmed site has quality 92 and an unresolved
site could have quality 100. A lower-quality unresolved site need not make an
already-supported higher result unresolved.

`best_candidate_id` still identifies the raw potential leader.
`best_specialisation_candidate_id` identifies a confirmed site supporting an exact
positive specialisation result; it is null for unresolved or zero results. The
two candidate identities can differ. Constraint states and candidate quality
bounds also appear in the text explanation.

## Validation and fixture handling

CPython 3.14.7: 154 tests pass across the original synthetic fixtures, evidence
regressions, new constraint tests and the 12-system cohort. Ruff passes on the
scorer and all four test modules. Tests cover three-state constraints, missing
requirements, source confidence/provenance, raw-score invariance, distinct best
sites, candidates outside the raw top four, known/unknown combinations, input
ordering, duplicate/conflicting requirements and JSON null/bounds output.

The synthetic fixtures that assert usable Refinery specialisation now explicitly
supply usable ground. Their score assertions remain unchanged. No blanket ground
assumption is applied to real-system data.

All 84 real-system potential values remain unchanged. All 72 non-Refinery
specialisation values remain unchanged. The frozen cohort has no retained usable
ground fact, so its ten systems with known Refinery opportunities now report null
Refinery specialisation with a lower bound of 0 and an upper bound equal to their
previous intrinsic quality (92 for Praea Euq WV-W b2-2, 100 for the other nine).
Borann and HD 38179 still have no known Refinery opportunity and report 0..0.
The prior candidate-2 values remain in `s_candidate_2`; candidate-1 history is
also retained. No ground evidence was fabricated to preserve an old score.

## Remaining work before freeze

1. Canonical input enrichment: retain detailed body classification, body/ring
   reserve observations and usable-ground evidence with provenance. Landability
   alone is not an authoritative substitute for a usable specialisation site.
2. Canonical-to-mechanics adaptation and persistence in a disposable derived
   generation, including nullable specialisation and constraint traces.
3. Reviewed real-system/v3.4 comparisons and manifest freeze, followed by the
   reviewed production derived-data publication work.

The existing `SystemFacts.reserve_level` remains a fixture convenience. This pass
does not create a production reserve scalar, schema migration or API route.
