# EDSM Data Audit

Date: 2026-05-25

This audit covers how ED-Finder should use EDSM system, station, and body data
to improve coordinate truth, station/body association, and occupied-slot
confidence without adding bulk imports yet.

## Sources Checked

- EDSM nightly dumps: https://www.edsm.net/en/nightly-dumps
- EDSM Systems API v1: https://www.edsm.net/en/api-v1
- EDSM System API v1, bodies/stations: https://www.edsm.net/en_GB/api-system-v1

Relevant EDSM surfaces:

- `systemsWithCoordinates.json.gz`: full systems-with-known-coordinates dump.
- `systemsWithCoordinates7days.json.gz`: recent coordinate changes.
- `systemsWithoutCoordinates.json.gz`: explicit unknown-coordinate coverage.
- `systemsPopulated.json.gz`: populated system metadata.
- `stations.json.gz`: full station dump.
- `bodies7days.json.gz`: recent body changes. The public nightly page does not
  list a current full bodies dump, so full body enrichment should stay
  per-system or incremental unless a full artifact is confirmed.
- `/api-v1/system` and `/api-v1/systems`: coordinate and system metadata probes.
  EDSM omits the `coords` key when coordinates are unknown.
- `/api-system-v1/bodies`: per-system body payloads with body ids, body names,
  physical fields, orbital fields, and rings.
- `/api-system-v1/stations`: per-system station payloads with station id, name,
  type, arrival distance, economy, market/shipyard booleans, and faction. The
  documented station payload does not show exact `bodyId` or `bodyName`.
- `/api-system-v1/stations/market|shipyard|outfitting`: station detail by
  `marketId`, useful for identity checks but not a station/body link on its own.

## Current ED-Finder State

Primary import is Spansh through `apps/importer/src/import_spansh.py`.
EDDN fills `journal_events` and `body_scan_facts` for simulation-relevant body
facts. System coordinates are now nullable, and API helpers avoid presenting
non-Sol `(0,0,0)` as real coordinates.

Occupied-slot association is moving to `station_body_links`:

- `confirmed`: exact or manually verified station/body association.
- `inferred`: deterministic but reviewable association, currently unique
  distance match or equivalent.
- `unresolved`: station is real, but ED-Finder cannot prove its body/lane.

This is the right shape for EDSM. EDSM should add evidence and confidence, not
write directly over core truth.

## Findings

1. EDSM is strongest as an independent coordinate witness.

   `systemsWithCoordinates7days.json.gz` is a low-risk daily reconciliation
   source. EDSM's API contract also makes unknown coordinates explicit by
   omission of `coords`, which matches ED-Finder's nullable-coordinate rule.

2. EDSM station data can improve station identity and lane classification, but
   not exact station/body association from the documented endpoint alone.

   The documented stations endpoint exposes `type` and `distanceToArrival`;
   examples include `Coriolis Starport` and `Planetary settlement`. That is
   enough to classify orbital/surface lane and compare station arrival
   distance, but not enough to mark an exact body link unless the dump contains
   extra `bodyId` or `bodyName` fields.

3. EDSM body data can improve slot prediction inputs for recently changed or
   weakly populated bodies.

   The per-system bodies endpoint includes radius, gravity, landability,
   surface temperature, atmosphere, terraforming state, volcanism, and rings.
   Those map directly to `validated-slot-v1` inputs. EDSM bodies should fill an
   evidence table or `body_scan_facts` with a distinct source/confidence; they
   should not bypass the canonical slot predictor.

4. ED-Finder must split source ids from game ids before relying on EDSM for
   exact links.

   `systems.id64` is the game system address. EDSM also has internal system ids.
   EDSM body examples use both `id` and `bodyId` depending on endpoint. Current
   `bodies.id` is populated from Spansh `id64/id/bodyId`, so ED-Finder should
   add explicit source-id columns/tables instead of assuming all ids are the
   same namespace.

## Schema Recommendations

Do not add EDSM rows directly into core tables during the first phase. Add
source/evidence scaffolding first.

### Coordinate Evidence

Add an append/upsert table:

```sql
CREATE TABLE system_coordinate_evidence (
    system_id64 BIGINT NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    source TEXT NOT NULL,
    source_system_id BIGINT,
    source_name TEXT,
    x REAL,
    y REAL,
    z REAL,
    source_updated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    coordinate_status TEXT NOT NULL DEFAULT 'known',
    confidence TEXT NOT NULL DEFAULT 'external_exact',
    PRIMARY KEY (system_id64, source, payload_hash)
);
```

Then expose a current view or materialized view:

- one row per system/source
- latest `fetched_at`
- delta from `systems.x/y/z`
- status: `matches`, `fills_null`, `conflict`, `source_unknown`

Only promote EDSM coordinates into `systems` when:

