# Stage 27B — Babylon 9 clean foundation contract

## Decision

Stage 27B is rebuilt from current `main` as a clean renderer foundation.

The authoritative target stack is:

- React 19 + TypeScript for application UI and controls;
- Babylon 9 directly for the 3D galaxy/runtime;
- WebGPU first, with WebGL fallback;
- a small renderer-neutral boundary between React and the 3D runtime;
- no React Three Fiber or Three.js dependency in the new Stage 27 runtime path unless a later explicit architecture decision authorizes a specific need.

The previous PR #545 is historical implementation evidence only and is not the architecture to continue repairing.

## Stage 27B purpose

Stage 27B proves the new Babylon foundation in isolation before real ED galaxy functionality is attached.

The first implementation must provide:

- isolated Babylon 9 workbench/canvas;
- deterministic engine create/destroy lifecycle;
- WebGPU initialization with truthful WebGL fallback;
- camera and navigation primitives;
- DPR-aware resize handling;
- synthetic star-field rendering with staged 100k, 500k and 1m-star proof points;
- pointer/mouse picking with explicit semantics;
- basic runtime telemetry including renderer/backend, FPS/capability state and resource/accounting evidence where available;
- renderer-neutral commands/events sufficient for React to request actions such as fly/highlight and receive selections/state;
- context/device-loss and recovery tests where the browser/runtime exposes those paths;
- isolated typecheck, unit, build and browser test coverage.

## Explicitly out of scope

Stage 27B must not include:

- production/public map cutover or route wiring;
- Stage 27C+ product work;
- real ED galaxy-data activation beyond minimal fixtures needed to validate neutral contracts;
- V3/ratings work;
- Journal ingestion or Commander History product activation;
- production access/writes or deployment;
- CRE/CPE mechanics changes;
- System Map product/infrastructure;
- migration of the old Hetzner deployment as the new runtime baseline;
- preservation of R3F/Three architectural assumptions merely because they existed historically.

## React/Babylon ownership boundary

React owns application UI state, controls, navigation, forms, panels and product composition.

Babylon owns the hot 3D path: engine, scene, camera, GPU resources, star rendering, picking, LOD/visibility strategy and renderer recovery.

React must not reconcile individual stars or other high-volume render objects.

The boundary between the two must remain small and renderer-neutral so future UI code does not depend directly on Babylon scene internals.

## Acceptance

Before Stage 27B can merge:

- all protected CI/security/coverage/status checks must pass on the exact latest head;
- Codex Review must complete on that exact head;
- Octopus Review must complete on that exact head;
- all inline comments, review bodies and unresolved conversations must be inspected;
- every substantive finding must be fixed and verified on the latest head or explicitly dispositioned under repository policy;
- no substantive unresolved review thread may remain;
- browser/hardware limitations must be stated honestly;
- no Stage 27C work begins automatically after merge.

## Hetzner retirement note

The retiring Hetzner host is a time-limited salvage source only. Unique V3/PG18 authority and irreplaceable evidence may be recovered through bounded secret-safe procedures before retirement, but the old host is not the deployment or renderer baseline for this Stage 27 rebuild.
