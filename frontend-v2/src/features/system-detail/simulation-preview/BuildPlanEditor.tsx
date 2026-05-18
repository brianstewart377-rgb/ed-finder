import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';
import type { TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import { ArchitectObservationPanel } from './ArchitectObservationPanel';
import { Chip, IconButton } from './components';
import { PlannerGuidanceList } from './PlannerGuidanceList';
import { buildPlannerGuidanceForPlacement } from './plannerGuidanceUtils';
import { StructureReplacementComparison } from './StructureReplacementComparison';
import { StructurePickerTable } from './StructurePickerTable';
import { getStructurePickerWarnings, resolveBodyContext } from './structurePickerUtils';
import { formatLocation } from './utils/formatters';

export function BuildPlanEditor({
  placements,
  templates,
  bodies,
  onUpdate,
  onRemove,
  onMove,
  topologySelection,
}: {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  onUpdate: (index: number, patch: Partial<SimulateBuildPlacement>) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  topologySelection?: TopologySelection;
}) {
  const [pickerIndex, setPickerIndex] = useState<number | null>(null);
  const [pendingReplacement, setPendingReplacement] = useState<{ index: number; templateId: string } | null>(null);
  const rowRefs = useRef(new Map<number, HTMLDivElement>());
  const selectedBodyId = topologySelection?.type === 'body' ? topologySelection.bodyId : null;
  const selectedPlacementIndex = topologySelection?.type === 'placement' ? topologySelection.placementIndex : null;

  useEffect(() => {
    if (selectedPlacementIndex == null) return;
    const node = rowRefs.current.get(selectedPlacementIndex);
    if (!node) return;
    node.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    node.focus({ preventScroll: true });
  }, [selectedPlacementIndex]);

  return (
    <div className="space-y-2">
      {placements.map((placement, index) => {
        const template = templates.find((item) => item.id === placement.facility_template_id);
        const hasMissingTemplate = !template && Boolean(placement.facility_template_id);
        const pickerOpen = pickerIndex === index;
        const proposedTemplate = pendingReplacement?.index === index
          ? templates.find((item) => item.id === pendingReplacement.templateId)
          : undefined;
        const bodyContext = resolveBodyContext(bodies, placement.local_body_id ?? null);
        const selectedByTopology = selectedPlacementIndex === index;
        const relatedToSelectedBody = Boolean(selectedBodyId && String(placement.local_body_id ?? '') === selectedBodyId);
        const pickerBodyContextId = placement.local_body_id ?? selectedBodyId ?? null;
        const guidance = buildPlannerGuidanceForPlacement({
          placement,
          template,
          body: bodyContext.body,
          hasUnknownBody: bodyContext.status === 'unknown',
          warnings: template ? getStructurePickerWarnings(template, bodyContext) : [],
        });
        return (
          <div
            key={`${placement.build_order}-${index}`}
            ref={(node) => {
              if (node) rowRefs.current.set(index, node);
              else rowRefs.current.delete(index);
            }}
            tabIndex={selectedByTopology ? -1 : undefined}
            data-testid={`build-plan-placement-${index}`}
            data-topology-highlight={selectedByTopology ? 'placement' : relatedToSelectedBody ? 'body' : 'none'}
            className={[
              'rounded-chunk-lg border p-3 outline-none transition-[border-color,box-shadow,background-color]',
              selectedByTopology
                ? 'border-orange/70 bg-orange/10 shadow-[0_0_18px_rgba(255,125,32,0.16)]'
                : relatedToSelectedBody
                  ? 'border-cyan/55 bg-cyan/5'
                  : 'border-border/70 bg-bg2/70',
            ].join(' ')}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Placement</span>
              <div className="flex flex-wrap justify-end gap-1.5">
                {selectedByTopology && (
                  <span className="rounded border border-orange/50 bg-orange/10 px-2 py-0.5 font-mono text-[10px] text-orange">
                    Topology selected
                  </span>
                )}
                {relatedToSelectedBody && !selectedByTopology && (
                  <span className="rounded border border-cyan/45 bg-cyan/10 px-2 py-0.5 font-mono text-[10px] text-cyan">
                    Selected body
                  </span>
                )}
                <span className="rounded border border-border/60 bg-bg3/45 px-2 py-0.5 font-mono text-[10px] text-silver-dk">
                  List view editor
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-orange/40 bg-orange/10 text-[11px] font-mono font-bold text-orange">
                {index + 1}
              </span>
              <select
                value={placement.facility_template_id}
                onChange={(e) => {
                  if (e.target.value !== placement.facility_template_id) {
                    setPendingReplacement({ index, templateId: e.target.value });
                  }
                }}
                className="min-w-0 flex-1"
              >
                {hasMissingTemplate && (
                  <option value={placement.facility_template_id} disabled>
                    Missing template - {placement.facility_template_id}
                  </option>
                )}
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

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-[10px] text-silver-dk">Use List view to edit. Compare options with Browse structures.</p>
              <button
                type="button"
                onClick={() => setPickerIndex((current) => current === index ? null : index)}
                className={[
                  'rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition',
                  pickerOpen
                    ? 'border-cyan/60 bg-cyan/10 text-cyan'
                    : 'border-border/65 bg-bg3/45 text-silver-dk hover:border-cyan/60 hover:text-cyan',
                ].join(' ')}
                aria-expanded={pickerOpen}
                aria-controls={`structure-picker-panel-${index}`}
              >
                Browse structures
              </button>
            </div>

            {!template && (
              <p className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[11px] text-gold">
                Needs review: facility template missing ({placement.facility_template_id})
              </p>
            )}

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
              <div className={[
                'inline-flex items-center gap-2 rounded-chunk-sm border px-3 py-2 text-[11px] font-mono',
                placement.is_primary_port ? 'border-cyan/35 bg-cyan/10 text-cyan' : 'border-border/50 bg-bg3/40 text-silver-dk',
              ].join(' ')}>
                {placement.is_primary_port ? 'Primary port flag present' : 'No primary-port flag'}
              </div>
            </div>

            <div className="mt-2">
              <ArchitectObservationPanel showPrimaryPortPlacementReminder={Boolean(placement.is_primary_port)} />
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

            <div className="mt-2">
              <PlannerGuidanceList items={guidance} />
            </div>

            {pickerOpen && (
              <div id={`structure-picker-panel-${index}`}>
                <StructurePickerTable
                  templates={templates}
                  bodies={bodies}
                  selectedBodyId={pickerBodyContextId}
                  topologyBodyId={selectedBodyId}
                  selectedTemplateId={placement.facility_template_id}
                  proposedTemplateId={pendingReplacement?.index === index ? pendingReplacement.templateId : null}
                  onSelectTemplate={(templateId) => {
                    if (templateId !== placement.facility_template_id) {
                      setPendingReplacement({ index, templateId });
                    }
                  }}
                />
              </div>
            )}

            {proposedTemplate && (
              <StructureReplacementComparison
                placement={placement}
                currentTemplate={template}
                proposedTemplate={proposedTemplate}
                bodies={bodies}
                onCancel={() => setPendingReplacement(null)}
                onApply={() => {
                  onUpdate(index, { facility_template_id: proposedTemplate.id });
                  setPendingReplacement(null);
                  setPickerIndex(null);
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
