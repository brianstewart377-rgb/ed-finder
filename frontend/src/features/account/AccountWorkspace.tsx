import { useAuth } from '@/features/auth/useAuth';
import { JournalUploadPanel } from './JournalUploadPanel';
import { ResearchConsentPanel } from './ResearchConsentPanel';

/**
 * Account workspace: personal journal import (private, account-scoped) and
 * the EXPLICITLY SEPARATE research-contribution card. Auth-gated: without a
 * Frontier session the workspace shows a sign-in prompt; the panels never
 * render for anonymous visitors.
 */
export function AccountWorkspace() {
  const auth = useAuth();

  if (auth.loading) {
    return (
      <section data-testid="account-workspace" className="panel p-5">
        <div className="font-mono text-xs text-silver-dk">Loading account…</div>
      </section>
    );
  }

  if (!auth.authenticated) {
    return (
      <section data-testid="account-workspace" className="space-y-5">
        <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
          <h2 className="font-display text-orange tracking-[0.14em] text-lg">Account</h2>
          <span className="font-mono text-xs text-silver-dk">
            personal journal import — Frontier sign-in required
          </span>
        </header>
        <section className="panel space-y-3 p-5" data-testid="account-sign-in-prompt">
          <h3 className="font-display text-xs uppercase tracking-[0.18em] text-orange">
            Sign in required
          </h3>
          <p className="max-w-3xl text-sm leading-relaxed text-silver">
            Journal import is scoped to your Frontier account so your exploration history stays
            private to you. Sign in to import journals or review your research contribution.
          </p>
          <button
            type="button"
            onClick={auth.signIn}
            data-testid="account-sign-in"
            className="btn-primary text-[11px] py-1.5 px-3"
          >
            Sign in with Frontier
          </button>
        </section>
      </section>
    );
  }

  return (
    <section data-testid="account-workspace" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">Account</h2>
        <span className="font-mono text-xs text-silver-dk">
          personal journal intelligence + explicit research contribution
        </span>
        {auth.user?.commander_name ? (
          <span className="font-mono text-xs text-silver" data-testid="account-commander">
            CMDR {auth.user.commander_name}
          </span>
        ) : null}
      </header>

      <JournalUploadPanel />
      <ResearchConsentPanel />
    </section>
  );
}
