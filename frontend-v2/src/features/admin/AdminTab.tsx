import { useState } from 'react';
import type { UseAdmin } from './useAdmin';

export interface AdminTabProps { admin: UseAdmin }

/**
 * Ops dashboard. Three sections:
 *   1. Auth — paste an admin token (sessionStorage).
 *   2. Live status — counts + meta flags + cache stats, auto-refreshing.
 *   3. Actions — Clear cache + Rebuild clusters (both token-gated).
 *
 * No live job-status polling yet — neither admin endpoint exposes one.
 * Adding a /api/admin/jobs/{id} endpoint server-side would let us show a
 * live progress bar for cluster rebuilds; until then a "triggered" toast
 * is honest about what we know.
 */
export function AdminTab({ admin }: AdminTabProps) {
  const [tokenDraft, setTokenDraft] = useState(admin.token);

  return (
    <section data-testid="admin-tab" className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">⚙️ Admin</h2>
        <span className="font-mono text-xs text-text-dim">
          ops console — token-gated actions
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void admin.refresh()}
          data-testid="admin-refresh"
          className="px-2 py-1 rounded bg-bg4 border border-border font-mono text-[11px] text-text-dim hover:text-orange hover:border-orange-dk transition-colors"
        >
          ↺ Refresh
        </button>
      </header>

      {/* ── Auth ─────────────────────────────────────────────────────── */}
      <section className="rounded border border-border p-4 space-y-2">
        <h3 className="font-mono text-orange text-xs uppercase tracking-wider">
          1. Admin token
        </h3>
        <p className="text-text-dim text-[11px]">
          Required for write actions only. Stored in <code className="text-orange">sessionStorage</code> —
          forgotten when this tab closes.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
            placeholder="X-Admin-Token"
            data-testid="admin-token-input"
            className="flex-1 min-w-[220px] bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => admin.setToken(tokenDraft.trim())}
            data-testid="admin-token-save"
            className="px-3 py-1 rounded bg-orange/20 border border-orange/50 text-orange font-mono text-[11px] hover:bg-orange/30"
          >
            Save
          </button>
          {admin.hasToken && (
            <button
              type="button"
              onClick={() => { admin.forgetToken(); setTokenDraft(''); }}
              data-testid="admin-token-forget"
              className="px-3 py-1 rounded bg-red/10 border border-red/40 text-red font-mono text-[11px] hover:bg-red/20"
            >
              Forget
            </button>
          )}
          <span
            data-testid="admin-token-status"
            className={[
              'font-mono text-[10px] uppercase tracking-wider',
              admin.hasToken ? 'text-green' : 'text-text-dim',
            ].join(' ')}
          >
            {admin.hasToken ? '● Token set' : '○ No token'}
          </span>
        </div>
      </section>

      {/* ── Status ───────────────────────────────────────────────────── */}
      <section className="rounded border border-border p-4 space-y-3">
        <h3 className="font-mono text-orange text-xs uppercase tracking-wider">
          2. Live status
        </h3>

        {admin.metaError && (
          <div className="rounded border border-red/50 bg-red/10 p-2 font-mono text-xs text-red">
            {admin.metaError}
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs font-mono">
          {admin.status && (
            <>
              <Stat label="Systems"          value={admin.status.systems_count.toLocaleString()} />
              <Stat label="Bodies"           value={admin.status.body_count.toLocaleString()} />
              <Stat label="Rated"            value={admin.status.rated_count.toLocaleString()} />
              <Stat label="Clustered"        value={admin.status.clustered_count.toLocaleString()} />
              <Stat label="Schema version"   value={admin.status.schema_version} />
              <Stat label="App version"      value={admin.status.version} />
              <Stat label="Last nightly"     value={admin.status.last_nightly_update} highlight={admin.status.last_nightly_update === 'never'} />
              <Flag label="Import complete"  value={admin.status.import_complete} />
              <Flag label="Ratings built"    value={admin.status.ratings_built} />
              <Flag label="Grid built"       value={admin.status.grid_built} />
              <Flag label="Clusters built"   value={admin.status.clusters_built} />
              <Flag label="EDDN enabled"     value={admin.status.eddn_enabled} />
            </>
          )}
          {admin.cache && (
            <>
              <Stat label="Mem cache hits"   value={admin.cache.cache_hits.toLocaleString()} />
              <Stat label="Mem cache misses" value={admin.cache.cache_misses.toLocaleString()} />
              {admin.cache.redis_hits != null && (
                <Stat label="Redis hits"     value={admin.cache.redis_hits.toLocaleString()} />
              )}
              {admin.cache.redis_misses != null && (
                <Stat label="Redis misses"   value={admin.cache.redis_misses.toLocaleString()} />
              )}
              {admin.cache.redis_memory_mb != null && (
                <Stat label="Redis memory"   value={`${admin.cache.redis_memory_mb} MB`} />
              )}
              <Stat label="DB cache rows"    value={admin.cache.db_cache_rows.toLocaleString()} />
            </>
          )}
        </div>

        <p className="text-[10px] text-text-dim font-mono">
          Auto-refreshes every 30s.
          {admin.metaLoading && <span className="text-orange ml-2">⟳ refreshing…</span>}
        </p>
      </section>

      {/* ── Actions ──────────────────────────────────────────────────── */}
      <section className="rounded border border-border p-4 space-y-3">
        <h3 className="font-mono text-orange text-xs uppercase tracking-wider">
          3. Actions
        </h3>

        <ActionToast state={admin.actionState} onDismiss={admin.resetActionState} />

        <div className="grid sm:grid-cols-2 gap-3">
          <ActionCard
            title="Clear cache"
            blurb="Flush Redis + expired api_cache rows. Cheap; safe to retry."
            confirmText="Flush all cached responses?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'clearCache'}
            onClick={admin.clearCache}
            testid="admin-clear-cache"
          />
          <ActionCard
            title="Rebuild clusters"
            blurb="Re-run the dirty-anchor cluster builder in the background. Rate-limited to 1/minute."
            confirmText="Trigger a cluster rebuild now?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'rebuildClusters'}
            onClick={admin.rebuildClusters}
            testid="admin-rebuild-clusters"
          />
        </div>

        {!admin.hasToken && (
          <p className="text-[10px] text-text-dim font-mono">
            Set a token in section 1 to enable actions.
          </p>
        )}
      </section>
    </section>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────────

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={[
      'rounded p-2 border bg-bg3/40',
      highlight ? 'border-red/40 bg-red/10' : 'border-border',
    ].join(' ')}>
      <div className="text-text-dim uppercase tracking-wider text-[10px]">{label}</div>
      <div className={['tabular-nums font-bold', highlight ? 'text-red' : 'text-text'].join(' ')}>
        {value}
      </div>
    </div>
  );
}

function Flag({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="rounded p-2 border border-border bg-bg3/40 flex items-center justify-between">
      <span className="text-text-dim uppercase tracking-wider text-[10px]">{label}</span>
      <span className={value ? 'text-green' : 'text-red'}>
        {value ? '✓' : '✕'}
      </span>
    </div>
  );
}

function ActionCard({
  title, blurb, confirmText, disabled, busy, onClick, testid,
}: {
  title: string; blurb: string; confirmText: string;
  disabled: boolean; busy: boolean;
  onClick: () => Promise<void>; testid: string;
}) {
  return (
    <div className="rounded border border-border p-3 space-y-2 bg-bg3/40">
      <div className="font-mono text-orange text-xs">{title}</div>
      <p className="text-[10px] text-text-dim leading-snug">{blurb}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => { if (confirm(confirmText)) void onClick(); }}
        data-testid={testid}
        className={[
          'w-full px-2 py-1.5 rounded font-mono text-xs border transition-colors',
          disabled
            ? 'bg-bg4 border-border text-text-dim opacity-50 cursor-not-allowed'
            : 'bg-orange/20 border-orange/50 text-orange hover:bg-orange/30',
        ].join(' ')}
      >
        {busy ? '⟳ Working…' : 'Run'}
      </button>
    </div>
  );
}

function ActionToast({
  state, onDismiss,
}: { state: UseAdmin['actionState']; onDismiss: () => void }) {
  if (state.kind === 'idle' || state.kind === 'busy') return null;
  const ok = state.kind === 'ok';
  return (
    <div
      data-testid="admin-action-toast"
      className={[
        'rounded border p-2 font-mono text-xs flex items-center gap-2',
        ok ? 'border-green/50 bg-green/10 text-green'
           : 'border-red/50   bg-red/10   text-red',
      ].join(' ')}
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
