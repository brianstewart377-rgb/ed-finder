import type { ReactNode } from 'react';
import {
  formatPopulationForSystem,
  formatDistance,
  formatCoords,
  distanceFromSol,
  systemStatusLabel,
} from '@/lib/format';
import { archetypeTierFromScore, formatArchetypeLabel } from '@/lib/archetypes';

/**
 * Minimal row shape that every "list of systems" feature shares (Watchlist,
 * Pinned, Compare results, Cluster anchors, …). Optional fields are null
 * when the source doesn't supply them — we prefer an explicit null over a
 * missing key so the column render is a pure function of the row.
 */
export interface SystemRow {
  id64:         number;
  name:         string;
  x:            number | null;
  y:            number | null;
  z:            number | null;
  population:   number | null;
  is_colonised: boolean;
  is_being_colonised?: boolean | null;
  score:        number | null;
  economy:      string | null;
  archetype?:   string | null;
  secondaryArchetype?: string | null;
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
  /** If supplied, clicking anywhere outside the actions cell triggers this.
   *  Used to open the system-detail modal from any table-based tab. */
  onRowClick?: (id64: number) => void;
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
  rows, columns, timestampLabel = 'Added', renderActions, rowTestIdPrefix, onRowClick,
}: SystemTableProps) {
  return (
    <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
      background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
    }}>
      <table className="w-full text-sm font-mono">
        <thead className="text-silver-dk text-[10px] uppercase tracking-[0.16em]" style={{
          background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
          borderBottom: '1px solid hsl(216 10% 24%)',
        }}>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className={[
                  'px-3 py-2.5',
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
              <th className="px-3 py-2.5 text-right">Actions</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <SystemTableRow
              key={row.id64}
              row={row}
              columns={columns}
              renderActions={renderActions}
              rowTestIdPrefix={rowTestIdPrefix}
              onRowClick={onRowClick}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Column renderers ──────────────────────────────────────────────────────

function SystemTableRow({
  row,
  columns,
  renderActions,
  rowTestIdPrefix,
  onRowClick,
}: {
  row: SystemRow;
  columns: SystemTableColumn[];
  renderActions?: (row: SystemRow) => ReactNode;
  rowTestIdPrefix?: string;
  onRowClick?: (id64: number) => void;
}) {
  const systemId64 = Number(row.id64);
  const canOpenRow = Boolean(onRowClick && Number.isFinite(systemId64) && systemId64 > 0);

  return (
    <tr
      data-testid={rowTestIdPrefix ? `${rowTestIdPrefix}${row.id64}` : undefined}
      onClick={canOpenRow ? () => onRowClick?.(systemId64) : undefined}
      className={[
        'border-t border-border/50 hover:bg-orange/5 transition-colors',
        canOpenRow ? 'cursor-pointer' : '',
      ].join(' ')}
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
        <td
          className="px-3 py-2 text-right space-x-1 whitespace-nowrap"
          onClick={(e) => e.stopPropagation()}
        >
          {renderActions(row)}
        </td>
      )}
    </tr>
  );
}

function headerLabel(col: SystemTableColumn, timestampLabel: string): string {
  switch (col) {
    case 'system':        return 'System';
    case 'coords':        return 'Coords (LY)';
    case 'population':    return 'Population';
    case 'score':         return 'Development';
    case 'economy':       return 'Archetype';
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
          {systemStatusLabel(row) !== 'Available' && (
            <span className="ml-2 text-[9px] px-1 py-0.5 rounded bg-red/20 text-red border border-red/40">
              {systemStatusLabel(row) === 'Colonised' ? 'COL' : 'BUILD'}
            </span>
          )}
        </>
      );

    case 'coords': {
      const dist = distanceFromSol(row, row.id64);
      return (
        <span className="text-text-dim text-xs tabular-nums">
          {formatCoords(row, row.id64)}
          {dist != null && (
            <div className="text-[10px] text-text-dim/70">
              {dist.toFixed(1)} LY from Sol
            </div>
          )}
        </span>
      );
    }

    case 'population':
      return (
        <span className="text-text-dim text-xs">
          {formatPopulationForSystem(row)}
        </span>
      );

    case 'score': {
      const tier = archetypeTierFromScore(row.score);
      return (
        <span
          className={[
            'inline-block px-2 py-0.5 rounded border text-[11px] font-bold',
            tier === 'S' && 'bg-cyan/20 text-cyan border-cyan/50',
            tier === 'A' && 'bg-green/20 text-green border-green/50',
            tier === 'B' && 'bg-gold/20 text-gold border-gold/50',
            tier === 'C' && 'bg-orange/20 text-orange border-orange/50',
            tier === 'D' && 'bg-red/20 text-red border-red/50',
            tier == null && 'bg-bg4 text-text-dim border-border',
          ].filter(Boolean).join(' ')}
          title={`Development score: ${row.score ?? '—'}/100`}
        >
          {tier ?? '—'} {row.score ?? '—'}
        </span>
      );
    }

    case 'economy':
      return (
        <div className="space-y-1 text-xs">
          <div className={row.archetype ? 'text-cyan' : 'text-text-dim'}>
            {row.archetype ? formatArchetypeLabel(row.archetype) : row.economy ?? '—'}
          </div>
          {row.secondaryArchetype && (
            <div className="text-[10px] text-text-dim">
              {formatArchetypeLabel(row.secondaryArchetype)}
            </div>
          )}
        </div>
      );

    case 'distanceRef':
      return (
        <span className="text-text-dim text-xs tabular-nums">
          {formatDistance(row.distance) ?? '—'}
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
