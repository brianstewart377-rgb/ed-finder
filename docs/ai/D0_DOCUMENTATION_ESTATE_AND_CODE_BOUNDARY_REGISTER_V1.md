# D0 Documentation Estate and Code Boundary Register V1

**Date:** 2026-07-03

## Purpose and limits

D0 records documentation-estate findings and initial code-boundary observations across `ed-finder`, CRE, and CPE.

It authorises no archive, deletion, move, rename, refactor, API build, database change, shared package, runtime, deployment, or implementation work.

Any SHA recorded here is an audit snapshot only, never a live recovery pointer.

## Verified cross-repository baseline

- `ed-finder`: `work/r1-canonical-body-evidence` at `95b1eba4c026ac75b003e148fc8d3d8a4430ac46`
- CRE: `main` at `add9a51350e7754dadc09cd9712cd43e96499e33`
- CPE: `main` at `9d5ff8cc3cdd6653081f5f490dfd4b5b40423197`

## Documentation-estate register

| Item | Classification | Authority | Permitted next action |
| --- | --- | --- | --- |
| `docs/ai/CURRENT_STAGE.md` | Current working-point authority | Current control document | Preserve |
| `docs/DOCUMENTATION_INDEX.md` | Current navigation authority | Current index | Preserve |
| Stage 25 roadmap | Current ED-Finder product control | `docs/colonisation-redesign/stage-25-roadmap.md` | Preserve |
| CPE roadmap, continuity ledger, closeout protocol, and decisions | Current cross-repository governance | `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`, `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md`, `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`, `docs/ai/DECISIONS.md` | Preserve |
| Legacy ED-Finder ratings contract | Current legacy product behaviour | `docs/colonisation-redesign/rating-system-current-contract.md` | Preserve; do not conflate with CRE, CPE, or R1 |
| R1 Laboratory contracts and closeouts | Historical and DEV control lineage | R1 contracts and closeout records in `docs/ai/` | Retain for provenance; do not treat as product truth |
| Older stage roadmaps and operations records | Historical/reference | Historic stage and operations documents | Retain pending separately authorised logical archive/index work |
| Root `README.md` and `CHANGES.md` | Navigation/history debt | Repository root documentation | Candidate for later D1b docs-only work |
| CRE knowledge-base index/count mismatch | Bounded documentation-repair debt | CRE repository documentation | Bounded later D1c documentation-repair candidate |
| CRE historic execution prompts | Reference-only historical material | CRE historic prompt records | Retain as reference-only, not living control |
| CPE root documentation | Living boundary documentation | CPE root documentation | Preserve with no runtime/API/database selection |

## Initial code-boundary register

- `ed-finder` owns the live product, existing HTTP API, search, stored ratings, simulation, optimiser, observations, and presentation.
- The R1 Assessment Laboratory remains local, deterministic, fixture-backed DEV control code inside `ed-finder`; it is not a service or extraction candidate.
- CRE exclusively owns evidence, provenance, mechanics, contradictions, confidence, and planner-safe releases.
- CPE will own programme-specific assessment and player-specific plan construction, consuming pinned CRE publications.
- `ed-finder`’s existing planner/evidence code must not silently become CRE truth or future CPE implementation.
- Temporary duplication is acceptable only at contract edges; direct database sharing is not.

## Shared-interface decision

The shared decision now is a versioned CRE-to-CPE release contract.
A shared network API is deferred until real operating needs justify it.
No shared database, raw CRE-evidence access from CPE, or shared package is selected.

API triggers:

- more than one deployed consumer;
- selective queries are genuinely needed beyond immutable releases;
- independent release/deployment cadence;
- access control or audit requirements;
- repeated copied-release drift.

When justified, `ed-finder` should consume CPE outputs through a dedicated adapter on its existing product API rather than becoming the owner of CRE truth or CPE planning logic.

## Remediation queue

- D1b: root navigation/history/changelog docs cleanup.
- D1c: CRE knowledge-base index/count repair.
- D2: logical archive/index treatment for historical records.
- Later targeted deletion review only after inbound-reference and unique-provenance checks.
- Later code-boundary review before any extraction, shared contract implementation, or API decision.

## Next safe action

D1b is the proposed next documentation batch: a separately authorised,
docs-only root navigation and history/changelog cleanup. It must not archive,
delete, move, rename, refactor, or implement any API or code boundary.
