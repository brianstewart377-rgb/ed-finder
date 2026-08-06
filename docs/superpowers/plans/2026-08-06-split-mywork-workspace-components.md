# Split MyWorkWorkspace.tsx Into Component Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink `frontend/src/features/my-work/MyWorkWorkspace.tsx` from 1098 lines to ~630 by extracting its five already-distinct, module-private presentational subcomponents into their own files under a new `frontend/src/features/my-work/components/` directory, with zero logic changes and zero changes to any file outside `frontend/src/features/my-work/`.

**Architecture:** Pure code movement, no logic changes. Five new files (`ContinueWhereLeftOff.tsx`, `SavedSystemCard.tsx`, `PlanCard.tsx`, `EmptyPanel.tsx`, `TelemetrySection.tsx`) each export exactly one component, moved verbatim from the current file. `LabelToggle` moves with `SavedSystemCard` (its only consumer); `MetricCard` and `formatCompactEventCounts` move with `TelemetrySection` (their only consumer) — all three stay module-private (not exported) in their new home, exactly as they are today. `MyWorkWorkspace.tsx` keeps its exact current path and its exported `MyWorkWorkspace` component; only its import block changes (add 5 new imports, drop imports that are no longer used directly in the orchestrator) and its trailing ~470 lines (the 7 extracted function definitions) are deleted. No barrel/index file — direct imports only.

**Tech Stack:** Frontend only (Vite + React 19 + TS 5, `frontend/`).

## Global Constraints

- No method's or component's implementation changes — every line of JSX, every prop, every helper function body moves verbatim from the current `frontend/src/features/my-work/MyWorkWorkspace.tsx` (read it before starting; it is the source of truth for every implementation. Current file is 1098 lines).
- `MyWorkWorkspace.tsx` keeps its current file path (`frontend/src/features/my-work/MyWorkWorkspace.tsx`) and keeps exporting exactly one symbol, `MyWorkWorkspace`, with the exact same props signature it has today. `App.tsx` imports `MyWorkWorkspace` from this path and must not need any change.
- `LabelToggle`, `MetricCard`, and `formatCompactEventCounts` remain non-exported (module-private) in their new files — they are not used anywhere except by the one component they move alongside.
- No new file introduces a default export; match the codebase's existing named-export convention (visible throughout the current file).

---

### Task 1: Create the five extracted component files

**Files:**
- Create: `frontend/src/features/my-work/components/ContinueWhereLeftOff.tsx`
- Create: `frontend/src/features/my-work/components/SavedSystemCard.tsx`
- Create: `frontend/src/features/my-work/components/PlanCard.tsx`
- Create: `frontend/src/features/my-work/components/EmptyPanel.tsx`
- Create: `frontend/src/features/my-work/components/TelemetrySection.tsx`
- Reference (read, do not modify yet): `frontend/src/features/my-work/MyWorkWorkspace.tsx`

**Interfaces:**
- Consumes: nothing new (first task) — each file imports directly from existing sibling/absolute modules (`../myWorkWorkspaceUtils`, `../useJournalTelemetrySummary`, `@/features/colony-planner/colonyProjectStore`, `@/features/colony-planner/plannerDraftContext`, `@/features/colony-planner/workspaceUtils`, `@/types/api`)
- Produces: named exports `ContinueWhereLeftOff`, `SavedSystemCard`, `PlanCard`, `EmptyPanel`, `TelemetrySection` — these exact names, each the default (only) export of its file — for Task 2 to import into `MyWorkWorkspace.tsx`

- [ ] **Step 1: Create `components/ContinueWhereLeftOff.tsx`**

Move verbatim from `MyWorkWorkspace.tsx` lines 632-681 (the `ContinueWhereLeftOff` function). It needs `ColonyProject` (type-only, for the `onContinuePlan` prop) and, as real value imports (needed for `ReturnType<typeof ...>` type queries, exactly as the original file does today), `selectContinuation`, `projectStatusLabel`, `formatRecentActivity`, `labelText`.

