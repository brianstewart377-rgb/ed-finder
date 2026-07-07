import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getSimulationSummary } from '@/lib/api';
import type { BuildabilityData, SimulationSummary } from '@/types/api';

export interface BuildabilityPanelProps {
  id64: number;
}

export function BuildabilityPanel({ id64 }: BuildabilityPanelProps) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const { data, isLoading, isError, error, refetch } = useQuery<SimulationSummary, Error>({
    queryKey: ['sim-summary', id64],
    queryFn: () => getSimulationSummary(id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/30 p-4 animate-pulse">
        <div className="h-4 w-44 rounded bg-bg4/70" />
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <div className="h-20 rounded bg-bg4/50" />
          <div className="h-20 rounded bg-bg4/40" />
          <div className="h-20 rounded bg-bg4/30" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-chunk-lg border border-red/40 bg-red/10 p-3 font-mono text-xs text-red">
        <div className="flex items-center gap-3">
          <span>Colony planning failed to load: {error?.message}</span>
          <button type="button" onClick={() => void refetch()} className="ml-auto underline hover:text-orange">
            retry
          </button>
        </div>
      </div>
    );
  }

  const buildability = data?.buildability;
  const classification = data?.classification;
  const archetype = classification?.primary_archetype ?? data?.archetype ?? 'flexible_multirole';
  const complexity = buildability?.build_complexity ?? 'unknown';
  const slotConfidence = buildability?.slot_confidence ?? classification?.data_confidence ?? null;
  const confidenceLabel = confidenceText(slotConfidence);
  const opportunities = buildability?.opportunities?.map((item) => item.description).filter(Boolean) ?? [];
  const risks = [
    ...(buildability?.bottlenecks?.map((item) => item.description).filter(Boolean) ?? []),
    ...(buildability?.warnings ?? []),
  ];
  const recommendation = planningRecommendation(archetype, complexity, slotConfidence, opportunities, risks);

  return (
    <div
      className="rounded-chunk-lg border border-orange/25 overflow-hidden shadow-metal"
      style={{ background: 'linear-gradient(180deg, rgba(27,29,34,0.95), rgba(11,13,17,0.95))' }}
    >
      <div className="border-b border-border/70 bg-orange/5 px-4 py-3">
        <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Colony Planning</h3>
        <p className="mt-1 text-[11px] text-silver-dk font-mono">
          Buildability, likely infrastructure capacity, and recommended next steps.
        </p>
      </div>

      <div className="space-y-4 p-4">
        <div className="rounded-chunk-lg border border-orange/35 bg-orange/10 p-4">
          <div className="flex flex-wrap items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Best use</div>
              <div className="mt-1 text-lg font-mono font-bold text-silver">
                {formatArchetype(archetype)}
              </div>
              <p className="mt-2 text-sm leading-snug text-silver">
                {recommendation.summary}
              </p>
            </div>
            <Badge label={titleCase(complexity)} tone={complexityTone(complexity)} />
            <Badge label={confidenceLabel} tone={confidenceTone(slotConfidence)} />
          </div>
        </div>

        <Callout title="Recommended next action" items={[recommendation.nextAction]} tone="info" />

        <div className="grid gap-3 md:grid-cols-2">
          <Callout
            title="Key opportunities"
            items={opportunities.length ? opportunities.slice(0, 3) : ['Use Recommended Builds to generate a practical starter plan for this system.']}
            tone="good"
          />
          <Callout
            title="Key risks"
            items={risks.length ? risks.slice(0, 3) : ['No major buildability risks are flagged yet. Preview the plan before committing resources.']}
            tone="warn"
          />
        </div>

        {slotConfidence != null && slotConfidence < 0.55 && (
          <Callout
            title="Data confidence"
            items={['Slot data is predicted, not observed. Advanced plans are hidden until better topology data is available.']}
            tone="warn"
          />
        )}

        <button
          type="button"
          onClick={() => setTechnicalOpen((value) => !value)}
          className="flex w-full items-center justify-between rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-left font-mono text-[11px] uppercase tracking-[0.14em] text-silver-dk hover:border-orange/50 hover:text-orange"
        >
          <span>Technical details</span>
          {technicalOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>

        {technicalOpen && buildability && <TechnicalDetails buildability={buildability} topology={data?.topology_summary ?? []} />}
      </div>
    </div>
  );
}

function TechnicalDetails({ buildability, topology }: { buildability: BuildabilityData; topology: string[] }) {
  const metrics = [
    ['Orbital slots', buildability.estimated_orbital_slots ?? '-'],
    ['Surface slots', buildability.estimated_ground_slots ?? '-'],
    ['Yellow CP', buildability.estimated_yellow_cp ?? '-'],
    ['Green CP', buildability.estimated_green_cp ?? '-'],
    ['T2 ports', buildability.max_t2_ports ?? '-'],
    ['T3 ports', buildability.max_t3_ports ?? '-'],
  ];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded border border-border/60 bg-bg3/60 p-2 text-center">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
            <div className="mt-1 font-mono text-sm font-bold text-orange tabular-nums">{value}</div>
          </div>
        ))}
      </div>
      {topology.length > 0 && (
        <ul className="mt-3 space-y-1 font-mono text-[11px] text-silver-dk">
          {topology.slice(0, 4).map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </div>
  );
}

function Callout({ title, items, tone }: { title: string; items: string[]; tone: 'good' | 'warn' | 'info' }) {
  const cls = tone === 'good'
    ? 'border-green/35 bg-green/5 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/5 text-gold'
      : 'border-cyan/30 bg-cyan/5 text-cyan';
  return (
    <div className={`rounded-chunk-lg border px-3 py-2 font-mono text-[11px] ${cls}`}>
      <div className="mb-1 text-[10px] uppercase tracking-[0.16em] opacity-80">{title}</div>
      <ul className="space-y-1">
        {items.map((item) => <li key={item} className="leading-snug">{item}</li>)}
      </ul>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: 'green' | 'gold' | 'red' | 'orange' | 'silver' }) {
  const colour = {
    green: '#4ade80',
    gold: '#fbbf24',
    red: '#ef5350',
    orange: '#f97316',
    silver: '#9ca3af',
  }[tone];
  return (
    <span
      className="rounded-chunk-sm border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
      style={{ borderColor: `${colour}70`, color: colour, backgroundColor: `${colour}18` }}
    >
      {label}
    </span>
  );
}

function planningRecommendation(archetype: string, complexity: string, confidence: number | null, opportunities: string[], risks: string[]) {
  const summary = `Best suited for ${formatArchetype(archetype)}. ${titleCase(complexity)} build: ${risks.length ? 'strong potential, but build order matters.' : 'good starting conditions for a recommended plan.'}`;
  const nextAction = confidence != null && confidence < 0.55
    ? 'Review the Simple recommended build first; use advanced simulation only after better body scan data is available.'
    : opportunities.length
      ? 'Open the Balanced recommended build, preview the result, then adjust facility order if warnings appear.'
      : 'Open Recommended Builds and choose a starter plan before editing manually.';
  return { summary, nextAction };
}

function formatArchetype(value?: string | null): string {
  if (!value) return 'Flexible Multirole';
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function titleCase(value?: string | null): string {
  if (!value) return 'Unknown';
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function confidenceText(value: number | null): string {
  if (value == null) return 'Unknown confidence';
  if (value >= 0.75) return 'High confidence';
  if (value >= 0.55) return 'Medium confidence';
  return 'Low confidence';
}

function confidenceTone(value: number | null): 'green' | 'gold' | 'red' | 'silver' {
  if (value == null) return 'silver';
  if (value >= 0.75) return 'green';
  if (value >= 0.55) return 'gold';
  return 'red';
}

function complexityTone(value?: string | null): 'green' | 'gold' | 'orange' | 'red' | 'silver' {
  if (value === 'simple' || value === 'trivial') return 'green';
  if (value === 'moderate') return 'gold';
  if (value === 'advanced' || value === 'complex') return 'orange';
  if (value === 'expert' || value === 'very_complex') return 'red';
  return 'silver';
}
