# Babylon Map implementation slice 06 — region hover and stellar heatmap

**Status:** implemented interaction/presentation foundation; production spatial packet integration remains open
**Review date:** 2026-09-13
**Repository state:** `03aabce5` plus the uncommitted map implementation

This continues the
[V2-first comparison protocol](../../v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol),
the [navigation/density slice](implementation-slice-04-navigation-density.md)
and the [projected-label slice](implementation-slice-05-projected-labels.md).

## Reference direction

Two user-supplied map references establish the intended visual language:

- region hover/selection must illuminate the complete irregular in-game region
  footprint rather than a circular proxy; and
- the real-star heatmap should read like a luminous Milky Way: cool sparse
  outskirts, warm cream/white concentrations, irregular structure and dark
  gaps.

The images are look references only. They are not copied into the product and
cannot act as a density texture, mask, occupancy source or substitute for real
coordinates.

## Region hover

The existing central Babylon picking path already resolved pointer coordinates
against the exact source-derived fill and authoritative region lookup. Its
initial alpha-only response was too weak. A first glow-pass experiment was then
too strong: when a close camera sat entirely inside one large region, glowing
the complete fill flooded the viewport.

The retained treatment therefore:

- brightens the exact hovered fill with translucent cyan emissive colour;
- renders the region fill before the factual stellar-density mesh so stars stay
  readable;
- gives the corresponding region label and overview leader a matching cyan
  emphasis;
- keeps persistent selection visually distinct in amber; and
- restores the base material on pointer exit.

No region geometry is inferred from pointer proximity. Hover identity, fill,
label and clear state all use the same canonical region ID.

## Real-star heatmap and Ratings V4 independence

The repository already contains the necessary star-coordinate source. The
legacy `build_grid.py` path aggregates every row in `systems` into
`spatial_grid` and checks the summed cell count against the full systems count.
That is evidence that real density need not wait for ratings to finish.

The old `/api/map/heatmap` is not suitable for the new base layer: it joins
ratings and describes mean/max score, so it represents rated analytical data,
not complete stellar density. V3 must not reuse that semantic contract.

The production path is now explicit:

1. pin one canonical systems generation;
2. build every `v3_spatial.cell_summary` level from all of its coordinate rows,
   independently of rating state;
3. reconcile `SUM(system_count)` exactly to the canonical systems count at each
   complete level;
4. publish the spatial receipt and generation identity; and
5. stream those accepted packets into the same renderer exercised by fixtures.

A derived-generation ID may remain a publication envelope in the current
schema, but Ratings V4 cannot filter the source rows or delay spatial building.
Ratings-derived colours and filters are optional analytical overlays, never the
Milky Way base.

## `stellar-heatmap-v2` presentation

The renderer still creates exactly one camera-facing instance per accepted
occupied cell at its declared centroid. The versioned transfer now uses only
`systemCount`, the response maximum and `cellSizeLy`:

- sparse cells are cool blue-grey and faint;
- increasing density moves through muted dust/mauve;
- the densest concentrations become warm cream/white;
- a compact core-and-halo kernel reaches exact zero at its support edge; and
- dense neighbouring cells receive bounded overlap while isolated sparse cells
  stay compact.

There is no random input, noise field, spiral equation, generated point,
painted mask or image-derived brightness. The real coordinates alone determine
where the apparent Galactic structure exists.

## Evidence and remaining boundary

Unit tests cover exact hover material activation/restoration, selection
distinction, palette ordering, bounded support, kernel symmetry/zero support,
source-centroid matrices, buffer ownership and empty-data behaviour. Isolated
browser diagnostics exercise hover and capture both local and whole-Galaxy
states on WebGPU and forced WebGL2.

Validation at this checkpoint: 29 Vitest files / 234 tests pass; Svelte check
reports zero errors/warnings; ESLint and the production build pass; and all four
browser scenarios pass across WebGPU and forced WebGL2 at 1280×720 and
1440×900. The run produced 20 captures, including exact-fill local and
whole-Galaxy hover states. The main Babylon client chunk is 958.79 kB pre-gzip
(226.64 kB gzip); the existing chunk-size warning remains an optimization input.

The Review Lab's 34-coordinate fixture is intentionally sparse. It proves
wiring and truth constraints but cannot establish the final Milky Way shape.
Visual acceptance against the supplied density reference requires a validated
packet built from the full canonical coordinate catalogue; it does not require
Ratings V4 scores.

No production database, deployment or migration operation is part of this
slice.
