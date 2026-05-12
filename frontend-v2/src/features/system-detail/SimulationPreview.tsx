import { useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, Play, Plus, Trash2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getFacilityTemplates, simulateBuild } from '@/lib/api';
import type {
  FacilityTemplate,
  SimulateBuildPlacement,
  SimulateBuildResponse,
  SystemBody,
  SystemDetail,
} from '@/types/api';

const ARCHETYPES = [
  { id: 'refinery_industrial', label: 'Refinery / Industrial' },
  { id: 'extraction_refinery', label: 'Extraction / Refinery' },
  { id: 'agriculture_terraforming', label: 'Agriculture / Industrial' },
  { id: 'hitech_tourism', label: 'High Tech / Tourism' },
  { id: 'military_industrial', label: 'Military / Industrial' },
  { id: 'trade_logistics', label: 'Trade / Logistics' },
  { id: 'flexible_multirole', label: 'Flexible Multirole' },
];

export function SimulationPreview({ system }: { system: SystemDetail }) {
  const templatesQuery = useQuery<FacilityTemplate[], Error>({
    queryKey: ['facility-templates'],
    queryFn: getFacilityTemplates,
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });
  const [targetArchetype, setTargetArchetype] = useState('refinery_industrial');
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [result, setResult] = useState<SimulateBuildResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const templates = templatesQuery.data ?? [];
  const bodies = useMemo(() => simulationBodies(system.bodies), [system.bodies]);
  const canRun = placements.length > 0 && !running;

  const addPlacement = () => {
    const firstTemplate = preferredTemplate(templates);
    if (!firstTemplate) return;
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
    setPlacements((current) => current.map((item, i) => {
      if (i !== index) {
        return patch.is_primary_port ? { ...item, is_primary_port: false } : item;
      }
      return { ...item, ...patch };
    }));
  };

  const removePlacement = (index: number) => {
    setPlacements((current) => resequence(current.filter((_, i) => i !== index)));
  };

  const movePlacement = (index: number, direction: -1 | 1) => {
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
              Choose a proposed build plan and preview CP pressure, economy order, contamination risk, and next steps.
            </p>
          </div>
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

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
        <div className="space-y-3">
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
            <div className="rounded-chunk-lg border border-dashed border-border bg-bg3/25 px-4 py-6 text-center">
              <div className="font-mono text-xs text-silver">No facilities in this preview yet.</div>
              <div className="mt-1 text-[11px] text-silver-dk">
                Add a primary port, then support facilities, then run the preview.
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

      <EconomyBars composition={result.economy_composition} order={result.economy_order} />
      <CpSummary cp={result.cp} />

      <div className="grid gap-2">
        {result.strengths.length > 0 && <Message title="Why this works" tone="good" items={result.strengths} />}
        {result.warnings.length > 0 && <Message title="Warnings" tone="warn" items={result.warnings} />}
        {result.recommendations.length > 0 && <Message title="Next steps" tone="info" items={result.recommendations} />}
      </div>

      <LinkSummary result={result} />
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

function resequence(items: SimulateBuildPlacement[]): SimulateBuildPlacement[] {
  return items.map((item, index) => ({ ...item, build_order: index + 1 }));
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
