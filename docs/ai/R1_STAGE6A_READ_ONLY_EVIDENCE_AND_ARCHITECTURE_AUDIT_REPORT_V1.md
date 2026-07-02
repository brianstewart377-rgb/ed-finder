# R1 Stage 6A — Read-Only Evidence and Architecture Audit Report v1

**Status:** Drafted for independent review. This is a documentation-only Stage 6A completion report. It does not accept an architecture, authorise implementation, or alter CRE, CPE, or `ed-finder` behaviour.

**Audit date:** 2026-07-02  
**Audit mode:** Repository metadata and committed-file inspection only.  
**Database inspection:** Not performed. No access, credential, endpoint, role, permission record, query, or database snapshot was supplied or used.

## 1. Baseline and access record

### 1.1 Audited repository baseline

- **Repository:** `brianstewart377-rgb/colonisation-research-engine`
- **Branch inspected:** `main`
- **Immutable commit inspected:** `add9a51350e7754dadc09cd9712cd43e96499e33`
- **Commit subject:** `Align planner taxonomy with ontology`
- **Inspection method:** Read-only GitHub repository metadata and committed file retrieval.

The audit also read the Stage 6A contract and working-point record in `brianstewart377-rgb/ed-finder` at canonical branch `work/r1-canonical-body-evidence`, whose then-current commit was `e599e7b6cc234f6bf631d0892a33dd890ac16354`.

### 1.2 Repositories actually available

| Repository | Observed purpose / state | Immutable reference or retrieval record | What this establishes | What it does not establish |
|---|---|---|---|---|
| `brianstewart377-rgb/ed-finder` | Main application repository; carries the Stage 6 governance records. | `work/r1-canonical-body-evidence` at `e599e7b6cc234f6bf631d0892a33dd890ac16354`; retrieved 2026-07-02. | The R1 laboratory and its governance records have a separate home from CRE. | That it is already integrated with CRE or CPE. |
| `brianstewart377-rgb/colonisation-research-engine` | Research-knowledge repository with mechanics, evidence, provenance, contradictions, experiments, schemas, and exports. | `main` at `add9a51350e7754dadc09cd9712cd43e96499e33`; retrieved 2026-07-02. | CRE is an evidence and knowledge foundation, not merely a rating UI. | A live service, deployed database, or production planner implementation. |
| `brianstewart377-rgb/colony-planning-engine` | Public repository with default branch `main`; GitHub metadata reported `size: 0` and no repository commit existed at audit retrieval. | GitHub repository metadata on 2026-07-02: repository ID `1287613646`, public visibility, `default_branch: main`, `size: 0`, `master_branch: null`. No immutable commit/ref could be recorded because the repository was empty. | A separate CPE repository existed but contained no committed implementation at that time. | Any CPE code, schema, storage, runtime, or integration behaviour; any later state of the repository. |

The CPE entry is an observed empty-repository metadata state, not a claim about a permanent condition. Because no commit existed, future recovery must not infer this empty state from the repository name or current contents; it must retrieve the historical audit record and inspect the relevant repository state directly.

### 1.3 Access limits and excluded work

This audit did not:

- inspect a CRE database, local filesystem, runtime process, deployment, secrets store, or cloud account;
- run the CRE export script or validate generated artifacts locally;
- perform web research, live game scouting, external-data collection, or database queries;
- change any CRE, CPE, or `ed-finder` source, test, fixture, UI, configuration, schema, data record, runtime, or deployment;
- determine that any prospective CRE-to-CPE interface is implemented, correct, or ready for production.

The durable Stage 6A report and checkpoint documentation branch/PR are permitted completion documentation under the accepted Stage 6A contract. Their current review head must always be read from live PR metadata before acceptance or merge; no static draft report-content commit is a merge target.

## 2. Evidence and data inventory

### 2.1 What CRE is documented to be

`README.md` defines CRE as an evidence-backed research platform for Elite Dangerous Colonisation. It says the repository preserves raw evidence, observations, mechanics, experiments, contradictions, and planner-safe knowledge, and is not the `ed-finder` application, a production application, or a database implementation.

The committed repository layout includes:

