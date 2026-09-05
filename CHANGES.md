# ED-Finder — V3 Development Change Log

This log records the **current V3 development era**, beginning with the infrastructure cutover on 2 September 2026. Entries are newest first.

It is a repository change record, not production/operator authority. For current truth, read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) for production, database, backup, and recovery boundaries;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) for programme stage and authorised next work;
- [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) for the locked V3 application target;
- [`CLAUDE.md`](CLAUDE.md) and [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) for engineering and command boundaries.

Pre-cutover history remains available in Git history and dated/archive documents. It is not repeated here where it could be mistaken for current operational guidance.

---

## 2026-09-05 — Codex worker reasoning-cost adjustment

### Fixed high-effort model contract

The self-hosted Linux Codex worker now pins both investigation and implementation runs to `model_reasoning_effort="high"` instead of `max` to reduce Contabo credit consumption. The official model ID remains the literal `gpt-5.6-sol`, and each pre-execution attestation reports the fixed `model=gpt-5.6-sol` and `reasoning_effort=high` values.

Exact governance tests now require the same `high` setting in both Codex CLI invocations and both pre-execution attestations, while rejecting the former `max` configuration.

### Trust and authority boundaries unchanged

This is a worker resource-setting change only. Strict configuration validation, ignored ambient user configuration, sandbox mode, least-privilege job permissions, immutable branch/base selection, repeated state gates, credential separation, result sealing, trusted compare-and-swap push, fresh CI/re-review requirements, the production/operator workflows, and deployment authority are unchanged.

---

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
- Cypress as the future protected browser/E2E authority;
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

The existing [`frontend/`](frontend/) React/R3F application remains intact as the behavioural, accessibility, browser, visual, and parity reference. It must not be removed until equivalent coverage exists or a governing contract explicitly retires a capability.

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

Cypress is the target browser authority, but useful Playwright coverage remains migration evidence until its unique Review Lab, accessibility, visual, Firefox/browser, and historical Stage 26 responsibilities are ported, archived, or explicitly retired. A dependency appearing “old” is not sufficient reason to remove its last accepted evidence.

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
