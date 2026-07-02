# R1 Stage 6B — CRE-to-CPE Boundary Contract v1

**Status:** Drafted for independent review. This is a documentation-only boundary contract. It does not authorise implementation, repository scaffolding, storage, an API, schema code, database access, integration, deployment, or any product-behaviour change.

## 1. Purpose

Stage 6B records the future logical ownership boundary and versioned exchange contract among:

- `brianstewart377-rgb/colonisation-research-engine` (**CRE** — Colonisation Research Engine);
- `brianstewart377-rgb/colony-planning-engine` (**CPE** — Colony Planning Engine);
- `brianstewart377-rgb/ed-finder` (**ed-finder** — main application and later presentation/integration surface).

The purpose is to preserve a clean separation between research evidence, player-specific planning, and user-facing presentation before any implementation is considered.

This contract is based on the Stage 6A repository-only audit merged in PR `#297` at `c50723e307566e0c008acf29a84e6dfa88d6ef29`. It converts none of the Stage 6A architecture options into a runtime, storage, or product decision.

## 2. Status and governing boundaries

### 2.1 Draft status

Until independently reviewed, accepted by the owner, and merged, this document is a proposed boundary. It creates no accepted technical interface and grants no implementation authority.

After acceptance, it is an ownership and contract-governance record only. It still does not authorise code, data movement, runtime selection, or deployment.

### 2.2 Continuing evidence discipline

The Stage 5A non-inference rule and Stage 5B evidence discipline remain in force:

```text
source record
→ normalized evidence fact
→ named programme requirement or constraint
→ bounded conclusion or stated limitation
```

Owner intent may define a future design direction. It does not turn incomplete evidence into a game fact, silently resolve a contradiction, or establish live-game correctness.

### 2.3 R1 protection

Nothing in this contract changes the accepted R1 laboratory. It remains DEV-only, deterministic, fixture-backed, local, and separate from any future CRE/CPE runtime.

## 3. Ownership boundary

### 3.1 CRE owns research knowledge

CRE remains the sole source of truth for:

- raw evidence and evidence metadata;
- source provenance, observations, claims, mechanics, experiments, contradictions, unknowns, confidence, review state, and patch/context caveats;
- canonical body, facility, economy, market-link, material, and other research facts or hypotheses;
- research-side planner-safety rules and the evidence supporting them;
- release-ready, planner-safe knowledge and observed-state publications.

CPE must not edit, reinterpret as fact, or replace CRE evidence, claims, mechanics, confidence, contradiction, or withholding decisions.

### 3.2 CPE owns player-specific planning

CPE is the future owner of:

- player objectives, preferences, risk tolerance, and declared priorities;
- hard planning constraints, including protected assets and explicit non-demolition rules;
- plan-specific coverage analysis;
- candidate layouts, facility choices, sequencing, alternatives, trade-offs, and plan revisions;
- plan results, their caveats, and proposed validation steps.

CPE must treat CRE material as an external published input, never as an editable internal source.

### 3.3 ed-finder owns later presentation and coordination

ed-finder is the future user-facing presentation and coordination layer. It does not become the private owner of CRE research logic or CPE planning logic merely because it displays their outputs.

### 3.4 Contract-governance location

During this documentation-only phase, this contract in `ed-finder/docs/ai/` is the governance record for the cross-repository boundary. That does not create a shared code package, shared schema repository, shared database, or runtime dependency.

Any later decision to relocate the accepted contract or create a technical shared-contract artifact requires a separately authorised and reviewed stage.

## 4. Four boundary objects

The following are logical contract objects. They are not implemented schemas, API payloads, database tables, or runtime messages.

### 4.1 CRE Knowledge Release

**Owner:** CRE  
**Purpose:** Publish planner-safe research knowledge without exposing CRE private storage or raw internal structures as a dependency.

A knowledge release must identify:

- a stable release identifier and contract version;
- publisher repository and immutable source/release reference where available;
- included mechanics, claims, observations, guardrails, and relevant patch/context information;
- provenance references sufficient to trace published statements back to CRE-held evidence or canonical records;
- confidence, contradiction, unknown, caveat, and withholding status;
- publication date and supersession or withdrawal information where applicable.