- `constitution/` for research principles and governance;
- `architecture/` for platform and evidence-vault design;
- `ontology/` for entities, relationships, confidence, identity, and graph material;
- `mechanics/`, `evidence/`, and `experiments/` for evidence-backed knowledge and unresolved validation work;
- `planner/` for knowledge-consumption guardrails and planning concepts;
- `schemas/` for documentation-first structured contracts;
- `exports/` and `tools/` for prototype derived release outputs.

### 2.2 Knowledge and provenance material

The CRE knowledge-base index points to source coverage, mechanic catalogues, claims, observations, provenance links, contradiction and unknown registers, live-verification work, schemas, and exports.

The source-coverage register states that the active direct-extraction corpus is local to CRE under `reference_sources/`, with named canonical source identifiers `MG-0001`, `FW-0001`, `DM-0001`, and `DD-0001`. The report treats that as a repository claim; this audit did not independently re-extract those underlying source artifacts.

The export manifest is marked `0.2.0-draft` and lists deterministic derived outputs including mechanics, planner rules, claims, provenance links, contradictions, unknowns, live-verification records, and graph nodes/edges. The manifest says canonical registers remain the source of truth.

### 2.3 Planner-adjacent material currently in CRE

Three documentation-first draft schemas are particularly relevant to a future CPE boundary:

1. **`schemas/knowledge_projection.schema.json`**
   - CRE-side, planner-safe publication shape.
   - Includes source basis, mechanic/claim/observation references, contradiction and unknown references, confidence, patch context, publication decision, and withholding/downgrade states.

2. **`schemas/colony_state.schema.json`**
   - Mixed observed-state and planning-context draft.
   - Includes systems, bodies, slots, facilities, market links, economy snapshots, services, commodity observations, planner constraints, evidence links, and review state.
   - The schema usefully distinguishes facility type, station type, economy state, and contextual planning roles, but its ownership split is not yet final.

3. **`schemas/planner_recommendation.schema.json`**
   - Draft recommendation shape containing a goal, objectives, constraints, coverage gap, roles, candidate builds, expected effects and trade-offs, confidence, evidence, unknowns, and validation experiments.
   - Its plan-specific fields are closer to future CPE ownership than CRE research ownership.

CRE also holds planner-safety and evidence-consumption rules. These include blocking impossible builds, avoiding direct-economy-selection language, warning against weak-link-only claims, preserving contradiction, labeling confidence, and avoiding universalisation of contextual strategies.

### 2.4 Freshness, consistency, and uncertainty findings

**Stale summary index:** `docs/knowledge_base_index.md` reports `8` mechanics, `4` contradiction cases, and `5` live-verification items, and says several named source artifacts remain absent locally. The later export manifest reports `13` mechanics, `9` contradictions, and `12` live-verification records; the source-coverage register states that a canonical `reference_sources/` corpus is present and directly processed. The audit therefore treats the knowledge-base index as stale until corrected or regenerated.

**Draft versus implemented boundary:** The schemas, exports, and architecture documents establish a designed direction and structured vocabulary. They do not establish that a live CRE API, shared database, runtime importer, or CPE integration already exists.

**Mechanics uncertainty remains substantive:** CRE’s contradiction and live-verification registers retain open questions around post-build station-class differences, weak-link thresholds, main-port aggregation, modifier stacking, exact prerequisites, and other patch-sensitive areas. CPE must not turn these into unqualified plan claims.

## 3. Capability map

### 3.1 Questions the audited material can support

The audited CRE material can support documentation-grounded answers to questions such as:

- What evidence, claim, mechanic, contradiction, unknown, experiment, and planner-safety structures CRE intends to maintain.
- Which existing CRE records are source/provenance-oriented rather than plan-oriented.
- Which current draft contracts could become inputs to CPE after ownership and versioning are explicitly agreed.
- Which mechanics and planner constraints must carry caveats, confidence, or live-verification requirements.
- Which CRE material should remain the research source of truth rather than being copied into a planning repository.

### 3.2 Questions it can support only with caveats

The audited material can only partly support:

