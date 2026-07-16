# Evidence Store & Data Enrichment Blueprint

**Date:** 2026-07-15 | **Scope:** Current state audit + future enrichment roadmap
**Method:** 5 parallel agents (evidence architecture, colonisation mechanics, data sources/APIs, enrichment ideas, novel features)

---

## Part 1: Current Evidence Architecture

### 1.1 What We Have Now

**Evidence Store (`apps/api/src/evidence_store/`):**

| Component | Description |
|-----------|-------------|
| `EvidenceRecord` | Content-addressed fact about a system. SHA-256 key (`evd_...`). 20 fields including system_id64, source_name, evidence_type, record_status, freshness_status, confidence. |
| `DerivedFeature` | Computed feature from 1+ evidence records (e.g., a rating). References source run. |
| `RuleProposal` | Governed change proposal with status/priority/risk. Evidence-backed. |
| `RuleDecision` | Audit trail for proposal approvals/rejections/rollbacks. |
| `EvidenceSystemSummary` | Per-system aggregation with focus areas (colonisation_status, station_set, body_completeness, ring_composition). |

**Evidence Lifecycle:** ingestion → active → superseded → [archived | expired | quarantined | rejected]

**Freshness Policies (per evidence type):**
- `colonisation_status`: stale at 3 days, expired at 14 days
- `service_snapshot` / `station_set`: stale at 7 days, expired at 30 days
- `body_completeness` / `body_scan` / `ring_composition`: stale at 90 days, expired at 365 days

**Canonical Evidence Promotion:** Four evidence types can be auto-promoted from canonical DB tables (body_completeness, station_set, colonisation_status, ring_composition). Triggered by EDDN listener on every flush + manual API.

### 1.2 Data Source Status

| # | Source | Status | What It Feeds |
|---|--------|--------|---------------|
| 1 | **Spansh** | ✅ Live | Bulk galaxy snapshots + delta imports. Systems, bodies, stations, rings. Nightly |
| 2 | **EDDN** | ✅ Live | ZMQ streaming. Real-time systems, bodies, rings, colonisation events, dirty flags |
| 3 | **EDSM** | 🟡 Bounded | Staging-only station/bodies probe. Not canonical yet |
| 4 | **canonical_app_data** | ✅ Live | Derived evidence from already-ingested canonical tables |
| 5 | **DaftMav** | ✅ Live | Facility template catalogue JSON (manual snapshot) |
| 6 | **Inara** | ❌ Planned | No importer. `inara_api.py` exists but not operational |
| 7 | **Frontier Journal** | ❌ Planned | No pipeline. Intended for commander-local file drops |
| 8 | **Canonn** | ❌ Planned | No importer |
| 9 | **EDCD** | ❌ Planned | No importer |

**5 of 9 sources are still "planned" — zero implementation.**

### 1.3 Enrichment Staging Warehouse (Designed But Mostly Empty)

`sql/026_enrichment_staging_foundation.sql` defines **16 staging tables** for external evidence — a complete "Data Warehouse Utopia" layer isolated from canonical tables:

- `staging_edsm_stations`, `staging_edsm_bodies` (partially populated from bounded EDSM probes)
- `staging_body_rings`, `staging_factions`, `staging_system_states`
- `staging_station_economies`, `staging_station_services`, `staging_market_commodities`
- `staging_body_signals`, `staging_codex_entries`
- `derived_mission_intelligence`, `derived_exploration_intelligence`
- `derived_colonisation_economy_intelligence`, `derived_alert_candidates`

All carry `source_class`, `confidence`, `freshness_class`, `provenance` JSONB — every row is fully traceable. But most tables are **empty** — the warehouse exists structurally but has no production pipeline filling it.

### 1.4 Nightly Pipeline

```
Download Spansh deltas → Import → Re-rate dirty systems → Build archetypes →
Build topology → Build regional analysis → Rebuild clusters →
FLUSHDB (Redis wipe) → Update app_meta → VACUUM ANALYZE
```

---

## Part 2: Colonisation Mechanics — What We Should Track

### 2.1 Core Economy Mechanics (Post-Update 3, April 2025)

The April 2025 rework was the single largest mechanics change. Key rules:

