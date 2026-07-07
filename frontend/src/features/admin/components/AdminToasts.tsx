import type { UseAdmin } from '../useAdmin';

export function ActionToast({
  state,
  onDismiss,
}: { state: UseAdmin['actionState']; onDismiss: () => void }) {
  if (state.kind === 'idle' || state.kind === 'busy') return null;
  const ok = state.kind === 'ok';
  return (
    <div
      data-testid="admin-action-toast"
      className={[
        'rounded-chunk-sm border p-2.5 font-mono text-xs flex items-center gap-2',
        ok ? 'border-green/50 text-green' : 'border-red/50 text-red',
      ].join(' ')}
      style={{ background: ok ? 'rgba(74,222,128,0.10)' : 'rgba(248,113,113,0.10)' }}
    >
      <span>{ok ? '✓' : '✕'}</span>
      <span className="font-bold">{state.what}:</span>
      <span>{state.message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-auto opacity-70 hover:opacity-100"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}
