# CRE ↔ ED-Finder Confidence Vocabulary Reconciliation

**Status:** Design / reconciliation reference. Documentation-only — no code, no
schema, no runtime change is authorized by this document.

**Roadmap anchor:** `docs/ROADMAP.md` Foundation Sequence step 4 — *"CRE
integration: confidence vocabulary first, then source authority, then release
artifact consumption"* — and its Do-Next line: *"Reconcile the CRE and ed-finder
confidence vocabularies before consuming CRE source-authority or release
artifacts at runtime."* The roadmap states the vocabularies are **currently
incompatible and must be reconciled before any evidence-layer integration
begins**, and that CRE's model **will become canonical**. This document is that
reconciliation. It unblocks the gate; it does not perform the integration.

**Companion:** `source-priority.md` in this directory is ED-Finder's existing
source-authority hierarchy. CRE's `evidence/source_authority_register.md`
(SA-0001…SA-0010) and `ontology/confidence_model_register.md` (CM-0001…CM-0007)
are the canonical registers this document reconciles against.

---

## 1. Scope and non-goals

**In scope:** a canonical mapping between every confidence vocabulary ED-Finder
currently uses and CRE's confidence/source-authority model; a statement of the
target end-state; the translation contract that a future integration must honour.

**Explicit non-goals (boundaries preserved):**

- **No code or schema change.** ED-Finder's `mechanics/confidence.py`,
  observation enums, evidence-store fields, and ratings confidence floats are
  **not** modified by this document. The actual `confidence.py` redesign and any
  runtime translation layer are deferred until CRE integration is separately
  authorized (roadmap Foundation Sequence step 4/5).
- **No runtime CRE consumption.** CRE is not wired into ED-Finder at runtime and
  nothing here wires it in.
- **No mechanics changes.** This reconciles *confidence vocabulary*, not
  colonisation mechanics truth. Mechanics truth remains CRE's to define
  (`CLAUDE.md` three-repo boundary).
- **ED-Finder does not author CRE's registers.** Where ED-Finder surfaces a
  concept CRE's registers do not cover, it is recorded in §9 as *feedback to CRE
  governance*, not resolved by editing CRE from this repo.
- **The existing "confidence must not feed scoring" conservatism is retained.**
  `ComparisonConfidenceImpact` and observed-fact confidence remain UI/advisory
  and must not be plumbed into scoring, CP, economy, buildability, or optimiser
  ranking — consistent with CRE CM-0006A (operational confidence ≠ research
  confidence) and ED-Finder's Stage 6C rule.

---

## 2. The real gap: ED-Finder has *seven* fragmented confidence surfaces

The incompatibility is not "two different word-lists for one axis." ED-Finder
has grown **seven independent confidence surfaces**, on **three-plus
incompatible scales**, none mapped to each other, let alone to CRE:

| # | Vocabulary | Location | Scale / values | What it describes | CRE layer (§6) |
|--:|---|---|---|---|---|
| 1 | `ConfidenceLevel` | `mechanics/confidence.py` | 7-value string enum: `observed`, `verified`, `community_observed`, `inferred`, `estimated`, `speculative`, `unknown` | Per-area quality of **simulation/planner output** (slots, topology, economy_stack, services…) | Projected-operational |
| 2 | facility `data_confidence` | `domain/facilities.py` | string, defaults `'estimated'`; used as a two-state gate (`'estimated'` vs known) | Certainty of a **facility-catalogue** template (DaftMav workbook) | Source / catalogue |
| 3 | archetype `data_confidence` | `build_archetype_scores.py` → `models.py` | numeric float `0.0–1.0` (default `0.85`) | **Body-data completeness** feeding a rating | Projected-operational |
| 4 | `archetype_confidence` | `routers/simulation.py:476` | numeric float `0.0–1.0` | Confidence in the **archetype match** for a rating | Projected-operational |
| 5 | `ObservedConfidence` | `observations/models.py` | 3-value enum: `low`, `medium`, `high` | Confidence a user attaches to a **submitted observed fact** | Observations |
| 6 | `ComparisonConfidence` (+ `ComparisonConfidenceImpact`, `ComparisonOverallStatus`) | `observations/comparison_models.py` | `low`/`medium`/`high`/`unknown`; impact `none`/`strengthened`/`weakened`/`mixed`/`insufficient_evidence` | Confidence in an **observation-vs-prediction** comparison, and how it moves trust | Evidence reconciliation |
| 7 | evidence-store `confidence` | `evidence_store/models.py` | free-form `str` | Confidence stamped on an **adopted evidence** record | Observations / evidence |

