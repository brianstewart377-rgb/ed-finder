import { Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { Chip } from './components';
import {
  filterStructureTemplates,
  formatCpGives,
  formatCpNeeds,
  formatTemplateConfidence,
  formatTemplateEconomy,
  formatTemplateLocation,
  formatTemplatePad,
  formatTemplatePortSupport,
  formatTemplateRole,
  formatTemplateTier,
  getStructurePickerBodyContext,
  getStructurePickerWarnings,
  type StructureLocationFilter,
} from './structurePickerUtils';

interface StructurePickerTableProps {
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  selectedBodyId?: string | number | null;
  selectedTemplateId?: string | null;
  placement?: SimulateBuildPlacement;
  onSelectTemplate: (templateId: string) => void;
}

const FILTERS: Array<{ id: StructureLocationFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'orbital', label: 'Orbital' },
  { id: 'surface', label: 'Surface' },
  { id: 'both', label: 'Both' },
];

export function StructurePickerTable({
  templates,
  bodies,
  selectedBodyId,
  selectedTemplateId,
  onSelectTemplate,
}: StructurePickerTableProps) {
  const [filter, setFilter] = useState<StructureLocationFilter>('all');
  const [query, setQuery] = useState('');
  const bodyContext = getStructurePickerBodyContext(bodies, selectedBodyId);
  const filteredTemplates = useMemo(
    () => filterStructureTemplates(templates, filter, query),
    [templates, filter, query],
  );

  return (
    <section
      aria-label="Structure picker"
      className="rounded-chunk-lg border border-cyan/30 bg-bg2/85 p-3 shadow-brand-glow"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Compare structures</div>
          <p className="mt-1 max-w-3xl text-[11px] leading-snug text-silver-dk">
            Uses current facility catalogue. Validity hints are planning checks; run Preview for full prediction.
          </p>
        </div>
        <BodyContextBadge context={bodyContext} />
      </div>

      <div className="mt-3 grid gap-2 lg:grid-cols-[minmax(14rem,1fr)_auto]">
        <label className="space-y-1">
          <span className="block font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">
            Search structures
          </span>
          <span className="flex items-center gap-2 rounded border border-border bg-bg3 px-2 py-1.5">
            <Search size={14} className="text-cyan" />
            <input
              aria-label="Search structures"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by structure, economy, role, or id"
              className="min-w-0 flex-1 border-0 bg-transparent p-0 text-xs text-silver outline-none placeholder:text-silver-dk"
            />
          </span>
        </label>
        <div>
          <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Location filter</div>
          <div className="inline-flex rounded-chunk-sm border border-border/70 bg-bg3/40 p-1">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={[
                  'rounded px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors',
                  filter === item.id ? 'bg-orange/15 text-orange' : 'text-silver-dk hover:bg-bg2 hover:text-silver',
                ].join(' ')}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {templates.length === 0 ? (
        <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-3 font-mono text-[11px] text-gold">
          No structures available yet.
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="mt-3 rounded border border-border/60 bg-bg3/35 px-3 py-3 font-mono text-[11px] text-silver-dk">
          No structures match the current filters.
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto rounded border border-border/60">
          <table className="min-w-[58rem] w-full border-collapse text-left text-[11px]">
            <thead className="bg-bg3/70 font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">
              <tr>
                <th className="px-2 py-2">Select</th>
                <th className="px-2 py-2">Structure</th>
                <th className="px-2 py-2">Location</th>
                <th className="px-2 py-2">Tier</th>
                <th className="px-2 py-2">Pad</th>
                <th className="px-2 py-2">Economy</th>
                <th className="px-2 py-2">Role</th>
                <th className="px-2 py-2">Type</th>
                <th className="px-2 py-2">CP gives</th>
                <th className="px-2 py-2">CP needs</th>
                <th className="px-2 py-2">Confidence</th>
                <th className="px-2 py-2">Validity / review hint</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {filteredTemplates.map((template) => (
                <StructurePickerRow
                  key={template.id}
                  template={template}
                  selected={template.id === selectedTemplateId}
                  bodyContext={bodyContext}
                  onSelectTemplate={onSelectTemplate}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BodyContextBadge({ context }: { context: ReturnType<typeof getStructurePickerBodyContext> }) {
  const tone = context.status === 'known' ? 'default' : 'warn';
  return (
    <div className="rounded border border-border/60 bg-bg3/45 px-3 py-2 font-mono text-[10px]">
      <div className={context.status === 'known' ? 'uppercase tracking-[0.14em] text-cyan' : 'uppercase tracking-[0.14em] text-gold'}>
        Selected body context
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {context.status === 'known' ? (
          <Chip tone={tone}>Evaluating against: {context.label}</Chip>
        ) : (
          <Chip tone={tone}>{context.label}</Chip>
        )}
      </div>
    </div>
  );
}

function StructurePickerRow({
  template,
  selected,
  bodyContext,
  onSelectTemplate,
}: {
  template: FacilityTemplate;
  selected: boolean;
  bodyContext: ReturnType<typeof getStructurePickerBodyContext>;
  onSelectTemplate: (templateId: string) => void;
}) {
  const warnings = getStructurePickerWarnings(template, bodyContext);
  const confidence = formatTemplateConfidence(template);

  return (
    <tr className={selected ? 'bg-orange/10' : 'bg-bg2/45'}>
      <td className="px-2 py-2 align-top">
        <button
          type="button"
          onClick={() => onSelectTemplate(template.id)}
          className={[
            'rounded border px-2 py-1 font-mono text-[10px] transition-colors',
            selected
              ? 'border-orange/60 bg-orange/15 text-orange'
              : 'border-border bg-bg3 text-silver hover:border-cyan/60 hover:text-cyan',
          ].join(' ')}
        >
          {selected ? 'Selected' : 'Select structure'}
        </button>
      </td>
      <td className="px-2 py-2 align-top">
        <div className="font-semibold text-silver">{template.name || template.id}</div>
        <div className="mt-0.5 font-mono text-[10px] text-silver-dk">{template.id}</div>
      </td>
      <td className="px-2 py-2 align-top"><Chip>{formatTemplateLocation(template)}</Chip></td>
      <td className="px-2 py-2 align-top">{formatTemplateTier(template)}</td>
      <td className="px-2 py-2 align-top">{formatTemplatePad(template)}</td>
      <td className="px-2 py-2 align-top">{formatTemplateEconomy(template)}</td>
      <td className="px-2 py-2 align-top">{formatTemplateRole(template)}</td>
      <td className="px-2 py-2 align-top">{formatTemplatePortSupport(template)}</td>
      <td className="px-2 py-2 align-top font-mono">{formatCpGives(template)}</td>
      <td className="px-2 py-2 align-top font-mono">{formatCpNeeds(template)}</td>
      <td className="px-2 py-2 align-top">
        <Chip tone={confidence === 'estimated' || confidence === 'missing' ? 'warn' : 'default'}>
          {confidence}
        </Chip>
      </td>
      <td className="px-2 py-2 align-top">
        <div className="flex max-w-md flex-wrap gap-1.5 font-mono text-[10px]">
          {warnings.length === 0 ? (
            <Chip tone="good">Looks valid</Chip>
          ) : (
            warnings.map((warning) => <Chip key={warning} tone="warn">{warning}</Chip>)
          )}
        </div>
      </td>
    </tr>
  );
}
