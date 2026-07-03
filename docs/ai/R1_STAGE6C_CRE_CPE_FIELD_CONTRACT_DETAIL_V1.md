# R1 Stage 6C — CRE-to-CPE Field Contract Detail v1

**Status:** Drafted for independent review. This is a documentation-only field-contract record. It defines logical field meaning and ownership only. It is not an executable schema, API specification, database design, event definition, shared package, or runtime contract.

**Governing boundary:** Stage 6B CRE-to-CPE Boundary Contract, merged in PR `#298` at `dad29b1760e8291f8c48db665ed4be5e193d51db`.

## 1. Purpose and scope

Stage 6C turns the accepted Stage 6B logical boundary into a field-level documentation record for these four logical objects:

1. **CRE Knowledge Release**
2. **CRE Observed Colony-State Snapshot**
3. **CPE Planning Request**
4. **CPE Plan Result**

It identifies each field's logical meaning, owner, presence rule, provenance obligations, uncertainty handling, and prohibited use. It does not select a physical encoding, field names in source code, data types, transport, endpoint, table, package, repository structure, or deployment model.

This document does not alter the Stage 5 evidence discipline, the Stage 6A audit findings, the Stage 6B ownership boundary, or existing R1 laboratory behaviour.

## 2. Contract language and field legend

### 2.1 Normative language

For this documentation contract:

- **Must** means a later implementation or publication cannot claim conformance without it.
- **May** means permitted but not required.
- **Must not** means prohibited by the ownership boundary.
- **Conditionally required** means required only when the stated condition exists; absence must be explicit, not silent.

### 2.2 Presence rules

| Mark | Meaning |
|---|---|
| **R** | Required in every instance of the logical object. |
| **C** | Conditionally required when its stated condition applies. |
| **O** | Optional; absence has no implied value. |
| **X** | Prohibited in this object. |

### 2.3 Ownership classes

| Owner class | Meaning |
|---|---|
| **CRE** | CRE determines and publishes the field. CPE must not replace its research meaning. |
| **CPE** | CPE determines the field from player input or planning work. CRE does not own it. |
| **Derived CPE** | CPE derives the field from pinned CRE inputs plus stated planning inputs. The derivation must remain traceable. |
| **Presentation only** | A later `ed-finder` presentation may display or format the field, but does not become its source of truth. |
| **Prohibited** | The field must not appear in the object. |

### 2.4 General field rules

Every later conforming object must:

- retain its object kind, contract major version, stable object identifier, owner/publisher, and creation or publication time;
- retain input pins and provenance links required by its object type;
- distinguish an absent field from an explicit `unknown`, `not applicable`, `withheld`, or `not assessed` state;
- preserve the uncertainty and caveat state attached to the underlying CRE material;
- avoid treating user preference, a CPE plan, a preview, or a prediction as an observed CRE fact.

No object may include private credentials, raw database connection details, unpublished storage paths, private source binaries, or a reference that requires another engine's private implementation to interpret.

## 3. Common logical envelope

The following fields apply across the four objects unless a later field table marks them prohibited.

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Object kind | R | Object owner | Identifies exactly one of the four Stage 6B object kinds. |
| Contract major version | R | Publisher | Identifies the compatible major contract meaning. A consumer must not assume compatibility across major versions. |
| Contract minor / patch version | C | Publisher | Required when a versioning scheme distinguishes them. Must not be used to hide a breaking semantic change. |
| Stable object identifier | R | Object owner | An opaque identifier for this logical record. It must not encode secret storage paths or rely on an implementation-specific database key. |
| Publisher / owner | R | Object owner | Identifies CRE or CPE as appropriate. `ed-finder` is presentation only unless a later contract expressly changes that. |
| Created or published time | R | Object owner | Timestamp for record capture or publication. It does not prove that the underlying game state was current at that time. |
| Immutable release/source reference | C | CRE or CPE | Required where a stable published revision exists. If none exists, the absence and reason must be visible. |
| Supersession / withdrawal status | C | Object owner | Required when an object has been superseded, withdrawn, or found unusable for its stated purpose. |
| Compatibility declaration | C | Publisher | Required when the object adds a non-default compatibility limitation or consumer requirement. |
| Scope statement | R | Object owner | States what system, bodies, assets, planning problem, or knowledge domain the object covers. |
| Provenance references | C | CRE or Derived CPE | Required whenever the object makes a research-grounded factual or causal statement. |
| Caveat / uncertainty references | C | CRE or Derived CPE | Required whenever a source, claim, field, or derived conclusion has a relevant limitation. |
| Private implementation detail | X | Prohibited | Must not appear as a contract dependency. |

