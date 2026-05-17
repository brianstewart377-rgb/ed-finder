import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { bodyDisplayName } from './buildPlanLayoutUtils';
import { Chip } from './components';
import {
  getStructurePickerValidityLabel,
  getStructurePickerWarnings,
  resolveBodyContext,
  type StructurePickerBodyContext,
} from './structurePickerUtils';
import {
  buildReplacementFieldDeltas,
  buildWarningDeltas,
  type ReplacementFieldDelta,
} from './structureReplacementDeltaUtils';

export function StructureReplacementComparison({
  placement,
  currentTemplate,
  proposedTemplate,
  bodies,
  onApply,
  onCancel,
}: {
  placement: SimulateBuildPlacement;
  currentTemplate?: FacilityTemplate;
  proposedTemplate: FacilityTemplate;
  bodies: SystemBody[];
  onApply: () => void;
  onCancel: () => void;
}) {
  const bodyContext = resolveBodyContext(bodies, placement.local_body_id ?? null);
  const currentWarnings = currentTemplate ? getStructurePickerWarnings(currentTemplate, bodyContext) : ['Needs review: current facility template missing'];
  const proposedWarnings = getStructurePickerWarnings(proposedTemplate, bodyContext);
  const currentValidity = currentTemplate ? getStructurePickerValidityLabel(currentTemplate, bodyContext) : 'Missing template';
  const proposedValidity = getStructurePickerValidityLabel(proposedTemplate, bodyContext);
  const fieldDeltas = buildReplacementFieldDeltas(currentTemplate, proposedTemplate);
  const warningDeltas = buildWarningDeltas(currentWarnings, proposedWarnings);

  return (
    <section
      aria-label="Review structure replacement"
      data-testid="structure-replacement-comparison"
      className="mt-3 rounded-chunk-lg border border-orange/45 bg-orange/5 p-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h6 className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Review replacement</h6>
          <p className="mt-1 text-[11px] leading-snug text-silver-dk">
            Compare the current and proposed structures before applying. This does not run Preview or change the plan until you apply it.
          </p>
        </div>
        <div className="rounded border border-border/60 bg-bg2/60 px-2 py-1 font-mono text-[10px] text-silver-dk">
          {bodyContextLabel(bodyContext)}
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <StructureColumn
          title="Current"
          template={currentTemplate}
          fallbackName={placement.facility_template_id}
          validity={currentValidity}
          warnings={currentWarnings}
        />
        <StructureColumn
          title="Proposed"
          template={proposedTemplate}
          validity={proposedValidity}
          warnings={proposedWarnings}
        />
      </div>

      <ReplacementDeltaTable deltas={fieldDeltas} />
      <WarningDeltaList deltas={warningDeltas} />

      <ArchitectPrimaryPortContext isPrimaryPort={Boolean(placement.is_primary_port)} />

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-border/70 bg-bg3/55 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-silver/60 hover:text-silver"
        >
          Cancel replacement
        </button>
        <button
          type="button"
          onClick={onApply}
          className="rounded border border-orange/60 bg-orange/15 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-orange hover:bg-orange/25"
        >
          Apply replacement
        </button>
      </div>
    </section>
  );
}

function StructureColumn({
  title,
  template,
  fallbackName,
  validity,
  warnings,
}: {
  title: string;
  template?: FacilityTemplate;
  fallbackName?: string;
  validity: string;
  warnings: string[];
}) {
  const validityTone: 'default' | 'good' | 'warn' = validity === 'Looks valid'
    ? 'good'
    : validity === 'Needs body' || validity === 'Unknown body'
      ? 'default'
      : 'warn';

  return (
    <div className="rounded border border-border/60 bg-bg2/70 p-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">{title}</div>
      <h6 className="mt-1 text-sm font-bold text-silver">{template?.name ?? fallbackName ?? 'Unknown structure'}</h6>
      <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <Chip tone={validityTone}>{validity}</Chip>
        {warnings.map((warning) => <Chip key={`${title}-${warning}`} tone="warn">{warning}</Chip>)}
      </div>
    </div>
  );
}

