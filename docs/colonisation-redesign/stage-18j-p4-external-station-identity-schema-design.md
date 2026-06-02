# Stage 18J-P4 — External Station Identity Schema Design

## Purpose

Stage 18J-P4 designs the external station identity schema needed before the
strict Stage 18J station-type dry-run can prove identity with explicit external
identifiers.

This stage is docs/design only. It does not add a live SQL migration under
`sql/`, run production commands, touch the production database, run imports,
run reconciliation, run the summarizer against production artifacts, run
station-type dry-run, run canonical apply, create approval records, or start
Stage 18K.

## Current Blocker

Stage 18J-P2 and Stage 18J-P3 confirmed the blocker:

- canonical `stations` has no `market_id`;
- canonical `stations` has no `edsm_station_id`;
- existing `s.id AS market_id` projections are compatibility aliases and
  update targets, not explicit external identity proof;
- `station_body_links.market_id` is association-scoped and not a general
  external station identity registry;
- the strict station-type filter correctly produces zero eligible candidates
  while confirmed canonical external identity is unavailable.

The blocker is therefore a data-model gap, not a dry-run filter bug.

## Why Not Relax The Strict Filter

The strict filter protects a canonical write-capable path. It must not accept:

- station-name-only matches;
- system/name matches without an external identifier match;
- source-only EDSM station IDs with no canonical-side identity;
- internal `stations.id` equality;
- proposed, conflicting, stale, or warehouse source-only identity evidence.

Station names can collide, be renamed, drift between sources, or be normalized
differently across snapshots. Warehouse evidence is source evidence until it is
reconciled and confirmed. Relaxing the filter would turn the missing identity
model into silent write eligibility, which is the unsafe outcome the P2
diagnostics prevented.

## Why Not Reuse stations.id As market_id

`stations.id` is the canonical station primary key and update target. Existing
queries sometimes project `s.id AS market_id` for compatibility with older
payload shapes, but that projection does not prove the value came from an
external market identifier source.

Treating `stations.id` as an external `market_id` would:

- hide whether the value was ever observed in EDSM or another external source;
- make compatibility payload shape look like identity evidence;
- prevent provenance and freshness review;
- make future conflicts hard to detect;
- encode a historical assumption as a write eligibility rule.

The model needs explicit external identity evidence, not an implicit primary-key
reinterpretation.

## Why Not Use station_body_links As General Identity

`station_body_links` models the association between a station and a body or
occupied slot. Its nullable `market_id` is scoped to that association evidence.
It is not a general station external identity model.

Using `station_body_links` as the identity registry would conflate two separate
questions:

- which external station identifier maps to this canonical station;
- which body or slot association is supported for that station.

The future identity model should support station/body link evidence, but it
must not make association evidence the owner of station identity. Conflicts in
body association should remain visible without blocking unrelated identity
review, and identity conflicts should remain visible without implying a body
association write.

## Recommended Model

Use a separate provenance-backed table named `station_external_identity`.

The table records confirmed and unconfirmed evidence that a canonical station
maps to one or more external station identifiers. It is separate from
`stations` so external IDs can carry source provenance, confidence, freshness,
status, and conflict state without making provisional source evidence look like
canonical station attributes.

Design rules:

- do not treat warehouse source-only evidence as canonical identity by default;
- do not accept name-only matches as proof;
- do not accept internal `stations.id` equality as external identity proof;
- preserve source run, source file, and source record hash provenance;
- make conflicting `market_id` or `edsm_station_id` evidence visible and
  blocked;
- allow only `confirmed` rows to serve as read-only reconciliation proof;
- keep station-type canonical writes blocked until confirmed external identity
  is available;
- support future station/body link evidence without conflating identity with
  association.

## Proposed Table Shape

This is a design sketch, not a live migration:

```sql
CREATE TABLE station_external_identity (
    id BIGSERIAL PRIMARY KEY,
    canonical_station_id BIGINT NOT NULL,
    system_id64 BIGINT NOT NULL,
    station_name TEXT NOT NULL,
    source TEXT NOT NULL,
    market_id BIGINT,
    edsm_station_id BIGINT,
    source_run_key TEXT NOT NULL,
    source_file_key TEXT NOT NULL,
    source_record_hash TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ,
    evidence_first_seen_at TIMESTAMPTZ NOT NULL,
    evidence_last_seen_at TIMESTAMPTZ NOT NULL,
    confidence TEXT NOT NULL,
    freshness_class TEXT NOT NULL,
    identity_status TEXT NOT NULL,
    conflict_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
```

