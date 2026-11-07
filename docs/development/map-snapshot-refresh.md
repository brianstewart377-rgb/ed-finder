# Refreshing the real-data Galaxy map test

## Goal and current state

The local map stack in `docker-compose.map-test.yml` runs the release web image,
normal V3 API, PostgreSQL 18 and Redis. Its dataset must represent one coherent
published canonical generation and the spatial pyramid published for that same
generation. Search and nearby stars around the recorded camera paths also need
real catalogue and Finder rows. A small synthetic fixture cannot establish
that the density-to-star handoff matches the live Copilot map.

**No fresh database archive has been captured by this PR.** There is no current
approved map-only production export path, and the production backup (1,252.9 GB
on 2026-10-18) includes other data. The V3 recovery documentation explicitly
does not authorize repository-driven backup restoration. Do not use the retired
V2 restore scripts or copy the production database into the test stack. The
export described below is a separate, read-only, reviewed data operation, not
a recovery or production deployment procedure.

## Snapshot contract

Build a new custom-format PostgreSQL 18 archive in an isolated staging database
from the current **published** catalogue and pyramid, using an explicit
relation allowlist. Preserve the map-serving schema and the ordinary Finder
search dependencies required by the Product journey. Include every published
spatial level, not just one chosen zoom, and the real catalogue coverage of
the six recorded camera paths (including Achenar and its surrounding viewports).
The test manifest records the level used for its density canary. Do not include
rows from `v3_identity`, `v3_private`, journals, auth, accounts, tokens or
operator/control-plane data. A reviewed inventory of every `TABLE DATA` entry
and a privacy review of selected columns are required; schema names alone do
not establish that a field is safe to export.

There are two honest coverage levels:

| Level | Data | What it establishes |
| --- | --- | --- |
| Camera-path acceptance | Complete real density pyramid plus real canonical stars/bodies and Finder rows for the recorded journeys | Renderer, handoff, search and navigation on those paths. Other regions are out of scope. |
| Whole-galaxy acceptance | Complete real density pyramid and complete published canonical catalogue/search data | Arbitrary pans and zooms against the same generation. Size and query time require a capacity check and may need a dedicated test host. |

The first archive should target camera-path acceptance, while the ordinary
synthetic Product E2E and Review Lab continue to catch deterministic failure
cases. Never label a bounded catalogue as whole-galaxy coverage. The manifest
and test report must carry the coverage level and viewport coordinates.

## Capture sequence for an authorized operator

1. Identify the current V3 production target and an explicitly reviewed,
   read-only map-export procedure. Check disk, transfer, query and privacy
   budgets before starting. Keep production credentials out of the archive and
   logs. This PR does not grant access or execute production commands.
2. In one consistent source snapshot, record the canonical generation ID,
   relation schema, publication sequence, spatial generation ID, pyramid
   version, spatial publication sequence, and Finder product pointers. Confirm
   the spatial generation is `PUBLISHED` and references that canonical ID.
   Refuse a pointer change while collecting data; restart against the new pair.
3. Export only the approved relation and column closure for map, search and
   spatial reads. Stage it in an isolated PostgreSQL 18 database with the
   reviewed V3 schema. Check that all referenced rows and indexes needed by
   the normal API exist. Keep the original IDs, coordinates, main-star
   spectral class, counts and cell values. Do not fabricate a missing region.
4. Run the normal API against staging and prove `/api/map/heatmap` serves
   `source=pyramid`, `coverage=complete` with no truncation at the tested
   views; `/api/map/systems` serves the star view; the Achenar autocomplete and
   search resolve the selected system. Compare published IDs and counts with
   the source receipt. Then make a custom-format archive of **staging**, not a
   whole-production backup.
5. Produce a sidecar JSON manifest with the exact archive SHA-256 and explicit
   data-relation inventory. Run `scripts/dev/map_snapshot_check.py archive`
   against it, restore into an empty disposable local database, then run
   `scripts/dev/map_snapshot_check.py local` and the Product browser test.
   Inspect the submitted Babylon frames beside the owner's six recordings.
6. Retain the current and previous accepted snapshots in restricted storage,
   with their manifests and test evidence. The archive and manifest are not
   committed to Git. Destroy rejected staging databases and temporary copies
   under the operator's approved retention procedure.

The manifest format expected by the local checker is:

