/**
 * BuildabilityPanel — Colony Build Analysis card
 * ================================================
 * Renders the buildability section within SystemDetailModal.
 *
 * Data source: GET /api/systems/{id64}/simulation-summary
 * The endpoint returns a `buildability` sub-object and `classification`
 * sub-object which this panel uses.
 *
 * Design language: ED orange / brushed-steel (matches SystemDetailModal).
 * Uses font-mono, text-orange, panel-thin, chip, tabular-nums throughout.
 *
 * Graceful degradation:
 *   • Loading  → skeleton shimmer rows
 *   • No data  → "Scan bodies in-game" prompt with EDDN hint
 *   • Partial  → renders whatever is available, hides missing sections
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSimulationSummary } from '@/lib/api';
import type { BuildabilityData, SimulationSummary } from '@/types/api';

// ─── Types ─────────────────────────────────────────────────────────────────

type ClassificationData = NonNullable<SimulationSummary['classification']>;
type BuildabilityIssue = NonNullable<BuildabilityData['bottlenecks']>[number];
type RecommendedBuildStep = NonNullable<BuildabilityData['recommended_build_order']>[number];

// ─── Fetch hook ─────────────────────────────────────────────────────────────

function useSimulationSummary(id64: number) {
  return useQuery<SimulationSummary, Error>({
    queryKey: ['sim-summary', id64],
    queryFn:  () => getSimulationSummary(id64),
    staleTime: 5 * 60 * 1000,   // 5 min — matches server Redis TTL
    retry:     1,
  });
}

// ─── Public component ───────────────────────────────────────────────────────

export interface BuildabilityPanelProps {
  id64: number;
}

export function BuildabilityPanel({ id64 }: BuildabilityPanelProps) {
  const { data, isLoading, isError, error, refetch } = useSimulationSummary(id64);

  if (isLoading) return <Buildabilityskeleton />;

  if (isError) {
    return (
      <div className="rounded border border-red/40 bg-red/10 px-3 py-2 font-mono text-xs text-red flex items-center gap-3">
        <span>Failed to load build analysis: {error?.message}</span>
        <button
          type="button"
          onClick={() => { void refetch(); }}
          className="ml-auto px-2 py-0.5 rounded bg-bg4 border border-border text-text-dim hover:text-orange"
        >
          ↺
        </button>
      </div>
    );
  }

  if (!data?.buildability || data.buildability.source === 'insufficient_data') {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/30 px-4 py-5 font-mono text-xs space-y-2 text-center">
        <div className="text-2xl" aria-hidden>🔭</div>
        <p className="text-silver font-semibold tracking-wide">No topology data yet</p>
        <p className="text-silver-dk max-w-sm mx-auto leading-relaxed">
          {data?.buildability?.note ??
            'Scan bodies with the Full Spectrum Scanner in-game to contribute slot data via EDDN.'}
        </p>
      </div>
    );
  }

  const ba = data.buildability;
  const cls = data.classification;

  return (
    <div className="space-y-4">
      {/* ── Classification badge row ─────────────────────────────────── */}
      {cls?.primary_archetype && (
        <ArchetypeBar classification={cls} />
      )}

      {/* ── Slot + CP summary grid ───────────────────────────────────── */}
      <SlotCpGrid ba={ba} />

      {/* ── Complexity + risk meters ─────────────────────────────────── */}
      <ComplexityRow ba={ba} />

      {/* ── Topology narrative bullets ───────────────────────────────── */}
      {data.topology_summary && data.topology_summary.length > 0 && (
        <TopologyNarrative points={data.topology_summary} />
      )}

      {/* ── Bottlenecks ──────────────────────────────────────────────── */}
      {ba.bottlenecks && ba.bottlenecks.length > 0 && (
        <BottleneckList items={ba.bottlenecks} />
      )}

      {/* ── Opportunities ────────────────────────────────────────────── */}
      {ba.opportunities && ba.opportunities.length > 0 && (
        <OpportunityList items={ba.opportunities} />
      )}

      {/* ── Recommended build order ──────────────────────────────────── */}
      {ba.recommended_build_order && ba.recommended_build_order.length > 0 && (
        <BuildOrderAccordion steps={ba.recommended_build_order} />
      )}

      {/* ── Data source footnote ─────────────────────────────────────── */}
      <DataSourceNote source={ba.source} confidence={ba.slot_confidence} />
    </div>
  );
}

// ─── ArchetypeBar ───────────────────────────────────────────────────────────

