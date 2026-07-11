import { useState } from 'react';
import type { UseAdmin } from './useAdmin';
import { AdminActionsPanel } from './components/AdminActionsPanel';
import { AdminAuthPanel } from './components/AdminAuthPanel';
import { AdminCronStatusPanel } from './components/AdminCronStatusPanel';
import { AdminDataStatusPanel } from './components/AdminDataStatusPanel';
import { AdminEnrichmentStatusPanel } from './components/AdminEnrichmentStatusPanel';
import { AdminImportDashboardPanel } from './components/AdminImportDashboardPanel';
import { AdminLiveStatusPanel } from './components/AdminLiveStatusPanel';
import { AdminWarehouseStatusPanel } from './components/AdminWarehouseStatusPanel';
import { ProfileSyncPanel } from '@/features/profile-sync/ProfileSyncPanel';

export interface AdminTabProps {
  admin: UseAdmin;
  onOpenOperator?: (sourceRunKey?: string) => void;
}

/**
 * Ops dashboard. Seven sections:
 *   1. Auth — paste an admin token (sessionStorage).
 *   2. Live status — counts + meta flags + cache stats, auto-refreshing.
 *   3. Import dashboard â€” recent source runs plus safety posture.
 *   4. Scheduler status â€” last cron-like runs plus rebuild job state.
 *   5. Enrichment status Ã¢â‚¬â€ read-only sanitized station enrichment state.
 *   6. Warehouse status Ã¢â‚¬â€ read-only sanitized warehouse evidence state.
 *   7. Data status Ã¢â‚¬â€ read-only database visibility snapshot.
 *   8. Actions Ã¢â‚¬â€ Clear cache + Rebuild clusters (both token-gated).
 *   9. Profile sync Ã¢â‚¬â€ cross-device local preference backup.
 *
 * Scheduler and rebuild recency are now surfaced through read-only admin
 * status endpoints. Progress is still coarse-grained rather than a live
 * per-step stream, but the dashboard can at least show the last known run
 * windows and current in-process rebuild state.
 */
export function AdminTab({ admin, onOpenOperator }: AdminTabProps) {
  const [tokenDraft, setTokenDraft] = useState(admin.token);

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

      <AdminAuthPanel
        tokenDraft={tokenDraft}
        onTokenDraftChange={setTokenDraft}
        hasToken={admin.hasToken}
        onSave={() => admin.setToken(tokenDraft.trim())}
        onForget={() => { admin.forgetToken(); setTokenDraft(''); }}
      />

      <AdminLiveStatusPanel
        status={admin.status}
        cache={admin.cache}
        metaError={admin.metaError}
        metaLoading={admin.metaLoading}
      />

      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          3. Import dashboard
        </h3>
        <AdminImportDashboardPanel
          hasToken={admin.hasToken}
          loading={admin.importDashboardLoading}
          error={admin.importDashboardError}
          safetyGates={admin.importSafetyGates}
          sourceRuns={admin.importSourceRuns}
          onOpenOperator={onOpenOperator}
        />
      </section>

      {/* ── Enrichment status ─────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          4. Scheduler status
        </h3>
        <AdminCronStatusPanel
          hasToken={admin.hasToken}
          status={admin.cronStatus}
          loading={admin.cronStatusLoading}
          error={admin.cronStatusError}
        />
      </section>

      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          5. Enrichment status
        </h3>
        <AdminEnrichmentStatusPanel
          hasToken={admin.hasToken}
          status={admin.enrichmentStatus}
          loading={admin.enrichmentLoading}
          error={admin.enrichmentError}
        />
      </section>

      {/* ── Warehouse status ──────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          6. Warehouse status
        </h3>
        <AdminWarehouseStatusPanel
          hasToken={admin.hasToken}
          status={admin.warehouseStatus}
          loading={admin.warehouseLoading}
          error={admin.warehouseError}
        />
      </section>

      {/* ── Data status ─────────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          7. Data status
        </h3>
        <AdminDataStatusPanel
          hasToken={admin.hasToken}
          status={admin.dataStatus}
          loading={admin.dataStatusLoading}
          error={admin.dataStatusError}
        />
      </section>

      <AdminActionsPanel admin={admin} />

      <ProfileSyncPanel />
    </section>
  );
}