## 4. CRE Knowledge Release — field detail

**Owner:** CRE  
**Purpose:** Publish planner-safe research knowledge without exposing raw CRE internals as a dependency.

### 4.1 Release-level fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Release identifier | R | CRE | Stable identity for the knowledge release. |
| Publication status | R | CRE | Indicates whether the release is active, superseded, withdrawn, partially withheld, or otherwise limited. The exact encoding remains unselected. |
| CRE source baseline | C | CRE | Immutable CRE commit, tag, content digest, or equivalent reference when one exists. A mutable branch name alone is not sufficient as an immutable baseline. |
| Publication time | R | CRE | When CRE published the release; does not itself establish factual freshness. |
| Knowledge-scope statement | R | CRE | Defines which mechanics, claims, observations, guardrails, patch contexts, or research areas are included. |
| Patch / context scope | C | CRE | Required where the published knowledge is patch-sensitive, version-sensitive, system-sensitive, or condition-sensitive. |
| Entry set | R | CRE | The published planner-safe knowledge entries described below. |
| Release-level caveats | C | CRE | Required when a limitation applies to the release as a whole. |
| Supersedes / superseded-by reference | C | CRE | Required when a relation is known. Must not imply that an old release is false unless CRE says so. |
| Withdrawal or withholding reason | C | CRE | Required when release status limits use. |

### 4.2 Knowledge-entry fields

Each published knowledge entry is a CRE-owned statement, not a CPE plan rule.

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Entry identifier | R | CRE | Stable identity for a published knowledge entry. |
| Entry category | R | CRE | Identifies the entry as, for example, mechanic, observation, claim, guardrail, contradiction, unknown, or experiment outcome. It must not collapse these categories. |
| Planner-safe statement | C | CRE | Required when Publication decision makes the entry publishable for planning, including a downgraded entry. It must preserve qualification rather than overstate evidence. It is not required for a withheld or excluded entry that uses the safe stub below. |
| Applicability conditions | C | CRE | Required when the statement depends on body type, facility context, patch, link type, current state, or another stated condition. |
| Evidence / provenance references | C | CRE | Required when Publication decision makes the entry publishable for planning, including a downgraded entry. They must trace the entry to CRE-held evidence, claims, observations, or canonical records. They are not required for a withheld or excluded entry that uses the safe stub below. |
| Confidence status | R | CRE | CRE's confidence classification for the published statement or, for a withheld/excluded entry, the bounded safe limitation. CPE must not silently strengthen it. |
| Caveat references | C | CRE | Required when material caveats exist and required for a downgraded entry to retain its explicit bounded limitations. |
| Contradiction references | C | CRE | Required when CRE records a relevant unresolved conflict. |
| Unknown / missing-evidence references | C | CRE | Required when absence or incompleteness limits the statement. |
| Live-verification requirement | C | CRE | Required when an irreversible or consequential use must be checked in live state or a trusted preview before action. |
| Publication decision | R | CRE | States whether the entry is publishable for planning, downgraded, withheld, or excluded. A downgraded entry remains publishable for planning only with explicit bounded limitations; it is not a withholding or exclusion decision. |
| Withholding / exclusion stub | C | CRE | Required when Publication decision is withheld or excluded. It must preserve the entry identifier, entry category, publication decision, bounded reason, and any safe caveat or limitation needed to explain why the entry cannot be used. It must not expose private evidence, raw storage, credentials, or unpublished material. |

### 4.3 Prohibited Knowledge Release content

A CRE Knowledge Release must not contain:

- player objectives, preferences, protected assets, risk tolerance, or a selected colony plan;
- CPE-generated candidate layout, build order, or recommendation language presented as CRE fact;
- raw private evidence storage location, database credentials, or unpublished source content as a required consumer dependency;
- an implicit resolution of a contradiction or unknown merely because CPE would prefer a decisive answer.

## 5. CRE Observed Colony-State Snapshot — field detail

**Owner:** CRE  
**Purpose:** Publish a timestamped, evidence-linked snapshot of observed or explicitly modelled colony context.

