import React from 'react';
import { Layers, Map, Boxes, Activity, Star, Route as RouteIcon, Eye, X } from 'lucide-react';
import { GlassPanel } from '../UI/Hud';

const LAYER_DEFS = [
  { key: 'regions',   label: 'Regions',   icon: Map,      hint: '1' },
  { key: 'clusters',  label: 'Clusters',  icon: Boxes,    hint: '2' },
  { key: 'heatmap',   label: 'Heatmap',   icon: Activity, hint: '3' },
  { key: 'systems',   label: 'Systems',   icon: Star,     hint: '4' },
  { key: 'watchlist', label: 'Watchlist', icon: Eye,      hint: '5' },
  { key: 'routes',    label: 'Routes',    icon: RouteIcon,hint: '6' },
];

export function LayerToggles({ layers, onToggle, economy, onEconomy, economies, onClose }) {
  return (
    <GlassPanel className="p-3 space-y-3 w-[230px] shadow-2xl" data-testid="layer-toggles">
      <div className="flex items-center gap-2 pb-2 border-b border-[hsla(232,22%,60%,0.22)]">
        <Layers size={13} className="text-[var(--ed-orange)]" strokeWidth={1.6} />
        <span className="font-display text-[10px] tracking-[0.2em] text-[var(--steel-100)] flex-1">MAP LAYERS</span>
        {onClose && (
          <button
            onClick={onClose}
            className="text-[var(--steel-400)] hover:text-[var(--steel-100)] p-0.5 rounded-sm hover:bg-[hsla(232,22%,30%,0.4)]"
            title="Hide layers"
          >
            <X size={11} strokeWidth={2} />
          </button>
        )}
      </div>

      <div className="space-y-1">
        {LAYER_DEFS.map((l) => {
          const Icon = l.icon;
          const on = !!layers[l.key];
          return (
            <button
              key={l.key}
              onClick={() => onToggle(l.key)}
              className={[
                'group w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md text-left transition-colors',
                on ? 'bg-[hsla(22,100%,50%,0.10)] text-[var(--ed-orange-lt)]' : 'text-[var(--steel-300)] hover:bg-[hsla(232,22%,28%,0.5)] hover:text-[var(--steel-100)]',
              ].join(' ')}
            >
              <span
                className={[
                  'w-3 h-3 rounded-[3px] border transition-all flex-shrink-0',
                  on ? 'bg-[var(--ed-orange)] border-[var(--ed-orange)] shadow-[0_0_8px_hsla(22,100%,50%,0.6)]' : 'border-[hsla(232,22%,60%,0.5)]',
                ].join(' ')}
              />
              <Icon size={12} strokeWidth={1.6} />
              <span className="font-display text-[10px] tracking-[0.14em] flex-1">{l.label}</span>
              <span className="font-mono text-[8px] text-[var(--steel-500)] tabular-nums">{l.hint}</span>
            </button>
          );
        })}
      </div>

      <div className="pt-2 border-t border-[hsla(232,22%,60%,0.22)] space-y-1.5">
        <div className="font-display text-[9px] tracking-[0.18em] text-[var(--steel-400)]">HEATMAP MODE</div>
        <select
          value={economy}
          onChange={(e) => onEconomy(e.target.value)}
          className="w-full bg-[hsla(232,30%,8%,0.85)] border border-[hsla(232,22%,50%,0.4)] rounded-md px-2 py-1.5 font-mono text-[10px] text-[var(--steel-100)]"
        >
          <option value="overall">Overall score</option>
          {economies.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
      </div>
    </GlassPanel>
  );
}
