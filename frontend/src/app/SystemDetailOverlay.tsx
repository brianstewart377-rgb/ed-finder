import { Suspense, lazy } from 'react';
import { toCompareSnapshot } from '@/app/compareSnapshot';
import type { ColonyProjectObjective, ColonyProjectStartApproach } from '@/features/colony-planner/plannerDraftContext';
import { toPinnedEntry } from '@/features/pinned/pinnedEntry';
import type { UseCompare } from '@/features/compare/useCompare';
import type { UsePinned } from '@/features/pinned/usePinned';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { SavedSystemActionState } from '@/app/savedSystems';
import type { SystemDetail } from '@/types/api';
import type { HashRoute } from '@/hooks/useHashRoute';

const LazySystemDetailModal = lazy(async () => ({ default: (await import('@/features/system-detail/SystemDetailModal')).SystemDetailModal }));

interface SystemDetailOverlayProps {
  selectedSystemId: number | null;
  detailFocus: 'colony-planner' | null;
  shellSystemData: SystemDetail | null;
  watchlist: UseWatchlist;
  pinned: UsePinned;
  compare: UseCompare;
  savedSystemActionState: Record<number, SavedSystemActionState>;
  toggleSavedSystem: (
    id64: number,
    hint: {
      name?: string | null;
      x?: number | null;
      y?: number | null;
      z?: number | null;
      population?: number | null;
      is_colonised?: boolean;
      developmentScore?: number | null;
      economy_suggestion?: string | null;
      primary_archetype?: string | null;
      secondary_archetype?: string | null;
      buildability_score?: number | null;
      purity_score?: number | null;
    },
  ) => Promise<void>;
  startPlanFromSystemDetail: (
    system: SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => void;
  closeSystemDetail: HashRoute['closeSystem'];
}

export function SystemDetailOverlay({
  selectedSystemId,
  detailFocus,
  shellSystemData,
  watchlist,
  pinned,
  compare,
  savedSystemActionState,
  toggleSavedSystem,
  startPlanFromSystemDetail,
  closeSystemDetail,
}: SystemDetailOverlayProps) {
  if (selectedSystemId === null) return null;

  return (
    <Suspense fallback={null}>
      <LazySystemDetailModal
        id64={selectedSystemId}
        focusIntent={detailFocus}
        onClose={closeSystemDetail}
        savedForLater={shellSystemData ? watchlist.has(shellSystemData.id64) : false}
        saveForLaterState={shellSystemData ? savedSystemActionState[shellSystemData.id64] ?? 'idle' : 'idle'}
        onToggleSaveForLater={(system) => {
          const developmentScore = system.archetype?.overall_development_potential
            ?? system.system.overall_development_potential
            ?? system.system.score
            ?? null;
          void toggleSavedSystem(system.system.id64, {
            name: system.system.name,
            x: system.system.x,
            y: system.system.y,
            z: system.system.z,
            population: system.system.population ?? null,
            is_colonised: !!system.system.is_colonised,
            developmentScore,
            economy_suggestion: system.system.economy_suggestion ?? null,
            primary_archetype: system.archetype?.primary_archetype ?? system.system.primary_archetype ?? null,
            secondary_archetype: system.archetype?.secondary_archetype ?? system.system.secondary_archetype ?? null,
            buildability_score: system.archetype?.buildability_score ?? system.system.buildability_score ?? null,
            purity_score: system.archetype?.purity_score ?? system.system.purity_score ?? null,
          });
        }}
        onStartPlan={startPlanFromSystemDetail}
        renderActions={({ system: sys, archetype }) => (
          <>
            <button
              type="button"
              disabled={!sys}
              onClick={() => sys && pinned.toggle(toPinnedEntry({
                id64: sys.id64,
                name: sys.name,
                coords: { x: sys.x ?? null, y: sys.y ?? null, z: sys.z ?? null },
                population: sys.population ?? null,
                is_colonised: !!sys.is_colonised,
                economy_suggestion: sys.economy_suggestion ?? sys.primary_economy ?? null,
                archetype_score: archetype?.overall_development_potential ?? sys.overall_development_potential ?? sys.score ?? null,
                primary_archetype: archetype?.primary_archetype ?? sys.primary_archetype ?? null,
                secondary_archetype: archetype?.secondary_archetype ?? sys.secondary_archetype ?? null,
                buildability_score: archetype?.buildability_score ?? sys.buildability_score ?? null,
                purity_score: archetype?.purity_score ?? sys.purity_score ?? null,
              }))}
              data-testid="modal-pin-toggle"
              className={[
                'px-2 py-1 rounded font-mono text-[11px] border transition-colors',
                sys && pinned.has(sys.id64)
                  ? 'bg-orange/20 border-orange text-orange'
                  : 'bg-bg4 border-border text-text-dim hover:text-orange hover:border-orange-dk',
                !sys && 'opacity-40 cursor-not-allowed',
              ].filter(Boolean).join(' ')}
            >
              {sys && pinned.has(sys.id64) ? '📌 Pinned - unpin' : '📍 Pin'}
            </button>

            <button
              type="button"
              disabled={!sys}
              onClick={() => sys && compare.toggle(toCompareSnapshot(sys, archetype))}
              data-testid="modal-compare-toggle"
              className={[
                'px-2 py-1 rounded font-mono text-[11px] border transition-colors',
                sys && compare.has(sys.id64)
                  ? 'bg-orange/20 border-orange text-orange'
                  : 'bg-bg4 border-border text-text-dim hover:text-orange hover:border-orange-dk',
                !sys && 'opacity-40 cursor-not-allowed',
              ].filter(Boolean).join(' ')}
            >
              {sys && compare.has(sys.id64) ? '⚖️ In comparison - remove' : '⚖️ Add to Compare'}
            </button>
          </>
        )}
      />
    </Suspense>
  );
}