A snapshot may contain observed, previewed, predicted, proposed, or completed state-bearing items, but each state-bearing item must carry its own state classification. A proposed Snapshot item is CRE-recorded colony context from an identified evidence source; it is not a CPE candidate action, CPE design intent, selected plan, or player commitment. A snapshot may also contain a limitation-only Snapshot stub when CRE cannot publish a state-bearing item. A snapshot must never make an entire system appear observed simply because some items are observed. A CPE candidate action or design intent is recorded separately in a Plan Result, not as a Snapshot item.

### 5.1 Snapshot-level fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Snapshot identifier | R | CRE | Stable identity for the state snapshot. |
| Knowledge Release pin | R | CRE | Exact CRE Knowledge Release used to interpret state labels, facility types, mechanics, or caveats. |
| Snapshot capture time | R | CRE | When the snapshot was assembled or captured. |
| Observation / model source time | C | CRE | Required when source evidence has a distinct capture time or when the snapshot contains modelled projection. |
| Subject scope | R | CRE | Identifies the system, bodies, facilities, links, or other bounded context covered. |
| Snapshot-item set | R | CRE | One or more separately identified state-bearing items and/or limitation-only Snapshot stubs. |
| Overall limitation statement | C | CRE | Required when the snapshot is materially incomplete, stale, partial, mixed-state, or dependent on unverified interpretation. |
| Snapshot supersession reference | C | CRE | Required if a newer snapshot supersedes it or if it has been withdrawn. |

### 5.2 Snapshot-item fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Item identifier | R | CRE | Stable item-level identity within the snapshot scope. |
| Entity identity | R | CRE | Identifies the body, orbital, facility, market link, economy snapshot, service, or other declared entity. |
| Entity category | R | CRE | Distinguishes physical body, orbital capacity, facility, station, market link, economy state, material observation, or another declared category. |
| Primary state classification | C | CRE | Required for a state-bearing Snapshot item that CRE can publish for planning use. It must be exactly one of the Stage 6C state classifications in Section 8. A limitation-only Snapshot stub must not carry a Section 8 primary state classification. |
| State-value content | C | CRE | Required for a state-bearing Snapshot item that CRE can publish for planning use. It is the fact, preview, projection, proposal, or completion record being stated, and its meaning must match the primary state classification. It is not required for a limitation-only Snapshot stub. |
| Evidence/model basis | C | CRE | Required for a state-bearing Snapshot item that CRE can publish for planning use. It is the provenance reference or named model/preview basis for that item. It is not required for a limitation-only Snapshot stub. |
| Limitation-only Snapshot stub | C | CRE | Required when CRE cannot publish the state or evidence basis for an item, or when the item is Unknown, Missing, Withheld, or Out of scope rather than state-bearing. It must preserve entity identity, entity category, the applicable Section 9 limitation state, bounded reason, and any safe caveat needed to explain why the item cannot be used. It must not expose withheld state value, private evidence, raw storage, credentials, or unpublished material. |
| Evidence capture / model time | C | CRE | Required when it differs materially from the snapshot capture time. |
| Body capacity / slot context | C | CRE | Required when the item concerns buildability, capacity, or placement. It must not be inferred solely from a facility proposal. |
| Realised facility state | C | CRE | Required when a facility is present, complete, under construction, demolished, or otherwise observed. |
| Facility class | C | CRE | Required when a facility is named; must remain distinct from station type and economy state. |
| Station type | C | CRE | Required when a station class is known. It must not be treated as final inherited economy. |
| Economy state | C | CRE | Required when known or modelled. When its primary classification differs from the facility, station, or other entity item that mentions it, it must be represented as a separate identified Snapshot item or a referenced Snapshot item with its own primary classification and caveats. It must not introduce a second primary classification into the entity item. |
| Market-link relationship | C | CRE | Required when a link is being asserted. Its evidence strength and state class must be visible. |
| Contextual planning role | O | CRE | A non-canonical explanatory role may be included only when clearly marked contextual; it must not become a universal mechanic. |
| Item caveats / uncertainty | C | CRE | Required when any applicable Section 9 limitation affects the item: unknown, missing, contradictory, stale, incomplete, unsupported, withheld, out of scope, or pending live verification. |
| Verification status | C | CRE | Required when a claimed outcome is not independently verified. |

### 5.3 Prohibited Snapshot content

A state snapshot must not contain:

- player objective ordering, subjective preference, risk tolerance, protected-asset policy, or a selected plan;
- a CPE decision rendered as though it were observed CRE state;
- an unqualified inference that a completed facility caused a predicted economy or commodity outcome;
- a silent substitution of a preview or prediction for an observed fact;
- a CPE candidate action or design intent recorded as though it were a CRE Snapshot item.

