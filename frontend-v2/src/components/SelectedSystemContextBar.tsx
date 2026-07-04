import { AlertTriangle, ExternalLink, RotateCcw } from 'lucide-react';
import type { SelectedSystemContext } from '@/features/system-detail/useSelectedSystemContext';
import { SemanticStatusBadge } from './SemanticStatusBadge';

export interface SelectedSystemContextBarProps {
  context: SelectedSystemContext;
  onInspect?: (id64: number) => void;
  onReturnToFinder: () => void;
}

/**
 * Route-owned selected-system context for Finder, Inspect, and Plan. This is
 * deliberately separate from a modal and from an active planner project.
 */
export function SelectedSystemContextBar({
  context,
  onInspect,
  onReturnToFinder,
}: SelectedSystemContextBarProps) {
  if (context.resolution === 'none') return null;

  if (context.resolution === 'invalid' || context.resolution === 'unavailable') {
    const title = context.resolution === 'invalid'
      ? 'Requested system link is invalid'
      : 'Requested system is unavailable';

    return (
      <section
        role="alert"
        aria-live="assertive"
        data-testid="selected-system-context-error"
        className="mb-5 flex flex-wrap items-start justify-between gap-3 rounded-chunk-lg border border-red/45 bg-red/10 px-4 py-3"
      >
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle className="mt-0.5 shrink-0 text-red" size={18} aria-hidden />
          <div>
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-red">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-silver">{context.error}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onReturnToFinder}
          data-testid="selected-system-context-recover"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-red/50 bg-red/10 px-3 py-2 text-xs font-mono font-bold text-red hover:bg-red/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red/80"
        >
          <RotateCcw size={14} aria-hidden />
          Return to Finder
        </button>
      </section>
    );
  }

  const isLoading = context.resolution === 'loading';
  const name = isLoading ? 'Loading selected system...' : context.data?.name || 'Unknown system';
  const posture = isLoading ? 'Loading system detail' : 'System detail available';

  return (
    <section
      aria-label="Selected system context"
      data-testid="selected-system-context-bar"
      className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-chunk-lg border border-cyan/30 bg-bg2/85 px-4 py-3 shadow-[0_14px_30px_-26px_rgba(0,0,0,0.9)]"
    >
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">Selected system</p>
        <p data-testid="selected-system-context-name" className="mt-1 truncate text-base font-semibold text-text sm:text-lg">{name}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <SemanticStatusBadge
            label={posture}
            tone={isLoading ? 'loading' : 'available'}
            testId="selected-system-context-posture"
          />
          <span data-testid="selected-system-context-id64" className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            ID64 {context.id64}
          </span>
        </div>
      </div>
      {onInspect && context.id64 != null ? (
        <button
          type="button"
          onClick={() => onInspect(context.id64 as number)}
          data-testid="selected-system-context-inspect"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80"
        >
          <ExternalLink size={14} aria-hidden />
          Inspect system
        </button>
      ) : null}
    </section>
  );
}
