import type { SavedSystemNoticeState } from './savedSystems';

export function SavedSystemNotice({
  notice,
  onDismiss,
  onOpenMyWork,
}: {
  notice: SavedSystemNoticeState | null;
  onDismiss: () => void;
  onOpenMyWork: () => void;
}) {
  if (!notice) return null;
  const isError = notice.tone === 'error';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      data-testid="saved-system-notice"
      className={[
        'fixed right-4 top-4 z-50 max-w-sm rounded-chunk-lg border p-3 font-mono text-xs shadow-metal backdrop-blur-xl',
        isError
          ? 'border-red/45 bg-[linear-gradient(180deg,rgba(248,113,113,0.18),rgba(127,29,29,0.22))] text-red'
          : 'border-green/40 bg-[linear-gradient(180deg,rgba(74,222,128,0.16),rgba(15,23,42,0.92))] text-green',
      ].join(' ')}
    >
      <div className="font-bold tracking-[0.08em]">{notice.message}</div>
      <p className="mt-1 leading-relaxed text-silver">{notice.detail}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {notice.actionLabel ? (
          <button
            type="button"
            onClick={onOpenMyWork}
            className="rounded-chunk-sm border border-green/40 bg-green/10 px-3 py-1.5 font-bold text-green hover:bg-green/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/80"
          >
            {notice.actionLabel}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-chunk-sm border border-border bg-bg4 px-3 py-1.5 font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
