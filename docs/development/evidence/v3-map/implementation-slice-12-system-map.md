# Implementation slice 12 — interactive 3D System Map

**Date:** 2026-09-14
**Status:** implemented S1 candidate; complex hierarchy fidelity remains open

## Delivered

- The shared Babylon runtime now accepts both Galaxy and System scene
  contracts, including resize, camera, hover, pick and lifecycle paths.
- Inspect builds a System scene from the existing typed system-detail response.
- Stars and bodies render as lit 3-D spheres, known rings receive a distinct
  ring visual, and the camera supports pointer orbit, wheel zoom, keyboard
  rotation/zoom and reset.
- Clicking a body selects its typed `BodyRef`, focuses the semantic layout and
  opens a native body-facts panel. The ordered body list is the accessible
  equivalent.

## Truth boundary

Class, subtype, physical radius, arrival distance and ring evidence retain
catalogue provenance. The current endpoint does not expose parent identity or
complete orbital elements, so all orbit positions, phase, spacing and display
size are deterministic `SCHEMATIC` presentation. The UI states that the view is
not to scale. It does not invent inclination, eccentricity, epoch or hierarchy.

## Evidence and remaining work

Contract/mapper tests cover factual versus schematic classification and stable
layout. Babylon tests cover 3-D bodies, rings, schematic orbits and shared
runtime acceptance. SpatialCanvas tests cover keyboard/pointer system controls.
The isolated browser diagnostic renders and navigates the same S1 scene on both
WebGPU and forced WebGL2; the complete local map matrix passes 6/6 and records
28 captures. Product E2E assertions cover Inspect activation, body list
selection and facts. Binary/multiple-star hierarchy, moons, infrastructure and
S2–S5 orbital fidelity remain later gates when the APIs supply authoritative
relationships.