Three structural problems follow:

- **Fragmentation.** Six vocabularies, three-plus scales (7-value enum,
  low/med/high, binary `estimated` gate, `0–1` float, free string). "High" in
  `ObservedConfidence` and "verified" in `ConfidenceLevel` and `0.85` in
  archetype confidence are not comparable, and nothing defines a mapping.
- **Axis conflation.** `ConfidenceLevel` mixes *who said it* (`verified`,
  `community_observed` — a **source-authority** claim) with *how sure we are*
  (`inferred`, `estimated`, `speculative` — a **confidence-degree** claim). CRE
  keeps these as separate concerns (SA-register vs CM-register).
- **No layer separation and no dynamics.** CRE requires confidence to be tracked
  separately per interpretation layer (CM-0001, CM-0006A) and to *move* —
  contradictions downgrade (CM-0002), patches decay (CM-0003), negative evidence
  counts against (CM-0005). Every ED-Finder vocabulary above is static and
  layer-blind.

This fragmentation is exactly the failure CRE's model is built to prevent, which
is why CRE's model is the right canonical target rather than a seventh
ED-Finder invention.

---

## 3. CRE's canonical model (summary)

Two governed registers, deliberately separate:

**Source Authority Register — SA-0001…SA-0010** classifies *source classes*:
official mechanics/patch notes are primary for intended rules (SA-0001);
community guides (Mega Guide, DaftMav, Raven references) are interpretation, not
canonical truth (SA-0002); live in-game evidence outranks secondary references
(SA-0003); raw source, parsed observation, inferred mechanics, and planner-safe
knowledge must stay separate layers (SA-0004); narrative evidence is allowed but
must be confidence-labelled (SA-0005); plus rules on identity collisions
(SA-0006), EDDN-as-transport (SA-0007), Inara (SA-0008), bulk dumps (SA-0009),
and absent artifacts (SA-0010).

**Confidence Model Register — CM-0001…CM-0007** defines a numeric model:

- **Six weighted components → a 0–100 score:** source authority 25, directness
  20, corroboration 20, specificity 15, freshness 10, exportability 10.
- **Four bands:** `85–100` High (may drive automation), `70–84` Usable with
  review, `50–69` Exploratory only, `<50` Weak / discovery-lead.
- **Layer separation:** confidence tracked separately for observations,
  experiments, mechanics, planner-knowledge, recommendations, and
  projected-operational data. High-confidence evidence ≠ high-confidence
  mechanics ≠ high-confidence recommendation.
- **Dynamics:** contradictions lower confidence (CM-0002); patch drift decays it
  (CM-0003); negative/failed evidence counts against it (CM-0005); recommendation
  confidence must reflect the weakest critical dependency, not a cosmetic
  top-level label (CM-0001A); operational confidence is distinct from research
  confidence (CM-0006A); community interpretation stays conditional (CM-0007).
- **Mechanic-level fields** each rule should eventually carry: `confidence_score`,
  `confidence_band`, `last_verified_version`, `last_verified_at`,
  `contradiction_count`, `corroborating_evidence_count`,
  `negative_evidence_count`, `patch_sensitivity`, `confidence_decay_state`.

---

## 4. Reconciliation principle

**Do not replace ED-Finder's vocabularies with a flat translation of CRE's
score.** The correct move is to *locate each ED-Finder vocabulary in CRE's layer
taxonomy first*, then map its values to (a) a CRE **source-authority class** and
(b) a CRE **confidence band**, keeping the two axes separate exactly as CRE does.