**Economy Scoring Formula:**
```
Final Economy Score = Body Type Override (1.00)
                    + Body Feature Bonuses (1.00 each)
                    + Strong Link T2 facilities (0.80 each)
                    + Strong Link T1 facilities (0.40 each)
                    + System-wide features (0.40 each)
                    + Boost/Reduction modifiers (0.40 each)
                    + Weak Links from other bodies (0.05 each)
```

**Body Type Economy Overrides:**
| Body Type | Override Economies |
|-----------|-------------------|
| Earth-Like World | Agriculture, High Tech, Military, Tourism |
| Water World | Agriculture + Tourism |
| Ammonia World | High Tech + Tourism |
| Gas Giant | High Tech + Industrial |
| High Metal Content / Metal Rich | Extraction |
| Rocky Ice | Industrial + Refinery |
| Rocky | Refinery |
| Icy | Industrial |
| Has Rings / Asteroid Belt | Extraction |
| Has Organics (Biologicals) | Agriculture + Terraforming |
| Has Geologicals | Extraction + Industrial |

**Economy Compatibility Matrix:**
| Good Pairings | Risky (Cannibalizing) Pairings |
|---|---|
| Extraction + Refinery | Refinery + Industrial |
| Tourism + Refinery | Refinery + High Tech |
| Military + Agriculture | Industrial + Agriculture |
| Extraction + Agriculture | Industrial + High Tech |
| Military + High Tech | Extraction + Industrial |
| Military + Tourism | Extraction + High Tech |
| Military + Industrial | High Tech + Colony / Refinery / Extraction |

**"One Body, One Economy"** — Mixing economy facilities on the same body causes commodity cannibalization. Each body should be dedicated to a single economy.

### 2.2 Facility Data We Should Catalog

**Construction Point Ladder:**
- T1 builds are free → grant 1 T2 point
- T2 builds consume T2 points → grant 1 T3 point
- T3 builds consume T3 points
- 6 T1 builds needed to fund 1 T3
- Starting with Outpost as primary port grants +1 T2 point upfront

**Commodity Costs (Approximate, ~10% variance per build):**
| Commodity | Outpost | Coriolis | Orbis/Ocellus |
|-----------|---------|----------|---------------|
| Steel | 5,588 | 14,076 | 56,304 |
| Titanium | 4,843 | 8,205 | 32,820 |
| CMM Composite | 3,912 | 11,261 | 45,044 |
| Total ~ | **22,500** | **53k-71k** | **210k+** |

**System Stats (capped -4 to 10):** Development Level, Security, Tech Level, Wealth, Standard of Living.

### 2.3 Economy Import/Export Table

| Economy | Imports | Exports |
|---------|---------|---------|
| Extraction | Consumer Items, Food, Explosives, Machinery | Minerals, Metals, Hydrogen Fuels |
| Refinery | Consumer Items, Food, Minerals, Microbial Furnaces | Metals, Industrial Materials, Hydrogen Fuels |
| Industrial | Food, Metals, Auto-Fabricators, Robotics | Machinery, Consumer Items, Food Cartridges, Computer Components |
| High Tech | Food, Machinery, Metals, Superconductors | Technology, Consumer Tech |
| Agriculture | Consumer Items, Crop Harvesters, Agri-Medicines, Pesticides | Food, Textiles |
| Tourism | General Goods | Hydrogen Fuel, Biowaste |
| Military | Aluminium, HE Suits, Polymers, Thorium, Titanium | Hydrogen Fuel, Scrap, Robotics, Non-Lethal Weapons |
| Colony | Cobalt, Rutile, Pyrophyllite, Clothing, Grain, Surface Stabilisers, Water Purifiers | Hydrogen Fuel, Biowaste, Limpets |

---

## Part 3: External Data Sources — What We Could Wire Up

### 3.1 APIs and Dumps Available Right Now