- current ED-Finder coordinates are null, or
- current coordinates match EDSM within a tiny tolerance, recommended
  `<= 0.001 ly`, and the update only refreshes provenance.

Queue review when both sides are known and differ by more than tolerance.

### Source Snapshots

Add one operational table for every downloaded artifact:

```sql
CREATE TABLE external_source_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    artifact_name TEXT NOT NULL,
    artifact_url TEXT NOT NULL,
    generated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sha256 TEXT NOT NULL,
    size_bytes BIGINT,
    row_count BIGINT,
    status TEXT NOT NULL,
    notes TEXT,
    UNIQUE (source, artifact_name, sha256)
);
```

This lets operators prove which EDSM dump informed a coordinate or station
decision.

### Station Evidence

Add source-specific station evidence rather than extending `stations` first:

```sql
CREATE TABLE station_source_evidence (
    source TEXT NOT NULL,
    source_station_id BIGINT,
    source_system_id BIGINT,
    system_id64 BIGINT NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    market_id BIGINT,
    station_name TEXT NOT NULL,
    station_type_raw TEXT,
    station_type_normalized TEXT,
    distance_to_arrival REAL,
    body_id BIGINT,
    body_name TEXT,
    primary_economy TEXT,
    have_market BOOLEAN,
    have_shipyard BOOLEAN,
    source_updated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (source, source_station_id, payload_hash)
);
```

Recommended later additions to `stations` after evidence proves stable:

- `market_id BIGINT`
- `source_ids JSONB`
- `source_last_seen JSONB`

Do not assume `stations.id == market_id` forever.

### Body Evidence

Add body source-id and scan evidence without changing the slot algorithm:

```sql
CREATE TABLE body_source_evidence (
    source TEXT NOT NULL,
    system_id64 BIGINT NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    body_id BIGINT REFERENCES bodies(id) ON DELETE SET NULL,
    local_body_id INTEGER,
    source_body_id BIGINT,
    body_name TEXT NOT NULL,
    distance_to_arrival REAL,
    radius REAL,
    gravity REAL,
    surface_temp REAL,
    atmosphere_type TEXT,
    volcanism TEXT,
    terraforming_state TEXT,
    is_landable BOOLEAN,
    is_ringed BOOLEAN,
    parents JSONB,
    rings JSONB,
    source_updated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (source, system_id64, source_body_id, payload_hash)
);
```

Later, promote EDSM body facts into `body_scan_facts` only with:

- `data_sources` containing `edsm_bodies_api` or `edsm_bodies7days`
- confidence below live DSS/EDDN scan confidence, recommended `0.60-0.75`
- no overwrite of higher-confidence EDDN facts with null/older fields

### Station Body Links

Keep `station_body_links` as the planner source of truth. Add EDSM-specific
source values when migration timing permits:

- `edsm_body_id`
- `edsm_body_name`
- `edsm_distance`
- `edsm_station_dump`
- `edsm_stations_api`

Recommended extra columns:

- `source_updated_at TIMESTAMPTZ`
- `last_seen_at TIMESTAMPTZ`
- `evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb`

Exact EDSM body id/name links can be `confirmed`. Distance-only links remain
`inferred` and must carry resolver notes.

## API Recommendations

Add source metadata, not raw dumps, to user-facing APIs.

`GET /api/system/{id64}`:

- add `coordinate_truth`:
  - `status`: `known`, `unknown`, `conflict`, `filled_from_external`
  - `source`: current promoted source
  - `checked_at`
  - `external_sources`: compact list of source/status/delta
- add `occupied_slot_summary`:
  - per body id and lane
  - `confirmed_count`
  - `inferred_count`
  - `unresolved_count`
  - `confidence_label`
  - `sources`
- keep station-level fields already planned:
  - `association_status`
  - `association_confidence`
  - `association_source`
  - `resolver_notes`

Admin/probe endpoints:

- `POST /api/admin/data-sources/edsm/probe-system`
  - input: `system_id64` or system name
  - output: coordinate/body/station diff only
  - no writes unless `apply_evidence=true`
- `GET /api/admin/data-sources/edsm/snapshots`
  - latest artifact metadata and row counts
- `GET /api/admin/data-sources/edsm/conflicts`
  - coordinate conflicts and station/body unresolved summaries

Do not put EDSM network calls on normal user request paths. Probe endpoints
should cache evidence and be operator-gated.

## Occupied-Slot Confidence Rules

Planner capacity should combine predicted/observed capacity with known
infrastructure occupancy:

- Capacity source:
  - `observed` beats `predicted`
  - `predicted` beats `unknown`
  - EDSM body facts can improve prediction inputs but do not create observed
    slot counts
