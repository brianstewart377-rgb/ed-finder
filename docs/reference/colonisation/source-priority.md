# Colonisation Source Priority

Use this hierarchy for ED-Finder colonisation mechanics, planner warnings,
picker validity, CP logic, strong/weak links, dependencies, economy influence,
and source-sensitive UI copy.

## Authority Hierarchy

| Priority | Source | Authority and use |
|---:|---|---|
| 1 | Elite Dangerous Colonization Mega Guide | Primary mechanics authority. If another source conflicts, prefer the Mega Guide unless newer verified evidence is explicitly documented. |
| 2 | User empirical findings and spreadsheet analysis | High-value evidence, especially surface-slot prediction and anomaly analysis. Prediction evidence is not confirmed truth unless backed by observed/imported Architect evidence. |
| 3 | DaftMav Colonization Construction spreadsheet | Catalogue, construction, support, comparison, and structure-table reference. Use for facility/catalogue enrichment where redistribution and versioning are safe. |
| 4 | OASIS Guide for Bootstrapping a Bubble | Planning workflow support, bootstrapping strategy, and operator/player workflow context. Not higher authority than the Mega Guide for mechanics conflicts. |
| 5 | Fandom, Frontier forum posts/PDFs, AetherWave PDFs, diagrams, and infographics | Secondary clarification, visual explanation, and cross-checking. Use to clarify or document conflicts, not to silently override primary mechanics authority. |
| 6 | RavenColonial screenshots/tooling | UI/tooling inspiration and possible future handoff target only. Not mechanics authority for ED-Finder scoring, CP, economy, service, buildability, or optimiser ranking. |
| 7 | Future external data sources: EDMC, EDDiscovery, EDSM, EDDN, Spansh, RavenColonial plugin data, imported snapshots | Evidence/source data with source, timestamp, freshness, confidence, and review controls. Not automatic mechanics truth. |

## Conflict Rules

When sources conflict:

1. Prefer the Elite Dangerous Colonization Mega Guide.
2. Record the conflict explicitly in the relevant implementation, test, or doc.
3. Treat newer evidence as a candidate update only when its source and
   verification path are documented.
4. Do not silently average, merge, or hide conflicting claims.
5. Keep unknown data unknown. Missing coordinates, distances, slot counts,
   rings, or body associations must not be coerced to zero or false.

## Planner Trust Rules

- Predicted surface slots are labelled prediction/evidence, not known or
  confirmed Architect truth.
- Existing infrastructure is not a Build Plan placement.
- Projected Suggested Build structures are ghost/projection-only until the user
  explicitly loads them.
- Observed/imported data is evidence first. It must not silently mutate Build
  Plans, Simulation Preview mechanics, scoring, CP, economy/service state,
  buildability, validation state, or optimiser ranking.
- Declared/inferred/observed roles remain guidance unless a future stage
  explicitly scopes mechanics behaviour.

## RavenColonial Boundary

RavenColonial can inform workflow observations such as readable body hierarchy,
local placement clarity, compact warnings, and handoff/export ideas. ED-Finder
must not copy RavenColonial source code, CSS, assets, icons, proprietary
implementation details, API keys, private plugin data, logistics workflow, or
mutating API behaviour.