| Source | Data Available | Format | Update Frequency | Rate Limits |
|--------|---------------|--------|-----------------|-------------|
| **EDSM** | Systems, stations, bodies, factions, traffic, markets, commodities | Nightly JSON dumps (12 GB+), REST API | Daily dumps + live API | None documented |
| **EDDN** | Real-time journal events from thousands of players | ZeroMQ streaming (`tcp://eddn.edcd.io:9500`) | Real-time | Already connected ✅ |
| **Spansh** | Systems, bodies, stations, neutron plotting | Dump downloads + REST API | Various (1-day, 1-week, monthly) | Already connected ✅ |
| **EDAstro** | 196M systems indexed, 98M visited, heat maps | Pre-computed map data | Every 2 days | None |
| **EDCD** | Coriolis, EDMC, EDSM ecosystem | GitHub org, libraries | Various | N/A |
| **Inara** | Systems, stations, commodities, factions | **No public API** | Real-time (scraping only) | N/A (scraping not recommended) |
| **Frontier Companion API** | Player data, market data | Legacy REST API (community-documented) | Real-time | Fragile, unofficial |
| **Player Journal** | EVERY in-game action | Local JSON file | Real-time (writes per event) | Local only — needs agent |
| **Canonn** | Lore, research data, generation ships, Guardian sites | Community wiki + research docs | Periodic | None |
| **Spansh API v2** | Route plotting, nearest-system, body search | REST API | Real-time | Coriolis ship loadout required |

### 3.2 Community Tools We Could Integrate With

| Tool | What It Does | Integration Opportunity |
|------|-------------|----------------------|
| **EDColonise.net** | Live colonisation candidate DB, tracks claims | Could consume their claim data or provide candidate scoring |
| **Raven Colonial** | Colony planner + progress tracker | Could export ed-finder plans to Raven format |
| **BGS-Tally** | Personal colonisation activity tracker (EDMC plugin) | Could share data format for import/export |
| **EDMC** (985+ stars) | The standard journal-reading platform | Build an EDMC plugin for real-time journal integration |
| **EDAstro** | Galaxy heat maps, traffic data | Could consume their pre-computed map for the colonisation heat map feature |
| **Coriolis** | Ship builder | Could pre-fill ship loadouts for Spansh route planning |
| **@kayahr/edsm** | Typed TypeScript EDSM API client | Already available as npm package |

### 3.3 The EDDB Vacuum

EDDB shut down April 2023 after years of being the community's indispensable data backbone. The creator cited burnout and frustration with Frontier's minimal API support. Over 30 parties offered to take it over. The community still feels the gap — no single tool has filled EDDB's role of "fast, no-frills, comprehensive search across all game data with an open API." **This is an opportunity.**

---

## Part 4: Evidence Store Improvements (Near-Term)

### 4.1 Wire the Planned Sources

| Priority | Source | What To Do | Effort |
|----------|--------|-----------|--------|
| 1 | **EDSM (full)** | Promote from bounded probe to production pipeline. Populate the 16 staging tables. | Medium (pipeline scripting) |
| 2 | **EDAstro** | Ingest their pre-computed heat maps and traffic data. 2-day freshness, no API limits. | Low (download + import) |
| 3 | **Inara** | Implement the `inara_api.py` client. Rate-limit aggressively. Focus on market/station data only. | Medium-High (API design + legal review) |
| 4 | **Frontier Journal** | Build journal upload endpoint. Let users opt-in to share their colonisation journal events. | Medium (EDMC plugin or web upload) |
| 5 | **Canonn** | Periodic snapshot of lore POI coordinates and research data. | Low (download + import) |

### 4.2 Add CRE Integration

The Colonisation Research Engine has 343 claims, 370 provenance links, 13 mechanics, and 16 CSV exports. None are loaded into ed-finder. The simplest first step:

- Import `mechanics.csv` into `derived_features` or a dedicated `cre_mechanics` table
- Import `claims.csv` into `evidence_records` with `source_name = 'mega_guide'`
- Import `claim_provenance_links.csv` to trace evidence provenance
- Each CRE release gets a versioned import, stored in `source_runs`

### 4.3 Add Colonisation-Specific Evidence Types

The current evidence types are generic (`body_completeness`, `station_set`, `colonisation_status`, `ring_composition`). Add:

