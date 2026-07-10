// All secondary-tab workspaces — Watchlist / Pinned / Compare / Advanced Search Tuning / Admin
// Brought up to iteration-3 aesthetic: chunky brushed-steel panels, SectionPanel
// containers, orange-pill sliders, dismissible briefing pattern matching Finder.
import React, { useState } from 'react';
import {
  Eye, Pin, Scale, Sliders, Settings, Database,
  Activity, Trash2, Bell, Server, Zap,
} from 'lucide-react';
import {
  Panel, PanelHeader, SectionPanel, SectionLabel, Readout,
  HudButton, RatingBar, TierPill,
} from '../UI/Hud';
import { SystemRow } from '../Discover/SystemRow';
import { SystemDrawer } from '../Discover/SystemDrawer';
import { SYSTEMS, ratingTier, ECON_COLORS } from '../../lib/mockData';

// ── Reusable: grid that adapts to whether a row is selected ──
function withBrief(selected) {
  return selected
    ? 'grid-cols-[minmax(0,1fr)_380px]'
    : 'grid-cols-[minmax(0,1fr)]';
}

// ════════════════════════════════════════════════════════════════
// WATCHLIST  ·  saved systems with EDDN-driven changelog
// ════════════════════════════════════════════════════════════════
const RECENT_CHANGES = [
  { sys: 'Wregoe XX-1 b48-2', delta: 'score 84 → 89', reason: 'new ELW discovered',  when: '2h ago',  tier: 'good' },
  { sys: 'HIP 22460',          delta: 'station added',  reason: 'KaelOrbital docked',  when: '7h ago',  tier: 'info' },
  { sys: 'Pleiades RX-K',      delta: 'bio +6',         reason: 'EDDN scan',           when: '14h ago', tier: 'info' },
  { sys: 'Synuefe IB-S c19',   delta: 'pop +1.2M',      reason: 'colonisation tick',   when: '22h ago', tier: 'warn' },
];

