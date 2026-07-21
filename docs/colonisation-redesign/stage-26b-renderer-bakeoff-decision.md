# Stage 26B Renderer Bake-Off Decision

## Decision

Select **Three.js with React Three Fiber** as the renderer foundation for the
isolated Stage 26C region-first implementation.

This decision does not authorize a production route change, declare the map
production-ready, or alter planner ownership. The current production map stays
live until the later Stage 26 gates are satisfied.

## Equal Matrix

The development-only harness executed all combinations of:

- deck.gl `OrbitView`, deck.gl `OrthographicView`, and Three.js/R3F;
- deterministic 100,000- and 500,000-system datasets; and
- 1280x720 and 1440x900 desktop viewports.

Every cell loaded 42 authoritative region labels plus runtime-derived boundary
segments, completed a renderer-backed system pick, and executed all 17 retained
contract fixtures. The region middleware reads ED-Finder's existing source at
runtime; no third-party pixel geometry is copied into the harness.

Environment: headless Chromium on Windows `10.0.26200`, Intel Core i7-14650HX.
The complete machine-readable receipt is
[`map-bakeoff-results.json`](../../artifacts/map-foundation/stage-26b/map-bakeoff-results.json).

## Measurement Summary

Values below are arithmetic means of the two required viewport observations.
They are local comparative evidence, not general performance guarantees.

| Candidate | Systems | Initial load ms | Frame p95 ms | Frame p99 ms | Pick latency ms | JS heap MB | Post-recovery pick |
|---|---:|---:|---:|---:|---:|---:|---|
| deck.gl OrbitView | 100k | 180.7 | 16.8 | 2424.9 | 2436.2 | 44.8 | fail / fail |
| deck.gl OrbitView | 500k | 123.2 | 16.8 | 12599.5 | 12611.0 | 142.6 | fail / fail |
| deck.gl OrthographicView | 100k | 161.3 | 16.8 | 2458.2 | 2477.2 | 45.0 | fail / fail |
| deck.gl OrthographicView | 500k | 194.9 | 16.8 | 12724.5 | 12737.4 | 131.5 | fail / fail |
| Three.js/R3F | 100k | 138.5 | 25.1 | 75.0 | 11.8 | 29.0 | pass / pass |
| Three.js/R3F | 500k | 181.4 | 83.3 | 108.3 | 30.9 | 85.6 | pass / pass |

## Rationale

R3F is the only candidate that remained usable after the tested WebGL context
loss/restoration sequence. Its renderer-backed pick latency averaged about
31 ms at 500k systems in this environment, versus roughly 12.6-12.7 seconds for
the tested deck.gl pick path. It used less observed JS heap at 500k.

R3F does not pass a production-performance gate yet. Its 500k frame p95 was
about 83 ms, so Stage 26C must prioritize bounded data transfer, visibility/LOD
work, and draw/update profiling before any cutover proposal.

## Explicit Unknowns And Limits

- One observation was recorded per matrix cell on one local machine/browser.
- GPU frame timing is `null`; no timer extension was used.
- Candidate-specific compressed bundle size is `null`; the shared harness is a
  comparison tool rather than three separately optimized production bundles.
- Context timing measures the restored WebGL event. A second renderer-backed
  pick establishes post-recovery usability.
- Region geography and names retain the legal uncertainty recorded in the
  research closure. No redistribution conclusion is made here.
- Mobile and touch remain out of scope.

## Stage 26C Entry Conditions

Stage 26C may build only the isolated R3F region-first foundation. It must keep
the production route unchanged, preserve the typed scene/handoff boundary,
support arbitrary highlights and clusters, keep Plan separate from Map, and
carry the unresolved performance, accessibility, visual, and legal gates
forward rather than treating this selection as cutover approval.
