# Colonisation Source Inventory

This inventory records known colonisation reference sources and how future PRs
should cite or use them. It is deliberately conservative: if redistribution is
not explicitly safe, the source file is not committed here.

| Source name | Purpose | Authority level | File status | Redistribution/licensing status | Future PR citation/use |
|---|---|---|---|---|---|
| Elite Dangerous Colonization Mega Guide | Primary mechanics reference for colonisation rules, body rules, links, dependencies, CP/economy mechanics, and planner warning claims. | Primary mechanics authority | Not committed; external/attached/local-only source expected when used. | Not confirmed safe to redistribute in this repo. | Cite as "Elite Dangerous Colonization Mega Guide" with inspected version/date when available. Prefer it in source conflicts unless newer verified evidence is documented. |
| User empirical findings and spreadsheet analysis | Empirical evidence for prediction work, especially surface-slot prediction, anomalies, and validation rows. | High-value evidence; prediction evidence, not confirmed truth | Not committed unless anonymised/source-permitted fixtures are added later. | Unknown unless the user explicitly marks a fixture safe to commit. | Cite dataset/spreadsheet name, attachment/local status, row scope, and whether evidence is prediction-only or observed/imported truth. |
| DaftMav Colonization Construction spreadsheet | Facility catalogue, construction, comparison, support values, and structure table reference. | Catalogue/construction/support reference | Not committed; external/attached/local-only workbook expected when used. | Not confirmed safe to redistribute in this repo. | Cite workbook name/version/date and the exact sheet/column used. Do not import workbook facts silently into mechanics without tests and source notes. |
| OASIS Guide for Bootstrapping a Bubble | Planning workflow support, bootstrapping strategy, and player workflow context. | Planning workflow support | Not committed; external/attached/local-only source expected when used. | Not confirmed safe to redistribute in this repo. | Cite as supporting workflow context. Do not override Mega Guide mechanics claims without documented verification. |
| Fandom System Colonisation reference | Secondary clarification and cross-checking for system colonisation concepts. | Secondary clarification | Not committed; external source. | Not confirmed safe to redistribute in this repo. | Cite URL/title/date if used. Treat as secondary clarification only. |
| Frontier forum strong/weak link references | Secondary clarification for strong/weak link concepts and community explanations. | Secondary clarification | Not committed; external source. | Not confirmed safe to redistribute in this repo. | Cite forum thread/title/date if used. Prefer Mega Guide for mechanics conflicts. |
| AetherWave PDFs and diagrams | Secondary visual explanation, diagrams, and cross-checking. | Secondary clarification | Not committed; external/attached/local-only source expected when used. | Not confirmed safe to redistribute in this repo. | Cite file/title/date and keep diagrams as explanatory evidence, not automatic mechanics truth. |
| Construction prerequisite images, link diagrams, and infographics | Visual clarification of dependencies, links, and construction flow. | Secondary clarification | Not committed; external/attached/local-only source expected when used. | Not confirmed safe to redistribute in this repo. | Cite source/title/date. Recreate only repo-native explanatory diagrams when licensing is safe or when based on original ED-Finder analysis. |
| RavenColonial screenshots/tooling observations | UI/workflow inspiration, planning clarity comparison, and possible future handoff/export research. | UI/tooling inspiration only | Not committed here; existing ED-Finder docs may describe clean-room observations. | Screenshots/assets/source/API material are not confirmed safe to redistribute. | Cite as clean-room workflow observation only. Never use as mechanics authority or copy source/CSS/assets/icons/API behaviour. |
| EDMC, EDDiscovery, EDSM, EDDN, Spansh, RavenColonial plugin data, imported snapshots | Future evidence/source data for enrichment, observations, validation, and source coverage. | Evidence/source data, not automatic truth | Not committed as source authority; fixtures may be committed only when safe and anonymised. | Varies by source; verify before committing. | Track source, timestamp, freshness, confidence, import method, and review path. Keep data passive unless a future stage explicitly scopes mechanics changes. |

## Placeholder Policy

- Do not commit DOCX, PDF, XLSX, screenshot, extracted-frame, plugin, API,
  commander, or private-data files unless redistribution is explicitly safe.
- Use small anonymised fixtures only when they are permitted and necessary for
  tests or deterministic examples.
- If a future PR depends on a non-committed source file, state whether that file
  is attached to the PR/review, external, or local-only.
- If source files are later added here, update this inventory with file path,
  version/date, redistribution status, and citation instructions.
