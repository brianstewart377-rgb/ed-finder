import type { Route } from '@/hooks/useHashRoute';
import type { RouteDescriptor } from './types';
import { isRouteActive } from './helpers';
import { NavTab } from './NavTab';

export function MenuSection({
  title,
  routes,
  current,
  onNavigate,
}: {
  title: string;
  routes: RouteDescriptor[];
  current: Route;
  onNavigate: (route: Route) => void;
}) {
  return (
    <section>
      <p className="mb-2 px-1 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        {title}
      </p>
      <div className="grid gap-1">
        {routes.map((tab) => (
          <NavTab
            key={`menu-${tab.route}`}
            label={tab.label}
            active={isRouteActive(current, tab.route)}
            onClick={() => onNavigate(tab.route)}
            testid={`${tab.testid}-menu`}
            badge={tab.badge}
            title={tab.title}
            compact
          />
        ))}
      </div>
    </section>
  );
}