- whether `knowledge_projection` is sufficient as a CRE-to-CPE public contract; it is a draft schema, not an accepted cross-repository compatibility contract;
- whether `colony_state` should be split into observed state and CPE planning context; the present schema mixes both concerns;
- whether the current planner recommendation schema should move wholly to CPE, be split, or be replaced; it demonstrates overlap but does not itself decide ownership;
- whether release bundles should be files, an API, events, or another transport; the repository supports deterministic export assembly, but no transport has been selected.

### 3.3 Questions this audit cannot answer

This audit cannot establish:

- that CRE’s mechanics or projections are live-game correct in every case;
- that any database, API, data model, or infrastructure is already deployed or production-ready;
- the actual performance, compatibility, security, or operational cost of a shared database, API, event system, or cross-repository package;
- the right storage implementation for CRE, CPE, or `ed-finder`;
- the best CPE planning algorithm, scoring model, UI, schedule, or deployment model.

### 3.4 Questions outside Stage 6A repository-only scope

These require separately authorised work, external evidence, database inspection, or live in-game verification:

- current external galaxy-data availability, completeness, and licensing;
- current live game mechanics and patch drift;
- database contents, roles, permissions, data quality, and actual query behaviour;
- validation of market links, station behaviour, commodity availability, or proposed colony plans in game;
- implementation, integration testing, service deployment, or repository migrations.

## 4. Assumption and counterexample register

| Assumption or proposal | Counterexample / confounder | Evidence that would strengthen or qualify it | Current treatment |
|---|---|---|---|
| “Everything called planner should leave CRE.” | Planner-safety rules and their provenance are research knowledge. Moving them would duplicate or detach their evidence chain. | A field-by-field ownership inventory. | Do not move material by filename alone. |
| “CPE should directly read CRE internals or a future CRE database.” | CRE’s evidence model will evolve; direct access would couple CPE to raw claims, contradictions, and private implementation details. | An accepted published-contract and compatibility policy. | Reject as a default boundary. |
| “A shared operational database now is automatically simpler.” | Shared storage can force CPE needs into CRE research modeling and let research volatility break planning behaviour. | Concrete query, latency, ownership, security, and release requirements. | Defer; not ruled out forever. |
| “CRE’s current knowledge projection is already the CPE interface.” | It is explicitly documentation-first and draft; no cross-repository versioning or compatibility agreement exists. | Contract review, sample payloads, compatibility rules, and consumer tests in a separately authorised stage. | Candidate starting point only. |
| “The current colony-state schema belongs entirely to one repository.” | It contains both observed state and planner-context fields. | Explicit separation of observed facts from player-specific planning inputs. | Split ownership is likely but not yet accepted. |
| “CPE will need integration with CRE.” | This is strong owner design intent, but the exact transport and operational form are not yet evidenced. | A bounded integration use case and accepted interface contract. | Record intent; do not implement yet. |
| “A repository summary count is authoritative.” | CRE’s knowledge-base index and export manifest currently disagree. | A regenerated or corrected canonical summary. | Treat the index as stale. |

## 5. Architecture options required by the Stage 6A contract

The three options below are discovery alternatives only. They are not selected by this report, and none authorises a change to R1, CRE, CPE, `ed-finder`, a database, an API, or deployment.

### Option A — Careful extension of the existing R1 laboratory

Keep the accepted R1 laboratory as the only active planning-related surface. Any later extension would remain DEV-only, fixture-backed, deterministic, local, and bounded by the existing Stage 5 evidence discipline.

- **Potential benefit:** Lowest structural change and the strongest continuity with existing R1 invariants.
- **Risk:** The current R1 laboratory is not a substitute for CRE’s source/provenance/contradiction lifecycle or for a separate player-specific colony-planning engine.
- **Migration cost:** Low initially; may defer rather than solve the evidence-to-planning boundary.
- **Unanswered question:** Whether a bounded R1 extension can accommodate observed evidence and programme definition without weakening its fixture-backed model.
- **R1 invariant:** Preserved directly; no external runtime or research-data dependency is introduced.

### Option B — Separate observed-evidence and programme-definition layer that preserves R1

