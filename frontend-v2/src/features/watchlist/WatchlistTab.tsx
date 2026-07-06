import { useState } from 'react';
import type { WatchlistEntry } from '@/lib/api';
import { SystemTable, type SystemRow } from '@/components/SystemTable';
import { distanceFromSol } from '@/lib/format';

export interface WatchlistTabProps {
  entries:    WatchlistEntry[];
  loading:    boolean;
  error:      string | null;
  onRefresh:  () => Promise<void> | void;
  onRemove:   (id64: number) => Promise<void> | void;
  onShowOnMap?: (id64: number) => void;
  onOpenDetail?: (id64: number) => void;
}

type Sort = 'added' | 'name' | 'score' | 'distance';

export function WatchlistTab({
  entries, loading, error, onRefresh, onRemove, onShowOnMap, onOpenDetail,
}: WatchlistTabProps) {
  const [sort, setSort] = useState<Sort>('added');

  const sorted = [...entries].sort((a, b) => {
    switch (sort) {
      case 'name':  return a.name.localeCompare(b.name);
      case 'score': return ((b.archetype_score ?? b.score) ?? -1) - ((a.archetype_score ?? a.score) ?? -1);
      case 'distance': {
        const da = distanceFromSol(a, a.system_id64) ?? Number.POSITIVE_INFINITY;
        const db = distanceFromSol(b, b.system_id64) ?? Number.POSITIVE_INFINITY;
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
    score:        e.archetype_score ?? e.score ?? null,
    economy:      e.economy_suggestion ?? null,
    archetype:    e.primary_archetype ?? null,
    secondaryArchetype: e.secondary_archetype ?? null,
    timestamp:    e.added_at,
  }));

  return (
    <section data-testid="watchlist-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">
          👁️ Watchlist
        </h2>
        <span className="font-mono text-xs text-silver-dk">
          {entries.length} system{entries.length === 1 ? '' : 's'}
        </span>
        <span className="flex-1" />
        <label className="font-mono text-[11px] text-silver-dk flex items-center gap-2">
          Sort:
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
          >
            <option value="added">Recently added</option>
            <option value="name">Name</option>
            <option value="score">Development ↓</option>
            <option value="distance">Distance from Sol ↑</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void onRefresh()}
          data-testid="watchlist-refresh"
          className="btn-metal text-[11px] py-1.5 px-3"
        >
          ↺ Refresh
        </button>
      </header>

      {error && (
        <div className="panel-thin border-red/50 p-3 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
          {error}
        </div>
      )}

      {loading && entries.length === 0 && (
        <div className="text-silver-dk font-mono text-sm py-12 text-center">
          Loading watchlist…
        </div>
      )}

      {!loading && entries.length === 0 && (
        <div className="panel-thin text-center py-16 px-4">
          <div className="text-3xl mb-2" aria-hidden>👁️</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No systems watched yet</h3>
          <p className="text-silver-dk text-xs max-w-sm mx-auto">
            Use Save for later on any Finder result to keep an eye on it here.
          </p>
        </div>
      )}

      {rows.length > 0 && (
        <SystemTable
          rows={rows}
          columns={['system', 'coords', 'population', 'score', 'economy', 'timestamp']}
          timestampLabel="Added"
          rowTestIdPrefix="watchlist-row-"
          onRowClick={onOpenDetail}
          renderActions={(row) => (
            <>
              {onShowOnMap && (
                <button
                  type="button"
                  onClick={() => onShowOnMap(row.id64)}
                  className="btn-metal text-[10px] py-1 px-2"
                  title="Show on map"
                >
                  🗺️
                </button>
              )}
              <button
                type="button"
                onClick={() => void onRemove(row.id64)}
                data-testid={`watchlist-remove-${row.id64}`}
                className="text-[10px] py-1 px-2 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20"
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