```tsx
import type { ColonyProject } from '@/features/colony-planner/colonyProjectStore';
import {
  formatRecentActivity,
  labelText,
  projectStatusLabel,
  selectContinuation,
} from '../myWorkWorkspaceUtils';

export function ContinueWhereLeftOff({
  continuation,
  onInspectSystem,
  onContinuePlan,
}: {
  continuation: ReturnType<typeof selectContinuation>;
  onInspectSystem: (id64: number) => void;
  onContinuePlan: (project: ColonyProject) => void;
}) {
  if (!continuation) return null;
  if (continuation.kind === 'plan') {
    return (
      <section data-testid="my-work-continuation" className="premium-subpanel border-orange/35 bg-orange/8 p-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange">Continue planning</p>
        <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
          {continuation.project.system_name} - {continuation.project.project_name}
        </h2>
        <p className="mt-1 text-sm text-silver">
          {projectStatusLabel(continuation.project.status)} · Updated {formatRecentActivity(continuation.project.updated_at)}
        </p>
        <button
          type="button"
          onClick={() => onContinuePlan(continuation.project)}
          className="btn-primary mt-3 text-[11px] font-mono"
        >
          Continue plan
        </button>
      </section>
    );
  }

  return (
    <section data-testid="my-work-continuation" className="premium-subpanel border-cyan/35 bg-cyan/8 p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">Ready to revisit</p>
      <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
        {continuation.system.name}
      </h2>
      <p className="mt-1 text-sm text-silver">
        Saved as {continuation.system.labels.map(labelText).join(' · ')} · No plan yet
      </p>
      <button
        type="button"
        onClick={() => onInspectSystem(continuation.system.id64)}
        className="mt-3 rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-1.5 font-mono text-[11px] font-bold text-cyan shadow-[0_14px_24px_-20px_rgba(34,211,238,0.8)] transition-colors hover:bg-cyan/20"
      >
        Inspect system
      </button>
    </section>
  );
}
```

- [ ] **Step 2: Create `components/SavedSystemCard.tsx`**

Move verbatim from `MyWorkWorkspace.tsx` lines 683-791 (`SavedSystemCard`) and lines 942-959 (`LabelToggle`, kept private — it is only used by `SavedSystemCard`, 3 call sites). Needs `SavedSystemViewModel` (type) and `formatTimestamp` (value) from `../myWorkWorkspaceUtils`, and `JournalTelemetryRecentSystem` (type) from `@/types/api`.

```tsx
import type { SavedSystemViewModel } from '../myWorkWorkspaceUtils';
import { formatTimestamp } from '../myWorkWorkspaceUtils';
import type { JournalTelemetryRecentSystem } from '@/types/api';

export function SavedSystemCard({
  system,
  telemetry,
  onInspect,
  onStartPlan,
  onContinuePlan,
  onToggleConsidering,
  onToggleFavourite,
  onToggleReadyToPlan,
  onRemove,
}: {
  system: SavedSystemViewModel;
  telemetry: JournalTelemetryRecentSystem | null;
  onInspect: () => void;
  onStartPlan: () => void;
  onContinuePlan: () => void;
  onToggleConsidering: (enabled: boolean) => void;
  onToggleFavourite: (enabled: boolean) => void;
  onToggleReadyToPlan: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <li data-testid={`saved-system-${system.id64}`} className="premium-subpanel flex flex-wrap items-start justify-between gap-4 p-4">
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base tracking-[0.1em] text-text">
              {system.name}
            </h2>
            {system.activeProject ? (
              <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange">
                Has active plan
              </span>
            ) : null}
            {system.isColonised ? (
              <span className="rounded border border-violet/35 bg-violet/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-violet">
                Colonised
              </span>
            ) : null}
            {telemetry ? (
              <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
                Personal telemetry imported
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-[11px] text-silver-dk">
            {system.planCount} associated plan{system.planCount === 1 ? '' : 's'}
            {system.latestPlanActivity ? ` · latest plan update ${formatTimestamp(system.latestPlanActivity)}` : ''}
          </p>
          {telemetry ? (
            <p className="mt-1 text-sm text-silver">
              Last observed {formatTimestamp(telemetry.last_observed_at)} · {telemetry.event_count} telemetry event{telemetry.event_count === 1 ? '' : 's'} · {telemetry.event_types.join(', ')}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <LabelToggle
            active={system.labels.includes('considering')}
            label="Considering"
            onClick={() => onToggleConsidering(!system.labels.includes('considering'))}
          />
          <LabelToggle
            active={system.labels.includes('favourite')}
            label="Favourite"
            onClick={() => onToggleFavourite(!system.labels.includes('favourite'))}
          />
          <LabelToggle
            active={system.labels.includes('ready_to_plan')}
            label="Ready to plan"
            onClick={() => onToggleReadyToPlan(!system.labels.includes('ready_to_plan'))}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onInspect}
          className="btn-metal text-[11px] font-mono"
        >
          Inspect
        </button>
        {system.activeProject ? (
          <button
            type="button"
            onClick={onContinuePlan}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartPlan}
            className="btn-primary text-[11px] font-mono"
          >
            Start plan
          </button>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="rounded border border-red/40 bg-red/10 px-3 py-1.5 font-mono text-[11px] text-red hover:bg-red/20"
        >
          Remove from saved
        </button>
      </div>
    </li>
  );
}

function LabelToggle({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
        active
          ? 'border-orange/50 bg-orange/12 text-orange'
          : 'border-border bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
      ].join(' ')}
    >
      {label}
      <span className="sr-only">{active ? ' enabled' : ' disabled'}</span>
    </button>
  );
}
```

