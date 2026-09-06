# V3 Coordination Control Plane

**Decision date:** 2026-09-05  
**Status:** authoritative coordination boundary for the V3 application programme  
**Tracking:** PR #601

## Purpose

ED-Finder needs one clear coordination model so the owner does not become the manual relay between ChatGPT, Codex, GitHub, CI, browser validation, deployment and the live-checkpoint host.

This control plane is **coordination and evidence**, not a new application runtime service. It must not become a central monolith that application features depend on.

The control plane routes governed work between existing authorities and preserves exact-head identity and receipts.

```text
Owner / ChatGPT
      |
      v
V3 Coordination Control Plane
      |
      +--> GitHub / PR #601 integration state
      +--> Codex governed implementation workers
      +--> normal CI / code contracts
      +--> Product E2E / Visual Acceptance
      +--> Review Lab synthetic proving environment
      +--> immutable release builder
      +--> Contabo live-checkpoint deployment
      +--> smoke checks / release and deployment receipts
```

## What it owns

The coordination plane owns:

- routing a task to the correct execution authority;
- exact branch/SHA selection and stale-head refusal where mutation is involved;
- allowlisted operational actions rather than arbitrary remote shell execution;
- separation of untrusted implementation workers from trusted repository writers;
- sequencing required gates before promotion;
- immutable release/deployment selection;
- collection of bounded machine-readable receipts and evidence;
- presenting enough status that the owner does not have to copy commands/results manually between tools.

It does **not** own:

- ED-Finder domain or scoring logic;
- Svelte application state;
- Babylon scene/domain truth;
- FastAPI business logic;
- PostgreSQL canonical data;
- Review Lab synthetic product semantics;
- test implementation details that belong to CI or browser lanes.

## Current authorities

### Integration state

PR #601 is the single active Svelte V3 integration lane until a coherent checkpoint is accepted and merged. Worker branches may feed #601 but must not create a second integration hierarchy.

After a checkpoint merges, `main` is the only source from which a live checkpoint release may be built. Contabo must never deploy an unmerged worker branch or an arbitrary source checkout.

### Codex implementation

The governed Codex bridge is the implementation-worker path:

`ChatGPT -> codex-task-requests -> Codex Dispatch -> prepare -> self-hosted Codex worker -> sealed result -> GitHub-hosted trusted push`

The self-hosted Codex worker does not receive the repository push credential. Routing and expected-head authority remain outside the worker. Existing-branch writes use a trusted GitHub-hosted push boundary and stale-head protection.

### Normal CI

Normal CI owns source-level implementation correctness that does not require a real browser journey: lint, formatting, type/compile checks, unit/component tests, API/backend tests, script/migration contracts, security/static analysis and repository architecture guards.

### Product E2E / Visual Acceptance

The normal V3 browser lane owns ordinary `apps/web` user behaviour and approved visual baselines. For map checkpoints it must execute the real Svelte + Babylon frontend/renderer.

Authority: `docs/development/v3-browser-validation-lanes.md`.

### Review Lab

Review Lab owns isolated deterministic synthetic states, review-only routes/fallbacks, containment, teardown and diagnostic evidence. For any V3 map scenario it must execute the **same `apps/web` + Babylon frontend/renderer** as the normal product lane; only the data/environment may differ.

Review Lab is not normal E2E and is not the product visual-baseline authority.

### Immutable release and live checkpoint

A green accepted checkpoint merges to `main` before release construction.

The target path is:

`main exact SHA -> immutable web/backend OCI images -> digest-pinned release manifest -> Contabo live-checkpoint environment -> smoke checks -> deployment receipt -> owner live testing`

Production-style safety applies to the release mechanism: no build, dependency resolution or `git pull` on the target host. Contabo is the live-checkpoint environment, not the production server.

## Application-side liaison boundary

The operations control plane must not be confused with the application coordination boundary.

Inside `apps/web`:

