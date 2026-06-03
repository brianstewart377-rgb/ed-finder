# Stage 18J-P Identity Evidence Execution Board

## Purpose

This board optimises the remaining Stage 18J-P external station identity
evidence workflow.

Stage 18J-P has deliberately used small safe chunks while it proved the
identity model, schema, read-only candidate artifact, and bounded load-plan
artifact. The remaining repo work can now be grouped into larger safe chunks
without relaxing production/operator boundaries.

This stage is docs/planning only. It does not run production commands, touch
the production database, load identity evidence, write to
`station_external_identity`, run imports, run reconciliation, run the
summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Current State

Known state:

- `station_external_identity` exists on Hetzner.
- `station_external_identity` row count is `0`.
- The read-only identity candidate artifact exists.
- The bounded no-write load-plan artifact exists.
- The load-plan artifact reported:
  - `total_candidates_seen = 298177`;
  - `eligible_confirmed_candidates_seen = 261938`;
  - `planned_rows_count = 20`;
  - `identity_rows_written = 0`;
  - `station_external_identity` row count remained `0`.
- Stage 18J-P10 verdict: `Ready only for bounded identity load dry-run`.
- Stage 18J-P11 produced the bounded no-write load-plan tool/artifact path.
- Stage 18J-P12/P13 records the bounded load-plan artifact review and adds an
  offline planned-row review packet generator.
- Stage 18J-P12/P13 verdict: `Ready only after planned-row manual review`.
- The first Hetzner offline review-packet run completed safely but exposed a
  packet contract issue: `manual_review_items` were not self-contained enough
  for manual row review. Stage 18J-P13A hardens the contract so each item
  embeds `planned_row`, boolean `checks`, and `reviewer_notes = null`.
- Stage 18K remains untouched.

## Why We Are Optimising

The earlier tiny chunks were correct while the risk was unknown:

- canonical `stations` had no `market_id` or `edsm_station_id`;
- the strict station-type dry-run correctly yielded zero eligible rows;
- external identity needed a separate schema and proof model;
- the first candidate and load-plan artifacts needed to prove they were
  read-only and bounded.

That risk is now better understood. Continuing with one docs-only PR per small
decision would add review overhead without improving production safety. Repo
work can be bundled when the bundle is still testable, no-write, and bounded.

## What Must Stay Small

Hetzner production actions must stay tiny and single-purpose:

- planned-row review packet generation;
- controlled load of exactly reviewed rows;
- post-load row-count and status-count checks;
- identity coverage artifact generation;
- read-only reconciliation artifact generation;
- strict station-type dry-run retry;
- any future approval packet;
- any future canonical apply.

Never combine identity load with station-type dry-run. Never combine
station-type dry-run with canonical apply.

## What Can Be Bundled

Repo work can be bundled where the bundle shares one goal and one safety
boundary:

- tool;
- tests;
- operator script;
- docs;
- roadmap/runbook updates.

Avoid docs-only PRs unless they unblock a risky action, clarify a safety gate,
or record an operator result that must be preserved before the next action.

## Remaining Workstreams

Remaining workstreams are:

- planned-row review packet generation;
- controlled identity evidence load tooling;
- identity coverage artifact after load;
- read-only reconciliation integration with confirmed identity;
- strict station-type dry-run retry using confirmed identity;
- review/approval packet only if a future dry-run produces acceptable
  station-type candidates;
- later apply only if a separate approval packet explicitly authorizes it.

## Proposed Chunked PR Plan

### Chunk A - P12/P13 Review Pack

Goal: review the bounded load-plan artifact and generate a planned-row review
packet.

Bundle:

- review bounded load-plan artifact;
- add planned-row review packet tooling if needed;
- add tests for review packet extraction and safety fields;
- add docs/runbook updates;
- no DB writes.

Exit criteria:

- exact load-plan artifact path and checksum recorded;
- each of the `20` planned rows can be inspected in a compact review packet;
- every manual review item embeds the exact planned row being reviewed;
- every manual review item embeds non-empty boolean review checks;
- every review item defaults to `needs_manual_review`;
- rejected/source-only and ambiguous rows remain non-loadable;
- `identity_rows_written = 0`;
- `approval_record_created = false`;
- station-type writes remain blocked.

### Chunk B - P14 Controlled Identity Load Tooling

Goal: add controlled load tooling for reviewed rows only.

Bundle:

- add controlled load tool;
- add operator script;
- enforce reviewed artifact checksum;
- enforce exact source run/file filters;
- enforce exact reviewed row IDs/hashes;
- enforce max rows;
- run inside a transaction;
- add tests for refusal modes and no accidental canonical writes;
- update docs/runbook.

