import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';
import type { SystemArchetypeResponse, SystemDetail } from '@/types/api';
import {
  type ColonyProjectObjective,
  type ColonyProjectStartApproach,
} from '@/features/colony-planner/plannerDraftContext';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { useSystemDetail } from './useSystemDetail';
import { useSystemArchetype } from './useSystemArchetype';
import { ArchetypeAssessment } from './ArchetypeAssessment';
import { buildFallbackArchetype } from './systemDetailFallbackArchetype';
import { ColonyPlannerEntryPoint } from './systemDetailPlannerEntry';
import {
  BodiesSection,
  ExplorationValue,
  ExternalLinks,
  ModalHeader,
  Section,
  StationsSection,
  SystemInfoGrid,
} from './systemDetailSections';

export interface SystemDetailModalProps {
  id64:    number;
  onClose: () => void;
  focusIntent?: 'colony-planner' | null;
  savedForLater?: boolean;
  saveForLaterState?: 'idle' | 'saving' | 'removing';
  onToggleSaveForLater?: (context: {
    system: SystemDetail;
    archetype: SystemArchetypeResponse | null;
  }) => void;
  onStartPlan?: (
    system: SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => void;
  /** Renders alongside Spansh / Inara / EDSM so callers can wire up
   *  Watchlist / Pin / Compare / Show-on-map without this component knowing
   *  about those features. Receives the loaded SystemDetail or null while
   *  the fetch is in flight. */
  renderActions?: (context: {
    system: SystemDetail | null;
    archetype: SystemArchetypeResponse | null;
  }) => ReactNode;
}

/**
 * Full system-detail modal. Renders on top of the current tab via a
 * fixed-position overlay; closes on:
 *   • Escape key
 *   • click on the dim backdrop (not the content)
 *   • the X button in the header
 *
 * Body scroll is locked while the modal is open so the page underneath
 * doesn't scroll when you wheel the modal content.
 */
export function SystemDetailModal({
  id64,
  onClose,
  focusIntent = null,
  savedForLater = false,
  saveForLaterState = 'idle',
  onToggleSaveForLater,
  onStartPlan,
  renderActions,
}: SystemDetailModalProps) {
  const { data, loading, error, refetch } = useSystemDetail(id64);
  const {
    data: archetypeData,
    loading: archetypeLoading,
    error: archetypeError,
    refetch: refetchArchetype,
  } = useSystemArchetype(id64);
  const [planStartOpen, setPlanStartOpen] = useState(false);
  const [selectedObjective, setSelectedObjective] = useState<ColonyProjectObjective | null>(null);
  const [selectedStartApproach, setSelectedStartApproach] = useState<ColonyProjectStartApproach | null>(null);
  const loadedSystemId = data?.id64 ?? null;
  const fallbackArchetype = useMemo(() => buildFallbackArchetype(data), [data]);
  const effectiveArchetype = archetypeData ?? fallbackArchetype;
  const archetypeWarning = archetypeError && effectiveArchetype
    ? 'Using the development snapshot already loaded with system detail while the live archetype service is unavailable.'
    : null;
  const showArchetypeLoading = archetypeLoading && !effectiveArchetype;
  const renderedActions = renderActions?.({ system: data, archetype: effectiveArchetype });

  // Esc closes the modal. Body scroll lock only fires if we're actually
  // mounted (id64 changes between mounts so this is per-open).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    if (loadedSystemId == null) return;
    setPlanStartOpen(focusIntent === 'colony-planner' && Boolean(onStartPlan));
    setSelectedObjective(null);
    setSelectedStartApproach(null);
  }, [focusIntent, loadedSystemId, onStartPlan]);

  return (
    <div
      data-testid="system-detail-modal"
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-[radial-gradient(circle_at_top,rgba(111,229,255,0.1),transparent_32%),radial-gradient(circle_at_top_right,rgba(255,122,20,0.14),transparent_34%),rgba(4,6,10,0.82)] backdrop-blur-xl px-4 py-8 sm:py-12"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="system-detail-title"
    >
      <article
        className="panel relative w-full max-w-6xl animate-fade-up overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          data-testid="system-detail-close"
          aria-label="Close system details"
          className="premium-toolbar absolute right-4 top-4 z-50 grid h-10 w-10 place-items-center rounded-full text-white transition-colors hover:border-orange/70 hover:bg-orange hover:text-bg1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          <X size={19} strokeWidth={3} />
        </button>
        <ModalHeader
          system={data}
          id64={id64}
          loading={loading}
          hasError={Boolean(error)}
        />

        <div className="space-y-5 px-5 py-5 text-sm sm:px-6">
          {loading && (
            <div className="premium-subpanel px-4 py-8 text-center">
              <div className="flex justify-center">
                <SemanticStatusBadge label="Loading" tone="loading" />
              </div>
              <p className="mt-3 text-sm text-silver">
                Loading system detail for inspection.
              </p>
              <p className="mt-1 text-xs text-silver-dk">
                Review the selected system here, then move into Colony Planner when the context is ready.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-chunk-lg border border-red/50 bg-[linear-gradient(180deg,rgba(248,113,113,0.16),rgba(127,29,29,0.2))] p-4 text-sm text-red shadow-[0_18px_40px_-28px_rgba(127,29,29,0.9)]">
              <div className="flex flex-wrap items-center gap-2">
                <SemanticStatusBadge label="Unavailable" tone="unavailable" />
                <span className="font-semibold">System detail is unavailable right now.</span>
              </div>
              <p className="mt-2 text-silver">
                Retry the request, or return to Explore and inspect another system.
              </p>
              <button
                type="button"
                onClick={refetch}
                className="btn-metal mt-3 text-xs font-mono font-bold"
              >
                Retry
              </button>
            </div>
          )}

          {data && (
            <>
              <ColonyPlannerEntryPoint
                system={data}
                archetype={effectiveArchetype}
                savedForLater={savedForLater}
                saveForLaterState={saveForLaterState}
                planningOpen={planStartOpen}
                selectedObjective={selectedObjective}
                selectedStartApproach={selectedStartApproach}
                onToggleSaveForLater={onToggleSaveForLater}
                onTogglePlanStart={() => setPlanStartOpen((open) => !open)}
                onSelectObjective={setSelectedObjective}
                onSelectStartApproach={setSelectedStartApproach}
                onStartPlan={onStartPlan}
              />
              <Section title="Archetype assessment">
                <ArchetypeAssessment
                  archetype={effectiveArchetype}
                  loading={showArchetypeLoading}
                  error={archetypeError}
                  warning={archetypeWarning}
                  onRetry={refetchArchetype}
                />
              </Section>
              <SystemInfoGrid sys={data} />
              <BodiesSection bodies={data.bodies} systemName={data.name} />
              <StationsSection stations={data.stations} />
              <ExplorationValue value={data.exploration_value} />


              <ExternalLinks sys={data} />
            </>
          )}

          {renderedActions ? (
            <div className="premium-toolbar flex flex-wrap gap-2 rounded-2xl border-t border-border px-3 py-3">
              {renderedActions}
            </div>
          ) : null}
        </div>
      </article>
    </div>
  );
}
