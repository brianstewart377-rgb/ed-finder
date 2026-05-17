import { Info, RotateCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import type { SystemBody } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  getBodyGroupSummary,
  getBodyGroupWarnings,
  getPlacementStatus,
  getPlacementWarnings,
  type BodyGroup,
  type GroupedPlacement,
  type PlanSummary,
} from './buildPlanLayoutUtils';
import { Chip } from './components';
import { formatLocation } from './utils/formatters';

export type LayoutSelection =
  | { kind: 'summary' }
  | { kind: 'body'; groupKey: string }
  | { kind: 'placement'; groupKey: string; placementIndex: number };

export function BuildPlanLayoutDetailPanel({
  summary,
  groups,
  selection,
  onSelectSummary,
}: {
  summary: PlanSummary;
  groups: BodyGroup[];
  selection: LayoutSelection;
  onSelectSummary: () => void;
}) {
  const selectedGroup = selection.kind === 'summary'
    ? null
    : groups.find((group) => group.key === selection.groupKey) ?? null;
  const selectedPlacement = selection.kind === 'placement'
    ? selectedGroup?.placements.find((item) => item.index === selection.placementIndex) ?? null
    : null;

  return (
    <aside
      aria-label="Layout selection detail"
      data-testid="layout-detail-panel"
      className="rounded-chunk-lg border border-cyan/30 bg-bg2/75 p-3 xl:sticky xl:top-3 xl:self-start"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
            <Info size={13} />
            Layout detail
          </div>
          <div className="mt-1 font-mono text-[11px] text-silver-dk">Read-only planning readout</div>
          <h5 className="mt-1 text-sm font-bold text-silver">
            {selection.kind === 'summary'
              ? 'Select a body or placement'
              : selectedPlacement
                ? selectedPlacement.template?.name ?? selectedPlacement.placement.facility_template_id ?? 'Unknown facility'
                : selectedGroup?.body
                  ? bodyDisplayName(selectedGroup.body)
                  : 'Unassigned / needs body'}
          </h5>
        </div>
      <button
        type="button"
        onClick={onSelectSummary}
        className="inline-flex items-center gap-1 rounded border border-border/70 bg-bg3/50 px-2 py-1 font-mono text-[10px] text-silver-dk hover:border-cyan/60 hover:text-cyan"
      >
        <RotateCcw size={12} />
        Summary
      </button>
      </div>

      {selection.kind === 'summary' && <SummaryDetail summary={summary} />}
      {selection.kind === 'body' && selectedGroup && <BodyDetail group={selectedGroup} summary={summary} />}
      {selection.kind === 'placement' && selectedGroup && selectedPlacement && (
        <PlacementDetail group={selectedGroup} item={selectedPlacement} summary={summary} />
      )}
      {selection.kind !== 'summary' && (!selectedGroup || (selection.kind === 'placement' && !selectedPlacement)) && (
        <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2 text-[11px] text-silver-dk">
          This selection no longer matches the current Build Plan. Review the current layout summary.
        </div>
      )}
    </aside>
  );
}

function SummaryDetail({ summary }: { summary: PlanSummary }) {
  return (
    <div className="mt-3 space-y-3">
      <p className="rounded border border-cyan/20 bg-cyan/5 px-2 py-1 font-mono text-[11px] leading-snug text-silver-dk">
        Pick a body group or placement card to inspect what it contributes. Detailed edits stay in List view.
      </p>
      <DetailSection title="Placement counts">
        <p className="text-[11px] text-silver-dk">
          Totals, assignment status, and warning totals for the current plan.
        </p>
      </DetailSection>
      <DetailGrid>
        <DetailItem label="Total placements" value={String(summary.totalPlacements)} />
        <DetailItem label="Assigned" value={String(summary.assignedPlacements)} />
        <DetailItem label="Unassigned" value={String(summary.unassignedPlacements)} tone={summary.unassignedPlacements > 0 ? 'warn' : 'default'} />
        <DetailItem label="Bodies used" value={String(summary.bodiesUsed)} />
        <DetailItem label="Primary port" value={summary.primaryPortLabel} tone={summary.primaryPortStatus === 'one' ? 'default' : 'warn'} />
        <DetailItem label="Warnings" value={String(summary.warningCount)} tone={summary.warningCount > 0 ? 'warn' : 'default'} />
        <DetailItem label="Preview" value={summary.previewStatus} tone={summary.previewStatus === 'current' ? 'default' : 'warn'} />
        <DetailItem label="CP visible" value={`Y+${summary.yellowGenerated}/${summary.yellowNeeded} G+${summary.greenGenerated}/${summary.greenNeeded}`} />
      </DetailGrid>
      <NextAction summary={summary} />
    </div>
  );
}

