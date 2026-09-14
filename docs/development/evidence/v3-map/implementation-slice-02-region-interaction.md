# Babylon Map implementation slice 02 — exact region interaction

**Status:** implemented fixture interaction baseline; not M2 acceptance
**Review date:** 2026-09-13
**Reviewed repository state:** `03aabce5` plus the uncommitted map implementation
**Scope:** exact source-derived region fills, hover/pick/selection, semantic
region controls and WebGPU/browser evidence

This packet follows the
[V2-first protocol](../../v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol)
and extends
[implementation slice 01](implementation-slice-01-density-regions.md). It does
not change production data, deploy services or apply database migrations.

## How V2 did it

V2's `frontend/src/features/map-foundation/AuthoritativeRegionMap.tsx` presents
the deterministic derived region resource as SVG/image context and retains
useful accessible system buttons and wheel-zoom behaviour.
`frontend/src/features/map-foundation/authoritative-regions.ts` provides the
coordinate lookup used by camera/current-region behaviour. Together with V2's
build path, this is strong evidence that the audited RLE source should remain
the authority.

The user-facing gap is equally clear: a region is not a first-class rendered
target. V2 does not provide source-derived per-region fill meshes, pointer hover,
region selection, click/query agreement or a complete keyboard region chooser.
Its tests prove deterministic resource handling and selected system behaviour,
but not a mounted region hit travelling from pixels to the same authoritative
lookup identity.

## What V3 now does better

### Exact geometry, without invented membership

`buildGalaxyRegionFillGeometry` consumes the accepted 2048×2048 RLE lookup. It
merges a span only when the same non-zero region ID has the identical x range on
the next row. It does not smooth edges, interpolate across gaps or assign
unknown cells to the nearest region.

For the pinned source this produces:

- exactly 42 non-empty region geometry packets;
- 13,634 fill rectangles from 21,204 source RLE runs, below the hard 25,000
  rectangle limit;
- 2,949,772 reconciled non-zero source cells;
- at most 724 rectangles in one region; and
- four vertices and six indices per rectangle at a renderer-only y offset of
  -1 ly. Canonical identity remains the source x/z lookup; the offset is not new
  geography.

The Babylon product creates one pickable mesh per authoritative region. Each
mesh carries the region ID/name, source-cell count, rectangle count,
representation and layer identity. The existing boundary mesh remains a single
non-pickable line system, while its receipt now correctly reports 42 pickable
regions.

### One identity path for hover and selection

The Babylon adapter first resolves the picked fill mesh and then verifies the
picked x/z coordinate with `findGalaxyRegionAt`. A region event is emitted only
when mesh identity and the CPU RLE lookup agree. Unknown space remains `null`.

Pointer movement is animation-frame throttled in `SpatialCanvas`; touch does not
run hover work, repeated target identities are not re-announced, and leaving the
canvas clears the hover state. Region targets flow through neutral
`TARGET_HOVERED` and `TARGET_PICKED` events rather than a page-specific Babylon
callback.

Selection changes with unchanged camera and contribution revisions patch the
existing Babylon materials in place. The Galaxy is not rebuilt merely to change
one selected region. A full scene rebuild remains mandatory when camera or
layer inputs differ.

### Semantic parity

The Review Lab exposes all 42 exact names and IDs in a native labelled select,
plus selected/hovered live text. The selector contains one explicit unselected
option and 42 region options. The `?region=18` review URL provides a reproducible
Inner Orion Spur visual state without implying a product URL contract.

This exceeds V2's region interaction while retaining its best accessibility
lesson: canvas interaction must have a semantic companion. Full keyboard
spatial navigation, overlap candidate choice and product-route integration are
still open.

## Comparative result

| Observable       | V2                                        | V3 slice 02                                                                |
| ---------------- | ----------------------------------------- | -------------------------------------------------------------------------- |
| Region authority | Deterministic derived resource and lookup | Same audited source, pinned hash and exact 42-name/ID validation           |
| Fill geometry    | Static image/SVG context                  | 42 exact RLE-derived Babylon meshes                                        |
| Unknown cells    | Lookup can return no region               | Still `null`; no smoothing or nearest-region invention                     |
| Hover            | No first-class region hover               | Throttled neutral event plus distinct fill treatment                       |
| Selection        | System-oriented                           | Region pick/select, persistent selected treatment and scene-contract state |
| Pick truth       | No mesh/lookup agreement gate             | Picked mesh must agree with CPU RLE lookup                                 |
| Keyboard mirror  | Accessible system targets                 | Native chooser for all 42 regions; broader spatial parity remains open     |
| Update cost      | React/resource presentation               | Selection-only revisions patch materials without rebuilding geometry       |

**Disposition:** accepted as the M2 region-interaction kernel. It closes the
fill/hover/select/query subset of V2 finding `V2-M03`; it does not close M2 as a
whole.

## Evidence and limitations

Automated evidence for the combined map implementation now includes:

- complete web Vitest: 25 files and 192 tests passed;
- exact-fill tests that reconcile every region's source-cell count, inspect all
  vertex/index budgets and resolve the centre of every rectangle back to the
  same source region;
- Babylon `NullEngine` inspection of all 42 pickable meshes, metadata and the
  distinct Inner Orion Spur selected material;
- component coverage for animation-frame hover throttling, leave clearing and
  semantic region event mirrors;
- `svelte-check`: zero errors and zero warnings;
- full web ESLint: passed;
- production Vite build: passed, with the existing approximately 925 kB
  pre-gzip Babylon client chunk warning and the 3,128.63 kB region resource;
- Chrome 152 headless WebGPU Review Lab: factual base-frame pixel signal,
  42/42 regions, 22,595 boundaries, exact hover ID, semantic selection and
  applied revision 3; and
- live in-app Chromium/WebGPU inspection of `?region=18`, showing the orange Inner
  Orion Spur source fill with density cells and region boundaries still visible.

The WebGPU canvas can become unavailable to a later 2-D `drawImage` readback in
the same headless Cypress session even while the normal browser compositor still
shows the correct frame. The release lane therefore keeps the proven first-frame
pixel assertion, DOM/runtime receipts and direct Babylon material tests separate;
it does not mislabel a second headless readback as physical-GPU evidence.

Still open and not waived:

- projected region labels, collision/priority budgets and
  topology-preserving fill/boundary LOD;
- profiling and reducing the current 42 region draw calls where evidence shows
  it is necessary;
- complete pointer/keyboard/assistive overlap parity;
- WebGL2 equivalence and retained physical-GPU receipts;
- production map-route integration and production catalogue-density
  publication; and
- the commercial-rights decision for the non-commercial region source.
