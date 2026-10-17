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

## 2026-10-17 — Switch base-image pulls to the populated GHCR mirror

CI services, Docker builds, Review Lab and the disposable purge rehearsal now
pull base images from `ghcr.io/brianstewart377-rgb/ed-finder/mirror/` to avoid
anonymous upstream data limits. Tags and all digest pins are unchanged,
including the production API and web base images. The mirror's upstream source
list remains `.github/ci-image-mirror.txt`; contract tests reject executable
upstream references and unlisted mirror tags or digests. Current pull guidance
and image assertions follow the mirror. No production operation is included.

## 2026-10-17 — CI base-image mirror on ghcr.io

Anonymous pulls from `public.ecr.aws` now regularly fail CI with
`toomanyrequests: Data limit exceeded`. A new `CI base-image mirror` workflow
(manual and weekly) copies the listed base images (`.github/ci-image-mirror.txt`)
into `ghcr.io/brianstewart377-rgb/ed-finder/mirror/*` with every platform and
their manifest digests preserved and verified, then checks the packages pull
anonymously. A contract test keeps every executable `public.ecr.aws` reference
on the mirror list. Switching CI, Review Lab and image builds to the mirror is
a follow-up once the mirror is populated. No production operation is included.
## 2026-10-17 — Finder first, governed purge after go-live (owner decision)