function BodyDetail({ group, summary }: { group: BodyGroup; summary: PlanSummary }) {
  const bodySummary = getBodyGroupSummary(group);
  const warnings = getBodyGroupWarnings(group);
  const name = group.body ? bodyDisplayName(group.body) : 'Unassigned / needs body';

  return (
    <div className="mt-3 space-y-3">
      <DetailSection title="Selected body">
        <p className="text-[11px] text-silver-dk">
          This panel explains current body-level placement impact and warnings.
        </p>
      </DetailSection>
      <DetailGrid>
        <DetailItem label="Body" value={name} tone={group.body ? 'default' : 'warn'} />
        <DetailItem label="Placements" value={String(group.placements.length)} />
        <DetailItem label="Primary port here" value={bodySummary.hasPrimaryPort ? 'Yes' : 'No'} tone={bodySummary.hasPrimaryPort ? 'default' : 'warn'} />
        <DetailItem label="CP visible" value={`Y+${bodySummary.yellowGenerated}/${bodySummary.yellowNeeded} G+${bodySummary.greenGenerated}/${bodySummary.greenNeeded}`} />
      </DetailGrid>
      <TagList body={group.body} />
      <WarningList warnings={warnings} emptyLabel="No body-level warnings from current layout data." />
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Placements on this body</div>
        <ul className="mt-2 space-y-1 font-mono text-[11px] text-silver-dk">
          {group.placements.map((item) => (
            <li key={`${item.index}-${item.placement.facility_template_id}`} className="rounded border border-border/50 bg-bg3/35 px-2 py-1">
              #{item.placement.build_order || item.index + 1} {item.template?.name ?? item.placement.facility_template_id ?? 'Unknown facility'}
              {item.placement.is_primary_port ? ' - primary port' : ''}
            </li>
          ))}
        </ul>
      </div>
      <NextAction summary={summary} bodyWarnings={warnings} hasUnassignedBody={!group.body} />
    </div>
  );
}

function PlacementDetail({ group, item, summary }: { group: BodyGroup; item: GroupedPlacement; summary: PlanSummary }) {
  const { placement, template } = item;
  const warnings = getPlacementWarnings(item, group.body);
  const bodyLabel = placementBodyLabel(group.body, item);
  const status = getPlacementStatus(item, group.body);

  return (
    <div className="mt-3 space-y-3">
      <DetailSection title="Selected placement">
        <p className="text-[11px] text-silver-dk">
          Placement info is read-only in Layout view; switch back to List view for edits.
        </p>
      </DetailSection>
      <DetailGrid>
        <DetailItem label="Facility" value={template?.name ?? placement.facility_template_id ?? 'Unknown facility'} tone={template ? 'default' : 'warn'} />
        <DetailItem label="Build order" value={String(placement.build_order || item.index + 1)} />
        <DetailItem label="Body" value={bodyLabel} tone={group.body ? 'default' : 'warn'} />
        <DetailItem label="Status" value={status} tone={status === 'planned' ? 'default' : 'warn'} />
        <DetailItem label="Primary port" value={placement.is_primary_port ? 'Yes' : 'No'} tone={placement.is_primary_port ? 'default' : 'warn'} />
        <DetailItem label="Location" value={template ? formatLocation(template.allowed_location) : 'Unknown'} tone={template ? 'default' : 'warn'} />
        <DetailItem label="Tier" value={template?.tier != null ? String(template.tier) : 'Unknown'} tone={template ? 'default' : 'warn'} />
        <DetailItem label="Pad" value={template?.pad_size ?? 'Unknown'} tone={template?.pad_size ? 'default' : 'warn'} />
        <DetailItem label="Economy" value={template?.economy ?? 'Unknown'} tone={template?.economy ? 'default' : 'warn'} />
        <DetailItem label="Role" value={template?.category ?? 'Unknown'} tone={template?.category ? 'default' : 'warn'} />
        <DetailItem label="CP visible" value={template ? `Y+${template.yellow_cp_generated}/${template.yellow_cp_cost} G+${template.green_cp_generated}/${template.green_cp_cost}` : 'Unknown'} tone={template ? 'default' : 'warn'} />
        <DetailItem label="Confidence" value={template?.confidence ?? 'missing'} tone={template?.confidence === 'estimated' || !template ? 'warn' : 'default'} />
      </DetailGrid>
      <WarningList warnings={warnings} emptyLabel="No placement warnings from current layout data." />
      <p className="rounded border border-border/50 bg-bg3/35 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        Use List view to edit this placement.
      </p>
      <NextAction summary={summary} bodyWarnings={warnings} hasUnassignedBody={!group.body} />
    </div>
  );
}

