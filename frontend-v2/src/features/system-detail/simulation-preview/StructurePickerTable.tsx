import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import type { FacilityTemplate, SystemBody } from '@/types/api';
import { bodyDisplayName } from './buildPlanLayoutUtils';
import { Chip } from './components';
import { formatLocation } from './utils/formatters';
import {
  getStructurePickerValidityLabel,
  getStructurePickerWarnings,
  locationMatchesFilter,
  resolveBodyContext,
  type StructurePickerLocationFilter,
} from './structurePickerUtils';

export function StructurePickerTable({
  templates,
  bodies,
  selectedBodyId,
  selectedTemplateId,
  onSelectTemplate,
}: {
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  selectedBodyId?: string | null;
  selectedTemplateId?: string | null;
  onSelectTemplate: (templateId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [locationFilter, setLocationFilter] = useState<StructurePickerLocationFilter>('all');
  const bodyContext = useMemo(
    () => resolveBodyContext(bodies, selectedBodyId),
    [bodies, selectedBodyId],
  );
  const filteredTemplates = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return templates.filter((template) => {
      if (!locationMatchesFilter(template, locationFilter)) return false;
      if (!normalizedQuery) return true;
      return `${template.name} ${template.category} ${template.economy ?? ''}`.toLowerCase().includes(normalizedQuery);
    });
  }, [templates, query, locationFilter]);

  return (
    <section
      aria-label="Structure picker"
      data-testid="structure-picker"
      className="mt-3 rounded-chunk-lg border border-border/65 bg-bg3/35 p-3"
    >
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h6 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Compare structures</h6>
          <p className="mt-1 text-[11px] text-silver-dk">Uses current facility catalogue. Validity hints are planning checks; run Preview for full prediction.</p>
        </div>
        <div className="rounded border border-border/60 bg-bg2/60 px-2 py-1 font-mono text-[10px] text-silver-dk">
          {bodyContext.status === 'selected'
            ? `Evaluating against: ${bodyDisplayName(bodyContext.body as SystemBody)}`
            : bodyContext.status === 'unknown'
              ? `Unknown body: ${bodyContext.bodyId}`
              : 'No body selected yet'}
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
        <label className="relative">
          <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-silver-dk" />
          <input
            aria-label="Search structures"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search structures"
            className="w-full rounded border border-border/70 bg-bg2 px-8 py-2 font-mono text-xs text-silver outline-none focus:border-cyan/60"
          />
        </label>
        <div className="inline-flex rounded border border-border/70 bg-bg2/60 p-1" role="group" aria-label="Location filter">
          {([
            ['all', 'All'],
            ['orbital', 'Orbital'],
            ['surface', 'Surface'],
            ['both', 'Both'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setLocationFilter(value)}
              aria-pressed={locationFilter === value}
              className={[
                'rounded px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em]',
                locationFilter === value ? 'bg-orange/15 text-orange' : 'text-silver-dk hover:text-silver',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {templates.length === 0 ? (
        <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 font-mono text-[11px] text-gold">
          No structures available yet.
        </p>
      ) : filteredTemplates.length === 0 ? (
        <p className="mt-3 rounded border border-border/60 bg-bg2/45 px-3 py-2 font-mono text-[11px] text-silver-dk">
          No structures match the current filters.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full border-collapse text-left font-mono text-[10px]">
            <thead>
              <tr className="border-b border-border/60 text-silver-dk">
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Structure</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Location</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Tier</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Pad</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Economy</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Role</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">CP gives</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">CP needs</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Confidence</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Validity</th>
                <th className="px-2 py-1 uppercase tracking-[0.14em]">Select</th>
              </tr>
            </thead>
            <tbody>
              {filteredTemplates.map((template) => {
                const warnings = getStructurePickerWarnings(template, bodyContext);
                const validity = getStructurePickerValidityLabel(template, bodyContext);
                const isSelected = selectedTemplateId === template.id;
                const validityTone = validity === 'Looks valid' ? 'good' : validity === 'Needs body' || validity === 'Unknown body' ? 'default' : 'warn';
                return (
                  <tr
                    key={template.id}
                    data-testid={`structure-picker-row-${template.id}`}
                    className={[
                      'border-b border-border/35 align-top',
                      isSelected ? 'bg-cyan/10' : 'bg-transparent',
                    ].join(' ')}
                  >
                    <td className="px-2 py-2 text-silver">
                      <div className="font-semibold">{template.name}</div>
                      {template.is_port ? (
                        <div className="mt-1"><Chip>Port</Chip></div>
                      ) : null}
                    </td>
                    <td className="px-2 py-2 text-silver-dk">{formatLocation(template.allowed_location)}</td>
                    <td className="px-2 py-2 text-silver-dk">{template.tier}</td>
                    <td className="px-2 py-2 text-silver-dk">{template.pad_size ?? 'Unknown'}</td>
                    <td className="px-2 py-2 text-silver-dk">{template.economy ?? 'Unknown'}</td>
                    <td className="px-2 py-2 text-silver-dk">{template.category}</td>
                    <td className="px-2 py-2 text-silver-dk">Y+{template.yellow_cp_generated} G+{template.green_cp_generated}</td>
                    <td className="px-2 py-2 text-silver-dk">Y{template.yellow_cp_cost} G{template.green_cp_cost}</td>
                    <td className="px-2 py-2 text-silver-dk">{template.confidence ?? 'missing'}</td>
                    <td className="px-2 py-2">
                      <div className="flex max-w-[14rem] flex-wrap gap-1">
                        <Chip tone={validityTone}>{validity}</Chip>
                        {warnings.map((warning) => (
                          <Chip key={`${template.id}-${warning}`} tone="warn">{warning}</Chip>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        aria-label={`Select structure ${template.name}`}
                        onClick={() => onSelectTemplate(template.id)}
                        className={[
                          'rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition',
                          isSelected
                            ? 'border-cyan/65 bg-cyan/15 text-cyan'
                            : 'border-border/60 bg-bg2 text-silver-dk hover:border-cyan/55 hover:text-cyan',
                        ].join(' ')}
                      >
                        {isSelected ? 'Selected' : 'Select structure'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
