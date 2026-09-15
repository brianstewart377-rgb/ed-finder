# Implementation slice 11 — complete attributed nebula inventory

**Date:** 2026-09-14
**Status:** implemented complete Mapcharts CSV candidate

## Delivered

- `pnpm map:nebulae` deterministically builds a local asset from EDAstro
  Mapcharts' dedicated Nebulae Coordinates CSV.
- The CSV parser detects columns by name as the publishing page recommends,
  handles quoted fields, and rejects malformed rows, unknown source types,
  invalid coordinates, invalid region IDs and duplicate stable identities.
- The current asset contains all 5,842 published `planetary`, `real` and
  `procgen` nebula rows, retaining name, reference system, exact `[x,y,z]`
  coordinates, source type and region ID. It also records the source byte count,
  Last-Modified value and SHA-256 for reproducibility.
- Explore loads the asset by default and exposes a visible toggle, record count,
  EDAstro / CMDR Orvidius attribution, publishing-page link, exact source-CSV
  link and the publisher's rights notice.
- Babylon renders one non-pickable ambient landmark per accepted row at the
  exact coordinate. Cloud radii are intentionally schematic and recorded as
  such in renderer metadata.

## Use and attribution decision

The owner confirmed that ED-Finder is non-commercial and directed use of the
purpose-built public CSV download. The publishing page explicitly addresses
automated consumers and column-order changes. ED-Finder retains attribution,
the exact source URL and the page's rights notice in both the asset and product
UI; it does not recast the Mapcharts dataset as CC-licensed.

## Evidence

Parser tests reject attribution loss, duplicate identities and invalid
coordinates. Adapter tests verify authoritative thin-instance translation,
ambient extent labelling, non-pickable behaviour and the rendered-layer
receipt. Product E2E asserts the 5,842 count, attribution, source link and
rendered layer.
