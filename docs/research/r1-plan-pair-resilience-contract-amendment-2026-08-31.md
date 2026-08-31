# ED-Finder R1 — Plan Pair Resilience Contract Amendment

Date: 2026-08-31  
Status: accepted design correction; docs/contract only  
Branch: `chatgpt-ed-new-ops-requests`

## Decision

`pair_stability` must **not** be treated as an intrinsic property of a star system or of canonical `CandidateEvidence`.

A system supplies capabilities, constraints and evidence. A player objective/programme causes ED-Finder to construct or evaluate a candidate plan. Only that candidate plan can have a top-two economy outcome and a resilience classification.

The correct flow is:

```text
system facts/capabilities
    ↓
selected comparison objective/programme
    ↓
candidate plan + concrete allocation
    ↓
modelled economy/link outcome for that plan
    ↓
plan-pair resilience
```

The incorrect flow is:

```text
system facts → intrinsic pair_stability
```

A strong Tourism/Agriculture system does not have to remain Tourism/Agriculture after a player deliberately replaces the intended programme with a mining-heavy build. That is a different plan and must be reassessed as such.

## New term

Use **`plan_pair_resilience`** for the plan-relative classification.

Allowed values remain conceptually:

- `robust` — the proposed plan produces the intended top-two pair and remains so under the declared ordinary-variation test pack;
- `fragile` — the proposed plan produces the pair at baseline but a small plausible variation can displace/tie one target economy;
- `mixed` — the proposed plan itself already has material third-economy competition or fails the intended top-two result;
- `unknown` — the proposed plan exists, but current link/economy evidence is insufficient to classify its outcome reliably.

`unknown` must **not** mean “the player might later choose to build something completely different.”

## Ordinary-variation boundary

Resilience testing may challenge the proposed plan with bounded, plausible perturbations such as:

- one plausible competing weak link;
- a small supporting-facility variation;
- a documented uncertain modifier;
- a bounded link/economy-model uncertainty.

It must not test wholesale abandonment of the selected programme, e.g. filling every available location with an unrelated economy and then claiming the original plan was unstable.

## Consequences for the Finder comparison proof

The existing shadow proof currently carries `pair_stability` on `CandidateEvidence`. That placement is now semantically deprecated.

Before that proof becomes the basis of a real-data bridge or Finder integration:

1. remove system-level pair-stability truth from candidate facts;
2. represent any fixture economy-outcome evidence separately from system capabilities;
3. generate/evaluate the candidate P-ER-01 allocation first;
4. calculate/attach `plan_pair_resilience` to the programme assessment or candidate-plan result;
5. keep role-only Extraction comparison independent of pair resilience;
6. preserve the existing state precedence and search→detail continuity rules.

The current proof remains useful as a semantic experiment, but its pair field location must not be copied into production R1 contracts.

## Consequences for the Real Evidence Bridge

The bridge must **not** project `pair_stability='unknown'` as a factual system property.

Instead it should project only system-level evidence such as:

- canonical body identities/modifiers;
- physical slot/capacity predictions with provenance;
- locality/distance facts;
- known Extraction/Refinery source capabilities;
- evidence availability/conflicts.

The bridge can truthfully say the system has known ER-supporting capabilities. It cannot classify an ER pair until a concrete candidate programme/allocation has been evaluated.

If downstream compatibility temporarily requires the old `CandidateEvidence.pair_stability` field, the adapter may populate the sentinel `unknown` **only as a compatibility placeholder**, clearly marked deprecated/non-factual and never surfaced as a system characteristic. The preferred remediation is to move the field out of `CandidateEvidence` before live integration.

## P-ER-01 assessment boundary

For a real system, the sequence becomes:

```text
real canonical system evidence
    ↓
P-ER-01 candidate-plan generator
    ↓
explicit body/node/slot/facility allocation
    ↓
link/economy-outcome model
    ↓
plan_pair_resilience
    ↓
assessment state + conditions
    ↓
optional Plan Fit
```

A system with strong Extraction and Refinery capabilities is therefore a promising ER candidate even before pair resilience is available. It is not condemned merely because the link/outcome layer has not yet run.

Search UX should distinguish this cleanly, e.g. capability evidence may be strong while final programme outcome remains pending/conditional.

## Supersession

This amendment supersedes references that describe `pair_stability` as a system/candidate-evidence fact in:

- `docs/research/r1-finder-comparison-proof-stage-review-2-2026-08-31.md`;
- `docs/research/r1-real-evidence-bridge-review-2-2026-08-31.md`.

All other evidence, Unknown-preservation, slot, ordering, plateau, carrier and provenance rules remain unchanged.

## Safety boundary

This amendment changes design semantics only. No production code, DB, migration, Finder UI, API, scoring, deployment or merge change is authorised by this document.
