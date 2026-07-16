# Evidence Store Quick Wins — 2026-07-15

## Changes Made

### 1. Added colonisation journal events to frontend import allowlist

**Files:**
- `frontend/src/types/api.ts:112` — added 6 colonisation events to `JournalImportObservationInput.event_type` union
- `frontend/src/features/journal-import/journalImportWorker.ts:21` — added 6 colonisation events to `ALLOWED_EVENT_TYPES`

**Events added:**
- `ColonisationBeaconDeployed` — beacon placement at construction site
- `ColonisationConstructionDepot` — fires every ~15s at construction site with full commodity requirements and progress
- `ColonisationContribution` — commodity delivery tracking
- `ColonisationSystemClaim` — system claimed for colonisation
- `ColonisationSystemClaimRelease` — claim released/abandoned
- `CompleteConstruction` — facility construction completed

**Impact:** The `ColonisationConstructionDepot` event alone is the single richest per-player colonisation data source — it contains exact per-station commodity requirements, progress percentages, and payment information. Previously discarded by the journal importer.

### 2. Added 3 missing data sources to evidence source catalog

**File:** `apps/api/src/evidence_store/source_catalog.py`

| # | Source | Priority | Domains | Status |
|---|--------|----------|---------|--------|
| 10 | **ED Astrometrics** (edastro.com) | 5 | systems, bodies, exploration, galactic_mapping | planned |
| 11 | **Elite BGS API** (elitebgs.app) | 6 | factions_bgs, economies_security | planned |
| 12 | **FDevIDs** (github.com/EDCD/FDevIDs) | 9 | systems, stations, markets, materials_resources | planned |

**Impact:**
- ED Astrometrics: POI database (GEC + GMP), regional statistics, galaxy map layers. 100 req/15min rate limit. Fills the exploration/narrative gap.
- Elite BGS API: Faction influence history, state change timelines. Critical for colonisation expansion strategy.
- FDevIDs: Maps Frontier internal IDs (`$aluminium_name;`) to human-readable labels. Low-update reference dataset.

### 3. Source catalog now has 12 entries (was 9)

**Live:** spansh, eddn, canonical_app_data, daftmav (4)
**Bounded:** edsm (1)
**Planned:** inara, frontier_journal, canonn, edcd, ed_astrometrics, elite_bgs_api, fdevids (7)

## Next Quick Wins (Not Yet Implemented)

| # | Action | Effort |
|---|--------|--------|
| 1 | Add 8 colonisation-specific evidence types to `_EVIDENCE_FRESHNESS_POLICIES` | 8 dict entries |
| 2 | Create `commodity_cost_estimates.json` — approximate costs per facility type | 1 static file |
| 3 | Add `CargoTransfer`, `CarrierJump`, `CarrierLocation` to journal import allowlist (carrier logistics) | 3 event names |
| 4 | Import CRE `mechanics.csv` into evidence_records (13 mechanics) | 1 import script |
| 5 | Add `last_cre_import` timestamp to `app_meta` table | 1 INSERT |
| 6 | Log Redis errors at WARNING level instead of swallowing silently | `log.debug` → `log.warning` |