A knowledge release must not be interpreted as a universal recommendation, scoring system, automatic choice, or proof of live-game behaviour beyond its stated evidence and caveats.

### 4.2 CRE Observed Colony-State Snapshot

**Owner:** CRE  
**Purpose:** Publish a timestamped, evidence-linked description of observed or explicitly projected colony context.

A state snapshot must distinguish, rather than collapse:

- observed, previewed, predicted, proposed, and completed state;
- physical body context, placement capacity, and realised facilities;
- facility class, station type, economy state, market-link relationship, and contextual planning role;
- evidence-backed facts, modelled hypotheses, contradictions, unknowns, and unverified assumptions.

A state snapshot must not contain player objectives, preferences, risk tolerance, protected-asset choices, or a selected plan. Those belong to CPE planning context.

### 4.3 CPE Planning Request

**Owner:** CPE  
**Purpose:** Combine pinned CRE publications with owner-provided planning intent without modifying either input.

A planning request must identify:

- the exact CRE Knowledge Release and Observed Colony-State Snapshot it consumes;
- player objectives and priorities;
- explicit hard constraints, protected assets, and prohibited actions;
- stated risk tolerance and handling preference for unknown or contradictory evidence;
- any declared programme requirements, assumptions, or scope limits.

A planning request must not present user preference as an observed CRE fact or rewrite a CRE caveat into a positive conclusion.

### 4.4 CPE Plan Result

**Owner:** CPE  
**Purpose:** Present a plan-specific decision-support output that remains traceable to its inputs and limitations.

A plan result must identify:

- the Planning Request and pinned CRE releases/snapshots used;
- candidate plan(s), sequence, alternatives, expected effects, and trade-offs;
- relevant constraints satisfied, unsatisfied, or not assessable;
- confidence, caveats, contradictions, unknowns, and any withheld conclusion;
- required live verification, validation steps, or evidence needed before irreversible action.

A plan result must not claim that CPE has changed CRE knowledge, resolved an unresolved mechanic, chosen a player objective, or established a live-game outcome without evidence.

## 5. Versioning and compatibility rules

### 5.1 Contract and object identity

Every later published boundary object must carry, at minimum:

- object kind;
- contract version;
- publisher/owner;
- stable object or release identifier;
- publication or capture time as applicable;
- immutable source/release reference where one exists;
- supersession, withdrawal, or compatibility status where relevant.

### 5.2 Version semantics

The future technical contract must use explicit semantic versioning or an equivalently documented major/minor/patch rule:

- **Major:** a breaking semantic or required-field change; consumers must not assume compatibility.
- **Minor:** an additive, backward-compatible extension; consumers may ignore optional unfamiliar content only when the release explicitly permits that.
- **Patch:** a correction or clarification that does not change the contract's required meaning.

This Stage 6B document is contract version `v1` as governance text. It does not itself publish an executable schema version or authorise implementation of semantic-version tooling.

### 5.3 Consumer obligations

Before CPE relies on a CRE publication, it must identify a supported contract major version. An unsupported or ambiguous version must produce a visible withholding, limitation, or non-assessable result; it must not silently be interpreted as compatible.

CPE plan results must preserve input identifiers so a later reader can determine which CRE release and state snapshot informed the plan.

## 6. Provenance, uncertainty, and withholding

### 6.1 Provenance preservation

Published CRE statements consumed by CPE must retain a traceable reference to the CRE release and its evidence/provenance basis. CPE may add plan-specific reasoning, but it must not erase or replace the research basis.

### 6.2 Unknown and contradictory evidence

The following states must survive the boundary without conversion into a positive or negative fact:

- unknown;
- missing;
- contradictory;
- stale;
- incomplete;
- unsupported;
- withheld;
- out of scope;
- pending live verification.

CPE may respond with a bounded warning, a validation step, alternatives conditioned on the uncertainty, or a non-assessable outcome. It must not silently treat an unknown as `false`, `zero`, `available`, `safe`, or `resolved`.

### 6.3 Withholding rules

CRE may withhold a publication or mark part of it unsuitable for planning. CPE must honor that decision. CPE cannot recreate a withheld conclusion from raw/private CRE internals or from absent data.

## 7. No-direct-access and no-duplication rules

### 7.1 No direct private-storage access