Repo work must not run production. The Hetzner production load remains a
separate tiny operator action after review.

### Chunk C - P15 Post-load Identity Coverage

Goal: prove what changed after the controlled identity load.

Bundle:

- coverage artifact tool;
- tests;
- operator script;
- docs/runbook updates.

Coverage must show:

- `station_external_identity` row count;
- counts by `identity_status`;
- source run/file/hash preservation;
- no rows without external IDs;
- no station-type writes;
- no canonical apply.

### Chunk D - P16 Reconciliation Integration

Goal: expose confirmed identity in read-only reconciliation.

Bundle:

- read-only reconciliation includes confirmed external identity fields;
- tests;
- docs/runbook updates;
- no canonical writes.

Confirmed identity may support read-only station identity proof. It is not
station-type truth.

### Chunk E - P17 Strict Station-Type Dry-Run Retry

Goal: retry the strict station-type dry-run using confirmed identity evidence.

Bundle:

- use confirmed identity in the strict filter/reconciliation input;
- keep the dry-run bounded;
- keep `canonical_writes_planned = 0`;
- no apply;
- add docs/runbook updates and tests as needed.

Any non-zero candidates still require a separate review packet before canonical
apply can be discussed.

## Proposed Hetzner Operator Actions

Use tiny, single-purpose Hetzner actions:

1. Run planned-row review packet.
2. Only after review, run controlled load of the exact reviewed `20` rows.
3. Generate identity coverage artifact.
4. Generate read-only reconciliation with confirmed identity.
5. Retry strict station-type dry-run only if identity coverage is acceptable.

Each action should use this standard command shape:

- pre-check row counts;
- run guarded script;
- output artifact path;
- output checksum;
- output compact summary;
- post-check row counts;
- explicit no-forbidden-actions confirmation.

## Stop / Go Gates

Stop if:

- artifact checksum mismatches;
- source run/file filters mismatch;
- planned rows are not the reviewed rows;
- `station_external_identity` row count is unexpected;
- any planned row lacks source run/file/hash provenance;
- any planned row lacks both `market_id` and `edsm_station_id`;
- any row depends on internal `stations.id` as external identity proof;
- any row uses `station_body_links.market_id` as general identity proof;
- conflicting or source-only evidence is treated as confirmed;
- imports, reconciliation, summarizer, dry-run, or apply are accidentally
  coupled to identity loading;
- Stage 18K appears in scope.

Go only when:

- exact artifacts and checksums are recorded;
- row counts match expectations;
- every planned row in scope has been reviewed;
- operator action is tiny and single-purpose;
- forbidden actions remain blocked.

## Artifact Rules

Artifacts must:

- use versioned schema names;
- include `generated_at`;
- include `dry_run`, `read_only`, and/or `report_only` flags when applicable;
- include source run/file filters;
- include input artifact checksums when derived from prior artifacts;
- include output artifact checksum or integrity block;
- include compact counts and bounded samples;
- avoid raw payload dumps unless a later explicit review stage requires them;
- record `canonical_writes_planned = 0` until a separate apply packet exists;
- record `station_type_writes_planned = 0` until strict dry-run review permits
  otherwise;
- preserve source run/file/hash provenance for identity evidence.

## Production Safety Rules

Production safety rules:

- Keep Hetzner production actions tiny and single-purpose.
- Never combine identity load with station-type dry-run.
- Never combine station-type dry-run with canonical apply.
- Never run apply without a separate approval packet.
- Never let scheduler/cron run canonical apply.
- Unknown remains unknown.
- Source-only remains source-only.
- Confirmed identity is identity evidence, not station-type truth.
- Conflicting evidence remains visible and blocked.
- Stage 18K remains out of scope.

## Recommended Next Actions

Recommended next actions:

1. Use this execution board as the remaining Stage 18J-P tracker.
2. Use `stage-18j-p12-p13-load-plan-review-packet.md` as the Chunk A review
   record.
3. Run the planned-row review packet as a tiny Hetzner offline action after
   Chunk A merges.
4. Proceed with Chunk B only after the planned rows are manually accepted.
5. Keep station-type dry-run blocked until post-load coverage and read-only
   reconciliation prove confirmed identity coverage.

## Final Recommendation

Move from one-stage-per-sentence to larger repo chunks, but keep every Hetzner
action small and explicit.

Use this board to track Stage 18J-P through identity evidence load, coverage,
read-only reconciliation integration, and the strict station-type dry-run
retry. Do not start Stage 18K, and do not discuss canonical apply until a
future bounded dry-run and separate approval packet justify it.
