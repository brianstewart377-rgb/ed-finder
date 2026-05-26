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

Migration: `sql/021_station_body_links.sql`

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
| `association_source` | `manual`, `import`, `eddn`, `resolver_body_id`, `resolver_body_name`, `resolver_distance`, or `unknown` |
| `resolver_notes` | human-readable reason/caveat |
| `updated_at` | link update timestamp |

This is separate from `stations` because a station row can be valid while its
body/lane association is unknown.

## Resolver Order

Implementation: `apps/api/src/station_body_resolver.py`

Resolver order:

1. Existing verified `body_id` / `local_body_id` if present.
2. Exact `body_name` match within the same system.
3. Unique `distance_from_star` match if station and body distances exist and
   exactly one body is within `0.01 ls`.
4. Otherwise unresolved.

Distance tolerance is intentionally tight because `distance_from_star` is not a
stable identity field. If more than one body is within tolerance, the result is
unresolved.

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

`FleetCarrier` and `MegaShip` rows may still carry exact station/body evidence
for display or audit, but their lane remains `unknown` and they do not occupy
permanent colony slots.

## Stage 17N.2d-I Station Data Audit

Current station evidence paths:

- Schema: `stations.station_type` is a constrained enum with `Unknown` as the
  safe fallback; `stations.body_name` and `stations.distance_from_star` are
  nullable evidence fields, not proof of a body link.
- Spansh import: `apps/importer/src/import_spansh.py` is the only current
  repo-side importer that writes station rows. It normalises source labels into
  the enum, imports source arrival distance, and imports source body-name
  aliases when present. It does not import an exact station body id.
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

- Exact `body_name` can be `confirmed` only when exactly one same-system body
  has the same normalised name.
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

## Diagnostic Queries

Association status:

```sql
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
- Fleet carriers and megaships need a separate model before they can be treated
  as permanent colony occupancy.

Future work should add exact body ids during station import when source data
supports it, provide manual correction/Architect-observed truth, and report
unresolved counts in operations dashboards.
