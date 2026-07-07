import { useState } from 'react';
import type { UseAdmin } from './useAdmin';
import { AdminActionsPanel } from './components/AdminActionsPanel';
import { AdminAuthPanel } from './components/AdminAuthPanel';
import { AdminDataStatusPanel } from './components/AdminDataStatusPanel';
import { AdminEnrichmentStatusPanel } from './components/AdminEnrichmentStatusPanel';
import { AdminLiveStatusPanel } from './components/AdminLiveStatusPanel';
import { AdminWarehouseStatusPanel } from './components/AdminWarehouseStatusPanel';
import { ProfileSyncPanel } from '@/features/profile-sync/ProfileSyncPanel';

export interface AdminTabProps { admin: UseAdmin }

/**
 * Ops dashboard. Seven sections:
 *   1. Auth — paste an admin token (sessionStorage).
 *   2. Live status — counts + meta flags + cache stats, auto-refreshing.
 *   3. Enrichment status — read-only sanitized station enrichment state.
 *   4. Warehouse status — read-only sanitized warehouse evidence state.
 *   5. Data status — read-only database visibility snapshot.
 *   6. Actions — Clear cache + Rebuild clusters (both token-gated).
 *   7. Profile sync — cross-device local preference backup.
 *
 * No live job-status polling yet — neither admin endpoint exposes one.
 * Adding a /api/admin/jobs/{id} endpoint server-side would let us show a
 * live progress bar for cluster rebuilds; until then a "triggered" toast
 * is honest about what we know.
 */
export function AdminTab({ admin }: AdminTabProps) {
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

      {/* ── Enrichment status ─────────────────────────────────────────── */}
      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          3. Enrichment status
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
          4. Warehouse status
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
          5. Data status
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
