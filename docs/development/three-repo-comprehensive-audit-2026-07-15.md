# ED-Finder 3-Repo Comprehensive Audit

**Date:** 2026-07-15 | **Scope:** ed-finder, colonisation-research-engine, colony-planning-engine
**Method:** 7 parallel sub-agents + direct analysis | **Findings:** 66 across all 3 repos

---

## CRITICAL (10 findings)

| # | Area | Finding |
|---|------|---------|
| 1 | Hygiene | **CLAUDE.md not in root allowlist** — `test_repo_hygiene_contract.py` will fail on the visible root files check. CLAUDE.md must be added to `ALLOWED_VISIBLE_ROOT_FILES` |
| 2 | Data/Ops | **Nightly `FLUSHDB` nukes all Redis keys** — `scripts/nightly_update.sh:368` runs `docker compose exec -T redis redis-cli FLUSHDB`. All keys carry explicit TTLs. This causes a thundering herd on PostgreSQL every night. Remove the FLUSHDB step |
| 3 | Backend | **`sse_clients` list mutated without locking** — `apps/api/src/state.py:72`. `append()` from HTTP handlers and iteration from the pub/sub bridge with no `asyncio.Lock`. Causes `RuntimeError: list mutated during iteration`, killing the bridge silently |
| 4 | CRE↔ed-finder | **Confidence vocabulary incompatibility** — documented blocker (CLAUDE.md line 22). CRE uses numeric 0-100 banded scoring across 6 weighted components with per-layer separation. ed-finder uses a flat 7-label enum (`OBSERVED`, `VERIFIED`, ..., `UNKNOWN`) with no layering, decay tracking, or contradiction counting |
| 5 | CRE↔ed-finder | **Source-authority hierarchy inverted** — ed-finder's `source-priority.md` ranks Mega Guide 1st ("If another source conflicts, prefer the Mega Guide"). CRE's `source_priority_register.csv` ranks Mega Guide 16th ("Medium" trust, community_reference) and Frontier official sources 1st |
| 6 | Data | **Missing FK on `colony_simulations.system_id64`** — `sql/015_simulation_engine.sql:324-325`. `BIGINT NOT NULL` with no FK constraint. Deleting a system leaves orphaned simulation records |
| 7 | Ops | **4 uncommitted production hotfixes** — `docs/ai/HANDOFF_2026-07-14.md` documents edits applied directly to `/opt/ed-finder/` (nightly_update.sh, run_dirty_ratings_if_needed.sh, build_clusters.py, DB function). Will be lost on next git operation |
| 8 | CPE | **Zero shared contracts** — CPE has no API definitions, schemas, or data contracts. Integration foundation does not exist |
| 9 | Frontend | **`recharts` is a dead dependency** — `package.json` lists `"recharts": "^2.15.0"` (2.15 MB unpacked). Zero imports in `src/`. Pollutes lockfile and install time |
| 10 | CRE | **No CLAUDE.md, no CI, no tests** — the repository that defines colonisation mechanics truth has zero project instructions for Claude Code, zero GitHub Actions, zero test files |

---

## HIGH (21 findings)

### Frontend (8)
| # | Finding |
|---|---------|
| 11 | **cluster-search has zero tests** — 3 source files (ClusterSearchForm, ClusterResultCard, useClusterSearch), 0 test files |
| 12 | **expansion-plans has zero tests** — 2 source files (ExpansionPlanBadge, expansionPlanStore), 0 test files |
| 13 | **ColonyPlannerWorkspace chunk is 442 KB** — 2.4× the largest other chunk. Sub-tabs (Preview, Evidence, Validation, Export) all ship in the same lazy chunk. Should be React.lazy + Suspense per tab |
| 14 | **No icon-tree splitting** — lucide-react is used in 40 files, inflates every lazy-loaded tab. Add `manualChunks: { 'lucide-icons': ['lucide-react'] }` |
| 15 | **ChipPreview.tsx is dead code** — zero imports from production code. Should be archived or deleted |
| 16 | **No per-route error boundaries** — only one `<ErrorBoundary>` at app root. A runtime error in the colony planner tears down the entire app |
| 17 | **PWA service worker is inert** — `vite-plugin-pwa` devDependency exists, `main.tsx` registers `sw.js`, but `vite.config.ts` has no `VitePWA()` plugin config. `sw.js` is never emitted |
| 18 | **Cross-feature import coupling** — features import internal modules from distant features without public API barrels (e.g., `plannerDraftContext` imported directly by `App.tsx`, `WorkspaceModeTabs` imported by `useHashRoute`) |

