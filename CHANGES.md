# ED-Finder — V3 Development Change Log

This log records the **current V3 development era**, beginning with the infrastructure cutover on 2 September 2026. Entries are newest first.

It is a repository change record, not production/operator authority. For current truth, read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) for production, database, backup, and recovery boundaries;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) for programme stage and authorised next work;
- [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) for the locked V3 application target;
- [`CLAUDE.md`](CLAUDE.md) and [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) for engineering and command boundaries.

Pre-cutover history remains available in Git history and dated/archive documents. It is not repeated here where it could be mistaken for current operational guidance.

> **Current-horizon note (2026-09-05):** dated entries below describe their own
> repository checkpoint. In particular, the 2026-09-04 foundation entry predates
> active PR #601. At known PR head
> `190d26446a2487596299cbb6b497ffa5201fee0b`, that lane contains a real
> Explore/Finder → fresh Babylon results → canonical Inspect product slice.
> This note records active-PR state, not a claim that it has merged into `main`.
> Use the authority chain in [`README.md`](README.md) for current truth.

---

## 2026-10-10 — Finder rollout step 0 run; capacity decision A + B recorded

The read-only `v3-derived-lifecycle-status` inspection ran against production
(run 38079894267). Its receipt is recorded under `docs/operations/evidence/`.
The data volume has about 292 GB free against roughly 1.4 TB for the fresh
Finder generation as designed. The owner chose to rewrite the unapplied
migration `011` as one wide archetype row per system (measured ≈65 GB) and to
attach both Finder products to the already-published generation behind an
explicit product-publication gate (`015`), deferring any purge; the ROADMAP's
steps 4–9 are replaced accordingly. The paused `opt1` ratings worker was killed
by the owner; step 0 closes when the confirming receipt is recorded.

## 2026-10-10 — CI pulls from ECR Public are sequential with retry

ECR Public's anonymous quota is one pull per second, so parallel pulls can fail
with `toomanyrequests`. Review Lab and the image-parity jobs now pull images
sequentially with three attempts and a three-second backoff. Review Lab bounds
each attempt to 60 seconds, while image parity bounds each attempt to 120
seconds; no image or digest changed.

## 2026-10-10 — CI failure causes surfaced as GitHub annotations

Failed pytest tests now emit `::error` annotations with the file, line, test ID,
and assertion text when running under GitHub Actions. The Review Lab job summary
now shows the failure code, failure summary, and failed phases and emits them as
annotations; nothing about test selection, assertions, or gates changed.

## 2026-10-10 — CI image builds avoid anonymous Docker Hub pulls

The API and web Dockerfiles now use the public ECR Docker Library mirror for
their digest-pinned Python, Node and nginx base images, preserving every
immutable digest. Compose validation and container-image parity use the Docker
daemon's built-in BuildKit driver, avoiding the default Docker Hub BuildKit
helper pull. The production release workflow and deploy contracts are
unchanged. The EDDN, importer, and maintenance Python base images now also come
from `public.ecr.aws/docker/library` with unchanged tags, and the
runtime-authority test now requires the mirror prefix.

## 2026-10-09 — CI Docker Official Images moved to ECR Public

CI workflows and the disposable Review Lab contract now pull the same pinned
Docker Official Image tags and digests through `public.ecr.aws/docker/library`.
This avoids anonymous Docker Hub pull limits on shared GitHub-hosted runner IP
addresses without changing the selected PostgreSQL, Redis, or nginx images.
Contract validation now rejects bare Docker Hub library references in those
surfaces while leaving legacy, local, and production Compose contracts
unchanged.

## 2026-10-09 — Finder migrations 010/011/013 registered after 014; 010 rewritten for bounded application

Migration `010_v3_system_search_body_type_counts.sql` now adds its 18 columns
without inline checks and declares the checks as `NOT VALID`, avoiding a
full-table validation scan during the bounded migration apply while continuing
to enforce them for subsequent writes. The V3 production manifest and authority
now register `010`, `011`, and `013` after `014`. This is registration only:
none of those migrations was applied, and the governed plan/apply and separate
constraint-validation operations remain outstanding.

## 2026-10-09 — Reviewed production-promotion hold in version-drift monitor

The production version-drift monitor now understands an explicit, reviewed,
time-bounded hold pinned to the live `bed755b9` release while the F3 Finder
products remain unpublished. The hold expires on 2026-11-09 and must be renewed
or removed through review; manual dispatch can ignore it to expose raw drift.
Web/API agreement, SHA validity, and the expected-SHA deployment gate remain
fail-closed.

## 2026-10-10 — Finder rollout step 6: read-only archetype calibration probe + governed action