## 6. CPE Planning Request — field detail

**Owner:** CPE  
**Purpose:** Capture the player-specific decision problem while pinning the CRE knowledge and observed-state inputs used to frame it.

### 6.1 Request-level fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Request identifier | R | CPE | Stable identity for the planning request. |
| Request creation time | R | CPE | When the requester or CPE created the planning context. |
| CRE Knowledge Release pin | R | CPE reference to CRE | Exact compatible CRE Knowledge Release being used. A vague reference to a branch or latest state is insufficient. |
| CRE Observed Colony-State Snapshot pin | C | CPE reference to CRE | Required only when an eligible Snapshot exists and is used. Where no eligible Snapshot exists, the pin must be explicitly absent, not fabricated, substituted, or replaced by a placeholder. In that case, Request limitations must state the absence and bounded limitation. |
| Planning scope | R | CPE | What the plan is attempting to decide or sequence. |
| Objectives / priorities | R | CPE | Player-declared desired outcomes. They are not CRE facts and must preserve priority ordering or explicit equal treatment. |
| Hard constraints | R | CPE | Non-negotiable limits. An empty set must be explicit rather than implicit. |
| Protected assets / prohibited actions | C | CPE | Required when any facility, body, service, investment, or action is explicitly protected or prohibited. |
| Preferences | O | CPE | Soft desires that may be traded off. They must not be silently promoted to hard constraints. |
| Risk tolerance / uncertainty policy | R | CPE | States whether the requester permits conditional options, requires live validation, or prefers withholding where evidence is weak. |
| Declared programme requirements | O | CPE | Optional named requirements used to assess capacity or coverage; must distinguish owner intent from CRE evidence. |
| Assumptions supplied by the requester | O | CPE | May be recorded, but must not be relabelled as observed fact without CRE support. |
| Request limitations | C | CPE | Required when inputs, scope, or required evidence are missing or incompatible. |

### 6.2 Prohibited Planning Request content

A Planning Request must not:

- modify or restate a CRE fact with stronger confidence;
- carry raw CRE internal storage handles, private credentials, or unpublished evidence as an input dependency;
- label a preference as a physical capacity, market outcome, mechanic, or live-game fact;
- contain a hidden selected plan presented as an objective.

## 7. CPE Plan Result — field detail

**Owner:** CPE  
**Purpose:** Provide bounded plan-specific decision support while preserving CRE inputs, uncertainty, and the distinction between plans and observed state.

### 7.1 Result-level fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Result identifier | R | CPE | Stable identity for the plan result. |
| Result creation time | R | CPE | When the result was produced. |
| Planning Request pin | R | CPE | Exact request from which the plan result derives. |
| CRE Knowledge Release pin | R | CPE reference to CRE | Must match the request or record a Section 11.2 permitted update, including the exact updated pin and reason. |
| CRE State Snapshot pin | C | CPE reference to CRE | Required only when the Planning Request pins a Snapshot. When present, it must match the request or record a Section 11.2 permitted update, including the exact updated pin and reason. When the Request has no Snapshot pin, the Result pin must remain explicitly absent and carry forward the bounded limitation. |
| Result disposition | R | Derived CPE | Distinguishes candidate plan set, conditional plan set, withheld conclusion, or non-assessable outcome. A result must not pretend a candidate exists when evidence cannot support one. |
| Candidate-plan set | C | Derived CPE | Required whenever Result disposition includes a candidate plan set or a conditional plan set. Each conditional alternative must carry the same candidate-plan detail needed for review: proposed actions, applicable expected effects, supporting inputs, trade-offs, caveats, and validation gates. |
| Constraint-outcome set | R | Derived CPE | States each material hard constraint as satisfied, unsatisfied, conditional, or not assessable. |
| Trade-off set | C | Derived CPE | Required when candidate plans differ materially or an objective is compromised. |
| Confidence and limitations | R | Derived CPE | Must identify plan-level confidence, caveats, contradictions, unknowns, and limitations. Plan-level confidence must not exceed what any material CRE confidence limitation or material Section 9 limitation supports, including unknown, missing, contradictory, stale, incomplete, unsupported, withheld, out of scope, and pending live verification. Where material inputs differ, the result must state the limiting qualification rather than mask it with an aggregate summary. |
| Required validation steps | C | Derived CPE | Required when an irreversible or consequential action depends on an unverified input, model, or mechanic. |
| Input-change sensitivity | C | Derived CPE | Required when a change in a pinned input, assumption, or verification result would materially alter the result. A permitted CRE input update must record its resulting sensitivity, limitation, or validation gate where applicable. |
| Presentation hints | O | Presentation only | Later display guidance may be included, but must not alter the plan's authoritative reasoning or data. |