The single most important realignment: **ED-Finder's `ConfidenceLevel` is not a
competitor to CRE's evidence model — it is CRE's *projected-operational* layer
(CM-0006A).** It describes "is this predicted slot count / economy stack
reliable," which is operational-projection confidence, not research/evidence
confidence. Recognising this dissolves most of the apparent conflict: the two
models mostly describe *different layers*, and reconciliation means giving each
ED-Finder surface its correct CRE layer and a consistent band scale — not
forcing them onto one axis.

---

## 5. Target end-state

CRE's model canonical; ED-Finder's vocabularies become **derived projections**
of it, not independent sources of truth:

- Each confidence-bearing value in ED-Finder carries (or can be resolved to)
  three CRE-aligned attributes: a **source-authority class** (SA-*), a **0–100
  confidence score + band**, and a **layer**.
- The existing enums (`ConfidenceLevel`, `ObservedConfidence`,
  `ComparisonConfidence`) survive as **thin display projections** of the
  canonical band — e.g. a UI chip — but stop being the system of record for
  "how much do we trust this."
- CRE's dynamics (decay, contradiction, negative evidence) become expressible;
  ED-Finder is not required to *compute* them until it consumes CRE, but its
  schema/response shapes must not *preclude* them.

None of that is built here. §10 states what remains deferred.

---

## 6. Layer map — where each ED-Finder surface belongs in CRE

| ED-Finder surface | CRE layer | Rationale |
|---|---|---|
| `ConfidenceLevel` (sim output) | **Projected-operational** (CM-0006A) | Describes reliability of a *generated* plan projection, not raw evidence. |
| facility `data_confidence` | **Source / catalogue** (SA-0002) | DaftMav catalogue = community interpretation; `estimated` = uncorroborated catalogue entry. |
| archetype `data_confidence` (body-data completeness) | **Projected-operational** | Reflects input-data completeness for a generated rating. |
| `archetype_confidence` (match) | **Projected-operational** | Confidence in a generated classification, not evidence. |
| `ObservedConfidence` | **Observations** (SA-0003 / SA-0005) | User-submitted direct or narrative observation. |
| `ComparisonConfidence` / `…Impact` | **Evidence reconciliation** (CM-0002/CM-0005) | Precisely CRE's "contradictions/negative evidence move trust" dynamic — but must stay advisory. |
| evidence-store `confidence` | **Observations / evidence** (SA-0004) | Adopted evidence record; must remain layer-separated from mechanics. |

---

## 7. Value crosswalks

Provisional mappings to be firmed up during integration. Bands are CRE CM bands;
SA references are the dominant source class, not the only one.

### 7.1 `ConfidenceLevel` (projected-operational)

| ED-Finder | Confidence-degree reading | CRE band (typical) | Source-authority note |
|---|---|---|---|
| `verified` | corroborated / direct | High (85–100) | resolves to SA-0003 live evidence when backed by imported Architect data |
| `observed` | directly observed | High–Usable (70–100) | SA-0003; band depends on corroboration |
| `community_observed` | community-sourced, conditional | Usable–Exploratory (50–84) | **SA-0002** — carries source authority, *not* a degree; CM-0007 keeps it conditional |
| `inferred` | derived, indirect | Exploratory (50–69) | derived-mechanics layer (SA-0004 separation) |
| `estimated` | low directness/specificity | Weak (<50) | discovery-lead |
| `speculative` | disputed / bugged | Weak (<50), decay-flagged | CM-0003 patch-sensitivity applies |
| `unknown` | no assessment | *not a band* — "insufficient evidence" | keep unknown unknown (source-priority rule 5) |

Note the axis-conflation call-out: `community_observed` and `verified` encode a
**source class**, the others encode a **degree**. In the target model these split
into the SA axis and the band axis.

### 7.2 low / medium / high (`ObservedConfidence`, `ComparisonConfidence`)

| ED-Finder | CRE band |
|---|---|
| `high` | High (85–100) |
| `medium` | Usable / Exploratory (50–84) |
| `low` | Weak (<50) |
| `unknown` (comparison only) | insufficient evidence |

### 7.3 facility `data_confidence` (source / catalogue)

