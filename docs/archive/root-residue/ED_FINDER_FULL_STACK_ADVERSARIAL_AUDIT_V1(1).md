# ED-Finder — Full-Stack Adversarial Audit (V1.1)

- **Repo:** `brianstewart377-rgb/ed-finder`
- **Revision:** V1.1 adds §9 (Tooling and Platform Migration Recommendations); findings in §§1–8 unchanged from V1.
- **Audited commit:** `7913c687e56e2813708bdb1f1d6edbe05e298790` (`main`, HEAD at audit time)
- **Auditor posture:** adversarial principal engineer / due-diligence reviewer. Read-only. All claims derived from the live tree at the pinned SHA; anything not directly verifiable is labelled with confidence.
- **Scale of tree:** ~1,046 tracked files; frontend ~68k lines TS/TSX across 336 files; API ~9k lines across 155 Python files (plus routers/subpackages); importer ~28k lines across 45 scripts; tests ~39k lines across 139 files; 188 markdown docs.

---

## A. Executive Summary

ED-Finder is a genuinely sophisticated single-maintainer product with **two codebases living inside it: the one the governance process touched, and the one it didn't.** The enrichment/canonical-write lane (Stage 18–19) is armoured to a standard most funded startups never reach — disposable-Postgres rehearsals, runtime environment guards, artifact ledgers, allowlisted read-only CI operator actions. Meanwhile, the foundations *underneath* that armour would fail technical due diligence in the first afternoon:

1. **No migration ledger.** `scripts/deploy_main.sh` re-applies **every** `sql/*.sql` on **every** deploy, with `statement_timeout=0`, trusting each file to be idempotent by convention. There is no `schema_migrations` table, and `sql/` contains a **duplicate migration number** (`025_eddn_ring_identity.sql` and `025_eddn_ring_identity_hardening.sql`). One migration (`019`) is silently excluded via a hardcoded filename filter documented only in a shell comment. This is the single most dangerous structural fact in the repo. **[Severity: critical, Confidence: high]**

2. **The ratings rebaseline is operationally incomplete and invisible.** Migration `020` says its purpose is for "the UI/API to distinguish old saturated rating rows from ratings rebuilt by the current scorer." Two months later: the API `SELECT`s `rating_version` (`routers/systems.py:61,355`, `local_search.py:430,748`), the generated types carry it (`api.gen.ts:3578`) — and **nothing anywhere filters on it, badges it, or asserts on the population.** Zero `rating_version IS NULL` predicates exist in the codebase. Users see 3.4 rows and legacy-saturated rows side by side, ranked together, with no cue. The mechanism was built; the product and operational closure were never done. **[Severity: critical for data trust, Confidence: high]**

3. **CI runs a small fraction of the test estate.** The "unit tests" CI step runs `test_smoke.py` only. Integration runs 9 files. Canonical-safety runs 5. The other **~120 test files (tens of thousands of lines)** run only via local `make` targets, i.e. only when a human remembers. That is a false-safety architecture: the suite exists, is impressive, and is not a gate. **[Severity: high, Confidence: high]**

4. **No committed backup path.** `setup.sh` creates `/data/backups`; nothing in the repo ever writes to it. No `pg_dump` cron, no restore runbook, no tested recovery. For a hand-tuned 128 GB Postgres holding a multi-day 186M-row import, this is an existential operational gap. **[Severity: critical, Confidence: high — no backup automation exists *in the repo*; an out-of-repo Hetzner snapshot policy may exist but is undocumented here]**

5. **A second, abandoned-or-pending frontend ships in the repo.** `frontend/src/_redesign/` — 21 files, `.jsx` not TS, mock data only, gated by `?ui=preview`, self-described as "Phase 1" of a migration whose Phase 2 never landed. It is a fork of the product's UI identity sitting in the canonical frontend. Decide: kill or commit. **[Severity: medium, Confidence: high]**

6. **Process residue is now load-bearing repo structure.** Stage-named one-shot operator scripts (`stage19ar_…`, `stage19bb_…`), stage-named test files (`test_stage17n2c_data_trust.py`), 130+ stage documents in `docs/colonisation-redesign/`, machine-consumed state in `docs/…/stage-19-state-authority.json`, and a stale `implementation_plan_stage_4a.md` at repo **root**. The governance programme's exhaust has not been separated from the product. **[Severity: medium individually, high in aggregate for diligence optics, Confidence: high]**

The good news, stated plainly: the API composition root is clean, the OpenAPI type-generation contract with CI drift-check is genuinely excellent, the hash router is well-specified and tested, the dirty-flag rating rebuild pipeline is a real architecture, the sync-key scoping fix (migration 010) closed an actual security hole properly, and the CORS fail-closed validator in `config.py` is better than most production FastAPI apps. The maintainer knows how to do this correctly — the debt is where attention wasn't, not where skill wasn't.

One correction to the audit brief: **`_promote_chip/` and `_promote_main_cleanup/` do not exist at HEAD** and left no trace under this name in the shallow history fetched. Either they were already cleaned or they live in a different clone/branch. The brief was stale on this point. **[Confidence: high for HEAD; medium for full history — clone was depth-50]**

---

## 1. Codebase Health

### 1.1 Delete list (residue, dead weight, or misleading)

