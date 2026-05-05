import { useState } from 'react';
import type { FcConfig, UseFcPlanner } from './useFcPlanner';
import { useAutocomplete } from '@/features/search/useAutocomplete';

export interface FcPlannerTabProps {
  fc: UseFcPlanner;
  onOpenDetail?: (id64: number) => void;
}

export function FcPlannerTab({ fc, onOpenDetail }: FcPlannerTabProps) {
  const { waypoints, config, route, add, remove, move, clear, setConfig, exportCsv } = fc;
  const [query, setQuery] = useState('');
  const { hits } = useAutocomplete(query);

  const showSummary = waypoints.length >= 2 && route.legs.some((l) => l.distance_ly !== null);

  return (
    <section data-testid="fc-tab" className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">🚀 FC Route Planner</h2>
        <span className="font-mono text-xs text-text-dim">
          Tritium / hop / cost calculator for Fleet Carrier journeys
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={exportCsv}
          disabled={waypoints.length === 0}
          data-testid="fc-export"
          className="px-2 py-1 rounded bg-bg4 border border-border font-mono text-[11px] text-text-dim hover:text-orange hover:border-orange-dk disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Export CSV
        </button>
        <button
          type="button"
          onClick={() => {
            if (waypoints.length === 0) return;
            if (confirm(`Clear all ${waypoints.length} waypoints?`)) clear();
          }}
          disabled={waypoints.length === 0}
          data-testid="fc-clear"
          className="px-2 py-1 rounded bg-red/10 border border-red/40 font-mono text-[11px] text-red hover:bg-red/20 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ✕ Clear
        </button>
      </header>

      {/* Config row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded border border-border p-3">
        <ConfigInput
          label="Jump range (LY)"
          value={config.jump_range_ly}
          min={100} max={500}
          onChange={(v) => setConfig({ jump_range_ly: v })}
          testid="fc-cfg-jump"
        />
        <ConfigInput
          label="Cargo hold (t)"
          value={config.cargo_t}
          min={1_000} max={25_000}
          onChange={(v) => setConfig({ cargo_t: v })}
          testid="fc-cfg-cargo"
        />
        <ConfigInput
          label="Tritium per jump"
          value={config.tritium_per_jump}
          min={1} max={200}
          onChange={(v) => setConfig({ tritium_per_jump: v })}
          testid="fc-cfg-trit-per-jump"
        />
        <ConfigInput
          label="Tritium price (cr/t)"
          value={config.tritium_price_cr}
          min={1_000}
          onChange={(v) => setConfig({ tritium_price_cr: v })}
          testid="fc-cfg-trit-price"
        />
      </div>

      {/* Waypoint entry */}
      <div className="rounded border border-border p-3 space-y-2 relative">
        <label className="font-mono text-[11px] text-text-dim uppercase tracking-wider block">
          Add waypoint
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="fc-input"
            placeholder="System name…"
            autoComplete="off"
            className="flex-1 bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
          />
          <button
            type="button"
            onClick={() => {
              if (!query.trim()) return;
              add({ name: query.trim(), x: null, y: null, z: null, id64: null });
              setQuery('');
            }}
            disabled={!query.trim()}
            data-testid="fc-add-blind"
            className="px-3 py-1 rounded bg-bg4 border border-border font-mono text-xs text-text-dim hover:text-orange hover:border-orange-dk disabled:opacity-40 disabled:cursor-not-allowed"
            title="Add by name (coords resolved later)"
          >
            ➕ Add as-is
          </button>
        </div>
        {hits.length > 0 && (
          <ul className="absolute left-3 right-3 z-10 mt-1 max-h-60 overflow-y-auto rounded border border-border bg-bg2 shadow-2xl">
            {hits.map((h) => (
              <li key={h.id64}>
                <button
                  type="button"
                  onClick={() => {
                    add({ name: h.name, x: h.x, y: h.y, z: h.z, id64: h.id64 });
                    setQuery('');
                  }}
                  data-testid={`fc-add-hit-${h.id64}`}
                  className="w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-bg3"
                >
                  <span className="text-orange">{h.name}</span>
                  <span className="text-text-dim text-[10px] ml-2">
                    {h.x.toFixed(0)}, {h.y.toFixed(0)}, {h.z.toFixed(0)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[10px] text-text-dim">
          Pick from autocomplete to grab coords automatically. Blind-adds get
          included in the route once you re-enter them with autocomplete.
        </p>
      </div>

      {/* Summary */}
      {showSummary && (
        <div data-testid="fc-summary" className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs font-mono">
          <SummaryStat label="Hops"        value={route.total_hops.toLocaleString()} />
          <SummaryStat label="Total LY"    value={Math.round(route.total_distance_ly).toLocaleString()} />
          <SummaryStat label="Tritium (t)" value={Math.round(route.total_tritium_t).toLocaleString()} />
          <SummaryStat label="Cost (M cr)" value={(route.total_cost_cr / 1e6).toFixed(1)} highlight />
          <SummaryStat label="Cargo trips" value={route.cargo_trips.toLocaleString()} />
        </div>
      )}

      {route.missing_coord_names.length > 0 && (
        <div className="rounded border border-gold/40 bg-gold/10 p-2 font-mono text-xs text-gold">
          ⚠ Coords missing for: {route.missing_coord_names.join(', ')}.
          Re-add them via autocomplete to include in the calculation.
        </div>
      )}

      {/* Hop list */}
      {waypoints.length === 0 ? (
        <div className="text-center py-12 px-4 rounded border border-dashed border-border">
          <div className="text-3xl mb-2" aria-hidden>🚀</div>
          <h3 className="font-mono text-orange text-sm mb-1">No waypoints yet</h3>
          <p className="text-text-dim text-xs">
            Type a system name above and pick from the autocomplete.
          </p>
        </div>
      ) : (
        <ol className="space-y-1.5">
          {waypoints.map((wp, i) => {
            const leg = i > 0 ? route.legs[i - 1] : null;
            const isFirst = i === 0;
            const isLast  = i === waypoints.length - 1;
            return (
              <li
                key={wp.id}
                data-testid={`fc-wp-${wp.id}`}
                className="rounded border border-border p-2 grid grid-cols-[40px_1fr_auto_auto] items-center gap-2 bg-bg3/30"
              >
                <span className="text-text-dim text-[11px] font-mono tabular-nums text-right">
                  {i + 1}.
                </span>
                <div className="min-w-0">
                  {wp.id64 != null && onOpenDetail
                    ? (
                      <button
                        type="button"
                        onClick={() => onOpenDetail(wp.id64!)}
                        className="font-mono text-orange font-bold hover:underline truncate"
                      >
                        {wp.name}
                      </button>
                    )
                    : (
                      <span className="font-mono text-orange font-bold truncate">{wp.name}</span>
                    )
                  }
                  {leg && leg.distance_ly !== null && (
                    <span className="ml-2 text-[10px] font-mono text-text-dim tabular-nums">
                      ← {leg.distance_ly.toFixed(1)} LY · {leg.hops}h · {leg.tritium_t}t
                    </span>
                  )}
                  {wp.x === null && (
                    <span className="ml-2 text-[10px] font-mono text-gold">⚠ no coords</span>
                  )}
                </div>
                <div className="flex gap-1">
                  <IconBtn
                    label="▲"
                    disabled={isFirst}
                    onClick={() => move(wp.id, -1)}
                    testid={`fc-up-${wp.id}`}
                  />
                  <IconBtn
                    label="▼"
                    disabled={isLast}
                    onClick={() => move(wp.id, 1)}
                    testid={`fc-down-${wp.id}`}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => remove(wp.id)}
                  data-testid={`fc-remove-${wp.id}`}
                  className="px-2 py-0.5 rounded bg-red/10 border border-red/40 text-red text-[10px] font-mono hover:bg-red/20"
                >
                  ✕
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

// ─── Subcomponents ────────────────────────────────────────────────────────

function ConfigInput({
  label, value, min, max, onChange, testid,
}: {
  label: string; value: number;
  min?: number; max?: number;
  onChange: (v: number) => void;
  testid: string;
}) {
  return (
    <label className="block">
      <span className="block font-mono text-[11px] text-text-dim uppercase tracking-wider mb-1">
        {label}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
        data-testid={testid}
        className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs tabular-nums"
      />
    </label>
  );
}

function SummaryStat({ label, value, highlight }: {
  label: string; value: string; highlight?: boolean;
}) {
  return (
    <div className={[
      'rounded p-2 border text-center',
      highlight ? 'border-orange/50 bg-orange/10 text-orange'
                : 'border-border bg-bg3/40',
    ].join(' ')}>
      <div className={[
        'tabular-nums font-bold text-base',
        highlight ? 'text-orange' : 'text-text',
      ].join(' ')}>
        {value}
      </div>
      <div className="text-text-dim uppercase tracking-wider text-[10px]">
        {label}
      </div>
    </div>
  );
}

function IconBtn({ label, disabled, onClick, testid }: {
  label: string; disabled: boolean; onClick: () => void; testid: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testid}
      className="w-6 h-6 rounded border border-border bg-bg4 text-text-dim text-[10px] font-mono hover:text-orange hover:border-orange-dk disabled:opacity-30 disabled:cursor-not-allowed"
    >
      {label}
    </button>
  );
}

// Re-export so callers don't have to drill into the hook.
export type { FcConfig };