### Backend (4)
| # | Finding |
|---|---------|
| 19 | **N+1 queries via repeated pool.acquire()** — archetypes endpoint makes 6 sequential DB round-trips per request instead of acquiring one connection |
| 20 | **CPU-bound endpoints with no rate limits** — `/api/simulate/build`, `/api/share/og/{id64}`, `/api/optimiser/candidates` are all unprotected |
| 21 | **Residual `_ECO_SCORE_COL` copy** — a 5th copy of the economy score column mapping survived the centralized `search_economies.py` consolidation, in `local_search.py` |
| 22 | **SQL `.format(score_col=...)` injection vector** — `archetypes.py:417` uses Python string formatting for column names. Currently safe (hardcoded dict) but fragile pattern indistinguishable from injection |

### Ops (2)
| # | Finding |
|---|---------|
| 23 | **No automated rollback script** — `deploy_main.sh` saves pre-deploy hash to `/tmp` and prints human-readable instructions. No executable `rollback.sh` |
| 24 | **`/api/health` doesn't check Redis** — Redis failure won't trigger container restart. Health probe only tests Postgres `SELECT 1` |

### Data (2)
| # | Finding |
|---|---------|
| 25 | **Redundant index `idx_sys_main_star_class`** — `main_star_class` is a `GENERATED ALWAYS AS (main_star_type) STORED` column. Both columns have identical partial indexes. Wastes ~3-4 GB |
| 26 | **SMALLINT overflow risk on ratings body-count columns** — only `cluster_summary` was widened to INTEGER. `ratings` and `system_archetype_traits` remain at risk (max 32,767). Audit with `SELECT MAX(gas_giant_count), MAX(rocky_count), MAX(hmc_count), MAX(icy_count)` |

### Docs (2)
| # | Finding |
|---|---------|
| 27 | **~120 unarchived stage docs in `docs/colonisation-redesign/`** — ROADMAP.md Foundation Sequence item 2 calls for docs triage. All Stages 2-24 are complete but remain in active directory. Only ~3 files in `docs/archive/` |
| 28 | **CLAUDE.md references non-existent `frontend/src/_redesign/`** — was archived to `docs/archive/frontend-redesign-prototype/` but doc wasn't updated |

### CRE (2)
| # | Finding |
|---|---------|
| 29 | **Knowledge base index stale** — `docs/knowledge_base_index.md` claims 10 planner rules, 10 economy rules, 8 construction rules, 5 verification items. Actual exports show 13, 20, 23, and 12 respectively |
| 30 | **Build tool has no tests** — `tools/build_release_bundle.py` is 600+ lines parsing Markdown registers with regex. No unit tests, no type checking |

### CPE (1)
| # | Finding |
|---|---------|
| 31 | **ed-finder's existing planner is a complete superset of CPE's described scope** — simulation (18 files), optimiser (13 files), recommendations (3 files), domain (7 files) already implement "Colony Plan Construction". CPE's README restates these as future work |

---

## MEDIUM (21 findings)

