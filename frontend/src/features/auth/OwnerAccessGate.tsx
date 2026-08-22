import { useState, type ReactNode } from 'react';
import type { UseAuth } from './useAuth';

export function OwnerAccessGate({
  auth,
  children,
}: {
  auth: UseAuth;
  children: ReactNode;
}) {
  const [adminToken, setAdminToken] = useState('');
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  if (auth.loading) {
    return (
      <section className="panel mx-auto max-w-2xl p-6 text-center" data-testid="owner-access-loading">
        <p className="font-mono text-sm text-silver-dk">Checking owner access…</p>
      </section>
    );
  }

  if (!auth.authenticated) {
    return (
      <section className="panel mx-auto max-w-2xl space-y-4 p-6" data-testid="owner-sign-in-required">
        <h2 className="font-display text-lg tracking-[0.14em] text-orange">Owner sign-in required</h2>
        <p className="text-sm leading-relaxed text-silver-dk">
          Operational dashboards and health information are private. Sign in with the Frontier account linked to ED-Finder.
        </p>
        <button type="button" onClick={auth.signIn} className="btn-primary px-4 py-2">
          Sign in with Frontier
        </button>
      </section>
    );
  }

  if (!auth.user?.is_owner) {
    return (
      <section className="panel mx-auto max-w-2xl space-y-4 p-6" data-testid="owner-access-denied">
        <h2 className="font-display text-lg tracking-[0.14em] text-orange">Owner access only</h2>
        <p className="text-sm leading-relaxed text-silver-dk">
          This Frontier account is signed in, but it is not linked as ED-Finder’s owner.
        </p>
        {auth.ownerClaimAvailable ? (
          <div className="premium-subpanel space-y-3 p-4">
            <p className="text-xs leading-relaxed text-silver-dk">
              First-time setup: enter the existing ED-Finder admin token once to link this Frontier account as the owner.
            </p>
            <div className="flex flex-wrap gap-2">
              <input
                type="password"
                value={adminToken}
                onChange={(event) => setAdminToken(event.target.value)}
                placeholder="Existing admin token"
                data-testid="owner-claim-token"
                className="min-w-[220px] flex-1"
                autoComplete="off"
              />
              <button
                type="button"
                disabled={!adminToken.trim() || claiming}
                data-testid="owner-claim-submit"
                className="btn-primary px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => {
                  setClaiming(true);
                  setClaimError(null);
                  void auth.claimOwner(adminToken.trim())
                    .then(() => setAdminToken(''))
                    .catch((caught: unknown) => {
                      setClaimError(caught instanceof Error ? caught.message : String(caught));
                    })
                    .finally(() => setClaiming(false));
                }}
              >
                {claiming ? 'Linking…' : 'Link owner account'}
              </button>
            </div>
            {claimError ? <p className="text-xs text-red">{claimError}</p> : null}
          </div>
        ) : null}
        <button type="button" onClick={() => void auth.signOut()} className="btn-metal px-4 py-2">
          Sign out
        </button>
      </section>
    );
  }

  return children;
}
