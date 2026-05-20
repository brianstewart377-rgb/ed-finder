import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { BodySlotPrediction, SlotPredictionResponse, SlotReason } from '@/types/api';

type BodyPrediction = BodySlotPrediction;

function useSlotPredictions(id64: number) {
  return useQuery<SlotPredictionResponse, Error>({
    queryKey: ['slot-predictions', id64],
    queryFn: () => api.slotPredictions(id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export interface SlotPredictionPanelProps {
  id64: number;
}

export function SlotPredictionPanel({ id64 }: SlotPredictionPanelProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useSlotPredictions(id64);
  const predictions = data?.predictions ?? [];

  const orbitalTotal = data?.predicted_orbital_slots_total ?? null;
  const groundTotal = data?.predicted_ground_slots_total ?? null;

  const headerContent = () => {
    if (isLoading) {
      return <span className="font-mono text-silver-dk text-[11px] animate-pulse">Loading slot data…</span>;
    }
    if (isError || !data) {
      return (
        <span className="font-mono text-red text-[11px]">
          Failed to load ·{' '}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              void refetch();
            }}
            className="underline hover:text-orange"
          >
            retry
          </button>
        </span>
      );
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-silver text-[11px]">
          <span className="tabular-nums text-cyan font-bold">{slotLabel(orbitalTotal)}</span>
          <span className="text-silver-dk"> orbital · </span>
          <span className="tabular-nums text-gold font-bold">{slotLabel(groundTotal)}</span>
          <span className="text-silver-dk"> ground · </span>
          <span className="tabular-nums text-silver">{data.body_count}</span>
          <span className="text-silver-dk"> bodies</span>
        </span>
        <StatusBadge status={data.prediction_status} />
      </div>
    );
  };

  return (
    <div
      className="rounded-chunk-lg border border-border/60 overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
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
          <span className={['font-mono text-orange text-sm transition-transform duration-200 ml-3 shrink-0', open ? 'rotate-180' : ''].join(' ')}>
            ▾
          </span>
        )}
      </button>

      {open && data && predictions.length > 0 && (
        <div className="border-t border-border/50">
          <div className="px-3 py-2 border-b border-border/40 font-mono text-[10px] text-silver-dk">
            <div className="text-silver">{data.disclaimer}</div>
            <div className="mt-1 italic">{data.validation_note}</div>
            {data.prediction_status === 'unknown' && (
              <div className="mt-1 text-gold">{data.note ?? 'insufficient prediction data. verify in Architect Mode.'}</div>
            )}
          </div>
          <PredictionTable predictions={predictions} />
        </div>
      )}
    </div>
  );
}

function PredictionTable({ predictions }: { predictions: BodyPrediction[] }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  return (
    <table className="w-full text-xs font-mono">
      <thead className="text-silver-dk uppercase tracking-[0.14em] text-[9px]" style={{ background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))', borderBottom: '1px solid hsl(216 10% 22%)' }}>
        <tr>
          <th className="px-3 py-2 text-left">Body</th>
          <th className="px-3 py-2 text-left">Class</th>
          <th className="px-3 py-2 text-right text-cyan">Orbital</th>
          <th className="px-3 py-2 text-right text-gold">Ground</th>
          <th className="px-3 py-2 text-center">Status</th>
          <th className="px-3 py-2 text-center">Reasons</th>
        </tr>
      </thead>
      <tbody>
        {predictions.map((prediction) => {
          const isExpanded = expandedId === prediction.body_id;
          return (
            <Fragment key={prediction.body_id}>
              <tr
                className="border-t border-border/40 hover:bg-orange/5 transition-colors cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : prediction.body_id)}
              >
                <td className="px-3 py-2 text-orange-lt font-semibold max-w-[140px] truncate">
                  {shortBodyName(prediction.body_name)}
                </td>
                <td className="px-3 py-2 text-silver max-w-[140px]">
                  <span className="truncate block">{abbreviateClass(prediction.planet_class)}</span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-cyan font-bold">{slotLabel(prediction.predicted_orbital_slots ?? null)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gold font-bold">{slotLabel(prediction.predicted_ground_slots ?? null)}</td>
                <td className="px-3 py-2 text-center">
                  <StatusBadge status={prediction.prediction_status} compact />
                </td>
                <td className="px-3 py-2 text-center">
                  {(prediction.reasons?.length ?? 0) > 0 ? (
                    <span className={['text-[10px]', isExpanded ? 'text-orange' : 'text-silver-dk'].join(' ')}>{isExpanded ? '▲' : `▾ ${prediction.reasons?.length ?? 0}`}</span>
                  ) : (
                    <span className="text-border">—</span>
                  )}
                </td>
              </tr>
              {isExpanded && (prediction.reasons?.length ?? 0) > 0 && (
                <tr className="border-t border-orange/10 bg-orange/5">
                  <td colSpan={6} className="px-4 py-2">
                    <ReasonList reasons={prediction.reasons ?? []} missingInputs={prediction.required_input_missing ?? []} />
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

function ReasonList({ reasons, missingInputs }: { reasons: SlotReason[]; missingInputs: string[] }) {
  return (
    <ul className="space-y-1">
      {reasons.map((reason, index) => (
        <li key={index} className="flex items-start gap-2 font-mono text-[10px]">
          <span className="text-orange shrink-0 mt-0.5">›</span>
          <span className="text-silver-dk uppercase tracking-wide shrink-0">{reason.factor}</span>
          {reason.delta != null && reason.delta !== 0 && (
            <span className={['tabular-nums font-bold shrink-0', reason.delta > 0 ? 'text-green' : 'text-red'].join(' ')}>
              {reason.delta > 0 ? `+${reason.delta}` : reason.delta}
            </span>
          )}
          {reason.note && <span className="text-silver italic leading-tight">{reason.note}</span>}
        </li>
      ))}
      {missingInputs.length > 0 && (
        <li className="flex items-start gap-2 font-mono text-[10px] text-gold">
          <span className="shrink-0 mt-0.5">!</span>
          <span>Missing inputs: {missingInputs.join(', ')}</span>
        </li>
      )}
    </ul>
  );
}

function StatusBadge({ status, compact = false }: { status: 'predicted' | 'unknown' | 'observed'; compact?: boolean }) {
  const style = status === 'predicted'
    ? { border: 'border-green/40', bg: 'bg-green/15', text: 'text-green', label: compact ? 'P' : 'predicted' }
    : status === 'observed'
      ? { border: 'border-cyan/40', bg: 'bg-cyan/15', text: 'text-cyan', label: compact ? 'O' : 'observed' }
      : { border: 'border-gold/40', bg: 'bg-gold/15', text: 'text-gold', label: compact ? '?' : 'unknown' };
  return (
    <span className={['rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em]', style.border, style.bg, style.text].join(' ')}>
      {style.label}
    </span>
  );
}

function slotLabel(value: number | null | undefined): string {
  return value == null ? '?' : String(value);
}

function shortBodyName(name?: string | null): string {
  if (!name) return 'Unknown body';
  const parts = name.trim().split(' ');
  if (parts.length <= 3) return name;
  return parts.slice(-3).join(' ');
}

function abbreviateClass(planetClass?: string | null): string {
  if (!planetClass) return '—';
  return planetClass
    .replace('High metal content body', 'HMC')
    .replace('High metal content world', 'HMC')
    .replace('Rocky ice body', 'Rocky-Ice')
    .replace('Earth-like world', 'ELW')
    .replace('Water world', 'WW');
}
