import { useState, useCallback } from 'react';
import { ChevronRight, Plus } from 'lucide-react';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import { useExpansionPlanStore } from '@/features/expansion-plans/expansionPlanStore';
import type { ExpansionPlanSlotInput } from '@/features/expansion-plans/expansionPlanStore';
import type { ClusterResult } from './useClusterSearch';
import type { SlotMatch } from './useClusterSearch';

export interface ClusterResultCardProps {
  cluster: ClusterResult;
  requiredEconomies: Set<string>;
  onOpenDetail: (id64: number) => void;
  onSystemClick?: (id64: number) => void;
}

const ECONOMY_DISPLAY: { key: string; countKey: keyof ClusterResult; bestKey: keyof ClusterResult }[] = [
  { key: 'Agriculture', countKey: 'agriculture_count',  bestKey: 'agriculture_best'  },
  { key: 'Refinery',    countKey: 'refinery_count',     bestKey: 'refinery_best'     },
  { key: 'Industrial',  countKey: 'industrial_count',   bestKey: 'industrial_best'   },
  { key: 'HighTech',    countKey: 'hightech_count',     bestKey: 'hightech_best'     },
  { key: 'Military',    countKey: 'military_count',     bestKey: 'military_best'     },
  { key: 'Tourism',     countKey: 'tourism_count',      bestKey: 'tourism_best'      },
];

export function ClusterResultCard({ cluster, requiredEconomies, onOpenDetail, onSystemClick }: ClusterResultCardProps) {
  const distLabel = cluster.distance_ly != null
    ? `${cluster.distance_ly.toFixed(1)} LY`
    : '—';

  const hasSlots = cluster.slots && cluster.slots.length > 0;

  // Local state for slot pick reordering and expansion toggle
  const [expandedSlot, setExpandedSlot] = useState<number | null>(null);
  const [slotPicks, setSlotPicks] = useState<Record<number, number>>({});

  // Create-plan confirmation state
  const [planCreated, setPlanCreated] = useState(false);
  const createPlan = useExpansionPlanStore((s) => s.createPlan);

  const handlePickAlternate = useCallback((slotIndex: number, matchIndex: number) => {
    setSlotPicks((prev) => ({ ...prev, [slotIndex]: matchIndex }));
    setExpandedSlot(null);
  }, []);

  const handleCreatePlan = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (!hasSlots) return;

    const slotInputs: ExpansionPlanSlotInput[] = cluster.slots!.map((slot) => {
      const pickIndex = slotPicks[slot.slot_index] ?? 0;
      const match: SlotMatch | undefined = slot.matches[pickIndex];
      return {
        slot_index: slot.slot_index,
        label: slot.label,
        economies: slot.economies,
        system_id64: match?.system_id64 ?? 0,
        system_name: match?.system_name ?? '(no match)',
        scores: match?.scores ?? {},
        distance_from_anchor_ly: match?.distance_from_anchor_ly ?? null,
      };
    });

    createPlan({
      anchor_system_id64: cluster.anchor_id64,
      anchor_system_name: cluster.anchor_name,
      galaxy_region: cluster.galaxy_region,
      slots: slotInputs,
    });

    setPlanCreated(true);
    setTimeout(() => setPlanCreated(false), 2000);
  }, [cluster, hasSlots, slotPicks, createPlan]);

  return (
    <article
      data-testid={`cluster-result-${cluster.anchor_id64}`}
      className="panel-thin overflow-hidden transition-all duration-200 hover:border-orange/40 hover:-translate-y-[1px]"
    >
      {/* Header — clickable to open anchor detail */}
      <div
        className="px-4 py-3 flex items-center justify-between gap-3 cursor-pointer"
        onClick={() => onOpenDetail(cluster.anchor_id64)}
      >
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

      {/* Slot-based detail (new format) */}
      {hasSlots ? (
        <div className="border-t border-border/70 px-4 py-3 space-y-3">
          {cluster.slots!.map((slot) => {
            const primaryEcon = slot.economies[0] ?? '';
            const slotColor = economyColor(primaryEcon);
            const pickIndex = slotPicks[slot.slot_index] ?? 0;
            const bestMatch = slot.matches[pickIndex];
            const moreCount = slot.matches.length - 1;
            const isExpanded = expandedSlot === slot.slot_index;

            return (
              <div key={slot.slot_index}>
                <div
                  className="font-mono text-[10px] uppercase tracking-[0.12em] mb-1.5"
                  style={{ color: slotColor }}
                >
                  {slot.label}
                </div>
                {bestMatch ? (
                  <div className="space-y-1">
                    <button
                      type="button"
                      className="font-mono text-sm text-text hover:text-orange transition-colors text-left truncate block max-w-full"
                      title={bestMatch.system_name}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSystemClick?.(bestMatch.system_id64);
                      }}
                    >
                      ► {bestMatch.system_name}
                    </button>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {Object.entries(bestMatch.scores).map(([econ, score]) => (
                        <span
                          key={econ}
                          className="font-mono text-[10px] px-1.5 py-0.5 rounded border"
                          style={{
                            color: economyColor(econ),
                            borderColor: `${economyColor(econ)}40`,
                            backgroundColor: `${economyColor(econ)}10`,
                          }}
                        >
                          {econ.slice(0, 4)} {score}
                        </span>
                      ))}
                      <span className="font-mono text-[10px] text-text-dim">
                        · {bestMatch.distance_from_anchor_ly} LY from anchor
                      </span>
                    </div>
                    {moreCount > 0 && (
                      <button
                        type="button"
                        className="font-mono text-[10px] text-cyan hover:text-white transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedSlot(isExpanded ? null : slot.slot_index);
                        }}
                      >
                        + {moreCount} more
                      </button>
                    )}
                    {isExpanded && moreCount > 0 && (
                      <div className="mt-1.5 ml-2 pl-3 border-l-2 border-border/50 space-y-1">
                        {slot.matches.slice(1).map((m, mi) => {
                          const matchIndex = mi + 1;
                          return (
                            <button
                              key={m.system_id64}
                              type="button"
                              className="block w-full text-left font-mono text-xs text-text-dim hover:text-orange transition-colors truncate"
                              title={m.system_name}
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePickAlternate(slot.slot_index, matchIndex);
                              }}
                            >
                              {m.system_name}
                              <span className="ml-2 text-[10px] text-text-dim/60">
                                {Object.entries(m.scores).map(([e, s]) => `${e.slice(0, 4)} ${s}`).join(' · ')}
                                {' · '}{m.distance_from_anchor_ly} LY
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="font-mono text-[10px] text-text-dim italic">
                    No matching system found
                  </div>
                )}
              </div>
            );
          })}

          {/* Create Expansion Plan button */}
          <button
            type="button"
            className={[
              'w-full py-2 rounded border font-mono text-[11px] uppercase tracking-wide transition-all',
              planCreated
                ? 'border-green/50 text-green bg-green/10'
                : 'border-orange/50 text-orange hover:bg-orange/10 hover:border-orange',
            ].join(' ')}
            onClick={handleCreatePlan}
            disabled={planCreated}
          >
            {planCreated ? (
              '✓ Plan Created'
            ) : (
              <><Plus size={13} className="inline mr-1.5" />Create Expansion Plan</>
            )}
          </button>
        </div>
      ) : (
        /* Legacy economy grid (no slot data) */
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
      )}

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
