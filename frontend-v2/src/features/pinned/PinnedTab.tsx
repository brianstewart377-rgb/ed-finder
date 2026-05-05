import { useState } from 'react';
import type { PinnedEntry, UsePinned } from './usePinned';
import { SystemTable, type SystemRow } from '@/components/SystemTable';

export interface PinnedTabProps {
  pinned:       UsePinned;
  onShowOnMap?: (id64: number) => void;
}

type Sort = 'pinned_at' | 'name' | 'rating' | 'distance';

export function PinnedTab({ pinned, onShowOnMap }: PinnedTabProps) {
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
    <section data-testid="pinned-tab" className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">
          📌 Pinned
        </h2>
        <span className="font-mono text-xs text-text-dim">
          {pinned.entries.length} system{pinned.entries.length === 1 ? '' : 's'}
        </span>
        <span className="flex-1" />

        <label className="font-mono text-[11px] text-text-dim">
          Sort:&nbsp;
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            data-testid="pinned-sort"
            className="bg-bg4 border border-border rounded px-2 py-0.5 text-text"
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
          className="px-2 py-1 rounded bg-bg4 border border-border font-mono text-[11px] text-text-dim hover:text-orange hover:border-orange-dk transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Export JSON
        </button>

        <button
          type="button"
          onClick={() => {
            if (pinned.entries.length === 0) return;
            if (confirm(`Clear all ${pinned.entries.length} pinned systems?`)) {
              pinned.clear();
            }
          }}
          disabled={pinned.entries.length === 0}
          data-testid="pinned-clear"
          className="px-2 py-1 rounded bg-red/10 border border-red/40 font-mono text-[11px] text-red hover:bg-red/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ✕ Clear all
        </button>
      </header>

      {pinned.entries.length === 0 && (
        <div className="text-center py-16 px-4 rounded border border-dashed border-border">
          <div className="text-3xl mb-2" aria-hidden>📌</div>
          <h3 className="font-mono text-orange text-sm mb-1">No pinned systems yet</h3>
          <p className="text-text-dim text-xs max-w-sm mx-auto">
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
                onClick={() => pinned.remove(row.id64)}
                data-testid={`pinned-remove-${row.id64}`}
                className="px-2 py-0.5 rounded bg-red/10 border border-red/40 text-[10px] text-red hover:bg-red/20"
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
 * shape when toggling. Passes through `distance` + `rating` if the caller
 * has them, otherwise leaves them null.
 */
export function toPinnedEntry(sys: {
  id64:         number;
  name:         string;
  coords?:      { x: number; y: number; z: number };
  distance?:    number | null;
  population:   number;
  is_colonised?: boolean;
  _rating?:     { score: number | null; economySuggestion?: string | null } | null;
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