| New Evidence Type | What It Tracks | Freshness |
|-------------------|---------------|-----------|
| `facility_built` | A new facility completed at a colony | 3d stale, 14d expired |
| `facility_demolished` | A facility marked for demolition | 3d stale, 14d expired |
| `economy_observed` | Observed economy at a colony port | 7d stale, 30d expired |
| `population_growth` | Population snapshot at a colony | 7d stale, 30d expired |
| `commodity_market` | Market commodity listing at a colony | 1d stale, 7d expired |
| `construction_progress` | % completion of active construction | 1d stale, 3d expired |
| `system_architect` | Who owns a colonised system | 7d stale, 30d expired |
| `build_order` | The sequence of facility construction | 30d stale, 90d expired |

### 4.4 Add Body Economy Profile Evidence

From the Mega Guide / DaftMav / CRE mechanics, populate a `body_economy_profiles` table:

```sql
CREATE TABLE body_economy_profiles (
    body_subtype TEXT PRIMARY KEY,
    base_economy TEXT[],
    feature_bonuses JSONB,  -- e.g., {"has_rings": "Extraction", "has_organics": "Agriculture"}
    avoid_economies TEXT[],
    confidence TEXT,        -- CRE confidence level
    source_refs TEXT[],     -- CRE claim references
    last_verified_version TEXT,
    updated_at TIMESTAMPTZ
);
```

---

## Part 5: Data Enrichment — Making It Sing

### 5.1 Tier 1: Core Utility (Build the Foundation)

| Feature | What It Does | Data Needed | Effort |
|---------|-------------|-------------|--------|
| **Construction Cost Calculator** | "I want to build X. Total commodities? Total carrier trips? Total cost?" | Facility recipes (from DaftMav/Mega Guide), commodity prices | Low |
| **Economy Override Lookup** | Select a body type + features → see exactly which economies manifest and at what weight | Body economy profile data | Low |
| **Economy Compatibility Matrix** | Visual/tabular view of which combinations cannibalize | Economy pairing rules | Low |
| **Integrated Search** | Single search bar for systems, stations, commodities, modules | EDSM dumps indexed locally | Medium |
| **System Evaluator** | Score every uncolonised system for colonisation potential | EDSM body data, distance-to-bubble | Medium |

### 5.2 Tier 2: The Killer Features

| Feature | What It Does | Data Needed | Effort |
|---------|-------------|-------------|--------|
| **Colony Economy Simulator** | "What happens if I build X and Y on body Z?" Predict final economy, production, population, trade routes. Compare scenarios side by side. | Facility economy types, link mechanics, population formulas, observed colony data | High |
| **Trade Route Optimizer** | Given construction shopping list, find optimal haul routes minimizing distance/time/cost. Multi-commodity, carrier-aware. | Station market data, commodity requirements, carrier mechanics | High |
| **Supply Chain Flow Map** | Origin-destination arrows showing commodity flows for construction. Identify bottlenecks. | Trade/commodity data, colonisation demand | Medium |
| **Colonisation Heat Map** | 2D/3D galaxy map: colonisation density, growth rate, frontier boundary, faction territories | EDSM dumps, EDDN firehose | Medium |
| **Galactic "Real Estate" Heat Map** | Score every system by desirability. Color-code like Zillow. "Where should I colonise?" | EDSM body data, faction data, colonisation mechanics | Medium-High |

### 5.3 Tier 3: Social & Ecosystem

| Feature | What It Does | Effort |
|---------|-------------|--------|
| **Colony Strategy Marketplace** | Publish, share, upvote, fork colony plans. Content creator ecosystem. | Medium |
| **Squadron Colony Planner** | Shared workspace, role assignments, live progress, hauling stats | High |
| **Community System Database** | Every colonised system gets a wiki page. Community-edited. | Medium-High |
| **Hauling Leaderboards** | Tons delivered per commander/squadron/colony. Achievements. | Medium |

### 5.4 Tier 4: The Wild Ideas

| Feature | What It Does | Effort |
|---------|-------------|--------|
| **Live Journal Agent** | Desktop app watching the player journal in real time. Cargo vs shopping list overlay, haul progress, auto-detect dock. Closes the planning-playing loop. | Medium |
| **3D System Architect** | Interactive 3D colony planning. Drag facilities onto bodies. Rotating view. Shareable. | High |
| **Colony Chronicle (AI)** | Auto-generate lore-rich narrative entries from actual game events. AI-powered but journal-grounded. | Medium-High |
| **ML Colonisation Recommender** | ML model scoring every system against user preferences. Learns from choices. | High |
| **Public API ("EDDB v2")** | Open REST API. Rate-limited, documented, versioned. Become the new community backbone. | Medium-High |
| **Economic Impact Predictor** | Supply shock modeling — predict price changes from nearby colonisation activity | High |

