# Adversarial frontend code review — 2026-06

**Scope:** `frontend/src/` (React 19 + TypeScript 5 + Vite, TanStack Query for server cache, Zustand for local state). `docs/archive/frontend-redesign-prototype/` was confirmed **not imported by any runtime code** (`grep` for `frontend-redesign-prototype` / `docs/archive` under `src/` returns nothing) and is otherwise ignored per the mandate.
**Audited ref:** `origin/main` @ `ecfdf1a` ("docs: adversarial backend review 2026-06 …"), inspected in a fresh detached worktree (`git worktree add --detach /tmp/edfe origin/main`). The frontend tree at `ecfdf1a` is byte-identical to `0f63585`; the only delta is the backend review doc.
**Mandate:** hostile, evidence-based. **Report only — no code changes.** Each finding cites `file:line`, quotes literal code, gives a concrete failure scenario, and a verdict.

**Verdict legend**
- **CONFIRMED** — the cited code provably exhibits the described behaviour.
- **PLAUSIBLE** — the pattern is real but whether it is a defect depends on runtime data/timing/design intent static analysis can't fully settle.

Where a category came back clean, that is stated explicitly rather than padded with weak findings.

---

## 1. Silent failures

### F1.1 — Service-worker registration/update failures are swallowed — CONFIRMED (low severity)
- `src/main.tsx:54`, `src/main.tsx:66`
- **Code:**
  ```
  54:  setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
  66:  .catch(err => console.warn('[ED:Finder] SW registration failed:', err));
  ```
- **Scenario:** if SW registration or hourly `update()` fails (e.g. the served `sw.js` 404s after a bad deploy), the app gives no user-visible signal and the empty arrow swallows the update rejection entirely. Users silently keep a stale cached bundle.
- **Verdict:** CONFIRMED. Genuine silent swallow, but on a progressive-enhancement path — impact is "stale cache", not a broken screen. Lowest-priority of the silent-failure hits.

### F1.2 — Coalsack background probe swallows fetch errors — CONFIRMED (justified)
- `src/app/coalsackBackground.ts:37-38`
- **Code:**
  ```
  36:  } catch {
  37:    continue;
  38:  }
  ```
- **Scenario:** every HEAD probe that throws is silently skipped and the function falls back to `candidates[0]`. If all candidates are unreachable the UI shows the default gradient with no signal.
- **Verdict:** CONFIRMED behaviour, but the fallback is sensible and this is a purely decorative background — acceptable by design.

**Clean here:** `fetchAuthoritativeRegionLayer` (`production-regions.ts:97-105`) throws on non-OK and is surfaced through a `useQuery` error state; `useEddnFeed` maps transport failures to a user-visible `offline`/`reconnecting` status. Neither swallows silently. The global `ErrorBoundary` (`components/ErrorBoundary.tsx`) and `MapErrorBoundary` both render fallback UI, not nothing.

---

## 2. Dead code (beyond `yarn knip --files`)

### F2.1 — Unreachable camelCase fallback branch in `readTemplateStat` — CONFIRMED
- `src/features/colony-planner/plannerCanvasUtils.ts:379`
- **Code:**
  ```
  379:  const effects = template.stat_effects ?? (template as unknown as { statEffects?: Record<string, unknown> }).statEffects;
  ```
- **Scenario:** the backend/OpenAPI field is snake_case `stat_effects` (see F8.1); the API never emits `statEffects`. The `?? … .statEffects` alternative is therefore never taken — a branch that cannot execute given how the data is actually shaped.
- **Verdict:** CONFIRMED dead branch (harmless, but misleading — it implies a camelCase shape that never arrives).

**Clean here:** both map surfaces are live — `App.tsx:45-47` lazy-loads `ProductionMapTab` when `VITE_STAGE26E_PRODUCTION_MAP` is enabled, else `MapTab`; `MapTab` is additionally used by `MapFoundationWorkspaceView`. Neither is an unreachable-but-imported component. No always-constant feature-flag prop was found (the Stage-26E flag is a genuine env-driven toggle). Nothing route-level was found dead beyond what knip already gates.

---

## 3. Effect / lifecycle bugs

### F3.1 — `useEddnFeed` dedupe Set grows unbounded for the feed's lifetime — CONFIRMED (memory), PLAUSIBLE (impact)
- `src/features/eddn/useEddnFeed.ts:84-85`
- **Code:**
  ```
  84:  if (seen.current.has(key)) return false;
  85:  seen.current.add(key);
  ```
- **Scenario:** `events` state is capped at `keep` (default 30), but `seen` — the ref used to suppress duplicate events — is only ever added to, never evicted. A browser tab left on the live EDDN ticker accumulates one Set entry per unique event indefinitely; over hours of a busy relay this is monotonic heap growth with no ceiling.
- **Verdict:** CONFIRMED unbounded growth. PLAUSIBLE user impact (needs a long-lived session to matter). Same *class* of bug as the backend's unbounded batches — an accumulator with no eviction.