Keep R1 unchanged. Treat CRE as the research/evidence layer and define a separately governed observed-state and programme/planning boundary for later CPE consumption. The boundary would publish only versioned, planner-safe material, leaving raw CRE evidence and R1’s deterministic fixture model isolated.

- **Potential benefit:** Separates evidence evolution, observed colony facts, player-specific planning context, and future presentation concerns without changing R1.
- **Risk:** Requires explicit ownership, contract-versioning, compatibility, provenance, unknown/withheld handling, and no-duplication rules.
- **Migration cost:** Documentation and contract work first; implementation remains a later separately authorised decision.
- **Unanswered question:** Whether the first transport should be a release bundle, API, event flow, or other mechanism.
- **R1 invariant:** Preserved; R1 remains fixture-backed, deterministic, local, and not a runtime dependency of CRE/CPE.

### Option C — Controlled wider re-baselining later

After a separate owner-approved stage, redefine the broader system around a new evidence/programme/planning architecture. This could revisit how R1 relates to later engines, but only with explicit migration, test, provenance, and rollback decisions.

- **Potential benefit:** Maximum long-term design freedom.
- **Risk:** Highest scope, migration, and governance risk; can erase or blur accepted R1 semantics if attempted prematurely.
- **Migration cost:** High and currently unbounded.
- **Unanswered question:** What evidence, product, operational, and user requirements would justify re-baselining.
- **R1 invariant:** Must be explicitly preserved, superseded, or retired only by a later accepted contract; this audit makes none of those choices.

### Option B ownership and integration variants

The following variants refine Option B only. They do not replace the three contract-required options above and are not selections.

#### Variant B1 — Keep all planner-adjacent ownership in CRE

CRE would continue to own research, planner rules, current-state structures, and plan-output structures. CPE would remain empty or become a thin presentation layer.

- **Benefit:** Lowest immediate migration cost.
- **Risk:** Conflicts with the owner’s separate CPE repository direction; leaves research ownership and player-plan ownership blurred.
- **Assessment:** Not preferred.

#### Variant B2 — Separate ownership with a versioned CRE-to-CPE contract

CRE owns evidence, observations, mechanics, contradictions, unknowns, confidence, and versioned published knowledge/state releases. CPE owns player goals, preferences, planning constraints, candidate build layouts, sequencing, alternatives, and plan results. CPE reads only published CRE contracts, never raw CRE internals or a private CRE database.

- **Benefit:** Clear compartmentalisation with a real integration path from day one.
- **Risk:** Requires careful contract design and version management before implementation.
- **Assessment:** Best fit for the current three-repository discussion direction.

#### Variant B3 — Shared operational runtime or database early

CRE, CPE, and possibly `ed-finder` would use a shared database, API, event system, or common runtime early.

- **Benefit:** May reduce later integration work if there is a proven high-frequency or transactional shared-data requirement.
- **Risk:** Premature coupling; unclear data ownership; research-model changes could break planning behaviour; no audited requirement yet proves that this is needed now.
- **Assessment:** Do not select now. Reconsider only after an accepted contract and demonstrated operational need.

### Discussion direction, not an accepted architecture decision

The owner discussion favours **Variant B2 as an ownership model** while designing the future integration boundary now. The discussion does not select an architecture, does not approve Variant B2, and does not authorise implementation. It is a discussion record only until separately owner-accepted in a later contract stage.

The intended boundary objects discussed are:

1. **CRE Knowledge Release** — published mechanics, caveats, provenance, confidence, contradictions, unknowns, and version/patch context.
2. **CRE Observed Colony-State Snapshot** — timestamped evidence-linked facts about a selected system/body/facility context; no player preferences or selected plan.
3. **CPE Planning Request** — a pinned CRE release and observed state plus player objective, preferences, hard constraints, risk tolerance, and protected assets.
4. **CPE Plan Result** — candidate layout, sequencing, alternatives, trade-offs, confidence, caveats, applied CRE versions, and required validation steps.

## 6. Discussion record: names, repositories, and intended ownership

This section records owner discussion during the Stage 6A audit. It is a factual discussion record, not a substitute for a separately accepted architecture contract.

### 6.1 Names and repositories

