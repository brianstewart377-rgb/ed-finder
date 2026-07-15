import { ChevronRight } from 'lucide-react';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import type { ClusterResult } from './useClusterSearch';

export interface ClusterResultCardProps {
  cluster: ClusterResult;
  requiredEconomies: Set<string>;
  onOpenDetail: (id64: number) => void;
}

const ECONOMY_DISPLAY: { key: string; countKey: keyof ClusterResult; bestKey: keyof ClusterResult }[] = [
  { key: 'Agriculture', countKey: 'agriculture_count',  bestKey: 'agriculture_best'  },
  { key: 'Refinery',    countKey: 'refinery_count',     bestKey: 'refinery_best'     },
  { key: 'Industrial',  countKey: 'industrial_count',   bestKey: 'industrial_best'   },
  { key: 'HighTech',    countKey: 'hightech_count',     bestKey: 'hightech_best'     },
  { key: 'Military',    countKey: 'military_count',     bestKey: 'military_best'     },
  { key: 'Tourism',     countKey: 'tourism_count',      bestKey: 'tourism_best'      },
];

export function ClusterResultCard({ cluster, requiredEconomies, onOpenDetail }: ClusterResultCardProps) {
  const distLabel = cluster.distance_ly != null
    ? `${cluster.distance_ly.toFixed(1)} LY`
    : '—';

  return (
    <article
      data-testid={`cluster-result-${cluster.anchor_id64}`}
      className="panel-thin overflow-hidden transition-all duration-200 hover:border-orange/40 hover:-translate-y-[1px] cursor-pointer"
      onClick={() => onOpenDetail(cluster.anchor_id64)}
    >
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-text truncate">
              {cluster.anchor_name}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-xs text-text-dim">
              {cluster.galaxy_region ?? 'Unknown region'}
            </span>
            <span className="text-text-dim text-[10px]">·</span>
            <span className="font-mono text-xs text-orange">
              Coverage: {cluster.coverage_score.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-xs tabular-nums text-silver px-2 py-0.5 rounded-md bg-bg3/60 border border-border">
            {distLabel}
          </span>
          <ChevronRight size={14} className="text-text-dim" />
        </div>
      </div>

      {/* Economy grid */}
      <div className="border-t border-border/70 px-4 py-3">
        <div className="grid grid-cols-3 gap-2">
          {ECONOMY_DISPLAY.map(({ key, countKey, bestKey }) => {
            const count = (cluster[countKey] as number) ?? 0;
            const best  = (cluster[bestKey] as number) ?? 0;
            const isRequired = requiredEconomies.has(key);
            const color = economyColor(key);

            return (
              <div
                key={key}
                className={[
                  'rounded border px-2 py-1.5 transition-opacity',
                  isRequired
                    ? 'border-border bg-bg3/80'
                    : 'border-border/40 bg-bg3/30 opacity-50',
                ].join(' ')}
              >
                <div
                  className="font-mono text-[10px] uppercase tracking-wide"
                  style={{ color }}
                >
                  {key}
                </div>
                <div className="font-mono text-sm font-bold text-text tabular-nums">
                  {count}
                </div>
                <div className="font-mono text-[10px] text-text-dim">
                  best: {best}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border/70 px-4 py-2 flex items-center gap-3 font-mono text-[10px] text-text-dim">
        <span>
          <span className="text-orange font-bold">{cluster.total_viable}</span> viable systems
        </span>
        <span>·</span>
        <span>Diversity: <span className="text-text">{cluster.economy_diversity}</span></span>
        <span>·</span>
        <span>Radius: <span className="text-text">{cluster.cluster_radius_ly.toFixed(0)} LY</span></span>
      </div>
    </article>
  );
}
