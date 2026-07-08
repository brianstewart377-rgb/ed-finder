import { useState } from 'react';
import type { FcConfig, UseFcPlanner } from './useFcPlanner';
import { useAutocomplete } from '@/features/search/useAutocomplete';
import { formatCoords } from '@/lib/format';
import { ReviewWorkspaceHeader, type ReviewSelectedSystem } from '@/components/ReviewWorkspaceHeader';

export interface FcPlannerTabProps {
  fc: UseFcPlanner;
  onOpenDetail?: (id64: number) => void;
  selectedSystem?: ReviewSelectedSystem | null;
}

export function FcPlannerTab({ fc, onOpenDetail, selectedSystem = null }: FcPlannerTabProps) {
  const { waypoints, config, route, add, remove, move, clear, setConfig, exportCsv } = fc;
  const [query, setQuery] = useState('');
  const { hits } = useAutocomplete(query);

  const showSummary = waypoints.length >= 2 && route.legs.some((l) => l.distance_ly !== null);

  return (
    <section data-testid="fc-tab" className="space-y-5">
      <ReviewWorkspaceHeader
        testId="fc-workspace-header"
        title="FC Route Planner"
        supportingText="Review Fleet Carrier waypoint plans while the selected-system context remains visible as player-journey reference, not route authority."
        selectedSystem={selectedSystem}
        facts={[
          {
            label: 'Waypoints',
            value: String(waypoints.length),
            tone: waypoints.length > 0 ? 'cyan' : 'default',
          },
        ]}
        actions={(
          <>
            <button
              type="button"
              onClick={exportCsv}
              disabled={waypoints.length === 0}
              data-testid="fc-export"
              className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
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
              className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20 font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ✕ Clear
            </button>
          </>
        )}
      />

      {/* Config row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 panel-thin p-4">
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
      <div className="panel-thin p-4 space-y-2 relative">
        <label className="font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] block">
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
            className="flex-1 font-mono text-xs"
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
            className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
            title="Add by name (coords resolved later)"
          >
            ➕ Add as-is
          </button>
        </div>
        {hits.length > 0 && (
          <ul className="absolute left-3 right-3 z-10 mt-1 max-h-60 overflow-y-auto panel">
            {hits.map((h) => (
              <li key={h.id64}>
                <button
                  type="button"
                  onClick={() => {
                    add({ name: h.name, x: h.x ?? null, y: h.y ?? null, z: h.z ?? null, id64: h.id64 });
                    setQuery('');
                  }}
                  data-testid={`fc-add-hit-${h.id64}`}
                  className="w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-orange/10 transition-colors"
                >
                  <span className="text-orange-lt">{h.name}</span>
                  <span className="text-silver-dk text-[10px] ml-2">
                    {formatCoords(h, h.id64)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[10px] text-silver-dk">
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
        <div className="panel-thin border-gold/40 p-2.5 font-mono text-xs text-gold" style={{ background: 'rgba(251,191,36,0.10)' }}>
          ⚠ Coords missing for: {route.missing_coord_names.join(', ')}.
          Re-add them via autocomplete to include in the calculation.
        </div>
      )}

      {/* Hop list */}
      {waypoints.length === 0 ? (
        <div className="panel-thin text-center py-12 px-4">
          <div className="text-3xl mb-2" aria-hidden>🚀</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No waypoints yet</h3>
          <p className="text-silver-dk text-xs">
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
                className="panel-thin p-3 grid grid-cols-[44px_1fr_auto_auto] items-center gap-2.5 hover:border-orange/40 transition-colors"
              >
                <span className="text-silver-dk text-[11px] font-mono tabular-nums text-right">
                  {i + 1}.
                </span>
                <div className="min-w-0">
                  {wp.id64 != null && onOpenDetail
                    ? (
                      <button
                        type="button"
                        onClick={() => onOpenDetail(wp.id64!)}
                        className="font-mono text-orange-lt font-bold hover:underline truncate"
                      >
                        {wp.name}
                      </button>
                    )
                    : (
                      <span className="font-mono text-orange-lt font-bold truncate">{wp.name}</span>
                    )
                  }
                  {leg && leg.distance_ly !== null && (
                    <span className="ml-2 text-[10px] font-mono text-silver-dk tabular-nums">
                      ← {leg.distance_ly.toFixed(1)} LY · {leg.hops}h · {leg.tritium_t}t
                    </span>
                  )}
                  {wp.x === null && (
                    <span className="ml-2 text-[10px] font-mono text-gold">⚠ no coords</span>
                  )}
                </div>
                <div className="flex gap-1.5">
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
                  className="px-2.5 py-1 rounded-chunk-sm bg-red/10 border border-red/40 text-red text-[10px] font-mono hover:bg-red/20 transition-colors"
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
      <span className="block font-mono text-[10px] text-silver-dk uppercase tracking-[0.18em] mb-1.5">
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
        className="w-full font-mono text-xs tabular-nums"
      />
    </label>
  );
}

function SummaryStat({ label, value, highlight }: {
  label: string; value: string; highlight?: boolean;
}) {
  return (
    <div
      className={[
        'rounded-chunk-sm p-3 text-center transition-colors',
        highlight
          ? 'border border-orange/55 text-orange'
          : 'panel-thin',
      ].join(' ')}
      style={highlight
        ? {
            background: 'linear-gradient(180deg, rgba(255,122,20,0.18) 0%, rgba(255,122,20,0.06) 100%)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 0 18px -8px rgba(255,122,20,0.55)',
          }
        : undefined}
    >
      <div className={[
        'tabular-nums font-bold text-base font-display',
        highlight ? 'text-orange-lt' : 'text-silver',
      ].join(' ')}>
        {value}
      </div>
      <div className="text-silver-dk uppercase tracking-[0.16em] text-[10px] mt-0.5">
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
      className="w-7 h-7 rounded-chunk-sm border border-border bg-gradient-to-b from-bg4 to-bg3 text-silver-dk text-[11px] font-mono hover:text-orange-lt hover:border-orange-dk transition-colors disabled:opacity-30 disabled:cursor-not-allowed shadow-metal"
    >
      {label}
    </button>
  );
}

// Re-export so callers don't have to drill into the hook.
export type { FcConfig };
