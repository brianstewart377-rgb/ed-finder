import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import { bodyDisplayName } from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { BodyPlannerLane } from './BodySlotPlanner';

export function CanvasStructurePicker({
  body,
  lane,
  templates,
  templatesLoading,
  templatesErrorMessage,
  onClose,
  onPickTemplate,
}: {
  body: SystemBody | null;
  lane: BodyPlannerLane | null;
  templates: FacilityTemplate[];
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
          template.category,
          template.economy ?? '',
          template.allowed_location,
          template.pad_size ?? '',
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
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
            Add {laneLabel} structure
          </div>
          <h3 id="canvas-structure-picker-title" className="mt-0.5 text-base font-bold text-silver">
            {bodyName}
          </h3>
          <p className="mt-0.5 font-mono text-[10px] text-silver-dk">
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
                  <PickerFact label={template.category || 'unknown type'} />
                  {template.economy && <PickerFact label={template.economy} />}
                  {template.pad_size && <PickerFact label={`${template.pad_size} pad`} />}
                  <PickerFact label={templateLocationKind(template)} tone="cyan" />
                </span>
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

export function laneDisabledReason(body: SystemBody, lane: BodyPlannerLane): string | null {
  if (lane !== 'surface') return null;
  if (body.is_water_world === true) return 'Surface limited: water world.';
  if (body.is_landable === false) return 'Surface limited: non-landable body.';
  return null;
}

export function templateMatchesLane(template: FacilityTemplate, lane: BodyPlannerLane): boolean {
  const location = templateLocationKind(template);
  if (lane === 'orbital') return location === 'orbital' || (location === 'both' && template.is_port);
  return location === 'surface' || (location === 'both' && !template.is_port);
}

export function templateCanFitBody(template: FacilityTemplate, body: SystemBody, lane: BodyPlannerLane): boolean {
  if (laneDisabledReason(body, lane)) return false;
  const location = templateLocationKind(template);
  if (location === 'surface') return body.is_landable === true && body.is_water_world !== true;
  return true;
}

function templateDisplayName(template: FacilityTemplate): string {
  const displayName = (template as unknown as { display_name?: unknown }).display_name;
  return typeof displayName === 'string' && displayName.trim() ? displayName.trim() : template.name;
}

function PickerFact({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'cyan' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
        tone === 'cyan'
          ? 'border-cyan/35 bg-cyan/10 text-cyan'
          : 'border-border/60 bg-bg2/60 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