The owner restored the build-first order: the 2026-10-11 pre-build purge
ordering is superseded, so the Finder products are built and published on
`parallel_v1` first (step 7′'s capacity gate still guards the builds) and the
governed purge of `ratings_v4_prod_p4`/`opt1` runs afterwards with its design
and gates unchanged. A host disk upgrade waits for NVMe availability.
`docs/ROADMAP.md`, `CLAUDE.md` and the capacity decision record carry the
amendment. Documentation only; no production operation is included.
## 2026-10-17 — Purge ledger state queries scale with batch history

The 1% disposable purge rehearsal stopped with `purge_state_query_failed`
during its third `delete-economy_opportunity` dispatch. Migration 016's
`purge_open_event` anti-joined every opening ledger event against every
closing event, so its cost grew with the square of the batch count, and the
operator state query let the planner call it once per batch event. The
never-applied 016 now resolves open events in one grouped last-closing pass
with identical results (randomised PG18 equivalence test), and the state
query materialises its scopes. Twenty thousand closed batches per relation
and request now resolve in about 0.13 s instead of about 30 s. The migration
checksum, manifest, target-authority migration-set identity and external
schema-identity checksum are re-pinned. No production operation is included.

## 2026-10-16 — Disposable governed purge rehearsal (P2d)

Added a manual Contabo self-hosted rehearsal workflow with a credential-free
PostgreSQL 18 container, unique disposable resources, disk admission checks,
scoped cleanup and 180-day evidence retention. The harness seeds lifecycle
receipt proportions, drives the real purge action through a production-refusing
disposable override, and records sealed measurements and crash-gate results.
Plan mode can consume a reviewed one-percent receipt by path and content SHA,
recomputing its production figures and refusing invalid seals or failed crash
gates. Smoke results cannot authorize production. Added workflow, harness,
override and receipt-consumption coverage and the P2d review runbook. No workflow
was dispatched or production system accessed; production artifact transport into
the protected plan workflow remains a separate gated integration.

## 2026-10-16 — Protected governed purge dispatch (P2c)

Added the manual, `v3-production`-protected derived-purge workflow with a closed
phase choice list, literal production-target confirmation, post-approval exact
`main` checks, both production/operator concurrency fences, pinned SSH trust,
authenticated sealed plan and exclusion-verification artifacts, and 180-day
receipts. Its controller waits for the remote action to exit and bounds delete
and rewrite timeouts; a trusted-main source bundle preserves the independent
rewrite monitor's source after controller loss. The ops workflow gains only
read-only purge plan/status choices. Added workflow contract coverage and the
dispatch/recovery runbook. The P2d disposable rehearsal and its sealed planning
figures remain required before destructive phases; no workflow was dispatched
and no production operation is included.

## 2026-10-16 — Purge physical rewrites and durable owner acknowledgement (P2b2b)

Added the four guarded rewrite dispatches, a backend-lifetime systemd watchdog,
filenode-based retry and interrupted-writer recovery, and recovered ANALYZE.
Amended unapplied migration 016 to durably record validated owner acknowledgement
on writer restoration, recutting its registered schema/target identities without
opening data-repair authority. Disposable PG18 catalog-worker races now use
fixture maintenance suppression and bounded waits. Added transaction, watchdog,
operator and PG18 recovery/completion coverage. No deployment, workflow dispatch
or production operation is authorized by this change; rehearsal figures remain
mandatory and come from P2d.

## 2026-10-15 — Bounded purge deletes and writer-fence recovery (P2b2a)

Extended the governed purge action with bounded, resumable delete dispatches,
per-batch disk/WAL/worker/controller checks, recorded-backend cancellation and
batch recovery through migration 016. Added exact-prior writer-fence restore,
signal cleanup ordering, acknowledged integrity-failure recovery and budgeted
autovacuum abort. The API stays running under the selected read-only fence.
The launcher requires CPython 3.14, source identity covers the backup wrapper,
and successful receipts derive WAL deltas through PostgreSQL. Physical rewrites
and their independent monitor remain P2b2b; workflow wiring and the disposable
1% rehearsal remain P2c/P2d. No production operation is included.

## 2026-10-15 — Purge plans and single-transaction phases (P2b1)

Added the governed purge action's closed mode allowlist, sealed read-only plan
and status receipts, authenticated authorization, zero-row dependency proof,
and completion gates through migration 016's functions. Shared preflight
checks pin the host/runtime/schema, workers, pointers, storage and WAL health,
backup wrapper, writer-fence authority and host lease. Single-transaction
phases wait boundedly for competing backend XIDs without changing 016's
production check. Added local operator contracts and disposable PostgreSQL 18
coverage. Delete/rewrite loops and recovery remain P2b2; protected workflow
wiring and rehearsal remain P2c/P2d. No production operation is included.

## 2026-10-15 — Purge entry fences and ledger-aware backups (P2a)

Added one read-only purge-ledger/host-lease admission check across production
mutators, with the exact authenticated-plan prefix exception only for schema
apply bootstrapping 016. The standalone pgBackRest wrapper skips live recorded
purge backends and fails closed on unavailable ledger evidence. A single new
trusted-main operator choice atomically installs and verifies that wrapper only
after 016, without changing timers or units. Added local contract tests and
PG18 ledger-query tests, plus the installation-order runbook. No production
operation, purge action/workflow, or rehearsal is included.

## 2026-10-15 — Governed derived purge capability registered (P1)

Migration `016` safely adopts a cluster-wide executor already installed by
another database only after checking its restricted role attributes, password
when readable, absence of memberships in other roles, and the non-superuser
creator's SET-only membership. Adoption also rejects every other incoming member
and any creator membership with ADMIN, INHERIT or no SET, including when the
creator is a superuser. Each database still installs its own grants and revokes.
PostgreSQL 18's implicit non-superuser creation ADMIN grant must be removed by an
authorized administrator before that role can be adopted in another database.
Rewrite cancellation authenticates a lock-waiting `VACUUM FULL` by its recorded
backend identity, bounded command and exact ungranted relation lock. Verified
rewrites reject repeated starts and new autovacuum fences. Service quiescence
allows one open record and restoration requires its exact container set; writer
and autovacuum fences preserve the recorded prior state across retries, and a
writer fence stays open until restoration is verified. Disposable PostgreSQL 18
regressions cover these recovery rules, reuse across databases and atomic
refusal of unsafe existing roles; fixture cleanup preserves shared roles.
The manifest and target schema identity are regenerated for these migration
bytes; this registration performs no production operation.

Migration `016` installs an append-only purge request/event ledger, fail-closed
bounded payload functions for only the two never-published rejected generations,
and the restricted executor role with autovacuum and application writer-fence
recovery support. It preserves manifests, products, receipts, publication
history and the published generation; installation performs no purge or rewrite.
The V3 manifest, target authority and every compatible transition prefix now
register `[014, 010, 011-rewritten, 013, 015, 016]`; the F2d release gate accepts
registration and still requires the exact applied ledger hashes. Lifecycle
status adds read-only role, writer-default and WAL/archive/slot facts for later
preflight evidence. Disposable PostgreSQL 18 tests cover the capability; operator
actions, protected workflow and crash rehearsal remain P2. Code only: no
production access, deployment or migration application.

## 2026-10-14 — Finder F2d release gate and identity attestation (PR4 D2b)

Adds the release-first Finder gate, grouped ranking/operator-code and rollback
attestation validation, post-promotion bounded-request probes, and a minimum
schema-compatible rollback boundary. The gate prefers recorded compatible
artifacts and permits the same operation's authenticated, checksum-bound
candidate as the first F2d rollback artifact after boundary and rollback-manifest
validation; preflight and promotion receipts retain its source and image identity.
Authenticated candidates defer image checks to promotion's candidate pull/verify
step; recorded rollback artifacts retain immediate verification. Publication's
bounded behavioural probes now require the exact READY-but-unpublished reason
for both 503s and receipt the parsed detail and verification result. The
publisher pins the active API DSN to the retained database and role, with the
host restricted to the pinned PostgreSQL container name or its inspected IPv4
address on the worker network, and independently checks the connected database
and user before any write (refusal code 79). The standalone plan probe also
refuses loaded checkout modules outside the operator-code manifest before
connecting. Regression tests cover all four review findings.
PR4b review round 3 fixes the deployed `picked` fetch-node recognition, applies
the KNN generation/tie allowance without the generic row cap, requires zero-heap
index-only windows for picked counts too, and measures bounding-box candidates
for the target generation before multiplying by the generation count. The
standalone probe now uses the publisher's pinned DSN binding and checks the
connected database and role before any probe statement (refusal code 24).
After commit, publication checks both live Finder endpoints for results and
the generation, attested ranking identity, and all three Archetype product
identities. A failed post-commit check records `published_unhealthy`, retains
the committed publication/write flags, and exits 80 without rollback.
Regression tests cover each of the six confirmed findings. These changes are
code only; no deployment or production access was performed.
PR4b review round 4 scopes `first-f2d-cutover-empty-finder-products` to the
currently accepted release lacking an F2d attestation group. Later upgrades use
`accepted-f2d-release-allowed-product-states`: keep the exact pinned generation,
allow BUILDING only unpublished and READY only VERIFIED (published or
unpublished), and refuse FAILED. Preflight and promotion receipts record the
rule and observed lifecycle, validation and publication states; post-promotion
bounded-request probes expect 200 after paired publication and the exact 503
reason during rollout. The choice uses accepted-release authority, independent
of optional dispatch attestation. F2d now authenticates the complete CPython
3.14 manylinux x86_64 Psycopg wheel graph through manifest-listed
`deploy/v3-production/f2d-wheels.txt`, hash-checked staging downloads and offline
installs in all six actions. The disposable capacity measurement uses the same
lock. Regression tests cover accepted later upgrades, first-cutover refusal,
failed products, rollout states, wheel hashes and every F2d install/download.
F2d operator operations now read their
attested identity from trusted-main's target authority. The gate requires all
six planned migrations and refuses explicitly while mandatory `016` remains
unregistered. The existing accepted-release values are unchanged. No deployment,
production access or production attestation was performed.

## 2026-10-14 — Finder F2d governed paired publication (PR4 D2a)

Adds the protected `publish-finder-products` operation, the deployment-lock-held
host action, and the paired publication transaction. The publisher checks bounded
view visibility, runs the deployed-image plan probe on its own connection before
commit, and waits for the host's repeated image-digest check. Sealed receipts
record preflights, maintenance, probe evidence and audit timestamps. The action
refuses until D2b supplies the accepted release's ranking and operator-code
attestation. No action was dispatched and no production system was accessed.

## 2026-10-14 — Codex worker model pin moved to `gpt-6.1-sol`

The Contabo Codex worker moves from `gpt-5.6-sol` to `gpt-6.1-sol`. The
2026-10-06 attempt (#784) was reverted because Codex then rejected
`gpt-6.1-sol` for ChatGPT-account sign-in. The worker's Codex CLI is now
0.162.1, and a live check on the worker, signed in with its ChatGPT account
and using the workflow's exact flags (`--ignore-user-config --strict-config
--model gpt-6.1-sol --config model_reasoning_effort="high"`), completed. The
owner chose 6.1 Sol over GPT-6 Astra to limit credit use. Effort stays
`high`; the single-model governance contract and its test keep the same shape
and now reject the old `gpt-5.6-sol` literal.

## 2026-10-13 — Finder F2d wide Archetype data layer

The governed read-only Archetype plan probe now generates all 80 ranking page
and count statements from the attested running API image, executes them with
production statistics under generic-plan settings, and seals complete
per-statement plan evidence. Its assertion module is connection-driven so the
later product publisher can run the same checks inside its own transaction;
the standalone action validates build maintenance receipts, product
publication, the image digest, and the densest current spatial window before
starting a bounded read-only worker. No action was dispatched and no production
system was accessed.

The governed Finder build slice now retargets Search to the current published
`ratings_v4_prod_p4_parallel_v1` generation and adds the wide Archetype build.
Both actions are identity- and migration-pinned, require the combined capacity
gate, bind registration to sealed manifest evidence, and finish only after
reviewed validation plus a receipted `VACUUM (ANALYZE)` of the physical product
table. The read-only lifecycle action now reports product publication
timestamps and the database publication-audit rows independently of publisher
receipts. No action was dispatched and no production system was accessed.

The combined Finder capacity gate is now wired as a synchronous, read-only
governed operation. Its trusted bundle is bound to the selected source SHA and
the explicitly supplied F2d operator-code attestation, and its sealed receipt
is retained for review before either product build can proceed.

The capacity-measurement slice adds fixed, shared F2d evidence paths and
canonical sealed-receipt loading; sealed, operator-identity-bound Archetype and
Search footprint receipts; and a manual GitHub-hosted PostgreSQL 18 measurement
workflow. Search is measured from three independent empty database states
(pre-010, post-010, and minimum-text fixed cost), while the Archetype receipt
records its measured text-free fixed cost for safe resume arithmetic. The
workflow only uploads evidence for review; it does not access or change
production.

The first governed-action slice pins the complete F2d operator surface to a
canonical content identity, adds matching fail-closed shell and Python identity
helpers, and allowlists a detached read-only complete calibration start/status
pair. The complete reader resumes only identity- and generation-bound chunk
checkpoints, scores every Ratings system through the shared model SQL and
`score_raw_system`, appends per-chunk tier counts to a digest-bound
`per-chunk.jsonl` log (the production generation has ~200,000 canonical chunks,
so the sealed receipt binds that log by length and SHA-256 rather than carrying
it), and seals the per-key totals, chunk-plan identity and expected product
manifest. A pure-standard-library converter verifies that receipt and
emits the measured 60/76/88 fractions consumed by the disposable footprint
measurement. No action was dispatched and no production system was accessed.

The additive `GET /api/archetypes/system/{id64}/explanation` route now
recomputes all eight archetype explanations on demand from the published
Ratings vector and opportunity inputs. It serves only an exact product/model
version and deployed-file hash match, holds identity and data reads in one
read-only repeatable-read snapshot, verifies every recomputed wide-row value,
and fails closed on identity or stored-score divergence. The legacy per-system
archetype route remains unchanged.

Migration `015` now permits independently validated Finder products to be
attached to the current published Ratings generation, while keeping product
rows and receipts insert-only and hiding READY products until a one-way,
audited publication timestamp is committed. Product publication and later
generation-pointer flips share a transaction lock; deferred table guards
enforce counterpart and unfinished-product rules even for direct DML. Search
and Archetype application views and API reads now require both products to be
READY and published, builders accept a PUBLISHED ratings base, and disposable
fixture seeds publish Search then Archetype in one transaction.

The unapplied migration `011` now stores one wide archetype row per system,
with integer-ppm confidences, exact integer weighted ranking keys, 24
tier-floor partial indexes, and application summary/detail views rather than a
physical summary table. The canonical scoring model now lives in
`shared_contracts`, carries a fail-closed semantic model digest, and is consumed
by a raw-input wide-row builder and exact validator. The governed migration
manifest and schema authority are recut for the rewritten `011`; this remains
registration only and does not claim production application.

The Finder ranking/API layer now reads that wide row through bounded 10,000-row
windows, literal B/A/S floors, cap-plus-one counts, and an anchored GiST KNN
nearest-first path. Picked and galaxy-wide hard-filter combinations fail
closed, filtered or score-sorted anchored searches are limited to 500 ly, and
both ranking envelopes carry the READY archetype product's complete identity.

The calibration probe now reads the canonical raw-vector and opportunity SQL,
scores only through the shared model entry point, and records model identities
and per-archetype tier histograms. The disposable footprint tool can apply and
measure the final `011` migration with all 26 indexes and histogram-shaped
builder rows, while fixture, Cypress, and Review Lab seeds validate one wide
row per system and keep product publication deferred to the follow-up PR.

## 2026-10-11 — Read-only production disk inventory action

The governed `v3-disk-inventory` action inventories PostgreSQL volume
directories, databases, WAL, temporary files and logs, large relations and
indexes, dead tuples, and derived-generation attribution, then summarizes
accounted and unaccounted usage. It is strictly read-only and performs no
reclamation; any purge or rewrite remains a separate reviewed design.

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