- [ ] **Step 3: Create `components/PlanCard.tsx`**

Move verbatim from `MyWorkWorkspace.tsx` lines 793-940 (`PlanCard`). Needs `ColonyProject`, `ColonyProjectStatus` (types) from `@/features/colony-planner/colonyProjectStore`; `objectiveSummaryLabel`, `startApproachLabel` from `@/features/colony-planner/plannerDraftContext`; `humanizeArchetype` from `@/features/colony-planner/workspaceUtils`; `formatTimestamp`, `projectStatusLabel` from `../myWorkWorkspaceUtils`.

```tsx
import type {
  ColonyProject,
  ColonyProjectStatus,
} from '@/features/colony-planner/colonyProjectStore';
import {
  objectiveSummaryLabel,
  startApproachLabel,
} from '@/features/colony-planner/plannerDraftContext';
import { humanizeArchetype } from '@/features/colony-planner/workspaceUtils';
import { formatTimestamp, projectStatusLabel } from '../myWorkWorkspaceUtils';

export function PlanCard({
  project,
  isEditing,
  editingName,
  onEditNameChange,
  onBeginRename,
  onSaveRename,
  onCancelRename,
  onDuplicate,
  onArchive,
  onStatusChange,
  onContinue,
  onInspectSystem,
  onToggleColonised,
  isExplicitlyColonised,
}: {
  project: ColonyProject;
  isEditing: boolean;
  editingName: string;
  onEditNameChange: (value: string) => void;
  onBeginRename: () => void;
  onSaveRename: () => void;
  onCancelRename: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
  onStatusChange: (status: ColonyProjectStatus) => void;
  onContinue: () => void;
  onInspectSystem: () => void;
  onToggleColonised: (enabled: boolean) => void;
  isExplicitlyColonised: boolean;
}) {
  return (
    <article data-testid={`plan-card-${project.id}`} className="premium-subpanel p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          {isEditing ? (
            <div className="flex flex-wrap gap-2">
              <input
                value={editingName}
                onChange={(event) => onEditNameChange(event.target.value)}
                className="min-w-[18rem] flex-1 rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-xs text-silver"
              />
              <button
                type="button"
                onClick={onSaveRename}
                className="btn-primary text-[11px] font-mono"
              >
                Save name
              </button>
              <button
                type="button"
                onClick={onCancelRename}
                className="btn-metal text-[11px] font-mono"
              >
                Cancel
              </button>
            </div>
          ) : (
            <h3 className="truncate font-display text-sm tracking-[0.1em] text-text">
              {project.project_name}
            </h3>
          )}
          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-silver-dk">
            <span>Objective: {objectiveSummaryLabel(project.objective)}</span>
            <span>Start: {startApproachLabel(project.start_approach)}</span>
            <span>Saved locally</span>
            <span>Updated {formatTimestamp(project.updated_at)}</span>
          </div>
          <div className="grid gap-2 text-[11px] font-mono text-silver sm:grid-cols-2">
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Plan health: {project.build_plan_placements.length} placements · {humanizeArchetype(project.target_archetype)}
            </div>
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Status: {projectStatusLabel(project.status)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onContinue}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
          <button
            type="button"
            onClick={onInspectSystem}
            className="btn-metal text-[11px] font-mono"
          >
            Inspect system
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Status
        </label>
        <select
          data-testid={`plan-status-${project.id}`}
          value={project.status}
          onChange={(event) => onStatusChange(event.target.value as ColonyProjectStatus)}
          className="rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-[11px] text-silver"
        >
          <option value="draft">Draft</option>
          <option value="ready_to_build">Ready to build</option>
          <option value="building">Building</option>
          <option value="established">Established</option>
        </select>
        <button
          type="button"
          onClick={onBeginRename}
          className="btn-metal text-[11px] font-mono"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="btn-metal text-[11px] font-mono"
        >
          Duplicate
        </button>
        <button
          type="button"
          onClick={onArchive}
          className="rounded border border-gold/35 bg-gold/10 px-3 py-1.5 font-mono text-[11px] text-gold hover:bg-gold/20"
        >
          Archive
        </button>
      </div>
      {project.status === 'established' ? (
        <div className="premium-subpanel mt-3 border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
          <p>
            Established is still player-managed planning state. Use the action below if you also want this system to appear in My Colonies as explicitly colonised.
          </p>
          <button
            type="button"
            onClick={() => onToggleColonised(!isExplicitlyColonised)}
            className="mt-2 rounded border border-violet/35 bg-violet/12 px-3 py-1.5 font-mono text-[11px] text-violet hover:bg-violet/20"
          >
            {isExplicitlyColonised ? 'Remove colonised mark' : 'Mark system colonised'}
          </button>
        </div>
      ) : null}
    </article>
  );
}
```