| ED-Finder | CRE reading |
|---|---|
| known (non-`estimated`) | corroborated catalogue entry — Usable+ under SA-0002 |
| `estimated` | uncorroborated catalogue entry — Exploratory/Weak; the optimiser already gates on this (`allow_estimated_data`), which is the correct SA-0002/CM-0007 conservatism |

### 7.4 numeric floats (archetype `data_confidence`, `archetype_confidence`)

Already `0.0–1.0`. Map to CRE bands by ×100: `≥0.85` High, `0.70–0.84` Usable,
`0.50–0.69` Exploratory, `<0.50` Weak. **Caveat:** these floats are *not* CRE's
six-component score — they measure input completeness / match strength, not
source authority + directness + corroboration + specificity + freshness +
exportability. They may sit in the same band space but must be labelled
projected-operational, never presented as evidence confidence (CM-0006A).

### 7.5 `ComparisonConfidenceImpact` → CRE dynamics

| ED-Finder impact | CRE dynamic |
|---|---|
| `strengthened` | corroboration ↑ (CM component) |
| `weakened` | contradiction / negative evidence ↓ (CM-0002, CM-0005) |
| `mixed` | net-neutral with recorded contradiction |
| `insufficient_evidence` | below Weak band; discovery-lead |
| `none` | no movement |

This vocabulary already expresses CRE's trust-movement dynamics — it is the
closest existing ED-Finder surface to CRE's model — but per Stage 6C it remains a
UI hint and **must not** feed scoring. That conservatism is retained.

---

## 8. Translation contract (for the future integration, not built here)

When CRE-to-ED-Finder integration is authorized, the translation layer must:

1. **Preserve both axes.** Never collapse source-authority (SA) into a single
   confidence degree, or vice-versa.
2. **Tag the layer.** Every translated value carries its CRE layer; operational
   and evidence confidence are never silently equated (CM-0006A).
3. **Keep unknown unknown.** Absent CRE data maps to "insufficient evidence,"
   never to a Weak-but-present band or to `0` (source-priority rule 5, SA-0010).
4. **One-way canonicity.** CRE is the source of truth; ED-Finder projects. A
   round-trip must not let an ED-Finder display projection overwrite a CRE score.
5. **No automation without band.** Only CRE `High` (85–100) may drive automation;
   ED-Finder must not treat a projected-operational float ≥0.85 as if it were an
   evidence-High that clears CRE's automation bar.
6. **Respect the scoring firewall.** Translated confidence remains advisory to
   scoring/CP/economy/buildability/optimiser until a roadmap stage explicitly
   authorizes otherwise.

---

## 9. Gaps to raise with CRE governance (feedback, not edits)

Recorded here as candidate feedback; **not** applied to CRE from this repo:

- **Projected-operational sub-vocabulary.** ED-Finder's richest real-world need
  is operational confidence (is *this generated plan* reliable). CRE names the
  layer (CM-0006A) but does not yet give it a value vocabulary. ED-Finder's
  `ConfidenceLevel` is candidate prior art.
- **Analyst low/med/high shorthand.** ED-Finder and human reviewers use
  low/med/high heavily. Worth an explicit CRE band-alias so the shorthand is
  governed rather than ad-hoc.
- **Catalogue `estimated` gate.** The binary "estimated vs known" catalogue gate
  is a useful, cheap SA-0002/CM-0007 signal; consider a named CRE treatment.

---

## 10. What this unblocks, and what remains deferred

**Unblocked by this document:** the roadmap gate — the confidence vocabularies
are now reconciled on paper, so source-authority mapping (Foundation Sequence
step 4b) and eventual release-artifact consumption (step 4c) have a defined
translation target.

**Still deferred (require separate authorization):**

- The `mechanics/confidence.py` (and sibling enums) redesign to carry the
  canonical `{source_authority, confidence_score, band, layer}` shape with the
  enums as projections — an implementation plan, not a doc.
- Any runtime CRE consumption / translation-layer code.
- Any change that lets translated confidence influence scoring, CP, economy,
  buildability, validation, or optimiser ranking.

Those follow the roadmap Foundation Sequence (step 4 → step 5) and this repo's
migration/plan-change discipline; none are started here.