CPE must not directly depend on:

- CRE raw evidence storage;
- a future CRE database, private table, internal import pipeline, working directory, or unpublished export;
- CRE internal source paths as a runtime contract;
- private credentials, secret stores, or unpublished operational interfaces.

A later API, file-release, event, shared-read-model, package, or storage decision requires separate authorisation. This contract chooses none of them.

### 7.2 No duplicate sources of truth

- CRE remains authoritative for research knowledge.
- CPE remains authoritative for player-specific planning context and plan output.
- ed-finder remains a future presentation/co-ordination layer, not a competing source of research or plan truth.

CPE may reference pinned CRE publication identifiers and derive plan-specific outputs. It must not create an unproven duplicate canonical mechanic, source provenance, confidence value, or contradiction resolution.

## 8. Ownership inventory for current CRE planner-adjacent material

This is a semantic inventory, not a file-move instruction.

| Current material | Current and future authoritative owner | Boundary treatment | Physical action in Stage 6B |
|---|---|---|---|
| `evidence/`, `mechanics/`, `experiments/`, contradiction/unknown registers, ontology, evidence-vault material | CRE | Research source of truth. | No copy, move, or edit. |
| CRE planner-safety rules and evidence-backed planner guardrails | CRE | CPE must consume their published implications, not rewrite their research basis. | No copy, move, or edit. |
| `schemas/knowledge_projection.schema.json` | CRE | Candidate starting point for the future CRE Knowledge Release, subject to later contract/schema work. | No copy, move, or edit. |
| Observed-state portions of `schemas/colony_state.schema.json` | CRE | Candidate starting point for a future CRE Observed Colony-State Snapshot. | No copy, move, or edit. |
| Player objectives, protected assets, preferences, risk tolerance, and plan constraints currently mixed into colony-state/planner drafts | CPE in a future authorised stage | Candidate Planning Request content. | No extraction, copy, move, or edit. |
| Plan-specific portions of `schemas/planner_recommendation.schema.json` | CPE in a future authorised stage | Candidate Plan Result content. | No extraction, copy, move, or edit. |
| `exports/` and release-building tools | CRE | Derived publication machinery remains CRE-owned. | No copy, move, or edit. |
| `ed-finder` UI or R1 laboratory | ed-finder / existing R1 governance | Not a CRE/CPE implementation target in this stage. | No change. |

## 9. Migration rules

No migration occurs in Stage 6B.

Before any future material is moved, copied, split, replaced, or newly implemented, a separately authorised stage must provide:

1. the exact source and destination of each affected item;
2. the post-migration source-of-truth rule;
3. stable identifiers and provenance preservation;
4. compatibility and rollback handling;
5. independent review and separate owner acceptance.

Until then, current CRE material remains where it is. CPE must not be scaffolded merely to mirror it.

## 10. Explicit non-goals

Stage 6B does not authorise:

- CPE repository scaffolding, README changes, schema files, code, tests, CI, packaging, UI, or documentation outside this controlled governance record;
- CRE source, schema, export, evidence, data, or governance changes;
- moving, copying, deleting, renaming, or splitting CRE files;
- shared storage, a shared database, direct database access, API work, event infrastructure, a shared package, a runtime, or deployment;
- external research, live-game work, game scouting, database queries, source collection, or data import;
- scoring, ranking, recommendation, automatic selection, planner algorithm design, or product behaviour;
- selection of a runtime, transport, storage, or integration architecture.

## 11. Allowed durable output and review process

The only allowed durable files for this stage are:

- `docs/ai/R1_STAGE6B_CRE_CPE_BOUNDARY_CONTRACT_V1.md`
- `docs/ai/CURRENT_STAGE.md`

The contract may create a dedicated documentation branch and pull request only for these files. It may not merge itself. Independent review and a separate owner acceptance remain required before merge.

## 12. Completion and next safe action

A merged Stage 6B contract would establish only the future logical ownership and governance boundary described here. It would not authorise a technical contract implementation.

The next safe action after a future acceptance and merge would be a separately authorised, documentation-only contract-detail stage, limited to selecting the first implementable publication shapes and a field-level ownership map. That later stage would still not authorise code, schemas, APIs, databases, shared storage, repository scaffolding, or integration.
