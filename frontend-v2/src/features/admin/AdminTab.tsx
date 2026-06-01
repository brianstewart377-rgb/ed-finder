import { useState } from 'react';
import type { UseAdmin } from './useAdmin';
import { useProfileSync, type UseProfileSync } from '@/features/profile-sync/useProfileSync';
import type { EnrichmentStationStatus } from '@/types/api';

export interface AdminTabProps { admin: UseAdmin }

/**
 * Ops dashboard. Five sections:
 *   1. Auth — paste an admin token (sessionStorage).
 *   2. Live status — counts + meta flags + cache stats, auto-refreshing.
 *   3. Enrichment status — read-only sanitized station enrichment state.
 *   4. Actions — Clear cache + Rebuild clusters (both token-gated).
 *   5. Profile sync — cross-device local preference backup.
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
          ops console — token-gated status and actions
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
          Required for enrichment status and write actions. Stored in <code className="text-orange-lt">sessionStorage</code> —
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

      {/* ── Enrichment status ─────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          3. Enrichment status
        </h3>
        <EnrichmentStatusPanel
          hasToken={admin.hasToken}
          status={admin.enrichmentStatus}
          loading={admin.enrichmentLoading}
          error={admin.enrichmentError}
        />
      </section>

      {/* ── Actions ──────────────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          4. Actions
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
        5. Profile sync
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

function EnrichmentStatusPanel({
  hasToken,
  status,
  loading,
  error,
}: {
  hasToken: boolean;
  status: EnrichmentStationStatus | null;
  loading: boolean;
  error: string | null;
}) {
  if (!hasToken) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        Set an admin token to view read-only enrichment status.
      </p>
    );
  }

  if (error) {
    return (
      <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
        {error}
      </div>
    );
  }

  if (!status) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        {loading ? 'Loading enrichment status...' : 'Enrichment status has not loaded yet.'}
      </p>
    );
  }

  if (!status.available) {
    return (
      <div className="space-y-2">
        <div className="panel-thin border-gold/45 p-3 font-mono text-xs text-gold" style={{ background: 'rgba(250,204,21,0.08)' }}>
          {status.message}
        </div>
        <p className="text-[10px] leading-snug text-silver-dk font-mono">
          The API reads a configured JSON artifact generated by the station enrichment status helper. It does not run enrichment, Docker, EDSM, or database work from this page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
        <Stat label="Status" value={status.state} highlight={status.state === 'failed' || status.state === 'rate_limited'} />
        <Stat label="Checkpointed systems" value={formatUnknown(status.checkpoint?.processed_count)} />
        <Stat label="Last checkpointed id64" value={formatUnknown(status.checkpoint?.last_system_id64)} />
        <Stat label="Latest batch" value={formatUnknown(status.latest_batch?.number)} />
        <Stat label="Batch state" value={formatUnknown(status.latest_batch?.state)} highlight={status.latest_batch?.state === 'failed'} />
        <Stat label="Latest phase" value={formatUnknown(status.latest_batch?.latest_phase_name)} />
        <Stat label="Processed in report" value={formatUnknown(status.latest_report?.systems_processed)} />
        <Stat label="Fetch failures" value={formatUnknown(status.latest_report?.systems_fetch_failed ?? status.latest_progress?.systems_fetch_failed)} highlight={(status.latest_report?.systems_fetch_failed ?? 0) > 0} />
        <Stat label="Fetch errors" value={formatUnknown(status.latest_report?.fetch_errors ?? status.latest_progress?.fetch_errors)} highlight={(status.latest_report?.fetch_errors ?? 0) > 0} />
        <Stat label="Safety conflicts" value={formatUnknown(status.latest_report?.conflicts)} highlight={(status.latest_report?.conflicts ?? 0) > 0} />
        <Stat label="Rate-limit lines" value={formatUnknown(status.rate_limit?.recent_429_lines)} highlight={Boolean(status.rate_limit?.repeated_429_detected)} />
        <Stat label="Progress" value={formatProgress(status)} />
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs font-mono">
        <Stat label="Status artifact" value={status.artifact?.file_name ?? 'hidden'} />
        <Stat label="Artifact age" value={formatAge(status.artifact?.age_seconds)} />
        <Stat label="Output dir" value={status.latest_run?.latest_all_records_output_dir_name ?? status.latest_run?.output_dir_name ?? '—'} />
        <Stat label="Latest report" value={status.latest_batch?.latest_report_file_name ?? '—'} />
        <Stat label="Latest stderr" value={status.latest_batch?.latest_stderr_file_name ?? '—'} />
        <Stat label="Latest log" value={status.latest_run?.latest_log_file_name ?? '—'} />
      </div>

      {status.warnings.length > 0 && (
        <div className="panel-thin border-gold/45 p-3 font-mono text-[11px] leading-snug text-gold" style={{ background: 'rgba(250,204,21,0.08)' }}>
          {status.warnings.slice(0, 3).map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}

      <p className="text-[10px] leading-snug text-silver-dk font-mono">
        Read-only status from sanitized JSON. Full filesystem paths are hidden; missing values stay unavailable.
        {loading && <span className="text-orange-lt ml-2">refreshing...</span>}
      </p>
    </div>
  );
}

function formatUnknown(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return value.toLocaleString();
  return value;
}

function formatProgress(status: EnrichmentStationStatus): string {
  const current = status.latest_progress?.current;
  const total = status.latest_progress?.total;
  const percent = status.latest_progress?.batch_progress_percent;
  if (current == null || total == null) return '—';
  const percentText = percent == null ? '' : ` (${percent}%)`;
  return `${current.toLocaleString()} / ${total.toLocaleString()}${percentText}`;
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
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
