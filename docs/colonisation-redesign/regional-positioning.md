# Regional Positioning Intelligence

Regional positioning answers a different question from local colony mechanics:

Is this system strategically placed relative to existing civilisation?

It does not produce one universal score. Distance can be good or bad depending
on the colony archetype. The model therefore exposes raw metrics, regional role,
and archetype-aware fit.

## Data Model

The `system_regional_analysis` table stores:

- Nearest colonised system id, name, and distance.
- Colonised counts within 25, 50, 100, and 250 LY.
- Isolation, density, expansion, and competition scores.
- Regional role.
- Archetype-specific regional fit.
- Rationale, strengths, warnings, and per-archetype notes.

Distances use normal Cartesian `x/y/z` coordinates:

```text
sqrt((x1 - x2)^2 + (y1 - y2)^2 + (z1 - z2)^2)
```

No PostGIS dependency is required.

## Colonised System Detection

The importer treats a system as colonised when available data indicates any of:

- `is_colonised`
- `is_being_colonised`
- `population > 0`
- known stations or settlements when those fields are available

Being-colonised state can be surfaced separately later if the source tables make
that distinction cleanly.

## Regional Roles

Current role classification:

- `isolated_frontier`: nearest colony is very distant and there are no nearby
  colonised systems.
- `frontier_hub`: moderate isolation with low nearby density.
- `emerging_cluster`: several colonies nearby but not yet dense.
- `dense_developed_cluster`: close to civilisation with many nearby colonies.
- `bridge_system`: positioned between existing colonies with useful spacing.
- `oversaturated_region`: very high nearby density and competition.
- `unknown`: missing coordinates or no usable regional data.

Thresholds are deliberately simple and documented in
`apps/api/src/regional/regional_roles.py` so they can be tuned against observed
data.

## Archetype Regional Fit

The model keeps regional fit separate from internal build quality.

- Expansion Capital likes moderate isolation, frontier hub potential, and bridge
  positioning. It dislikes oversaturation.
- Extraction/Refinery likes isolation, low competition, and frontier dominance.
- Refinery/Industrial likes logistics access without oversaturation.
- High Tech/Tourism likes nearby civilisation, clusters, and travel access. It
  dislikes extreme isolation unless the local body value is exceptional.
- Agriculture/Terraforming likes moderate proximity and regional growth support.
- Flexible Multirole likes balanced regional conditions.

Recommended builds use regional fit as a light adjustment before recommendation
sorting, roughly 5-10 percent, so close plans can be ordered by regional
strategy while local body mechanics, topology, economy stack, CP sequence, and
services remain the primary signal. A clearly stronger local build should not be
overturned by regional fit alone.

## Importer

`apps/importer/src/build_regional_analysis.py` computes the table. It supports:

- `--all`
- `--dirty` when dirty flags are available
- `--limit` for local testing

For each target system it loads colonised candidates within a 250 LY coordinate
box, computes exact distances in Python, classifies the role, scores archetype
fit, and upserts the result.

## API And UI

Standalone endpoint:

```text
GET /api/systems/{id64}/regional-analysis
```

Simulation summary also includes `regional_context` so the Colony Planning UI can
show regional context beside the deterministic local simulation.

Frontend display includes:

- Regional role badge.
- Nearest colonised system and distance.
- Counts within 50/100/250 LY.
- Archetype regional fit badges.
- Summary, strengths, and warnings.

The Simulation Preview shows regional context separately from local deterministic
results to avoid implying that regional access changes strong/weak link
mechanics.

Regional position uses the standard data-quality label `inferred`. The raw
distance/count metrics are computed from stored coordinates, but strategic role
and archetype fit are model interpretations.

## Limitations And Future Work

The first regional model is intentionally heuristic and transparent. It does not
model traffic volume, player faction politics, route economics, or future
colonisation claims. Those can be added later as separate signals once clean
source data exists.