- [ ] **Step 4: Create `components/EmptyPanel.tsx`**

Move verbatim from `MyWorkWorkspace.tsx` lines 961-968 (`EmptyPanel`). No imports needed.

```tsx
export function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="premium-subpanel px-4 py-12 text-center">
      <h2 className="font-display text-sm tracking-[0.12em] text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-silver-dk">{body}</p>
    </div>
  );
}
```

- [ ] **Step 5: Create `components/TelemetrySection.tsx`**

Move verbatim from `MyWorkWorkspace.tsx` lines 970-1082 (`TelemetrySection`), lines 1084-1092 (`MetricCard`, kept private — only used by `TelemetrySection`, 4 call sites), and lines 1094-1098 (`formatCompactEventCounts`, kept private — only used by `TelemetrySection`, 2 call sites). Needs `formatTimestamp` (value) from `../myWorkWorkspaceUtils` and `useJournalTelemetrySummary` (value import, needed for the `ReturnType<typeof useJournalTelemetrySummary>['data']` type query — this file does not call the hook itself) from `../useJournalTelemetrySummary`.

```tsx
import { formatTimestamp } from '../myWorkWorkspaceUtils';
import { useJournalTelemetrySummary } from '../useJournalTelemetrySummary';

export function TelemetrySection({
  syncKey,
  isLoading,
  error,
  telemetry,
  onInspectSystem,
}: {
  syncKey: string;
  isLoading: boolean;
  error: string | null;
  telemetry: ReturnType<typeof useJournalTelemetrySummary>['data'] | null;
  onInspectSystem: (id64: number) => void;
}) {
  return (
    <section className="space-y-4" data-testid="my-work-telemetry">
      <div className="premium-subpanel border-cyan/30 bg-cyan/8 px-3 py-2 text-sm text-silver">
        My Work telemetry is sync-key scoped and read-only. It shows what your imported journal data observed; it does not claim canonical truth or live commander identity.
      </div>
      <div className="rounded border border-border/60 bg-bg2/35 px-3 py-2 font-mono text-[11px] text-silver-dk">
        Telemetry scope: <span className="text-cyan">{syncKey}</span>
      </div>
      {isLoading ? (
        <div className="premium-subpanel px-4 py-8 text-sm text-silver-dk">
          Loading telemetry summary...
        </div>
      ) : null}
      {error ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red">
          {error}
        </div>
      ) : null}
      {!isLoading && !error && telemetry ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Imports" value={telemetry.runs_count} detail={telemetry.last_imported_at ? `Last import ${formatTimestamp(telemetry.last_imported_at)}` : 'No imports yet'} />
            <MetricCard label="Observed systems" value={telemetry.systems_observed} detail="Distinct systems seen in your staged journal telemetry" />
            <MetricCard label="Body observations" value={telemetry.body_observation_count} detail="Scan and signal events captured from your journal imports" />
            <MetricCard label="Docked events" value={telemetry.docked_observation_count} detail="Station visit observations captured from your journal imports" />
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div className="premium-subpanel space-y-3 p-4">
              <div>
                <h2 className="font-display text-base tracking-[0.1em] text-text">Recently observed systems</h2>
                <p className="mt-1 text-sm text-silver-dk">
                  Recent systems found in your imported journal history. This is your personal reference and does not alter shared system data.
                </p>
              </div>
              {telemetry.recent_systems.length === 0 ? (
                <p className="text-sm text-silver-dk">No journal systems yet. Import journal files above to start building your personal history.</p>
              ) : (
                <ul className="space-y-2">
                  {telemetry.recent_systems.map((system) => (
                    <li key={system.system_id64} className="premium-toolbar flex flex-wrap items-center justify-between gap-3 rounded-2xl px-3 py-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-display text-sm tracking-[0.08em] text-text">{system.system_name}</div>
                        <div className="mt-1 text-sm text-silver-dk">
                          {system.event_count} event{system.event_count === 1 ? '' : 's'} · {system.event_types.join(', ')} · Last observed {formatTimestamp(system.last_observed_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => onInspectSystem(system.system_id64)}
                        className="btn-metal text-[11px] font-mono"
                      >
                        Inspect system
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-4">
              <div className="premium-subpanel space-y-3 p-4">
                <div>
                  <h2 className="font-display text-base tracking-[0.1em] text-text">Recent import runs</h2>
                  <p className="mt-1 text-sm text-silver-dk">
                    Bounded receipts for your recent sync-key journal imports.
                  </p>
                </div>
                {telemetry.recent_runs.length === 0 ? (
                  <p className="text-sm text-silver-dk">No recent runs yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {telemetry.recent_runs.map((run) => (
                      <li key={run.run_key} className="rounded border border-border/40 bg-bg1/35 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">{run.status}</span>
                          <span className="font-mono text-[11px] text-silver-dk">{run.run_key}</span>
                        </div>
                        <p className="mt-2 text-sm text-silver">
                          Staged {run.observations_staged} · Duplicates {run.duplicates_skipped}
                        </p>
                        <p className="mt-1 text-sm text-silver-dk">
                          {formatCompactEventCounts(run.event_counts)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="premium-subpanel space-y-3 p-4">
                <h2 className="font-display text-base tracking-[0.1em] text-text">Event mix</h2>
                <p className="text-sm text-silver-dk">
                  {formatCompactEventCounts(telemetry.event_counts)}
                </p>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="premium-subpanel p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mt-1 text-2xl text-text">{value.toLocaleString()}</div>
      <div className="mt-2 text-sm text-silver-dk">{detail}</div>
    </div>
  );
}

function formatCompactEventCounts(eventCounts: Record<string, number>): string {
  const entries = Object.entries(eventCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return 'No observed events recorded yet.';
  return entries.map(([eventType, count]) => `${eventType} ${count}`).join(' · ');
}
```

