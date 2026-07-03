# Historical Records Index

This index classifies records for navigation and safe interpretation.
It does not authorise archive moves, renames, deletions, or content removal.

## Lifecycle taxonomy

| Classification | Meaning |
| --- | --- |
| `current_control` | Current working-point authority |
| `current_navigation` | Current navigation/index layer |
| `active_contract` | Still relevant contract logic, but not a working-point override |
| `frozen_dev_control` | Frozen DEV-only control lineage retained for provenance |
| `historic_reference` | Completed historical record retained for explanation or audit |
| `superseded_reference` | Retained older record replaced by a named successor |
| `stale_conflict` | Record whose wording can mislead unless read through current control |
| `deletion_candidate` | Candidate only where current evidence genuinely supports later review |
| `unknown` | Retained until better evidence exists |

## Register

| Path or family | Lifecycle classification | Can authorise current work | Controlling replacement or next read | Why retained | Inbound-reference check needed before any physical action |
| --- | --- | --- | --- | --- | --- |
| `docs/ai/CURRENT_STAGE.md` | `current_control` | Yes | None above it | Current working-point authority | No |
| `docs/DOCUMENTATION_INDEX.md` | `current_navigation` | No | `docs/ai/CURRENT_STAGE.md` | Navigation layer for current control | No |
| `docs/ai/AGENT_WORKING_POINT_PREFLIGHT_PROTOCOL_V1.md` | `current_navigation` | No | `docs/ai/CURRENT_STAGE.md` then this protocol | Mandatory preflight and proof discipline | No |
| `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` | Current cross-repository roadmap context | No |
| `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` | Lifecycle and anti-burial continuity record | No |
| `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` | Merge-closeout and recovery protocol | No |
| `docs/ai/DECISIONS.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` | Durable decisions and invariants | No |
| `docs/colonisation-redesign/rating-system-current-contract.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` then `docs/DOCUMENTATION_INDEX.md` | Current legacy ED-Finder ratings behaviour | No |
| `docs/ai/R1_*LAB*`, `docs/ai/R1_STAGE4*_PLAN_FIT*`, `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md` | `frozen_dev_control` | No | `docs/ai/CURRENT_STAGE.md` then `docs/DOCUMENTATION_INDEX.md` | Frozen DEV-only R1 lineage and provenance | Yes |
| `docs/ai/R1_STAGE4C_*` completed records | `historic_reference` | No | `docs/ai/CURRENT_STAGE.md` then `docs/HISTORICAL_RECORDS_INDEX.md` | Completed Stage 4C historical record only | Yes |
| `docs/ai/R1_STAGE6B_CRE_CPE_BOUNDARY_CONTRACT_V1.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` then `docs/ai/R1_STAGE6_STATUS_CLOSEOUT_V1.md` | Current logical ownership boundary reference | No |
| `docs/ai/R1_STAGE6C_CRE_CPE_FIELD_CONTRACT_DETAIL_V1.md` | `active_contract` | No, not by itself | `docs/ai/CURRENT_STAGE.md` then `docs/ai/R1_STAGE6_STATUS_CLOSEOUT_V1.md` | Current field-level logical boundary reference | No |
| Older completed roadmaps and operations records under `docs/colonisation-redesign/` and older completed records under `docs/ai/` | `historic_reference` | No | `docs/ai/CURRENT_STAGE.md`, `docs/DOCUMENTATION_INDEX.md`, then the named current roadmap or active contract | Provenance, historical reasoning, and audit trace | Yes |
| Historical records with wording that can still look current unless read through live state | `stale_conflict` | No | `docs/ai/CURRENT_STAGE.md`, live GitHub PR and branch state | Retained because provenance still matters, but wording can mislead | Yes |
| Root `CHANGES.md` | `historic_reference` | No | `docs/DOCUMENTATION_INDEX.md` then live GitHub history | Retained historical development log | No |
| `docs/ai/D0_DOCUMENTATION_ESTATE_AND_CODE_BOUNDARY_REGISTER_V1.md` | `historic_reference` | No | `docs/ai/CURRENT_STAGE.md` then this index | Completed read-only audit register that produced later follow-on batches | No |
| D1a merge and closeout records in `docs/ai/CURRENT_STAGE.md` and PR `#303` lineage | `historic_reference` | No | `docs/ai/CURRENT_STAGE.md` then live GitHub PR history | Records the completed D1a merge and closeout provenance | No |
| D1b root navigation/history framing records in `docs/ai/CURRENT_STAGE.md` and PR `#305` lineage | `historic_reference` | No | `docs/ai/CURRENT_STAGE.md` then live GitHub PR history | Records the completed D1b merge provenance | No |

## Interpretation rule

A historical contract may explain provenance, but it must never authorise current work, define the next stage, or override the current working-point record.

When uncertain, prefer `historic_reference` or `unknown` over `deletion_candidate`.