### F3.2 — `setTimeout` after action with no cleanup can set state post-unmount — CONFIRMED (low severity)
- `src/features/cluster-search/ClusterResultCard.tsx:71`
- **Code:**
  ```
  70:  setPlanCreated(true);
  71:  setTimeout(() => setPlanCreated(false), 2000);
  ```
- **Scenario:** this runs inside a `useCallback` click handler with no stored timer id and no cleanup. If the results list re-renders and unmounts this card within the 2 s window (e.g. the user re-runs the search), the timer fires `setPlanCreated` on an unmounted component.
- **Verdict:** CONFIRMED pattern. Low severity on React 18 (post-unmount `setState` is a no-op, not the old warning), but it is an untracked timer.

**Clean here:** every effect-scoped timer/listener/subscription I inspected tears down correctly — `WholeSystemColonyPlanner.tsx:130-131` (clearTimeout), `useAdmin.ts:228-230` (clearInterval), the three `storage` listeners (`useProfileSync`/`useFcPlanner`/`useCompare`, all `removeEventListener` in cleanup), and `useEddnFeed`'s full teardown (ES close + timers cleared + `cancelled` guard). No missing-dependency stale-closure effect was found; `useEddnFeed` correctly reads mutable state through refs.

---

## 4. API-layer discipline

**Clean.** The only raw `fetch()` calls under `src/` are `coalsackBackground.ts:29` (a HEAD probe for a static background image) and `production-regions.ts:98` (loading a static JSON asset from `import.meta.env.BASE_URL`). Neither targets an API endpoint that has a helper in `src/lib/api/*`. All backend calls go through `@/lib/api`. `src/lib/api/` is a directory with an `index.ts` barrel and no sibling flat `src/lib/api.ts`, so nothing shadows the barrel the way CLAUDE.md warns about. No violation.

---

## 5. TanStack Query misuse

### F5.1 — Observation mutations don't invalidate three of the four observed-facts read models — CONFIRMED (disjoint keys) / PLAUSIBLE (staleness impact)
- Mutations: `src/features/system-detail/simulation-preview/observations/ObservedEvidencePanel.tsx:113-119, 135-137, 152-154`
- Un-invalidated readers of the same data:
  - `provenance/ProvenanceCockpitPanel.tsx:27` → `['provenance-cockpit-observed-facts', systemId64, targetArchetype ?? null]`
  - `ExportReadinessWorkspaceView.tsx:46` → `['observed-facts-export', system.id64, targetArchetype]`
  - `SimulationPreview.tsx:103` → `['role-review-observed-facts', system.id64]`
- **Code (what the mutation actually invalidates):**
  ```
  113:  void queryClient.invalidateQueries({ queryKey: ['observed-facts', systemId64] });
  118:  void queryClient.invalidateQueries({ queryKey: ['observation-compare', systemId64] });
  119:  void queryClient.invalidateQueries({ queryKey: ['observation-review', systemId64] });
  ```
  All four un-listed readers call `listObservedFacts({ system_id64, … })` for the *same* system.
- **Scenario:** a user records (or edits/deletes) an observed fact in the Observed Evidence panel, then within the 60 s `staleTime` opens the Export Readiness view or the Provenance Cockpit → those panels still show the pre-mutation observed-fact set/count because their query keys were never invalidated. The Evidence panel itself, and the Validation panel (`observation-compare`/`observation-review`, prefix-matched), *do* update — which makes the discrepancy more confusing, not less.
- **Verdict:** CONFIRMED the three keys are disjoint from the invalidation set. PLAUSIBLE user-visible staleness (depends on the panels being mounted and the 60 s window). This is the "stale read model after a write" class flagged in the brief.

### F5.2 — Four ad-hoc `listObservedFacts` queries with four key schemes and no shared hook — CONFIRMED
- `ObservedEvidencePanel.tsx:79`, `ProvenanceCockpitPanel.tsx:28`, `ExportReadinessWorkspaceView.tsx:47`, `SimulationPreview.tsx:104`
- **Scenario:** the same endpoint is wired four times with four unrelated key roots (`observed-facts`, `provenance-cockpit-observed-facts`, `observed-facts-export`, `role-review-observed-facts`) and differing `limit`/`target_archetype` args. There is no `useObservedFacts(systemId64, …)` hook to centralise the key and its invalidation — which is precisely why F5.1 is easy to introduce and easy to miss.
- **Verdict:** CONFIRMED duplicated fetch logic; direct root cause of F5.1.

