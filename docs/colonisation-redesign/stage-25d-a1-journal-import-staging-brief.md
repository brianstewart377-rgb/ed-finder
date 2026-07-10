# Stage 25D A-1 — Journal Import Staging Brief

## Purpose

Ship the smallest safe journal-import slice:

- parse Elite Dangerous journal files in the client,
- strip personal and out-of-scope data before network,
- submit normalised observation batches,
- persist them as staging/evidence artifacts with source-run traceability,
- stop short of canonical promotion.

This is intentionally `A-1` only. It is not the full journal ingestion lane.

## Why This Slice

- It captures the highest-value journal advantage immediately: historical
  backfill and first-party evidence.
- It avoids raw-file upload into the backend.
- It fits the repo's existing evidence/store/staging direction.
- It does not require accounts to provide value.
- It does not create a second soft path into canonical tables.

## Product Value

Phase-1 user promise:

> Import your local journal history safely, preview what will be shared, and
> stage observations as evidence without changing canonical data directly.

This slice is about:

- communal enrichment evidence,
- import receipts,
- provenance,
- future reconciliation readiness.

It is not yet about:

- live folder tailing,
- automatic canonical updates,
- personal depot progress across sessions,
- public commander attribution.

## Scope

### In Scope

- Browser-side file picker / dropzone.
- Web Worker parser for newline-delimited JSON journal files.
- Event allowlist with privacy stripping before upload.
- Normalised batch payloads to a bounded API endpoint.
- New `journal_import_staging` table or equivalent bounded staging store.
- `source_runs` row per import session.
- Writes to `observed_facts` and `evidence_records` with
  `source_name='frontier_journal'`.
- Import receipt UI with counts, run identifier, and bounded conflict summary.

### Out Of Scope

- Raw file storage on the server.
- Direct canonical writes from the import endpoint.
- Live tail / companion app / EDMC plugin.
- Cross-session personal telemetry tied to a stable user identity.
- Automatic scheduler activation.

## Transport Decision

Recommended transport:

- client-side parsing in a Web Worker,
- normalised observation batches over the API,
- no raw journal file upload.

Rejected for this slice:

- server-side raw log upload,
- desktop companion app as the initial transport.

## Privacy Rules

Parse only the allowlisted event classes needed for the initial value case.

Phase-1 allowlist:

- `FSDJump`
- `Location`
- `CarrierJump`
- `Scan`
- `FSSDiscoveryScan`
- `FSSAllBodiesFound`
- `SAASignalsFound`
- `FSSBodySignals`
- `Docked`
- colonisation-related events once exact names/payloads are verified against the
  current game build
- optional exploration-sale events only if the UX actually uses them

Always strip before network:

- commander name unless explicitly opted in later,
- squadron identifiers,
- chat and social events,
- wing/crew/friend events,
- ship loadout,
- credits/balance,
- any event not on the allowlist.

The user preview must make the privacy boundary explicit, for example:

- `2,341 body scans`
- `118 visited systems`
- `3 colonisation depot events`
- `nothing else leaves your machine`

## Write Path

Required write path:

```text
browser worker
  -> POST /api/journal/import
     -> journal_import_staging
     -> source_runs
     -> observed_facts / evidence_records
     -> reviewable reconciliation later
```

Non-negotiable rule:

- The import endpoint must not write canonical `systems`, `bodies`, or
  `stations` rows directly in `A-1`.

## Attribution Rules

For `A-1`:

- tie observations to the import session and source run,
- store any `source_commander` form as an opaque/import-scoped identifier only
  if needed,
- do not create a new persistent identity model.

For later phases:

- `A-3` personal telemetry may depend on sync/accounts,
- do not invent a third identity rail just for journals.

## API Contract

Suggested endpoints:

- `POST /api/journal/import`
- `GET /api/journal/imports/{run_key}`

Suggested request shape:

```json
{
  "client_manifest": {
    "parser_version": "v1",
    "files": [
      {
        "name": "Journal.2026-07-01T120000.01.log",
        "event_count": 3421
      }
    ]
  },
  "observations": [
    {
      "event_type": "Scan",
      "observed_at": "2026-07-01T12:00:00Z",
      "system_id64": 123,
      "body_id": 7,
      "payload": {}
    }
  ]
}
```

Suggested response shape:

```json
{
  "run_key": "jrnl-20260708-abc123",
  "summary": {
    "observations_received": 2341,
    "observations_staged": 2338,
    "duplicates_skipped": 3,
    "conflicts_flagged": 0
  }
}
```

## Dedupe Contract

- Re-importing the same file set should be a no-op at the evidence level.
- Use a stable dedupe/evidence key derived from:
  - event type,
  - system identity,
  - body or subject identity where present,
  - event timestamp,
  - source shape as needed.

This must dedupe whole-folder re-imports cleanly because users will do that.

## Storage Contract

New bounded table:

- `journal_import_staging`

Expected re-use:

- `source_runs`
- `observed_facts`
- `evidence_records`

Design preference:

- mirror the shape and operational discipline of the existing enrichment staging
  lane rather than inventing a parallel import architecture.

## UI Contract

Entry points:

- My Work as the primary entry,
- System Detail evidence surface as a secondary prompt.

Required UI states:

- file selection / drag-drop,
- parsing in progress,
- preview summary,
- privacy confirmation,
- import receipt,
- bounded error state for malformed files or rejected payloads.

Copy posture:

- evidence-first,
- explicit about what was staged,
- explicit that canonical data was not directly changed by the import itself.

## Technical Work

Frontend:

- journal-import feature folder,
- worker parser,
- allowlist normaliser,
- preview/consent UI,
- receipt UI.

Backend:

- typed batch endpoint,
- server-side validation of normalised observations,
- staging/evidence persistence,
- source-run creation and lookup,
- bounded rate limiting and payload caps.

Ops:

- import receipt/report visibility,
- source-run observability,
- no scheduler activation,
- no background auto-promotion in this slice.

Tests:

- worker parser ignores non-allowlisted events,
- privacy stripping happens before request submission,
- re-import dedupe works,
- endpoint rejects malformed shapes,
- source-run and receipt are created consistently.

## Risks

- Fabricated journals can still inject false observations into staging/evidence.
- Parser drift can happen when Frontier changes journal payloads.
- Large imports may create a flood of future reconciliation candidates.
- Later canonical promotion will increase `rating_dirty` churn and must be
  monitored, but that is an `A-2` concern, not a reason to block `A-1`.

## Gating

- `A-1` is allowed before accounts and before canonical promotion because it is
  staging/evidence only.
- `A-2` remains gated on migration-ledger and backup/restore readiness.
- `A-3` remains gated on identity continuity.

## Definition Of Done

- A user can select local journal files and see a privacy-bounded preview.
- The client submits only normalised allowlisted observations.
- The backend records a source run plus staging/evidence artifacts.
- The UI shows a clear receipt.
- No direct canonical mutation happens from the journal import endpoint.
