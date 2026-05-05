import { useState } from 'react';
import type { WatchlistEntry } from '@/lib/api';
import { SystemTable, type SystemRow } from '@/components/SystemTable';

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
      case 'distance': {
        const da = Math.hypot(a.x, a.y, a.z);
        const db = Math.hypot(b.x, b.y, b.z);
        return da - db;
      }
      case 'added':
      default: return new Date(b.added_at).getTime() - new Date(a.added_at).getTime();
    }
  });

  // Adapter: WatchlistEntry → SystemRow for the shared table.
  const rows: SystemRow[] = sorted.map((e) => ({
    id64:         e.system_id64,
    name:         e.name,
    x:            e.x,
    y:            e.y,
    z:            e.z,
    population:   e.population,
    is_colonised: e.is_colonised,
    score:        e.score ?? null,
    economy:      e.economy_suggestion ?? null,
    timestamp:    e.added_at,
  }));

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

      {rows.length > 0 && (
        <SystemTable
          rows={rows}
          columns={['system', 'coords', 'population', 'score', 'economy', 'timestamp']}
          timestampLabel="Added"
          rowTestIdPrefix="watchlist-row-"
          renderActions={(row) => (
            <>
              {onShowOnMap && (
                <button
                  type="button"
                  onClick={() => onShowOnMap(row.id64)}
                  className="px-2 py-0.5 rounded bg-bg4 border border-border text-[10px] text-text-dim hover:text-orange hover:border-orange-dk"
                  title="Show on map"
                >
                  🗺️
                </button>
              )}
              <button
                type="button"
                onClick={() => void onRemove(row.id64)}
                data-testid={`watchlist-remove-${row.id64}`}
                className="px-2 py-0.5 rounded bg-red/10 border border-red/40 text-[10px] text-red hover:bg-red/20"
              >
                ✕ Remove
              </button>
            </>
          )}
        />
      )}
    </section>
  );
}