export function WatchlistTab() {
  const [selected, setSelected] = useState(null);
  const [watched, setWatched]   = useState(new Set([1001, 1002, 1003, 1004]));
  const watchlist = SYSTEMS.filter((s) => watched.has(s.id64));

  const toggleWatch = (id) => setWatched((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  return (
    <div className={`flex-1 grid ${selected ? 'grid-cols-[minmax(0,1fr)_320px_380px]' : 'grid-cols-[minmax(0,1fr)_320px]'} gap-3 p-3 min-h-0 transition-[grid-template-columns] duration-300 ease-out`}>
      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Eye size={14} strokeWidth={1.6} />}
          title={`WATCHLIST · ${watchlist.length}`}
          sub="Live EDDN diffs · server-saved"
          right={<HudButton size="sm" icon={Bell}>ALERTS</HudButton>}
        />
        <div className="flex-1 overflow-y-auto divide-y divide-[hsla(232,22%,55%,0.15)]">
          {watchlist.map((s, i) => (
            <SystemRow
              key={s.id64} system={s} index={i}
              selected={selected?.id64 === s.id64}
              watched={true}
              onSelect={setSelected}
              onWatch={toggleWatch}
              onCompare={() => {}}
            />
          ))}
        </div>
      </Panel>

      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader title="RECENT CHANGES" sub="Last 24h · live feed" />
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {RECENT_CHANGES.map((c, i) => {
            const tierColor = c.tier === 'good' ? 'var(--rate-good)'
                            : c.tier === 'warn' ? 'var(--ed-amber)'
                            : 'var(--info)';
            return (
              <div key={i} className="section-panel">
                <div className="px-3 py-2.5">
                  <div
                    className="font-display text-[10px] tracking-[0.12em] mb-0.5"
                    style={{ color: tierColor }}
                  >
                    {c.sys}
                  </div>
                  <div className="font-mono text-[11px] text-[var(--steel-100)]">{c.delta}</div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="font-mono text-[9px] text-[var(--steel-400)]">{c.reason}</span>
                    <span className="font-mono text-[9px] text-[var(--steel-500)]">{c.when}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      {selected && (
        <SystemDrawer
          system={selected}
          watched={watched.has(selected.id64)}
          onClose={() => setSelected(null)}
          onWatch={toggleWatch}
        />
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// PINNED  ·  local-storage snapshots
// ════════════════════════════════════════════════════════════════
export function PinnedTab() {
  const [selected, setSelected] = useState(null);
  const pinned = SYSTEMS.slice(2, 5);

  return (
    <div className={`flex-1 grid ${withBrief(selected)} gap-3 p-3 min-h-0 transition-[grid-template-columns] duration-300 ease-out`}>
      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Pin size={14} strokeWidth={1.6} />}
          title={`PINNED · ${pinned.length}`}
          sub="Local snapshots · click to brief"
          right={<HudButton size="sm" icon={Trash2}>CLEAR ALL</HudButton>}
        />
        <div className="flex-1 overflow-y-auto divide-y divide-[hsla(232,22%,55%,0.15)]">
          {pinned.map((s, i) => (
            <SystemRow
              key={s.id64} system={s} index={i}
              selected={selected?.id64 === s.id64}
              watched={false}
              onSelect={setSelected}
              onWatch={() => {}}
              onCompare={() => {}}
            />
          ))}
        </div>
      </Panel>

      {selected && (
        <SystemDrawer
          system={selected} watched={false}
          onClose={() => setSelected(null)}
          onWatch={() => {}}
        />
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// COMPARE  ·  side-by-side matrix with overlaid radars
// ════════════════════════════════════════════════════════════════
export function CompareTab() {
  const cols = SYSTEMS.slice(0, 3);
  const axes = Object.keys(cols[0].breakdown);
  return (
    <div className="flex-1 p-3 min-h-0">
      <Panel className="h-full overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Scale size={14} strokeWidth={1.6} />}
          title={`COMPARE · ${cols.length} SYSTEMS`}
          sub="Side-by-side · winners highlighted"
          right={<HudButton size="sm" icon={Trash2}>REMOVE ALL</HudButton>}
        />
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* Header strip per system */}
          <div className="grid gap-3" style={{ gridTemplateColumns: `180px repeat(${cols.length}, 1fr)` }}>
            <div />
            {cols.map((s) => {
              const tier = ratingTier(s.score);
              return (
                <div key={s.id64} className="section-panel">
                  <div className="section-panel-header">
                    <span className="font-display text-[11px] tracking-[0.1em] text-[var(--steel-100)] truncate flex-1">
                      {s.name}
                    </span>
                  </div>
                  <div className="px-3 py-2.5 flex items-center justify-between">
                    <TierPill score={s.score} tier={tier} />
                    <span className="font-mono text-[10px] text-[var(--steel-400)]">{s.distance.toFixed(1)} LY</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Economy axes — winner per axis highlighted */}
          <SectionPanel
            icon={<Database size={13} strokeWidth={1.8} />}
            title="ECONOMY BREAKDOWN"
          >
            <div className="space-y-2">
              {axes.map((axis) => {
                const max = Math.max(...cols.map((c) => c.breakdown[axis]));
                return (
                  <div
                    key={axis}
                    className="grid gap-3 items-center"
                    style={{ gridTemplateColumns: `180px repeat(${cols.length}, 1fr)` }}
                  >
                    <div className="font-mono text-[10px] text-[var(--steel-400)] uppercase tracking-wider">{axis}</div>
                    {cols.map((s) => {
                      const v = s.breakdown[axis];
                      const isWin = v === max;
                      return (
                        <div
                          key={s.id64}
                          className={[
                            'rounded-lg px-3 py-2 border transition-all',
                            isWin
                              ? 'border-[hsla(22,100%,50%,0.55)] bg-[hsla(22,100%,50%,0.10)] shadow-[0_0_12px_hsla(22,100%,50%,0.2)]'
                              : 'border-[hsla(232,22%,55%,0.25)] bg-[hsla(232,18%,18%,0.45)]',
                          ].join(' ')}
                        >
                          <RatingBar score={v} color={ECON_COLORS[axis] || 'var(--ed-orange)'} size="sm" />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </SectionPanel>

          {/* Rationale row */}
          <SectionPanel
            icon={<Activity size={13} strokeWidth={1.8} />}
            title="RATIONALE"
          >
            <div className="grid gap-3" style={{ gridTemplateColumns: `180px repeat(${cols.length}, 1fr)` }}>
              <div />
              {cols.map((s) => (
                <p key={s.id64} className="text-[11px] text-[var(--steel-300)] italic leading-snug">
                  {s.rationale}
                </p>
              ))}
            </div>
          </SectionPanel>
        </div>
      </Panel>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// ADVANCED SEARCH TUNING  ·  weight-tuned Finder-result re-rank with proper sliders
// ════════════════════════════════════════════════════════════════
const WEIGHT_DEFS = [
  { key: 'economy',     label: 'Economy match',     def: 30 },
  { key: 'slots',       label: 'Build slots',       def: 20 },
  { key: 'strategic',   label: 'Strategic value',   def: 15 },
  { key: 'safety',      label: 'Orbital safety',    def: 15 },
  { key: 'terraforming',label: 'Terraforming',      def: 10 },
  { key: 'diversity',   label: 'Body diversity',    def: 10 },
];

export function SearchTuningTab() {
  const [weights, setWeights] = useState(
    Object.fromEntries(WEIGHT_DEFS.map((w) => [w.key, w.def]))
  );
  const [selected, setSelected] = useState(null);
  const setW = (k, v) => setWeights((w) => ({ ...w, [k]: v }));
  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <div className={`flex-1 grid ${selected ? 'grid-cols-[340px_minmax(0,1fr)_380px]' : 'grid-cols-[340px_minmax(0,1fr)]'} gap-3 p-3 min-h-0 transition-[grid-template-columns] duration-300 ease-out`}>
      {/* Weights panel */}
      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Sliders size={14} strokeWidth={1.6} />}
          title="ADVANCED SEARCH TUNING"
          sub={`Total ${total}% · tunes current Finder results only`}
          right={<HudButton size="sm" icon={Zap} active>RUN</HudButton>}
        />
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
          <SectionPanel
            icon={<Sliders size={13} strokeWidth={1.8} />}
            title="SCORING WEIGHTS"
          >
            <div className="space-y-3.5">
              {WEIGHT_DEFS.map((w) => {
                const val = weights[w.key];
                const pct = val;
                return (
                  <div key={w.key} className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="font-display text-[10px] tracking-[0.16em] text-[var(--steel-200)]">
                        {w.label}
                      </label>
                      <span className="font-mono text-[12px] text-[var(--ed-orange-lt)] text-glow-orange tabular-nums">
                        {val}%
                      </span>
                    </div>
                    <input
                      type="range"
                      className="slider-single"
                      min={0} max={100}
                      value={val}
                      onChange={(e) => setW(w.key, Number(e.target.value))}
                      style={{ '--val': `${pct}%` }}
                    />
                  </div>
                );
              })}
            </div>
          </SectionPanel>

          <SectionPanel
            icon={<Activity size={13} strokeWidth={1.8} />}
            title="PRESETS"
            defaultOpen={false}
          >
            <div className="grid grid-cols-2 gap-2">
              {['Balanced', 'Economy first', 'Safety first', 'Pioneer'].map((p) => (
                <button
                  key={p}
                  className="px-2.5 py-2 rounded-lg border border-[hsla(232,22%,55%,0.28)] bg-[hsla(232,18%,18%,0.45)] hover:border-[hsla(232,30%,70%,0.4)] font-display text-[10px] tracking-[0.1em] text-[var(--steel-200)] hover:text-[var(--steel-100)]"
                >
                  {p}
                </button>
              ))}
            </div>
          </SectionPanel>
        </div>
      </Panel>

      {/* Re-ranked results */}
      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Activity size={14} strokeWidth={1.6} />}
          title="TUNED FINDER RESULTS"
          sub="Advanced Search Tuning does not generate colony build plans"
        />
        <div className="flex-1 overflow-y-auto divide-y divide-[hsla(232,22%,55%,0.15)]">
          {SYSTEMS.map((s, i) => (
            <SystemRow
              key={s.id64} system={s} index={i}
              selected={selected?.id64 === s.id64}
              watched={false}
              onSelect={setSelected}
              onWatch={() => {}}
              onCompare={() => {}}
            />
          ))}
        </div>
      </Panel>

      {selected && (
        <SystemDrawer
          system={selected} watched={false}
          onClose={() => setSelected(null)}
          onWatch={() => {}}
        />
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// ADMIN  ·  ops console (token-gated stub)
// ════════════════════════════════════════════════════════════════
export function AdminTab() {
  return (
    <div className="flex-1 p-3 min-h-0">
      <Panel className="h-full overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Settings size={14} strokeWidth={1.6} />}
          title="ADMIN · OPS CONSOLE"
          sub="Token-gated · authenticated as ROOT"
          right={<Readout size="sm">SECURE · TLS</Readout>}
        />
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <SectionPanel
            icon={<Database size={13} strokeWidth={1.8} />}
            title="DATABASE STATS"
          >
            <div className="grid grid-cols-4 gap-3">
              {[
                ['SYSTEMS',   '186.2M'],
                ['BODIES',    '1.28B'],
                ['CACHE HIT', '94.2%'],
                ['EDDN/HR',   '14.3K'],
              ].map(([l, v]) => (
                <div key={l} className="readout px-3 py-3 text-center">
                  <div className="font-mono text-[9px] text-[var(--steel-500)] uppercase tracking-wider mb-1">{l}</div>
                  <div className="font-display text-[20px] tracking-[0.06em] text-[var(--ed-orange-lt)] tabular-nums text-glow-orange">{v}</div>
                </div>
              ))}
            </div>
          </SectionPanel>

          <SectionPanel
            icon={<Server size={13} strokeWidth={1.8} />}
            title="LIVE METRICS"
          >
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Postgres latency p95', '12.4ms', 'good'],
                ['Redis hit ratio',      '94.2%',  'good'],
                ['EDDN consumer lag',    '0.3s',   'good'],
                ['Cluster build queue',  '14 jobs','warn'],
                ['Free disk',            '412 GB', 'good'],
                ['Memory pressure',      '38%',    'good'],
              ].map(([l, v, t]) => {
                const c = t === 'warn' ? 'var(--ed-amber)' : 'var(--rate-good)';
                return (
                  <div key={l} className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-[hsla(232,22%,18%,0.55)] border border-[hsla(232,22%,55%,0.25)]">
                    <span className="font-mono text-[11px] text-[var(--steel-300)]">{l}</span>
                    <span className="font-mono text-[12px] tabular-nums" style={{ color: c, textShadow: `0 0 6px ${c}66` }}>{v}</span>
                  </div>
                );
              })}
            </div>
          </SectionPanel>

          <SectionPanel
            icon={<Zap size={13} strokeWidth={1.8} />}
            title="ACTIONS"
          >
            <div className="flex flex-wrap gap-2">
              <HudButton>CLEAR CACHE</HudButton>
              <HudButton>REBUILD CLUSTERS</HudButton>
              <HudButton>FORCE EDDN RECONNECT</HudButton>
              <HudButton>RESEED RATINGS</HudButton>
              <HudButton>EXPORT TELEMETRY</HudButton>
            </div>
          </SectionPanel>
        </div>
      </Panel>
    </div>
  );
}