### 5.5 The EDDB Opportunity

EDDB's shutdown left a vacuum. Key lessons from EDDB's success:
1. **Fast, no-frills, straight to the point**
2. **Open API** that became backbone for dozens of other tools
3. **Painstaking data quality** — the creator spent years on this
4. **Integrated search** across all game data types in one place

ed-finder already has: 186M systems, live EDDN, nightly Spansh imports, ratings, clusters. With the staging warehouse designed but empty, the infrastructure for "EDDB v2" already exists — it just needs the pipelines turned on.

---

## Part 6: CRE Integration Path

The Colonisation Research Engine is the "truth" repo. Currently zero integration with ed-finder at runtime.

### 6.1 What CRE Has (Ready for Import)

| Export | Records | What ed-finder Could Do With It |
|--------|---------|-------------------------------|
| `mechanics.csv` | 13 | Populate a mechanics reference table. Link to evidence records. |
| `claims.csv` | 343 | Import as evidence_records with source_name='mega_guide'. Each claim gets an evidence_key. |
| `claim_provenance_links.csv` | 370 | Populate a provenance graph table. Trace every claim to its source. |
| `economy_rules.csv` | 20 | Feed the economy simulator. Each rule gets a version + confidence. |
| `construction_rules.csv` | 23 | Feed the construction cost calculator. Rules tagged with source and patch version. |
| `planner_rules.csv` | 13 | Feed the colony planner's constraint model. |
| `unknowns.csv` | 20 | Show "Known Unknowns" in the UI — things we don't know yet. Builds trust. |
| `contradictions.csv` | 9 | Show "Known Contradictions" — "Source A says X, Source B says Y." Honesty builds trust. |
| `graph_nodes.csv` + `graph_edges.csv` | 533 | Import into a graph DB or materialized as SQL join tables for relationship queries. |

### 6.2 Integration Steps

1. **Add a CRE version table** — track which CRE knowledge version is currently loaded
2. **Build the CSV import pipeline** — run `build_release_bundle.py` (CRE) → download exports → import into ed-finder
3. **Map confidence vocabularies** — CRE uses numeric 0-100 bands, ed-finder uses string labels. Build a mapping table.
4. **Wire RuleProposals to CRE claims** — each RuleProposal can reference CRE claim IDs as evidence
5. **Add a "CRE Knowledge" page** in the app — show what mechanics are documented, what's uncertain, what's contradicted

---

## Part 7: Priority Roadmap

### Now (This Week)

| # | Action | Why |
|---|--------|-----|
| 1 | Import CRE mechanics.csv + claims.csv into evidence_records | Instant mechanics knowledge base, zero infrastructure |
| 2 | Add body economy profiles table + populate from CRE/Mega Guide | Foundation for economy override lookup and simulator |
| 3 | Build the Construction Cost Calculator | Every coloniser's #1 question. Low effort, high value |
| 4 | Add colonisation-specific evidence types to the freshness policy table | Track what matters for colonies, not just generic body data |

### Next (This Month)

| # | Action | Why |
|---|--------|-----|
| 5 | Promote EDSM from bounded probe to production pipeline | Fill the staging warehouse with real data |
| 6 | Build the Economy Override Lookup + Compatibility Matrix | Low-effort tools that answer the most common planning questions |
| 7 | Ingest EDAstro pre-computed heat maps + traffic data | 2-day freshness, no API limits, immediate map enrichment |
| 8 | Add CRE provenance graph import (graph_nodes.csv + graph_edges.csv) | Trace every claim to its source. Radically improves evidence trust |

### Soon (This Quarter)

| # | Action | Why |
|---|--------|-----|
| 9 | Colony Economy Simulator | The definitive planning tool. No other app does this |
| 10 | Trade Route Optimizer for construction | Solves the #1 pain point (hauling logistics) |
| 11 | Colonisation Heat Map | Visualize the colonisation wave. Competitive differentiator |
| 12 | Wire Inara API (rate-limited, market data only) | Commodity prices and station services for trade optimizer |

