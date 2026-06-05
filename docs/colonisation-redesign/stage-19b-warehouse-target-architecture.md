# Stage 19B — Warehouse Target Architecture and Auto-Import Safety Design

## Purpose

Stage 19B defines the target architecture for Data Warehouse Utopia.

Stage 19A showed that ED-Finder already has substantial data and scaffolding:

- very large `systems`, `bodies`, and `ratings` tables;
- existing staging/enrichment/source-run signals;
- station/body/ring/faction/market/service/domain scaffolding;
- mission-intelligence scaffolding;
- source provenance columns;
- a working evidence/review/write pattern proven by Stage 18J/P18.

The problem is not lack of data. The problem is that the warehouse is not yet organised as a safe, automated, auditable import engine.

## Architecture goal

The warehouse must become a pipeline with clear boundaries:

external source -> source run ledger -> raw/source retention -> staging tables -> warehouse facts -> reconciliation candidates -> review packet -> approval allowlist -> bounded write-reviewed canonical update -> post-write verification

Automatic imports must stop before canonical mutation.

Canonical mutation remains a separate controlled lane.

## Layer 1 — Source-run ledger

The source-run ledger is the backbone of the warehouse.

Every import attempt must create or reference a source-run record.

Minimum fields:

- source run key;
- source name;
- source category;
- source input type;
- source URL/path/API endpoint;
- source input SHA-256;
- git commit SHA;
- importer name/version;
- started at;
- finished at;
- status;
- rows read;
- rows staged;
- rows rejected;
- error summary;
- artifact path;
- artifact SHA-256;
- artifact integrity SHA-256;
- scheduler/operator context.

Status values should include `planned`, `running`, `succeeded`, `failed`, `rejected`, and `superseded`.

Rules:

- no overlapping active run for the same source;
- no missing source hash for file-based imports;
- no silent success without artifact;
- failed imports must record failure artifact/log details.

## Layer 2 — Raw/source retention

Raw/source retention means ED-Finder can prove where facts came from.

Depending on source size, retention may be one of:

- full raw file stored on disk with SHA-256;
- compressed source snapshot;
- source record hashes;
- source API response page hashes;
- source-run manifest with per-record hashes.

Rules:

- no source evidence without provenance;
- large sources may use hash manifests instead of storing every raw byte forever;
- raw/source retention should have a disk-retention policy.

## Layer 3 — Staging tables

Staging tables represent source facts as they were imported.

They do not decide canonical truth.

Initial staging domains:

- systems;
- stars;
- bodies;
- rings;
- belt clusters;
- stations;
- settlements;
- station services;
- markets;
- factions;
- construction sites;
- facility templates;
- rules/reference facts;
- mission observations;
- operator artifacts.

Rules:

- staging rows must reference source-run identity;
- staging rows should contain source record hash;
- staging should be idempotent for repeated source runs;
- staging must tolerate source-specific naming/schema quirks;
- staging must not directly overwrite canonical tables.

## Layer 4 — Warehouse fact tables

Warehouse facts are cleaned, queryable, source-grounded facts.

They may merge multiple source runs and expose latest-evidence views.

Warehouse facts should not be treated as canonical by default.

Initial warehouse domains:

- system facts;
- body facts;
- ring facts;
- station facts;
- service facts;
- market facts;
- faction/economy facts;
- construction facts;
- mission intelligence facts;
- facility/rule facts;
- artifact/freshness facts.

Rules:

- every fact must retain source lineage;
- facts should expose freshness and conflict state;
- derived facts must say what they derive from;
- conflicts must be visible, not hidden.

## Layer 5 — Reconciliation candidates

Reconciliation candidates are the bridge between warehouse evidence and canonical data.

Candidate types:

- external identity;
- station type;
- station services;
- market availability;
- landing pad;
- economy;
- body metadata;
- rings;
- construction state;
- facility/build-plan rules;
- mission intelligence scores.

Each candidate should include:

- current canonical value;
- proposed value;
- source evidence;
- source run key;
- source record hash;
- confidence;
- conflict reason;
- freshness;
- review questions.

Candidates do not write canonical data.

## Layer 6 — Review and approval

Any canonical-impacting lane must follow this pattern:

dry-run artifact -> review packet -> human approval -> approval allowlist artifact -> bounded write-reviewed execution -> post-write verification -> docs closeout

This pattern was proven in Stage 18J/P18 and should be reused.

## Layer 7 — Canonical tables

Canonical tables remain protected.

Imports must not directly mutate canonical tables.

Canonical changes should only happen via explicit controlled write lanes.

Known canonical lanes:

- station external identity;
- station type;
- station service availability;
- body facts;
- ring facts;
- economy/faction facts;
- facility/build rules;
- mission intelligence summaries, if/when promoted.

## Layer 8 — Scheduler and automation

Automation should use a simple and boring scheduler first.

Preferred initial approach:

- systemd timer on Hetzner;
- one import source per timer/job;
- lockfile to prevent overlap;
- fixed log path;
- fixed artifact path;
- disabled-by-default until reviewed;
- clear rollback/disable instructions.

Scheduler rules:

- no secret printing;
- no canonical writes;
- no canonical apply;
- no running if previous run is still active;
- no ignoring failed source validation;
- artifact required for every run.

## Layer 9 — Admin/operator visibility

The UI/API should expose warehouse health.

Useful views:

- latest source runs;
- source freshness;
- failed imports;
- staged row counts;
- warehouse fact counts;
- pending reconciliation candidates;
- artifact links/hashes;
- unknown/refused/deferred source values;
- mission intelligence freshness;
- last write-reviewed execution;
- safety state.

## Initial source priority

1. EDSM station/system enrichment.
2. Spansh systems/bodies/rings.
3. EDSM/Spansh body/ring normalisation.
4. Station services/economies.
5. Facility templates / build rules.
6. Mission observations and mission intelligence.
7. Inara enrichment after access/trust review.
8. Markets/shipyard/outfitting after freshness model exists.

## Initial implementation path

### Stage 19C — Source and domain contract

Turn the roadmap matrices into an implementation contract covering source names, source categories, domains, import scope, freshness model, and failure model.

### Stage 19D — Source-run ledger schema

Implement or harden the source-run ledger.

### Stage 19E — Idempotent import wrapper

Create a reusable import wrapper.

### Stage 19F — EDSM auto-import MVP

Automate one source safely.

### Stage 19G — Freshness/status artifact

Generate a current warehouse health artifact.

### Stage 19H — Scheduler

Enable reviewed automation.

## Non-goals

Do not do these in early Stage 19:

- broad canonical apply;
- automatic canonical writes;
- parallel imports for every source;
- UI mega-redesign;
- source imports without provenance;
- source imports without artifacts;
- mission intelligence without freshness;
- huge repo-wide refactor.

## Definition of done for Stage 19B

Stage 19B is complete when this architecture is recorded and accepted as the guiding design for Stage 19 implementation.

No DB writes, imports, migrations, or canonical apply are approved by this document.
