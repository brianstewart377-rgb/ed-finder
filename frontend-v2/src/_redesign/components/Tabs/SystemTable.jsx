// Lightweight system table used by Watchlist / Pinned / Optimizer stubs.
import React from 'react';
import { ratingTier, fmtPop } from '../../lib/mockData';
import { TierPill } from '../UI/Hud';
import { Eye, Scale, Trash2 } from 'lucide-react';

export function SystemTable({ systems, onSelect, watched }) {
  return (
    <div className="flex-1 overflow-auto">
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-[var(--steel-900)] border-b border-[var(--steel-700)]">
          <tr className="text-left text-[var(--steel-400)] font-display tracking-[0.14em] text-[9px]">
            <th className="px-3 py-2 w-8">#</th>
            <th className="px-3 py-2">SYSTEM</th>
            <th className="px-3 py-2">RATIONALE</th>
            <th className="px-3 py-2 w-20 text-right">DIST</th>
            <th className="px-3 py-2 w-24 text-right">POP</th>
            <th className="px-3 py-2 w-28 text-center">SCORE</th>
            <th className="px-3 py-2 w-20"></th>
          </tr>
        </thead>
        <tbody>
          {systems.map((s, i) => {
            const tier = ratingTier(s.score);
            return (
              <tr
                key={s.id64}
                onClick={() => onSelect?.(s)}
                className="border-b border-[var(--steel-800)] hover:bg-[var(--steel-850)]/60 cursor-pointer"
              >
                <td className="px-3 py-2 font-mono text-[10px] text-[var(--steel-500)] tabular-nums">{i + 1}</td>
                <td className="px-3 py-2 font-display text-[11px] tracking-[0.06em] text-[var(--steel-100)]">{s.name}</td>
                <td className="px-3 py-2 text-[var(--steel-300)] italic max-w-[400px] truncate">{s.rationale}</td>
                <td className="px-3 py-2 font-mono text-[10px] text-[var(--steel-300)] text-right tabular-nums">{s.distance.toFixed(1)} LY</td>
                <td className="px-3 py-2 font-mono text-[10px] text-[var(--steel-300)] text-right">{fmtPop(s.population)}</td>
                <td className="px-3 py-2 text-center"><TierPill score={s.score} tier={tier} /></td>
                <td className="px-3 py-2">
                  <div className="flex items-center justify-end gap-0.5">
                    <button className="p-1 rounded-sm text-[var(--steel-400)] hover:text-[var(--info)] hover:bg-[var(--steel-700)]">
                      <Eye size={11} strokeWidth={1.5} />
                    </button>
                    <button className="p-1 rounded-sm text-[var(--steel-400)] hover:text-[var(--ed-orange-lt)] hover:bg-[var(--steel-700)]">
                      <Scale size={11} strokeWidth={1.5} />
                    </button>
                    <button className="p-1 rounded-sm text-[var(--steel-400)] hover:text-[var(--alert)] hover:bg-[var(--steel-700)]">
                      <Trash2 size={11} strokeWidth={1.5} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
