import type { Route } from '@/hooks/useHashRoute';
import type { UseAuth } from './useAuth';

export function AccountControls({
  auth,
  onNavigate,
}: {
  auth: UseAuth;
  onNavigate: (route: Route) => void;
}) {
  if (auth.loading) {
    return <span className="hidden font-mono text-[10px] text-silver-dk sm:inline">Account…</span>;
  }

  if (!auth.authenticated) {
    return (
      <button
        type="button"
        onClick={auth.signIn}
        data-testid="frontier-sign-in"
        className="premium-toolbar shrink-0 rounded-full px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-orange hover:border-orange/60"
      >
        Sign in
      </button>
    );
  }

  return (
    <div className="premium-toolbar flex shrink-0 items-center gap-2 rounded-full px-2.5 py-1.5">
      <span className="hidden max-w-36 truncate font-mono text-[10px] text-silver sm:inline" data-testid="frontier-account-name">
        {auth.user?.commander_name ? `CMDR ${auth.user.commander_name}` : 'Frontier account'}
      </span>
      {auth.user?.is_owner ? (
        <button
          type="button"
          onClick={() => onNavigate('admin')}
          data-testid="owner-open-ops"
          className="font-mono text-[10px] uppercase tracking-[0.12em] text-gold hover:text-orange"
        >
          Ops
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => void auth.signOut()}
        data-testid="frontier-sign-out"
        className="font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:text-orange"
      >
        Sign out
      </button>
    </div>
  );
}