### 7.2 Candidate-plan fields

| Logical field | Presence | Owner | Meaning and rule |
|---|---:|---|---|
| Candidate identifier | R | Derived CPE | Stable identity for a specific plan alternative. |
| Candidate role / intent | R | Derived CPE | States why the candidate exists relative to the request objective. It is not a CRE mechanic. |
| Proposed actions | R | Derived CPE | Facility choices, sequencing, preservation, deferral, validation, or other plan actions. Proposed here is a CPE action/design-intent classification. It is distinct from an evidence-linked CRE Snapshot item classified Proposed under Section 8. Every irreversible action must carry an applicable evidence/validation basis. |
| Sequence / dependency order | C | Derived CPE | Required where order changes buildability, risk, verification, or expected effect. |
| Expected effects | C | Derived CPE | Required when claimed. Each expected effect must carry one primary Section 8 classification. “Observed carry-forward” is an Observed effect repeated unchanged from a pinned Snapshot. “Conditional” is not a sixth state; it must be expressed as a Predicted effect whose named assumptions, uncertainty, or validation gate state the condition. A proposed action remains Proposed rather than being relabelled as an effect. No expected effect may be stated as a guaranteed outcome. |
| Supporting input references | R | Derived CPE | Links each material candidate claim to its relevant CPE Planning Request inputs. CRE Knowledge Release entries and/or Snapshot items are required where those CRE inputs exist and are material. A request-only conclusion must not invent CRE, Snapshot, or hard-constraint references. |
| Trade-offs | C | Derived CPE | Required where the candidate sacrifices or defers a stated objective, preference, coverage, time, or risk posture. |
| Caveats / uncertainty | R | Derived CPE | Must retain all material CRE and CPE limitations relevant to this candidate. |
| Validation gate | C | Derived CPE | Required before irreversible action when material evidence is stale, incomplete, contradictory, preview-only, or pending live verification. |

### 7.3 Prohibited Plan Result content

A Plan Result must not:

- claim a plan is an observed colony state;
- claim that CPE changed a CRE mechanic, confidence, source record, or contradiction decision;
- present a station class, facility type, or role as a guaranteed inherited economy or material outcome without supporting state and caveat information;
- silently discard a hard constraint, unknown, contradiction, or required validation step;
- represent a recommendation as automatic selection or final player choice.

## 8. State-classification semantics

Each state-bearing Snapshot item and each Plan Result expected effect must use one primary classification. Snapshot items may use only **Observed**, **Previewed**, **Predicted**, **Proposed**, or **Completed**. Plan Result expected effects may use only **Observed**, **Previewed**, **Predicted**, or **Completed**. In a Snapshot, **Proposed** is an evidence-linked CRE record that an identified source states a future colony context or state is proposed; it is not a CPE candidate action, CPE design intent, selected plan, player commitment, observed fact, or guaranteed outcome. In CPE Plan Result action/design-intent content, **Proposed** remains a distinct CPE classification defined below. A limitation-only Snapshot stub carries a Section 9 limitation rather than a primary state classification; it must not use a Section 8 classification. **Unknown** is a Section 9 limitation state, not a replacement primary state classification. The exact encoding is not selected here.

| State classification | Meaning | Must not be interpreted as |
|---|---|---|
| **Observed** | A fact recorded from an identified evidence source at an identified or bounded capture time. | A universal mechanic, permanent state, or causal explanation not separately supported. |
| **Previewed** | A result displayed by an identified trusted preview, construction interface, or stated preview method before the action is completed. | A completed build, a guaranteed live result, or proof that a previewed effect persists after later changes. |
| **Predicted** | A modelled expectation produced from named assumptions, a stated method, or a known simulation. | An observed in-game result or a guarantee. |
| **Proposed** | An evidence-linked CRE record that an identified source states a future colony context or state is proposed. | A CPE candidate action, CPE design intent, selected plan, player commitment, observed fact, completed action, or guaranteed outcome. |
| **Completed** | A build, action, or milestone recorded as finished by identified evidence. | Verification that the intended economic, market, service, or material effect occurred. |

A facility may be **Completed** while its expected consequence remains **Unknown**, **Predicted**, or **Pending live verification**. A later outcome observation must be represented separately rather than implied by completion.

