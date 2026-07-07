export function AdminAuthPanel({
  tokenDraft,
  onTokenDraftChange,
  hasToken,
  onSave,
  onForget,
}: {
  tokenDraft: string;
  onTokenDraftChange: (next: string) => void;
  hasToken: boolean;
  onSave: () => void;
  onForget: () => void;
}) {
  return (
    <section className="panel p-5 space-y-2">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        1. Admin token
      </h3>
      <p className="text-silver-dk text-[11px]">
        Required for enrichment status and write actions. Stored in <code className="text-orange-lt">sessionStorage</code> —
        forgotten when this tab closes.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="password"
          value={tokenDraft}
          onChange={(e) => onTokenDraftChange(e.target.value)}
          placeholder="X-Admin-Token"
          data-testid="admin-token-input"
          className="flex-1 min-w-[220px]"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={onSave}
          data-testid="admin-token-save"
          className="btn-primary text-[11px] py-1.5 px-3"
        >
          Save
        </button>
        {hasToken && (
          <button
            type="button"
            onClick={onForget}
            data-testid="admin-token-forget"
            className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-red/40 bg-red/10 text-red hover:bg-red/20 font-mono"
          >
            Forget
          </button>
        )}
        <span
          data-testid="admin-token-status"
          className={[
            'font-mono text-[10px] uppercase tracking-wider',
            hasToken ? 'text-green' : 'text-silver-dk',
          ].join(' ')}
        >
          {hasToken ? '● Token set' : '○ No token'}
        </span>
      </div>
    </section>
  );
}
