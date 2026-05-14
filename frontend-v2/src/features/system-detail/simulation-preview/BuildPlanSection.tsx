import { Plus } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { BuildPlanEditor } from './BuildPlanEditor';
import { ModeIntro, StartModes } from './StartModes';
import { Message } from './components';
import { ARCHETYPES, type StartMode } from './types';

export function BuildPlanSection({
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
  onUseRecommended,
  onEditRecommended,
  onBlank,
  onAddPlacement,
  onUpdatePlacement,
  onRemovePlacement,
  onMovePlacement,
}: {
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
  onUseRecommended: () => void;
  onEditRecommended: () => void;
  onBlank: () => void;
  onAddPlacement: () => void;
  onUpdatePlacement: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  onRemovePlacement: (index: number) => void;
  onMovePlacement: (index: number, direction: -1 | 1) => void;
}) {
  return (
    <section aria-label="Build Plan" className="rounded-chunk-lg border border-border/60 bg-bg2/30 p-4">
      <div className="mb-3">
        <h4 className="font-mono text-[11px] uppercase tracking-[0.18em] text-orange">Build Plan</h4>
        <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
          Edit the facility list, body assignments, and target archetype before running the Simulation Preview.
        </p>
      </div>
      <StartModes
        mode={startMode}
        hasRecommendedBuild={hasRecommendedBuild}
        loadingRecommended={loadingRecommended}
        onUseRecommended={onUseRecommended}
        onEditRecommended={onEditRecommended}
        onBlank={onBlank}
      />
      {optimiserCandidateOriginLabel && (
        <div className="mt-3 rounded border border-cyan/35 bg-cyan/5 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Optimiser candidate origin</div>
          <div className="mt-1 text-[11px] text-silver-dk">
            {optimiserCandidateWasEdited ? (
              <>Started from optimiser candidate: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. This preview plan has been edited since loading.</>
            ) : (
              <>Loaded optimiser candidate: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. You can edit the build and run the normal preview.</>
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

      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
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
            Target archetype guides candidate generation, ranking, and preview scoring. Changing it does not change anything in-game.
          </span>
        </label>
        <button
          type="button"
          onClick={onAddPlacement}
          disabled={templates.length === 0}
          className="self-end inline-flex items-center justify-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-xs font-mono text-silver hover:border-orange/60 hover:text-orange disabled:opacity-45"
        >
          <Plus size={14} />
          Add Facility
        </button>
      </div>

      {templatesLoading && (
        <div className="mt-3 rounded border border-border/60 bg-bg3/30 px-3 py-3 text-xs font-mono text-silver-dk">
          Loading facility catalogue...
        </div>
      )}

      {templatesErrorMessage && (
        <div className="mt-3"><Message tone="warn" items={[templatesErrorMessage]} /></div>
      )}

      <div className="mt-3">
        {placements.length === 0 ? (
          <div className="rounded-chunk-lg border border-dashed border-gold/45 bg-gold/5 px-4 py-6 text-center">
            <div className="font-mono text-xs text-gold">
              {startMode === 'blank_advanced' ? 'Blank advanced simulation' : 'No recommended build loaded yet'}
            </div>
            <div className="mt-1 text-[11px] text-silver-dk">
              {startMode === 'blank_advanced'
                ? 'Start with a primary port, then add support facilities and run the preview.'
                : 'Use a recommended build when available, or choose the advanced blank mode.'}
            </div>
          </div>
        ) : (
          <BuildPlanEditor
            placements={placements}
            templates={templates}
            bodies={bodies}
            onUpdate={onUpdatePlacement}
            onRemove={onRemovePlacement}
            onMove={onMovePlacement}
          />
        )}
      </div>
    </section>
  );
}