- [ ] **Step 6: Verify no function or helper was missed**

Run: `grep -nE "^(export )?function (ContinueWhereLeftOff|SavedSystemCard|LabelToggle|PlanCard|EmptyPanel|TelemetrySection|MetricCard|formatCompactEventCounts)" frontend/src/features/my-work/components/*.tsx`
Expected: exactly 8 matches, one per name, each in the file this step's design assigns it to (`ContinueWhereLeftOff.tsx`: `ContinueWhereLeftOff`; `SavedSystemCard.tsx`: `SavedSystemCard`, `LabelToggle`; `PlanCard.tsx`: `PlanCard`; `EmptyPanel.tsx`: `EmptyPanel`; `TelemetrySection.tsx`: `TelemetrySection`, `MetricCard`, `formatCompactEventCounts`).

---

### Task 2: Update MyWorkWorkspace.tsx, verify, smoke-test, commit

**Files:**
- Modify: `frontend/src/features/my-work/MyWorkWorkspace.tsx`

**Interfaces:**
- Consumes: `ContinueWhereLeftOff`, `SavedSystemCard`, `PlanCard`, `EmptyPanel`, `TelemetrySection` (Task 1)
- Produces: `export function MyWorkWorkspace(...)` — same signature as today; this is the only symbol anything outside `frontend/src/features/my-work/` imports (confirmed via grep: only `App.tsx` does, unchanged import path)

