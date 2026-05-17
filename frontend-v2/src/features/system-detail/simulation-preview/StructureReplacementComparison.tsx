import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { bodyDisplayName } from './buildPlanLayoutUtils';
import { Chip } from './components';
import { formatLocation } from './utils/formatters';
import {
  getStructurePickerValidityLabel,
  getStructurePickerWarnings,
  resolveBodyContext,
  type StructurePickerBodyContext,
} from './structurePickerUtils';

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
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        <ComparisonMetric label="Tier" value={template?.tier != null ? String(template.tier) : 'Unknown'} warn={!template} />
        <ComparisonMetric label="Allowed location" value={template ? formatLocation(template.allowed_location) : 'Unknown'} warn={!template} />
        <ComparisonMetric label="Pad size" value={template?.pad_size ?? 'Unknown'} warn={!template?.pad_size} />
        <ComparisonMetric label="Economy" value={template?.economy ?? 'Unknown'} warn={!template?.economy} />
        <ComparisonMetric label="Role" value={template?.category ?? 'Unknown'} warn={!template?.category} />
        <ComparisonMetric label="CP gives" value={template ? `Y+${template.yellow_cp_generated} G+${template.green_cp_generated}` : 'Unknown'} warn={!template} />
        <ComparisonMetric label="CP needs" value={template ? `Y${template.yellow_cp_cost} G${template.green_cp_cost}` : 'Unknown'} warn={!template} />
        <ComparisonMetric label="Confidence" value={template?.confidence ?? 'missing'} warn={!template || template.confidence === 'estimated'} />
      </dl>
      <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <Chip tone={validityTone}>{validity}</Chip>
        {warnings.map((warning) => <Chip key={`${title}-${warning}`} tone="warn">{warning}</Chip>)}
      </div>
    </div>
  );
}

function ComparisonMetric({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={['rounded border px-2 py-1.5', warn ? 'border-gold/35 bg-gold/5' : 'border-border/50 bg-bg3/35'].join(' ')}>
      <dt className={['font-mono text-[9px] uppercase tracking-[0.14em]', warn ? 'text-gold' : 'text-silver-dk'].join(' ')}>{label}</dt>
      <dd className="mt-0.5 break-words text-[11px] text-silver">{value}</dd>
    </div>
  );
}

function ArchitectPrimaryPortContext({ isPrimaryPort }: { isPrimaryPort: boolean }) {
  return (
    <div className="mt-3 rounded border border-cyan/25 bg-cyan/5 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Architect primary-port context</div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">
        Architect primary-port location should be checked before final station placement. Primary-port location is planning context, not a Build Point source.
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
