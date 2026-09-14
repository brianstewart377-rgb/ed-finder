# Babylon Map implementation slice 03 — visual foundation

**Status:** implemented review-fixture visual kernel; not visual acceptance
**Review date:** 2026-09-13
**Reviewed repository state:** `03aabce5` plus the uncommitted map implementation
**Scope:** truthful high-end Galaxy presentation baseline, visual hierarchy and
WebGPU review evidence

This packet follows the
[V2-first protocol](../../v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol)
and extends
[implementation slice 02](implementation-slice-02-region-interaction.md). It
does not publish production density, change a database or deploy a service.

## How V2 did it

V2 established useful spatial drama with a dark field, bright volumetric-looking
Galaxy material, depth cues and a luminous focal treatment. Its visual ambition
is worth retaining. The audited implementation also shows why the effect cannot
be ported literally: the Galaxy-shaped light was procedural presentation rather
than the accepted catalogue-density truth, some wide-view marks read as uniform
blobs, and region colour could compete with the stellar subject.

V3 therefore preserves the contrast, depth and sense of arrival while replacing
the visual source and making every important effect independently attributable.

## What V3 now does better

The Babylon scene applies a deliberately small visual stack:

- ACES tone mapping with controlled exposure and contrast;
- a dark multiply vignette and subtle dithering for depth and gradient quality;
- one focused Babylon `GlowLayer` that includes only factual catalogue-density
  cells, finder systems and the selected-system marker; and
- translucent region fills with a restrained cyan boundary, a cool hover state
  and a warm selected state.

The glow excludes region geometry and does not create an ambient Galaxy-shaped
substitute. Disabling a factual contribution therefore removes its luminous
signal. Scene metadata exposes this invariant as `ambientDensitySubstitute:
false` so tests and review tooling can detect a future regression.

The camera field of view, system tessellation and selected marker have also been
tuned as a presentation baseline. These are visual parameters, not new spatial
facts.

An initial all-in-one post-processing pipeline was evaluated and removed because
its shader/module cost was disproportionate to this early kernel. The retained
stack uses Babylon's image processing plus a focused glow layer and keeps the
production build's main client chunk at approximately 925 kB pre-gzip (about
216 kB gzip), alongside the existing 3,128.63 kB exact-region resource. Both
remain optimization inputs rather than accepted budgets.

## Comparative result

| Observable           | V2                                                 | V3 slice 03                                                                              |
| -------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Galaxy luminance     | Visually strong procedural structure               | Presentation applied only to factual density/system geometry                             |
| Tone response        | Custom scene/material treatment                    | Explicit ACES, exposure, contrast, vignette and dithering                                |
| Bloom/glow ownership | Coupled to V2 visual implementation                | Focused Babylon layer with an allow-list of factual meshes                               |
| Region hierarchy     | Can dominate the stellar field                     | Low-opacity cartographic glass, precise boundary, stronger only on interaction           |
| Selected state       | Bright system-focused treatment                    | Warm selected target retained; exact region selection also receives a distinct treatment |
| Diagnosability       | Visual effect and truth were difficult to separate | Metadata and direct scene tests prove no ambient density substitute                      |

**Disposition:** accepted as the visual foundation for continued development,
not as the shippable Galaxy art direction or M2 visual acceptance.

## Evidence and limitations

Automated and live evidence includes:

- Babylon `NullEngine` inspection of ACES, glow settings, exact 42-region mesh
  identity and the no-ambient-substitute receipt;
- Chrome 152 headless WebGPU first-frame pixel evidence plus factual runtime and
  interaction receipts;
- the 1280×720 Review Lab capture at
  `apps/web/cypress/artifacts/screenshots/map-review-lab.cy.ts/map-review-lab/babylon-map-before-selection-1280x720.png`;
- live in-app Chromium/WebGPU inspection of the selected Inner Orion Spur state;
  and
- production build evidence for the retained modular effect stack.

The current deterministic density fixture contains only 20 occupied cells. It
is intentionally sufficient to prove truth, rendering and hierarchy but is not
representative of a production Galaxy. Its sphere marks are instrumentation,
not the approved wide-view density representation.

Still open and not waived:

- publish and exercise the real reconciled production density pyramid;
- replace fixture spheres with a scale-aware factual volume/point treatment,
  without a procedural Galaxy silhouette;
- establish paired 1280×720 and 1440×900 captures on WebGPU and WebGL2;
- profile shader startup, long frames, draw calls, GPU resources and quality-tier
  fallbacks on retained physical hardware;
- implement premium camera travel and reduced-motion equivalents;
- design projected labels and UI composition around the canvas; and
- give the System Map its own physically informed orrery materials, lighting,
  atmosphere, rings and colonisation-state visual language.