Recommended constraints for a later migration draft:

- `canonical_station_id` references `stations(id)`;
- `system_id64` references `systems(id64)`;
- at least one of `market_id` or `edsm_station_id` must be present;
- `identity_status` is limited to the status model below;
- active confirmed identities should not allow the same `(source, market_id)`
  or `(source, edsm_station_id)` to map to multiple canonical stations;
- conflicting evidence should remain stored, but blocked from proof use.

The final migration draft should choose exact index names, timestamp defaults,
and trigger/update mechanics. P4 intentionally does not add that migration.

Stage 18J-P5 follows this design with the draft additive migration
`sql/027_station_external_identity.sql`. P5 does not apply the migration to
production and does not backfill identity evidence.

## Identity Status Model

Recommended statuses:

| Status | Meaning | May prove canonical external identity? |
|---|---|---:|
| `proposed` | Evidence suggests a mapping, but it has not passed confirmation rules. | No |
| `confirmed` | Evidence passed the identity stage rules and can be used by read-only reconciliation as canonical external identity. | Yes |
| `conflicting` | Evidence conflicts with another active external ID, canonical station, system, name, or source record. | No |
| `rejected` | Evidence was reviewed or classified as not acceptable proof. | No |
| `superseded` | Historical mapping retained for audit after a newer confirmed mapping replaced it. | No |

Only `confirmed` rows should satisfy Stage 18J station-type external identity
proof. All other statuses should remain visible in coverage and diagnostics.

## Source / Provenance Fields

External identity rows must retain enough provenance to explain why the mapping
exists:

- `source`: source adapter or evidence family, for example an EDSM nightly
  station snapshot;
- `source_run_key`: warehouse source-run identifier;
- `source_file_key`: warehouse source-file identifier;
- `source_record_hash`: deterministic hash of the source station evidence;
- `source_updated_at`: source-side update timestamp when available;
- `evidence_first_seen_at`: first time this exact mapping evidence was seen;
- `evidence_last_seen_at`: latest time this mapping evidence was seen.

These fields keep identity review auditably tied to the warehouse evidence
layer. They also prevent a confirmed identity from becoming an unexplained
column value on `stations`.

## Confidence And Freshness Fields

`confidence` should describe why the mapping is believed:

- exact external ID and same `system_id64`;
- exact normalized station name plus explicit external ID;
- repeated evidence across source runs;
- manually reviewed evidence, if a later stage permits manual review metadata.

`freshness_class` should describe whether the evidence is current enough for
use:

- `current`;
- `recent`;
- `stale`;
- `undated`;
- `unknown`.

Freshness is not identity by itself. Stale or undated rows can be retained for
audit and diagnostics, but the confirmation rules for write-adjacent
reconciliation should decide whether they are eligible to remain `confirmed`.

## Conflict Handling

Conflicts must be stored and blocked, not collapsed away.

Examples:

- one `market_id` maps to multiple canonical stations;
- one `edsm_station_id` maps to multiple canonical stations;
- one canonical station receives multiple active `market_id` values for the
  same source;
- one canonical station receives multiple active `edsm_station_id` values for
  the same source;
- external ID evidence matches a different `system_id64`;
- external ID evidence matches a different station name after normalization;
- source records for the same source identity disagree.

Rows with unresolved conflicts should be marked `conflicting` with
`conflict_reason` populated. They must not be accepted by the strict
station-type filter or by read-only reconciliation as canonical external
identity proof.

## Backfill Strategy

Backfill should be its own later stage and should not run station-type dry-run
or apply.

Recommended path:

1. Extract identity evidence from warehouse station snapshots and staged EDSM
   station rows.
2. Match only within the same `system_id64`.
3. Require explicit `market_id` and/or `edsm_station_id` evidence.
4. Require a deterministic source run key, file key, and source record hash.
5. Reject name-only matches.
6. Reject internal `stations.id` equality as proof.
7. Create `proposed` rows for evidence that is plausible but not yet
   confirmed.
8. Promote only rows that pass the confirmation rules to `confirmed`.
9. Mark conflicting evidence as `conflicting` and keep it out of proof use.
10. Emit a read-only coverage artifact before any production identity load.

