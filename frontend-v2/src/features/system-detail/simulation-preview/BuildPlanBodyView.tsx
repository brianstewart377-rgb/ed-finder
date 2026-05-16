import { ArrowDown, ArrowUp, AlertTriangle, Trash2 } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import { Chip, IconButton } from './components';
import { formatLocation } from './utils/formatters';

interface BuildPlanBodyViewProps {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
}

interface GroupedPlacement {
  placement: SimulateBuildPlacement;
  index: number;
  template?: FacilityTemplate;
}

interface BodyGroup {
  key: string;
  body: SystemBody | null;
  placements: GroupedPlacement[];
}

export function BuildPlanBodyView({
  placements,
  templates,
  bodies,
  onRemove,
  onMove,
}: BuildPlanBodyViewProps) {
  const groups = groupPlacementsByBody(placements, templates, bodies);

  return (
    <div className="space-y-3">
      <div className="rounded border border-cyan/30 bg-cyan/5 px-3 py-2 text-[11px] text-silver-dk">
        <span className="font-mono uppercase tracking-[0.14em] text-cyan">Body view</span>
        <span className="ml-2">Use List view for detailed editing. This view shows where the current Build Plan is placed.</span>
      </div>

      {groups.map((group) => (
        <section
          key={group.key}
          aria-label={group.body ? `Body group ${bodyDisplayName(group.body)}` : 'Unassigned / needs body'}
          className={[
            'rounded-chunk-lg border p-3',
            group.body ? 'border-border/70 bg-bg2/65' : 'border-gold/45 bg-gold/5',
          ].join(' ')}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h5 className={group.body ? 'text-sm font-bold text-silver' : 'text-sm font-bold text-gold'}>
                  {group.body ? bodyDisplayName(group.body) : 'Unassigned / needs body'}
                </h5>
                {group.body ? (
                  <Chip>{group.placements.length} placement{group.placements.length === 1 ? '' : 's'}</Chip>
                ) : (
                  <Chip tone="warn">{group.placements.length} placement{group.placements.length === 1 ? '' : 's'}</Chip>
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5 font-mono text-[10px]">
                {group.body ? (
                  bodyTags(group.body).map((tag) => <Chip key={tag}>{tag}</Chip>)
                ) : (
                  <Chip tone="warn">Needs assignment</Chip>
                )}
              </div>
            </div>
            {!group.body && (
              <div className="flex max-w-md items-start gap-2 rounded border border-gold/30 bg-bg2/40 px-2 py-1.5 text-[10px] text-gold">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                <span>Assign these placements to bodies before trusting Preview.</span>
              </div>
            )}
          </div>

          <div className="mt-3 grid gap-2">
            {group.placements.map(({ placement, index, template }) => (
              <article
                key={`${placement.build_order}-${index}-${placement.facility_template_id}`}
                className="rounded border border-border/65 bg-bg3/45 p-3"
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
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
                      {placement.is_primary_port && <Chip tone="good">Primary port</Chip>}
                      <Chip>{template ? formatLocation(template.allowed_location) : 'Unknown location'}</Chip>
                      {template?.tier != null && <Chip>Tier {template.tier}</Chip>}
                      {template?.pad_size && <Chip>Pad: {template.pad_size}</Chip>}
                      {template?.economy && <Chip>Economy: {template.economy}</Chip>}
                      {template?.category && <Chip>Role: {template.category}</Chip>}
                      {template && (
                        <Chip>
                          CP: Y+{template.yellow_cp_generated} G+{template.green_cp_generated}
                        </Chip>
                      )}
                      {template && (
                        <Chip>
                          Needs: Y{template.yellow_cp_cost} G{template.green_cp_cost}
                        </Chip>
                      )}
                      {template?.confidence === 'estimated' && <Chip tone="warn">Estimated data</Chip>}
                      {!template && <Chip tone="warn">Missing template</Chip>}
                      {!group.body && <Chip tone="warn">No body</Chip>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
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
                </div>
                <p className="mt-2 font-mono text-[10px] text-silver-dk">
                  Body assignment: {group.body ? bodyDisplayName(group.body) : 'Unassigned'}
                </p>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function groupPlacementsByBody(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
): BodyGroup[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const bodiesById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [String(body.id), body]),
  );
  const bodyOrder = bodies
    .filter((body) => body.id != null)
    .map((body) => String(body.id));
  const groupsByKey = new Map<string, BodyGroup>();

  const ensureGroup = (key: string, body: SystemBody | null): BodyGroup => {
    const existing = groupsByKey.get(key);
    if (existing) return existing;
    const next = { key, body, placements: [] };
    groupsByKey.set(key, next);
    return next;
  };

  placements.forEach((placement, index) => {
    const bodyId = placement.local_body_id != null ? String(placement.local_body_id) : '';
    const body = bodyId ? bodiesById.get(bodyId) ?? null : null;
    const key = body ? bodyId : 'unassigned';
    ensureGroup(key, body).placements.push({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
    });
  });

  return Array.from(groupsByKey.values()).sort((a, b) => {
    if (a.key === 'unassigned') return 1;
    if (b.key === 'unassigned') return -1;
    const aIndex = bodyOrder.indexOf(a.key);
    const bIndex = bodyOrder.indexOf(b.key);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex)
        - (bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex);
    }
    return a.key.localeCompare(b.key);
  });
}

export function bodyDisplayName(body: SystemBody): string {
  return body.name || (body.id != null ? `Body ${body.id}` : 'Unknown body');
}

export function bodyTags(body: SystemBody): string[] {
  const tags = [
    body.body_type,
    body.subtype,
    body.is_landable ? 'Landable' : null,
    body.is_water_world ? 'Water world' : null,
    body.is_earth_like ? 'Earth-like' : null,
    body.is_ammonia_world ? 'Ammonia world' : null,
    body.is_terraformable ? 'Terraformable' : null,
  ].filter((value): value is string => Boolean(value));

  const uniqueTags = Array.from(new Set(tags));
  return uniqueTags.length > 0 ? uniqueTags : ['Unknown body data'];
}
