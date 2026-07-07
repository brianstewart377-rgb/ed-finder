import type { UseAdmin } from '../useAdmin';
import { ActionCard } from './AdminActionCard';
import { ActionToast } from './AdminToasts';

export function AdminActionsPanel({ admin }: { admin: UseAdmin }) {
  return (
    <section className="panel p-5 space-y-3">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        6. Actions
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
  );
}