| # | Area | Finding |
|---|------|---------|
| 32 | Frontend | **ExpansionPlanBadge chunk at 9.8 KB** — tiny chunk from accidental code-splitting. Should fold into parent or be intentionally lazy-loaded |
| 33 | Frontend | **Legacy route types clutter `Route` enum** — `watchlist`, `pinned` listed as primary routes when they function as aliases to `my-work` |
| 34 | Frontend | **No dark/light mode toggle** — app is permanently dark mode. No `prefers-color-scheme` fallback |
| 35 | Frontend | **22 non-test files >500 lines** — `PlannerCanvasPreview.tsx` at 1,417 lines, `MyWorkWorkspace.tsx` at 1,098 lines, `api.gen.ts` at 6,090 lines |
| 36 | Frontend | **No memoization on ResultCard** — every keystroke in search re-renders all visible cards |
| 37 | Frontend | **api.gen.ts has no generation timestamp** — cannot tell when types were last regenerated or which backend version they match |
| 38 | Frontend | **Hand-written type intersections risk drift** — `api.ts` extends generated types with extra fields. New backend fields invisible until manually added |
| 39 | Frontend | **Comment block dead zone at bottom of App.tsx** — leftover section markers from refactoring |
| 40 | Frontend | **No `useCallback`/`useMemo` on ResultCard** — re-renders entire card list on every filter change |
| 41 | Frontend | **Feature directory nesting inconsistent** — some features flat, others deeply nested with components/hooks/utils subdirs |
| 42 | Backend | **`edfinder_api/` package is a cosmetic shim** — `__init__.py` uses `__path__` hack to expose parent `src/`. Zero actual code inside. CLAUDE.md misleadingly calls it "newer" |
| 43 | Backend | **Rate limiter uses `memory://` storage** — counters reset on container restart. Moved from Redis due to fragility |
| 44 | Backend | **Missing DB error boundaries in 5+ routers** — notes, watchlist, events, profile, simulate hit generic 500 on PostgresError |
| 45 | Backend | **`share_router.py` swallows DB failures at DEBUG level** — renders degraded OG card instead of surfacing error |
| 46 | Backend | **`colony_planner.py` returns 200 OK on DB failures** — frontend cannot distinguish "empty import" from "backend on fire" |
| 47 | Backend | **Duplicate cache helpers in archetypes.py** — reimplemented alongside generic `deps.py` helpers with different versioning |
| 48 | Data | **Out-of-sequence migration numbering** — `031_eddn_ring_identity_hardening.sql` appears between 025 and 026 in manifest |
| 49 | Data | **No cache invalidation granularity** — after dirty rebuild updates 500 systems, all cached responses stale until TTL expiry (up to 24h) |
| 50 | Data | **`api_cache` table has no pruning** — `expires_at` column + index exist but no scheduled DELETE |
| 51 | Docs | **Two docs floating at `docs/` root** — GRID_SLOWDOWN_MITIGATION.md and SCHEMA_AND_REFACTOR_ADVISORY.md should be under subdirectories |
| 52 | Docs | **`docs/ai/` directory not documented** — contains agent handoff files, not mentioned in CLAUDE.md or any policy |

---

## LOW (14 findings)

| # | Area | Finding |
|---|------|---------|
| 53 | Frontend | `as any` appears 5 times — all in test files ✓ |
| 54 | Frontend | `@ts-expect-error` appears 2 times — both intentional test guard coverage ✓ |
| 55 | Frontend | workbox-build/workbox-window devDependencies need a comment explaining PWA purpose |
| 56 | Frontend | `catch (e: any)` in `useClusterSearch.ts:148` — should be `unknown` |
| 57 | Backend | 7 `# type: ignore` annotations — 2 borderline (share_router.py could be fixed) |
| 58 | Backend | `_gone()` helper raises HTTPException as control flow but returns None — code smell |
| 59 | Backend | `SELECT *` on small lookup tables (facility_templates ~20 rows) — benign |
| 60 | Data | `watchlist_changelog.system_id64` lacks FK — should reference systems(id64) |
| 61 | Data | `body_slot_predictions` uses EDDN journal addressing scheme — not documented |
| 62 | Data | Backup rehearsal receipt 6 days stale — should be weekly-automated |
| 63 | Docs | Development docs missing dates in filenames — convention calls for dated names |
| 64 | Docs | 3 TODO comments in Python source — all legitimate deferred items |
| 65 | Ops | Prometheus metrics lack latency histograms, pool stats, per-status-code breakdowns |
| 66 | CPE | CPE's "System Assessment Engine" is the only genuinely new scope that doesn't overlap with existing ed-finder code |