Warehouse source-only evidence should remain source evidence until the identity
stage explicitly confirms it.

## Reconciliation Integration

Read-only reconciliation should eventually join confirmed identity rows to the
canonical station candidate and expose:

- `canonical.market_id`;
- `canonical.edsm_station_id`;
- `canonical.external_identity_status`;
- `canonical.external_identity_source`;
- `canonical.external_identity_confidence`;
- `canonical.external_identity_freshness_class`;
- `canonical.external_identity_source_run_key`;
- `canonical.external_identity_source_file_key`;
- `canonical.external_identity_source_record_hash`.

Rows in `proposed`, `conflicting`, `rejected`, or `superseded` status should be
reported for diagnostics, but they must not satisfy the strict identity proof
used by station-type dry-run eligibility.

## Station-Type Dry-Run Impact

Before confirmed external identity exists, the strict Stage 18J-P dry-run
should continue to produce zero eligible station-type update candidates.

After the identity table exists, is populated, and read-only reconciliation
exposes confirmed canonical external IDs, the station-type dry-run can be
retried as a separate operator stage. The filter should remain unchanged in
spirit:

- update-only station candidate;
- station-type delta only;
- exact external ID equality using confirmed canonical `market_id` or
  `edsm_station_id`;
- exactly one canonical match;
- matching `system_id64`;
- matching normalized station name;
- no volatile evidence;
- no transient or non-slot station type;
- explicit max-row bound;
- `canonical_writes_planned = 0` in dry-run output.

A non-zero eligible count still would not authorize apply. It would only feed a
later dry-run review packet.

## Non-Goals

This stage does not:

- add a live SQL migration under `sql/`;
- add columns to `stations`;
- populate `station_external_identity`;
- run production commands;
- touch the production database;
- run imports;
- run reconciliation;
- run the summarizer against production artifacts;
- run station-type dry-run;
- run canonical apply;
- create approval records;
- start Stage 18K;
- relax the strict station-type filter;
- accept warehouse source-only evidence as canonical identity;
- accept name-only matches as proof;
- accept internal `stations.id` equality as external identity proof;
- conflate station identity with station/body association.

## Migration Strategy

The next implementation stage should draft an additive migration only. It
should create the identity table and indexes without applying them to
production during the development stage.

Recommended migration-draft rules:

- table creation is additive;
- no rewrite of `stations`;
- no station-type writes;
- no backfill in the migration itself;
- no production apply in the development stage;
- rollback is table/index removal only before any identity load exists;
- tests should cover constraints, status values, and conflict-safe uniqueness.

The migration draft should remain separate from evidence extraction and
separate from any station-type dry-run retry.

Stage 18J-P5 implements this draft step in repo only. Production application is
still deferred to a later explicit readiness review and approval stage.

## Production Safety Gates

Before any production identity load or station-type dry-run retry, require:

- reviewed additive migration;
- staging or disposable database rehearsal;
- explicit source inventory;
- read-only identity evidence extraction report;
- conflict report with blocked conflicting IDs;
- coverage report proving confirmed canonical external IDs are available;
- no acceptance of source-only, name-only, or internal-primary-key proof;
- explicit operator prompt for any production step;
- `canonical_writes_planned = 0` for all dry-run artifacts until an approval
  packet is separately requested;
- no approval record until a later apply packet is explicitly approved.

## Recommended Next Stages

- Stage 18J-P5 - External station identity migration draft, not applied to
  production.
- Stage 18J-P6 - External identity evidence loader/reconciliation design.
- Stage 18J-P7 - External identity migration production readiness review.
- Stage 18J-P8 - Apply external identity schema migration only, if approved.
- Stage 18J-P9 - Load/reconcile identity evidence, no station-type writes.
- Stage 18J-P10 - Retry strict station-type dry-run with confirmed external
  identity.

## Final Recommendation

Proceed with a separate `station_external_identity` table design. Keep it
provenance-backed, status-aware, conflict-visible, and separate from both
`stations` and `station_body_links`.

Do not relax the strict station-type filter. Stage 18J station-type writes must
remain blocked until confirmed external identity rows exist, read-only
reconciliation exposes them, and a later dry-run review proves that eligible
candidates pass the unchanged identity boundary.