function NextAction({
  summary,
  bodyWarnings = [],
  hasUnassignedBody = false,
}: {
  summary: PlanSummary;
  bodyWarnings?: string[];
  hasUnassignedBody?: boolean;
}) {
  const action = getLayoutNextAction(summary, bodyWarnings, hasUnassignedBody);
  return (
    <div className="rounded border border-cyan/25 bg-cyan/5 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Next safe action</div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">{action}</p>
    </div>
  );
}

function getLayoutNextAction(summary: PlanSummary, warnings: string[], hasUnassignedBody: boolean): string {
  if (summary.totalPlacements === 0) return 'Copy a Suggested Build or add facilities in List view.';
  if (summary.previewStatus === 'running') return 'Preview is running. Wait for the result before relying on the layout.';
  if (summary.previewStatus === 'stale') return 'Build Plan changed. Run Preview again before relying on this result.';
  if (summary.unassignedPlacements > 0 || hasUnassignedBody) return 'Assign bodies in List view before relying on Preview.';
  if (summary.previewStatus === 'not run') return 'Run Preview when the Build Plan is ready.';
  if (summary.warningCount > 0 || warnings.length > 0) return 'Review warning chips, then adjust the plan in List view if needed.';
  return 'Layout looks ready for Preview review. Check Preview Result and later evidence if available.';
}

function DetailGrid({ children }: { children: ReactNode }) {
  return <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">{children}</dl>;
}

function DetailItem({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'warn';
}) {
  return (
    <div className={['rounded border px-2 py-1.5', tone === 'warn' ? 'border-gold/35 bg-gold/5' : 'border-border/55 bg-bg3/35'].join(' ')}>
      <dt className={['font-mono text-[9px] uppercase tracking-[0.14em]', tone === 'warn' ? 'text-gold' : 'text-silver-dk'].join(' ')}>
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-[11px] text-silver">{value}</dd>
    </div>
  );
}

function TagList({ body }: { body: SystemBody | null }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Body tags</div>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        {body ? bodyTags(body).map((tag) => <Chip key={tag}>{tag}</Chip>) : <Chip tone="warn">Needs assignment</Chip>}
      </div>
    </div>
  );
}

function WarningList({ warnings, emptyLabel }: { warnings: string[]; emptyLabel: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Warnings</div>
      {warnings.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
          {warnings.map((warning) => <Chip key={warning} tone="warn">{warning}</Chip>)}
        </div>
      ) : (
        <p className="mt-1 font-mono text-[11px] text-silver-dk">{emptyLabel}</p>
      )}
    </div>
  );
}

function placementBodyLabel(body: SystemBody | null, item: GroupedPlacement): string {
  if (body) return bodyDisplayName(body);
  if (item.hasUnknownBody) return `Unknown body ${item.bodyId}`;
  return 'Unassigned';
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">{title}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