- [ ] **Step 1: Replace the import block**

Replace `MyWorkWorkspace.tsx` lines 1-38 (everything from `import { useMemo, useState } from 'react';` through `import type { JournalTelemetryRecentSystem } from '@/types/api';`) with:

```tsx
import { useMemo, useState } from 'react';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { UsePinned } from '@/features/pinned/usePinned';
import {
  useColonyProjectStore,
  type ColonyProject,
} from '@/features/colony-planner/colonyProjectStore';
import {
  useMyWorkStore,
  type SavedSystemLabel,
} from './myWorkStore';
import {
  buildColonies,
  buildSavedSystems,
  formatTimestamp,
  groupPlansBySystem,
  selectContinuation,
  type SavedSystemViewModel,
} from './myWorkWorkspaceUtils';
import { JournalImportPanel } from '@/features/journal-import/JournalImportPanel';
import { useJournalTelemetrySummary } from './useJournalTelemetrySummary';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import {
  useExpansionPlanStore,
  type ExpansionPlan,
} from '@/features/expansion-plans/expansionPlanStore';
import { computeExpansionPlanStatus } from './expansionPlanStatus';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import type { JournalTelemetryRecentSystem } from '@/types/api';
import { ContinueWhereLeftOff } from './components/ContinueWhereLeftOff';
import { SavedSystemCard } from './components/SavedSystemCard';
import { PlanCard } from './components/PlanCard';
import { EmptyPanel } from './components/EmptyPanel';
import { TelemetrySection } from './components/TelemetrySection';
```

This drops `type ColonyProjectStatus` (only referenced inside the now-extracted `PlanCard`), `objectiveSummaryLabel`/`startApproachLabel` (only used inside the now-extracted `PlanCard`), `humanizeArchetype` (only used inside the now-extracted `PlanCard`), and `formatRecentActivity`/`labelText`/`projectStatusLabel` (only used inside the now-extracted `ContinueWhereLeftOff`/`PlanCard`) — none of these are referenced anywhere else in the file (verify in Step 3 below; typecheck/lint catch any miss).

- [ ] **Step 2: Delete the extracted function definitions**

