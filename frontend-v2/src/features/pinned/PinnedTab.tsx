import { useState } from 'react';
import type { PinnedEntry, UsePinned } from './usePinned';
import { SystemTable, type SystemRow } from '@/components/SystemTable';

export interface PinnedTabProps {
  pinned:       UsePinned;
  onShowOnMap?: (id64: number) => void;
  onOpenDetail?: (id64: number) => void;
}

type Sort = 'pinned_at' | 'name' | 'rating' | 'distance';

export function PinnedTab({ pinned, onShowOnMap, onOpenDetail }: PinnedTabProps) {
  const [sort, setSort] = useState<Sort>('pinned_at');

  const sorted = [...pinned.entries].sort((a, b) => {
    switch (sort) {
      case 'name':   return a.name.localeCompare(b.name);
      case 'rating': return (b.rating ?? -1) - (a.rating ?? -1);
      case 'distance': {
        const da = Math.hypot(a.x, a.y, a.z);
        const db = Math.hypot(b.x, b.y, b.z);
        return da - db;
      }
      case 'pinned_at':
      default:
        return new Date(b.pinned_at).getTime() - new Date(a.pinned_at).getTime();
    }
  });

  const rows: SystemRow[] = sorted.map((p) => ({
    id64:         p.id64,
    name:         p.name,
    x:            p.x,
    y:            p.y,
    z:            p.z,
    population:   p.population,
    is_colonised: p.is_colonised,
    score:        p.rating,
    economy:      p.economy,
    timestamp:    p.pinned_at,
    distance:     p.distance ?? null,
  }));

  return (
    <section data-testid="pinned-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">📌 Pinned</h2>
        <span className="font-mono text-xs text-silver-dk">
          {pinned.entries.length} system{pinned.entries.length === 1 ? '' : 's'}
        </span>
        <span className="flex-1" />

        <label className="font-mono text-[11px] text-silver-dk flex items-center gap-2">
          Sort:
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            data-testid="pinned-sort"
          >
            <option value="pinned_at">Recently pinned</option>
            <option value="name">Name</option>
            <option value="rating">Rating ↓</option>
            <option value="distance">Distance from Sol ↑</option>
          </select>
        </label>

        <button
          type="button"
          onClick={pinned.exportJson}
          disabled={pinned.entries.length === 0}
          data-testid="pinned-export"
          className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Export JSON
        </button>

        <button
          type="button"
          onClick={() => {
            if (pinned.entries.length === 0) return;
            if (confirm(`Clear all ${pinned.entries.length} pinned systems?`)) pinned.clear();
          }}
          disabled={pinned.entries.length === 0}
          data-testid="pinned-clear"
          className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20 font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ✕ Clear all
        </button>
      </header>

      {pinned.entries.length === 0 && (
        <div className="panel-thin text-center py-16 px-4">
          <div className="text-3xl mb-2" aria-hidden>📌</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No pinned systems yet</h3>
          <p className="text-silver-dk text-xs max-w-sm mx-auto">
            Click 📍 on any system in the Finder tab to keep a shortlist.
            Pinned systems live in your browser — no server round-trip.
          </p>
        </div>
      )}

      {pinned.entries.length > 0 && (
        <SystemTable
          rows={rows}
          columns={['system', 'coords', 'score', 'economy', 'distanceRef', 'timestamp', 'externalLinks']}
          timestampLabel="Pinned"
          rowTestIdPrefix="pinned-row-"
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
                onClick={() => pinned.remove(row.id64)}
                data-testid={`pinned-remove-${row.id64}`}
                className="text-[10px] py-1 px-2 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20"
              >
                ✕ Unpin
              </button>
            </>
          )}
        />
      )}
    </section>
  );
}

/**
 * Factory helper so call-sites don't have to spell out the whole PinnedEntry
 * shape when toggling.
 */
export function toPinnedEntry(sys: {
  id64:         number;
  name:         string;
  coords?:      { x: number; y: number; z: number } | null;
  distance?:    number | null;
  population:   number;
  is_colonised?: boolean | null;
  _rating?:     { score?: number | null; economySuggestion?: string | null } | null;
}): PinnedEntry {
  return {
    id64:         sys.id64,
    name:         sys.name,
    x:            sys.coords?.x ?? 0,
    y:            sys.coords?.y ?? 0,
    z:            sys.coords?.z ?? 0,
    population:   sys.population,
    is_colonised: !!sys.is_colonised,
    distance:     sys.distance ?? null,
    rating:       sys._rating?.score ?? null,
    economy:      sys._rating?.economySuggestion ?? null,
    pinned_at:    new Date().toISOString(),
  };
}
