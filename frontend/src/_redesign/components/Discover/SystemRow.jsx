import React from 'react';
import { ratingTier, fmtPop } from '../../lib/mockData';
import { EconomyBars } from './RatingRadar';
import { RatingBar, TierPill } from '../UI/Hud';
import { Eye, Bookmark, Scale, MapPin } from 'lucide-react';

export function SystemRow({ system, index, selected, watched, onSelect, onWatch, onCompare }) {
  const tier = ratingTier(system.score);
  return (
    <article
      onClick={() => onSelect(system)}
      className={[
        'group relative px-3 py-2.5 border-l-2 cursor-pointer transition-colors',
        selected
          ? 'bg-[var(--ed-orange)]/8 border-l-[var(--ed-orange)]'
          : 'border-l-transparent hover:bg-[var(--steel-800)]/50 hover:border-l-[var(--steel-500)]',
        watched && !selected ? 'border-l-[var(--info)]' : '',
      ].join(' ')}
      data-testid={`system-row-${system.id64}`}
    >
      <div className="flex items-start gap-2.5">
        {/* Index */}
        <span className="font-mono text-[10px] text-[var(--steel-500)] mt-1 tabular-nums w-5 flex-shrink-0">
          #{index + 1}
        </span>

        {/* Main column */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-display text-[12px] tracking-[0.08em] text-[var(--steel-100)] truncate flex-1">
              {system.name}
            </h3>
            <TierPill score={system.score} tier={tier} />
          </div>

          {/* Rationale — ELEVATED. The "why" goes right under the name. */}
          <p className="text-[11px] text-[var(--steel-300)] leading-snug mb-1.5">
            {system.rationale}
          </p>

          <div className="flex items-center gap-3 text-[10px] font-mono text-[var(--steel-400)]">
            <EconomyBars breakdown={system.breakdown} />
            <span className="text-[var(--steel-500)]">·</span>
            <span className="tabular-nums">{system.distance.toFixed(1)} LY</span>
            <span className="text-[var(--steel-500)]">·</span>
            <span>{fmtPop(system.population)}</span>
            {system.is_colonised && (
              <span className="px-1 py-px rounded-[2px] bg-[var(--alert)]/15 text-[var(--alert)] text-[9px]">COL</span>
            )}
            {system.bodies.elw > 0 && (
              <span className="px-1 py-px rounded-[2px] bg-[#4ade80]/15 text-[#4ade80] text-[9px]">{system.bodies.elw} ELW</span>
            )}
            {system.stars.blackHole > 0 && (
              <span className="px-1 py-px rounded-[2px] bg-[var(--alert)]/15 text-[var(--alert)] text-[9px]">BH</span>
            )}
          </div>
        </div>

        {/* Hover-revealed action cluster */}
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity self-start mt-0.5">
          <button
            onClick={(e) => { e.stopPropagation(); onWatch(system.id64); }}
            className={[
              'p-1 rounded-sm hover:bg-[var(--steel-700)]',
              watched ? 'text-[var(--info)]' : 'text-[var(--steel-400)] hover:text-[var(--steel-100)]',
            ].join(' ')}
            title="Watch"
          >
            <Eye size={13} strokeWidth={1.5} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onCompare(system.id64); }}
            className="p-1 rounded-sm text-[var(--steel-400)] hover:text-[var(--steel-100)] hover:bg-[var(--steel-700)]"
            title="Compare"
          >
            <Scale size={13} strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </article>
  );
}