Delete everything from the line `function ContinueWhereLeftOff({` (originally line 632, immediately after the `MyWorkWorkspace` component's closing `}` and a blank line) through the end of the file (originally line 1098, the closing `}` of `formatCompactEventCounts`). Do not change anything between the new import block (Step 1) and this deleted region — the `type MyWorkSection` declaration, `MyWorkWorkspaceProps` interface, `SECTION_OPTIONS`/`SAVED_LABEL_FILTERS` constants, and the entire `export function MyWorkWorkspace({ ... }) { ... }` body (originally lines 40-630) are unchanged, including its JSX, which already calls `<ContinueWhereLeftOff .../>`, `<SavedSystemCard .../>`, `<PlanCard .../>`, `<EmptyPanel .../>` (4 call sites), and `<TelemetrySection .../>` by these exact names — those calls now resolve to the imported components instead of file-local functions.

The file should end with the `MyWorkWorkspace` component's closing `}` (immediately after the closing `</section>` of its returned JSX).

- [ ] **Step 3: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors. An unused import (from Step 1) or a missed reference to a moved function would surface here.

- [ ] **Step 4: Lint**

Run: `cd frontend && yarn lint`
Expected: passes (0 errors; pre-existing unrelated warnings are fine).

- [ ] **Step 5: Knip unused-file/export check**

Run: `cd frontend && yarn knip --files`
Expected: passes — no new unused-export warnings.

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && yarn test`
Expected: passes in full, including `MyWorkWorkspace.test.tsx` unchanged (it only imports and renders `MyWorkWorkspace` black-box; it does not import any of the 5 extracted components directly — confirmed by grep before this plan was written).

- [ ] **Step 7: Production build**

Run: `cd frontend && yarn build`
Expected: succeeds with no errors.

- [ ] **Step 8: Manual smoke check**

Start the dev server (`yarn dev`) and the local API server, then in a browser navigate to My Work and exercise all 5 tabs:
- **Saved Systems** — confirm cards render (tests `SavedSystemCard`/`LabelToggle`); toggle a label (Considering/Favourite/Ready to plan) and confirm it updates.
- **Plans** — confirm plan cards render (tests `PlanCard`); rename a plan, change its status dropdown, confirm both persist.
- **Expansion Plans** — confirm this tab still renders (unchanged inline JSX, not extracted — sanity check nothing else broke).
- **My Colonies** — confirm this tab still renders (unchanged inline JSX, not extracted).
- **Telemetry** — confirm the tab renders (tests `TelemetrySection`/`MetricCard`); if any journal telemetry exists locally, confirm the metrics and recent-systems list render.

Also confirm the "Continue where you left off" banner appears when applicable (tests `ContinueWhereLeftOff`) and that empty-state messaging appears correctly when a tab has no data (tests `EmptyPanel`).

Confirm no new console errors versus a pre-change baseline.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/features/my-work/MyWorkWorkspace.tsx frontend/src/features/my-work/components/
git commit -m "Split MyWorkWorkspace.tsx into component files

frontend/src/features/my-work/MyWorkWorkspace.tsx (1098 lines) shrinks to
~630 - ContinueWhereLeftOff, SavedSystemCard, PlanCard, EmptyPanel, and
TelemetrySection move to frontend/src/features/my-work/components/, one
file each, verbatim. LabelToggle moves with SavedSystemCard and
MetricCard/formatCompactEventCounts move with TelemetrySection (their
only consumers), staying module-private. No logic changes, no barrel
file, no changes outside frontend/src/features/my-work/ - App.tsx's
import of MyWorkWorkspace is unaffected. See
docs/superpowers/specs/2026-08-06-split-mywork-workspace-components-design.md."
```

---

## Self-Review

**Spec coverage:** All 5 extracted components plus their 3 private co-located helpers (`LabelToggle`, `MetricCard`, `formatCompactEventCounts`) are named explicitly with full verbatim code in Task 1. The import-block rewrite and trailing-code deletion for `MyWorkWorkspace.tsx` are both fully specified in Task 2, including the exact reasoning for every dropped import.

**Placeholder scan:** No TBD/TODO. Every step shows complete code, not a description of code.

**Type consistency:** Component prop names and types in each new file match the original file's exact signatures (verified line-by-line against the current `MyWorkWorkspace.tsx` while writing this plan). `ReturnType<typeof selectContinuation>` and `ReturnType<typeof useJournalTelemetrySummary>['data']` type-query patterns are preserved exactly as the original file uses them, requiring `selectContinuation` and `useJournalTelemetrySummary` to be real (non-type-only) imports in `ContinueWhereLeftOff.tsx` and `TelemetrySection.tsx` respectively, exactly as the original file imports them as values today.
