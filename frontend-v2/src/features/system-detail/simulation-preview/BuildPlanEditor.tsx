import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { Chip, IconButton } from './components';
import { formatLocation } from './utils/formatters';

export function BuildPlanEditor({
  placements,
  templates,
  bodies,
  onUpdate,
  onRemove,
  onMove,
}: {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  onUpdate: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
}) {
  return (
    <div className="space-y-2">
      {placements.map((placement, index) => {
        const template = templates.find((item) => item.id === placement.facility_template_id);
        return (
          <div key={`${placement.build_order}-${index}`} className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-full border border-orange/40 bg-orange/10 text-[11px] font-mono font-bold text-orange">
                {index + 1}
              </span>
              <select
                value={placement.facility_template_id}
                onChange={(e) => {
                  const nextTemplate = templates.find((item) => item.id === e.target.value);
                  onUpdate(index, {
                    facility_template_id: e.target.value,
                    is_primary_port: Boolean(placement.is_primary_port && nextTemplate?.is_port),
                  });
                }}
                className="min-w-0 flex-1"
              >
                {templates.map((item) => (
                  <option key={item.id} value={item.id}>
                    T{item.tier} - {item.name}{item.economy ? ` - ${item.economy}` : ''}
                  </option>
                ))}
              </select>
              <IconButton label="Move up" onClick={() => onMove(index, -1)} disabled={index === 0}>
                <ArrowUp size={14} />
              </IconButton>
              <IconButton label="Move down" onClick={() => onMove(index, 1)} disabled={index === placements.length - 1}>
                <ArrowDown size={14} />
              </IconButton>
              <IconButton label="Remove" onClick={() => onRemove(index)}>
                <Trash2 size={14} />
              </IconButton>
            </div>

            <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
              <select
                value={placement.local_body_id ?? ''}
                onChange={(e) => onUpdate(index, { local_body_id: e.target.value || null })}
                className="w-full"
              >
                <option value="">System-wide / undecided body</option>
                {bodies.map((body) => (
                  <option key={body.id ?? body.name} value={body.id ?? ''}>
                    {body.name ?? `Body ${body.id}`} {body.subtype ? `- ${body.subtype}` : ''}
                  </option>
                ))}
              </select>
              <label className={[
                'inline-flex items-center gap-2 rounded-chunk-sm border px-3 py-2 text-[11px] font-mono',
                template?.is_port ? 'border-border bg-bg3 text-silver' : 'border-border/50 bg-bg3/40 text-silver-dk',
              ].join(' ')}>
                <input
                  type="checkbox"
                  checked={Boolean(placement.is_primary_port)}
                  disabled={!template?.is_port}
                  onChange={(e) => onUpdate(index, { is_primary_port: e.target.checked })}
                  className="accent-orange"
                />
                Primary port
              </label>
            </div>

            {template && (
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-mono">
                <Chip>Tier {template.tier}</Chip>
                {template.economy && <Chip>{template.economy}</Chip>}
                <Chip>{formatLocation(template.allowed_location)}</Chip>
                <Chip>Y+{template.yellow_cp_generated} G+{template.green_cp_generated}</Chip>
                {template.confidence === 'estimated' && <Chip tone="warn">Estimated data</Chip>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