```json
{
  "format": "edfinder-map-snapshot/v1",
  "captured_at": "2026-11-07T00:00:00Z",
  "sha256": "<64 lowercase hex characters of the archive>",
  "generation_id": "<published canonical UUID>",
  "canonical_publication_sequence": 1,
  "relation_schema": "v3_gen_<published key>",
  "spatial_generation_id": "<published spatial UUID>",
  "spatial_publication_sequence": 1,
  "spatial_pyramid_version": "<published version>",
  "derived_generation_id": "<published Finder/Ratings UUID>",
  "derived_publication_sequence": 1,
  "source_system_count": 1,
  "level": 0,
  "level_cell_count": 1,
  "coverage_level": "camera-path",
  "camera_paths": ["<reviewed viewport coordinates and recording ID>"],
  "data_relations": ["<every TABLE DATA relation in pg_restore --list>"]
}
```

The numeric `1` values above are placeholders, never an acceptable real-map
fixture. Record actual published counts. The checker compares the archive
bytes, the explicit inventory and the restored published pointers; it is a
structural gate, not an automatic privacy certification.

## Keeping it current

- Check the canonical, spatial and Finder publication markers weekly and
  whenever a new dataset is published. A changed marker calls for a new
  capture. A code-only change needs a new browser run at the exact release
  build SHA, not necessarily another data export.
- Refresh a camera-path archive at least every 30 days even if the pointers
  have not moved, then compare source counts, coverage, canary responses,
  screenshot frames and archive size with the prior accepted manifest.
- For each proposed release, run the real-data Product journey with the latest
  accepted archive and record build SHA, archive SHA-256, generation IDs,
  capture date, Chrome result, frames and any known untested regions. Mark a
  snapshot stale if its published markers differ from the current source or
  its 30-day interval has elapsed. Do not silently fall back to a seeded run.
- Keep the previous accepted archive until the new one passes restore,
  pointer checks, API canaries and visual review. Revert the local test stack
  to the previous archive if the new export fails; investigate source or
  export changes before calling the release tested.

The next implementation step is a reviewed, narrow map-export operator path
that can produce the first archive and a measured staging rehearsal. Until
that path exists, this is a ready-to-run **consumer and acceptance contract**,
not a claim that a fresh snapshot or real-data browser pass has happened.

## Operator path to implement before the first capture

The current V3 operator surface has a bounded read-only inventory operation,
but no map-data export or approved transfer destination. A production backup
restore is not the export path. Add a dedicated protected, manual operation on
trusted `main` with two phases: a metadata/capacity **plan** that exports no
rows, then a separately dispatched **capture** bound to that exact plan and
source commit. It must verify the replacement-host identity and use a fixed
read-only database role or read-only transaction. The caller must not supply
SQL, a relation name, a filesystem path, a host, or a destination.

The fixed data graph for the initial camera-path slice is:

| Reader | Required published data |
| --- | --- |
| `/api/map/heatmap` | `v3_spatial.current_spatial_generation`, its `spatial_generation`, matching `cell_level` and all `cell_summary` levels |
| `/api/map/systems` | `v3_meta.current_canonical_generation`, its `canonical_generation`, and bounded real `systems` and `bodies` rows in that generation's validated `v3_gen_*` schema |
| Finder search and autocomplete | `v3_meta.current_derived_generation`, its `derived_generation`, two READY/published `derived_product` rows, and corresponding `v3_derived.system_search` and `system_archetype` rows plus the view/schema dependencies from the applied migration set |

The operator must derive the exact row and column allowlist from those readers
and the current SQL definitions, then review foreign-key and view dependencies.
That review must explicitly inspect source provenance and free-text/JSON
columns for indirect personal data; rejecting `v3_identity` and `v3_private`
schemas is necessary but insufficient. Use a consistent source snapshot so
the three publication pointers cannot describe different moments. Recheck the
pointer triple before accepting the export and fail if it moved.

The plan phase must report estimated row counts and bytes for every selected
relation, the camera-path coordinate boxes, a maximum query time and source
load budget, free space in staging and the destination, and a privacy-approved
transfer/retention location. A whole-galaxy catalogue is approximately 198.5
million systems in the current production lineage, so it is a separate
capacity decision; a camera-path slice must not be called complete galaxy
coverage. Capture must refuse missing capacity, destination authority,
privacy approval, a changed source generation, or an unreviewed relation.
Transfer the reviewed staging archive and receipt only through that approved
destination; never through public Git, routine CI logs, or a generic workflow
artifact. Once the local consumer passes its hash, inventory, pointer, API and
visual gates, record the accepted archive identity and schedule the next
marker/30-day check.

