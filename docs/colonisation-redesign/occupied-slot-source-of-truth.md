# Occupied Slot Source Of Truth

Stage 17N.2d-H adds the backend contract ED-Finder needs before Light /
Medium / High / Maxed plans can safely reason about already-built systems.

The core rule is conservative:

- **confirmed** means an exact/verified body association is known
- **inferred** means a deterministic resolver found one plausible body, but the
  planner must label it as inferred/verify
- **unresolved** means the station exists, but ED-Finder cannot prove its
  body/lane

Unresolved infrastructure must remain visible. It must not be forced into fake
body slots.

## Schema

Migrations:

- `sql/021_station_body_links.sql`
- `sql/023_station_data_provenance.sql`

The normalized table is `station_body_links`:

| Field | Meaning |
|---|---|
| `station_id` | FK to `stations.id`; current station identity |
| `market_id` | nullable market identity; currently mirrors `stations.id` where available |
| `system_id64` | owning system |
| `body_id` | nullable FK to `bodies.id`; never invented |
| `body_name` | matched/resolved body name when known |
| `lane` | `orbital`, `surface`, or `unknown` |
| `association_status` | `confirmed`, `inferred`, or `unresolved` |
| `association_confidence` | `exact`, `strong_inference`, `weak_inference`, or `unresolved` |
| `association_source` | `manual`, `import`, `eddn`, `resolver_body_id`, `resolver_body_name`, `resolver_distance`, `edsm_body_name`, `edsm_distance`, or `unknown` |
| `resolver_notes` | human-readable reason/caveat |
| `updated_at` | link update timestamp |

This is separate from `stations` because a station row can be valid while its
body/lane association is unknown.

## Resolver Order

Implementation: `apps/api/src/station_body_resolver.py`

Resolver order:

1. Existing verified `body_id` / `local_body_id` if present.
2. Trusted EDSM `body_name` provenance when it matches exactly one body in the
   same system. Legacy local `body_name` can only be inferred.
3. Unique `distance_from_star` match if station and body distances exist and
   exactly one body is within `0.01 ls`.
4. Otherwise unresolved.

Distance tolerance is intentionally tight because `distance_from_star` is not a
stable identity field. Legacy local station distance is weak evidence only and
can produce only `weak_inference`; EDSM/provenance-backed distance can produce
`strong_inference`. Distance-only evidence never creates a confirmed link. If
more than one body is within tolerance, the result is unresolved.

Existing confirmed links are preserved by default. A later weaker resolver pass
must not overwrite manual/confirmed truth unless the operator explicitly uses
`--overwrite-confirmed`.

## Lane Rules

Station labels are normalised with an explicit whitelist before lane
classification. The resolver intentionally does not use substring/fuzzy
classification; an unmapped label remains `Unknown` / lane `unknown`.

Orbital slot occupants:

- `Coriolis`
- `Coriolis Starport`
- `Orbis`
- `Orbis Starport`
- `Ocellus`
- `Ocellus Starport`
- `Outpost`
- `AsteroidBase`
- `Asteroid Base`

Surface slot occupants:

- `PlanetaryPort`
- `Planetary Port`
- `PlanetaryOutpost`
- `Planetary Outpost`
- `Planetary Settlement`
- `Settlement`
- `Surface Settlement`
- legacy Spansh surface labels already in the importer whitelist, such as
  `SurfaceStation`, `CraterPort`, and `CraterOutpost`

Unknown / not permanent colony-slot occupants:

- `FleetCarrier`
- `Fleet Carrier`
- `MegaShip`
- `Megaship`
- `Carrier`
- `Unknown`
- any unmapped label

Unknown-lane infrastructure remains visible but does not consume orbital or
surface capacity.

`FleetCarrier`, raw `Carrier`, and `MegaShip` rows may still carry diagnostic
station/body evidence for display or audit, but their lane remains `unknown`
and they do not occupy permanent colony slots.

## Stage 17N.2d-I Station Data Audit

Current station evidence paths:

- Schema: `stations.station_type` is a constrained enum with `Unknown` as the
  safe fallback; `stations.body_name` and `stations.distance_from_star` are
  nullable evidence fields, not proof of a body link.
- Spansh import: `apps/importer/src/import_spansh.py` is the only current
  repo-side importer that writes station rows. It normalises source labels into
  the enum, imports source arrival distance, and imports source body-name
  aliases when present. It does not import an exact station body id, and those
  imported station distance/body-name values remain legacy unless provenance is
  later added.
- EDDN listener: `apps/eddn/src/eddn_listener.py` currently updates systems and
  bodies from live journal events. It does not ingest station rows or station
  types, so it cannot repair `stations.station_type` or `stations.body_name`.
