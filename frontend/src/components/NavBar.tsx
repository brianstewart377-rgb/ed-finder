import type { Route } from '@/hooks/useHashRoute';
import { useDensity } from '@/hooks/useDensity';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { Logo } from './navbar/Logo';
import { NavTab } from './navbar/NavTab';
import { MenuSection } from './navbar/MenuSection';
import { OperatorModePanel } from './navbar/OperatorModePanel';
import { OperatorModeMenu } from './navbar/OperatorModeMenu';
import { primaryWorkspaceForRoute, isRouteActive, workspaceMetaForRoute } from './navbar/helpers';
import type { RouteDescriptor, PrimaryWorkspace } from './navbar/types';

/** Top-bar nav for the live app — sticky chrome panel with brushed-metal sheen
 *  and an ED-orange "active-tab" indicator. Height tuned to match the bottom
 *  headline banner for visual symmetry. */
export interface NavBarProps {
  current:    Route;
  onNavigate: (r: Route) => void;
  watchlistCount?: number | null;
  pinnedCount?:    number;
  compareCount?:   number;
  fcCount?:        number;
  health?:         string;
  fullWidth?:      boolean;
  selectedSystem?: {
    id64: number;
    name: string | null;
    loading: boolean;
    evidenceLabel: string;
    evidenceTone: SemanticStatusTone;
    evidenceSummary: string;
  } | null;
  onOpenSelectedSystemInPlan?: (() => void) | undefined;
  onDismissSelectedSystem?: (() => void) | undefined;
}

const PLAYER_WORKSPACES: PrimaryWorkspace[] = ['explore', 'plan', 'review'];