```text
Svelte / SvelteKit
      |
application + domain orchestration
      |
renderer-neutral spatial contracts
      |
Babylon runtime adapter
      |
GPU / spatial presentation

Svelte typed API client
      |
FastAPI
      |
PostgreSQL / Valkey
```

Rules:

- Svelte/SvelteKit owns routing, accessible DOM UI, application/domain state and product orchestration.
- Babylon owns spatial/GPU presentation, camera implementation, picking implementation, scene resources and rendering lifecycle.
- Domain/feature code must not import Babylon types.
- Renderer-neutral commands/events/contracts are the liaison between application/domain code and Babylon.
- Babylon must not calculate or own canonical product truth, ranking, persistence or planning mechanics.
- Typed API contracts are the liaison between browser application and backend; do not create a second ad-hoc application bus to mimic the operations control plane.

## Routing a new piece of work

Use the narrowest correct authority:

1. Source/code correctness without a browser -> normal CI/Codex implementation.
2. Ordinary user-visible V3 behaviour/appearance -> Product E2E / Visual Acceptance.
3. Deterministic synthetic/failure/fallback state -> Review Lab.
4. Spatial/GPU presentation implementation -> Babylon adapter behind renderer-neutral application contracts.
5. Application/domain behaviour -> Svelte/domain layer, never Babylon.
6. Operational status/deploy/restart/release action -> allowlisted operations control-plane action with receipt.
7. Live checkpoint promotion -> exact merged `main` SHA through immutable release path only.

Do not make one lane compensate for another. A green Review Lab does not replace Product E2E. A green browser suite does not replace source CI. A successful deploy does not prove product acceptance.

## Checkpoint promotion sequence

For each meaningful live checkpoint:

1. consolidate the intended implementation into #601;
2. run normal source/contract CI on the exact candidate head;
3. run normal Product E2E / Visual Acceptance on the exact candidate head;
4. run the relevant Review Lab synthetic scenarios on the exact candidate head;
5. perform one batched browser stabilisation pass if needed and rerun the affected gates;
6. merge the accepted checkpoint to `main`;
7. build immutable artifacts from that exact `main` SHA;
8. record image digests and release manifest identity;
9. deploy the digest-pinned release to Contabo;
10. run bounded smoke checks and write a deployment receipt;
11. hand that exact live checkpoint to the owner for product testing.

No worker branch deploy, no production-host build, no `git pull`, and no unreceipted promotion.

## Current implementation state

As of PR #601:

- the Codex request/dispatch/worker/trusted-push bridge exists;
- the narrow `ChatGPT ed-new Ops` workflow exists for a small allowlisted set of operator actions;
- Product E2E and Review Lab are explicitly separate browser authorities: Product E2E covers the first normal Explore -> Babylon -> Inspect checkpoint in Chrome and Firefox, while Review Lab now drives that same `apps/web` + Babylon frontend against its isolated synthetic runtime;
- `apps/web` is the V3 application destination and the fresh map will use Babylon;
- the first bounded V3 Explore/Inspect/Babylon checkpoint now exists with renderer-neutral lifecycle contracts, normal Product E2E authority, and separate synthetic Review Lab coverage; later product expansion remains separately governed;
- the immutable `main -> images -> Contabo -> smoke -> receipt` live-checkpoint path still needs to be completed;
- the older `chatgpt-ops-control-plane.md` contains useful design history but is not the current authority for what operations are implemented or authorised.

## Safety rules

- No control-plane document by itself authorises database mutation, schema migration, credential rotation, DNS changes or destructive recovery.
- Operator actions must be allowlisted and fail closed.
- Secrets must not be embedded in request files, receipts, logs or source.
- Implementation workers do not receive deployment or repository-write credentials merely because they are coordinated through the same plane.
- Exact-head identity must survive from accepted code through build, release, deploy and receipt.
- The control plane coordinates authorities; it does not erase their trust boundaries.