The bounded, read-only probe samples published Ratings V4 vectors and reports per-archetype score distributions, primary and secondary counts, tier histograms, and mining/manufacturing/megacomplex separation. The governed operator action verifies the published current generation, runs the probe with fixed resource limits, and retains its JSON receipt as calibration evidence. It has not been run, and the resulting coefficient decision must be recorded before the `system_archetype` product is registered and built.

## 2026-10-10 — Finder rollout step 3: governed system_search constraint validation action

The action runs all 18 deferred `system_search` check validations in a detached runner and provides a separate read-only status operation. It changes only catalog validation flags, with no row data changes and no publication. It has not been run.

## 2026-10-10 — Finder rollout step 0: read-only derived lifecycle status action

The action reports the four worker states, the migration ledger, and the canonical, derived, and spatial pointers and lifecycle states. Its footprint evidence reports measured live relation and index sizes, database size, host disk headroom, and a `measured_footprint_attribution` section with proportional chunk-receipt system-count attribution per generation as inputs to the disk decision. These measurements do not replace the required disposable PostgreSQL 18 sample measurement and full-scale extrapolation of the post-`010` `system_search` row width or the `system_archetype` and `system_archetype_summary` relations and indexes. It is strictly read-only, using READ ONLY transactions and reading identity names only. Running it is a governed operator operation that has not yet happened.

## 2026-10-08 — Codex worker model pin reverted to `gpt-5.6-sol`

