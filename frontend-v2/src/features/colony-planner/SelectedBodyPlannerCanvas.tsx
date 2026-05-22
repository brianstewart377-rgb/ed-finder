import { PanelTopOpen, Sparkles, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { BodySlotPrediction, FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import {
  bodyDisplayName,
  bodyTags,
  compactBodyDisplayName,
  getBodyGroupWarnings,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import type { SimulationWorkspaceMode } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';
import { BodySlotPlanner, type BodyPlannerLane } from './BodySlotPlanner';
import type { TopologyPlanSnapshot, TopologySelection } from './ColonyTopologyRail';

interface PlacementViewItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
  bodyId: string;
  hasUnknownBody: boolean;
}

interface ProjectedPlacementViewItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
}

export function SelectedBodyPlannerCanvas({
  system,
  body,
  snapshot,
  selection,
  selectedPlacementIndex,
  selectedProjectedPlacementIndex,
  templatesLoading,
  templatesErrorMessage,
  onAddStructure,
  onOpenAdvanced,
  onReviewStructures,
  onClose,
  onSelectBody,
  onSelectPlacement,
  onSelectProjectedPlacement,
}: {
  system: SystemDetail;
  body: SystemBody | null;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  selectedPlacementIndex: number | null;
  selectedProjectedPlacementIndex: number | null;
  templatesLoading: boolean;
  templatesErrorMessage: string | null;
  onAddStructure: (bodyId: string, lane: BodyPlannerLane, templateId: string) => void;
  onOpenAdvanced: (mode?: SimulationWorkspaceMode) => void;
  onReviewStructures: (bodyId: string) => void;
  onClose: () => void;
  onSelectBody: (bodyId: string) => void;
  onSelectPlacement: (placementIndex: number) => void;
  onSelectProjectedPlacement: (placementIndex: number) => void;
}) {
  const [pickerContext, setPickerContext] = useState<{ bodyId: string; lane: BodyPlannerLane } | null>(null);

  useEffect(() => {
    if (!body?.id || !pickerContext) return;
    if (!sameBodyId(body.id, pickerContext.bodyId)) {
      setPickerContext(null);
    }
  }, [body?.id, pickerContext]);

  const pickerBody = pickerContext && body?.id != null && sameBodyId(body.id, pickerContext.bodyId)
    ? body
    : null;

  const pickTemplateForBody = (templateId: string) => {
    if (!pickerContext) return;
    onAddStructure(pickerContext.bodyId, pickerContext.lane, templateId);
    setPickerContext(null);
  };

  if (!body || body.id == null) {
    return (
      <section data-testid="selected-body-planner-canvas" data-readability="stage17k" className="text-sm leading-relaxed">
        <SystemOverviewPlannerCanvas
          system={system}
          snapshot={snapshot}
          onSelectBody={onSelectBody}
          onOpenAdvanced={onOpenAdvanced}
        />
        {selection.type === 'group' && (
          <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-gold">
            {selection.groupKey === 'unknown' ? 'Unknown placements need a matching body.' : 'Unassigned placements need a body.'}
          </p>
        )}
      </section>
    );
  }

  const bodyId = bodyIdKey(body.id);
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const placements: PlacementViewItem[] = snapshot.placements
    .map((placement, index) => ({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
      bodyId: bodyIdKey(placement.local_body_id),
      hasUnknownBody: false,
    }))
    .filter((item) => item.bodyId === bodyId);
  const warnings = getBodyGroupWarnings({ key: bodyId, body, placements });
  const projectedPlacements: ProjectedPlacementViewItem[] = (snapshot.projection?.placements ?? [])
    .map((placement, index) => ({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
    }))
    .filter((item) => sameBodyId(item.placement.local_body_id, bodyId));
  const slotPrediction = snapshot.slotPredictions?.predictions?.find((item) => sameBodyId(item.body_id, bodyId)) ?? null;

  return (
    <div data-testid="selected-body-planner-canvas" data-readability="stage17k" className="text-sm leading-relaxed">
      <div className="mb-2 flex justify-end">
        <button
          type="button"
          data-testid="selected-body-close"
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          <X size={12} />
          Close
        </button>
      </div>
      <BodySlotPlanner
        body={body}
        slotPrediction={slotPrediction}
        placements={placements}
        projectedPlacements={projectedPlacements}
        selectedPlacementIndex={selectedPlacementIndex}
        selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
        hasTemplates={snapshot.templates.length > 0}
        onSelectPlacement={onSelectPlacement}
        onSelectProjectedPlacement={onSelectProjectedPlacement}
        onAddLaneStructure={(lane) => setPickerContext({ bodyId, lane })}
      />

      {warnings.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5 rounded border border-gold/30 bg-gold/6 px-3 py-2">
          {warnings.slice(0, 3).map((warning) => <BodyFact key={warning} label={warning} tone="gold" />)}
        </div>
      )}

      {templatesErrorMessage && (
        <div className="mb-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-sm leading-relaxed text-gold">
          {templatesErrorMessage}
        </div>
      )}

      {templatesLoading && (
        <div className="mb-3 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-sm leading-relaxed text-silver-dk">
          Facility catalogue loading.
        </div>
      )}

      <div className="mb-3 flex justify-end">
        <button
          type="button"
          onClick={() => onReviewStructures(bodyId)}
          className="rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-cyan hover:bg-cyan/20"
        >
          Review structures
        </button>
      </div>

      <BodyStructurePickerDrawer
        body={pickerBody}
        lane={pickerContext?.lane ?? null}
        templates={snapshot.templates}
        onClose={() => setPickerContext(null)}
        onPickTemplate={pickTemplateForBody}
      />
    </div>
  );
}