---

## What's Working Well

| Area | Comment |
|------|---------|
| **Production code quality** | Zero `console.log()`, zero `@ts-ignore`, zero `as any`, zero bare `print()` in API source. Exceptional discipline |
| **SQL parameterization** | All user input goes through `$1, $2` parameters. No injection vectors for user data |
| **Connection pooling** | Well-configured (min=5, max=20, pgBouncer-aware, statement_timeout=15s) |
| **TypeScript strictness** | No production `as any` casts. Types generated from OpenAPI schema |
| **shared_contracts/** | Actively used across API, importer, EDDN, scripts, tests. Well-maintained |
| **Deploy script** | 7-step sequence with health checks, rollback instructions, `--skip-*` flags |
| **Operator scripts** | Clean active/archive separation, no stale references |
| **CRE evidence model** | 343 claims, 370 provenance links, 13 mechanics, per-layer confidence, contradiction tracking |
| **103 test files, 703 tests** | All passing. Test culture exists |
| **Search module** | Correctly returns 503 instead of silently degrading |

---

## Code Splitting Opportunities

| Target | Current Size | Action |
|--------|-------------|--------|
| `ColonyPlannerWorkspace` | 442 KB | `React.lazy()` + `Suspense` for sub-tabs (Preview, Evidence, Validation, Export) |
| `SystemDetailModal` | 48 KB | Lazy-load ArchetypeAssessment, RegionalPositionPanel |
| `AdminTab` | 48 KB | `React.lazy()` — never loads for normal users |
| `MyWorkWorkspace` | 40 KB | Lazy-load JournalImportPanel, Telemetry section |
| `ExpansionPlanBadge` | 10 KB | Split store: badge-only lightweight read hook vs mutation store |
| `lucide-react` | ~40 KB across chunks | `manualChunks` entry to deduplicate |

## Feature Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| Dark/light mode toggle | Medium | Permanently dark mode, no user preference |
| Responsive mobile/tablet | Medium | Desktop-first, no systematic breakpoint design |
| Keyboard navigation in planner canvas | Medium | Slot selection/placement is pointer-only |
| PWA/offline support | Medium | SW registration is inert (no vite config) |
| E2E tests in CI | High | Playwright configured but no CI integration verified |
| Bundle size budgets | Medium | No CI-enforced limits |

## Top 5 Immediate Actions

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1 | Remove nightly FLUSHDB | 1 line | Prevents daily cache stampede |
| 2 | Add asyncio.Lock on sse_clients | 1 line | Fixes pub/sub crash vector |
| 3 | Add CLAUDE.md to root allowlist | 1 line | Unbreaks hygiene test |
| 4 | Commit or revert 4 production hotfixes | 10 min | Prevents data loss |
| 5 | Add rate limits to CPU-bound endpoints | 3 decorators | Closes resource exhaustion |

## Top 5 Architectural Milestones

| # | Milestone | Depends On |
|---|-----------|-----------|
| 1 | Reconcile confidence vocabulary | CRE↔ed-finder agreement on single model |
| 2 | Define CPE shared contracts | Pydantic/JSON Schema for plan outputs, assessments |
| 3 | Wire VitePWA config | Enable offline caching, PWA manifest |
| 4 | Lazy-split ColonyPlannerWorkspace tabs | React.lazy + Suspense per cockpit mode |
| 5 | CRE CI + tests | Schema validation, export integrity, register parsing tests |
