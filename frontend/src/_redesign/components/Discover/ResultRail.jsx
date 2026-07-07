import React from 'react';
import { Panel, PanelHeader, HudButton } from '../UI/Hud';
import { SystemRow } from './SystemRow';
import { ListFilter, ArrowDownNarrowWide } from 'lucide-react';

export function ResultRail({ systems, selectedId, watched, onSelect, onWatch, onCompare }) {
  return (
    <Panel className="h-full overflow-hidden flex flex-col" chamfer={false}>
      <PanelHeader
        icon={<ListFilter size={13} strokeWidth={1.6} />}
        title={`RESULTS · ${systems.length} SYSTEMS`}
        sub="Ranked by tuned weights · click to brief"
        right={
          <div className="flex items-center gap-1">
            <HudButton size="sm" icon={ArrowDownNarrowWide}>SCORE</HudButton>
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto divide-y divide-[var(--steel-800)]">
        {systems.map((s, i) => (
          <SystemRow
            key={s.id64}
            system={s}
            index={i}
            selected={selectedId === s.id64}
            watched={watched.has(s.id64)}
            onSelect={onSelect}
            onWatch={onWatch}
            onCompare={onCompare}
          />
        ))}
      </div>
    </Panel>
  );
}