interface SystemOverviewItem {
  body: SystemBody;
  bodyId: string;
  compactName: string;
  kind: string;
  icon: string;
  tags: string[];
  orbitalCapacity: number | null;
  surfaceCapacity: number | null;
  plannedOrbital: number;
  plannedSurface: number;
  projectedOrbital: number;
  projectedSurface: number;
  score: number;
}

function SystemOverviewPlannerCanvas({
  system,
  snapshot,
  onSelectBody,
  onOpenAdvanced,
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  onSelectBody: (bodyId: string) => void;
  onOpenAdvanced: (mode?: SimulationWorkspaceMode) => void;
}) {
  const overviewItems = buildSystemOverviewItems(system, snapshot);
  const featuredItems = overviewItems.slice(0, 18);
  const bodies = system.bodies ?? [];
  const landableCount = bodies.filter((candidate) => candidate.is_landable === true).length;
  const knownOrbitalCapacity = sumKnownCapacity(overviewItems, 'orbital');
  const knownSurfaceCapacity = sumKnownCapacity(overviewItems, 'surface');
  const unknownSurfaceCount = overviewItems.filter((item) => item.surfaceCapacity == null).length;
  const plannedCount = snapshot.placements.length;
  const projectedCount = snapshot.projection?.placements.length ?? 0;

  return (
    <section
      data-testid="system-overview-planner-canvas"
      className="mb-3 overflow-hidden rounded-chunk-lg border border-cyan/30 bg-cyan/5 px-4 py-4 text-sm leading-relaxed"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Whole-system build map</div>
          <h3 className="mt-1 text-base font-semibold text-silver">Select a body from the system map</h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-silver-dk">
            Bodies with known capacity, planned structures, projected structures, and landable build targets are surfaced first.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <OverviewStat label="Bodies" value={String(bodies.length)} />
          <OverviewStat label="Landable" value={String(landableCount)} tone="green" />
          <OverviewStat label="Orbit cap" value={knownOrbitalCapacity > 0 ? String(knownOrbitalCapacity) : 'unknown'} tone="cyan" />
          <OverviewStat label="Surface cap" value={knownSurfaceCapacity > 0 ? String(knownSurfaceCapacity) : 'unknown'} tone="gold" />
        </div>
      </div>

      <div className="mt-4 rounded border border-border/60 bg-bg3/30 p-3" data-testid="system-overview-map">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-silver-dk">Priority bodies</div>
          <div className="flex flex-wrap gap-1.5">
            <MiniLegend label={`${plannedCount} planned`} tone={plannedCount > 0 ? 'orange' : 'silver'} />
            {projectedCount > 0 && <MiniLegend label={`${projectedCount} projected`} tone="cyan" />}
            {unknownSurfaceCount > 0 && <MiniLegend label={`${unknownSurfaceCount} surface unknown`} tone="gold" />}
          </div>
        </div>

        {featuredItems.length === 0 ? (
          <div className="rounded border border-border/55 bg-bg2/45 px-3 py-3 text-sm text-silver-dk">
            No body layout is available for this system yet.
          </div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
            {featuredItems.map((item) => (
              <SystemOverviewBodyButton
                key={item.bodyId}
                item={item}
                onSelect={() => onSelectBody(item.bodyId)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <BodyStartAction label="Select a body" detail="Use the priority map or the whole-system list." />
        <button
          type="button"
          onClick={() => onOpenAdvanced('suggested-builds')}
          className="rounded border border-cyan/35 bg-cyan/8 px-3 py-2 text-left hover:border-cyan/65 hover:bg-cyan/12"
        >
          <span className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-cyan">
            <Sparkles size={13} />
            Generate Suggested Build
          </span>
          <span className="mt-1 block text-sm leading-relaxed text-silver-dk">Open Suggested Builds without loading or previewing.</span>
        </button>
        <button
          type="button"
          onClick={() => onOpenAdvanced('build-plan')}
          className="rounded border border-orange/35 bg-orange/8 px-3 py-2 text-left hover:border-orange/65 hover:bg-orange/12"
        >
          <span className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-orange">
            <PanelTopOpen size={13} />
            Open Advanced Planner
          </span>
          <span className="mt-1 block text-sm leading-relaxed text-silver-dk">Preview, Suggested Builds, and list editor stay explicit.</span>
        </button>
      </div>
    </section>
  );
}

function SystemOverviewBodyButton({
  item,
  onSelect,
}: {
  item: SystemOverviewItem;
  onSelect: () => void;
}) {
  const plannedTotal = item.plannedOrbital + item.plannedSurface;
  const projectedTotal = item.projectedOrbital + item.projectedSurface;

  return (
    <button
      type="button"
      data-testid={`system-overview-body-${item.bodyId}`}
      onClick={onSelect}
      className="min-w-0 rounded border border-border/55 bg-bg2/55 px-3 py-2 text-left transition-colors hover:border-orange/55 hover:bg-orange/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70"
      title={bodyDisplayName(item.body)}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded border border-cyan/35 bg-cyan/8 text-[11px] font-bold text-cyan">
          {item.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11px] font-bold text-silver">{item.compactName}</div>
          <div className="mt-0.5 truncate text-[10px] text-silver-dk">{item.kind}</div>
        </div>
        {plannedTotal > 0 && <MiniLegend label={String(plannedTotal)} tone="orange" />}
        {projectedTotal > 0 && <MiniLegend label={`+${projectedTotal}`} tone="cyan" />}
      </div>
      <div className="mt-2 grid gap-1.5">
        <OverviewLane
          label="Orbit"
          capacity={item.orbitalCapacity}
          planned={item.plannedOrbital}
          projected={item.projectedOrbital}
        />
        <OverviewLane
          label="Surface"
          capacity={item.surfaceCapacity}
          planned={item.plannedSurface}
          projected={item.projectedSurface}
        />
      </div>
      {item.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {item.tags.slice(0, 3).map((tag) => <BodyFact key={tag} label={tag} />)}
        </div>
      )}
    </button>
  );
}

function OverviewLane({
  label,
  capacity,
  planned,
  projected,
}: {
  label: string;
  capacity: number | null;
  planned: number;
  projected: number;
}) {
  const used = planned + projected;
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 shrink-0 text-[9px] uppercase tracking-[0.12em] text-silver-dk">{label}</span>
      <OverviewSlotCells capacity={capacity} planned={planned} projected={projected} />
      {used > 0 && (
        <span className="shrink-0 text-[9px] text-silver-dk">
          {capacity == null ? `${used}` : `${used}/${capacity}`}
        </span>
      )}
    </div>
  );
}

function OverviewSlotCells({
  capacity,
  planned,
  projected,
}: {
  capacity: number | null;
  planned: number;
  projected: number;
}) {
  if (capacity == null) {
    return <span className="rounded border border-gold/35 bg-gold/10 px-1 text-[9px] text-gold">[?]</span>;
  }
  if (capacity <= 0) {
    return <span className="rounded border border-border/50 bg-bg3/45 px-1 text-[9px] text-silver-dk">0</span>;
  }
  const visibleCells = Math.min(capacity, 7);
  const overflow = Math.max(0, planned + projected - capacity);
  return (
    <span className="flex min-w-0 flex-wrap gap-1">
      {Array.from({ length: visibleCells }, (_unused, index) => {
        const filled = index < planned;
        const ghost = !filled && index < planned + projected;
        return (
          <span
            key={index}
            className={[
              'h-3 w-3 rounded-sm border',
              filled
                ? 'border-orange/60 bg-orange/60'
                : ghost
                  ? 'border-cyan/50 bg-cyan/35'
                  : 'border-border/60 bg-bg2/60',
            ].join(' ')}
          />
        );
      })}
      {capacity > visibleCells && <span className="text-[9px] text-silver-dk">+{capacity - visibleCells}</span>}
      {overflow > 0 && <span className="text-[9px] text-gold">+{overflow}</span>}
    </span>
  );
}

function OverviewStat({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: string;
  tone?: 'silver' | 'cyan' | 'green' | 'gold';
}) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1 text-right">
      <div className="text-[9px] uppercase tracking-[0.12em] text-silver-dk">{label}</div>
      <div
        className={[
          'mt-0.5 truncate text-[11px] font-bold',
          tone === 'cyan'
            ? 'text-cyan'
            : tone === 'green'
              ? 'text-green'
              : tone === 'gold'
                ? 'text-gold'
                : 'text-silver',
        ].join(' ')}
      >
        {value}
      </div>
    </div>
  );
}

function MiniLegend({
  label,
  tone,
}: {
  label: string;
  tone: 'silver' | 'orange' | 'cyan' | 'gold';
}) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'cyan'
            ? 'border-cyan/35 bg-cyan/10 text-cyan'
            : tone === 'gold'
              ? 'border-gold/35 bg-gold/10 text-gold'
              : 'border-border/55 bg-bg3/45 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}

function buildSystemOverviewItems(system: SystemDetail, snapshot: TopologyPlanSnapshot): SystemOverviewItem[] {
  const bodies = system.bodies ?? [];
  const predictionsByBodyId = new Map(
    (snapshot.slotPredictions?.predictions ?? []).map((prediction) => [bodyIdKey(prediction.body_id), prediction]),
  );
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const bodiesById = new Map(bodies.filter((body) => body.id != null).map((body) => [bodyIdKey(body.id), body]));
  const plannedCounts = countPlacementsByBody(snapshot.placements, templatesById, bodiesById);
  const projectedCounts = countPlacementsByBody(snapshot.projection?.placements ?? [], templatesById, bodiesById);

  return bodies
    .filter((body) => body.id != null)
    .map((body) => {
      const bodyId = bodyIdKey(body.id);
      const slotPrediction = predictionsByBodyId.get(bodyId) ?? null;
      const planned = plannedCounts.get(bodyId) ?? emptyLaneCounts();
      const projected = projectedCounts.get(bodyId) ?? emptyLaneCounts();
      const orbitalCapacity = readOverviewSlotCount(slotPrediction, 'orbital');
      const surfaceCapacity = readOverviewSlotCount(slotPrediction, 'surface');
      const tags = bodyTags(body);
      const score = overviewBodyScore(body, planned, projected, orbitalCapacity, surfaceCapacity, tags);
      return {
        body,
        bodyId,
        compactName: compactBodyDisplayName(body, system.name),
        kind: overviewBodyKind(body),
        icon: overviewBodyIcon(body),
        tags,
        orbitalCapacity,
        surfaceCapacity,
        plannedOrbital: planned.orbital,
        plannedSurface: planned.surface,
        projectedOrbital: projected.orbital,
        projectedSurface: projected.surface,
        score,
      };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return bodySortDistance(a.body) - bodySortDistance(b.body);
    });
}

interface LaneCounts {
  orbital: number;
  surface: number;
}

function countPlacementsByBody(
  placements: SimulateBuildPlacement[],
  templatesById: Map<string, FacilityTemplate>,
  bodiesById: Map<string, SystemBody>,
) {
  const counts = new Map<string, LaneCounts>();
  for (const placement of placements) {
    if (placement.local_body_id == null) continue;
    const bodyId = bodyIdKey(placement.local_body_id);
    const current = counts.get(bodyId) ?? emptyLaneCounts();
    const lane = overviewLaneForTemplate(templatesById.get(placement.facility_template_id), bodiesById.get(bodyId));
    current[lane] += 1;
    counts.set(bodyId, current);
  }
  return counts;
}

function emptyLaneCounts(): LaneCounts {
  return { orbital: 0, surface: 0 };
}

function overviewLaneForTemplate(template: FacilityTemplate | undefined, body: SystemBody | undefined): BodyPlannerLane {
  if (!template) return fallbackOverviewLane(body);
  const location = templateLocationKind(template);
  if (location === 'orbital') return 'orbital';
  if (location === 'surface') return 'surface';
  if (location === 'both') {
    if (template.is_port) return 'orbital';
    return body?.is_landable === true && body.is_water_world !== true ? 'surface' : 'orbital';
  }
  return fallbackOverviewLane(body);
}

function fallbackOverviewLane(body: SystemBody | undefined): BodyPlannerLane {
  return body?.is_landable === true && body.is_water_world !== true ? 'surface' : 'orbital';
}

function readOverviewSlotCount(
  prediction: BodySlotPrediction | null,
  lane: 'orbital' | 'surface',
): number | null {
  const raw = lane === 'orbital'
    ? prediction?.predicted_orbital_slots
    : prediction?.predicted_ground_slots;
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < 0) {
    return null;
  }
  return Math.floor(raw);
}

function overviewBodyScore(
  body: SystemBody,
  planned: LaneCounts,
  projected: LaneCounts,
  orbitalCapacity: number | null,
  surfaceCapacity: number | null,
  tags: string[],
) {
  const plannedTotal = planned.orbital + planned.surface;
  const projectedTotal = projected.orbital + projected.surface;
  const type = `${body.body_type ?? ''} ${body.subtype ?? ''}`.toLowerCase();
  const isBarycentre = type.includes('barycentre');
  if (isBarycentre && plannedTotal === 0 && projectedTotal === 0) return 0;

  let score = 0;
  score += plannedTotal * 120;
  score += projectedTotal * 90;
  if (body.body_type !== 'Star') score += 10;
  if (body.is_landable === true) score += 35;
  if (body.is_terraformable === true) score += 20;
  if (body.is_water_world === true) score += 12;
  if (orbitalCapacity != null && orbitalCapacity > 0) score += 16 + orbitalCapacity;
  if (surfaceCapacity != null && surfaceCapacity > 0) score += 22 + surfaceCapacity;
  if (tags.some((tag) => /earth-like|water|high metal|metal-rich|terraformable/i.test(tag))) score += 15;
  if (body.body_type === 'Star') score -= 25;
  return Math.max(0, score);
}

function overviewBodyIcon(body: SystemBody) {
  if (body.body_type === 'Star') return 'S';
  if (body.body_type === 'Planet' && body.parent_body_id != null) return 'M';
  if (body.body_type === 'Planet') return 'P';
  return 'B';
}

function overviewBodyKind(body: SystemBody) {
  const subtype = body.subtype?.replace(/\bworld\b/i, '').trim();
  const type = subtype || body.body_type || 'Body';
  const flags = [
    body.is_landable ? 'landable' : null,
    body.is_water_world ? 'water' : null,
    body.is_terraformable ? 'terraformable' : null,
  ].filter(Boolean);
  return flags.length > 0 ? `${type} / ${flags.join(' / ')}` : type;
}

function bodySortDistance(body: SystemBody) {
  return body.distance_from_star ?? Number.MAX_SAFE_INTEGER;
}

function sumKnownCapacity(items: SystemOverviewItem[], lane: 'orbital' | 'surface') {
  return items.reduce((sum, item) => {
    const value = lane === 'orbital' ? item.orbitalCapacity : item.surfaceCapacity;
    return sum + (value ?? 0);
  }, 0);
}

function BodyStructurePickerDrawer({
  body,
  lane,
  templates,
  onClose,
  onPickTemplate,
}: {
  body: SystemBody | null;
  lane: BodyPlannerLane | null;
  templates: FacilityTemplate[];
  onClose: () => void;
  onPickTemplate: (templateId: string) => void;
}) {
  const [query, setQuery] = useState('');

  if (!body || body.id == null || !lane) return null;

  const bodyName = bodyDisplayName(body);
  const laneLabel = lane === 'orbital' ? 'orbit' : 'surface';
  const filtered = templates
    .filter((template) => templateMatchesLane(template, lane))
    .filter((template) => templateCanFitBody(template, body, lane))
    .filter((template) => {
      const text = `${template.name} ${template.id} ${template.category} ${template.economy ?? ''}`.toLowerCase();
      return text.includes(query.trim().toLowerCase());
    })
    .sort((a, b) => (a.tier - b.tier) || a.name.localeCompare(b.name));

  return (
    <section
      data-testid="body-structure-picker"
      className="mb-3 rounded-chunk-lg border border-orange/35 bg-bg2/75 px-3 py-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
            Add {laneLabel} structure
          </div>
          <h4 className="mt-0.5 text-sm font-bold text-silver">{bodyName}</h4>
          <p className="mt-0.5 font-mono text-[10px] text-silver-dk">
            Filtered to {laneLabel}-compatible templates for this body.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          Close
        </button>
      </div>

      <label className="mt-3 block">
        <span className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">Filter structures</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, economy, or category"
          className="mt-1 w-full"
        />
      </label>

      {templates.length === 0 ? (
        <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-[11px] text-gold">
          Facility catalogue is loading.
        </p>
      ) : filtered.length === 0 ? (
        <p className="mt-3 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-[11px] text-silver-dk">
          No matching {laneLabel} structures for this body and filter.
        </p>
      ) : (
        <div className="mt-3 grid max-h-72 gap-1.5 overflow-y-auto">
          {filtered.map((template) => (
            <button
              key={template.id}
              type="button"
              data-testid={`body-structure-template-${template.id}`}
              onClick={() => onPickTemplate(template.id)}
              className="flex items-center justify-between gap-2 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-left hover:border-orange/45 hover:bg-orange/8"
            >
              <div className="min-w-0">
                <div className="truncate text-[11px] font-bold text-silver">{template.name}</div>
                <div className="mt-0.5 flex flex-wrap gap-1.5">
                  <BodyFact label={`tier ${template.tier}`} />
                  <BodyFact label={template.category} />
                  {template.economy && <BodyFact label={template.economy} />}
                  <BodyFact label={templateLocationKind(template)} tone="cyan" />
                </div>
              </div>
              <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-orange">
                Add
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function templateCanFitBody(template: FacilityTemplate, body: SystemBody, lane: BodyPlannerLane) {
  const location = templateLocationKind(template);
  if (lane === 'surface') {
    if (body.is_water_world) return false;
    if (body.is_landable === false) return false;
  }
  if (location === 'surface') return Boolean(body.is_landable) && !body.is_water_world;
  return true;
}

function templateMatchesLane(template: FacilityTemplate, lane: BodyPlannerLane) {
  const location = templateLocationKind(template);
  if (lane === 'orbital') return location === 'orbital' || location === 'both';
  return location === 'surface' || location === 'both' || location === 'unknown';
}

function BodyStartAction({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-silver">{label}</div>
      <p className="mt-1 text-[10px] text-silver-dk">{detail}</p>
    </div>
  );
}

function BodyFact({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'orange' | 'gold' | 'cyan' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
            : tone === 'cyan'
              ? 'border-cyan/35 bg-cyan/10 text-cyan'
              : 'border-border/60 bg-bg3/45 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