For CPE Plan Result action/design-intent content only:

| Action classification | Meaning | Must not be interpreted as |
|---|---|---|
| **Proposed** | A candidate plan action or design intent not yet verified as built or effective. | Existing facility state, an evidence-linked CRE Snapshot proposed-state item, an expected effect, player commitment, or research fact. |

## 9. Uncertainty, withholding, and validation semantics

The following limitation states are preserved across all four objects when applicable.

| Limitation state | Meaning | Required downstream handling |
|---|---|---|
| **Unknown** | The value or effect is not established. | Do not infer a default. Surface the limitation or withhold the conclusion. |
| **Missing** | Needed information has not been supplied or located. | Identify what is missing and do not treat absence as negative evidence. |
| **Contradictory** | Relevant sources or observations conflict. | Preserve the conflict, identify the competing basis, and avoid unilateral resolution. |
| **Stale** | Information may no longer represent the relevant current patch, world state, or observation time. | Display date/context and require re-check where material. |
| **Incomplete** | Some relevant scope is known but not fully covered. | State the bounded scope and do not claim total coverage. |
| **Unsupported** | No adequate evidence supports a proposed assertion. | Exclude, downgrade, or mark non-assessable. |
| **Withheld** | CRE or CPE intentionally does not publish a conclusion for stated reasons. | Respect the withholding; do not reconstruct it from private inputs. |
| **Out of scope** | The question cannot be answered within the object's declared scope. | State the boundary and avoid implication. |
| **Pending live verification** | A consequential claim requires in-game or other specified validation before reliance. | Carry a validation gate into the Plan Result. |

A limitation-only Snapshot stub preserves the applicable Section 9 limitation and its bounded reason instead of presenting a state-bearing item. It does not convert an Unknown, Missing, Withheld, or Out of scope limitation into a Section 8 primary state classification.

A plan result may use these states to produce conditional alternatives or a non-assessable result. It must not silently convert them to `false`, `zero`, `safe`, `available`, `resolved`, or `not relevant`.

## 10. Provenance and caveat propagation

### 10.1 Minimum propagation chain

For every material CPE conclusion, a reader must be able to trace:

```text
CPE Plan Result assertion
→ candidate-plan / constraint / trade-off item
→ Planning Request objective, hard constraint, preference, risk-tolerance policy, declared programme requirement, or stated assumption
→ pinned CRE Knowledge Release entry and/or State Snapshot item
→ CRE provenance, caveat, contradiction, unknown, and validation basis
```

If a material conclusion depends only on a planning input and not on a CRE factual basis, the trace must stop at the relevant Planning Request input and must not pretend a CRE factual basis exists.

### 10.2 Required references by assertion type

| CPE assertion type | Must retain |
|---|---|
| Uses a mechanic or guardrail | CRE Knowledge Release entry identifier, confidence, applicability conditions, and caveats. |
| Uses a physical or facility-state fact | CRE State Snapshot item identifier, state classification, evidence/model basis, and capture time/context. |
| Predicts an effect | Named input references, state classification `Predicted`, assumptions, and a validation gate where consequential. |
| Proposes an action | Request objective, hard constraint, preference, risk-tolerance policy, declared programme requirement, or stated assumption linkage; supporting CRE inputs when they exist; trade-offs; and irreversible-action validation requirements. |
| Withholds an answer | Every applicable limitation basis: unknown, missing, contradictory, stale, incomplete, unsupported, withheld, out of scope, and pending live verification. |

### 10.3 Caveat-preservation rule

CPE may add plan-specific caveats. It must not remove a material CRE caveat, contradiction, confidence limitation, or verification requirement merely because it makes a preferred plan less decisive.

## 11. Identity, release pinning, and compatibility detail

### 11.1 Stable identifiers

- Object identifiers must remain stable for a given published object instance.
- A new publication that materially changes meaning must receive a new object or release identity, not silently overwrite historical meaning.
- Identifiers may be opaque. They must not expose private paths, credentials, or implementation-specific database keys as the consumer contract.

### 11.2 Release pinning

A CPE Planning Request must pin the exact Knowledge Release used. It must pin the exact State Snapshot only when an eligible Snapshot exists and is used. A CPE Plan Result must pin the exact Knowledge Release used and must pin the exact State Snapshot only when the Request pins one. Every present pin must include a stable identifier plus immutable revision/source information when available.

