/**
 * SlotPredictionPanel — Per-body slot prediction table
 * ======================================================
 * Renders inside the "Colony Build Analysis" section of SystemDetailModal.
 *
 * Data source: GET /api/systems/{id64}/slot-predictions
 * Shows predicted orbital + surface slots per body, confidence badges,
 * and expandable reason tooltips for each prediction.
 *
 * Design language: ED orange / brushed-steel (matches SystemDetailModal).
 */

import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { BodySlotPrediction, SlotPredictionResponse, SlotReason } from '@/types/api';

// ─── Types ──────────────────────────────────────────────────────────────────

type BodyPrediction = BodySlotPrediction;

// ─── Fetch hook ─────────────────────────────────────────────────────────────

function useSlotPredictions(id64: number) {
  return useQuery<SlotPredictionResponse, Error>({
    queryKey: ['slot-predictions', id64],
    queryFn:  () => api.slotPredictions(id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

// ─── Public component ───────────────────────────────────────────────────────

export interface SlotPredictionPanelProps {
  id64: number;
}

export function SlotPredictionPanel({ id64 }: SlotPredictionPanelProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useSlotPredictions(id64);
  const predictions = data?.predictions ?? [];

  // Collapsed header — always show, even before expand
  const headerContent = () => {
    if (isLoading) {
      return (
        <span className="font-mono text-silver-dk text-[11px] animate-pulse">
          Loading slot data…
        </span>
      );
    }
    if (isError || !data) {
      return (
        <span className="font-mono text-red text-[11px]">
          Failed to load · <button
            type="button"
            onClick={(e) => { e.stopPropagation(); void refetch(); }}
            className="underline hover:text-orange"
          >retry</button>
        </span>
      );
    }
    if (data.data_source === 'none' || predictions.length === 0) {
      return (
        <span className="font-mono text-silver-dk text-[11px] italic">
          No body scan data available
        </span>
      );
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-silver text-[11px]">
          <span className="tabular-nums text-cyan font-bold">{data.estimated_orbital_slots}</span>
          <span className="text-silver-dk"> orbital · </span>
          <span className="tabular-nums text-gold font-bold">{data.estimated_ground_slots}</span>
          <span className="text-silver-dk"> surface · </span>
          <span className="tabular-nums text-silver">{data.body_count}</span>
          <span className="text-silver-dk"> bodies scanned</span>
        </span>
        <ConfidenceBadge label={data.slot_confidence_label} />
        <DataSourceBadge source={data.data_source} />
      </div>
    );
  };

  return (
    <div
      className="rounded-chunk-lg border border-border/60 overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow:  'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}
    >
      {/* ── Collapsible header ────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!data || predictions.length === 0}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-orange/5 disabled:cursor-default transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] shrink-0">
            Per-body slot predictions
          </span>
          {headerContent()}
        </div>
        {data && predictions.length > 0 && (
          <span
            className={[
              'font-mono text-orange text-sm transition-transform duration-200 ml-3 shrink-0',
              open ? 'rotate-180' : '',
            ].join(' ')}
          >
            ▾
          </span>
        )}
      </button>

      {/* ── Expanded table ────────────────────────────────────────────── */}
      {open && data && predictions.length > 0 && (
        <div className="border-t border-border/50">
          <PredictionTable predictions={predictions} />
          {data.note && (
            <div className="px-3 py-2 font-mono text-[10px] text-silver-dk border-t border-border/40 italic leading-snug">
              {data.note}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── PredictionTable ────────────────────────────────────────────────────────

function PredictionTable({ predictions }: { predictions: BodyPrediction[] }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  return (
    <table className="w-full text-xs font-mono">
      <thead
        className="text-silver-dk uppercase tracking-[0.14em] text-[9px]"
        style={{
          background:   'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
          borderBottom: '1px solid hsl(216 10% 22%)',
        }}
      >
        <tr>
          <th className="px-3 py-2 text-left">Body</th>
          <th className="px-3 py-2 text-left">Class</th>
          <th className="px-3 py-2 text-center">Tags</th>
          <th className="px-3 py-2 text-right text-cyan">Orbital</th>
          <th className="px-3 py-2 text-right text-gold">Surface</th>
          <th className="px-3 py-2 text-center">Conf.</th>
          <th className="px-3 py-2 text-center">Reasons</th>
        </tr>
      </thead>
      <tbody>
        {predictions.map((p) => {
          const isExpanded = expandedId === p.body_id;
          return (
            <Fragment key={p.body_id}>
              <tr
                className="border-t border-border/40 hover:bg-orange/5 transition-colors cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : p.body_id)}
              >
                {/* Body name */}
                <td className="px-3 py-2 text-orange-lt font-semibold max-w-[140px] truncate">
                  {shortBodyName(p.body_name)}
                </td>

                {/* Planet class */}
                <td className="px-3 py-2 text-silver max-w-[120px]">
                  <span className="truncate block">{abbreviateClass(p.planet_class)}</span>
                </td>

                {/* Body tags */}
                <td className="px-3 py-2 text-center">
                  <BodyTagRow pred={p} />
                </td>

                {/* Orbital slots */}
                <td className="px-3 py-2 text-right tabular-nums text-cyan font-bold">
                  {p.estimated_orbital_slots > 0 ? p.estimated_orbital_slots : <span className="text-text-dim font-normal">—</span>}
                </td>

                {/* Surface slots */}
                <td className="px-3 py-2 text-right tabular-nums text-gold font-bold">
                  {p.estimated_surface_slots > 0 ? p.estimated_surface_slots : <span className="text-text-dim font-normal">—</span>}
                </td>

                {/* Confidence */}
                <td className="px-3 py-2 text-center">
                  <ConfidencePip value={p.slot_confidence} />
                </td>

                {/* Reasons toggle */}
                <td className="px-3 py-2 text-center">
                  {p.reasons && p.reasons.length > 0 ? (
                    <span className={['text-[10px]', isExpanded ? 'text-orange' : 'text-silver-dk'].join(' ')}>
                      {isExpanded ? '▲' : `▾ ${p.reasons.length}`}
                    </span>
                  ) : (
                    <span className="text-border">—</span>
                  )}
                </td>
              </tr>

              {/* Expanded reasons row */}
              {isExpanded && p.reasons && p.reasons.length > 0 && (
                <tr key={`${p.body_id}-reasons`} className="border-t border-orange/10 bg-orange/5">
                  <td colSpan={7} className="px-4 py-2">
                    <ReasonList reasons={p.reasons} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── ReasonList ─────────────────────────────────────────────────────────────

function ReasonList({ reasons }: { reasons: SlotReason[] }) {
  return (
    <ul className="space-y-1">
      {reasons.map((r, i) => (
        <li key={i} className="flex items-start gap-2 font-mono text-[10px]">
          <span className="text-orange shrink-0 mt-0.5">›</span>
          <span className="text-silver-dk uppercase tracking-wide shrink-0">{r.factor}</span>
          {r.delta != null && r.delta !== 0 && (
            <span
              className={['tabular-nums font-bold shrink-0', r.delta > 0 ? 'text-green' : 'text-red'].join(' ')}
            >
              {r.delta > 0 ? `+${r.delta}` : r.delta}
            </span>
          )}
          {r.note && <span className="text-silver italic leading-tight">{r.note}</span>}
        </li>
      ))}
    </ul>
  );
}

// ─── BodyTagRow ─────────────────────────────────────────────────────────────

function BodyTagRow({ pred }: { pred: BodyPrediction }) {
  const tags: string[] = [];
  if (pred.is_ringed)   tags.push('⊙');   // ringed
  if (pred.is_landable) tags.push('⬇');   // landable
  if (tags.length === 0) return <span className="text-border">—</span>;
  return (
    <span className="text-silver-dk text-[10px] tracking-widest">{tags.join(' ')}</span>
  );
}

// ─── ConfidenceBadge ────────────────────────────────────────────────────────

function ConfidenceBadge({ label }: { label: string }) {
  const colour = confidenceColour(label);
  return (
    <span
      className="px-1.5 py-0.5 rounded border font-mono text-[9px] font-bold uppercase tracking-wide"
      style={{ borderColor: `${colour}60`, color: colour, backgroundColor: `${colour}18` }}
    >
      {label}
    </span>
  );
}

// ─── ConfidencePip ──────────────────────────────────────────────────────────

function ConfidencePip({ value }: { value: number }) {
  const pct   = Math.round(value * 100);
  const colour = value >= 0.85 ? '#4caf50' : value >= 0.65 ? '#f5c518' : value >= 0.45 ? '#ff9800' : '#8c9bab';
  return (
    <span
      className="inline-block px-1.5 py-0.5 rounded font-mono text-[9px] tabular-nums font-bold border"
      style={{ borderColor: `${colour}50`, color: colour, backgroundColor: `${colour}15` }}
      title={`${pct}% confidence`}
    >
      {pct}%
    </span>
  );
}

// ─── DataSourceBadge ────────────────────────────────────────────────────────

function DataSourceBadge({ source }: { source: 'eddn' | 'spansh' | 'none' }) {
  const map: Record<string, { label: string; colour: string }> = {
    eddn:   { label: 'EDDN', colour: '#4caf50' },
    spansh: { label: 'Spansh', colour: '#f5c518' },
    none:   { label: 'No data', colour: '#8c9bab' },
  };
  const { label, colour } = map[source] ?? map.none;
  return (
    <span
      className="px-1.5 py-0.5 rounded border font-mono text-[9px] uppercase tracking-wide"
      style={{ borderColor: `${colour}50`, color: colour, backgroundColor: `${colour}12` }}
    >
      {label}
    </span>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function confidenceColour(label: string): string {
  switch (label) {
    case 'High':      return '#4caf50';
    case 'Moderate':  return '#f5c518';
    case 'Low':       return '#ff9800';
    default:          return '#8c9bab';
  }
}

/** Strip the system name prefix from body names (e.g. "Colonia 1 a" → "1 a") */
function shortBodyName(name?: string | null): string {
  if (!name) return '—';
  // Body names in ED follow pattern "<System> <body designator>"
  // We show the full name but truncate long system-name prefixes
  const parts = name.trim().split(' ');
  // If ≤3 words it's already short
  if (parts.length <= 3) return name;
  // Return last 2 tokens (body designator usually 1-2 tokens)
  return parts.slice(-2).join(' ');
}

const CLASS_ABBREV: Record<string, string> = {
  'High metal content body':         'HMC',
  'Rocky body':                      'Rocky',
  'Rocky ice body':                  'Rocky Ice',
  'Icy body':                        'Icy',
  'Metal rich body':                 'Metal Rich',
  'Earth-like world':                'ELW',
  'Water world':                     'Water World',
  'Ammonia world':                   'Ammonia',
  'Gas giant with water-based life': 'GG Water',
  'Gas giant with ammonia-based life':'GG Ammonia',
  'Class I gas giant':               'GG-I',
  'Class II gas giant':              'GG-II',
  'Class III gas giant':             'GG-III',
  'Class IV gas giant':              'GG-IV',
  'Class V gas giant':               'GG-V',
  'Sudarsky class I gas giant':      'GG-I',
  'Sudarsky class II gas giant':     'GG-II',
  'Sudarsky class III gas giant':    'GG-III',
  'Sudarsky class IV gas giant':     'GG-IV',
  'Sudarsky class V gas giant':      'GG-V',
  'Helium-rich gas giant':           'GG He',
  'Helium gas giant':                'GG He',
  'Water giant':                     'Water GG',
};

function abbreviateClass(cls?: string | null): string {
  if (!cls) return '—';
  return CLASS_ABBREV[cls] ?? cls;
}