**Clean here:** `ObservedEvidencePanel`'s list key `['observed-facts', systemId64, factTypeFilter||null, statusFilter||null]` (line 72-75) correctly varies with every server-applied filter, and the mutation's `['observed-facts', systemId64]` invalidation prefix-matches all filter variants. No permanently-disabled query was found (`SimulationPreview`'s `enabled` gate is a legitimate mode guard). `ValidationPanel` correctly keys compare/review by `predictionFingerprint` and is invalidated via the `observation-compare`/`observation-review` namespaces.

---

## 6. Zustand store issues

### F6.1 — Archived projects/plans are soft-deleted and never purged (unbounded persisted growth) — PLAUSIBLE
- `src/features/colony-planner/colonyProjectStore.ts:131-141` (`archiveProject`), `src/features/expansion-plans/expansionPlanStore.ts:134-143` (`archivePlan`)
- **Code:**
  ```
  138:  [projectId]: { ...project, archived_at: now, updated_at: now },
  ```
- **Scenario:** archiving sets `archived_at` but leaves the record in the persisted `projects`/`plans` map; `activeProjectsForSystem` merely filters archived rows out of the *view*. A hard `deleteProject`/`deletePlan` exists but the archive path never calls it, so localStorage accumulates every archived project/plan forever.
- **Verdict:** PLAUSIBLE. User-scale data in localStorage, so unlikely to bite in practice, but there is genuinely no eviction on the archive path.

**Clean here:** all five stores mutate exclusively through immutable `set((state) => ({ … }))` spreads — no direct state mutation outside setters. No obvious over-broad selector causing render storms was found (components select whole slices from small stores).

---

## 7. Duplicated logic

### F7.1 — Cross-tab localStorage sync hand-rolled in three hooks — CONFIRMED
- `src/features/profile-sync/useProfileSync.ts:163-168`, `src/features/fc-planner/useFcPlanner.ts:105-110`, `src/features/compare/useCompare.ts:58-63`
- **Code (same shape in all three):**
  ```
  window.addEventListener('storage', onStorage);
  return () => window.removeEventListener('storage', onStorage);
  ```
  each paired with its own `readStorage()`/`writeStorage()` + `'storage'` event handler.
- **Scenario:** three features independently reimplement the exact cross-tab persistence that Zustand's `persist` middleware already provides and that `pinnedStore`/`myWorkStore`/`colonyProjectStore` use. Any fix to the sync semantics (e.g. debouncing, quota handling) must be applied in three places or they drift — the TS analogue of the backend's triple-copied CASE SQL.
- **Verdict:** CONFIRMED duplication.

### F7.2 — `createProjectId` and `createPlanId` are copy-pasted — CONFIRMED (minor)
- `src/features/colony-planner/colonyProjectStore.ts:269-274`, `src/features/expansion-plans/expansionPlanStore.ts:185-190`
- **Code (identical `crypto.randomUUID` fallback in both):**
  ```
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  ```
- **Verdict:** CONFIRMED minor duplication of a prefixed-UUID helper.

(See also F5.2 — duplicated observed-facts fetch logic.)

---

## 8. Type-safety erosion

### F8.1 — `FacilityTemplate` contract is bypassed with `as unknown as` for fields the generated type can't express — CONFIRMED (strongest finding)
- Generated type: `src/types/api.gen.ts:2724` `prerequisites?: Record<string, never>[];`, `:2748` `stat_effects?: Record<string, never>;`  (and `display_name` is **absent** from the type entirely).
- Casts that read the real data:
  - `src/features/colony-planner/structurePlanningRules.ts:106` — `(template as unknown as { display_name?: unknown }).display_name`
  - `src/features/colony-planner/structurePlanningRules.ts:149` — `(template as unknown as { prerequisites?: unknown } …).prerequisites`
  - `src/features/colony-planner/plannerCanvasUtils.ts:377` — `(template as unknown as Record<string, unknown>)[field]`
  - `src/features/colony-planner/plannerCanvasUtils.ts:379` — `… (template as unknown as { statEffects?: … }).statEffects`
- **Scenario:** `Record<string, never>` is the unusable type `openapi-typescript` emits from a bare Pydantic `dict` — CLAUDE.md's own type-contract note (Architecture → "Type contract") warns about exactly this ("Pydantic 2.10+ turns bare `dict` into the unusable `Record<string, never>`"). So the wire type for `prerequisites`/`stat_effects` is uninhabitable and `display_name` isn't modelled at all; the planner is forced to `as unknown as` to read fields the API really returns. Because the cast erases checking, if the backend renames `stat_effects` or drops `display_name`, `tsc` stays green and the planner silently reads `undefined` (stat totals collapse to 0 via `readTemplateStat`, structure names fall back to `template.name`) with no compile-time or runtime signal.
- **Verdict:** CONFIRMED. This is type erosion masking a real backend↔frontend contract gap, and it traces to a documented backend hazard (bare `dict` in the `FacilityTemplate` Pydantic model). Highest-value finding in this review.

### F8.2 — `previewResult as unknown as Record<string, unknown>` in ValidationPanel — CONFIRMED (justified)
- `src/features/system-detail/simulation-preview/validation/ValidationPanel.tsx:86, 109`
- **Scenario:** the compare/review endpoints accept an arbitrary JSON object as `prediction` (documented in the inline comment at lines 79-81); the cast widens a known `SimulateBuildResponse` to `Record<string, unknown>` deliberately.
- **Verdict:** CONFIRMED cast, but genuinely justified — it is not hiding a runtime mismatch. Listed for completeness, not as a defect.

### F8.3 — Unchecked `err as unknown as ApiError` in the error describer — PLAUSIBLE (minor)
- `src/features/system-detail/simulation-preview/observations/observationUtils.ts:227`
- **Scenario:** `describeApiError` casts an `unknown` caught value straight to `ApiError` before reading fields; a thrown non-`ApiError` value would read `undefined` properties. It is guarded enough in practice, but the cast defeats the `unknown` safety the signature advertises.
- **Verdict:** PLAUSIBLE minor.

---

## 9. Overcomplicated abstractions / prop-drilling

### F9.1 — Deep prop-drilling of the project-state hook into `WorkspaceSummaryRail` — PLAUSIBLE (style)
- `src/features/colony-planner/WholeSystemColonyPlanner.tsx:531-554`
- **Scenario:** ~18 individual fields and callbacks from `useWorkspaceProjectState(...)` (`projectState.*`) are spread one-by-one as props into `WorkspaceSummaryRail`. Passing the `projectState` object (or letting the rail call the hook) would remove a wide, churn-prone prop surface.
- **Verdict:** PLAUSIBLE / subjective. Not a correctness bug.

**Clean here:** the codebase uses **zero** React `createContext` providers, so there are no single-consumer context wrappers to flag; local state is Zustand + props throughout. F9.1 is the inverse trade-off (prop-drilling instead of a shared object), not needless indirection.

---

## Summary table

| # | Category | Location | Verdict |
|---|----------|----------|---------|
| F1.1 | Silent failure (SW) | `main.tsx:54,66` | CONFIRMED (low) |
| F1.2 | Silent failure (bg probe) | `coalsackBackground.ts:37` | CONFIRMED (justified) |
| F2.1 | Dead branch (camelCase fallback) | `plannerCanvasUtils.ts:379` | CONFIRMED |
| F3.1 | Unbounded dedupe Set | `useEddnFeed.ts:85` | CONFIRMED / PLAUSIBLE impact |
| F3.2 | Untracked timer → post-unmount setState | `ClusterResultCard.tsx:71` | CONFIRMED (low) |
| §4 | API-layer discipline | — | CLEAN |
| F5.1 | Mutation misses 3 observed-facts read models | `ObservedEvidencePanel.tsx:113-154` | CONFIRMED / PLAUSIBLE impact |
| F5.2 | 4 ad-hoc observed-facts queries, no shared hook | 4 files | CONFIRMED |
| F6.1 | Archived projects/plans never purged | `colonyProjectStore.ts:131`, `expansionPlanStore.ts:134` | PLAUSIBLE |
| F7.1 | Cross-tab storage sync hand-rolled ×3 | `useProfileSync/useFcPlanner/useCompare` | CONFIRMED |
| F7.2 | Duplicated id-generator helper | `colonyProjectStore.ts:269`, `expansionPlanStore.ts:185` | CONFIRMED (minor) |
| F8.1 | `FacilityTemplate` contract bypassed via `as unknown as` | `api.gen.ts:2724,2748`; `structurePlanningRules.ts:106,149`; `plannerCanvasUtils.ts:377,379` | CONFIRMED (strongest) |
| F8.2 | Justified `as unknown as` (arbitrary-JSON endpoint) | `ValidationPanel.tsx:86,109` | CONFIRMED (justified) |
| F8.3 | Unchecked error cast | `observationUtils.ts:227` | PLAUSIBLE (minor) |
| F9.1 | Deep prop-drilling of project state | `WholeSystemColonyPlanner.tsx:531-554` | PLAUSIBLE (style) |

**Method note:** all evidence gathered by `grep`/file read against a fresh detached worktree at `origin/main@ecfdf1a`. No code was modified. `yarn knip --files` output was treated as already-covered and deliberately not re-reported — F2.1 is a *branch*-level dead path, not an unused file/export. Where a hunt category was clean (API discipline; no dead routes; no direct store mutation; no React context), that is stated rather than filled with weak findings. The highest-value finding (F8.1) links a frontend type-erosion cluster back to a documented backend Pydantic-`dict` hazard; the most likely user-visible defect is F5.1 (stale observed-facts read models after a write).
