# Babylon Map implementation slice 08 — product regions and stable selection

**Status:** implemented Galaxy RC1 code candidate; normal Product E2E and owner visual acceptance remain release gates
**Review date:** 2026-09-14
**Repository state:** `03aabce5` plus the uncommitted map implementation

This slice moves the audited region experience out of the non-product Review
Lab and into the real Svelte Explore/Finder workspace. It also closes ordinary
selection rebuilds in the Babylon session.

## V2 baseline and V3 improvement

| Observable          | V2 behaviour                                                                                          | V3 slice 08                                                                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Region availability | Regions were an optional Map-tab layer and could be absent from the active Finder map.                | The product Explore map loads the pinned authoritative resource independently of Finder results and reports `42/42 regions`.                              |
| Names               | A toggle exposed region context, but the product did not guarantee a persistent exact 42-name atlas.  | A native keyboard selector contains every canonical ID/name and **All 42 regions** fits a whole-Galaxy atlas where all 42 projected names remain visible. |
| Shape interaction   | V2 drew map context but did not provide exact whole-footprint Babylon hover/select.                   | Pointer hover illuminates the exact source-cell footprint in cyan; selection persists the same footprint in amber.                                        |
| Failure             | Region/API failure could make the layer disappear without preserving a strong product truth boundary. | Validation failure is explicit and retryable; Finder systems remain usable and no substitute geography is generated.                                      |
| Selection lifecycle | Selection/camera coupling could re-centre or reconstruct map presentation.                            | Stable Finder and region contributions let system and region selection update the existing scene, meshes and camera in place.                             |

## Product integration

`ExploreWorkspace` now owns the asynchronous region-resource lifecycle. It
accepts only the validated build asset, creates one stable
`SPATIAL_PLATFORM` contribution and composes it beside the Finder-owned system
contribution. The scene retains live camera state for selection-only revisions
while a new Finder result generation still receives its own camera framing.

The product UI provides:

- a `42/42 regions` receipt;
- a semantic selector containing all 42 exact ID/name pairs;
- whole-Galaxy and selected-region camera presets;
- visible selected and hovered region names; and
- explicit loading, validation-failure and retry states.

The product does **not** add fixture density. Until a reconciled,
generation-pinned catalogue packet is connected, the factual density layer is
absent rather than replaced with a procedural swirl, artwork or rated-score
heatmap.

## Post-capture interaction contrast correction

The first RC1 audit capture proved that hover resolved the exact source region,
but its `0.14` fill alpha was too restrained to read as a deliberate highlight
at whole-Galaxy scale. The atlas state was also being visually weakened by a
later general atlas colour rule. The renderer now uses a conspicuous cyan exact
fill for hover, a distinct amber exact fill for persistent selection and a
clearer authoritative boundary treatment. Atlas-specific hover/selection rules
now win in the cascade. This changes presentation only: the highlighted cells,
lookup identity, 42 labels and truth receipt remain unchanged.

The corrected presentation was recaptured on the complete WebGPU/WebGL2 ×
1280×720/1440×900 matrix. All 4 cases passed and produced the same 24 diagnostic
captures, including explicit overview-hover frames.

## Stable Babylon selection

System selection now uses the same in-place scene path as region selection when
camera and contribution inputs are unchanged. The selected-system torus is
moved, created or disposed inside the existing scene and GlowLayer allow-list.
The camera, Finder thin-instance mesh, density resource and 42 region meshes are
preserved. A NullEngine test proves mesh and camera identity across a system
selection revision.

## Browser evidence and diagnostic correction

Normal Product E2E now asserts that Explore accepts the region layer, exposes
the exact 42-name set, keeps Finder targets and can select Inner Orion Spur.
That normal seeded-API lane remains required on the release head and was not
relabelled as locally executed evidence.

The isolated renderer diagnostic covers WebGPU and forced WebGL2 at 1280×720
and 1440×900. Its final keyboard check originally used Cypress text entry on a
non-text `role="application"` host and reported bearing `0` despite passing
native camera tests and toolbar rotation. The retained browser check first
proves pointer focus, then dispatches the actual cancelable `KeyboardEvent`
handled by the component. An isolated rerun proved the correction before the
complete matrix ran.

Validation at this checkpoint:

- 29 Vitest files / 239 tests pass;
- Svelte check reports zero errors and warnings;
- ESLint and the production build pass;
- 4/4 local renderer diagnostics pass on WebGPU/WebGL2 at both required
  viewports; and
- the final matrix produces 24 screenshots plus video.

The generated authoritative region asset is 3,128.63 kB (327.29 kB gzip). The
largest Babylon client chunk is 961.05 kB (227.15 kB gzip) and still triggers
the existing 500 kB warning. Bundle splitting is therefore an explicit RC
hardening item, not a hidden success claim.

No production database, migration, deployment, commit or catalogue publication
operation is part of this slice.
