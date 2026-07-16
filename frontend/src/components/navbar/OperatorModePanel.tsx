import type { Route } from '@/hooks/useHashRoute';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { NavTab } from './NavTab';

export function OperatorModePanel({
  current,
  onNavigate,
  title,
  supportingText,
  contextTestId,
  returnTestId,
  mobile = false,
}: {
  current: Route;
  onNavigate: (route: Route) => void;
  title: string;
  supportingText: string;
  contextTestId: string;
  returnTestId: string;
  mobile?: boolean;
}) {
  return (
    <div
      className="rounded-chunk-lg border border-gold/40 bg-gold/10 p-4"
      data-testid="operator-mode-panel"
    >
      <WorkspaceContextHeader
        journeyLabel="Separate mode: Operator"
        title={title}
        headingLevel={2}
        supportingText={`${supportingText} This route sits outside the normal Explore, Plan, and Review player journey.`}
        status={<SemanticStatusBadge label="Separate operator mode" tone="caution" />}
        facts={[
          { label: 'Player shell', value: 'Explore / Plan / Review', tone: 'gold' },
          { label: 'Next action', value: 'Return to Finder when operator work is complete.', tone: 'orange' },
        ]}
        actions={(
          <>
            <button
              type="button"
              onClick={() => onNavigate('finder')}
              data-testid={returnTestId}
              className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-orange transition-colors hover:border-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
            >
              Return to player workspace
            </button>
            <NavTab
              label="Admin"
              active={current === 'admin'}
              onClick={() => onNavigate('admin')}
              testid={mobile ? 'nav-admin-mobile-operator-mode' : 'nav-admin-operator-mode'}
            />
            <NavTab
              label="Operator"
              active={current === 'operator'}
              onClick={() => onNavigate('operator')}
              testid={mobile ? 'nav-operator-mobile-operator-mode' : 'nav-operator-operator-mode'}
            />
          </>
        )}
        testId={contextTestId}
      />
    </div>
  );
}
