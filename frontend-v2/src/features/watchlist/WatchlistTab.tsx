import { useState } from 'react';
import type { WatchlistEntry } from '@/lib/api';
import { ratingTier, formatPopulation } from '@/lib/format';

export interface WatchlistTabProps {
  entries:    WatchlistEntry[];
  loading:    boolean;
  error:      string | null;
  onRefresh:  () => Promise<void> | void;
  onRemove:   (id64: number) => Promise<void> | void;
  onShowOnMap?: (id64: number) => void;
}

type Sort = 'added' | 'name' | 'score' | 'distance';

export function WatchlistTab({
  entries, loading, error, onRefresh, onRemove, onShowOnMap,
}: WatchlistTabProps) {
  const [sort, setSort] = useState<Sort>('added');

  const sorted = [...entries].sort((a, b) => {
    switch (sort) {
      case 'name':  return a.name.localeCompare(b.name);
      case 'score': return (b.score ?? -1) - (a.score ?? -1);
      // distance from Sol — handy heuristic for routing
      case 'distance': {
        const da = Math.hypot(a.x, a.y, a.z);
        const db = Math.hypot(b.x, b.y, b.z);
        return da - db;
      }
      case 'added':
      default: return new Date(b.added_at).getTime() - new Date(a.added_at).getTime();
    }
  });

  return (
    <section data-testid="watchlist-tab" className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">
          👁️ Watchlist
        </h2>
        <span className="font-mono text-xs text-text-dim">
          {entries.length} system{entries.length === 1 ? '' : 's'}
        </span>
        <span className="flex-1" />
        <label className="font-mono text-[11px] text-text-dim">
          Sort:&nbsp;
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="bg-bg4 border border-border rounded px-2 py-0.5 text-text"
          >
            <option value="added">Recently added</option>
            <option value="name">Name</option>
            <option value="score">Score ↓</option>
            <option value="distance">Distance from Sol ↑</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void onRefresh()}
          data-testid="watchlist-refresh"
          className="px-2 py-1 rounded bg-bg4 border border-border font-mono text-[11px] text-text-dim hover:text-orange hover:border-orange-dk transition-colors"
        >
          ↺ Refresh
        </button>
      </header>

      {error && (
        <div className="rounded border border-red/50 bg-red/10 p-3 font-mono text-xs text-red">
          {error}
        </div>
      )}

      {loading && entries.length === 0 && (
        <div className="text-text-dim font-mono text-sm py-12 text-center">
          Loading watchlist…
        </div>
      )}

      {!loading && entries.length === 0 && (
        <div className="text-center py-16 px-4 rounded border border-dashed border-border">
          <div className="text-3xl mb-2" aria-hidden>👁️</div>
          <h3 className="font-mono text-orange text-sm mb-1">No systems watched yet</h3>
          <p className="text-text-dim text-xs max-w-sm mx-auto">
            Click 👁️ Watch on any system in the Finder tab to keep an eye on it here.
          </p>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm font-mono">
            <thead className="bg-bg3/60 text-text-dim text-[11px] uppercase tracking-wider">
              <tr>
                <th className="px-3 py-2 text-left">System</th>
                <th className="px-3 py-2 text-right">Coords (LY)</th>
                <th className="px-3 py-2 text-right">Population</th>
                <th className="px-3 py-2 text-center">Score</th>
                <th className="px-3 py-2 text-left">Suggested</th>
                <th className="px-3 py-2 text-right">Added</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => {
                const tier = ratingTier(row.score);
                const dist = Math.hypot(row.x, row.y, row.z);
                return (
                  <tr
                    key={row.system_id64}
                    data-testid={`watchlist-row-${row.system_id64}`}
                    className="border-t border-border hover:bg-bg3/40"
                  >
                    <td className="px-3 py-2">
                      <span className="text-orange font-bold">{row.name}</span>
                      {row.is_colonised && (
                        <span className="ml-2 text-[9px] px-1 py-0.5 rounded bg-red/20 text-red border border-red/40">COL</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-text-dim text-xs tabular-nums">
                      {row.x.toFixed(0)}, {row.y.toFixed(0)}, {row.z.toFixed(0)}
                      <div className="text-[10px] text-text-dim/70">{dist.toFixed(1)} LY from Sol</div>
                    </td>
                    <td className="px-3 py-2 text-right text-text-dim text-xs">
                      {formatPopulation(row.population)}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span
                        className={[
                          'inline-block px-2 py-0.5 rounded border text-[11px] font-bold',
                          tier.label === 'EXCELLENT' && 'bg-green/20 text-green border-green/50',
                          tier.label === 'GOOD'      && 'bg-gold/20 text-gold border-gold/50',
                          tier.label === 'OK'        && 'bg-orange/20 text-orange border-orange/50',
                          tier.label === 'POOR'      && 'bg-red/20 text-red border-red/50',
                          tier.label === 'N/A'       && 'bg-bg4 text-text-dim border-border',
                        ].filter(Boolean).join(' ')}
                      >
                        {row.score ?? '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-text-dim text-xs">
                      {row.economy_suggestion ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right text-text-dim text-[10px]">
                      {new Date(row.added_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2 text-right space-x-1 whitespace-nowrap">
                      {onShowOnMap && (
                        <button
                          type="button"
                          onClick={() => onShowOnMap(row.system_id64)}
                          className="px-2 py-0.5 rounded bg-bg4 border border-border text-[10px] text-text-dim hover:text-orange hover:border-orange-dk"
                        >
                          🗺️
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void onRemove(row.system_id64)}
                        data-testid={`watchlist-remove-${row.system_id64}`}
                        className="px-2 py-0.5 rounded bg-red/10 border border-red/40 text-[10px] text-red hover:bg-red/20"
                      >
                        ✕ Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