- API detail: `apps/api/src/routers/systems.py` reads stations and existing
  `station_body_links`; if no link exists, it runs the conservative resolver
  for that one response and labels the association status/confidence.

Why production can show `station_type='Unknown'`:

- Older inline Spansh station imports checked `type` and `station_type` but not
  `stationType`, while the station-refresh path checked all three. Source rows
  that only had `stationType` were therefore normalised from missing data.
- Any raw label outside the whitelist is deliberately stored as `Unknown`.
- If the source label is literally `Unknown` or blank, ED-Finder preserves that
  unknown instead of guessing orbital or surface.

Body association evidence quality:

- Exact `body_name` can be `confirmed` only when trusted provenance says it
  came from an exact EDSM station identity match and exactly one same-system
  body has the same normalised name. Legacy local `body_name` is inferred.
- Blank `body_name` stays unresolved unless distance evidence produces exactly
  one same-system body match.
- `distance_from_star` / `distanceToArrival` is imported as source evidence and
  can produce only `inferred` links. It never creates a confirmed link.
- Distance-only inference is rejected when more than one body falls within the
  tight resolver tolerance.
- Missing source fields needed for high confidence are: exact station body id,
  exact body name in the same namespace as `bodies.name`, source timestamp, and
  station identity fields such as stable `marketId` separate from source ids.

## API Contract

`/api/system/{id64}` station payloads expose:

- `id`
- `market_id`
- `name`
- `station_type`
- `distance_from_star`
- `distance_source`
- `distance_confidence`
- `station_type_source`
- `station_type_confidence`
- `body_name_source`
- `body_name_confidence`
- `station_body_name`
- `body_id`
- `body_name`
- `lane`
- `association_status`
- `association_confidence`
- `association_source`
- `resolver_notes`
- `primary_economy`
- `secondary_economy`
- `landing_pad_size`
- service flags

If `station_body_links` has not been migrated yet, the system-detail endpoint
falls back to the backend resolver for that one system and still emits explicit
association metadata. The frontend is not the source of truth for confirmed
occupancy.

## Backfill Command

Script: `apps/importer/src/backfill_station_body_links.py`

Dry run:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --dry-run --limit 10
```

Apply one known system:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --apply --system-id64 2008132031194
```

Gentle production batch:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --apply --limit 1000
```

Default behaviour preserves confirmed links. Use `--overwrite-confirmed` only
for a deliberate correction pass.

## Targeted EDSM Probe And Metadata-Only Apply

Script: `apps/importer/src/edsm_station_enrichment_probe.py`

Stage 17N.2d-J adds a one-system EDSM comparison probe. Stage 17N.2d-K adds a
metadata-only apply mode. Stage 17N.2d-L adds station data provenance and an
explicit confirmed-link apply flag. It is not a user-path API call, not a
scheduled importer, and not a bulk enrichment path.

Local run:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/edsm_station_enrichment_probe.py \
    --system-name Exioce --system-id64 2008132031194 --dry-run --json
```

Importer container run:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --dry-run --json
```

Metadata-only apply, after reviewing dry-run output:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --apply-metadata --json
```

Confirmed link apply, after reviewing dry-run output:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --apply-confirmed-links --json
```

Interpretation:

- `station_metadata_changes`: safe metadata evidence found by the dry-run. In
  Stage 17N.2d-L, `station_type`, `distance_from_star`, and `body_name` can be
  applied only with EDSM provenance.
- `metadata_updates_applied`: actual station metadata/provenance writes made by
  `--apply-metadata`.
- `association_changes`: station/body link proposals. Only confirmed/exact
  EDSM bodyName links are applied by `--apply-confirmed-links`; inferred
  distance links remain dry-run/review evidence.
- `confirmed`: exact EDSM id/marketId plus exact station name, and exact
  same-system EDSM bodyName evidence.
- `inferred`: unique distance-only body match. It can explain occupied-slot
  review queues, but must remain labelled inferred.
- `unresolved`: no exact station/body match, ambiguous station/body candidates,
  missing body distance/name, or conflicting evidence. Unknown station types
  keep `lane=unknown`; exact body evidence can still be shown, but it does not
  become occupied-slot proof.
- `conflicts`: review items. They never overwrite existing confirmed
  `station_body_links` rows.
- `ignored_transient_non_slot`: `FleetCarrier`, raw `Carrier`, `MegaShip`, or
  other mobile/transient infrastructure. It may remain visible but does not
  consume orbital/surface colony capacity.

`--apply` is deliberately not implemented. Apply flags require
`--system-id64`. `--apply-metadata` writes only trusted station
metadata/provenance; `--apply-confirmed-links` writes only confirmed exact EDSM
bodyName station/body links. Neither mode writes economies, service flags,
inferred distance links, bulk data, or transient/mobile infrastructure links.

For Exioce, dry-run should show:

- Macmillan Depot: `Unknown -> Orbis`, distance `592`, bodyName `Exioce 3 d`
- Fort Lawrence: `Unknown -> Orbis`, distance `1627`, bodyName `Exioce 4`
- Miller Terminal: `Unknown -> Coriolis`, distance `2219`, bodyName
  `Exioce 5 b`
- `association_changes=3` and `confirmed_link_updates_planned=3` when those
  EDSM body names match exactly one local body each
- `ignored_transient_non_slot=5`: WFK-N6Z, K2W-77Q, WFW-4TZ, T9J-B2N, XFK-T4M

The matching metadata apply updates those three station rows with EDSM
provenance. The matching confirmed-link apply creates confirmed/exact
`edsm_body_name` links for those permanent stations only.

## Diagnostic Queries

Association status:

```sql
SELECT distance_source, distance_confidence, count(*)
FROM stations
GROUP BY distance_source, distance_confidence
ORDER BY distance_source NULLS FIRST, distance_confidence NULLS FIRST;

