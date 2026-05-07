import { useState } from 'react';
import type { UseAdmin } from './useAdmin';
import { useProfileSync, type UseProfileSync } from '@/features/profile-sync/useProfileSync';

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
  const sync = useProfileSync();

  return (
    <section data-testid="admin-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">⚙️ Admin</h2>
        <span className="font-mono text-xs text-silver-dk">
          ops console — token-gated actions
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void admin.refresh()}
          data-testid="admin-refresh"
          className="btn-metal text-[11px] py-1.5 px-3"
        >
          ↺ Refresh
        </button>
      </header>

      {/* ── Auth ─────────────────────────────────────────────────────── */}
      <section className="panel p-5 space-y-2">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          1. Admin token
        </h3>
        <p className="text-silver-dk text-[11px]">
          Required for write actions only. Stored in <code className="text-orange-lt">sessionStorage</code> —
          forgotten when this tab closes.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
            placeholder="X-Admin-Token"
            data-testid="admin-token-input"
            className="flex-1 min-w-[220px]"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => admin.setToken(tokenDraft.trim())}
            data-testid="admin-token-save"
            className="btn-primary text-[11px] py-1.5 px-3"
          >
            Save
          </button>
          {admin.hasToken && (
            <button
              type="button"
              onClick={() => { admin.forgetToken(); setTokenDraft(''); }}
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
              admin.hasToken ? 'text-green' : 'text-silver-dk',
            ].join(' ')}
          >
            {admin.hasToken ? '● Token set' : '○ No token'}
          </span>
        </div>
      </section>

      {/* ── Status ───────────────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          2. Live status
        </h3>

        {admin.metaError && (
          <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
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

        <p className="text-[10px] text-silver-dk font-mono">
          Auto-refreshes every 30s.
          {admin.metaLoading && <span className="text-orange-lt ml-2">⟳ refreshing…</span>}
        </p>
      </section>

      {/* ── Actions ──────────────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          3. Actions
        </h3>

        <ActionToast state={admin.actionState} onDismiss={admin.resetActionState} />

        <div className="grid sm:grid-cols-3 gap-3">
          <ActionCard
            title="Rebuild ratings"
            blurb="Recompute every system's per-economy scores. Cheap on preview (~40 systems), background pipeline in prod."
            confirmText="Rebuild ratings now?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'rebuildRatings'}
            onClick={admin.rebuildRatings}
            testid="admin-rebuild-ratings"
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
          <ActionCard
            title="Clear cache"
            blurb="Flush Redis + expired api_cache rows. Cheap; safe to retry."
            confirmText="Flush all cached responses?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'clearCache'}
            onClick={admin.clearCache}
            testid="admin-clear-cache"
          />
        </div>

        {!admin.hasToken && (
          <p className="text-[10px] text-silver-dk font-mono">
            Set a token in section 1 to enable actions. Preview default token: <code className="text-orange-lt">local-dev-admin-token</code>
          </p>
        )}
      </section>

      {/* ── Profile Sync ─────────────────────────────────────────────── */}
      <ProfileSyncSection sync={sync} />
    </section>
  );
}

// ─── Profile sync section ─────────────────────────────────────────────────

