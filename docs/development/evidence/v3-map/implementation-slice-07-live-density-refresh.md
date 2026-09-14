# Babylon Map implementation slice 07 — live density refresh

**Status:** implemented runtime/fixture proof; production packet transport remains open
**Review date:** 2026-09-13
**Repository state:** `03aabce5` plus the uncommitted map implementation

This slice closes the renderer-side update path required when newly discovered
systems enter a later accepted catalogue generation. It extends the
[region-hover and stellar-heatmap slice](implementation-slice-06-region-hover-stellar-heatmap.md)
without changing its factual-density rules.

## Runtime behaviour

`PATCH_CONTRIBUTION` now supports a catalogue-owned `catalogue-density`
contribution. The command replaces only the density mesh and its owned material,
kernel texture and instance buffers. It does not recreate or move the Babylon
scene, camera, Finder stars, region geometry, selection or label host.

The retained invariants are:

- contribution revision must increase monotonically; stale revisions are
  ignored;
- only the catalogue owner may patch the base density layer;
- the replacement payload passes the same count, bounds, centroid and
  completeness validation as an initial scene load;
- the old density resource is removed from the glow allow-list and disposed;
- the new factual mesh is added to the existing visual pipeline; and
- `CONTRIBUTION_APPLIED` reports the accepted revision and complete rendered
  layer receipt without pretending that the whole scene changed.

This is an instantaneous resource swap at this checkpoint. A later production
streaming slice may cross-fade two already validated generations, but it must
never interpolate occupied cells, fabricate intermediate systems or keep an old
generation labelled as current.

## Discovery-update diagnostic

The Review Lab begins with the reconciled 34-coordinate
`fixture:galaxy-review-v1` generation. Its explicit **Simulate 6 new
discoveries** control publishes `fixture:galaxy-review-v2`, containing those 34
coordinates plus six deterministic new coordinates.

The browser lane asserts that:

- source and covered counts move from 34 to 40;
- the accepted contribution revision moves to 2;
- scene revision and camera revision do not change;
- all 42 region resources remain accepted; and
- the submitted Babylon frame contains the new luminous concentration.

The simulation is evidence for the update mechanism only. Production discovery
freshness still requires the generation-pinned spatial builder, publication
pointer/API and client request lifecycle described by M3/M4.

## Validation

Validation at this checkpoint: 29 Vitest files / 237 tests pass; Svelte check
reports zero errors/warnings; ESLint and the production build pass; and all four
browser scenarios pass across WebGPU and forced WebGL2 at 1280×720 and
1440×900. The run produced 24 captures, including the before/after density
generation frames. The main Babylon client chunk is 960.45 kB pre-gzip
(227.02 kB gzip); the existing chunk-size warning remains an RC1 optimization
input.

No production database, migration, deployment or catalogue publication
operation is part of this slice.
