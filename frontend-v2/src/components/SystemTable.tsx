import type { ReactNode } from 'react';
import { ratingTier, formatPopulation } from '@/lib/format';

/**
 * Minimal row shape that every "list of systems" feature shares (Watchlist,
 * Pinned, Compare results, Cluster anchors, …). Optional fields are null
 * when the source doesn't supply them — we prefer an explicit null over a
 * missing key so the column render is a pure function of the row.
 */
export interface SystemRow {
  id64:         number;
  name:         string;
  x:            number;
  y:            number;
  z:            number;
  population:   number;
  is_colonised: boolean;
  score:        number | null;
  economy:      string | null;
  /** ISO timestamp for the "added" / "pinned at" column. null = hide. */
  timestamp:    string | null;
  /** LY from the current search reference. null if the caller has no ref. */
  distance?:    number | null;
}

export type SystemTableColumn =
  | 'system'       // name + COL pill
  | 'coords'       // x, y, z + distance-from-Sol
  | 'population'
  | 'score'        // coloured tier badge
  | 'economy'      // suggested / snapshot economy
  | 'distanceRef'  // distance from search reference (if supplied)
  | 'timestamp'    // added_at / pinned_at
  | 'externalLinks'; // Spansh + Inara

export interface SystemTableProps {
  rows:        SystemRow[];
  columns:     SystemTableColumn[];
  /** Header label for the timestamp column (e.g. "Added", "Pinned"). */
  timestampLabel?: string;
  /** Rendered as the last cell of every row — tab-specific actions. */
  renderActions?:  (row: SystemRow) => ReactNode;
  /** Test-id prefix so rows can be targeted per feature (e.g. "pinned-row-"). */
  rowTestIdPrefix?: string;
}

/**
 * Pure presentational table. No sort UI, no toolbar — parent owns those
 * because tab-specific header actions (Refresh vs Export vs Clear) make a
 * one-size-fits-all toolbar actively unhelpful.
 *
 * The column set is intentionally finite. If a new feature needs a column
 * that isn't here, add it to SystemTableColumn rather than inventing a
 * parallel table — keeping every system list visually consistent is worth
 * more than column flexibility.
 */
export function SystemTable({
  rows, columns, timestampLabel = 'Added', renderActions, rowTestIdPrefix,
}: SystemTableProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm font-mono">
        <thead className="bg-bg3/60 text-text-dim text-[11px] uppercase tracking-wider">
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className={[
                  'px-3 py-2',
                  col === 'coords' || col === 'population' || col === 'distanceRef' || col === 'timestamp'
                    ? 'text-right'
                    : col === 'score'
                      ? 'text-center'
                      : 'text-left',
                ].join(' ')}
              >
                {headerLabel(col, timestampLabel)}
              </th>
            ))}
            {renderActions && (
              <th className="px-3 py-2 text-right">Actions</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id64}
              data-testid={rowTestIdPrefix ? `${rowTestIdPrefix}${row.id64}` : undefined}
              className="border-t border-border hover:bg-bg3/40"
            >
              {columns.map((col) => (
                <td
                  key={col}
                  className={[
                    'px-3 py-2',
                    col === 'coords' || col === 'population' || col === 'distanceRef' || col === 'timestamp'
                      ? 'text-right'
                      : col === 'score'
                        ? 'text-center'
                        : 'text-left',
                  ].join(' ')}
                >
                  {renderCell(col, row)}
                </td>
              ))}
              {renderActions && (
                <td className="px-3 py-2 text-right space-x-1 whitespace-nowrap">
                  {renderActions(row)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Column renderers ──────────────────────────────────────────────────────

function headerLabel(col: SystemTableColumn, timestampLabel: string): string {
  switch (col) {
    case 'system':        return 'System';
    case 'coords':        return 'Coords (LY)';
    case 'population':    return 'Population';
    case 'score':         return 'Score';
    case 'economy':       return 'Suggested';
    case 'distanceRef':   return 'Dist. from ref.';
    case 'timestamp':     return timestampLabel;
    case 'externalLinks': return 'Links';
  }
}

function renderCell(col: SystemTableColumn, row: SystemRow): ReactNode {
  switch (col) {
    case 'system':
      return (
        <>
          <span className="text-orange font-bold">{row.name}</span>
          {row.is_colonised && (
            <span className="ml-2 text-[9px] px-1 py-0.5 rounded bg-red/20 text-red border border-red/40">
              COL
            </span>
          )}
        </>
      );

    case 'coords': {
      const dist = Math.hypot(row.x, row.y, row.z);
      return (
        <span className="text-text-dim text-xs tabular-nums">
          {row.x.toFixed(0)}, {row.y.toFixed(0)}, {row.z.toFixed(0)}
          <div className="text-[10px] text-text-dim/70">
            {dist.toFixed(1)} LY from Sol
          </div>
        </span>
      );
    }

    case 'population':
      return (
        <span className="text-text-dim text-xs">
          {formatPopulation(row.population)}
        </span>
      );

    case 'score': {
      const tier = ratingTier(row.score);
      return (
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
      );
    }

    case 'economy':
      return <span className="text-text-dim text-xs">{row.economy ?? '—'}</span>;

    case 'distanceRef':
      return (
        <span className="text-text-dim text-xs tabular-nums">
          {row.distance != null ? `${row.distance.toFixed(2)} LY` : '—'}
        </span>
      );

    case 'timestamp':
      return (
        <span className="text-text-dim text-[10px]">
          {row.timestamp ? new Date(row.timestamp).toLocaleDateString() : '—'}
        </span>
      );

    case 'externalLinks':
      return (
        <span className="space-x-2 whitespace-nowrap">
          <a
            href={`https://spansh.co.uk/system/${row.id64}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-orange text-[11px] hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            Spansh↗
          </a>
          <a
            href={`https://inara.cz/starsystem/?search=${encodeURIComponent(row.name)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-cyan text-[11px] hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            Inara↗
          </a>
        </span>
      );
  }
}
