# Evidence Store And Ingestion Foundation

Date: 2026-07-06

## What This Adds

This slice introduces an Evidence Store MVP that sits on top of the existing `observed_facts` and `source_runs` seams instead of replacing them.

New storage surfaces:

- `evidence_records`
- `derived_features`
- `rule_proposals`
- `rule_decisions`

New API surfaces:

- `GET /api/evidence/sources`
- `POST /api/evidence/records`
- `GET /api/evidence/records`
- `POST /api/evidence/features`
- `GET /api/evidence/features`
- `POST /api/evidence/rule-proposals`
- `GET /api/evidence/rule-proposals`
- `POST /api/evidence/rule-proposals/{proposal_key}/decisions`
- `GET /api/evidence/systems/{system_id64}/summary`

These endpoints are intended to be the first durable seam for:

- imported evidence
- inferred or derived signals
- proposal review and decision audit
- a future CRE approval workflow

## Why This Shape

The repo already had:

- `observed_facts` for passive/manual evidence
- `source_runs` for provenance and import-run audit
- operator/admin review surfaces for bounded import workflows

What it did not have was a single place to store:

- imported evidence items with provenance
- derived features linked back to evidence
- rule proposals backed by evidence
- decision audit for proposal review

This MVP fills that gap without disturbing the existing planner evidence contract.

## Layer Contract

The split between `observed_facts` and `evidence_records` is now intentional and should remain explicit:

- `observed_facts`
  - raw observation log
  - append-oriented
  - broad source coverage, including manual/test-fixture and future imported lanes
  - useful for comparisons, debugging, and low-level traceability

- `evidence_records`
  - lifecycle-managed explanation layer
  - one active record per `(system, subject, evidence_type)` contract
  - supports quarantine, supersession, freshness aging, and player-facing trust surfaces
  - this is the layer future enrichment decisions and Evidence-panel reads should consume by default

Put differently: `observed_facts` answers "what did we see?", while `evidence_records` answers "what fact are we currently standing behind, and why?"

## Import Source Priority

Recommended implementation order:

1. `Spansh`
   - Keep as the canonical baseline for broad galaxy coverage.
   - Already live and should remain the backbone snapshot source.

2. `EDDN`
   - Keep as the freshness layer between snapshot imports.
   - Best source for near-real-time evidence and dirty-system triggers.

3. `EDSM`
   - Productionise the existing bounded enrichment path.
   - Best next expansion because the repo already contains staging, probe, and guard flows.

4. `Inara`
   - Highest-value missing enrichment source.
   - Strong candidate for station services, markets, factions, and mission context.
   - Must be rate-limited and provenance-heavy.

5. `Frontier Journal / commander logs`
   - Best path to first-party observational truth.
   - Foundation for opt-in EDMC or EDDiscovery uploads later.

6. `Canonn`
   - Useful for specialist discoveries and research-heavy evidence.
   - Good after core operational feeds are in place.

7. `EDCD`
   - Useful as a periodic reference dataset complementing EDDN.

8. `DaftMav`
   - Already live for facility-template imports.
   - Valuable, but narrower than the missing evidence feeds above.

## Practical Next Build

Best next ingestion implementation order:

1. turn the existing bounded `EDSM` flow into a normal evidence-record writer
2. add `Inara` as a bounded evidence importer with review packets
3. add journal upload or operator-drop ingestion for commander-local evidence
4. derive mission and colonisation features into `derived_features`
5. emit proposal candidates into `rule_proposals`
6. expose proposal review in Admin

Status after this slice:

- `EDSM` staging writes now emit `evidence_records` for station snapshots.
- The writer is idempotent on `evidence_key`.
- It only attaches `source_run_key` when the station row clearly came from the newer `source_runs` ledger flow, avoiding invalid links to legacy enrichment-only staging runs.
- Windows local importer paths now pass the local-file assertion correctly instead of being misread as URLs.
- Added `apps/importer/src/inara_evidence_import.py` for the first bounded `Inara -> evidence_records` path.
- The first Inara slice targets `station_services` only, resolves `system_id64` against the local `systems` table, records a `source_runs` ledger entry, and writes a JSON artifact for review.
- Example dry run:
  - `py apps/importer/src/inara_evidence_import.py --system "Shinrarta Dezhra" --dry-run --artifact-dir artifacts/inara`
- Example bounded write:
  - `py apps/importer/src/inara_evidence_import.py --system "Shinrarta Dezhra" --artifact-dir artifacts/inara`

## Guardrails

- Evidence Store does not replace canonical game-state tables.
- Evidence Store does not auto-apply rule changes.
- Rule proposals remain review-first.
- Future low-risk auto-approval should be policy-gated and auditable through `rule_decisions`.

## Retention Posture Before Personal Telemetry

Before journal Lane 2 or any other high-volume personal telemetry lane opens, retention needs to be explicit:

- `observed_facts`
  - remains the hot raw log, not the forever store
  - operator/manual/test-fixture observations can stay durable
  - imported high-volume telemetry should be treated as hot retention with a planned archive/export path, not endless primary-DB growth
  - future implementation target: monthly partitioning before commander-local telemetry is allowed to scale up

- `evidence_records`
  - remains the durable trust layer because it stores the curated fact we currently stand behind
  - active, superseded, and quarantined records stay longer than raw observations because they are the player-facing and operator-facing explanation surface
  - expired or rejected records can eventually move to colder storage, but only after their source-run provenance and review trail remain reproducible

- `source_runs` and import artifacts
  - keep compact receipts and provenance records durable
  - raw import artifacts can use bounded retention once the curated evidence layer and checksums make replay/audit possible

- admission control
  - every incoming fact still has to do one of three useful things: dedupe to an existing record, replace the currently active record, or land quarantined for later promotion
  - raw observations that never promote should age out with the hot-log window instead of accumulating forever
  - large journal syncs should be sharded into bounded batches so one commander import cannot silently create an unreviewable storage spike

Practical policy direction:

1. keep the primary app database optimized for hot observations plus durable curated evidence
2. push long-tail raw history into partitioned or archived storage, not one ever-growing heap table
3. preserve enough source-run artifact data to replay or explain any promoted evidence record later

Current operational guardrail:

- use `scripts/checks/telemetry_hot_log_snapshot.py` as the read-only operator snapshot for this posture
- treat `journal_import_staging` as the first hot-log pressure gauge because A-1 personal telemetry lands there today
- preferred working thresholds before Lane 2 broadens:
  - `journal_import_staging`
    - healthy: mostly inside 30 days
    - warning: meaningful tail beyond 30 days
    - action-needed: persistent tail beyond 90 days without an archive/export path
  - `observed_facts` imported telemetry rows
    - healthy: bounded hot working set only
    - action-needed: imported telemetry building a long-lived 90+ day heap without partition or archive
  - `source_runs`
    - receipts remain durable, but raw bulky artifacts should not quietly become the forever store

