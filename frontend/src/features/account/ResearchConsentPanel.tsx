import { useState } from 'react';
import { useAuth } from '@/features/auth/useAuth';
import { useResearchConsent } from './useResearchConsent';

/**
 * Honest research-contribution copy (decision doc R7 / plan UX contract).
 * Verbatim — do not soften. "Pseudonymous" is a deliberate, tested claim;
 * this panel must never say "anonymous".
 */
export const RESEARCH_CONSENT_COPY = 'Sanitized and pseudonymous — not anonymous. Travel sequences can still identify an explorer. Withdrawal stops future exports; observations already in published EDRE releases cannot be retracted (supersede-not-delete).';

/**
 * Explicit research opt-in card. Completely separate from journal upload:
 * uploading journals never mentions or requires research contribution.
 * State machine: NONE → GRANTED (version + date) / WITHDRAWN.
 */
export function ResearchConsentPanel() {
  const auth = useAuth();
  const consent = useResearchConsent(!!auth.user);
  const [actionError, setActionError] = useState<string | null>(null);
  const decision = consent.state?.decision ?? 'NONE';

  const handleGrant = async () => {
    setActionError(null);
    try {
      await consent.grant();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not share observations with EDRE research.');
    }
  };

  const handleWithdraw = async () => {
    setActionError(null);
    try {
      await consent.withdraw();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not withdraw research contribution.');
    }
  };

  return (
    <section className="premium-subpanel space-y-4 p-4" data-testid="research-consent-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base tracking-[0.12em] text-text">
            Research contribution
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-silver">
            {RESEARCH_CONSENT_COPY}
          </p>
        </div>
        <span
          className="premium-toolbar rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange-lt"
          data-testid="research-consent-state"
        >
          {decision === 'GRANT' ? 'Contributing' : decision === 'WITHDRAW' ? 'Withdrawn' : 'No contribution'}
        </span>
      </div>

      {consent.loading ? (
        <div className="rounded-sm border border-border/50 bg-bg1/35 px-3 py-2 text-sm text-silver-dk" data-testid="research-consent-loading">
          Loading contribution state...
        </div>
      ) : null}

      {consent.state && consent.state.decision === 'GRANT' ? (
        <div className="rounded-chunk-lg border border-green/25 bg-green/10 p-3" data-testid="research-consent-granted">
          <p className="text-sm text-silver">
            Active contribution — consent {consent.state.consent_version ?? '1.0'}
            {consent.state.decided_at ? ` since ${formatDate(consent.state.decided_at)}` : ''}.
          </p>
          {consent.state.withdrawable ? (
            <button
              type="button"
              onClick={() => void handleWithdraw()}
              disabled={consent.busy}
              data-testid="research-consent-withdraw"
              className="btn-metal mt-3 text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {consent.busy ? 'Withdrawing...' : 'Withdraw contribution'}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="rounded-chunk-lg border border-orange/25 bg-orange/5 p-3">
          <p className="text-sm leading-relaxed text-silver">
            {decision === 'WITHDRAW'
              ? 'Your contribution is withdrawn. You can share sanitized observations with EDRE research again at any time.'
              : 'Journal upload never requires this. Contribute only if you want sanitized observations to reach the EDRE research corpus.'}
          </p>
          <button
            type="button"
            onClick={() => void handleGrant()}
            disabled={consent.busy}
            data-testid="research-consent-share"
            className="btn-primary mt-3 text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {consent.busy ? 'Updating...' : 'Share sanitized observations with EDRE research'}
          </button>
        </div>
      )}

      {actionError ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red" data-testid="research-consent-error">
          {actionError}
        </div>
      ) : null}
    </section>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}
