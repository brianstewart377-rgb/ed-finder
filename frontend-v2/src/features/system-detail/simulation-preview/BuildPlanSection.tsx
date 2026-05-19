import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Columns3, DownloadCloud, ListChecks, Plus } from 'lucide-react';
import { importSystemLayout } from '@/lib/api';
import type { FacilityTemplate, LayoutImportResponse, SimulateBuildPlacement, SimulateBuildResponse, SystemBody } from '@/types/api';
import { BuildPlanBodyView } from './BuildPlanBodyView';
import { BuildPlanEditor } from './BuildPlanEditor';
import { ModeIntro, StartModes } from './StartModes';
import { Message } from './components';
import { ARCHETYPES, type StartMode } from './types';
import type { TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { PlannerWorkspaceCommand } from '@/features/colony-planner/workspaceUtils';
import { bodyDisplayName } from './buildPlanLayoutUtils';

type BuildPlanViewMode = 'list' | 'body';

export function BuildPlanSection({
  systemId64,
  systemName,
  startMode,
  hasRecommendedBuild,
  loadingRecommended,
  targetArchetype,
  onTargetArchetypeChange,
  placements,
  templates,
  bodies,
  templatesLoading,
  templatesErrorMessage,
  optimiserCandidateOriginLabel,
  optimiserCandidateWasEdited,
  initialAssumptions,
  previewResult,
  isPreviewResultStale,
  runningPreview,
  onUseRecommended,
  onBlank,
  onShowSuggestedBuilds,
  onAddPlacement,
  onUpdatePlacement,
  onRemovePlacement,
  onMovePlacement,
  topologySelection,
  workspaceCommand,
}: {
  systemId64: number;
  systemName: string;
  startMode: StartMode;
  hasRecommendedBuild: boolean;
  loadingRecommended: boolean;
  targetArchetype: string;
  onTargetArchetypeChange: (value: string) => void;
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  templatesLoading: boolean;
  templatesErrorMessage?: string | null;
  optimiserCandidateOriginLabel: string | null;
  optimiserCandidateWasEdited: boolean;
  initialAssumptions: string[];
  previewResult: SimulateBuildResponse | null;
  isPreviewResultStale: boolean;
  runningPreview: boolean;
  onUseRecommended: () => void;
  onBlank: () => void;
  onShowSuggestedBuilds?: () => void;
  onAddPlacement: (bodyId?: string | null) => void;
  onUpdatePlacement: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  onRemovePlacement: (index: number) => void;
  onMovePlacement: (index: number, direction: -1 | 1) => void;
  topologySelection?: TopologySelection;
  workspaceCommand?: PlannerWorkspaceCommand | null;
}) {
  const [viewMode, setViewMode] = useState<BuildPlanViewMode>('list');
  const [layoutImportResult, setLayoutImportResult] = useState<LayoutImportResponse | null>(null);
  const [layoutImportError, setLayoutImportError] = useState<string | null>(null);
  const [layoutImportRunning, setLayoutImportRunning] = useState(false);
  const lastHandledWorkspaceCommandToken = useRef<number | null>(null);
  useEffect(() => {
    setLayoutImportResult(null);
    setLayoutImportError(null);
    setLayoutImportRunning(false);
  }, [systemId64]);
  const assignedUnknownBodyIds = getAssignedUnknownBodyIds(placements, bodies);
  const templateCatalogueEmpty = !templatesLoading && !templatesErrorMessage && templates.length === 0;
  const selectedBodyId = topologySelection?.type === 'body' ? topologySelection.bodyId : null;
  const selectedPlacementIndex = topologySelection?.type === 'placement' ? topologySelection.placementIndex : null;
  const selectedBody = selectedBodyId
    ? bodies.find((body) => body.id != null && String(body.id) === selectedBodyId) ?? null
    : null;
  const selectedBodyPlacementCount = selectedBodyId
    ? placements.filter((placement) => String(placement.local_body_id ?? '') === selectedBodyId).length
    : 0;

  useEffect(() => {
    if (selectedBodyId) setViewMode('body');
  }, [selectedBodyId]);

  useEffect(() => {
    if (!workspaceCommand) return;
    if (lastHandledWorkspaceCommandToken.current === workspaceCommand.token) return;
    lastHandledWorkspaceCommandToken.current = workspaceCommand.token;
    if (workspaceCommand.kind === 'add-structure') {
      setViewMode('body');
      onAddPlacement(workspaceCommand.bodyId);
      return;
    }
    if (workspaceCommand.kind === 'review-structures') {
      setViewMode('body');
    }
  }, [onAddPlacement, workspaceCommand]);

  const handleImportLayout = async () => {
    setLayoutImportRunning(true);
    setLayoutImportError(null);
    try {
      const result = await importSystemLayout(systemId64, { source: 'spansh' });
      setLayoutImportResult(result);
    } catch (error) {
      setLayoutImportResult(null);
      setLayoutImportError(error instanceof Error ? error.message : 'Layout import failed.');
    } finally {
      setLayoutImportRunning(false);
    }
  };

  return (
    <section aria-label="Build Plan" className="rounded-chunk-lg border border-border/60 bg-bg2/30 p-4">
      <div className="mb-3">
        <h4 className="font-mono text-[11px] uppercase tracking-[0.18em] text-orange">Build Plan</h4>
        <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
          Select a body, add structures deliberately, then run Preview when ready.
        </p>
      </div>
      <BuildPlanStatus
        placementCount={placements.length}
        previewResult={previewResult}
        isPreviewResultStale={isPreviewResultStale}
        runningPreview={runningPreview}
      />
      <LayoutImportControl
        running={layoutImportRunning}
        result={layoutImportResult}
        errorMessage={layoutImportError}
        assignedUnknownBodyIds={assignedUnknownBodyIds}
        onImport={() => void handleImportLayout()}
      />
      <StartModes
        mode={startMode}
        hasRecommendedBuild={hasRecommendedBuild}
        loadingRecommended={loadingRecommended}
        onUseRecommended={onUseRecommended}
        onBlank={onBlank}
        onShowSuggestedBuilds={onShowSuggestedBuilds}
      />
      {optimiserCandidateOriginLabel && (
        <div className="mt-3 rounded border border-cyan/35 bg-cyan/5 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Suggested build origin</div>
          <div className="mt-1 text-[11px] text-silver-dk">
            {optimiserCandidateWasEdited ? (
              <>Started from suggested build: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. This Build Plan has been edited since loading.</>
            ) : (
              <>Copied suggested build: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. You can edit the Build Plan and run Preview when ready.</>
            )}
          </div>
        </div>
      )}
      {initialAssumptions.length > 0 && (
        <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">Estimated assumptions</div>
          <ul className="mt-1 space-y-1 font-mono text-[11px] text-silver-dk">
            {initialAssumptions.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <ModeIntro mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />
      </div>

      <div className="mt-3 rounded-chunk-lg border border-border/60 bg-bg3/25 p-3">
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <label className="space-y-1">
            <span className="block text-[10px] font-mono uppercase tracking-[0.16em] text-silver-dk">
              Target archetype
            </span>
            <select
              value={targetArchetype}
              onChange={(e) => onTargetArchetypeChange(e.target.value)}
              className="w-full"
            >
              {ARCHETYPES.map((archetype) => (
                <option key={archetype.id} value={archetype.id}>{archetype.label}</option>
              ))}
            </select>
            <span className="block text-[10px] text-silver-dk font-mono leading-snug">
              Target for Suggested Builds and Preview.
            </span>
          </label>
          <button
            type="button"
            onClick={() => onAddPlacement()}
            disabled={templates.length === 0}
            className="self-end inline-flex items-center justify-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-xs font-mono text-silver hover:border-orange/60 hover:text-orange disabled:opacity-45"
          >
            <Plus size={14} />
            Add Facility
          </button>
        </div>
        {selectedBodyId && (
          <div
            data-testid="topology-planner-context"
            className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded border border-cyan/30 bg-cyan/5 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
                Body context
              </div>
              <p className="mt-0.5 truncate text-[11px] font-mono text-silver-dk">
                {selectedBody ? bodyDisplayName(selectedBody) : 'Selected topology body'} - {selectedBodyPlacementCount} matching placement{selectedBodyPlacementCount === 1 ? '' : 's'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onAddPlacement(selectedBodyId)}
              data-testid="add-structure-selected-body"
              disabled={templates.length === 0 || !selectedBody}
              className="inline-flex items-center justify-center gap-2 rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-2 text-xs font-mono text-cyan hover:bg-cyan/20 disabled:opacity-45"
            >
              <Plus size={14} />
              Add structure here
            </button>
          </div>
        )}
        {selectedPlacementIndex != null && (
          <div
            data-testid="topology-placement-context"
            className="mt-3 rounded border border-orange/30 bg-orange/5 px-3 py-2 font-mono text-[11px] text-silver-dk"
          >
            Currently viewing placement {selectedPlacementIndex + 1}. The matching editor row is highlighted in List view.
          </div>
        )}
      </div>

      {templatesLoading && (
        <div className="mt-3 rounded border border-border/60 bg-bg3/30 px-3 py-3 text-xs font-mono text-silver-dk">
          Loading facility catalogue...
        </div>
      )}

      {templatesErrorMessage && (
        <div className="mt-3"><Message tone="warn" items={[templatesErrorMessage]} /></div>
      )}

      {templateCatalogueEmpty && (
        <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2 text-[11px] font-mono text-gold">
          Facility catalogue is empty. Structures cannot be added until templates load.
        </div>
      )}

      <div className="mt-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Planner views</div>
            <p className="mt-0.5 text-[10px] font-mono text-silver-dk">
              Body view is the default planning surface. List view is the advanced editor.
            </p>
          </div>
          <div className="inline-flex rounded-chunk-sm border border-border/70 bg-bg3/40 p-1">
            <BuildPlanViewButton
              active={viewMode === 'list'}
              icon={<ListChecks size={14} />}
              label="List view"
              helper="Edit placements in order."
              testId="build-plan-list-view"
              onClick={() => setViewMode('list')}
            />
            <BuildPlanViewButton
              active={viewMode === 'body'}
              icon={<Columns3 size={14} />}
              label="Body view"
              helper="Plan by body."
              testId="build-plan-body-view"
              onClick={() => setViewMode('body')}
            />
          </div>
        </div>
        {placements.length === 0 ? (
          <div className="rounded-chunk-lg border border-dashed border-gold/45 bg-gold/5 px-4 py-6 text-center">
            <div className="font-mono text-xs text-gold">
              {startMode === 'blank_advanced' ? 'Blank manual Build Plan' : 'No recommended build loaded yet'}
            </div>
            <div className="mt-1 text-[11px] text-silver-dk">
              {startMode === 'blank_advanced'
                ? 'Select a body and add a structure there.'
                : 'Select a body, generate Suggested Builds, or start blank.'}
            </div>
          </div>
        ) : (
          viewMode === 'body' ? (
            <BuildPlanBodyView
              systemName={systemName}
              targetArchetype={targetArchetype}
              placements={placements}
              templates={templates}
              bodies={bodies}
              previewResult={previewResult}
              isPreviewResultStale={isPreviewResultStale}
              runningPreview={runningPreview}
            />
          ) : (
            <BuildPlanEditor
              placements={placements}
              templates={templates}
              bodies={bodies}
              topologySelection={topologySelection}
              onUpdate={onUpdatePlacement}
              onRemove={onRemovePlacement}
              onMove={onMovePlacement}
            />
          )
        )}
      </div>
    </section>
  );
}

function LayoutImportControl({
  running,
  result,
  errorMessage,
  assignedUnknownBodyIds,
  onImport,
}: {
  running: boolean;
  result: LayoutImportResponse | null;
  errorMessage: string | null;
  assignedUnknownBodyIds: string[];
  onImport: () => void;
}) {
  const status = errorMessage ? 'failed' : result?.status ?? null;
  const tone = status === 'failed' || status === 'partial' || assignedUnknownBodyIds.length > 0 ? 'warn' : 'default';

  return (
    <div className={[
      'mb-3 rounded border px-3 py-2',
      tone === 'warn' ? 'border-gold/35 bg-gold/5' : 'border-cyan/30 bg-cyan/5',
    ].join(' ')}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className={['font-mono text-[10px] uppercase tracking-[0.16em]', tone === 'warn' ? 'text-gold' : 'text-cyan'].join(' ')}>
            System layout import
          </div>
          <p className="mt-1 text-[11px] leading-snug text-silver-dk">
            Manual refresh only. Imported layout status never changes the current Build Plan placements automatically.
          </p>
        </div>
        <button
          type="button"
          onClick={onImport}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-xs font-mono text-silver hover:border-cyan/60 hover:text-cyan disabled:opacity-45"
        >
          <DownloadCloud size={14} />
          {running ? 'Importing layout...' : 'Import / refresh system layout'}
        </button>
      </div>

      {running && (
        <p className="mt-2 rounded border border-cyan/25 bg-cyan/5 px-2 py-1 font-mono text-[10px] text-cyan">
          Import request is running...
        </p>
      )}

      {(result || errorMessage) && (
        <div className="mt-2 grid gap-2 font-mono text-[10px] text-silver-dk md:grid-cols-2">
          <ImportMetric label="Status" value={status ?? 'unknown'} warn={status === 'failed' || status === 'partial'} />
          <ImportMetric label="Source" value={result?.source ?? 'spansh'} />
          <ImportMetric label="Fetched at" value={result ? formatImportTimestamp(result.fetched_at) : 'Not available'} warn={!result} />
          <ImportMetric label="Bodies imported" value={String(result?.summary.bodies_upserted ?? 0)} />
          <ImportMetric label="Stations imported" value={String(result?.summary.stations_upserted ?? 0)} />
          <ImportMetric label="Warnings" value={String((result?.summary.warnings_count ?? 0) + assignedUnknownBodyIds.length)} warn={(result?.summary.warnings_count ?? 0) + assignedUnknownBodyIds.length > 0} />
        </div>
      )}

      {result && (
        <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
          <span className="rounded border border-border/55 bg-bg3/40 px-2 py-0.5">Bodies found: {result.summary.bodies_found}</span>
          <span className="rounded border border-border/55 bg-bg3/40 px-2 py-0.5">Stations found: {result.summary.stations_found}</span>
        </div>
      )}

      {errorMessage && (
        <p className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-[11px] text-gold">
          Layout import failed: {errorMessage}
        </p>
      )}

      {result?.errors.map((error) => (
        <p key={error} className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-[11px] text-gold">
          Layout import failed: {error}
        </p>
      ))}

      {result?.warnings.map((warning) => (
        <p key={warning} className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-[11px] text-gold">
          Layout import warning: {warning}
        </p>
      ))}

      {assignedUnknownBodyIds.length > 0 && (
        <p className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-[11px] text-gold">
          Needs review: imported/current body data does not match assigned placement body IDs ({assignedUnknownBodyIds.join(', ')}). No placements were reassigned.
        </p>
      )}
    </div>
  );
}

function ImportMetric({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={['rounded border px-2 py-1', warn ? 'border-gold/35 bg-gold/5' : 'border-border/55 bg-bg3/35'].join(' ')}>
      <div className={warn ? 'uppercase tracking-[0.14em] text-gold' : 'uppercase tracking-[0.14em] text-cyan'}>{label}</div>
      <div className="mt-0.5 break-words text-silver">{value}</div>
    </div>
  );
}

function formatImportTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function getAssignedUnknownBodyIds(placements: SimulateBuildPlacement[], bodies: SystemBody[]): string[] {
  const knownBodyIds = new Set(
    bodies
      .filter((body) => body.id != null)
      .map((body) => String(body.id)),
  );
  const unknownIds = placements
    .map((placement) => placement.local_body_id)
    .filter((bodyId): bodyId is string => Boolean(bodyId))
    .filter((bodyId) => !knownBodyIds.has(String(bodyId)));
  return Array.from(new Set(unknownIds));
}

function BuildPlanViewButton({
  active,
  icon,
  label,
  helper,
  testId,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  helper: string;
  testId: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={[
        'inline-flex min-w-[8.5rem] items-center gap-2 rounded px-2.5 py-1.5 text-left transition-colors',
        active ? 'bg-orange/15 text-orange' : 'text-silver-dk hover:bg-bg2 hover:text-silver',
      ].join(' ')}
      aria-pressed={active}
    >
      {icon}
      <span>
        <span className="block font-mono text-[10px] font-bold uppercase tracking-[0.12em]">{label}</span>
        <span className="block text-[10px] normal-case tracking-normal">{helper}</span>
      </span>
    </button>
  );
}

function BuildPlanStatus({
  placementCount,
  previewResult,
  isPreviewResultStale,
  runningPreview,
}: {
  placementCount: number;
  previewResult: SimulateBuildResponse | null;
  isPreviewResultStale: boolean;
  runningPreview: boolean;
}) {
  const placementLabel = `${placementCount} placement${placementCount === 1 ? '' : 's'} in Build Plan`;
  const status = runningPreview
    ? 'Preview is running'
    : !previewResult
      ? 'Preview not run yet'
      : isPreviewResultStale
        ? 'Preview is stale - run Preview again'
        : 'Preview matches current Build Plan';
  const guidance = runningPreview
    ? 'ED-Finder is evaluating the current Build Plan.'
    : !previewResult
      ? 'Preview has not been run for this plan yet. Run Preview to estimate the outcome.'
      : isPreviewResultStale
        ? 'Build Plan changed. Run Preview to update the prediction.'
        : 'This Preview Result was generated for the current Build Plan.';

  return (
    <div className="mb-3 rounded border border-cyan/30 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-0.5 text-cyan">{placementLabel}</span>
        <span className={isPreviewResultStale ? 'text-gold' : 'text-silver'}>{status}</span>
      </div>
      <p className="mt-1 text-silver-dk">{guidance}</p>
    </div>
  );
}