The 2026-10-06 bump to `gpt-6.1-sol` (#784) is reverted. The Contabo Codex
worker authenticates with a ChatGPT account, and the Codex API rejects
`gpt-6.1-sol` for that auth mode (`400 invalid_request_error: The
'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT
account`). The first run after #784 (Codex Laptop run 37820866840) failed at
`Run Codex implementation` with that error. The pin returns to `gpt-5.6-sol`,
used by every successful run since #593; effort stays `high` and the
single-model governance contract and test are unchanged in shape.

## 2026-09-05 — Codex worker reasoning-cost adjustment

### Fixed high-effort model contract

The self-hosted Linux Codex worker now pins both investigation and implementation runs to `model_reasoning_effort="high"` instead of `max` to reduce Contabo credit consumption. The official model ID remains the literal `gpt-5.6-sol`, and each pre-execution attestation reports the fixed `model=gpt-5.6-sol` and `reasoning_effort=high` values.

Exact governance tests now require the same `high` setting in both Codex CLI invocations and both pre-execution attestations, while rejecting the former `max` configuration.

### Trust and authority boundaries unchanged

This is a worker resource-setting change only. Strict configuration validation, ignored ambient user configuration, sandbox mode, least-privilege job permissions, immutable branch/base selection, repeated state gates, credential separation, result sealing, trusted compare-and-swap push, fresh CI/re-review requirements, the production/operator workflows, and deployment authority are unchanged.

---

## 2026-09-04 — Issue #577 hard replacement tranche

- Made `apps/web/` the sole browser-application destination; React is temporary source evidence only, and this branch remains unmerged until replacement parity is complete.
- Made Cypress the sole active browser framework for Review Lab, Chrome/Firefox, axe accessibility, and deterministic screenshot evidence. Playwright survives only in static historical provenance.
- Preserved the Python Review Lab evaluator as the acceptance and browser-summary schema owner; Cypress is only its browser driver.
- This tranche does not authorize production deployment, database work, OAuth activation, a Babylon runtime, or later Stage 27 work.
- Marked root Compose, its PostgreSQL 16 maintenance image, and restore/rehearsal helpers as legacy local/CI tooling, never PostgreSQL 18 V3 production or backup authority.

## 2026-09-04 — V3 application stack lock and implementation foundation

### One deliberate application baseline

ED-Finder locked the V3 application architecture rather than carrying each V2-era choice forward independently.

The new browser-application target is:

- Svelte 5 and SvelteKit 2;
- TypeScript 6;
- Vite 8 / Rolldown;
- Node.js 24 LTS and pnpm 11;
- Tailwind CSS 4, Bits UI v2, and Lucide Svelte;
- TanStack Svelte Query for server state;
- Hey API + Fetch for generated FastAPI clients;
- Cypress as the sole active protected browser/E2E authority;
- static SvelteKit output served through the same-origin V3 web boundary.

The backend/data direction remains FastAPI, Pydantic 2, PostgreSQL 18, reviewed SQL migrations, and an eventual CPython 3.14 + `uv` baseline. Valkey is the locked cache/pub-sub direction; NATS is not part of the new baseline without a newly justified responsibility.

The spatial target is a Babylon.js 9-class workbench behind the existing renderer-neutral Stage 27 contracts. The stack decision does **not** authorise Babylon implementation, a renderer cutover, or a later Stage 27 slice.

### New `apps/web` implementation lane

A parallel V3 application foundation now lives under [`apps/web/`](apps/web/). It establishes:

- a static SvelteKit SPA shell and route skeleton;
- Node 24 / pnpm 11 frozen dependency management;
- Tailwind 4, Bits UI, Lucide, and TanStack Svelte Query foundations;
- Hey API generation from an explicitly supplied FastAPI OpenAPI source;
- bootstrap health/session client calls through the generated SDK;
- ESLint 10, Prettier 3, Svelte checks, Vitest/Testing Library, and Cypress smoke coverage;
- CI checks for generation drift, type/check, lint, format, unit tests, build, and browser smoke;
- explicit same-origin route ownership: `/api/*`, exact `/openapi.json`, and numeric `/s/{id64}` remain FastAPI-owned while other application/static routes belong to SvelteKit.

The existing [`frontend/`](frontend/) React/R3F tree is temporary source evidence only during the hard replacement, not an active runnable or validation lane.

### Scope deliberately not claimed

This foundation is **not**:

- a production deployment or public cutover;
- Finder, Inspect, Colony Planner, Review, Admin/Ops, or map feature parity;
- a Babylon renderer implementation;
- a React/R3F retirement;
- a Playwright removal;
- a Redis-to-Valkey or NATS removal;
- a Python 3.14 / `uv` backend migration;
- a database migration, restore, or production OAuth activation.

Those remain separate reviewed slices with their own acceptance and rollback boundaries.

### API and test transition rules

While both frontend lanes exist, both generated API clients must come from the same authoritative FastAPI `/openapi.json` document. The repository drift check regenerates both and fails if checked-in output differs.

Cypress is the only active browser authority. Review Lab, accessibility, visual, and Chrome/Firefox responsibilities are Cypress-owned; Playwright remains only as wording inside clearly historical evidence.

### Root documentation re-baseline

The root [`README.md`](README.md) now acts as the complete V3 entrypoint. It distinguishes:

- infrastructure cutover from application completion;
- the new Svelte lane from the retained React reference;
- programme authority from technology selection;
- SvelteKit routes from FastAPI-owned routes;
- production V3 authority from root legacy/self-host Compose;
- selective legacy-data migration from wholesale database recovery;
- Cypress direction from still-load-bearing Playwright evidence;
- inert/historical Hetzner references from executable production authority.

---

## 2026-09-02 — V3 infrastructure cutover and V2/Hetzner severance

### What the cutover established

The cutover established the replacement V3 **infrastructure authority**:

- PostgreSQL 18 is the production database generation;
- the V3 backup/PITR design and current infrastructure status document define the recovery boundary;
- Frontier identity and replacement-host trust/configuration belong to the V3 environment;
- GitHub and reviewed V3 workflows/runbooks are the application and infrastructure source authority;
- old Hetzner/V2 release, SSH, hosted-review, and server-maintenance procedures no longer authorise production work.

This was an infrastructure boundary, **not a claim that the complete application had already been rebuilt, released, or proven at the public edge**. Current live application state must be established from current status/provenance evidence, not from this historical entry.

### Operational severance

The repository retired or removed the former V2 execution path:

- the old main deployment entrypoint became an inert fail-closed tombstone;
- obsolete Windows release and direct-SSH wrappers were deleted;
- the Hetzner operator workflow and hosted-review deployment lane were removed;
- retired database/recovery runbooks were converted to explicit non-executable historical material;
- current V3 operator actions remained narrow and did not acquire an implied deploy, migration, or database-restore operation;
- environment examples were sanitised so retired Storage Box and V2 secret/config values were not presented as V3 authority.

Some historical identifiers, archived stage records, and local/self-host tooling remain intentionally. The decommission goal is **zero live V2 path and zero ambiguous authority**, not deletion of every historical mention.

### Data migration boundary

Public and reconstructable galaxy data should be reimported or rebuilt through current data paths. Redis/cache state and NATS/JetStream transport state are not canonical domain truth.

A validated PostgreSQL custom-format dump is retained offsite solely as a selective source for genuinely irreplaceable/private/manual/history data:

| Field | Value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Recorded offsite sync | `2026-08-23T05:32:41Z` |

The dump is not the operating database, not a PostgreSQL 18 physical backup, and not a general disaster-recovery shortcut. Never attach or copy an older PostgreSQL physical data directory into PostgreSQL 18. Any extraction must identify the exact irreplaceable data, use reviewed migration tooling, verify the target, and validate the selected result.

### Recovery remains fail-closed

A retained dump, source archive, status action, local Compose restore helper, or old incident note is not automatically a production recovery procedure.

When a current V3 runbook does not authorise the required production database restore/PITR action, stop rather than adapting a retired V2 PostgreSQL/Compose sequence. Recovery authority must identify the V3 target, data source, safety checks, compatibility boundary, validation, and rollback/abort conditions explicitly.
