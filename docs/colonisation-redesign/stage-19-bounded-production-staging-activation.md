# Stage 19BA - Bounded Production Staging Activation

## Purpose

Stage 19BA prepares the next separate Stage 19 operational dependency after the
completed safety programme and the merged Stage 23A evidence work. It defines a
bounded production-staging activation contract for a future manual EDSM staging
run without authorizing execution in this checkpoint.

This document does not reopen canonical apply, rebaseline, scheduler/service
activation, or full production automation. It only prepares a reviewed,
staging-only operator boundary.

## Business Justification

- Stage 23B can only consume warehouse evidence confidently after a bounded
  production staging lane exists and succeeds.
- The repo already proved local bounded staging safety through Stage 19AR,
  Stage 19AS-AU, and Stage 19AV.
- A production-staging activation contract is therefore the next separate
  operational dependency, while Stage 23 remains the active product/evidence
  roadmap.

## Completed Safety Prerequisites

The following prerequisites are already complete and preserved:

- Stage 19AS.1 disposable PostgreSQL constraint coverage;
- Stage 19AS.2 operator script contract formalization;
- Stage 19AR approved 25-row diagnostic staging baseline;
- Stage 19AS-AU controlled 100-row staging expansion;
- Stage 19AU read-only AS-AU verification;
- Stage 19AV expanded 250-row staging pilot;
- Stage 19AW paused-state decision boundary;
- Stage 19AX read-only AV verification;
- Stage 19AY test-environment and safety-programme closeout;
- merged Stage 23A live per-system evidence provider.

The Stage 19 safety programme is complete. Full production automation is not.

## Proposed Source

- source: `EDSM`;
- invocation: manual operator command only;
- source identity required: `--source-name edsm` and an explicit
  `--source-batch-label`;
- source location required: explicit `--source-uri`;
- source hash required: explicit `--source-sha256` (64 lowercase hex chars).

No source acquisition is authorized by this checkpoint. The source file or URI
must already exist and be supplied by a later approved operator action.

For the baseline wrapper:

- URI userinfo is forbidden;
- URI credentials are forbidden;
- query strings are never logged;
- fragments are never logged;
- query strings/fragments are never logged;
- source URIs are sanitized for display;
- only a sanitized source reference may be printed;
- the SHA-256 remains the immutable approved source identity.

## Exact Write Boundary

The initial bounded activation is staging-only and may write only these tables:

- `source_runs`;
- `enrichment_source_runs`;
- `staging_edsm_stations`.

This three-table description is the original Stage 19BA control-baseline
shorthand. A later executable loader audit in Stage 19BB established that the
real tested loader path also depends on two additional non-canonical support
tables:

- `enrichment_source_files`;
- `enrichment_raw_records`.

That Stage 19BB correction does not rewrite Stage 19BA history and does not
claim Stage 19BA previously authorized five-table execution. It records that
the real execution boundary for the later exact authorization lane is five
tables, not three, while canonical tables remain forbidden.

Everything else is forbidden for this lane. In particular, this checkpoint does
not authorize writes to:

- `systems`;
- `stations`;
- `bodies`;
- `body_rings`;
- `station_body_links`;
- `body_scan_facts`;
- `observed_facts`;
- materialized views;
- any canonical promotion/apply table.

## Conservative Initial Activation Boundary

The initial proposed boundary is intentionally stricter than Stage 19AV:

- row cap: `100`;
- maximum runtime: `900` seconds;
- malformed-row threshold: `0` tolerated rows before hard failure;
- automatic retry: disabled;
- overlapping run: forbidden;
- scheduler/service invocation: forbidden;
- canonical apply: unauthorized;
- rebaseline: unauthorized.

The `100` row cap is chosen because the repo already proved a safe local
staging-only `250` row lane in Stage 19AV. The first production-staging
activation should reopen below that proof size, not above it.

## Transaction And Rollback Requirements

