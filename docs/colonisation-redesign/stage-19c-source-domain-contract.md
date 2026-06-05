# Stage 19C — Source and Domain Contract

## Purpose

Stage 19C turns the Stage 19 roadmap and target architecture into an implementation contract.

This contract defines the allowed source names, source categories, import domains, import scopes, freshness classes, failure states, and canonical-impact boundaries for Data Warehouse Utopia.

No DB writes, imports, migrations, or canonical apply are approved by this document.

## Source category contract

| Category key | Meaning | Canonical impact | Automation posture |
|---|---|---|---|
| `source_of_truth` | Authoritative reference for rules or definitions | May inform canonical logic after structured review | Usually manual or curated import |
| `source_of_evidence` | External factual evidence | Must be staged and reconciled before canonical use | Auto-import eligible with provenance |
| `source_of_inspiration` | UI or workflow inspiration | No canonical impact | Not imported as data |
| `manual_operator_source` | Human-curated review packets, allowlists, and artifacts | May approve bounded writes | Manual only |
| `derived_source` | ED-Finder generated facts derived from other evidence | May produce candidates, not direct canonical writes | Auto-generated with lineage |

## Source name contract

| Source key | Category | Initial priority | Auto-import eligible | Notes |
|---|---|---:|---:|---|
| `edsm` | `source_of_evidence` | 1 | Yes | First automation target for station/system enrichment. |
| `spansh` | `source_of_evidence` | 2 | Yes | High-value for systems, bodies, rings, coordinates, and large snapshots. |
| `inara` | `source_of_evidence` | 4 | Maybe | Needs access, rate-limit, trust, and freshness review. |
| `daftmav` | `source_of_truth` | 3 | Manual first | Build templates and facility rules should be versioned and hashed. |
| `mega_guide` | `source_of_truth` | 3 | Manual curated | Rules/reference source, not automatic factual feed. |
| `operator_artifact` | `manual_operator_source` | 1 | Yes as artifact indexing | Review packets, dry-runs, allowlists, write results, and closeouts. |
| `local_generated_artifact` | `derived_source` | 2 | Yes | ED-Finder reports, summaries, and reconciliation outputs. |
| `mission_observation` | `source_of_evidence` | 5 | Later | Volatile evidence for mission-board intelligence. |
| `frontier_journal` | `source_of_evidence` | 6 | Later | Player-observed journal data, useful but user-specific/manual at first. |
| `edcd` | `source_of_evidence` | 8 | Later | Future community source candidate. |
| `canonn` | `source_of_evidence` | 9 | Later | Specialist community data, later-stage. |
| `ravencolonial` | `source_of_inspiration` | 10 | No | UI/workflow inspiration only, not canonical data. |

## Import domain contract

| Domain key | Meaning | Initial source candidates | Freshness class | Canonical impact |
|---|---|---|---|---|
| `systems` | System-level facts | EDSM, Spansh, Inara | slow_changing | high |
| `stars` | Star-level facts | Spansh, EDSM | stable_or_slow | medium |
| `bodies` | Planets, moons, body facts | Spansh, EDSM | stable_or_slow | very_high |
| `rings` | Ring facts and reserve/hotspot context | Spansh, EDSM | stable_or_slow | high |
| `belt_clusters` | Belt cluster evidence | Spansh, EDSM, manual | stable_or_slow | medium |
| `stations` | Stable ports and stations | EDSM, Inara, Spansh | moderate | very_high |
| `settlements` | Stable surface infrastructure | Inara, EDSM, manual | moderate | high |
| `station_services` | Service availability | Inara, EDSM, journal | volatile | high |
| `markets` | Commodity prices, supply, demand | Inara, journal | volatile | medium_high |
| `shipyard_outfitting` | Ship and module availability | Inara, journal | volatile | medium |
| `factions_bgs` | Factions, state, influence | Inara, EDSM, journal | volatile | medium_high |
| `economies_security` | Economy and security signals | EDSM, Inara, Spansh | moderate | high |
| `construction_sites` | Colonisation construction evidence | manual, journal, future community sources | ephemeral | high but transient |
| `fleet_carriers_transient` | Fleet carriers as mobile evidence | Inara, EDSM, journal | ephemeral | low for stable catalogue |
| `materials_resources` | Hotspots, resources, body materials | Spansh, EDSM, journal | moderate | medium_high |
| `facility_templates` | Colonisation build templates | DaftMav, Mega Guide, curated files | versioned_reference | very_high for planner |
| `rules_reference` | Mechanics and constraints | Mega Guide, curated docs | versioned_reference | very_high for planner |
| `mission_intelligence` | Mission-board and mission-network analytics | mission observations, derived facts, Inara context | ephemeral | high as analytics |
| `operator_artifacts` | Review/write evidence artifacts | operator artifacts, GitHub docs | audit_permanent | high for audit |