A CPE Plan Result may use a newer compatible CRE Knowledge Release or State Snapshot than its Planning Request only where the update does not materially alter the request's planning scope, objective, hard constraint, protected asset, preference, risk-tolerance policy, declared programme requirement or its capacity/coverage implications, stated assumption, applicable CRE semantic meaning, or the material Snapshot state items and limitations that frame those matters. A material change to any of those matters, including to how a declared programme requirement is evaluated or to relevant facility presence, protected assets, body capacity, economy state, market-link state, or other Snapshot facts or limitations bearing on the planning problem, requires a new Planning Request.

For a permitted update, the Plan Result must record the exact updated pin, the update reason, Input-change sensitivity, and every resulting limitation or validation gate. This is field-level governance only; it does not create or select an implementation, compatibility engine, or update mechanism.

A mutable label such as `main`, `latest`, `current`, or a repository name by itself is insufficient for a reproducible planning input.

When an immutable revision does not exist, the object must state that absence and why. The consumer must treat reproducibility as limited rather than pretending the input is pinned.

When no eligible Snapshot exists, the Request and Result must keep the Snapshot pin explicitly absent, state the bounded limitation, and must not fabricate a substitute identifier or placeholder.

### 11.3 Supersession and withdrawal

A later release or snapshot may supersede an earlier one. Supersession does not automatically mean the older content was false; it means consumers must see the newer status and reason where available.

A withdrawn or withheld item must remain identifiable enough to explain why a conclusion is no longer supported, without exposing private evidence or credentials.

### 11.4 Compatibility behaviour

- A consumer must declare supported contract major version(s).
- A major-version mismatch must result in a visible unsupported/non-assessable condition unless a separately published compatibility mapping exists.
- A minor extension may be ignored only when the release declares it optional and doing so does not drop a material caveat, constraint, or provenance requirement.
- A patch correction may clarify or repair a release, but must not silently change a required semantic meaning.

No parser, validator, compatibility shim, or semantic-version tooling is created or selected by this documentation.

## 12. Documentation-only illustrative examples

These are conceptual examples, not payloads, schemas, fixtures, or actual game facts.

### 12.1 Example: a qualified CRE Knowledge Release entry

| Field | Illustrative value |
|---|---|
| Entry category | Planner guardrail |
| Planner-safe statement | “Do not represent a station class as the final inherited economy without a separate supported economy-state basis.” |
| Confidence | Qualified / evidence-limited |
| Caveat | “Applies only within the stated evidence and patch context.” |
| Planning effect | CPE may require a snapshot or validation step rather than claim a guaranteed outcome. |

### 12.2 Example: mixed state in a Snapshot

| Snapshot item | State classification | Interpretation |
|---|---|---|
| Existing facility record | Observed | A facility is recorded as present by identified evidence. |
| Candidate construction preview | Previewed | The preview may guide a conditional plan, but does not establish a completed outcome. |
| Expected post-change material coverage | Predicted | A modelled effect under named assumptions, requiring a validation gate if consequential. |
| Evidence-linked colony proposal record | Proposed | An identified source records a proposed future colony state; it is not a CPE candidate action or player commitment. |
| Finished construction milestone | Completed | A build may be done, but its market/economy consequence still needs separate observation. |

A CPE candidate build action is recorded separately in a CPE Plan Result as `Proposed` action/design-intent content. That is distinct from an evidence-linked CRE Snapshot item whose source records a proposed colony state.

### 12.3 Example: a CPE Plan Result validation gate

| Field | Illustrative value |
|---|---|
| Candidate action | Preserve a protected facility and defer an irreversible replacement. |
| Supporting inputs | Pinned state snapshot, planner guardrail, hard constraint. |
| Plan condition | Proceed only after the relevant live preview or observed-state check is recorded. |
| Plan status | Conditional candidate, not automatic recommendation. |
| Uncertainty carried forward | Effect remains pending verification. |

## 13. Documentation validation checklists

These are review checklists, not executable validators.

### 13.1 CRE Knowledge Release checklist

- Does every published entry have a stable identifier, category, publication decision, and—when publishable for planning, including a downgraded entry—a bounded statement, provenance basis, confidence, and explicit relevant limitation?
- When an entry is withheld or excluded, does it retain a safe stub with its bounded reason and any safe caveat or limitation, without exposing private evidence or unpublished material?
- Are caveats, contradictions, unknowns, and live-verification requirements carried where applicable?
- Does the release avoid embedding player-specific objective or plan content?
- Is the release pin reproducible or explicitly marked as not fully reproducible?