```text
ed-finder
= main application repository

CRE — Colonisation Research Engine
= brianstewart377-rgb/colonisation-research-engine

CPE — Colony Planning Engine
= brianstewart377-rgb/colony-planning-engine
```

### 6.2 Intended responsibility split

**CRE should retain:**

- source evidence, provenance, observations, claims, mechanics, experiments, contradictions, unknowns, and confidence;
- canonical body/facility/economy facts and caveats;
- research-side planner-safety rules and the evidence supporting them;
- versioned CRE knowledge releases and observed-state snapshots.

**CPE should later own:**

- player objectives, preferences, risk tolerance, and hard constraints;
- protected facilities and explicit “do not demolish” decisions;
- colony-specific coverage analysis;
- candidate facilities, layouts, sequencing, alternatives, trade-offs, and plan revisions;
- CPE plan results.

**`ed-finder` should later own:**

- user-facing integration and presentation;
- no private ownership of CRE research logic or CPE plan logic.

### 6.3 Current CRE material requiring a later ownership inventory

| Current CRE material | Provisional ownership after split | Reason |
|---|---|---|
| Evidence, mechanics, contradictions, unknowns, experiments, provenance | CRE | Research source of truth. |
| Planner-safety rules tied to evidence | CRE | CPE must consume these, not rewrite their research basis. |
| `knowledge_projection.schema.json` | CRE-published contract candidate | Already expresses planner-safe, provenance-aware publication. |
| Observed portions of `colony_state.schema.json` | CRE-published state contract candidate | Captures evidence-linked system/body/facility state. |
| Player preferences, protected assets, plan constraints within `colony_state` | CPE planning-request candidate | These are owner-specific planning inputs, not observed CRE facts. |
| `planner_recommendation.schema.json` plan-specific fields | CPE plan-result candidate | Goal, constraints, candidate builds, trade-offs, and plan output belong to CPE. |
| Cross-repository versioning and compatibility rules | Shared boundary contract | Must have one named source of truth after a later approved contract stage. |

No file is moved, copied, renamed, or deleted by this report.

## 7. Safe next decision

The smallest decision for the owner to make after independent review of this report is whether to accept or amend this boundary statement:

> CRE, CPE, and `ed-finder` remain separate repositories with separate ownership. CRE publishes versioned evidence and observed-state contracts. CPE consumes only published CRE contracts and owns player planning context and colony-plan outputs. `ed-finder` later integrates and presents the two engines. No engine may directly depend on another engine’s private storage or internal implementation.

If accepted, the next stage must still be separately authorised and documentation-only. Its scope should be limited to a CRE-to-CPE boundary contract and ownership inventory. It should define versioning, compatibility, four boundary objects, provenance requirements, unknown/withheld handling, and a migration/no-duplication policy.

This report does **not** authorise code, tests, UI, fixtures, data, database access or writes, shared storage, API work, external research, live queries, scoring, rankings, recommendations, architecture implementation, deployment, or changes to normal R1 behaviour.

## 8. Recovery checkpoint

- **Audit report branch:** `docs/r1-stage6a-cre-repo-audit-report`
- **Audited CRE baseline:** `main` at `add9a51350e7754dadc09cd9712cd43e96499e33`
- **Audited `ed-finder` baseline:** `work/r1-canonical-body-evidence` at `e599e7b6cc234f6bf631d0892a33dd890ac16354`
- **Observed CPE audit state:** Metadata retrieval on 2026-07-02 reported public repository ID `1287613646`, default branch `main`, size `0`, and no commit/ref because the repository was empty.
- **Database inspection:** None; no access was supplied or verified.
- **Material caveats:** CRE summary index is stale; several CRE schemas are documentation-first drafts; live mechanics and database state were not independently verified.
- **Current review reference:** Before any acceptance or merge, fetch PR `#297` metadata and use its live head SHA. The static report-document revision commit recorded in `CURRENT_STAGE.md` is provenance for this document revision, not a merge target.
- **Next safe action:** Independent read-only review of this report and `CURRENT_STAGE.md`, then separate owner acceptance before merge. Do not start CPE design or implementation work until a later scope is expressly authorised.
