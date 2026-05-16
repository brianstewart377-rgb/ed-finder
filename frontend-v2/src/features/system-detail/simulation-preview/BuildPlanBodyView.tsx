import { useState, type KeyboardEvent } from 'react';
import { AlertTriangle, CircleDotDashed, LayoutPanelTop } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SimulateBuildResponse, SystemBody } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  getBodyGroupSummary,
  getBodyGroupWarnings,
  getPlacementStatus,
  getPlacementWarnings,
  getPlanSummary,
  groupPlacementsByBody,
  type BodyGroup,
  type GroupedPlacement,
  type PlanSummary,
} from './buildPlanLayoutUtils';
import { BuildPlanLayoutDetailPanel, type LayoutSelection } from './BuildPlanLayoutDetailPanel';
import { Chip } from './components';
import { formatLocation } from './utils/formatters';

interface BuildPlanBodyViewProps {
  systemName: string;
  targetArchetype: string;
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  previewResult: SimulateBuildResponse | null;
  isPreviewResultStale: boolean;
  runningPreview: boolean;
}

export function BuildPlanBodyView({
  systemName,
  targetArchetype,
  placements,
  templates,
  bodies,
  previewResult,
  isPreviewResultStale,
  runningPreview,
}: BuildPlanBodyViewProps) {
  const [selection, setSelection] = useState<LayoutSelection>({ kind: 'summary' });
  const groups = groupPlacementsByBody(placements, templates, bodies);
  const summary = getPlanSummary({
    systemName,
    targetArchetype,
    placements,
    templates,
    bodies,
    previewResult,
    isPreviewResultStale,
    runningPreview,
    groups,
  });
  const selectSummary = () => setSelection({ kind: 'summary' });
  const selectBody = (groupKey: string) => setSelection({ kind: 'body', groupKey });
  const selectPlacement = (groupKey: string, placementIndex: number) => {
    setSelection({ kind: 'placement', groupKey, placementIndex });
  };

  return (
    <div className="space-y-3">
      <div className="rounded border border-cyan/30 bg-cyan/5 px-3 py-2 text-[11px] text-silver-dk">
        <div className="flex flex-wrap items-center gap-2">
          <LayoutPanelTop size={14} className="text-cyan" />
          <span className="font-mono uppercase tracking-[0.14em] text-cyan">Layout view</span>
          <span>Use List view for detailed editing. This view is a planning readout of the same Build Plan.</span>
        </div>
      </div>

      <PlanSummaryPanel summary={summary} />

      {summary.planWarnings.length > 0 && (
        <div className="rounded border border-gold/35 bg-gold/5 px-3 py-2">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
            <AlertTriangle size={13} />
            Plan needs review
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
            {summary.planWarnings.map((warning) => (
              <Chip key={warning.key} tone="warn">{warning.text}</Chip>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-3">
          {groups.map((group) => (
            <BodyGroupCard
              key={group.key}
              group={group}
              placements={placements}
              selected={selection.kind === 'body' && selection.groupKey === group.key}
              selectedPlacementIndex={selection.kind === 'placement' && selection.groupKey === group.key ? selection.placementIndex : null}
              onSelectBody={() => selectBody(group.key)}
              onSelectPlacement={(placementIndex) => selectPlacement(group.key, placementIndex)}
            />
          ))}
        </div>
        <BuildPlanLayoutDetailPanel
          summary={summary}
          groups={groups}
          selection={selection}
          onSelectSummary={selectSummary}
        />
      </div>
    </div>
  );
}

function PlanSummaryPanel({ summary }: { summary: PlanSummary }) {
  const primaryTone = summary.primaryPortStatus === 'one' ? 'good' : 'warn';
  const previewTone = summary.previewStatus === 'current' ? 'good' : summary.previewStatus === 'running' ? 'default' : 'warn';

  return (
    <section aria-label="Layout plan summary" className="rounded-chunk-lg border border-border/70 bg-bg2/65 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">System layout planner</div>
          <h5 className="mt-1 text-sm font-bold text-silver">{summary.systemName || 'Unknown system'}</h5>
          <p className="mt-1 font-mono text-[10px] text-silver-dk">Target: {summary.targetArchetypeLabel}</p>
        </div>
        <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
          <Chip>{summary.totalPlacements} total</Chip>
          <Chip>{summary.assignedPlacements} assigned</Chip>
          <Chip tone={summary.unassignedPlacements > 0 ? 'warn' : 'good'}>{summary.unassignedPlacements} unassigned</Chip>
          <Chip>{summary.bodiesUsed} bodies used</Chip>
          <Chip tone={primaryTone}>{summary.primaryPortLabel}</Chip>
          <Chip tone={summary.warningCount > 0 ? 'warn' : 'good'}>{summary.warningCount} warnings</Chip>
          <Chip tone={previewTone}>Preview: {summary.previewStatus}</Chip>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <SummaryMetric
          label="Yellow CP"
          value={`+${summary.yellowGenerated} / needs ${summary.yellowNeeded}`}
          warn={summary.yellowNeeded > summary.yellowGenerated}
        />
        <SummaryMetric
          label="Green CP"
          value={`+${summary.greenGenerated} / needs ${summary.greenNeeded}`}
          warn={summary.greenNeeded > summary.greenGenerated}
        />
      </div>
    </section>
  );
}

function SummaryMetric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={[
      'rounded border px-3 py-2 font-mono',
      warn ? 'border-gold/35 bg-gold/5' : 'border-border/55 bg-bg3/35',
    ].join(' ')}>
      <div className={warn ? 'text-[10px] uppercase tracking-[0.16em] text-gold' : 'text-[10px] uppercase tracking-[0.16em] text-cyan'}>
        {label}
      </div>
      <div className="mt-1 text-xs text-silver">{value}</div>
    </div>
  );
}

function BodyGroupCard({
  group,
  placements,
  selected,
  selectedPlacementIndex,
  onSelectBody,
  onSelectPlacement,
}: {
  group: BodyGroup;
  placements: SimulateBuildPlacement[];
  selected: boolean;
  selectedPlacementIndex: number | null;
  onSelectBody: () => void;
  onSelectPlacement: (placementIndex: number) => void;
}) {
  const bodyWarnings = getBodyGroupWarnings(group);
  const summary = getBodyGroupSummary(group);
  const isUnassigned = group.body === null;
  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelectBody();
    }
  };

  return (
    <section
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={group.body ? `Body group ${bodyDisplayName(group.body)}` : 'Unassigned / needs body'}
      data-testid={`layout-body-group-${group.key}`}
      onClick={onSelectBody}
      onKeyDown={handleKeyDown}
      className={[
        'rounded-chunk-lg border p-3 text-left transition-[border-color,background-color,box-shadow]',
        isUnassigned ? 'border-gold/45 bg-gold/5' : 'border-border/70 bg-bg2/65',
        selected ? 'border-cyan/80 bg-cyan/10 shadow-brand-glow' : 'hover:border-cyan/45',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h5 className={isUnassigned ? 'text-sm font-bold text-gold' : 'text-sm font-bold text-silver'}>
              {group.body ? bodyDisplayName(group.body) : 'Unassigned / needs body'}
            </h5>
            <Chip tone={isUnassigned ? 'warn' : 'default'}>
              {group.placements.length} placement{group.placements.length === 1 ? '' : 's'}
            </Chip>
            {summary.hasPrimaryPort && <Chip tone="good">Primary port body</Chip>}
            {bodyWarnings.length > 0 && <Chip tone="warn">{bodyWarnings.length} body warning{bodyWarnings.length === 1 ? '' : 's'}</Chip>}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5 font-mono text-[10px]">
            {group.body ? (
              bodyTags(group.body).map((tag) => <Chip key={tag}>{tag}</Chip>)
            ) : (
              <Chip tone="warn">Needs assignment</Chip>
            )}
            <Chip>CP: Y+{summary.yellowGenerated} G+{summary.greenGenerated}</Chip>
            <Chip>Needs: Y{summary.yellowNeeded} G{summary.greenNeeded}</Chip>
          </div>
        </div>
        {bodyWarnings.length > 0 && (
          <div className="flex max-w-md flex-wrap gap-1.5 font-mono text-[10px]">
            {bodyWarnings.map((warning) => <Chip key={warning} tone="warn">{warning}</Chip>)}
          </div>
        )}
      </div>

      <div className="mt-3 grid gap-2">
        {group.placements.map((placement) => (
          <PlacementCard
            key={`${placement.placement.build_order}-${placement.index}-${placement.placement.facility_template_id}`}
            item={placement}
            body={group.body}
            totalPlacements={placements.length}
            selected={selectedPlacementIndex === placement.index}
            onSelect={() => onSelectPlacement(placement.index)}
          />
        ))}
      </div>
    </section>
  );
}

function PlacementCard({
  item,
  body,
  totalPlacements,
  selected,
  onSelect,
}: {
  item: GroupedPlacement;
  body: SystemBody | null;
  totalPlacements: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const { placement, template, index } = item;
  const warnings = getPlacementWarnings(item, body);
  const status = getPlacementStatus(item, body);
  const confidence = template?.confidence ?? 'missing';
  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      event.stopPropagation();
      onSelect();
    }
  };

  return (
    <article
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`Placement ${placement.build_order || index + 1}: ${template?.name ?? placement.facility_template_id ?? 'Unknown facility'}`}
      data-testid={`layout-placement-${index}`}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
      onKeyDown={handleKeyDown}
      className={[
        'rounded border p-3 text-left transition-[border-color,background-color,box-shadow]',
        selected ? 'border-orange/80 bg-orange/10 shadow-brand-glow' : 'border-border/65 bg-bg3/45 hover:border-orange/50',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full border border-orange/40 bg-orange/10 text-[11px] font-mono font-bold text-orange">
              {placement.build_order || index + 1}
            </span>
            <h6 className="min-w-0 text-sm font-semibold text-silver">
              {template?.name ?? placement.facility_template_id ?? 'Unknown facility'}
            </h6>
            <Chip tone={status === 'planned' ? 'good' : 'warn'}>Status: {status}</Chip>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
            {placement.is_primary_port && <Chip tone="good">Primary port</Chip>}
            <Chip>{template ? formatLocation(template.allowed_location) : 'Unknown location'}</Chip>
            {template?.tier != null && <Chip>Tier {template.tier}</Chip>}
            {template?.pad_size && <Chip>Pad: {template.pad_size}</Chip>}
            {template?.economy && <Chip>Economy: {template.economy}</Chip>}
            {template?.category && <Chip>Role: {template.category}</Chip>}
            {template && <Chip>CP: Y+{template.yellow_cp_generated} G+{template.green_cp_generated}</Chip>}
            {template && <Chip>Needs: Y{template.yellow_cp_cost} G{template.green_cp_cost}</Chip>}
            <Chip tone={confidence === 'estimated' || confidence === 'missing' ? 'warn' : 'default'}>Confidence: {confidence}</Chip>
            {warnings.map((warning) => <Chip key={warning} tone="warn">{warning}</Chip>)}
          </div>
        </div>
        <div className="flex items-center gap-1 rounded border border-border/55 bg-bg2/55 px-2 py-1 font-mono text-[10px] text-silver-dk">
          <CircleDotDashed size={12} />
          {index + 1} of {totalPlacements}
        </div>
      </div>
      <p className="mt-2 font-mono text-[10px] text-silver-dk">
        Body assignment: {body ? bodyDisplayName(body) : item.hasUnknownBody ? `Unknown body ${item.bodyId}` : 'Unassigned'}
      </p>
    </article>
  );
}
