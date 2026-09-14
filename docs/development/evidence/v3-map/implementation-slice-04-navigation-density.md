# Babylon Map implementation slice 04 — navigation and soft density

**Status:** implemented fixture camera/density slice; M1/M2 acceptance remains open
**Review date:** 2026-09-13
**Repository state:** `03aabce5` plus the uncommitted map implementation

This continues the [V2-first comparison protocol](../../v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol)
and [visual foundation](implementation-slice-03-visual-foundation.md).

## V2 baseline and V3 improvement

V2's `frontend/src/features/map-foundation/camera.ts` provides exponential zoom,
sine easing, bounded camera controls and view presets. Its top-down helper
resets bearing, and the live interaction path keeps bearing fixed at zero. V3
preserves the useful zoom/easing behaviour and adds a full spherical camera
model in canonical light-years, independent bearing, a stable exact top-down
orientation, and cancellable travel between views.

V2's `DensitySwirl.tsx` sizes points indirectly from colour brightness. Its
live `SceneContents` disables that path and substitutes the procedural
`VolumetricGalaxy` field. V3 instead renders one camera-facing quad per accepted
occupied cell, with static source-centroid matrices and count-driven radius and
opacity. A compact core-and-halo alpha texture softens those quads; it does not
create new positions or a Galaxy-shaped mask. The versioned stellar palette
makes sparse cells cool/faint and dense cells warm cream/white. This follows the
supplied BSSA visual reference without using that image as data. The fixture
remains explicitly synthetic: 34 input coordinates reconcile to 20 occupied
cells.

| Area                | Implemented improvement                                                                                   | Evidence boundary                                                   |
| ------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Orientation         | Independent bearing/pitch, exact top-down basis and perspective/orthographic camera application           | Actual Babylon view-matrix tests                                    |
| Navigation          | Grab-to-pan, Shift/right-drag orbit, scroll zoom, keyboard pan/rotation/zoom, native buttons              | Component tests and live browser inspection                         |
| Travel              | Sine-eased focus/pitch, shortest bearing arc, logarithmic distance; immediate reduced-motion path         | Timed session tests, cancellation and completion assertions         |
| Resource continuity | Camera commands preserve scene and mesh identities; idle render loop stops after transition/warm-up       | Babylon session tests                                               |
| Density             | Four shared quad vertices, static instance matrices, bounded core/halo texture and stellar count transfer | Buffer, kernel, palette, empty-data, orientation and disposal tests |
| Overview            | All 42 regions, selected-region focus, fixture-neighbourhood return and semantic system focus actions     | Diagnostic browser interactions                                     |
| Selection truth     | Systems are picked before translucent region planes; empty Finder buffers disable the source mesh         | Real Babylon picking and empty-mesh tests                           |

## Implementation details that affect correctness

The camera adapter uses an explicit quaternion derived from its forward/up
basis. Babylon's ordinary `TargetCamera.setTarget` nudges an exact pole and
discards part of the orientation, which would break exact top-down position and
bearing. Tests check the rendered camera basis as well as the neutral model.

Direct camera input cancels any active flight, and a cancelled flight does not
emit a stale completion event. Resize recomputes the orthographic aspect while
preserving the same camera and meshes. Babylon's automatic scene input handlers
are detached because the Svelte host owns input and explicit picking. Together
with suppressed native pointer focus, this keeps keyboard focus on the semantic
map host after a drag; the hidden canvas does not steal focus or scroll the page.
The browser diagnostics assert that canvas clicks preserve host focus before
exercising keyboard rotation.

The density renderer rotates only the four shared vertices when the camera
orientation changes. Per-cell translations remain static. Conservative bounds
cover every billboard orientation, and owned observers, material and texture
are disposed with the mesh. Babylon's focused glow respects the radial opacity
texture; its glow pass does not consume per-instance colour alpha, so glow area
follows count-derived radius while base opacity also follows count.