| Item | Evidence | Verdict |
|---|---|---|
| `apps/api/src/server.py` | Docstring: "The Emergent preview supervisor runs `uvicorn server:app`… this file just re-exports app." Production `Dockerfile` CMD is `uvicorn main:app`. This is residue from the Emergent platform era. | **Delete.** If anything still points at it, that pointer is also residue. |
| `implementation_plan_stage_4a.md` (repo root) | Stage 4A plan; programme is on Stage 25. Only planning doc at root; everything else lives in `docs/`. | **Delete or move to `docs/colonisation-redesign/`** where its 130 siblings live. Its presence at root signals repo hygiene failure to any reviewer. |
| `frontend/src/_redesign/` (21 files) | Self-described quarantined UIItty4 prototype, `.jsx`, mock data, "Phase 2 lands via an adapter layer" — Phase 2 is absent. Referenced only by `main.tsx` behind `?ui=preview`. | **Decide within one stage: kill or commit.** As-is it's a shipped parallel product identity. If the Stage 25 "restrained cockpit" direction supersedes UIItty4 (the roadmap language suggests it does), delete it and the `main.tsx` bootstrap fork. |
| Stage-named operator one-shots (`scripts/operator/stage19ar_…`, `stage19as_au_…`, `stage19anr_…`, `stage19ba_…`, `stage19bb_…`) | These are completed historical actions kept as executable scripts. `stage19bb` was "first production staging activation" — done. | **Archive.** Move to `scripts/archive/` or delete and rely on git history + closeout docs. Executable history is a hazard: someone (or some agent) can re-run a completed production action. |
| `scripts/dev/review_lab/` browser_runner + friends if Review Lab is not an active lane | 12 modules of bespoke E2E harness. `review-lab.yml` only triggers on changes to its own paths — it validates itself, not the product. | **Keep only if actively used.** [Confidence: medium — it may be Brian's primary local QA rig; if so, document that in `docs/README.md`, because right now it reads as a parallel test framework.] |
| Duplicate migration numbering: `sql/025_eddn_ring_identity.sql` + `sql/025_eddn_ring_identity_hardening.sql` | Two files share prefix 025; `seed_check.sh` and `deploy_main.sh` both apply via `sort`, so order is lexical-accident, not intent. | **Renumber the hardening file to its true sequence position** (or fold into a ledger — see §7). |

### 1.2 Naming that lies or drifted

- **"Development Tuning" / `search-tuning` / `optimizer`** — one surface, three names (`NavBar.tsx:69` label, `useHashRoute.ts` route, legacy `#optimizer` alias). The nav label "Development Tuning" is *internal-facing language shipped to users*. Pick the product name, keep one legacy alias, delete the third identity.
- **`Route` type carries three ghost routes**: `'watchlist'`, `'pinned'`, `'colony'`. Nav shows none of them; `watchlist`/`pinned` render `MyWorkWorkspace` (App.tsx:339), and `'colony'` still renders a whole separate `LazyColonyTab` (App.tsx:393) reachable only by typing `#colony`. That is an **unlisted, unmaintained product surface in production**. Either My Work absorbed Colony tracking (then delete `features/colony/` and redirect the route) or it didn't (then put it in the nav). A hidden tab is the worst of both.
- **`app_version: '3.0.1-hetzner'`** in `config.py` vs `main.py` docstring "Version: 3.1" vs importer `RATING_VERSION = '3.4'` vs `sql/004_ratings_v31.sql`. Four version vocabularies. Nobody can answer "what version is production" from the repo.
- **CI job named `v2` ("Frontend v2 build")** for the only frontend. The name is fossil stratigraphy from the index.html-monolith era that `CHANGES.md` still documents in loving detail.
- **`tests/test_stage17n2c_data_trust.py`, `test_stage19ar_operator_script.py`, etc.** — tests named after process stages, not behaviour. In 6 months nobody will know what invariant `stage17n2c` protects without reading it. Rename by domain (`test_rating_version_contract.py`).

### 1.3 Structural smells

- **`apps/api/src` is not a Python package.** No `__init__.py`; imports are flat (`from config import settings`), and the Dockerfile explicitly says it flattens `src/` into `/app` "so the existing flat-import style keeps working without a package rename." That comment is a confession. Every tool that assumes packages (mypy configs, IDEs, pytest rootdir resolution, future extraction of shared models) fights this. **[Must fix — cheap, one-time, unblocks everything else.]**
- **Prefix-cluster modules instead of packages.** `enrichment_operator_status{,_constants,_io,_sanitize,_station,_warehouse}.py` (6 files), `warehouse_planner_evidence{,_models,_provider}.py` (3), `review_*` (7) — all flat in `src/` alongside genuinely different concerns. These are directories wearing filename trench coats.
- **`review_*` modules interleaved with production code.** `review_environment_fixtures.py` is 1,000 lines of fixture data sitting in the production API source directory, shipped in the production image. The runtime guard (`review_runtime_guard.py`) is good defensive engineering, but the *placement* is wrong: review-environment code belongs in its own package (or under `scripts/dev/`), imported only by `review_main.py`, excluded from the prod image.
- **`models.py` (1,315 lines) and `local_search.py` (1,046 lines)** are the two monoliths in an otherwise well-decomposed API. `models.py` is every response contract for every domain in one file — contract drift risk concentrates here.
- **`frontend/src/App.tsx` is a god-shell.** It instantiates ~10 feature hooks (`useSearch`, `useWatchlist`, `usePinned`, `useCompare`, `useSearchTuning`, `useColony`, `useFcPlanner`, `useAdmin`, `useSystemDetail`, planner store) and prop-drills them into every tab. The comment justifies it ("tabs can share data"), and it *works*, but it means every feature's state shape is coupled to the shell, and the shell re-renders on everything. This is the main frontend refactor target.
- **Three coexisting persistence idioms** in the frontend: zustand stores with rehydrate helpers (`pinnedStore`, `myWorkStore`, `colonyProjectStore`), hand-rolled hook+localStorage (`useCompare`, `useFcPlanner`, `useColony`), and server-backed sync-key resources (`useWatchlist`, notes). 65 raw `localStorage` call sites. `useProfileSync` has to know about all three idioms individually to build its blob — which is exactly the coupling that will break silently when a fourth store appears.
- **`CHANGES.md` and `README.md` are archaeology, not documentation.** README (29 KB) contains "The 41M stall" bug forensics and per-script changelogs; CHANGES.md documents fixes to `frontend/index.html` files that no longer exist. Move the archaeology to `docs/archive/`; a diligence reader opening README should see the system, not its scar tissue.

### 1.4 Too clever / fragile

- The nginx CI job **patches the production nginx config with inline `sed` + a 20-line inline Python block that comments out the TLS server by brace-counting**. It validates a *mutation* of the config, not the config. One structural change to the file and the brace-counter silently validates garbage. Replace with an nginx config template + envsubst, or a test-specific include.
- `build_ratings.py`'s column/placeholder assertion (`RATING_INSERT_COLUMNS` vs `%s`-count) is actually *good* fragility-detection — credit where due — but the fact it's needed shows the write shape should be generated from one schema definition, not maintained as parallel tuple + format-string.

---

## 2. Architecture

### 2.1 Where it is strong

- **App decomposition is right.** `apps/api` (read/serve), `apps/eddn` (live ingest), `apps/importer` (batch build), `apps/maintenance` (cron sidecar) is the correct shape for this product, and the docker-compose profiles (`import`, `pooler`, `monitoring`) keep optional weight out of the default path.
- **The type contract is the best thing in the repo.** Pydantic models → OpenAPI → `openapi-typescript` → `api.gen.ts`, with a CI drift job *and* a local mirror (`scripts/checks/openapi-drift.sh`) that refuses production-looking DSNs. This is how frontend/backend contract discipline should work.
- **Dirty-flag propagation (migration 022 + `run_dirty_ratings_if_needed.sh`)** is a real incremental-recompute architecture: triggers mark `rating_dirty`/`cluster_dirty` on semantically relevant column changes, a locked threshold-gated cron drains it. Well designed, well guarded (flock, threshold, explicit command logging).
- **The review-environment runtime guard** (`review_runtime_guard.py` hard-failing unless DB host is literally `review-postgres` and DB name is `edfinder_local_review`) is exactly the kind of cheap, absolute safety wall this project's write-lane philosophy demands.

### 2.2 Where concerns leak

- **The importer and the API co-own the enrichment/warehouse domain via parallel module families** (`apps/importer/src/enrichment_warehouse*.py` writes; `apps/api/src/enrichment_operator_status*.py` + `warehouse_planner_evidence*` read). The boundary is enforced by convention and docstrings ("the API reads and sanitizes it only; it never invokes importer scripts") rather than by a shared contract artifact. The actual contract is JSON files on a mounted volume (`enrichment_status_json_path`), whose schema exists only implicitly in producer and consumer code. This is contract drift waiting for a quiet Sunday. **Extract the artifact schemas into one shared module (or JSON Schema files) both sides validate against.**
- **`docs/colonisation-redesign/stage-19-state-authority.json` is machine state living in the docs tree**, consumed by `scripts/dev/resolve_project_state.py` and gated by `make state-check`. It even embeds absolute paths from the maintainer's home directory (`/home/brian/.local/share/ed-finder/...`). Disciplined idea, wrong home, leaky content. Move to `config/` or `state/`, and strip personal absolute paths from committed state.
- **Frontend shell vs features:** module boundaries (`features/*`) match product surfaces well, but the *state* boundaries don't — the shell owns everything (§1.3). Selected-system context continuity (a stated product priority) is implemented as a localStorage key + `useState` in `AppInner` (`SHELL_SELECTED_SYSTEM_STORAGE_KEY`), not as an owned store with a contract. Stage 25C's "context spine" deserves a real module.
- **Codebase shape vs product strategy:** the roadmap says the journey is Explore → Inspect → Plan → Review/Export, and the nav even groups routes that way (`NavBar.tsx:65` — good!). But the repo still carries the pre-consolidation lanes as first-class code: `features/colony/` (hidden tab), `features/watchlist/` + `features/pinned/` (absorbed by My Work but fully present), `features/fc-planner/` (a Plan-adjacent lane the roadmap never mentions), `_redesign/` (an alternative shell). The product strategy consolidated; the code didn't. **This is the clearest "shape no longer matches strategy" finding.**
- **Under-engineered:** schema migration management (none), backup/restore (none), error observability (in-process metrics dict, no Sentry-class capture, Grafana behind an off-by-default profile).
- **Over-engineered relative to product value:** the Review Lab harness (12 modules + its own workflow) and the stage-artifact machinery, *if* the evidence-store lane stays paused. These are superb process tools whose maintenance cost is only justified while the lane is active.

---

## 3. Refactoring Opportunities (ranked)

### Must refactor soon (high impact)

| # | Refactor | Impact | Effort |
|---|---|---|---|
| R1 | **Introduce a migration ledger.** Add `schema_migrations` table + a 60-line applier (or adopt `dbmate`/`sqitch`-class tooling) recording filename+checksum+applied_at. Renumber the duplicate 025. Make `deploy_main.sh` apply only unapplied files; make the 019 exception a ledger state, not a shell `! -name` filter. | Removes the single biggest prod-inconsistency vector; makes 019's status auditable | S–M |
| R2 | **Close the rating rebaseline.** (a) one-time backfill or delete of `rating_version IS NULL` rows; (b) importer/DB invariant: after full build, `COUNT(*) WHERE rating_version IS DISTINCT FROM '3.4'` must be 0, asserted by a committed check script and a nightly guard; (c) until (a) lands, surface version in the API/UI as a trust cue (the stated purpose of migration 020). | Data trust; converts a silent mixed population into a managed migration | S (script) + one long importer run |
| R3 | **Make CI run the test estate.** Add a `pytest -m "unit or not (integration or db or operator or e2e or slow)"` job (the `make test-unit` expression already exists — CI just never calls it). Quarantine genuinely broken files explicitly rather than by omission. | Turns 39k lines of tests from decoration into a gate | S |
| R4 | **Package `apps/api/src`** (`edfinder_api/` with `__init__.py`, absolute imports), delete the Dockerfile flatten hack and `server.py`. | Unblocks tooling, shared-model extraction, honest imports | S–M, mechanical |
| R5 | **Add backups.** Nightly `pg_dump -Fc` (or `pg_basebackup`) into `/data/backups` from the maintenance sidecar + retention + a *tested* restore runbook in `docs/operations/`. | Existential risk removal | S |
| R6 | **Decide `_redesign/`.** Delete (recommended, given Stage 25 supersedes it) or write the Phase-2 adapter plan into ROADMAP with a deadline. | Removes a forked product identity | S to delete |

### Nice to clean up later

| # | Refactor | Impact | Effort |
|---|---|---|---|
| R7 | Fold prefix-clusters into subpackages: `enrichment_status/`, `warehouse_evidence/`, `review_env/` (the last excluded from prod image). | Readability, image hygiene | S |
| R8 | Split `models.py` per router domain (`models/search.py`, `models/planner.py`, …) with a re-export shim to avoid a big-bang. | Contract locality | M |
| R9 | Frontend: extract a `shellContext` store (selected system, route source) and move per-feature hooks into their tabs; App.tsx becomes routing + providers only. Standardise on one persistence idiom (zustand + persist) and make `useProfileSync` consume a registry of stores instead of hardcoding three idioms. | Reduces shell coupling; makes accounts work (§6) tractable | M–L |
| R10 | Retire ghost routes: delete `features/colony/` (after confirming My Work parity), collapse `watchlist`/`pinned` route aliases into redirects, rename `search-tuning` properly. | Product coherence | S–M |
| R11 | Importer: extract shared DB/connection/progress/artifact helpers (they exist — `progress.py`, `artifact_utils.py` — but stage scripts still re-implement plumbing) and move completed one-shots to archive. | Ops safety | M |
| R12 | Replace the nginx CI sed/brace-counter with templated config. | CI honesty | S |

### New internal tools that would materially pay off

1. **`scripts/checks/data_invariants.py`** — one runner asserting: rating_version population uniform; every system has a rating; no `sync_key='legacy'` rows growing; MV freshness within N hours; duplicate-station identity counts stable. Run nightly in maintenance + on demand. This converts your review-culture instincts into a machine.
2. **Migration linter** — refuses duplicate numeric prefixes, requires an idempotency header comment, refuses `DROP`/`UPDATE` on large tables without an explicit `-- MANUAL:` tag (which would have made the 019 exception declarative).
3. **Artifact-schema validator** — JSON Schemas for the enrichment/warehouse status artifacts, validated by both producer (importer) and consumer (API) in tests.

---

## 4. Product and Feature Review

### 4.1 Ten best features (and why they're actually valuable)

1. **Finder search with rationale'd ratings** — score + `score_breakdown` + `rationale` + `confidence` is the core moat: it answers *why*, not just *what*, which is the difference between a tool and a toy for colonisation research.
2. **Colony Planner as canonical workspace with deep-linkable projects** — `#colony-planner/system/{id}/project/{id}/detail/{id}` routes mean a plan is a shareable, bookmarkable object. That's real product engineering.
3. **Simulation preview + optimiser + mechanics trace** — deterministic build-preview with per-port economy states and an influence ledger is the most defensible feature in the app; nobody casual builds this.
4. **Observed-vs-predicted / evidence language discipline** — the assessment vocabulary (observed, inferred, provisional) carried into UI copy is a genuine trust differentiator versus every "score go up" fan tool.
5. **Provenance cockpit + operator visibility (read-only)** — exposing source runs and ingest provenance to an operator surface is the right long-term bet for a data product.
6. **My Work consolidation** — merging watchlist/pins/tracking into one work surface matches how players actually operate (the *execution* has leftovers — see weaknesses — but the idea is right).
7. **Profile sync without accounts** — a 16+ char sync key as a portable profile is a pragmatic, privacy-light bridge that already solves multi-device for motivated users.
8. **EDDN live layer** (ticker + SSE feed) — live universe changes feeding a research tool keeps it feeling alive and honest about freshness.
9. **Share stop-page with OG card rendering** (`/s/{id64}` + Pillow card) — link-unfurl-quality sharing is rare in this niche and is your organic acquisition channel.
10. **Map as secondary Explore surface** — the roadmap's restraint here (map supports, planner leads) is correct product judgment; the recovered map with heatmap/MV backing is good supporting cast.

### 4.2 Ten weakest aspects

1. **Ratings trust is silently two-tier** (§Exec 2). This undermines feature #1 directly. *Good idea, execution abandoned mid-migration.* Repair (R2), urgently.
2. **Hidden `#colony` tab.** An unlisted production surface duplicating My Work. *Should not exist in current form* — delete or reintegrate.
3. **FC Route Planner is an orphan lane.** Present in nav ("Review" group, oddly), absent from the roadmap's journey and Frozen Facts. It's a different product (logistics) bolted to a research product. *Reposition under Plan as "Logistics" with explicit planner integration, or defer/remove.* [Confidence on product intent: medium.]
4. **"Development Tuning" in the user nav.** Internal tuning tooling exposed as a peer of Finder/Map. *Good tool, wrong shelf* — move behind Admin/Operator or a query flag.
5. **Compare is shallow relative to the app's depth.** A snapshot table in a product whose soul is simulation; comparing systems without comparing *plans/assessments* undersells the engine. *Good idea, weak execution* — grow it into evidence-aware comparison or fold into Finder.
6. **`_redesign` parallel UI** — a second visual identity reachable by query param contradicts "one coherent product" (ROADMAP §"What We Are Doing Now" item 1).
7. **`planner-preview` / `chip-preview` routes ship to production users.** Design-QA harnesses as top-level routes. Gate behind DEV or delete after sign-off.
8. **Admin vs Operator split is under-explained in-product.** Two adjacent gated tabs whose distinction lives in stage docs, not the UI.
9. **First-run experience.** Landing is a fully armed cockpit with no guidance toward the Explore→Plan journey the roadmap defines. Empty states exist per-surface but there's no journey scaffold. [Confidence: medium — judged from code/copy, not live use.]
10. **Per-user data has no account story** while accumulating value (planner projects, My Work, notes) across three storage idioms and one paste-bin table. Every month of growth raises the migration cost of §6.

---

## 5. UI/UX — Ten Improvements, in order

1. **Ship the rating-version trust cue.** A small "Rated v3.4 / Legacy rating — pending rebuild" badge on cards and System Detail. This is the highest trust-per-pixel change available and finishes migration 020's stated purpose.
2. **One name per surface.** Rename "Development Tuning" (or hide it), kill the `#optimizer` alias from docs/UI, resolve My Work vs Colony vs Watchlist vocabulary everywhere copy still mixes them.
3. **Make the selected-system context spine visible and consistent** across Finder → Map → Planner → Review: same chip, same position, same clear/change affordance. The persistence exists (`SHELL_SELECTED_SYSTEM_STORAGE_KEY`, "Keep review context visible" commits show active work) — the remaining gap is uniform presentation and an explicit "context: none" state rather than silent absence.
4. **Journey affordances between stages.** From System Detail (Inspect) the "Plan this system" path should be the primary action; from Planner, "Review evidence" likewise. Commits like "Polish plan entry copy and Map handoff" show this is understood — finish it as a checklist across all four transitions.
5. **Unify density/spacing on evidence surfaces.** The cockpit posture demands dense, aligned, mono-numeric tables; audit the planner telemetry panel vs warehouse evidence card vs provenance cockpit for one shared table/label primitive (Stage 25B's "evidence-language visual primitives" — make it a real component set, not a doc).
6. **Restrain the chrome experiments.** The last five commits at HEAD are all economy-chip geometry polish ("Diagonal split economy chip", "Trim economy chip height"). That's fine craft, but glass/chip styling iterations on chrome while ratings trust and empty states lag inverts the roadmap's own priority ("operationally boring" planner first). Freeze chrome; spend the polish budget on trust cues.
7. **Empty states as onboarding.** My Work with nothing tracked, Compare with no snapshots, Planner with no project should each teach the next action with one primary button, in evidence language, not generic "nothing here."
8. **Accessibility pass on the tab shell.** The nav has aria-labels and testids (good); verify focus order into modals (`SystemDetailModal` over any tab), Escape/route-back consistency, and contrast on dim mono text (`text-[11px] font-mono text-text-dim` footer suggests sub-AA sizes/contrast exist). [Confidence: medium — needs live axe run.]
9. **Operator/Admin mode framing is actually good — extend it.** The "Separate operator mode / Return to player workspace" banner pattern in NavBar is exactly right; apply the same explicit mode framing to preview routes and the review environment so *every* non-player surface self-identifies.
10. **Trust cues on data freshness.** Surface `updated_at`/source-run age on system detail and map layers ("bodies observed 2026-06-30 · EDSM"). The provenance exists in the schema; users currently can't see staleness where decisions happen.

**Premium vs messy, honestly:** the planner workspace, nav grouping, and evidence-language copy read premium. The seams read improvised: three-name surfaces, hidden tab, preview routes, a footer that says "Vite production build · root-served live app" to end users, and chrome polish outrunning trust plumbing. The cockpit posture is 80% there; the remaining 20% is consistency, not more styling.

---

## 6. User Accounts and Per-Account Persistence

### 6.1 Current state (the raw material)

- Server-side per-user data already exists, keyed by **bearer-string `sync_key`** (16–128 chars, `[A-Za-z0-9_-]`): `profile_sync` (1 JSONB blob/slot, 1 MiB cap), `watchlist(sync_key, system_id64)`, `system_notes(sync_key PK composite)`. Legacy rows tagged `'legacy'`; old unscoped endpoints return 410. The key IS the credential — no hashing at rest, no rotation, no recovery, no enumeration protection beyond keyspace size and an **in-memory, per-IP** rate limiter.
- Client-side: pinned/My Work/planner projects/compare/FC live in localStorage across three idioms; `useProfileSync` serialises them into the blob manually.

### 6.2 Three strategies evaluated

**Option A — FastAPI + Postgres native auth.** Email+password (argon2) or better, passkeys/magic-link; opaque session tokens in an HttpOnly cookie; `users` + `sessions` tables.
*Fits:* zero new vendors (matches the repo's whole posture — self-hosted Hetzner, pinned images, no SaaS anywhere); Postgres is already the center of gravity; sync_key precedent means the API layer already does credential-scoped resources.
*Costs:* you own email delivery (verification/reset), credential security, session hygiene. Password auth is the part most likely to be done naively.

**Option B — External IdP (Clerk/Auth0/Supabase Auth).** Fast, secure defaults, MFA/passkeys free.
*Against, specifically for this repo:* introduces the project's **first hard third-party runtime dependency and first PII processor**, contradicts the sovereignty posture of the entire stack; nginx/SPA/hash-routing + cookie/token juggling with a hosted IdP adds CORS/session complexity the current single-origin design avoids; vendor outage = login outage for a hobby-revenue product. Also: the governance culture here would want to audit the auth path, and you can't audit a vendor's.

**Option C — Hybrid: accounts as an optional sync/ownership layer over a local-first workspace.** Everything keeps working anonymous/local (as today); an account, once created, becomes the durable owner of profile state; sync_key survives as (a) legacy import credential and (b) optional share/device-link mechanism.

### 6.3 Recommendation: **C, implemented with A's machinery — passwordless-first.**

Native FastAPI/Postgres auth (no vendor), but **magic-link email + passkeys, no passwords at MVP**. Rationale: passwordless removes the highest-risk part of Option A (password storage, reset flows, credential stuffing) while keeping everything self-hosted; local-first preserves the product's current zero-friction entry, which is a real strength for a niche tool; and the migration path from sync_key is natural because sync-scoped tables already exist — accounts are "a sync_key with a login."

### 6.4 Data model

```sql
users(id UUID PK, email CITEXT UNIQUE, email_verified_at, created_at, disabled_at)
auth_tokens(id, user_id FK, purpose ENUM('magic_link','session','device_link'),
            token_hash BYTEA,          -- store SHA-256 only, never raw
            expires_at, used_at, created_ip)
webauthn_credentials(id, user_id, credential_id, public_key, sign_count, created_at)
profiles(user_id PK FK, blob JSONB, blob_bytes, updated_at)   -- successor of profile_sync
-- ownership columns, additive:
ALTER TABLE watchlist    ADD COLUMN user_id UUID NULL REFERENCES users(id);
ALTER TABLE system_notes ADD COLUMN user_id UUID NULL REFERENCES users(id);
ALTER TABLE profile_sync ADD COLUMN user_id UUID NULL REFERENCES users(id);
-- later, first real relational promotion out of the blob:
planner_projects(id, user_id, system_id64, name, payload JSONB, updated_at, version INT)
```

**Account-owned:** planner projects, My Work, watchlist, notes, pins, profile prefs.
**Anonymous/local-only forever:** search filters, density/UI prefs, selected-system context, compare scratch, preview flags. Never sync ephemera; it's how sync systems rot.

### 6.5 Migration of existing state (safe path)

1. Additive schema only (nullable `user_id`), zero behavior change. Sync_key endpoints untouched.
2. **Claim flow:** logged-in user enters their sync key once → server verifies key exists → sets `user_id` on the `profile_sync` row and all `watchlist`/`system_notes` rows for that key, records the claim, and *retires* the key for write (reads keep working during a grace window). Local-only users without a key: client pushes its current localStorage blob into `profiles` at first login (the `useProfileSync` serialiser already builds exactly this blob — reuse it).
3. Conflict rule at claim/merge: **union with per-item `updated_at` winner**, never blind overwrite; keep a one-time pre-merge snapshot row for 30 days (undo).
4. `'legacy'`-tagged rows: they are unattributable by design — set a sunset date, export nothing, delete after notice. Don't invent ownership.
5. Only after adoption: promote planner projects out of the blob into `planner_projects` with optimistic `version` for multi-device conflict handling. **Do not normalise the whole blob on day one** — the paste-bin model is a feature until sync conflicts prove otherwise.

### 6.6 MVP vs long-term

**MVP (one stage):** users + magic-link + HttpOnly session cookie (SameSite=Lax; the SPA is same-origin behind nginx, so no token-in-JS at all), claim-sync-key flow, `profiles` push/pull replacing the sync panel for logged-in users, per-key/per-account rate limits **backed by Redis, not the in-memory limiter** (auth endpoints must survive the workers=1 assumption changing).
**Long-term:** passkeys as primary; `planner_projects` relational with versioned sync; per-device sessions list + revoke; account deletion = hard delete of owned rows (GDPR posture — you're storing EU emails from Edinburgh, so data-subject deletion/export must exist from day one); audit log for auth events; optional read-only share links for projects (replacing sync-key-as-sharing).

### 6.7 What would be dangerously naive

- **Treating sync_key as the account primary key.** It's a bearer secret; making it an identity means every leak is an account takeover with no recovery. It must become a claimable credential, then die.
- Rolling your own password auth "quickly" — if passwords ever land, argon2id + breach-list check + rate limiting or don't ship it.
- Storing session/magic tokens raw in Postgres (hash them; your DB is one `pg_dump` on an unencrypted `/data` volume away from being the credential store).
- Auth rate limiting on the current `memory://` limiter — restart clears buckets; magic-link endpoints become an email-bombing vector.
- Auto-merging cloud and local state without the snapshot/undo — the first user who loses a 40-station plan to a merge is your last power user.
- Shipping accounts before R2/R5: authenticated users amplify both the data-trust problem and the no-backup problem.

---

## 7. Security, Reliability, Operations

- **Migration process (critical, restated):** no ledger; full replay each deploy under `statement_timeout=0`; idempotency-by-convention; duplicate `025` prefix; `019` excluded by filename in a shell script. Any non-idempotent slip in a future file executes against production on every deploy until noticed. R1 fixes the class.
- **No backups in repo (critical):** §Exec 4. The maintenance sidecar with a crontab is *right there* — this is a one-evening fix.
- **Single DB role everywhere:** `edfinder` is app runtime, migration applier, importer, and psql-in-container superuser-equivalent for its DB. The warehouse read-only DSN work (docs/operations stage-18j-q4*) shows you know how to do role separation — apply it at home: `edfinder_app` (DML on serving tables), `edfinder_migrate` (DDL), `edfinder_import`. [Severity: medium-high, Confidence: high.]
- **Sync-key surface:** design is defensible (96+ bits, regex, `legacy` blocked at API, 007's CHECK constraints). Gaps: keys stored plaintext (they're credentials — hash like tokens, cost is trivial), in-memory rate limiter resets on restart, and no per-key access logging. [Medium.]
- **Reproducibility contradiction:** `frontend/yarn.lock` **exists in the repo**, but CI installs with a comment saying "yarn.lock is intentionally not in repo — Emergent's auto-commit strips lockfiles; install fresh each time," and therefore doesn't use `--frozen-lockfile`; `deploy_main.sh` then rebuilds the frontend *on the production box* with whatever resolves that day. So: CI-built artifact ≠ deployed artifact, and neither is pinned. Fix: `yarn install --immutable` in CI and deploy, delete the Emergent-era comment. This is a two-line change removing a whole class of "works in CI, broken in prod" incidents. [High confidence; the stale comment is itself a docs-vs-code divergence exhibit.]
- **`latest` image tags** for prometheus/grafana/exporters vs pinned pgbouncer ("pinned for reproducibility (audit fix)") — the audit fixed one image and left four floating. Pin them.
- **Emergent residue beyond `server.py`:** the CI lockfile comment, and `CHANGES.md`'s references, indicate an incomplete platform migration; grep and purge.
- **Docs/code divergence, concrete instances:** `main.py` module docstring lists 11 routers; 21 are mounted (news, profile, evidence, colony_planner, provenance, warehouse, simulate, simulation, optimiser, observations missing from the doc). `config.py` app_version 3.0.1 vs main.py header 3.1. README repo-layout section [not fully verified] almost certainly trails the tree given 188 docs. The project *has* a doc-integrity culture — point it at these.
- **Ops rituals that are manual and load-bearing:** `019` migration, `--nuke`/`--reinstall` setup semantics, `sync_password.sh`, `cleanup.sh` for orphaned importer containers, screen-session imports. Each is documented (good) but none is monitored; the failure mode is "forgot," not "broke."
- **Observability:** metrics live in an in-process dict (lost on restart, single-process by design), Grafana/Prometheus are opt-in profiles (are they running in prod? unknowable from repo), slow-query visibility is still a *proposal* in `SCHEMA_AND_REFACTOR_ADVISORY.md` §1.2 (correctly marked "single highest-leverage db observability change" — it's been sitting there since May; ship it). No crash capture at all on frontend or backend beyond logs.
- **Genuinely good, for the record:** CORS fail-closed validator with explicit wildcard rejection; postgres bound to 127.0.0.1; per-container log caps with the disk-fill rationale written down; the pgbouncer incident writeup embedded where the decision lives; the Hetzner-operator GH workflow being allowlist-only, read-only, environment-gated. The security *thinking* is above average; the gaps are coverage, not competence.

---

## 8. Testing and Quality

- **The headline (restated):** CI gates on `test_smoke.py` + 9 integration files + 5 canonical-safety files. ~120 test files / most of 39k lines are local-only. Tests that don't run in CI rot without a signal — and several of the biggest files are stage-frozen (e.g. `test_stage19ar_operator_script.py`, 1,216 lines, guarding a completed one-shot). **Fix:** R3 (run the unit-marked estate in CI) + an explicit decision per stage-test: promote to a domain-named contract test, or archive with its script.
- **False-safety exhibits:**
  - `test_stage17n2c_data_trust.py` asserts the migration *file text* contains `ADD COLUMN IF NOT EXISTS rating_version` and that the importer constant is `'3.4'` — it protects the mechanism's existence, not the outcome. Nothing anywhere tests "production-shaped data has a uniform version." A schema-text regex test passing while the actual population is mixed is the definition of false safety.
  - The nginx CI job (§1.4) validates a sed-mutated config.
  - `review-lab.yml` triggers only on its own paths: the E2E harness never runs against product changes, so "we have Playwright E2E" is true and non-protective.
  - Non-frozen yarn install means the frontend CI green-check certifies a dependency set that may not match deployment.
- **Highest-value missing tests:**
  1. **Migration replay test** — apply all of `sql/` twice against fresh Postgres; fail on any error (directly certifies the idempotency the deploy script bets production on; near-free to add to the existing integration job).
  2. **Data-invariant suite** (§3 tool 1) run in CI against seeded DB and nightly against prod read-only: rating population uniformity, MV freshness, every-system-has-rating (partially in `seed_check.sh` already — promote it).
  3. **Profile sync round-trip E2E** — the highest-value user data path (push→wipe→pull→deep-equal across all three store idioms). Unit tests exist (`useProfileSync.test.ts`); an E2E through the real API does not.
  4. **Artifact contract tests** for enrichment/warehouse JSON (producer emits → consumer parses, one fixture, both sides).
  5. **Route contract test** covering every `Route` union member — would have caught the ghost `#colony` tab (a test asserting each route renders *and is reachable from nav or documented as hidden*).
- **Where manual QA is compensating for structure:** deploy verification (health-check curl loop in `deploy_main.sh` is the only post-deploy assertion), rating rebuild correctness (no post-run invariant), the entire `_redesign` preview, chip/planner preview routes (the last five commits are visual polish verified by eye — a Playwright screenshot test on `#chip-preview` would make that loop cheaper than the manual one), and cross-tab context continuity (App.test.tsx covers pieces; no journey-level test walks Explore→Plan→Review with context asserted at each hop).
- **Low-value/over-coupled tests to prune:** the schema-text regex assertions (replace with live-DB column introspection in the integration job); stage-script tests for archived one-shots; any `_redesign` coverage if R6 = delete.

---

## 9. Tooling and Platform Migration Recommendations

Only three areas justify adopting a new program — migrations, backups, and error visibility. Everywhere else the correct call is discipline changes to existing tooling, and in several areas the honest recommendation is an explicit **do-not-migrate** to prevent future churn. Each entry below carries a verdict.

### 9.1 Adopt — clear ROI

| Area | Recommendation | Verdict |
|---|---|---|
| Schema migrations | **dbmate** | Adopt (implements R1) |
| Database backups | **pgBackRest** (pg_dump cron as immediate stopgap) | Adopt (implements R5) |
| Error tracking | **GlitchTip** (self-hosted, Sentry-SDK-compatible) | Adopt |

**dbmate.** The strongest tooling case in the repo. The existing convention is plain numbered SQL files, which is exactly dbmate's model: a single static Go binary, a `schema_migrations` table, `dbmate up` applies only pending files. No ORM, no DSL — `sql/` survives almost as-is. Alternatives rejected: Alembic (ORM-flavoured; would fight raw-SQL-as-source-of-truth), Flyway (JVM dependency on a box with none), Atlas/sqitch (overkill for one maintainer). Migration path: renumber the duplicate `025`, write a one-time baseline marking `001`–`030` as applied in production, delete the replay loop from `deploy_main.sh`. The `019` exception becomes a normal pending-migration state instead of a shell `! -name` filter.

**pgBackRest.** A nightly `pg_dump -Fc` from the maintenance sidecar costs one evening and should happen regardless — but dump-only backups of a hand-tuned 128 GB database mean up to 24 h recovery point and a full-restore recovery time. pgBackRest adds WAL archiving, point-in-time recovery, and an **offsite** target (Hetzner Storage Box over SFTP, or any S3-compatible bucket). wal-g is the lighter alternative; pgBackRest wins on documentation and restore ergonomics for a solo operator restoring under stress. Rule: a backup that has not been test-restored is a hypothesis — the runbook must include a rehearsed restore.

**GlitchTip.** Today a frontend crash or unhandled API exception is invisible unless someone is tailing logs. Sentry SaaS contradicts the repo's zero-vendor posture; self-hosted Sentry is a resource monster (~16 GB, a dozen containers). GlitchTip is Sentry-API-compatible in two–three containers; the FastAPI and browser Sentry SDKs point at it unchanged. Pair with `pg_stat_statements` — not a new program, and already flagged in `SCHEMA_AND_REFACTOR_ADVISORY.md` §1.2 as "the single highest-leverage db observability change" in May, still unshipped. Optionally add Uptime Kuma (one container) for external health probes, since the only post-deploy check today is a curl loop inside the deploy script.

### 9.2 Consider — real but second-order

- **Python installs → uv, with a lockfile.** The Python side has the same reproducibility gap flagged for yarn (D5): `pip install -r requirements.txt` in three Dockerfiles and four CI jobs. `uv` is a drop-in pip replacement, dramatically faster in CI, and `uv lock` provides the Python equivalent of a frozen lockfile. Low risk, incremental. [Confidence caveat: requirements pinning strictness was not audited file-by-file; if already fully pinned with hashes, this drops to a CI-speed win only.]
- **Package manager → pnpm, or just fix yarn.** Yarn 1.x is unmaintained legacy; pnpm gives strict, content-addressed, immutable installs. But 90% of the benefit comes from the two-line fix already in §7: commit to the lockfile that exists and use `--immutable` in CI and deploy. Do that first; migrate to pnpm only if frontend infra is being touched anyway.
- **Auth → `fastapi-users` (library), not an auth program.** Keycloak/Authentik are the self-hosted IdP programs and both are wildly oversized for one app needing magic-link + passkeys — operating a second product to avoid ~500 lines. `fastapi-users` keeps identity in the existing Postgres and inside the project's audit surface, consistent with §6's Option C recommendation.

### 9.3 Explicitly do not migrate

- **Hash router → react-router / TanStack Router.** The hand-rolled router is ~150 lines, fully specified in its own docstring, and tested. Its comment names the correct re-evaluation trigger (nested route growth); accounts will not hit it. Keep.
- **asyncpg → SQLAlchemy ORM.** The query layer is raw SQL against a hand-tuned schema with MVs and plpgsql functions; an ORM fights every strength this codebase has. If accounts CRUD becomes tedious, adopt SQLAlchemy Core *for those tables only* — never wholesale.
- **docker compose → Kubernetes / Nomad / Dokku.** One box, one operator, compose profiles already doing the job. Pure ceremony. The maintenance sidecar's crond → systemd timers is likewise a lateral move.
- **Make → just.** Marginal ergonomics, real churn in docs and muscle memory. Skip.
- **Docs → MkDocs / Docusaurus.** 188 markdown files is a curation problem, not a rendering problem; a site generator makes the sprawl prettier, not smaller. The §1 archive-and-prune recommendation is the actual fix.
- **slowapi → a rate-limiting product.** When auth lands, the fix is Redis-backed storage for auth endpoints (config change) plus `limit_req` zones in the existing nginx. No new program.

### 9.4 Sequencing

dbmate and pgBackRest slot directly into recommended-sequence move 1 (R1+R5); GlitchTip rides with move 3. The tool adoptions therefore add no new workstream — they are the concrete implementations of the remediation sequence in this report. The only genuinely new decision is GlitchTip versus remaining blind to production errors; given authenticated users' data is the next product lane (§6), remaining blind is not recommended.

---

## Diligence Red-Flag Register (what an acquirer's technical DD writes down)

| # | Flag | Severity |
|---|---|---|
| D1 | No migration ledger; full SQL replay on deploy; duplicate migration number | Critical |
| D2 | No database backup/restore capability in repo | Critical |
| D3 | Mixed-version ratings population, acknowledged in migration text, unresolved and invisible to users | Critical (data trust) |
| D4 | CI gates on <15% of test files; large suites run only by human ritual | High |
| D5 | Non-reproducible frontend builds (lockfile present but unused; prod-box builds) | High |
| D6 | Single DB role for app/migrate/import; credentials (sync keys, tokens-to-be) would sit plaintext in it | High |
| D7 | Second UI codebase (`_redesign`) and hidden product surface (`#colony`) in production bundle | Medium |
| D8 | Process exhaust as structure: stage-named scripts/tests/130+ stage docs, machine state in docs/, personal absolute paths committed | Medium (heavy optics cost) |
| D9 | Platform-migration residue (Emergent shim, stale CI comments) | Low-Medium |
| D10 | No accounts while per-user value accumulates across three storage idioms | Medium (product/strategic) |
| D11 | Version identity incoherence (3.0.1 / 3.1 / v3.4 ratings / "v2" CI job) | Low, but it's the first thing a reviewer notices |

**Counterweights a diligence report would also record:** exceptional write-path safety culture; best-in-class API↔frontend type contract with drift CI; real incremental-recompute architecture; incident learnings written into the code where decisions live; a maintainer who demonstrably audits himself. The debt here is concentrated, named, and fixable in weeks — which is the best kind of debt to buy.

---

## Recommended sequence (four moves, in order)

1. **R1 + R5** (migration ledger + backups, via dbmate + pgBackRest per §9.1) — one focused stage; removes both critical operational flags.
2. **R2** (ratings rebaseline closure + trust badge) — restores the core product promise.
3. **R3 + lockfile fix** (+ GlitchTip per §9.1) — makes green CI mean something and makes production errors visible.
4. **R6 + R10 residue purge** (`_redesign`, `server.py`, root plan file, ghost routes, stage-script archive, naming) — one hygiene stage that transforms diligence optics.

Accounts (§6) should be the stage *after* those four — it's the right next product lane, and it lands on foundations that can carry it.

— End of audit. All findings re-derivable from the pinned SHA; confidence labels mark the exceptions.
