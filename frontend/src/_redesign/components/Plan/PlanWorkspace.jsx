// FC Route — waypoints rail + map with route polyline. New aesthetic.
import React from 'react';
import { Route, Fuel, Trash2 } from 'lucide-react';
import { Panel, PanelHeader, SectionPanel, HudButton } from '../UI/Hud';
import { MapCanvas } from '../Map/MapCanvas';
import { SYSTEMS, REGIONS, CLUSTERS, HEATMAP } from '../../lib/mockData';

const WAYPOINTS = [
  { i: 1, name: 'Sol',                  x: 0,    z: 0,   leg: null,  warn: null },
  { i: 2, name: 'Synuefe IB-S c19-12',  x: 58,   z: 88,  leg: 158.3, warn: null },
  { i: 3, name: 'Wregoe XX-1 b48-2',    x: -118, z: -42, leg: 184.2, warn: 'tritium <30%' },
  { i: 4, name: 'NGC 1893 OD-T b3-7',   x: -91,  z: 178, leg: 201.5, warn: null },
];

export function PlanWorkspace() {
  const layers = { regions: false, clusters: false, heatmap: false, systems: true, watchlist: false, routes: true };
  const total = WAYPOINTS.reduce((a, w) => a + (w.leg || 0), 0);
  const tritium = Math.ceil(total / 500 * 8);

  return (
    <div className="flex-1 grid grid-cols-[340px_minmax(0,1fr)] gap-3 p-3 min-h-0">
      <Panel className="overflow-hidden flex flex-col">
        <PanelHeader
          icon={<Route size={14} strokeWidth={1.6} />}
          title="FC ROUTE"
          sub="Drag waypoints to reorder"
          right={<HudButton size="sm">EXPORT</HudButton>}
        />
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
          {/* Summary readouts */}
          <div className="grid grid-cols-3 gap-2">
            {[['LEGS', WAYPOINTS.length - 1], ['LY', total.toFixed(0)], ['TRT', tritium]].map(([l, v]) => (
              <div key={l} className="readout rounded-lg px-2 py-2 text-center">
                <div className="font-mono text-[8px] text-[var(--steel-500)] uppercase tracking-wider">{l}</div>
                <div className="font-display text-[16px] tracking-[0.06em] text-[var(--ed-orange-lt)] tabular-nums text-glow-orange mt-0.5">{v}</div>
              </div>
            ))}
          </div>

          <SectionPanel
            icon={<Route size={13} strokeWidth={1.8} />}
            title="WAYPOINTS"
          >
            <div className="space-y-2">
              {WAYPOINTS.map((wp, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[hsla(232,22%,18%,0.55)] border border-[hsla(232,22%,55%,0.28)] hover:border-[hsla(232,30%,70%,0.4)] cursor-grab">
                    <span className="font-display text-[10px] tracking-wider text-[var(--ed-orange-lt)] w-6 tabular-nums">
                      {String(wp.i).padStart(2, '0')}
                    </span>
                    <span className="font-mono text-[11px] text-[var(--steel-100)] flex-1 truncate">{wp.name}</span>
                    <button className="text-[var(--steel-400)] hover:text-[var(--alert)] p-1">
                      <Trash2 size={11} strokeWidth={1.5} />
                    </button>
                  </div>
                  {idx < WAYPOINTS.length - 1 && (
                    <div className="ml-3 pl-3 border-l border-dashed border-[hsla(232,22%,60%,0.3)] py-1 flex items-center gap-2">
                      <Fuel size={10} className="text-[var(--steel-500)]" strokeWidth={1.5} />
                      <span className="font-mono text-[10px] text-[var(--steel-300)]">
                        {WAYPOINTS[idx + 1].leg?.toFixed(1)} LY
                      </span>
                      {WAYPOINTS[idx + 1].warn && (
                        <span className="px-1.5 py-px rounded-[3px] bg-[hsla(45,95%,56%,0.15)] text-[var(--ed-amber)] text-[9px] font-mono">
                          ⚠ {WAYPOINTS[idx + 1].warn}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}

              <button className="w-full mt-2 px-3 py-2.5 rounded-lg border border-dashed border-[hsla(232,22%,55%,0.4)] text-[var(--steel-400)] hover:text-[var(--ed-orange-lt)] hover:border-[hsla(22,100%,50%,0.5)] font-display text-[10px] tracking-wider">
                + ADD WAYPOINT
              </button>
            </div>
          </SectionPanel>
        </div>
      </Panel>

      {/* Map with route polyline */}
      <div className="relative panel overflow-hidden">
        <MapCanvas
          systems={SYSTEMS} regions={REGIONS}
          clusters={CLUSTERS} heatmap={HEATMAP}
          layers={layers}
          selectedId={null} onSelect={() => {}}
          viewport="ROUTE PLAN"
        />
        <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="-400 -400 800 800" preserveAspectRatio="xMidYMid slice">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="3" markerHeight="3" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#ff6a00" />
            </marker>
          </defs>
          {WAYPOINTS.map((wp, idx) => {
            if (idx === 0) return null;
            const a = WAYPOINTS[idx - 1];
            const ax = (a.x / 500) * 400, az = -(a.z / 500) * 400;
            const bx = (wp.x / 500) * 400, bz = -(wp.z / 500) * 400;
            return (
              <line key={idx} x1={ax} y1={az} x2={bx} y2={bz} stroke="#ff6a00" strokeWidth="1.4" strokeDasharray="3 2" opacity="0.85" markerEnd="url(#arrow)" />
            );
          })}
          {WAYPOINTS.map((wp, idx) => {
            const x = (wp.x / 500) * 400, z = -(wp.z / 500) * 400;
            return (
              <g key={`wp-${idx}`}>
                <circle cx={x} cy={z} r="4" fill="#ff6a00" stroke="#0a0c12" strokeWidth="1" />
                <text x={x + 5} y={z - 5} fontFamily="JetBrains Mono, monospace" fontSize="6" fill="#ff9133">
                  {String(wp.i).padStart(2, '0')}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
