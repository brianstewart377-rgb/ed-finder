import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { bodyDisplayName } from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { BodyPlannerLane } from './BodySlotPlanner';
import {
  contextualEconomyLabel,
  isContextualEconomyTemplate,
  laneDisabledReason,
  missingPrerequisitesForTemplate,
  structureFamilyLabel,
  templateCanFitBody,
  templateDisplayName,
  templateMatchesLane,
  templatePrerequisiteDescriptions,
} from './structurePlanningRules';

export function CanvasStructurePicker({
  body,
  lane,
  templates,
  placements = [],
  templatesLoading,
  templatesErrorMessage,
  onClose,
  onPickTemplate,
}: {
  body: SystemBody | null;
  lane: BodyPlannerLane | null;
  templates: FacilityTemplate[];
  placements?: SimulateBuildPlacement[];
  templatesLoading: boolean;
  templatesErrorMessage?: string | null;
  onClose: () => void;
  onPickTemplate: (templateId: string) => void;
}) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    setQuery('');
  }, [body?.id, lane]);

  const bodyName = body ? bodyDisplayName(body) : 'Selected body';
  const laneLabel = lane === 'orbital' ? 'orbit' : 'surface';
  const disabledReason = body && lane ? laneDisabledReason(body, lane) : null;
  const normalisedQuery = query.trim().toLowerCase();

  const laneCompatibleTemplates = useMemo(() => (
    lane ? templates.filter((template) => templateMatchesLane(template, lane)) : []
  ), [lane, templates]);

  const bodyCompatibleTemplates = useMemo(() => (
    body && lane && !disabledReason
      ? laneCompatibleTemplates.filter((template) => templateCanFitBody(template, body, lane))
      : []
  ), [body, disabledReason, lane, laneCompatibleTemplates]);

  const visibleTemplates = useMemo(() => (
    bodyCompatibleTemplates
      .filter((template) => {
        if (!normalisedQuery) return true;
        return [
          templateDisplayName(template),
          template.name,
          template.id,
          structureFamilyLabel(template),
          template.category,
          template.economy ?? '',
          template.allowed_location,
          template.pad_size ?? '',
          `tier ${template.tier}`,
          ...templatePrerequisiteDescriptions(template),
        ].join(' ').toLowerCase().includes(normalisedQuery);
      })
      .sort((a, b) => (a.tier - b.tier) || templateDisplayName(a).localeCompare(templateDisplayName(b)))
  ), [bodyCompatibleTemplates, normalisedQuery]);

  if (!body || body.id == null || !lane) return null;

  const laneHiddenCount = Math.max(0, templates.length - laneCompatibleTemplates.length);
  const bodyHiddenCount = Math.max(0, laneCompatibleTemplates.length - bodyCompatibleTemplates.length);
  const canSelectTemplate = !templatesLoading && !templatesErrorMessage && !disabledReason;

  return (
    <section
      aria-labelledby="canvas-structure-picker-title"
      data-testid="body-structure-picker"
      data-lane={lane}
      className="rounded-chunk-lg border border-orange/35 bg-bg2/90 px-3 py-3 shadow-metal"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="canvas-structure-picker-title" className="text-base font-bold text-silver">
            Add to {bodyName}
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 font-mono text-[10px] text-silver-dk">
            <PickerFact label={laneLabel === 'orbit' ? 'Orbit lane' : 'Surface lane'} tone="cyan" />
            <span data-testid="canvas-picker-compatible-count">
              {canSelectTemplate
                ? `${visibleTemplates.length} compatible option${visibleTemplates.length === 1 ? '' : 's'}`
                : `Picker is disabled for this ${laneLabel} lane.`}
            </span>
          </p>
          <p className="sr-only">
            {canSelectTemplate
              ? `${visibleTemplates.length} compatible option${visibleTemplates.length === 1 ? '' : 's'} shown for this ${laneLabel} lane.`
              : `Picker is disabled for this ${laneLabel} lane.`}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close structure picker"
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          <X size={12} />
          Close
        </button>
      </div>

      {templatesLoading && (
        <p data-testid="canvas-picker-loading" className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-[11px] text-gold">
          Facility catalogue loading.
        </p>
      )}

      {templatesErrorMessage && (
        <p data-testid="canvas-picker-error" className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-[11px] text-gold">
          {templatesErrorMessage}
        </p>
      )}

      {disabledReason && (
        <p data-testid="canvas-picker-disabled-reason" className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-[11px] text-gold">
          {disabledReason}
        </p>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <label className="relative block">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-silver-dk">Filter structures</span>
          <Search size={13} className="pointer-events-none absolute bottom-2.5 left-2 text-silver-dk" />
          <input
            aria-label="Filter structures"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name, economy, or type"
            className="w-full rounded border border-border/70 bg-bg2 px-8 py-2 font-mono text-xs text-silver outline-none focus:border-cyan/60"
          />
        </label>
        <div data-testid="canvas-picker-compatibility-summary" className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] text-silver-dk">
          {laneHiddenCount + bodyHiddenCount > 0
            ? `${laneHiddenCount + bodyHiddenCount} incompatible hidden`
            : 'No incompatible templates hidden'}
        </div>
      </div>

      {disabledReason ? null : !templatesLoading && !templatesErrorMessage && (templates.length === 0 || visibleTemplates.length === 0) ? (
        <p data-testid="canvas-picker-empty-state" className="mt-3 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-[11px] text-silver-dk">
          No compatible structures available for this lane/body.
        </p>
      ) : visibleTemplates.length > 0 ? (
        <div className="mt-3 grid max-h-80 gap-1.5 overflow-y-auto" data-testid="canvas-picker-template-list">
          {visibleTemplates.map((template) => (
            <button
              key={template.id}
              type="button"
              data-testid={`body-structure-template-${template.id}`}
              aria-label={`Add ${templateDisplayName(template)} to ${bodyName}`}
              disabled={!canSelectTemplate}
              onClick={() => onPickTemplate(template.id)}
              className="flex items-center justify-between gap-2 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-left hover:border-orange/45 hover:bg-orange/8 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="min-w-0">
                <span className="block truncate text-[11px] font-bold text-silver">{templateDisplayName(template)}</span>
                <span className="mt-1 flex flex-wrap gap-1.5">
                  <PickerFact label={`tier ${template.tier}`} />
                  <PickerFact label={structureFamilyLabel(template)} />
                  <PickerFact label={template.category || 'unknown type'} />
                  {template.economy ? <PickerFact label={template.economy} /> : isContextualEconomyTemplate(template) ? <PickerFact label="contextual economy" tone="gold" /> : null}
                  {template.pad_size && <PickerFact label={`${template.pad_size} pad`} />}
                  <PickerFact label={templateLocationKind(template)} tone="cyan" />
                  {templatePrerequisiteDescriptions(template).length > 0 && (
                    <PickerFact
                      label={missingPrerequisitesForTemplate(template, placements, templates).length > 0
                        ? `${missingPrerequisitesForTemplate(template, placements, templates).length} prerequisite missing`
                        : 'prerequisites satisfied'}
                      tone={missingPrerequisitesForTemplate(template, placements, templates).length > 0 ? 'gold' : 'green'}
                    />
                  )}
                </span>
                {isContextualEconomyTemplate(template) && (
                  <span data-testid={`canvas-picker-contextual-economy-${template.id}`} className="mt-1 block text-[10px] leading-snug text-cyan">
                    {contextualEconomyLabel(template)}
                  </span>
                )}
                {missingPrerequisitesForTemplate(template, placements, templates).length > 0 && (
                  <span data-testid={`canvas-picker-prerequisite-warning-${template.id}`} className="mt-1 block text-[10px] leading-snug text-gold">
                    Missing prerequisite: {missingPrerequisitesForTemplate(template, placements, templates).join('; ')}. Planning can continue.
                  </span>
                )}
              </span>
              <span className="shrink-0 rounded border border-orange/35 bg-orange/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-orange">
                Add
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function PickerFact({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'cyan' | 'gold' | 'green' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
        tone === 'cyan'
          ? 'border-cyan/35 bg-cyan/10 text-cyan'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
            : tone === 'green'
              ? 'border-green/35 bg-green/10 text-green'
              : 'border-border/60 bg-bg2/60 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