## Import scope contract

| Scope key | Meaning | May run automatically | Can write canonical |
|---|---|---:|---:|
| `raw_capture_only` | Capture raw source input or source hash only | Yes | No |
| `staging_only` | Load source facts into staging tables | Yes | No |
| `warehouse_fact_refresh` | Build queryable latest evidence/fact tables | Yes | No |
| `reconciliation_candidate` | Generate candidates from evidence | Yes | No |
| `review_packet` | Build human review packet | Yes | No |
| `approval_allowlist` | Human-approved write scope | No, requires explicit approval | No |
| `bounded_write_reviewed` | Controlled canonical write | No, manual controlled execution | Yes, bounded only |
| `canonical_apply` | Broad canonical apply lane | No | Only with separate explicit approval |

## Freshness class contract

| Freshness key | Meaning | Example domains |
|---|---|---|
| `audit_permanent` | Permanent audit evidence | operator artifacts, write records |
| `versioned_reference` | Stable until source version changes | rules, facility templates |
| `stable_or_slow` | Rarely changes | bodies, rings, stars |
| `slow_changing` | Changes occasionally | systems, stations |
| `moderate` | Changes enough to track freshness | economies, services, station metadata |
| `volatile` | Changes often | markets, factions, services |
| `ephemeral` | Short-lived or observed snapshots | missions, construction sites, fleet carriers |

## Import status contract

| Status key | Meaning |
|---|---|
| `planned` | Run record created before execution. |
| `running` | Import is in progress. |
| `succeeded` | Import completed and artifact was produced. |
| `failed` | Import errored and failure artifact/log was recorded. |
| `rejected` | Source validation failed before staging. |
| `superseded` | A newer successful run replaces this run for latest-view purposes. |
| `cancelled` | Operator stopped the run before completion. |

## Failure reason contract

Failure reasons should be structured rather than free-text only.

Initial keys:

- `missing_source_hash`
- `source_download_failed`
- `source_schema_mismatch`
- `source_too_large`
- `source_parse_failed`
- `row_validation_failed`
- `duplicate_active_run`
- `db_connection_failed`
- `staging_write_failed`
- `artifact_write_failed`
- `postcheck_failed`
- `operator_cancelled`

## Canonical-impact boundary

Automatic imports may populate raw, staging, warehouse, and candidate layers.

They must not directly mutate canonical tables.

Canonical-impacting changes must move through:

dry-run artifact -> review packet -> approval allowlist -> bounded write-reviewed execution -> post-write verification -> docs closeout

## Stage 18 policies carried forward

| Source value | Policy |
|---|---|
| `Coriolis Starport` | May map to `Coriolis` with confirmed identity and review/approval. |
| `Dodec Starport` | May map to `Dodec` with confirmed identity and review/approval. |
| `Drake-Class Carrier` | Refuse/defer as transient/mobile carrier. |
| `Space Construction Depot` | Refuse/defer as transient construction object. |
| `NULL` | Refuse. |

## Mission intelligence contract

Mission data is volatile and must be freshness-bound.

Mission intelligence should support:

- mission source station;
- destination station/system/body;
- mission type classification;
- faction/economy/state context;
- passenger/cargo/combat/mining/source-return categories;
- repeat destination patterns;
- station-to-station mission links;
- mission density score;
- passenger mission suitability;
- cargo/source-return suitability;
- large-pad mission usefulness;
- home-system mission paradise score.

Mission intelligence should be stored as evidence and derived analytics, not timeless canonical truth.

## Initial implementation decision

The first automated import lane should be EDSM station/system enrichment because:

- EDSM evidence already exists in staging;
- EDSM station evidence powered the Stage 18J/P18 station-type work;
- the source is high value and comparatively well understood;
- it can exercise the source-run ledger, staging, artifact, freshness, and candidate layers without direct canonical writes.

## Next stage

Stage 19D should define or harden the source-run ledger schema and its artifact contract.

Stage 19D should be schema/design first, then implementation.

## Non-goals

- no automatic canonical writes;
- no broad canonical apply;
- no parallel import automation for every source;
- no mission intelligence without freshness;
- no market data without age/freshness;
- no source evidence without provenance;
- no hidden conflicts.

## Definition of done for Stage 19C

Stage 19C is complete when this contract is recorded and accepted as the vocabulary for Stage 19 implementation.

No DB writes, imports, migrations, or canonical apply are approved by this document.