The `stellar-heatmap-v2` transfer uses only each accepted cell's
`systemCount`, the response maximum and `cellSizeLy`. Dense neighbouring cells
receive bounded overlapping support so real structures can read as continuous
stellar clouds; isolated sparse cells retain compact support. Colour, opacity
and radius therefore remain data-derived presentation, never evidence of
occupancy beyond the accepted cell set.

## Browser diagnostics and validation ownership

The previous fixture spec was incorrectly included in Product E2E's enumerated
spec list. It now has the explicit local command `pnpm test:map-diagnostics`
and `cypress.map-diagnostics.config.ts`, with artifacts under
`apps/web/cypress/artifacts/map-diagnostics/`. It invokes neither Product E2E nor
the guarded backend Review Lab workflow. Existing browser-lane guard tests pass.

This local command proves renderer wiring and records diagnostic images. It is
not product visual acceptance, a physical-GPU performance receipt, or a new CI
acceptance lane. The historical `/map-review-lab` route name does not grant it
the isolated Review Lab runtime's authority.

Current source validation: 28 Vitest files / 223 tests pass; Svelte check reports
zero errors/warnings; ESLint and the production build pass. The main Babylon
client chunk remains approximately 951 kB pre-gzip, and the exact region asset
remains 3,128.63 kB pre-gzip. The existing chunk-size warning is unresolved.
Formatting checks pass for touched frontend files. The whole-app
`pnpm format:check` still reports pre-existing formatting issues in untouched
files; unrelated files were not reformatted.

Browser checks exercise Chrome 152 with actual `WEBGPU` and capability-selected
`WEBGL2` at requested 1280×720 and 1440×900 viewports. Each scenario checks the
captured density/overview canvas pixels, all 42 regions, hover/selection,
top-down rotation, wide overview, return travel and native keyboard navigation. All four scenarios
pass. Each produces an initial-page image, density image and region-overview
image, plus one shared run video. Local artifact filenames use
`map-review-lab/{galaxy-truth,babylon-density,babylon-regions}-{WEBGPU,WEBGL2}-{1280x720,1440x900}.png`
under `apps/web/cypress/artifacts/map-diagnostics/screenshots/map-review-lab.cy.ts/`.

Visual inspection caught blank overview captures despite passing state checks.
The live browser rendered the geometry correctly, and allowing timers to run
during Cypress capture restored the overview images on both backends. These
diagnostics therefore set `disableTimersAndAnimations: false` and wait for view
travel to settle before capture. Headless Chrome also uses a 1920×1200 capture
surface at DPR 1 so the requested test viewports are not cropped by the default
headless window. A further check found that `drawImage(WebGPUCanvas)` could
return empty pixels while the captured/displayed frame was visibly correct.
The pixel assertion now decodes Cypress's canvas-only PNG and checks it for
non-background signal for both density and overview. UI text cannot satisfy
this check. This retains a fail-on-blank visual assertion without depending on
WebGPU drawing-buffer readback. These are diagnostic settings, not
renderer-only test branches.
See Cypress's [screenshot options](https://docs.cypress.io/api/commands/screenshot)
and [headless screen-size guidance](https://docs.cypress.io/api/node-events/browser-launch-api#set-screen-size-when-running-headless).

Live in-app Chromium/WebGPU inspection verified soft density, dragging, the
whole-region overview and keyboard rotation. It exposed and led to the pointer
focus correction described above.

## Remaining work

- Projected, collision-aware region/system labels and target overlap UI.
- Scale-aware density refinement and representative production-density data;
  the sparse fixture does not establish a realistic wide Galaxy.
- Star billboard/importance work; Finder system markers remain spheres.
- Large World Rendering, precision and dense-data performance budgets.
- Whole-workspace state restoration, camera bounds policy, richer touch input
  and semantic zoom/hysteresis.
- System Map orrery, truthful body/ring/atmosphere materials, hierarchy and
  colonisation contributions.
- Product-route acceptance, Firefox and retained physical-GPU evidence.

No production data, database or deployment operation is part of this slice.
