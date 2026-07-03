# ED-Finder Documentation Index

This is the practical entry point for the current ED-Finder documentation estate.

## Authority order

Current control document  
    beats  
Current index  
    beats  
Current named roadmap or active contract  
    beats  
Live GitHub PR and branch state  
    beats  
Historical or frozen control record  
    beats  
Chat memory

- **Current control document:** `docs/ai/CURRENT_STAGE.md`
- **Current index:** `docs/DOCUMENTATION_INDEX.md`
- **Current named roadmap or active contract:** the current roadmap or accepted contract named by `CURRENT_STAGE.md`
- **Live GitHub PR and branch state:** current live branch, head/base, review state, and merge state
- **Historical or frozen control record:** any stage-specific roadmap, contract, closeout, or operations record kept for provenance
- **Chat memory:** disposable working context only; never a durable authority

## Read first

1. `docs/ai/CURRENT_STAGE.md`
2. `docs/ai/AGENT_WORKING_POINT_PREFLIGHT_PROTOCOL_V1.md` — mandatory preflight and proof discipline before drafting, reviewing, or merging work
3. `docs/ai/D0_DOCUMENTATION_ESTATE_AND_CODE_BOUNDARY_REGISTER_V1.md` — current read-only documentation-estate and code-boundary register
4. the current named roadmap or active contract identified by `CURRENT_STAGE.md`
5. live GitHub PR and branch state
6. `docs/HISTORICAL_RECORDS_INDEX.md` — logical index for historical, frozen, superseded, and conflict-prone records
7. `docs/ai/DECISIONS.md`

Then inspect the live branch, exact commit, worktree state, and live GitHub PR state before making any write.

## Control planes

### Current ED-Finder Stage 25 product control

`docs/colonisation-redesign/stage-25-roadmap.md` is the current Stage 25 product-control document for ED-Finder. It governs the live product shell, product journey, and no-write boundaries for the current colonisation product work.

### Legacy ED-Finder ratings

The current stored ED-Finder ratings are the legacy `0–100` product ratings documented in `docs/colonisation-redesign/rating-system-current-contract.md`. They are offline-generated, stored product ratings for best-build potential and economy suitability; they are not player-specific plans, not R1 output, and not the future CPE assessment model.

### R1 Assessment Laboratory

The R1 Assessment Laboratory is a DEV-only, fixture-backed prototype and control-suite lineage kept inside `ed-finder`. It remains separate from the public product, must stay deterministic and local, and must not be described as a live public ranking, recommendation, or universal score.

### Future CPE System Assessment Engine

The future **CPE / System Assessment Engine** owns programme-specific candidate-system assessment against explicit requirements, pinned CRE inputs, and bounded comparison-ready outputs. It does not produce a universal score, universal rank, or product-wide replacement for the legacy ED-Finder stored ratings.

### CRE authority

CRE owns evidence, provenance, mechanics, contradictions, confidence, planner-safe knowledge releases, and observed-state publications. If a question is about source truth, evidence quality, uncertainty, or mechanical interpretation, CRE is the authority.

### CPE authority

CPE is the future authority for programme-specific assessment and player-specific plan construction. Within CPE, System Assessment evaluates candidate systems against a named programme, and Colony Plan Construction turns assessed systems plus player intent into layouts, sequencing, alternatives, and validation-aware plan outputs.

### Historical stage and operations records

Historic stage roadmaps, contracts, closeouts, and operations notes remain in place for provenance and recovery. They are useful when tracing why a boundary exists, but they do not outrank `docs/ai/CURRENT_STAGE.md` or this index.

## Historical record rule

A historical contract may explain provenance, but it must never authorise current work, define the next stage, or override the current working-point record.

## Safe interpretation rules

- Do not collapse the legacy ED-Finder ratings into R1, CRE, or future CPE assessment.
- Do not treat the R1 laboratory as a public runtime feature.
- Do not treat future CPE assessment as a universal score.
- Do not treat historic stage wording as current control when `CURRENT_STAGE.md` or the live merged GitHub state says otherwise.
- Do not rely on chat summaries when repository records and live Git state can answer the question directly.
