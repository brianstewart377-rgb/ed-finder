import { useEffect, useState } from 'react';
import { ExternalLink, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import type { SystemDetail } from '@/types/api';
import { useHashRoute } from '@/hooks/useHashRoute';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';

type State = { kind: 'none' | 'loading' | 'available' | 'invalid' | 'unavailable'; data: SystemDetail | null; error: string | null };

export function SelectedSystemRouteBar() {
  const route = useHashRoute();
  const [state, setState] = useState<State>({ kind: 'none', data: null, error: null });
  const id64 = route.contextSystemId;

  useEffect(() => {
    if (route.selectedSystemRouteStatus === 'invalid') {
      setState({ kind: 'invalid', data: null, error: 'The requested system link is invalid.' });
      return;
    }
    if (id64 == null) {
      setState({ kind: 'none', data: null, error: null });
      return;
    }
    let active = true;
    setState({ kind: 'loading', data: null, error: null });
    void api.system(id64).then(
      (data) => active && setState({ kind: 'available', data, error: null }),
      (error: unknown) => active && setState({ kind: 'unavailable', data: null, error: error instanceof Error ? error.message : 'The requested system is unavailable.' }),
    );
    return () => { active = false; };
  }, [id64, route.selectedSystemRouteStatus]);

  if (state.kind === 'none') return null;
  if (state.kind === 'invalid' || state.kind === 'unavailable') {
    return (
      <section role="alert" data-testid="selected-system-context-error" className="fixed left-4 right-4 top-24 z-50 mx-auto max-w-4xl rounded-chunk-lg border border-red/45 bg-bg1/95 p-4 shadow-metal">
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-red">Requested system unavailable</p>
        <p className="mt-1 text-sm text-silver">{state.error}</p>
        <button type="button" onClick={() => { window.location.hash = '#finder'; }} data-testid="selected-system-context-recover" className="mt-3 inline-flex items-center gap-2 rounded-chunk-sm border border-red/50 bg-red/10 px-3 py-2 text-xs font-mono font-bold text-red hover:bg-red/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red/80">
          <RotateCcw size={14} aria-hidden /> Return to Finder
        </button>
      </section>
    );
  }

  const loading = state.kind === 'loading';
  return (
    <section aria-label="Selected system context" data-testid="selected-system-context-bar" className="fixed left-4 right-4 top-24 z-50 mx-auto max-w-4xl rounded-chunk-lg border border-cyan/30 bg-bg1/95 px-4 py-3 shadow-metal">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">Selected system</p>
          <p data-testid="selected-system-context-name" className="mt-1 truncate text-base font-semibold text-text">{loading ? 'Loading selected system...' : state.data?.name || 'Unknown system'}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <SemanticStatusBadge label={loading ? 'Loading system detail' : 'System detail available'} tone={loading ? 'loading' : 'available'} testId="selected-system-context-posture" />
            <span data-testid="selected-system-context-id64" className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">ID64 {id64}</span>
          </div>
        </div>
        {id64 != null ? <button type="button" onClick={() => route.openSystem(id64)} data-testid="selected-system-context-inspect" className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80"><ExternalLink size={14} aria-hidden />Inspect system</button> : null}
      </div>
    </section>
  );
}