- default mode must be dry-run/no-write;
- `--commit` must be explicit;
- an activation-specific confirmation flag must also be explicit;
- write-capable execution must run inside the existing bounded staging helper
  transaction model;
- failures must roll back the attempted staging transaction;
- no canonical transaction may be opened;
- resumability is limited to staging/source-run ledger recovery and does not
  authorize automatic retries.

For this baseline wrapper specifically:

- dry-run is filesystem-non-mutating;
- the wrapper must not create the artifact directory during dry-run;
- unauthorized `--commit --confirm-stage19ba` refusal must occur before any
  filesystem mutation;
- actual artifact-directory creation belongs only to a later separately
  authorized execution path.

## Target And Secret Handling

- the production staging target must be supplied later through an approved
  operator-managed secret/environment mechanism;
- target shape validation alone is insufficient for execution authorization;
- a later execution gate must approve the exact reviewed target identity or an
  approved target fingerprint;
- exact production target approval remains a later gate;
- no production target is approved by this checkpoint;
- no production DSN may be committed in docs, authority, tests, or code;
- full DSNs and secrets must never be printed;
- secret output is forbidden;
- direct host `5432` assumptions are forbidden;
- local `127.0.0.1:55432` is preserved as historical proof only and is not the
  production target for Stage 19BA.

## Source-Run Ledger And Artifact Requirements

Any future approved execution must create:

- a `source_runs` ledger record;
- the compatibility `enrichment_source_runs` bridge required by the current
  staging schema;
- a sanitized audit artifact in the operator artifact directory;
- source URI and source hash metadata;
- row counts, staging status, and failure classification metadata;
- artifact checksum/integrity fields.

Runtime source files and operator artifact JSON remain evidence only and are not
committed authority.

This baseline wrapper may validate and normalize a proposed artifact directory
reference, but it must not create that directory and must not write any audit
artifact.

## Overlap, Schema Drift, And Failure Stops

Any future approved execution must fail closed when:

- an overlapping active or failed Stage 19 run is present;
- staging/source-run schema expectations drift from the reviewed contract;
- the source hash is missing or malformed;
- the source identity does not match the approved EDSM contract;
- the target shape is unsafe or ambiguous;
- the row cap or runtime cap is exceeded;
- malformed rows exceed the initial threshold of `0`.

## Operator Review Requirements

Before any future execution:

- operator review must confirm the exact target is production-staging only;
- operator review must confirm the supplied source URI and source hash;
- operator review must confirm the row cap and runtime cap;
- operator review must confirm no overlapping Stage 19 run is active;
- operator review must confirm Stage 23B still depends on successful bounded
  activation rather than inferred warehouse state.

## Post-Run Verification

Any future approved execution must verify:

- staging writes occurred only in the exact later-reviewed boundary for the
  selected execution lane;
- Stage 19BB's exact execution lane narrows that executable boundary to:
  `source_runs`, `enrichment_source_runs`, `enrichment_source_files`,
  `enrichment_raw_records`, and `staging_edsm_stations`;
- row counts match the approved cap and source-run ledger;
- the audit artifact checksum matches the ledger record;
- no canonical table write occurred;
- no canonical apply ran;
- no rebaseline ran;
- no scheduler/service change occurred.

## Stage 23 Dependency

Stage 23 remains the active product/evidence roadmap. Stage 23B is blocked on a
successful bounded production-staging activation or an equivalent future
reviewed proof. Until then, warehouse evidence remains a separate operational
dependency rather than assumed product truth.

## Explicit Non-Authorization

Stage 19BA does not authorize:

- production-staging execution in this checkpoint;
- canonical apply;
- rebaseline;
- scheduler, timer, or service activation;
- automatic retries;
- source acquisition;
- canonical table writes;
- full production automation.

Next explicit action after this baseline is operator approval/review, followed
by a separate reviewed execution decision if the lane is still needed.

