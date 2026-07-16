import type { Route } from '@/hooks/useHashRoute';
import { NavTab } from './NavTab';

export function OperatorModeMenu({
  current,
  onNavigate,
}: {
  current: Route;
  onNavigate: (route: Route) => void;
}) {
  return (
    <section data-testid="operator-mode-menu">
      <p className="mb-2 px-1 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Operator mode
      </p>
      <p className="mb-3 px-1 text-xs leading-relaxed text-silver">
        Separate from the normal Explore, Plan, and Review player journey.
      </p>
      <div className="grid gap-1">
        <NavTab
          label="Return to player workspace"
          active={false}
          onClick={() => onNavigate('finder')}
          testid="nav-return-to-player-menu"
          compact
        />
        <NavTab
          label="Admin"
          active={current === 'admin'}
          onClick={() => onNavigate('admin')}
          testid="nav-admin-operator-menu"
          compact
        />
        <NavTab
          label="Operator"
          active={current === 'operator'}
          onClick={() => onNavigate('operator')}
          testid="nav-operator-operator-menu"
          compact
        />
      </div>
    </section>
  );
}