export function NavBar({
  current, onNavigate,
  compareCount, fcCount,
  health,
  fullWidth = false,
  selectedSystem = null,
  onOpenSelectedSystemInPlan,
  onDismissSelectedSystem,
}: NavBarProps) {
  const appVersionLabel = `v${__APP_VERSION__}`;
  const ok = (health ?? '').toLowerCase() === 'online';
  const { density, cycle } = useDensity();
  const densityIcon  = density === 'compact' ? '▬' : density === 'spacious' ? '☰' : '≡';
  const densityLabel = density.charAt(0).toUpperCase() + density.slice(1);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const groupedRoutes = useMemo<Record<'explore' | 'plan' | 'review' | 'operator', RouteDescriptor[]>>(() => ({
    explore: [
      { route: 'finder' as const, label: 'Finder', testid: 'nav-finder' },
      { route: 'map' as const, label: 'Map', testid: 'nav-map', title: 'Secondary Explore surface' },
    ],
    plan: [
      { route: 'my-work' as const, label: 'My Work', testid: 'nav-my-work' },
      { route: 'colony-planner' as const, label: 'Colony Planner', testid: 'nav-colony-planner' },
    ],
    review: [
      { route: 'compare' as const, label: 'Compare', testid: 'nav-compare', badge: compareCount },
      { route: 'fc' as const, label: 'FC Route Planner', testid: 'nav-fc', badge: fcCount },
    ],
    operator: [
      { route: 'admin' as const, label: 'Admin', testid: 'nav-admin' },
      { route: 'operator' as const, label: 'Operator', testid: 'nav-operator' },
    ],
  }), [compareCount, fcCount]);
  const playerRoutes = useMemo(
    () => PLAYER_WORKSPACES.flatMap((workspace) => groupedRoutes[workspace]),
    [groupedRoutes],
  );

  const operatorMode = current === 'admin' || current === 'operator';
  const showPlayerContext = selectedSystem != null || !['finder', 'colony-planner', 'my-work', 'watchlist', 'pinned'].includes(current);
  const currentPrimary = primaryWorkspaceForRoute(current);
  const currentRouteDescriptor = PLAYER_WORKSPACES
    .flatMap((workspace) => groupedRoutes[workspace])
    .find((tab) => tab.route === current)
    ?? groupedRoutes.operator.find((tab) => tab.route === current)
    ?? null;
  const currentWorkspaceMeta = workspaceMetaForRoute(current);

  useEffect(() => {
    setMenuOpen(false);
  }, [current]);

  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (toggleRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [menuOpen]);

  const handleNavigate = (route: Route) => {
    onNavigate(route);
    setMenuOpen(false);
  };

  return (
    <nav
      className={[
        'sticky top-3 z-30 mb-8 px-3',
        fullWidth ? 'w-full max-w-none' : 'mx-auto max-w-[1840px]',
      ].join(' ')}
      data-testid="navbar"
    >
      {/* py-1.5 here matches the bottom headline banner so top + bottom chrome align */}
      <div className="panel relative overflow-hidden px-4 py-3.5 sm:px-6">
        <div className="flex items-center gap-3 sm:gap-5">
        {/* ── Logo lockup ─────────────────────────────── */}
          <div className="flex items-center gap-3 shrink-0">
          <Logo />
          <div className="flex flex-col leading-tight hidden sm:flex">
            <span className="font-mono text-[15px] font-bold tracking-[0.18em] text-orange">
              ED:FINDER
            </span>
            <span className="font-mono text-[9px] tracking-[0.32em] text-silver-dk -mt-0.5">
              {appVersionLabel}
            </span>
          </div>
        </div>

          {/* divider */}
          <span className="hidden h-9 w-px shrink-0 bg-gradient-to-b from-transparent via-border-bright to-transparent sm:block" />

          <div
            className="hidden min-w-0 flex-1 items-center gap-3 lg:flex"
            data-testid="nav-desktop-route-strip"
          >
            {!operatorMode ? (
              <div
                className="premium-toolbar flex min-w-0 flex-wrap items-center gap-1 overflow-x-auto rounded-full px-2 py-1.5"
                aria-label="Player routes"
                data-testid="nav-player-routes"
              >
                {playerRoutes.map((tab) => (
                  <NavTab
                    key={tab.route}
                    label={tab.label}
                    active={isRouteActive(current, tab.route)}
                    onClick={() => handleNavigate(tab.route)}
                    testid={tab.testid}
                    badge={tab.badge}
                    title={tab.title}
                  />
                ))}
              </div>
            ) : null}
          </div>

          <div className="min-w-0 flex-1 lg:hidden">
            <span className="truncate rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
              {currentPrimary ? `${currentWorkspaceMeta.primaryLabel} · ${currentRouteDescriptor?.label ?? currentWorkspaceMeta.title}` : currentWorkspaceMeta.title}
            </span>
          </div>

        {/* ── Density toggle ─────────────────────────── */}
          <button
            type="button"
            onClick={cycle}
            data-testid="nav-density-toggle"
            title={`Density: ${densityLabel} (click to cycle)`}
            aria-label={`Density: ${densityLabel}, click to cycle`}
            className="premium-toolbar flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-mono text-[14px] leading-none text-silver transition-colors hover:border-orange-dk hover:text-orange-lt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
          >
            <span aria-hidden>{densityIcon}</span>
          </button>

          <button
            ref={toggleRef}
            type="button"
            data-testid="nav-menu-toggle"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
            className="premium-toolbar inline-flex items-center justify-center rounded-chunk-sm px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-silver hover:border-orange/50 hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80 lg:hidden"
          >
            Menu
          </button>

        {/* ── Status pill — always visible across breakpoints.
         * Collapses to a dot-only chip on narrow screens, expands with
         * the text label at md+. Used to be 'hidden md:flex' which led
         * users on smaller viewports to think the backend was offline. */}
          <div
            className="premium-toolbar flex shrink-0 items-center gap-2 rounded-full px-2.5 py-1.5 md:px-3"
            title={ok ? `Backend online — ${health}` : (health ?? 'Checking…')}
            data-testid="nav-status-pill"
          >
            <span className={[
              'h-2 w-2 rounded-full',
              ok ? 'bg-green shadow-[0_0_8px_2px_rgba(74,222,128,0.55)]'
                 : 'bg-red shadow-[0_0_8px_2px_rgba(248,113,113,0.55)]',
            ].join(' ')} />
            <span className="hidden font-mono text-[10px] uppercase tracking-wider text-silver-dk md:inline">
              {ok ? 'Online' : (health ?? 'API')}
            </span>
          </div>
        </div>

        {operatorMode || showPlayerContext ? (
        <div className="mt-4 border-t border-border/70 pt-4">
          {operatorMode ? (
            <>
              <div className="hidden lg:block">
                <OperatorModePanel
                  current={current}
                  onNavigate={handleNavigate}
                  title={currentWorkspaceMeta.title}
                  supportingText={currentWorkspaceMeta.supportingText}
                  contextTestId="operator-mode-context-desktop"
                  returnTestId="nav-return-to-player-desktop"
                />
              </div>
              <div className="space-y-3 lg:hidden" data-testid="operator-mode-context-mobile">
                <OperatorModePanel
                  current={current}
                  onNavigate={handleNavigate}
                  title={currentWorkspaceMeta.title}
                  supportingText={currentWorkspaceMeta.supportingText}
                  contextTestId="operator-mode-context-mobile-panel"
                  returnTestId="nav-return-to-player-mobile"
                  mobile
                />
              </div>
            </>
          ) : showPlayerContext ? (
            <>
              <div className="hidden lg:block">
                <WorkspaceContextHeader
                  journeyLabel={current === 'compare' ? undefined : currentWorkspaceMeta.primaryLabel}
                  title={currentWorkspaceMeta.title}
                  headingLevel={2}
                  supportingText={currentWorkspaceMeta.supportingText}
                  selectedSystemName={selectedSystem ? (selectedSystem.loading ? 'Loading system...' : selectedSystem.name ?? 'Selected system') : null}
                  selectedSystemMeta={selectedSystem ? <span className="tabular-nums">ID64 {selectedSystem.id64}</span> : undefined}
                  onDismissSelectedSystem={selectedSystem ? onDismissSelectedSystem : undefined}
                  selectedSystemDetail={selectedSystem ? (
                    <div className="space-y-2">
                      <SemanticStatusBadge
                        label={selectedSystem.evidenceLabel}
                        tone={selectedSystem.evidenceTone}
                        testId="selected-system-evidence-badge"
                      />
                      <p className="text-xs normal-case tracking-normal text-silver-dk">
                        {selectedSystem.evidenceSummary}
                      </p>
                    </div>
                  ) : undefined}
                  status={(
                    <SemanticStatusBadge
                      label={currentWorkspaceMeta.statusLabel}
                      tone={currentWorkspaceMeta.statusTone}
                    />
                  )}
                  actions={selectedSystem && onOpenSelectedSystemInPlan ? (
                    <button
                      type="button"
                      onClick={onOpenSelectedSystemInPlan}
                      data-testid="nav-open-selected-system-plan"
                      className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-orange transition-colors hover:border-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
                    >
                      Open in Plan
                    </button>
                  ) : undefined}
                  testId="product-shell-context"
                />
              </div>

              <div className="space-y-3 lg:hidden" data-testid="product-shell-context-mobile">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                    Workspace
                  </span>
                  <SemanticStatusBadge
                    label={`${currentWorkspaceMeta.primaryLabel} · ${currentWorkspaceMeta.title}`}
                    tone={currentWorkspaceMeta.statusTone}
                  />
                </div>
                <p className="text-sm leading-relaxed text-silver">
                  {currentWorkspaceMeta.supportingText}
                </p>
                {selectedSystem ? (
                  <div className="premium-subpanel p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                        Selected system
                      </p>
                      {onDismissSelectedSystem ? (
                        <button
                          type="button"
                          onClick={onDismissSelectedSystem}
                          aria-label="Clear selected system"
                          data-testid="selected-system-dismiss-mobile"
                          className="shrink-0 rounded-full p-0.5 text-silver-dk transition-colors hover:bg-white/10 hover:text-orange-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60"
                        >
                          <X size={14} />
                        </button>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm font-semibold text-text">
                      {selectedSystem.loading ? 'Loading system...' : selectedSystem.name ?? 'Selected system'}
                    </p>
                    <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
                      ID64 {selectedSystem.id64}
                    </p>
                    <div className="mt-2">
                      <SemanticStatusBadge
                        label={selectedSystem.evidenceLabel}
                        tone={selectedSystem.evidenceTone}
                        testId="selected-system-evidence-badge-mobile"
                      />
                    </div>
                    <p className="mt-2 text-xs leading-relaxed text-silver-dk">
                      {selectedSystem.evidenceSummary}
                    </p>
                    {onOpenSelectedSystemInPlan ? (
                      <button
                        type="button"
                        onClick={onOpenSelectedSystemInPlan}
                        data-testid="nav-open-selected-system-plan-mobile"
                        className="mt-3 w-full rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-orange transition-colors hover:border-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
                      >
                        Open in Plan
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
        ) : null}
      </div>

      {menuOpen && (
        <div
          ref={menuRef}
          data-testid="nav-menu-panel"
          className="panel mt-2 p-2 lg:hidden"
        >
          <div className="grid gap-3">
            <MenuSection
              title="Routes"
              routes={playerRoutes}
              current={current}
              onNavigate={handleNavigate}
            />
            {operatorMode ? (
              <OperatorModeMenu
                current={current}
                onNavigate={handleNavigate}
              />
            ) : null}
          </div>
        </div>
      )}
    </nav>
  );
}
