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