function ProfileSyncSection({ sync }: { sync: UseProfileSync }) {
  const [draft, setDraft] = useState(sync.syncKey);

  return (
    <section className="panel p-5 space-y-3">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        4. Profile sync
      </h3>
      <p className="text-silver-dk text-[11px] leading-snug">
        Cross-device sync for your <strong className="text-orange-lt">Pinned</strong>,
        <strong className="text-orange-lt"> Compare</strong>,
        <strong className="text-orange-lt"> FC route</strong>, and
        <strong className="text-orange-lt"> Colony tracker</strong>.
        The sync key IS the credential — pick a hard-to-guess string and
        share it across your devices. Last-write-wins; no auto-merge.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="16+ chars, [A-Za-z0-9_-]"
          data-testid="sync-key-input"
          className="flex-1 min-w-[260px]"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => sync.setSyncKey(draft.trim())}
          disabled={draft.trim().length < 16 || draft.trim() === sync.syncKey}
          data-testid="sync-key-save"
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save key
        </button>
        <button
          type="button"
          onClick={() => setDraft(sync.generateKey())}
          data-testid="sync-key-generate"
          className="btn-metal text-[11px] py-1.5 px-3"
          title="Generate a 24-char random key"
        >
          🎲 Generate
        </button>
      </div>

      <SyncStateToast state={sync.state} onDismiss={sync.resetState} />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void sync.pull()}
          disabled={!sync.hasKey || sync.state.kind === 'busy'}
          data-testid="sync-pull"
          className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-cyan/50 bg-cyan/15 text-cyan font-mono hover:bg-cyan/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Pull from cloud
        </button>
        <button
          type="button"
          onClick={() => void sync.push()}
          disabled={!sync.hasKey || sync.state.kind === 'busy'}
          data-testid="sync-push"
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬆ Push to cloud
        </button>
        <span className="flex-1" />
        {sync.lastPushAt && (
          <span className="font-mono text-[10px] text-silver-dk">
            last push: {new Date(sync.lastPushAt).toLocaleString()}
          </span>
        )}
        <span
          data-testid="sync-key-status"
          className={[
            'font-mono text-[10px] uppercase tracking-wider',
            sync.hasKey ? 'text-green' : 'text-silver-dk',
          ].join(' ')}
        >
          {sync.hasKey ? '● Key set' : '○ No key'}
        </span>
      </div>

      {!sync.hasKey && (
        <p className="text-[10px] text-silver-dk font-mono">
          A key is needed before push/pull. Click Generate then Save.
        </p>
      )}
    </section>
  );
}

function SyncStateToast({
  state, onDismiss,
}: { state: UseProfileSync['state']; onDismiss: () => void }) {
  if (state.kind === 'idle' || state.kind === 'busy') return null;
  const ok = state.kind === 'ok';
  return (
    <div
      data-testid="sync-toast"
      className={[
        'rounded-chunk-sm border p-2.5 font-mono text-xs flex items-center gap-2',
        ok ? 'border-green/50 text-green' : 'border-red/50 text-red',
      ].join(' ')}
      style={{ background: ok ? 'rgba(74,222,128,0.10)' : 'rgba(248,113,113,0.10)' }}
    >
      <span>{ok ? '✓' : '✕'}</span>
      <span className="font-bold">{state.what}:</span>
      <span>
        {ok
          ? `${state.bytes != null ? `${state.bytes.toLocaleString()} bytes · ` : ''}saved at ${new Date(state.updated_at).toLocaleString()}`
          : state.message}
      </span>
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

// ─── Sub-components ────────────────────────────────────────────────────────

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={[
      'rounded-chunk-sm p-2.5 border',
      highlight ? 'border-red/40 bg-red/10' : 'border-border bg-bg3/40',
    ].join(' ')}>
      <div className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</div>
      <div className={['tabular-nums font-bold mt-0.5', highlight ? 'text-red' : 'text-silver'].join(' ')}>
        {value}
      </div>
    </div>
  );
}

function Flag({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="rounded-chunk-sm p-2.5 border border-border bg-bg3/40 flex items-center justify-between">
      <span className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</span>
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
    <div className="panel-thin p-4 space-y-2 flex flex-col">
      <div className="font-display text-orange text-xs tracking-[0.14em]">{title}</div>
      <p className="text-[11px] text-silver-dk leading-snug flex-1">{blurb}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => { if (confirm(confirmText)) void onClick(); }}
        data-testid={testid}
        className={disabled ? 'btn-metal opacity-50 cursor-not-allowed text-[11px] py-1.5' : 'btn-primary text-[11px] py-1.5'}
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