function ArchetypeBar({ classification: cls }: { classification: ClassificationData }) {
  const pct = Math.round((cls.confidence ?? 0) * 100);
  return (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <span className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">Archetype</span>
      <span className="px-2.5 py-0.5 rounded-chunk-sm border border-orange/50 bg-orange/10 text-orange font-mono text-[11px] font-semibold tracking-wide">
        {formatArchetype(cls.primary_archetype)}
      </span>
      {cls.secondary_archetype && (
        <span className="px-2 py-0.5 rounded-chunk-sm border border-silver-dk/40 bg-bg4 text-silver-dk font-mono text-[10px]">
          {formatArchetype(cls.secondary_archetype)}
        </span>
      )}
      <span className="ml-auto font-mono text-[10px] text-silver-dk tabular-nums">
        {pct}% confidence
      </span>
      {cls.display_tags?.map((tag) => (
        <span key={tag} className="chip">{tag}</span>
      ))}
    </div>
  );
}

// ─── SlotCpGrid ─────────────────────────────────────────────────────────────

function SlotCpGrid({ ba }: { ba: BuildabilityData }) {
  const confColour = confidenceColour(ba.slot_confidence_label);

  const cells: Array<{ label: string; value: React.ReactNode; highlight?: boolean }> = [
    {
      label: 'Orbital slots',
      value: (
        <span className="text-cyan tabular-nums">
          {ba.estimated_orbital_slots ?? '—'}
        </span>
      ),
    },
    {
      label: 'Surface slots',
      value: (
        <span className="text-cyan tabular-nums">
          {ba.estimated_ground_slots ?? '—'}
        </span>
      ),
    },
    {
      label: 'Yellow CP',
      value: (
        <span className="tabular-nums" style={{ color: '#f5c518' }}>
          {ba.estimated_yellow_cp ?? '—'}
        </span>
      ),
    },
    {
      label: 'Green CP',
      value: (
        <span className="tabular-nums" style={{ color: '#4caf50' }}>
          {ba.estimated_green_cp ?? '—'}
        </span>
      ),
    },
    {
      label: 'Max T2 ports',
      value: <span className="text-text tabular-nums">{ba.max_t2_ports ?? '—'}</span>,
    },
    {
      label: 'Max T3 ports',
      value: <span className="text-text tabular-nums">{ba.max_t3_ports ?? '—'}</span>,
    },
  ];

  return (
    <div className="space-y-2">
      {/* Confidence badge */}
      {ba.slot_confidence_label && (
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.14em]">
            Slot confidence
          </span>
          <span
            className="px-2 py-0.5 rounded-chunk-sm border font-mono text-[10px] font-bold"
            style={{ borderColor: confColour, color: confColour, backgroundColor: `${confColour}18` }}
          >
            {ba.slot_confidence_label}
          </span>
          {ba.slot_confidence != null && (
            <span className="text-silver-dk font-mono text-[10px] tabular-nums">
              ({Math.round(ba.slot_confidence * 100)}%)
            </span>
          )}
        </div>
      )}

      {/* Grid of stat cells */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {cells.map((c) => (
          <div
            key={c.label}
            className={[
              'rounded border p-2 text-center',
              c.highlight
                ? 'border-orange/50 bg-orange/10'
                : 'border-border bg-bg3/40',
            ].join(' ')}
          >
            <div className="font-mono uppercase tracking-wider text-[9px] text-text-dim mb-0.5">
              {c.label}
            </div>
            <div className="font-mono font-bold text-sm">{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── ComplexityRow ──────────────────────────────────────────────────────────

function ComplexityRow({ ba }: { ba: BuildabilityData }) {
  const complexityStyle = complexityChipStyle(ba.build_complexity);
  const risks: Array<{ label: string; value: number; colour: string }> = [
    {
      label:  'CP pressure',
      value:  ba.cp_bottleneck_score ?? 0,
      colour: riskColour(ba.cp_bottleneck_score ?? 0),
    },
    {
      label:  'Slot exhaustion',
      value:  ba.slot_exhaustion_risk ?? 0,
      colour: riskColour(ba.slot_exhaustion_risk ?? 0),
    },
    {
      label:  'Order sensitivity',
      value:  ba.build_order_sensitivity ?? 0,
      colour: riskColour(ba.build_order_sensitivity ?? 0),
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Complexity chip */}
      {ba.build_complexity && ba.build_complexity !== 'unknown' && (
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.14em]">Complexity</span>
          <span
            className="px-2.5 py-0.5 rounded-chunk-sm border font-mono text-[10px] font-bold uppercase tracking-wide"
            style={complexityStyle}
          >
            {ba.build_complexity}
          </span>
        </div>
      )}

      {/* Risk meter bars */}
      <div className="flex gap-3 ml-auto">
        {risks.map((r) => (
          <RiskMeter key={r.label} label={r.label} value={r.value} colour={r.colour} />
        ))}
      </div>
    </div>
  );
}

function RiskMeter({ label, value, colour }: { label: string; value: number; colour: string }) {
  const pct = riskPercent(value);
  return (
    <div className="flex flex-col items-center gap-0.5 min-w-[56px]">
      <div className="font-mono text-[9px] text-text-dim uppercase tracking-wide text-center whitespace-nowrap">
        {label}
      </div>
      <div className="w-full h-1.5 bg-bg4 rounded-full overflow-hidden border border-border/60">
        <div
          className="h-full transition-all rounded-full"
          style={{ width: `${pct}%`, backgroundColor: colour, boxShadow: `0 0 6px ${colour}66` }}
        />
      </div>
      <div className="font-mono text-[9px] tabular-nums" style={{ color: colour }}>
        {pct}%
      </div>
    </div>
  );
}

// ─── TopologyNarrative ──────────────────────────────────────────────────────

function TopologyNarrative({ points }: { points: string[] }) {
  return (
    <div
      className="rounded-chunk-lg border border-border/60 px-3 py-2.5 space-y-1.5"
      style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.7), rgba(14,16,20,0.7))',
      }}
    >
      <div className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] mb-1">
        Topology notes
      </div>
      <ul className="space-y-1">
        {points.map((pt, i) => (
          <li key={i} className="flex items-start gap-2 font-mono text-[11px] text-silver">
            <span className="text-orange mt-0.5 shrink-0">›</span>
            <span className="leading-snug">{pt}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── BottleneckList ─────────────────────────────────────────────────────────

function BottleneckList({
  items,
}: {
  items: BuildabilityIssue[];
}) {
  return (
    <div className="space-y-1.5">
      <div className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">
        ⚠ Bottlenecks
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => {
          const sevColour = severityColour(item.severity);
          return (
            <li
              key={i}
              className="flex items-start gap-2 rounded border px-3 py-1.5 font-mono text-[11px]"
              style={{ borderColor: `${sevColour}50`, backgroundColor: `${sevColour}0d` }}
            >
              <span className="shrink-0 mt-0.5 text-[10px] font-bold uppercase tracking-wide" style={{ color: sevColour }}>
                {item.severity ?? item.type}
              </span>
              <span className="text-silver leading-snug">{item.description}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─── OpportunityList ────────────────────────────────────────────────────────

function OpportunityList({
  items,
}: {
  items: BuildabilityIssue[];
}) {
  return (
    <div className="space-y-1.5">
      <div className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">
        ✦ Opportunities
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-2 rounded border border-green/30 bg-green/5 px-3 py-1.5 font-mono text-[11px]"
          >
            <span className="shrink-0 mt-0.5 text-[10px] font-bold uppercase tracking-wide text-green">
              {item.type}
            </span>
            <span className="text-silver leading-snug">{item.description}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── BuildOrderAccordion ────────────────────────────────────────────────────

function BuildOrderAccordion({
  steps,
}: {
  steps: RecommendedBuildStep[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="rounded-chunk-lg border border-border/60 overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow:  'inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
    >
      {/* Header / toggle */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-orange/5 transition-colors"
      >
        <span className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em]">
          Recommended build order
          <span className="ml-2 text-silver tabular-nums">({steps.length} steps)</span>
        </span>
        <span className={['font-mono text-orange text-sm transition-transform duration-200', open ? 'rotate-180' : ''].join(' ')}>
          ▾
        </span>
      </button>

      {/* Steps */}
      {open && (
        <div className="border-t border-border/50">
          <table className="w-full text-xs font-mono">
            <thead className="text-silver-dk uppercase tracking-[0.14em] text-[9px]"
              style={{
                background:   'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
                borderBottom: '1px solid hsl(216 10% 22%)',
              }}
            >
              <tr>
                <th className="px-3 py-2 text-left w-8">#</th>
                <th className="px-3 py-2 text-left">Facility</th>
                <th className="px-3 py-2 text-left">Loc</th>
                <th className="px-3 py-2 text-right" style={{ color: '#f5c518' }}>⬡ CP</th>
                <th className="px-3 py-2 text-right" style={{ color: '#4caf50' }}>⬡ CP</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((s) => (
                <tr key={s.step} className="border-t border-border/40 hover:bg-orange/5 transition-colors">
                  <td className="px-3 py-2 text-silver-dk tabular-nums">{s.step}</td>
                  <td className="px-3 py-2">
                    <span className="text-orange-lt font-semibold">
                      {s.facility_name ?? s.facility_id ?? '—'}
                    </span>
                    {s.notes && (
                      <span className="block text-[10px] text-silver-dk italic leading-tight mt-0.5">
                        {s.notes}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <LocationBadge location={s.location} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: '#f5c518' }}>
                    {s.cumulative_yellow_cp != null ? s.cumulative_yellow_cp : '—'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: '#4caf50' }}>
                    {s.cumulative_green_cp != null ? s.cumulative_green_cp : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 py-1.5 text-[9px] font-mono text-silver-dk border-t border-border/40">
            ⬡ = cumulative construction points after this step · placement order determines economy hierarchy
          </div>
        </div>
      )}
    </div>
  );
}

// ─── DataSourceNote ─────────────────────────────────────────────────────────

function DataSourceNote({
  source,
  confidence,
}: {
  source: BuildabilityData['source'];
  confidence?: number | null;
}) {
  const labels: Record<string, string> = {
    precomputed: 'Pre-computed — updated with topology pipeline',
    computed:    'Computed on demand from topology data',
  };
  const label = labels[source] ?? source;
  return (
    <div className="flex items-center gap-2 font-mono text-[9px] text-text-dim pt-1 border-t border-border/30">
      <span className="uppercase tracking-wide">Source</span>
      <span>{label}</span>
      {confidence != null && (
        <>
          <span className="mx-1 text-border">·</span>
          <span>Slot confidence {Math.round(confidence * 100)}%</span>
        </>
      )}
    </div>
  );
}

// ─── Skeleton ───────────────────────────────────────────────────────────────

function Buildabilityskeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="grid grid-cols-6 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-12 rounded border border-border/40 bg-bg3/30" />
        ))}
      </div>
      <div className="h-5 w-48 rounded bg-bg3/40" />
      <div className="h-20 rounded border border-border/40 bg-bg3/30" />
    </div>
  );
}

// ─── LocationBadge ──────────────────────────────────────────────────────────

function LocationBadge({ location }: { location?: string | null }) {
  if (!location) return <span className="text-text-dim">—</span>;
  const isOrbital = location === 'orbital';
  return (
    <span
      className={[
        'inline-block px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide border',
        isOrbital
          ? 'border-cyan/40 text-cyan bg-cyan/10'
          : 'border-gold/40 text-gold bg-gold/10',
      ].join(' ')}
    >
      {location}
    </span>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatArchetype(key?: string | null): string {
  if (!key) return '—';
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function confidenceColour(label?: string | null): string {
  switch (label) {
    case 'High':     return '#4caf50';  // green
    case 'Moderate': return '#f5c518';  // yellow
    case 'Low':      return '#ff9800';  // orange
    default:         return '#8c9bab';  // silver-dk
  }
}

function riskColour(v: number): string {
  const pct = riskPercent(v);
  if (pct >= 70) return '#ef5350'; // red
  if (pct >= 40) return '#ff9800'; // orange
  return '#4caf50';               // green
}

function riskPercent(v: number): number {
  const bounded = Number.isFinite(v) ? Math.max(0, v) : 0;
  const pct = bounded <= 1 ? bounded * 100 : bounded;
  return Math.min(100, Math.round(pct));
}

function severityColour(sev?: string | null): string {
  switch (sev?.toLowerCase()) {
    case 'high':     return '#ef5350';
    case 'medium':   return '#ff9800';
    case 'low':      return '#f5c518';
    default:         return '#8c9bab';
  }
}

function complexityChipStyle(complexity?: string | null): React.CSSProperties {
  switch (complexity) {
    case 'trivial':     return { borderColor: '#4caf5060', color: '#4caf50', backgroundColor: '#4caf5018' };
    case 'simple':      return { borderColor: '#8bc34a60', color: '#8bc34a', backgroundColor: '#8bc34a14' };
    case 'moderate':    return { borderColor: '#f5c51860', color: '#f5c518', backgroundColor: '#f5c51814' };
    case 'complex':     return { borderColor: '#ff980060', color: '#ff9800', backgroundColor: '#ff980014' };
    case 'very_complex':return { borderColor: '#ef535060', color: '#ef5350', backgroundColor: '#ef535014' };
    default:            return { borderColor: '#8c9bab50', color: '#8c9bab', backgroundColor: '#8c9bab10' };
  }
}
