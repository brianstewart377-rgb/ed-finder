import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Edit3, Play, Plus, Sparkles, Trash2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getFacilityTemplates, getSimulationSummary, simulateBuild } from '@/lib/api';
import type {
  BuildabilityData,
  FacilityTemplate,
  RecommendedBuildPlan,
  SimulateBuildPlacement,
  SimulateBuildRequest,
  SimulateBuildResponse,
  SimulationSummary,
  SystemBody,
  SystemDetail,
} from '@/types/api';

const ARCHETYPES = [
  { id: 'refinery_industrial', label: 'Refinery / Industrial' },
  { id: 'extraction_refinery', label: 'Extraction / Refinery' },
  { id: 'agriculture_terraforming', label: 'Agriculture / Terraforming' },
  { id: 'hitech_tourism', label: 'High Tech / Tourism' },
  { id: 'military_industrial', label: 'Military / Industrial' },
  { id: 'trade_logistics', label: 'Trade / Logistics' },
  { id: 'flexible_multirole', label: 'Flexible Multirole' },
];

type StartMode = 'recommended' | 'edit_recommended' | 'blank_advanced';
type RecommendedStep = NonNullable<BuildabilityData['recommended_build_order']>[number];

export function SimulationPreview({
  system,
  initialRequest,
  initialPlanLabel,
  initialAssumptions = [],
}: {
  system: SystemDetail;
  initialRequest?: SimulateBuildRequest | null;
  initialPlanLabel?: string | null;
  initialAssumptions?: string[];
}) {
  const templatesQuery = useQuery<FacilityTemplate[], Error>({
    queryKey: ['facility-templates'],
    queryFn: getFacilityTemplates,
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });
  const summaryQuery = useQuery<SimulationSummary, Error>({
    queryKey: ['sim-summary-preview', system.id64],
    queryFn: () => getSimulationSummary(system.id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  const [targetArchetype, setTargetArchetype] = useState('refinery_industrial');
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [result, setResult] = useState<SimulateBuildResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startMode, setStartMode] = useState<StartMode>('recommended');
  const [autoLoadedRecommendation, setAutoLoadedRecommendation] = useState(false);

  const templates = templatesQuery.data ?? [];
  const bodies = useMemo(() => simulationBodies(system.bodies), [system.bodies]);
  const recommendedSteps = summaryQuery.data?.buildability?.recommended_build_order ?? [];
  const regionalContext = summaryQuery.data?.regional_context ?? null;
  const suggestedArchetype = summaryQuery.data?.classification?.primary_archetype
    ?? archetypeFromEconomy(system.economy_suggestion)
    ?? 'refinery_industrial';
  const recommendedPlacements = useMemo(
    () => buildRecommendedPlacements(recommendedSteps, templates, bodies),
    [recommendedSteps, templates, bodies],
  );
  const hasRecommendedBuild = recommendedPlacements.length > 0;
  const canRun = placements.length > 0 && !running;

  useEffect(() => {
    if (!initialRequest) return;
    setTargetArchetype(initialRequest.target_archetype);
    setPlacements(resequence(initialRequest.placements));
    setResult(null);
    setError(null);
    setStartMode('edit_recommended');
    setAutoLoadedRecommendation(true);
  }, [initialRequest]);

  useEffect(() => {
    if (!hasRecommendedBuild || autoLoadedRecommendation) return;
    if (placements.length > 0 || startMode === 'blank_advanced') return;
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    setResult(null);
    setError(null);
    setStartMode('recommended');
    setAutoLoadedRecommendation(true);
  }, [autoLoadedRecommendation, hasRecommendedBuild, placements.length, recommendedPlacements, startMode, suggestedArchetype]);

  const loadRecommendedPlan = (mode: StartMode) => {
    if (!hasRecommendedBuild) return;
    setStartMode(mode);
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    setResult(null);
    setError(null);
  };

  const startBlankAdvanced = () => {
    setStartMode('blank_advanced');
    setAutoLoadedRecommendation(true);
    setPlacements([]);
    setResult(null);
    setError(null);
  };

  const addPlacement = () => {
    const firstTemplate = preferredTemplate(templates);
    if (!firstTemplate) return;
    if (placements.length === 0 && startMode !== 'blank_advanced') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => [
      ...current,
      {
        facility_template_id: firstTemplate.id,
        local_body_id: bodies[0]?.id != null ? String(bodies[0].id) : null,
        is_primary_port: current.length === 0 && firstTemplate.is_port,
        build_order: current.length + 1,
      },
    ]);
  };

  const updatePlacement = (index: number, patch: Partial<SimulateBuildPlacement>) => {
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => current.map((item, i) => {
      if (i !== index) {
        return patch.is_primary_port ? { ...item, is_primary_port: false } : item;
      }
      return { ...item, ...patch };
    }));
  };

  const removePlacement = (index: number) => {
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => resequence(current.filter((_, i) => i !== index)));
  };

  const movePlacement = (index: number, direction: -1 | 1) => {
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
      return resequence(copy);
    });
  };

  const runSimulation = async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    try {
      const response = await simulateBuild({
        system_id64: system.id64,
        target_archetype: targetArchetype,
        placements: resequence(placements),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div
      className="rounded-chunk-lg border border-orange/25 overflow-hidden shadow-metal"
      style={{
        background: 'linear-gradient(180deg, rgba(27,29,34,0.95), rgba(11,13,17,0.95))',
      }}
    >
      <div className="px-4 py-3 border-b border-border/70 bg-orange/5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">
              Simulation Preview
            </h3>
            <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
              This preview shows what your selected build would produce before you commit in-game.
            </p>
            {initialPlanLabel && (
              <p className="mt-1 text-[11px] text-orange font-mono">
                You are previewing the {initialPlanLabel}.
              </p>
            )}
          </div>
          <PlanBadge mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />
          <button
            type="button"
            onClick={runSimulation}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 disabled:opacity-45 disabled:cursor-not-allowed"
          >
            <Play size={14} />
            {running ? 'Running' : 'Run Preview'}
          </button>
        </div>
      </div>

      <div className="border-b border-border/60 px-4 py-3">
        <StartModes
          mode={startMode}
          hasRecommendedBuild={hasRecommendedBuild}
          loadingRecommended={summaryQuery.isLoading || templatesQuery.isLoading}
          onUseRecommended={() => loadRecommendedPlan('recommended')}
          onEditRecommended={() => loadRecommendedPlan('edit_recommended')}
          onBlank={startBlankAdvanced}
        />
        {initialAssumptions.length > 0 && (
          <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">Estimated assumptions</div>
            <ul className="mt-1 space-y-1 font-mono text-[11px] text-silver-dk">
              {initialAssumptions.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
        <div className="space-y-3">
          <ModeIntro mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />

          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="space-y-1">
              <span className="block text-[10px] font-mono uppercase tracking-[0.16em] text-silver-dk">
                Target archetype
              </span>
              <select
                value={targetArchetype}
                onChange={(e) => setTargetArchetype(e.target.value)}
                className="w-full"
              >
                {ARCHETYPES.map((archetype) => (
                  <option key={archetype.id} value={archetype.id}>{archetype.label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={addPlacement}
              disabled={templates.length === 0}
              className="self-end inline-flex items-center justify-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-xs font-mono text-silver hover:border-orange/60 hover:text-orange disabled:opacity-45"
            >
              <Plus size={14} />
              Add Facility
            </button>
          </div>

          {templatesQuery.isLoading && (
            <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 text-xs font-mono text-silver-dk">
              Loading facility catalogue...
            </div>
          )}

          {templatesQuery.isError && (
            <Message tone="warn" items={[templatesQuery.error?.message ?? 'Facility catalogue failed to load.']} />
          )}

          {placements.length === 0 ? (
            <div className="rounded-chunk-lg border border-dashed border-gold/45 bg-gold/5 px-4 py-6 text-center">
              <div className="font-mono text-xs text-gold">
                {startMode === 'blank_advanced' ? 'Blank advanced simulation' : 'No recommended build loaded yet'}
              </div>
              <div className="mt-1 text-[11px] text-silver-dk">
                {startMode === 'blank_advanced'
                  ? 'Start with a primary port, then add support facilities and run the preview.'
                  : 'Use a recommended build when available, or choose the advanced blank mode.'}
              </div>
            </div>
          ) : (
            <BuildPlanEditor
              placements={placements}
              templates={templates}
              bodies={bodies}
              onUpdate={updatePlacement}
              onRemove={removePlacement}
              onMove={movePlacement}
            />
          )}
        </div>

        <div className="space-y-3">
          <RegionalContextMini regional={regionalContext} loading={summaryQuery.isLoading} />
          {error && <Message tone="danger" items={[error]} />}
          {result ? (
            <SimulationResult result={result} />
          ) : (
            <div className="h-full min-h-[260px] rounded-chunk-lg border border-border/60 bg-bg3/25 p-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                Awaiting preview
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <GhostMetric label="Score" />
                <GhostMetric label="Build" />
                <GhostMetric label="Confidence" />
              </div>
              <div className="mt-5 space-y-2">
                <div className="h-3 w-4/5 rounded bg-bg4/70" />
                <div className="h-3 w-2/3 rounded bg-bg4/50" />
                <div className="h-3 w-1/2 rounded bg-bg4/40" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export type { RecommendedBuildPlan };

function StartModes({
  mode,
  hasRecommendedBuild,
  loadingRecommended,
  onUseRecommended,
  onEditRecommended,
  onBlank,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
  loadingRecommended: boolean;
  onUseRecommended: () => void;
  onEditRecommended: () => void;
  onBlank: () => void;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      <ModeButton
        active={mode === 'recommended'}
        disabled={!hasRecommendedBuild}
        icon={<Sparkles size={15} />}
        title="Use recommended build"
        body={hasRecommendedBuild ? 'Load ED-Finder\'s suggested plan and preview it directly.' : loadingRecommended ? 'Looking for a suggested plan...' : 'No suggested plan is available yet.'}
        onClick={onUseRecommended}
      />
      <ModeButton
        active={mode === 'edit_recommended'}
        disabled={!hasRecommendedBuild}
        icon={<Edit3 size={15} />}
        title="Edit selected recommended build"
        body="Start from the suggested plan, then adjust facilities, bodies, and order."
        onClick={onEditRecommended}
      />
      <ModeButton
        active={mode === 'blank_advanced'}
        icon={<AlertTriangle size={15} />}
        title="Start blank advanced simulation"
        body="Begin with an empty plan when you already know what you want to test."
        onClick={onBlank}
      />
    </div>
  );
}

function ModeButton({
  active,
  disabled,
  icon,
  title,
  body,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  icon: ReactNode;
  title: string;
  body: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        'rounded-chunk-lg border p-3 text-left transition-colors',
        active
          ? 'border-orange/65 bg-orange/12 shadow-brand-glow'
          : 'border-border/70 bg-bg2/70 hover:border-orange/45 hover:bg-orange/5',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-orange">
        {icon}
        <span>{title}</span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">{body}</p>
    </button>
  );
}

function ModeIntro({
  mode,
  hasRecommendedBuild,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
}) {
  const copy = mode === 'blank_advanced'
    ? {
        title: 'Advanced blank plan',
        body: 'You are building from scratch. Add every facility yourself, then run the preview to check CP, economy order, and risks.',
        tone: 'warn' as const,
      }
    : mode === 'edit_recommended'
      ? {
          title: 'Recommended plan editor',
          body: 'A suggested build is loaded. Adjust the sequence or facilities before previewing the in-game outcome.',
          tone: 'info' as const,
        }
      : {
          title: hasRecommendedBuild ? 'Recommended build loaded' : 'Waiting for recommended build',
          body: hasRecommendedBuild
            ? 'Start here: this is the safest first view. Run the preview as-is, then edit if you want to experiment.'
            : 'ED-Finder will load a recommended plan here when buildability data is available.',
          tone: hasRecommendedBuild ? 'good' as const : 'info' as const,
        };

  return <Message title={copy.title} tone={copy.tone} items={[copy.body]} />;
}

function PlanBadge({
  mode,
  hasRecommendedBuild,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
}) {
  const label = mode === 'blank_advanced'
    ? 'Advanced blank'
    : mode === 'edit_recommended'
      ? 'Editing recommendation'
      : hasRecommendedBuild ? 'Recommended plan' : 'Recommendation pending';
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chunk-sm border border-orange/40 bg-orange/10 px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-[0.12em] text-orange">
      <CheckCircle2 size={13} />
      {label}
    </span>
  );
}

function BuildPlanEditor({
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

function SimulationResult({ result }: { result: SimulateBuildResponse }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Final score" value={Math.round(result.final_score)} tone="orange" />
        <Metric label="Build" value={titleCase(result.build_complexity)} tone={complexityTone(result.build_complexity)} />
        <Metric label="Confidence" value={confidenceLabel(result.confidence)} tone={confidenceTone(result.confidence)} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Metric label="Composition" value={Math.round(result.composition_score)} />
        <Metric label="Buildability" value={Math.round(result.buildability_score)} />
      </div>

      <DataConfidencePanel result={result} />
      <EconomyBars composition={result.economy_composition} order={result.economy_order} />
      <EconomyStackPanel stack={result.economy_stack} />
      <PortEconomyPanel states={result.port_economy_states} ledger={result.influence_ledger} />
      <InheritedEconomyPanel profiles={result.inherited_economies} />
      <TopologyPanel topology={result.topology} />
      <CpSummary cp={result.cp} />
      <CpTimelinePanel timeline={result.cp_timeline} />
      <ServicesPanel services={result.services} />
      <PortServicePanel states={result.port_service_states} ledger={result.service_unlock_ledger} />

      <div className="grid gap-2">
        {result.strengths.length > 0 && <Message title="Why this works" tone="good" items={result.strengths} />}
        {result.warnings.length > 0 && <Message title="Warnings" tone="warn" items={result.warnings} />}
        {result.recommendations.length > 0 && <Message title="Next steps" tone="info" items={result.recommendations} />}
      </div>

      <LinkSummary result={result} />
      <MechanicsTracePanel trace={result.mechanics_trace} />
    </div>
  );
}

export function DataConfidencePanel({ result }: { result: SimulateBuildResponse }) {
  const qualityRows = Object.entries(result.data_quality ?? {});
  const signals = result.confidence_signals ?? [];
  if (qualityRows.length === 0 && signals.length === 0) return null;
  return (
    <details className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Data Confidence
      </summary>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {qualityRows.map(([area, level]) => (
          <Chip key={area} tone={levelTone(level)}>{titleCase(area)}: {standardLabel(level)}</Chip>
        ))}
      </div>
      {signals.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {signals.slice(0, 5).map((signal) => (
            <div key={`${signal.area}-${signal.reason}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]">
                <span className="text-silver">{titleCase(signal.area)}</span>
                <span className={confidenceLevelTone(signal.level)}>{standardLabel(signal.level)}</span>
              </div>
              <p className="mt-1 text-[10px] leading-snug text-silver-dk">{signal.reason}</p>
            </div>
          ))}
        </div>
      )}
    </details>
  );
}

export function MechanicsTracePanel({ trace }: { trace: SimulateBuildResponse['mechanics_trace'] }) {
  const categories = Object.entries(trace ?? {}).filter(([, events]) => Array.isArray(events) && events.length > 0);
  if (categories.length === 0) return null;
  return (
    <details data-testid="mechanics-trace-accordion" className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.18em] text-silver">
        Mechanics Trace
      </summary>
      <div className="mt-3 space-y-2">
        {categories.slice(0, 6).map(([category, events]) => (
          <div key={category} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-orange">{titleCase(category)}</div>
            <div className="mt-1 space-y-1">
              {events.slice(0, 3).map((event) => (
                <div key={`${category}-${event.label}-${event.description}`} className="font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{event.label}:</span> {event.description}
                  {event.delta != null && <span className="text-orange"> ({event.delta > 0 ? '+' : ''}{event.delta})</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function RegionalContextMini({
  regional,
  loading,
}: {
  regional: SimulationSummary['regional_context'];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-chunk-lg border border-border/50 bg-bg3/25 p-3">
        <div className="h-3 w-40 rounded bg-bg4/60" />
        <div className="mt-3 h-3 w-2/3 rounded bg-bg4/40" />
      </div>
    );
  }
  if (!regional || regional.regional_role === 'unknown') {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-3 font-mono text-[11px] text-silver-dk">
        <div className="text-[10px] uppercase tracking-[0.18em] text-silver-dk">Regional context</div>
        <div className="mt-1">Regional positioning is not computed yet; local simulation remains deterministic.</div>
      </div>
    );
  }
  const bestFit = Object.entries(regional.archetype_regional_fit)
    .sort((a, b) => b[1] - a[1])[0];
  return (
    <div className="rounded-chunk-lg border border-orange/25 bg-orange/5 p-3 font-mono text-[11px] text-silver">
      <div className="text-[10px] uppercase tracking-[0.18em] text-orange">Regional context</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Chip tone="warn">{titleCase(regional.regional_role)}</Chip>
        {regional.nearest_colonised_system?.distance_ly != null && (
          <Chip>{regional.nearest_colonised_system.distance_ly.toFixed(0)} LY nearest colony</Chip>
        )}
        {bestFit && <Chip tone="good">{titleCase(bestFit[0])}: {Math.round(bestFit[1])}</Chip>}
      </div>
      {regional.rationale?.summary && (
        <p className="mt-2 leading-snug text-silver-dk">{regional.rationale.summary}</p>
      )}
    </div>
  );
}

function EconomyStackPanel({ stack }: { stack: SimulateBuildResponse['economy_stack'] }) {
  const topTwo = asStringArray(stack.top_two);
  const tertiary = asStringArray(stack.tertiary);
  const strengths = stack.strengths && typeof stack.strengths === 'object'
    ? Object.entries(stack.strengths as Record<string, unknown>)
      .filter(([, value]) => typeof value === 'number')
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 5)
    : [];
  const warnings = asStringArray(stack.warnings);
  if (topTwo.length === 0 && strengths.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Economy stack identity
      </div>
      <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
        {topTwo.map((economy) => <Chip key={economy} tone="good">{economy} top-two</Chip>)}
        {tertiary.map((economy) => <Chip key={economy} tone="warn">{economy} tertiary pressure</Chip>)}
        {asNumber(stack.purity_score) != null && <Chip>{Math.round(asNumber(stack.purity_score) ?? 0)} purity</Chip>}
        {asString(stack.contamination_risk) && <Chip tone={asString(stack.contamination_risk) === 'low' ? 'good' : 'warn'}>{titleCase(asString(stack.contamination_risk) ?? '')} contamination</Chip>}
      </div>
      {strengths.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {strengths.map(([economy, value]) => (
            <div key={economy} className="grid grid-cols-[96px_minmax(0,1fr)_42px] items-center gap-2">
              <span className="truncate font-mono text-[10px] text-silver-dk">{economy}</span>
              <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                <div className="h-full rounded-full bg-orange-grad" style={{ width: `${Math.max(3, Math.min(100, Number(value)))}%` }} />
              </div>
              <span className="text-right font-mono text-[10px] text-orange tabular-nums">{Number(value).toFixed(0)}</span>
            </div>
          ))}
        </div>
      )}
      {warnings.slice(0, 2).map((warning) => (
        <div key={warning} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
          {warning}
        </div>
      ))}
    </div>
  );
}

function PortEconomyPanel({
  states,
  ledger,
}: {
  states: SimulateBuildResponse['port_economy_states'];
  ledger: SimulateBuildResponse['influence_ledger'];
}) {
  if ((!states || states.length === 0) && (!ledger || ledger.length === 0)) return null;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Port Economy Breakdown
      </div>
      {states && states.length > 0 ? (
        <div className="space-y-3">
          {states.map((state) => {
            const topInfluences = [...(state.influences ?? [])]
              .sort((a, b) => b.value - a.value)
              .slice(0, 4);
            return (
              <div key={`${state.local_body_id ?? 'system'}-${state.port_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-[11px] text-silver">{state.port_name}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
                      {state.body_name || (state.local_body_id ? `Body ${state.local_body_id}` : 'System-wide')} · {titleCase(state.location_type)} · {titleCase(state.effective_role)}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5 font-mono text-[10px]">
                    {state.top_two.map((economy) => <Chip key={economy} tone="good">{economy}</Chip>)}
                    {state.tertiary_economies.map((economy) => <Chip key={economy} tone="warn">{economy} tertiary</Chip>)}
                    <Chip>{Math.round(state.purity_score)} purity</Chip>
                    <Chip tone={state.contamination_risk === 'low' ? 'good' : 'warn'}>{titleCase(state.contamination_risk)} risk</Chip>
                  </div>
                </div>
                {topInfluences.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {topInfluences.map((influence) => (
                      <div key={`${influence.source_id}-${influence.influence_type}-${influence.economy}-${influence.value}`} className="grid grid-cols-[minmax(0,1fr)_70px_42px] gap-2 font-mono text-[10px] text-silver-dk">
                        <span className="truncate">{influence.source_name} · {titleCase(influence.influence_type)}</span>
                        <span className="truncate text-silver">{influence.economy}</span>
                        <span className="text-right text-cyan tabular-nums">{influence.value.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {[...(state.warnings ?? []), ...(state.recommendations ?? [])].slice(0, 2).map((item) => (
                  <div key={item} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                    {item}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-border/60 bg-bg3/45 px-2 py-2 font-mono text-[10px] text-silver-dk">
          No Main Ports are present yet, so there are no per-port economy states.
        </div>
      )}
      {ledger && ledger.length > 0 && (
        <details className="mt-3 rounded border border-border/60 bg-bg2/55 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Influence Ledger
          </summary>
          <div className="mt-2 space-y-1.5">
            {ledger.slice(0, 12).map((influence) => (
              <div key={`${influence.source_id}-${influence.target_port_id}-${influence.influence_type}-${influence.economy}-${influence.value}`} className="rounded border border-border/50 bg-bg3/45 px-2 py-1.5">
                <div className="grid gap-1 font-mono text-[10px] text-silver-dk sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_92px_70px_42px]">
                  <span className="truncate"><span className="text-silver">Source:</span> {influence.source_name}</span>
                  <span className="truncate"><span className="text-silver">Target:</span> {influence.target_port_name}</span>
                  <span>{titleCase(influence.influence_type)}</span>
                  <span>{influence.economy}</span>
                  <span className="text-right text-cyan tabular-nums">{influence.value.toFixed(2)}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{titleCase(influence.confidence)}:</span> {influence.reason}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

type TopologySummary = {
  local_body_groups?: Array<{
    local_body_id: string;
    body_name?: string | null;
    main_surface_port?: { facility_name: string; tier: number } | null;
    main_orbital_port?: { facility_name: string; tier: number } | null;
    facility_count: number;
  }>;
  strong_links?: unknown[];
  weak_links?: unknown[];
  pass_through_links?: unknown[];
  converted_ports?: Array<{ facility_name: string; reason: string }>;
};

function TopologyPanel({ topology }: { topology: SimulateBuildResponse['topology'] }) {
  const summary = topology as TopologySummary | undefined;
  const groups = summary?.local_body_groups ?? [];
  if (groups.length === 0) return null;
  const strong = summary?.strong_links?.length ?? 0;
  const weak = summary?.weak_links?.length ?? 0;
  const passThrough = summary?.pass_through_links?.length ?? 0;
  const converted = summary?.converted_ports ?? [];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3 font-mono text-[11px] text-silver">
      <div className="mb-2 text-[10px] uppercase tracking-[0.18em] text-silver-dk">Topology graph</div>
      <div className="flex flex-wrap gap-1.5">
        <Chip tone={strong > 0 ? 'good' : 'default'}>{strong} strong links</Chip>
        <Chip>{weak} weak links</Chip>
        {passThrough > 0 && <Chip tone="good">{passThrough} pass-through</Chip>}
        {converted.length > 0 && <Chip tone="warn">{converted.length} converted ports</Chip>}
      </div>
      <div className="mt-2 space-y-1.5">
        {groups.slice(0, 3).map((group) => (
          <div key={group.local_body_id} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="text-silver">{group.body_name || `Body ${group.local_body_id}`}</div>
            <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-silver-dk">
              {group.main_orbital_port && <span>Orbital Main: {group.main_orbital_port.facility_name}</span>}
              {group.main_surface_port && <span>Surface Main: {group.main_surface_port.facility_name}</span>}
              <span>{group.facility_count} assets</span>
            </div>
          </div>
        ))}
      </div>
      {converted.slice(0, 2).map((port) => (
        <div key={port.facility_name} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 text-[10px] leading-snug text-gold">
          {port.facility_name}: {port.reason}
        </div>
      ))}
    </div>
  );
}

function CpTimelinePanel({ timeline }: { timeline: SimulateBuildResponse['cp_timeline'] }) {
  if (!timeline || timeline.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        CP build-order timeline
      </div>
      <div className="space-y-1.5">
        {timeline.slice(0, 5).map((step) => (
          <div key={`${step.step}-${step.facility_template_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-silver">
              <span className="truncate">{step.step}. {step.facility_name}</span>
              <span className="shrink-0 tabular-nums text-orange">
                Y {signed(step.yellow_delta)} / G {signed(step.green_delta)}
              </span>
            </div>
            <div className="mt-1 font-mono text-[10px] text-silver-dk">
              {step.yellow_before} {'->'} {step.yellow_after} yellow, {step.green_before} {'->'} {step.green_after} green
            </div>
            {step.warnings.slice(0, 1).map((warning) => (
              <div key={warning} className="mt-1 text-[10px] text-gold">{warning}</div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function ServicesPanel({ services }: { services: SimulateBuildResponse['services'] }) {
  const rows = Object.entries(services ?? {});
  if (rows.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Service unlocks
      </div>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {rows.map(([service, detail]) => (
          <div key={service} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
              <span className="truncate text-silver">{titleCase(service)}</span>
              <span className={serviceTone(detail.status)}>{titleCase(detail.status)}</span>
            </div>
            <div className="mt-1 line-clamp-2 text-[10px] leading-snug text-silver-dk">{detail.reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PortServicePanel({
  states,
  ledger,
}: {
  states: SimulateBuildResponse['port_service_states'];
  ledger: SimulateBuildResponse['service_unlock_ledger'];
}) {
  if ((!states || states.length === 0) && (!ledger || ledger.length === 0)) return null;
  return (
    <div className="rounded-chunk-lg border border-green/25 bg-green/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-green">
        Port Service Graph
      </div>
      {states && states.length > 0 ? (
        <div className="space-y-3">
          {states.map((state) => {
            const active = Object.values(state.active_services ?? {});
            const locked = Object.values(state.locked_services ?? {});
            const unknown = Object.values(state.unknown_services ?? {});
            return (
              <div key={`${state.local_body_id ?? 'system'}-${state.port_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-[11px] text-silver">{state.port_name}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
                      {state.body_name || (state.local_body_id ? `Body ${state.local_body_id}` : 'System-wide')} · {titleCase(state.location_type)} · {titleCase(state.effective_role)}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5 font-mono text-[10px]">
                    <Chip tone="good">{active.length} active</Chip>
                    <Chip tone={locked.length > 0 ? 'warn' : 'default'}>{locked.length} locked</Chip>
                    <Chip>{unknown.length} unknown</Chip>
                  </div>
                </div>
                <ServiceEntryGroup title="Active services" entries={active.slice(0, 4)} tone="good" />
                <ServiceEntryGroup title="Locked services" entries={locked.slice(0, 4)} tone="warn" />
                <ServiceEntryGroup title="Unknown" entries={unknown.slice(0, 3)} tone="default" />
                {[...(state.warnings ?? []), ...(state.recommendations ?? [])].slice(0, 2).map((item) => (
                  <div key={item} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                    {item}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-border/60 bg-bg3/45 px-2 py-2 font-mono text-[10px] text-silver-dk">
          No Main Ports are present yet, so there are no per-port service states.
        </div>
      )}
      {ledger && ledger.length > 0 && (
        <details className="mt-3 rounded border border-border/60 bg-bg2/55 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Service Unlock Ledger
          </summary>
          <div className="mt-2 space-y-1.5">
            {ledger.slice(0, 14).map((entry) => (
              <div key={`${entry.target_port_id}-${entry.service}-${entry.status}-${entry.unlock_type}-${entry.source_id ?? 'none'}`} className="rounded border border-border/50 bg-bg3/45 px-2 py-1.5">
                <div className="grid gap-1 font-mono text-[10px] text-silver-dk sm:grid-cols-[92px_72px_minmax(0,1fr)_minmax(0,1fr)]">
                  <span className={serviceTone(entry.status)}>{titleCase(entry.status)}</span>
                  <span>{titleCase(entry.unlock_type)}</span>
                  <span className="truncate"><span className="text-silver">Service:</span> {titleCase(entry.service)}</span>
                  <span className="truncate"><span className="text-silver">Target:</span> {entry.target_port_name}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{titleCase(entry.confidence)}:</span> {entry.reason}
                </div>
                {entry.caveats.slice(0, 1).map((caveat) => (
                  <div key={caveat} className="mt-1 font-mono text-[10px] leading-snug text-gold">{caveat}</div>
                ))}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function ServiceEntryGroup({
  title,
  entries,
  tone,
}: {
  title: string;
  entries: SimulateBuildResponse['service_unlock_ledger'];
  tone: 'good' | 'warn' | 'default';
}) {
  if (!entries || entries.length === 0) return null;
  const titleClass = tone === 'good' ? 'text-green' : tone === 'warn' ? 'text-gold' : 'text-silver-dk';
  return (
    <div className="mt-2 space-y-1">
      <div className={`font-mono text-[9px] uppercase tracking-[0.14em] ${titleClass}`}>{title}</div>
      {entries.map((entry) => (
        <div key={`${entry.service}-${entry.status}-${entry.source_id ?? 'none'}`} className="rounded border border-border/50 bg-bg2/45 px-2 py-1 font-mono text-[10px] text-silver-dk">
          <span className="text-silver">{titleCase(entry.service)}</span>
          {entry.source_name && <span> · {entry.source_name}</span>}
          <span> · {titleCase(entry.unlock_type)}</span>
          {entry.requirements.length > 0 && <div className="mt-0.5 text-gold">{entry.requirements[0]}</div>}
          {entry.caveats.length > 0 && <div className="mt-0.5 text-gold">{entry.caveats[0]}</div>}
        </div>
      ))}
    </div>
  );
}

function InheritedEconomyPanel({ profiles }: { profiles: SimulateBuildResponse['inherited_economies'] }) {
  if (!profiles || profiles.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Mixed inheritance
      </div>
      <div className="space-y-3">
        {profiles.map((profile, index) => {
          const rows = Object.entries(profile.weights).sort((a, b) => b[1] - a[1]);
          return (
            <div key={`${profile.source_body_id ?? 'body'}-${index}`} className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-silver">
                <span>{profile.source_body_name || (profile.source_body_id ? `Body ${profile.source_body_id}` : 'Inherited body')}</span>
                <span className={purityTone(profile.purity)}>{purityLabel(profile.purity)} purity</span>
              </div>
              <div className="space-y-1.5">
                {rows.map(([economy, weight]) => (
                  <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_44px] items-center gap-2">
                    <span className="truncate font-mono text-[10px] text-silver-dk">{economy}</span>
                    <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                      <div
                        className="h-full rounded-full bg-cyan"
                        style={{ width: `${Math.max(4, Math.min(100, weight * 100))}%` }}
                      />
                    </div>
                    <span className="text-right font-mono text-[10px] text-cyan tabular-nums">{Math.round(weight * 100)}%</span>
                  </div>
                ))}
              </div>
              {profile.modifier_economies.length > 0 && (
                <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                  {profile.modifier_economies.map((economy) => <Chip key={economy} tone="warn">{economy} modifier</Chip>)}
                </div>
              )}
              {profile.caveats.slice(0, 2).map((caveat) => (
                <div key={caveat} className="rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                  {caveat}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EconomyBars({ composition, order }: { composition: Record<string, number>; order: string[] }) {
  const rows = order.map((economy) => [economy, composition[economy] ?? 0] as const);
  if (rows.length === 0) {
    return <Message tone="warn" items={['No economy-producing facilities are present yet.']} />;
  }
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Economy result
      </div>
      <div className="space-y-2">
        {rows.map(([economy, value]) => (
          <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_48px] items-center gap-2">
            <span className="truncate font-mono text-[11px] text-silver">{economy}</span>
            <div className="h-2.5 overflow-hidden rounded-full border border-border bg-bg4">
              <div
                className="h-full rounded-full bg-orange-grad shadow-brand-glow"
                style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
              />
            </div>
            <span className="text-right font-mono text-[11px] tabular-nums text-orange">{value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function purityLabel(value: number): string {
  if (value >= 0.75) return 'High';
  if (value >= 0.55) return 'Medium';
  return 'Low';
}

function purityTone(value: number): string {
  if (value >= 0.75) return 'text-green';
  if (value >= 0.55) return 'text-gold';
  return 'text-red';
}

function CpSummary({ cp }: { cp: SimulateBuildResponse['cp'] }) {
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Construction points
      </div>
      <div className="grid grid-cols-4 gap-2">
        <CpCell label="Yellow" value={cp.yellow_cp_final} colour="#fbbf24" />
        <CpCell label="Green" value={cp.green_cp_final} colour="#4ade80" />
        <CpCell label="T2 ports" value={cp.t2_ports} colour="#c8ccd1" />
        <CpCell label="T3 ports" value={cp.t3_ports} colour="#7dd3fc" />
      </div>
      {cp.warnings.length > 0 && (
        <div className="mt-2 flex items-start gap-2 rounded border border-gold/30 bg-gold/5 px-2 py-1.5 text-[10px] font-mono text-gold">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>{cp.warnings[0]}</span>
        </div>
      )}
    </div>
  );
}

function LinkSummary({ result }: { result: SimulateBuildResponse }) {
  const strong = result.links.strong_links.length;
  const weak = result.links.weak_links.length;
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3 font-mono text-[11px] text-silver">
      <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-silver-dk">Link summary</div>
      <div className="flex flex-wrap gap-2">
        <Chip tone={strong > 0 ? 'good' : 'default'}>{strong} strong same-body links</Chip>
        <Chip>{weak} weak cross-body links</Chip>
        <Chip tone={result.contamination_risk === 'low' ? 'good' : 'warn'}>
          {titleCase(result.contamination_risk)} contamination
        </Chip>
        <Chip>{titleCase(result.top_two_alignment)} alignment</Chip>
      </div>
    </div>
  );
}

function Message({
  title,
  tone,
  items,
}: {
  title?: string;
  tone: 'good' | 'warn' | 'danger' | 'info';
  items: string[];
}) {
  const toneClass = {
    good: 'border-green/35 bg-green/5 text-green',
    warn: 'border-gold/35 bg-gold/5 text-gold',
    danger: 'border-red/40 bg-red/10 text-red',
    info: 'border-cyan/30 bg-cyan/5 text-cyan',
  }[tone];
  return (
    <div className={`rounded-chunk-lg border px-3 py-2 font-mono text-[11px] ${toneClass}`}>
      {title && <div className="mb-1 text-[10px] uppercase tracking-[0.16em] opacity-80">{title}</div>}
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item} className="leading-snug">{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = 'silver',
}: {
  label: string;
  value: string | number;
  tone?: 'orange' | 'silver' | 'green' | 'gold' | 'red' | 'cyan';
}) {
  const colour = {
    orange: 'text-orange',
    silver: 'text-silver',
    green: 'text-green',
    gold: 'text-gold',
    red: 'text-red',
    cyan: 'text-cyan',
  }[tone];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/80 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold tabular-nums ${colour}`}>{value}</div>
    </div>
  );
}

function GhostMetric({ label }: { label: string }) {
  return (
    <div className="rounded-chunk-lg border border-border/40 bg-bg2/50 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mx-auto mt-2 h-5 w-12 rounded bg-bg4/60" />
    </div>
  );
}

function CpCell({ label, value, colour }: { label: string; value: number; colour: string }) {
  return (
    <div className="rounded border border-border/60 bg-bg3/60 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="font-mono text-sm font-bold tabular-nums" style={{ color: colour }}>
        {value > 0 ? `+${value}` : value}
      </div>
    </div>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-chunk-sm border border-border bg-bg3 text-silver-dk hover:border-orange/50 hover:text-orange disabled:opacity-35 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

function Chip({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'good' | 'warn' }) {
  const cls = tone === 'good'
    ? 'border-green/35 bg-green/10 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border bg-bg4 text-silver-dk';
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 border ${cls}`}>
      {children}
    </span>
  );
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function serviceTone(status: string): string {
  if (status === 'active') return 'text-green';
  if (status === 'locked') return 'text-gold';
  return 'text-silver-dk';
}

function standardLabel(value: string): string {
  const labels: Record<string, string> = {
    observed: 'Observed',
    verified: 'Verified',
    community_observed: 'Community observed',
    inferred: 'Inferred',
    estimated: 'Estimated',
    speculative: 'Speculative',
    unknown: 'Unknown',
    predicted: 'Estimated',
  };
  return labels[value] ?? titleCase(value);
}

function levelTone(value: string): 'default' | 'good' | 'warn' {
  if (value === 'observed' || value === 'verified' || value === 'community_observed') return 'good';
  if (value === 'estimated' || value === 'speculative' || value === 'unknown' || value === 'predicted') return 'warn';
  return 'default';
}

function confidenceLevelTone(value: string): string {
  if (value === 'observed' || value === 'verified' || value === 'community_observed') return 'text-green';
  if (value === 'estimated' || value === 'speculative') return 'text-gold';
  if (value === 'unknown') return 'text-silver-dk';
  return 'text-cyan';
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function resequence(items: SimulateBuildPlacement[]): SimulateBuildPlacement[] {
  return items.map((item, index) => ({ ...item, build_order: index + 1 }));
}

function buildRecommendedPlacements(
  steps: RecommendedStep[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
): SimulateBuildPlacement[] {
  if (steps.length === 0 || templates.length === 0) return [];
  const byId = new Map(templates.map((template) => [template.id, template]));
  let primaryPortAssigned = false;
  const placements: SimulateBuildPlacement[] = [];

  for (const step of steps) {
    const facilityId = step.facility_id;
    if (!facilityId) continue;
    const template = byId.get(facilityId);
    if (!template) continue;
    const isPrimaryPort = template.is_port && !primaryPortAssigned;
    if (isPrimaryPort) {
      primaryPortAssigned = true;
    }
    placements.push({
      facility_template_id: template.id,
      local_body_id: recommendedBodyId(step.location, template, bodies),
      is_primary_port: isPrimaryPort,
      build_order: placements.length + 1,
    });
  }

  return resequence(placements);
}

function recommendedBodyId(
  location: string | null | undefined,
  template: FacilityTemplate,
  bodies: SystemBody[],
): string | null {
  if (bodies.length === 0) return null;
  const locationText = `${location ?? ''} ${template.allowed_location}`.toLowerCase();
  const body = locationText.includes('surface')
    ? bodies.find((item) => item.is_landable) ?? bodies[0]
    : bodies[0];
  return body?.id != null ? String(body.id) : null;
}

function preferredTemplate(templates: FacilityTemplate[]): FacilityTemplate | undefined {
  return templates.find((item) => item.is_port) ?? templates[0];
}

function simulationBodies(bodies?: SystemBody[]): SystemBody[] {
  return (bodies ?? []).filter((body) => body.body_type !== 'Star');
}

function formatLocation(location: string): string {
  return location.replace(/_/g, ' ');
}

function archetypeFromEconomy(economy?: string | null): string | null {
  const normalised = (economy ?? '').toLowerCase();
  if (normalised.includes('refinery')) return 'refinery_industrial';
  if (normalised.includes('extraction')) return 'extraction_refinery';
  if (normalised.includes('agriculture')) return 'agriculture_terraforming';
  if (normalised.includes('hightech') || normalised.includes('high tech') || normalised.includes('tourism')) return 'hitech_tourism';
  if (normalised.includes('military')) return 'military_industrial';
  if (normalised.includes('industrial')) return 'refinery_industrial';
  return null;
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function confidenceLabel(value: number): string {
  if (value >= 0.75) return 'High';
  if (value >= 0.55) return 'Medium';
  return 'Low';
}

function confidenceTone(value: number): 'green' | 'gold' | 'red' {
  if (value >= 0.75) return 'green';
  if (value >= 0.55) return 'gold';
  return 'red';
}

function complexityTone(value: SimulateBuildResponse['build_complexity']): 'green' | 'gold' | 'orange' | 'red' {
  if (value === 'simple') return 'green';
  if (value === 'moderate') return 'gold';
  if (value === 'advanced') return 'orange';
  return 'red';
}