SELECT association_status, association_confidence, count(*)
FROM station_body_links
GROUP BY association_status, association_confidence
ORDER BY association_status, association_confidence;
```

Unresolved by station type:

```sql
SELECT s.station_type, count(*)
FROM station_body_links l
JOIN stations s ON s.id = l.station_id
WHERE l.association_status = 'unresolved'
GROUP BY s.station_type
ORDER BY count(*) DESC, s.station_type;
```

Inferred by source:

```sql
SELECT association_source, count(*)
FROM station_body_links
WHERE association_status = 'inferred'
GROUP BY association_source
ORDER BY count(*) DESC;
```

Stations with raw body names but no confirmed body id:

```sql
SELECT count(*)
FROM stations s
LEFT JOIN station_body_links l ON l.station_id = s.id
WHERE s.body_name IS NOT NULL
  AND (l.body_id IS NULL OR l.association_status <> 'confirmed');
```

Occupied orbital/surface slots by confidence:

```sql
SELECT lane, association_status, association_confidence, count(*)
FROM station_body_links
WHERE lane IN ('orbital', 'surface')
GROUP BY lane, association_status, association_confidence
ORDER BY lane, association_status, association_confidence;
```

Unresolved infrastructure in one system:

```sql
SELECT s.id, s.name, s.station_type, s.body_name, s.distance_from_star,
       l.lane, l.association_status, l.association_confidence,
       l.association_source, l.resolver_notes
FROM stations s
LEFT JOIN station_body_links l ON l.station_id = s.id
WHERE s.system_id64 = :system_id64
  AND COALESCE(l.association_status, 'unresolved') = 'unresolved'
ORDER BY s.name;
```

Exioce trusted station metadata/link inspection:

```sql
SELECT id, name, station_type::text,
       distance_from_star, distance_source, distance_confidence,
       body_name, body_name_source, body_name_confidence
FROM stations
WHERE system_id64 = 2008132031194
  AND name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal')
ORDER BY name;

SELECT s.name AS station_name, l.body_id, l.body_name, l.lane,
       l.association_status, l.association_confidence, l.association_source
FROM station_body_links l
JOIN stations s ON s.id = l.station_id
WHERE l.system_id64 = 2008132031194
  AND s.name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal')
ORDER BY s.name;
```

## Remaining Limits

This stage establishes the source-of-truth foundation. It does not make perfect
station/body association possible from current data.

Stage 17N.2e note: confirmed and inferred body associations can support
station/port inherited baseline economy display because the body is known. That
baseline still uses the ED-Finder body economy profile formula and remains
pre-Preview. Unresolved or `lane='unknown'` infrastructure must not derive a
body baseline from a guessed body.

Known gaps:

- `stations` still has no native exact `body_id` from Spansh/EDDN.
- `stations.id` is exposed as `market_id` where available but still needs a
  verified separate column if sources diverge.
- `body_name` is useful but not guaranteed complete or unique forever.
- `distance_from_star` is a fallback only, never confirmed truth.
- Ring state is not occupied-slot evidence. `body_rings` carries
  provenance-backed ring rows, while trusted no-ring scan evidence belongs in
  `body_scan_facts.is_ringed = false`. Missing rows in both places mean ring
  state is unknown, not confirmed no-rings.
- Fleet carriers and megaships need a separate model before they can be treated
  as permanent colony occupancy.

Future work should add exact body ids during station import when source data
supports it, provide manual correction/Architect-observed truth, and report
unresolved counts in operations dashboards.