### 13.2 CRE State Snapshot checklist

- Does each state-bearing item have exactly one primary state classification?
- Does every limitation-only Snapshot stub preserve entity identity, entity category, the applicable Section 9 limitation state, a bounded reason, and any safe caveat without exposing withheld state or private evidence; and does it avoid a Section 8 primary state classification?
- Are facility class, station type, economy state, market links, body capacity, and planning role kept distinct where present?
- When an economy state has a different primary classification from the facility, station, or other entity item that mentions it, is it represented as a separate or referenced Snapshot item with its own primary classification?
- Are every applicable Section 9 item limitation, including Unknown, Missing, Contradictory, Stale, Incomplete, Unsupported, Withheld, Out of scope, and Pending live verification, carried explicitly?
- Is completed construction kept distinct from verified outcome?
- Are mixed observed/previewed/predicted/proposed/completed items separated rather than collapsed?
- Are CPE candidate actions kept out of the Snapshot and recorded separately in a Plan Result?

### 13.3 CPE Planning Request checklist

- Is the exact CRE release pin present?
- Is the Snapshot pin present only when an eligible Snapshot exists and is used, and otherwise explicitly absent with a bounded limitation?
- Are player objectives, hard constraints, preferences, protected assets, and risk tolerance distinguished?
- Are user assumptions clearly marked as user-provided rather than observed CRE facts?
- Does a missing required input cause an explicit limitation rather than invented state?

### 13.4 CPE Plan Result checklist

- When Result disposition includes a candidate plan set or a conditional plan set, is the Candidate-plan set present and does each conditional alternative carry proposed actions, applicable expected effects, supporting inputs, trade-offs, caveats, and validation gates?
- Are every material candidate claim and trade-off traceable to the relevant request inputs and CRE inputs where they exist and are material, without inventing CRE, Snapshot, or hard-constraint references for a request-only conclusion?
- Are hard constraint outcomes explicit: satisfied, unsatisfied, conditional, or not assessable?
- Are caveats, contradictions, unknowns, and validation gates preserved?
- Does plan-level confidence remain bounded by every material CRE confidence limitation and Section 9 limitation, including unknown, missing, contradictory, stale, incomplete, unsupported, withheld, out of scope, and pending live verification?
- When withholding an answer, are all applicable limitation bases retained, including unknown, missing, contradictory, stale, incomplete, unsupported, withheld, out of scope, and pending live verification?
- Does an irreversible action that depends on materially stale, incomplete, contradictory, preview-only, or pending-live-verification evidence carry a validation gate?
- Where a Result uses a permitted updated CRE input, are the exact updated pin, reason, Input-change sensitivity, and each resulting limitation or validation gate recorded; and has a new Planning Request been used for a material change, including a material change to a declared programme requirement or its capacity/coverage evaluation or to material Snapshot facts or limitations that alter the planning problem?
- Do proposed actions trace to the relevant objective, hard constraint, preference, risk tolerance, declared programme requirement, or stated assumption, without inventing a CRE factual basis where none exists?
- Is the result clearly a plan-specific decision-support output rather than observed reality or automatic player choice?

## 14. Explicit non-goals

Stage 6C does not authorise:

- code, executable schema definitions, parsers, validators, fixtures, tests, UI, CI, packages, APIs, events, runtime messages, or deployment;
- CPE repository scaffolding or implementation;
- database creation, database access, shared storage, credentials, or private cross-repository access;
- external research, live-game work, source collection, data import, or changes to CRE evidence;
- moving, copying, deleting, renaming, splitting, or modifying CRE material;
- selection of JSON, YAML, SQL, HTTP, files, queues, packages, shared repositories, runtime, transport, storage, or integration architecture;
- scoring, ranking, automatic selection, planner algorithm design, recommendations, or product-behaviour changes.

## 15. Allowed durable output and review process

The only durable files permitted for Stage 6C are:

- `docs/ai/R1_STAGE6C_CRE_CPE_FIELD_CONTRACT_DETAIL_V1.md`
- `docs/ai/CURRENT_STAGE.md`

A documentation branch and pull request may contain only those files. Independent read-only review and separate owner acceptance are required before merge.

## 16. Completion and next safe action

A merged Stage 6C record would establish only field-level logical contract meaning. It would not authorise an implementation or technical architecture.

The next safe action after a future acceptance and merge is a separately authorised decision on whether to begin a narrow, documentation-only implementation-readiness assessment or to pause. No follow-on technical work is implied by this document.
