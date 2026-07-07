// Track / Colony — phase pipeline kanban. Iteration-3 panel aesthetic.
import React from 'react';
import { Building2, Clock, Hammer, CheckCircle2, Activity } from 'lucide-react';
import { Panel, PanelHeader } from '../UI/Hud';

const PHASES = [
  { key: 'planning',  label: 'PLANNING',  icon: Clock,        color: '#60a5fa' },
  { key: 'building',  label: 'BUILDING',  icon: Hammer,       color: '#facc15' },
  { key: 'active',    label: 'ACTIVE',    icon: Activity,     color: '#3ddc84' },
  { key: 'complete',  label: 'COMPLETE',  icon: CheckCircle2, color: '#ff6a00' },
];

const COLONIES = {
  planning:  [{ name: 'Wregoe XX-1 b48-2', score: 89, suggested: 'High Tech',  pct: 12 }],
  building:  [
    { name: 'HIP 22460',         score: 82, suggested: 'Tourism',     pct: 64 },
    { name: 'Synuefe IB-S c19',  score: 76, suggested: 'Refinery',    pct: 38 },
  ],
  active:    [{ name: 'Pleiades RX-K d8',  score: 71, suggested: 'Agriculture', pct: 100 }],
  complete:  [],
};

export function TrackWorkspace() {
  return (
    <div className="flex-1 p-3 min-h-0">
      <Panel className="h-full overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Building2 size={14} strokeWidth={1.6} />}
          title="COLONY PIPELINE"
          sub="Phase by phase · driven by EDDN events"
        />
        <div className="flex-1 overflow-auto p-4">
          <div className="grid grid-cols-4 gap-3 h-full">
            {PHASES.map((p) => {
              const Icon = p.icon;
              const items = COLONIES[p.key];
              return (
                <div
                  key={p.key}
                  className="section-panel flex flex-col overflow-hidden"
                  style={{ borderTopColor: p.color, borderTopWidth: 2, borderTopStyle: 'solid' }}
                >
                  <header className="section-panel-header">
                    <Icon size={12} strokeWidth={1.6} style={{ color: p.color }} />
                    <span className="font-display text-[11px] tracking-[0.18em] flex-1" style={{ color: p.color }}>
                      {p.label}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--steel-400)] tabular-nums">{items.length}</span>
                  </header>
                  <div className="flex-1 p-2.5 space-y-2 overflow-y-auto">
                    {items.map((c, i) => (
                      <article
                        key={i}
                        className="rounded-lg border border-[hsla(232,22%,55%,0.28)] bg-[hsla(232,22%,16%,0.55)] p-3 hover:border-[hsla(22,100%,50%,0.45)] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="font-mono text-[10px] tabular-nums px-2 py-0.5 rounded-[3px]"
                            style={{
                              color: p.color,
                              background: `${p.color}1a`,
                              border: `1px solid ${p.color}55`,
                              boxShadow: `0 0 6px ${p.color}33`,
                            }}
                          >
                            {c.score}
                          </span>
                          <span className="font-display text-[11px] tracking-[0.06em] text-[var(--steel-100)] flex-1 truncate">
                            {c.name}
                          </span>
                        </div>
                        <div className="font-mono text-[9px] text-[var(--steel-400)] mb-2">
                          → {c.suggested}
                        </div>
                        <div className="h-1.5 bg-[hsla(232,30%,5%,0.7)] rounded-full overflow-hidden">
                          <div
                            className="h-1.5 rounded-full"
                            style={{ width: `${c.pct}%`, background: p.color, boxShadow: `0 0 6px ${p.color}88` }}
                          />
                        </div>
                        <div className="flex items-center justify-between mt-1.5">
                          <span className="font-mono text-[9px] text-[var(--steel-500)]">{c.pct}% complete</span>
                          <span className="font-mono text-[9px] text-[var(--steel-500)]">3d ago</span>
                        </div>
                      </article>
                    ))}
                    {items.length === 0 && (
                      <div className="text-center py-6 font-mono text-[9px] text-[var(--steel-500)]">
                        — empty —
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Panel>
    </div>
  );
}