### Later (Next Quarter+)

| # | Action | Why |
|---|--------|-----|
| 13 | Live Journal Agent (EDMC plugin) | Closes the planning-playing loop |
| 14 | Public API ("EDDB v2 backbone") | Ecosystem play — let other tools build on ed-finder data |
| 15 | 3D System Architect | Flagship visual feature |
| 16 | ML Colonisation Recommender | Eliminates decision paralysis |
| 17 | Colony Strategy Marketplace | Social features, content ecosystem |

---

## Part 8: Quick Wins (1-2 Lines of Code Each)

These are tiny changes with outsized impact:

1. **Add `facility_built` to freshness policies** — one dict entry in `_EVIDENCE_FRESHNESS_POLICIES`
2. **Log Redis errors to WARNING instead of swallowing them** — change `log.debug` to `log.warning` in `deps.py` cache_get/cache_set
3. **Add a `last_cre_import` timestamp to app_meta** — one INSERT, zero schema changes
4. **Add "System Architect" field to the SystemRow response** — one JOIN on `systems.system_architect` if the column exists
5. **Add `import_meta` stats to the nightly summary** — already collected, just surface in the log output
6. **Add commodity_cost_estimates.json** — a static data file with the approximate costs per facility type. Doesn't need a DB table — just a JSON file in `domain/`. Load at startup alongside the facility catalogue.

---

## Part 9: Sources NOT in the Catalog (Gaps Found)

Research discovered these valuable sources that aren't in ed-finder's `source_catalog.py`:

| Source | What It Provides | Rate Limit |
|--------|-----------------|------------|
| **ED Astrometrics** (edastro.com) | System API, POI database (GEC + GMP), regional stats, galaxy map layers, heat maps | 100 req/15 min |
| **Elite BGS API** (elitebgs.app) | Faction influence history, state change timelines, time-range queries | Unknown |
| **EDDiscovery Colonisation Panel** | Per-system colonisation tracking, Python plugin pipeline (ZMQ), build state memory | N/A (local tool) |
| **Elite Observatory + BioInsights** | Bio/geo signal prediction, planet class analysis, first discovery flagging | N/A (local tool) |
| **Raven Colonial** | Web-based colonisation planning, carrier pre-loading, BGS-Tally integration | N/A (companion site) |
| **EDCD FDevIDs** | Frontier's internal commodity/station/ship ID mappings | N/A (reference dataset) |
| **EDCD Tick Detector** | BGS daily tick detection (via `edkit.ticks.getLatest()`) | N/A |

### Specific Action Items from These Sources

1. **Add ED Astrometrics to source catalog** — POI proximity scoring for colonisation targets, regional statistics, galaxy map enrichment
2. **Add Elite BGS API to source catalog** — faction influence history for understanding who controls nearby space
3. **Add FDevIDs to source catalog** — essential reference for commodity name mapping
4. **Add colonisation journal events to the frontend import allowlist** — `ColonisationConstructionDepot`, `ColonisationContribution`, `ColonisationSystemClaim`, etc. are currently NOT in `journalImportWorker.ts:21`
5. **The `ColonisationConstructionDepot` event fires every ~15 seconds** — contains exact per-station commodity requirements and progress. This is a free, unused data stream

---

## Part 10: Data Quality Principles

From studying EDDB's success and failure:

1. **Data quality is the product.** EDDB's creator spent years on data cleaning. It was the differentiator.
2. **Show your work.** Surface unknowns and contradictions. CRE's unknowns.csv and contradictions.csv are trust-builders, not liabilities.
3. **Version everything.** Which patch were these mechanics extracted from? Which CRE release is loaded? Users need to know if data is pre-Update-3 or post-Dodec.
4. **Staging before canonical.** The enrichment warehouse design is correct — never write external data directly to canonical tables. Review first, promote after.
5. **Contribute back.** EDDB's open API made it the community backbone. ed-finder should export to EDDN, not just consume.
6. **Freshness transparency.** Tell users how old the data is. The freshness_status system (current/stale/expired) is a strong foundation — surface it in the UI.
