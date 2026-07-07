import React from 'react';
import { Activity, Radio, X } from 'lucide-react';
import { GlassPanel } from '../UI/Hud';

export function EDDNFeed({ feed, onClose }) {
  return (
    <GlassPanel className="p-2.5 w-[260px] shadow-2xl" data-testid="eddn-feed">
      <div className="flex items-center gap-2 px-1 pb-2 border-b border-[hsla(232,22%,60%,0.22)] mb-1.5">
        <span className="relative flex w-2 h-2">
          <span className="absolute inset-0 rounded-full bg-[var(--success)] hud-pulse" />
          <span className="relative w-2 h-2 rounded-full bg-[var(--success)]" />
        </span>
        <span className="font-display text-[10px] tracking-[0.2em] text-[var(--steel-100)] flex-1">EDDN · LIVE</span>
        <Radio size={10} className="text-[var(--steel-400)]" strokeWidth={1.6} />
        {onClose && (
          <button
            onClick={onClose}
            className="text-[var(--steel-400)] hover:text-[var(--steel-100)] p-0.5 rounded-sm hover:bg-[hsla(232,22%,30%,0.4)]"
            title="Hide feed"
          >
            <X size={10} strokeWidth={2} />
          </button>
        )}
      </div>

      <ul className="space-y-0.5 max-h-[230px] overflow-y-auto">
        {feed.map((e, i) => (
          <li
            key={i}
            className="px-1.5 py-1.5 rounded-md hover:bg-[hsla(232,22%,30%,0.4)] cursor-pointer group"
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-mono text-[9px] text-[var(--steel-500)] tabular-nums w-12 flex-shrink-0">{e.ago}</span>
              <span className="font-display text-[9px] tracking-[0.1em] text-[var(--ed-orange-lt)] group-hover:text-glow-orange truncate">
                {e.cmdr}
              </span>
            </div>
            <div className="ml-14 -mt-0.5">
              <span className="text-[10px] text-[var(--steel-300)]">{e.action}</span>
              <span className="text-[10px] text-[var(--steel-500)]"> · </span>
              <span className="font-mono text-[10px] text-[var(--steel-100)]">{e.system}</span>
            </div>
            <div className="ml-14 font-mono text-[9px] text-[var(--info)]">
              {e.scoreDelta}
            </div>
          </li>
        ))}
      </ul>
    </GlassPanel>
  );
}