function ReplacementDeltaTable({ deltas }: { deltas: ReplacementFieldDelta[] }) {
  return (
    <div className="mt-3 overflow-x-auto rounded border border-border/60 bg-bg2/55" data-testid="structure-replacement-deltas">
      <table className="min-w-full border-collapse text-left font-mono text-[10px]">
        <thead>
          <tr className="border-b border-border/55 text-silver-dk">
            <th className="px-2 py-1 uppercase tracking-[0.14em]">Field</th>
            <th className="px-2 py-1 uppercase tracking-[0.14em]">Current</th>
            <th className="px-2 py-1 uppercase tracking-[0.14em]">Proposed</th>
          </tr>
        </thead>
        <tbody>
          {deltas.map((delta) => (
            <tr
              key={delta.label}
              data-testid={`structure-replacement-delta-${delta.label.toLowerCase().replace(/\s+/g, '-')}`}
              data-changed={delta.changed ? 'true' : 'false'}
              className={[
                'border-b border-border/35 align-top',
                delta.changed ? 'bg-orange/10' : 'bg-transparent',
              ].join(' ')}
            >
              <th className={['px-2 py-2 text-left uppercase tracking-[0.12em]', delta.changed ? 'text-orange' : 'text-silver-dk'].join(' ')}>
                {delta.label}
              </th>
              <DeltaValue value={delta.currentValue} warn={delta.warnCurrent} changed={delta.changed} />
              <DeltaValue value={delta.proposedValue} warn={delta.warnProposed} changed={delta.changed} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeltaValue({ value, warn, changed }: { value: string; warn: boolean; changed: boolean }) {
  return (
    <td className={['px-2 py-2', changed ? 'text-silver' : 'text-silver-dk'].join(' ')}>
      <span className={['break-words', warn ? 'text-gold' : ''].join(' ')}>
        {value}
      </span>
    </td>
  );
}

function WarningDeltaList({ deltas }: { deltas: ReturnType<typeof buildWarningDeltas> }) {
  return (
    <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="structure-replacement-warning-deltas">
      <WarningDeltaBucket title="Warnings added" warnings={deltas.added} tone="warn" emptyLabel="No new warnings" />
      <WarningDeltaBucket title="Warnings removed" warnings={deltas.removed} tone="good" emptyLabel="No warnings removed" />
      <WarningDeltaBucket title="Warnings unchanged" warnings={deltas.unchanged} tone="default" emptyLabel="No unchanged warnings" subdued />
    </div>
  );
}

function WarningDeltaBucket({
  title,
  warnings,
  tone,
  emptyLabel,
  subdued = false,
}: {
  title: string;
  warnings: string[];
  tone: 'default' | 'good' | 'warn';
  emptyLabel: string;
  subdued?: boolean;
}) {
  return (
    <div className="rounded border border-border/55 bg-bg2/55 p-2">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{title}</div>
      <div className={['mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]', subdued ? 'opacity-75' : ''].join(' ')}>
        {warnings.length > 0
          ? warnings.map((warning) => <Chip key={`${title}-${warning}`} tone={tone}>{warning}</Chip>)
          : <Chip>{emptyLabel}</Chip>}
      </div>
    </div>
  );
}

function ArchitectPrimaryPortContext({ isPrimaryPort }: { isPrimaryPort: boolean }) {
  return (
    <div className="mt-3 rounded border border-cyan/25 bg-cyan/5 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Architect primary-port context</div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">
        Check the primary-port location in-game through System Map and Architect Mode before final major station placement. Primary-port location is placement guidance, not a Build Point source.
      </p>
      {isPrimaryPort && (
        <p className="mt-1 text-[11px] leading-snug text-silver-dk">
          If the flagged slot is inconvenient, consider placing an outpost there and using a better body/orbit for the main station.
        </p>
      )}
    </div>
  );
}

function bodyContextLabel(context: StructurePickerBodyContext): string {
  if (context.status === 'selected' && context.body) return `Body context: ${bodyDisplayName(context.body)}`;
  if (context.status === 'unknown') return `Body context: unknown body ${context.bodyId}`;
  return 'Body context: no body selected';
}
