# Ratings V4 production integration

Status: implementation in progress after architecture PR #645 and freeze PR #646
merged on 2026-09-08. No production derived generation has been published.

## Source recovery

The retained `v3_spansh` package has been restored byte-for-byte from
`/data/v3/phase4c-correction-gate/repo/apps/importer/src/v3_spansh` on
`ed-finder-prod`. The combined sorted Python-file checksum is
`b5bf4e0c62a75e10bf6e3dfb6dc1934353f09e18afabcddbbb706e8277238d53`;
the normalizer checksum is
`e9d86fbea1bad3049f2ab9e93e51da9eb1ca681a631ed049dee833d185820f24`.
Both exactly match the published canonical source-run metadata. Individual file
checksums and the source location are recorded in
[`v3-canonical-source-recovery.json`](v3-canonical-source-recovery.json).

The recovered baseline SQL matches the live migration ledger checksum
`ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e`.
Its original comments, versions and lab entry points remain historical source
evidence. Recovery does not turn the old lab runner into a production operation,
reapply the baseline, or permit rewriting published canonical relations.

## Verified production scale and compatibility

Read-only inventory on 2026-09-08 identified PostgreSQL 18.6 and canonical
generation `a7076522-54cd-52f3-a291-4e5406bea230`, publication sequence 4.
Its validation receipt records 198,528,286 systems, 598,724,752 bodies and
93,642,930 ring/belt rows. The database occupies approximately 608 GB.

The retained database is `edfinder_v3_phase4c_full_20260827_r5`, with role
`edfinder_v3`. The canonical migration ledger is `v3_meta.schema_migration`;
`public.schema_migrations` does not exist. The inventory helper previously
assumed the historical database/ledger and is corrected to inspect the actual
V3 ledger, including its `r1_v3/001_structural_shell.sql` entry.

This inventory correction does not establish compatibility for the application
deployer: its legacy migration-set expectations still need a separately
verified V3 schema contract. The stopped production target stays stopped until
all release facts and the migration authority are established.

## Canonical input bridge

[`canonical_stream.py`](../../scripts/ratings_v4/canonical_stream.py) pins the
canonical pointer and source metadata in one read snapshot. Subsequent chunks
read that immutable generation even if the current pointer changes. Chunk
system/body counts and database query time are bounded.

The snapshot retains every `canonical_generation_input` entry in admission
order, with its run, source and optional artifact metadata, including inputs
with no rows in a particular chunk. Canonical rows must reference an admitted
run and retain that run's provenance and inventory completeness. Relation reads
use stable identity ordering so scan plans cannot alter output or content hashes.

PR #647's review repair extends the adapter to this explicit multi-run manifest.
Only the adapter implementation checksum in the freeze manifest is repinned;
the scorer, mechanics, coefficients, retained source fixtures, 84 cohort outputs
and derived-input hashes remain unchanged. Historical single-source exports
retain their exact frozen facts and lineage.

The retained compressed source is streamed and hashed as read. Only successful
EOF with the exact expected byte count and SHA256 produces an acquisition
receipt. A cancelled, truncated or corrupt stream cannot establish completeness.
Staged work before EOF is therefore not eligible for READY or publication.

Only `subType` is enriched from this source. The bridge requires exact system,
source-body and Frontier-body joins, then delegates all mechanics inputs to the
frozen canonical adapter. The field provenance identifies the retained artifact
and compact classification projection, rather than incorrectly calling it an
API response. Reserves remain body-scoped, absent rings remain unknown, signal
absence depends on explicit completeness, and usable ground remains unknown.

The freeze cohort's newer API responses exercise bridge equivalence in tests;
they are not represented as original full-galaxy artifact bytes. Production
coverage must come from the separately hash-verified retained artifact.

## Remaining production work

1. Implement compact, immutable generation storage and a bounded resumable
   builder. Do not scale the disposable proof's repeated JSON lineage to hundreds
   of millions of bodies.
2. Validate all-source coverage, score parity, explanations, measured resources,
   publication compare-and-swap and rollback in PostgreSQL 18.
3. Establish the reviewed migration/runtime/release authority, build and validate
   the complete generation, then expose it through a generation-pinned V3 API.

Ratings V4.0 mechanics and coefficients remain frozen. Archetype judgement,
Finder ranking and practical buildability remain subsequent independent layers.
