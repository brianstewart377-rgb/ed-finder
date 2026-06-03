# Stage 18J-P9 — Read-only External Identity Candidate Artifact

## Purpose

Stage 18J-P9 adds a read-only external station identity candidate artifact
generator. It proposes reviewable identity rows from staged EDSM station
evidence without writing to `station_external_identity`.

This stage is read-only artifact/tooling work. It does not run production
commands, touch the production database, write to `station_external_identity`,
load identity evidence, run production imports, run production reconciliation,
run the summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Input Evidence

The artifact generator reads staged EDSM station evidence through an explicit
read-only DSN:

- `staging_edsm_stations`;
- `enrichment_source_runs`;
- `enrichment_source_files`;
- canonical `systems`;
- canonical `stations`.

The first source is `edsm_nightly_stations`, as selected by Stage 18J-P8.
Source run filtering is required through `--source-run-key`, with optional
`--source-file-key` and `--limit`.

The current known production state remains:

- `station_external_identity` exists;
- `station_external_identity` row count is `0`;
- canonical `stations` count is `284763`;
- staged EDSM station evidence exists;
- no identity evidence has been loaded.

## Matching Strategy

The candidate query intentionally does not use `station_external_identity` and
does not use `station_body_links`.

Candidate canonical matching requires:

- staged source is `edsm_nightly_stations`;
- source row is within the requested source run/file filters;
- source `system_id64` matches canonical `systems.id64`;
- normalized staged `station_name` matches normalized canonical `stations.name`
  within that system.

The artifact classifies:

- exactly one canonical station match as reviewable;
- zero canonical station matches as rejected/source-only;
- multiple canonical station matches as conflicting/ambiguous.

The tool preserves source `market_id` and `edsm_station_id` values from staged
evidence. It does not infer external IDs from `stations.id`, and it does not
use `station_body_links.market_id` as general station identity proof.

## Candidate Statuses

Artifact statuses are:

- `confirmed_candidate`: one canonical station matches by `system_id64` and
  normalized station name, source provenance is complete, at least one external
  source ID is present, and source confidence/freshness are reviewable.
- `proposed`: one canonical station matches, but source confidence/freshness
  requires review before it can be treated as a confirmed identity candidate.
- `conflicting`: multiple canonical station matches or direct match proof
  conflict, such as system/name mismatch.
- `rejected`: missing external source ID, missing provenance, missing
  `system_id64`, missing station name, or no canonical station match.

These statuses are artifact review statuses. P9 does not insert table rows and
does not mark any identity as confirmed in production.

## Artifact Contract

Tool:

- `apps/importer/src/station_external_identity_candidates.py`

The CLI supports:

- `--dsn`;
- `--source-run-key`;
- `--source-file-key`;
- `--limit`;
- `--sample-limit`;
- `--json`;
- `--output`.

The emitted JSON includes:

- `schema_version = station_external_identity_candidates/v1`;
- `generated_at`;
- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`;
- source run/file filters;
- total staged rows inspected;
- candidate counts by status;
- conflict reason counts;
- match basis counts;
- source identity coverage counts;
- canonical match coverage counts;
- capped sample candidates;
- artifact checksum/integrity block.

Sample candidates omit raw payload dumps. They include source run/file/hash
provenance, external source IDs, source/canonical match proof, and explicit
flags that internal `stations.id` and `station_body_links` were not used as
identity proof.

## Safety Boundaries

The tool is read-only:

- its SQL is SELECT-only;
- it rejects `--apply`, `--write`, `--write-staging`, `--commit`, and `--load`;
- it does not write to `station_external_identity`;
- it does not write canonical tables;
- it does not run station-type dry-run;
- it emits deterministic JSON for review.

Tests use synthetic rows and fake DB cursors. They do not require production
credentials.

## What This Does Not Write

P9 writes nothing to:

- `station_external_identity`;
- `stations`;
- `station_type`;
- warehouse staging tables;
- approval records;
- production artifact directories.

It also does not load identity evidence, run imports, run reconciliation, run
summarizer, run station-type dry-run, or run canonical apply.

## Operator Workflow

After merge, a future Hetzner operator may run the tool as a read-only artifact
step with explicit source filters and an operator-managed read-only DSN.

Operator workflow requirements:

- run from the approved Hetzner operator context only;
- use a read-only DB role/DSN;
- provide `--source-run-key`;
- provide `--source-file-key` when narrowing to the known staged source file;
- write output to an operator artifact path;
- preserve the artifact checksum;
- do not combine this artifact run with identity evidence load,
  reconciliation integration, station-type dry-run, or apply.

## Review Requirements

Before any bounded load-plan or write-staging/load stage:

- review candidate status counts;
- review conflict reason counts;
- inspect capped samples;
- confirm source run/file filters;
- confirm raw payloads are not dumped;
- confirm `canonical_writes_planned`, `station_type_writes_planned`, and
  `identity_rows_written` are all `0`;
- confirm source provenance is present for reviewable candidates;
- confirm rejected/source-only and conflicting/ambiguous candidates are not
  treated as confirmed identity.

Stage 18J-P10 reviews the first Hetzner read-only artifact. It records
`261938` `confirmed_candidate` rows, `258` conflicting rows, and `35981`
rejected/source-only rows. The readiness verdict is `Ready only for bounded
identity load dry-run`; `confirmed_candidate` remains an artifact status, not a
production-confirmed identity status.

## Recommended Next Stages

- Stage 18J-P10 - External identity candidate artifact review.
- Stage 18J-P11 - Bounded external identity load-plan artifact, no DB writes.
- Stage 18J-P12 - Review bounded identity load plan.
- Stage 18J-P13 - Controlled identity evidence load into
  `station_external_identity`, no station-type writes.
- Stage 18J-P14 - Identity coverage artifact after load.
- Stage 18J-P15 - Read-only reconciliation integration with confirmed
  identity.
- Stage 18J-P16 - Retry strict station-type dry-run.

## Final Recommendation

Use the P9 artifact as the review gate before any writes to
`station_external_identity`.

Do not load identity evidence until the candidate artifact has been generated,
reviewed, and accepted with exact source filters and artifact checksum. Keep
station-type dry-run and canonical apply blocked.