- Occupancy source:
  - exact body id/name/manual link: consumes slot as confirmed
  - EDSM or Spansh unique distance match: consumes lane with warning as inferred
  - unresolved body or unknown lane: visible infrastructure, does not consume a
    body slot
  - fleet carriers/megaships: visible infrastructure, not permanent colony
    occupancy unless a separate future model proves otherwise

Recommended confidence labels:

| Capacity | Occupancy | Planner Label |
|---|---|---|
| observed | confirmed | verified |
| predicted | confirmed | high |
| predicted | inferred | review |
| unknown | confirmed | occupied-known-capacity-unknown |
| any | unresolved | unresolved-infrastructure |

## Runbook Recommendation

Phase 0 - no import:

1. Keep EDSM URLs out of `DUMP_FILES` and nightly jobs.
2. Add schema migrations for evidence tables only.
3. Add station type normalization tests for EDSM labels.
4. Add a dry-run probe script later, but do not schedule it.

Stage 17N.2d-I keeps this phase light. EDSM should be used as targeted
evidence, not as a live user-path dependency:

- No normal UI/API request should call EDSM over the network.
- Do not schedule or run a bulk `stations.json.gz` import until a staging host
  proves disk use, parser behaviour, row counts, and conflict reports.
- Add a small operator-only enrichment command later with a shape like
  `--system-id64 <id64> --dry-run`. It should fetch one system, write or print
  evidence/diff output, and leave core `stations` / `station_body_links`
  untouched unless a later apply mode is explicitly designed.
- The first production-safe target is one known unresolved system at a time,
  comparing EDSM station `marketId`, `name`, `type`, `distanceToArrival`, and
  any `body` / `bodyName` field the source actually returns.
- EDSM `type` labels can improve lane classification through the same
  whitelist as Spansh labels. Unknown or unmapped labels remain `Unknown`.
- EDSM `body` / `bodyName`, if present, can support a confirmed
  `station_body_links` proposal only when it matches exactly one ED-Finder body
  in the same system.
- EDSM distance-only evidence can support only an `inferred`
  `resolver_distance` proposal when exactly one body is within tolerance.
- EDSM `marketId` can improve station identity checks, but ED-Finder should not
  assume forever that `stations.id == marketId`; keep source ids in evidence
  until the namespace is proven.
- Conflicts are review items, not automatic overwrites. Preserve existing
  confirmed/manual links, keep weaker EDSM evidence labelled as inferred, and
  report mismatched station type/body/distance/source ids in dry-run output.

Phase 1 - one-system probe:

1. Fetch one known system by API only.
2. Store evidence snapshots, not core table changes.
3. Diff:
   - EDSM coords vs `systems`
   - EDSM body ids/names vs `bodies`
   - EDSM station ids/names/types/distances vs `stations`
   - proposed `station_body_links` changes
4. Require zero coordinate conflicts and explain every proposed inferred link.

Phase 2 - small incremental files:

1. Download `systemsWithCoordinates7days.json.gz` and record sha256.
2. Parse only enough rows to compute coordinate diff counts.
3. Download `bodies7days.json.gz` only after coordinate diffing is stable.
4. Do not download `stations.json.gz` in production until disk, parser, and
   row-count telemetry have been proven on a staging host.

Phase 3 - station evidence:

1. Run a station API probe on 10 systems with known unresolved infrastructure.
2. Record how many station rows match by market id, name, and distance.
3. Promote no links automatically unless an exact body id/body name exists.
4. Use distance-only matches to reduce unresolved review queues, not to create
   silent confirmed occupancy.

Stop conditions:

- EDSM coordinate differs from current known coordinate by `> 0.001 ly`.
- EDSM source ids do not match expected namespaces.
- More than one body matches a station distance within tolerance.
- EDSM station type cannot be normalized to a known lane.
- Any parser would overwrite a higher-confidence EDDN scan field with null.
- Artifact row count, sha256, or generated timestamp is missing.

Verification queries after evidence-only rollout:

```sql
SELECT status, count(*)
FROM external_source_snapshots
WHERE source = 'edsm'
GROUP BY status;

SELECT coordinate_status, count(*)
FROM system_coordinate_evidence
WHERE source = 'edsm'
GROUP BY coordinate_status;

SELECT association_source, association_status, association_confidence, count(*)
FROM station_body_links
GROUP BY association_source, association_status, association_confidence
ORDER BY association_source, association_status, association_confidence;
```

## Small Tests Added

The first safe test layer should remain parser/resolver-only:

- EDSM-style station labels classify correctly:
  - `Coriolis Starport` -> orbital
  - `Orbis Starport` -> orbital
  - `Ocellus Starport` -> orbital
  - `Planetary settlement` -> surface
  - `Fleet Carrier` -> unknown/non-permanent
- The importer station-type normalizer accepts the same labels without adding
  EDSM dumps to the active download list.

These tests reduce future EDSM ingestion risk without importing any EDSM data.
