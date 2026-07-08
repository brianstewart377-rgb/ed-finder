import type { Route } from '@/hooks/useHashRoute';
import { useDensity } from '@/hooks/useDensity';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { useEffect, useMemo, useRef, useState } from 'react';

/** Top-bar nav for the live app — sticky chrome panel with brushed-metal sheen
 *  and an ED-orange "active-tab" indicator. Height tuned to match the bottom
 *  headline banner for visual symmetry. */
export interface NavBarProps {
  current:    Route;
  onNavigate: (r: Route) => void;
  watchlistCount?: number | null;
  pinnedCount?:    number;
  compareCount?:   number;
  colonyCount?:    number;
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
}

type PrimaryWorkspace = 'explore' | 'plan' | 'review';
const PLAYER_WORKSPACES: PrimaryWorkspace[] = ['explore', 'plan', 'review'];

interface RouteDescriptor {
  route: Route;
  label: string;
  testid: string;
  badge?: number;
  title?: string;
}

interface WorkspaceMeta {
  title: string;
  primaryLabel: string;
  supportingText: string;
  nextAction: string;
  statusLabel: string;
  statusTone: 'available' | 'canonical' | 'caution';
}

export function NavBar({
  current, onNavigate,
  compareCount, fcCount,
  health,
  fullWidth = false,
  selectedSystem = null,
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
      { route: 'search-tuning' as const, label: 'Development Tuning', testid: 'nav-search-tuning' },
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
                  <Tab
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
                    <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                      Selected system
                    </p>
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

// ─── Logo — minimal "compass / star reticle" mark ─────────────────────────
function Logo() {
  return (
    <div
      className="relative w-10 h-10 rounded-chunk-sm grid place-items-center"
      style={{
        background: 'radial-gradient(circle at 30% 25%, rgba(111,229,255,0.15), transparent 38%), linear-gradient(135deg, #1c1f24 0%, #0a0c10 100%)',
        boxShadow:
          'inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(255,122,20,0.4), 0 0 12px -2px rgba(255,122,20,0.5), 0 10px 22px -18px rgba(111,229,255,0.55)',
      }}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#ff7a14" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" stroke="#ff7a14" strokeOpacity="0.85" />
        <path d="M12 3v18M3 12h18" stroke="#c8ccd1" strokeOpacity="0.5" />
        <path d="M12 7l2.5 5L12 17l-2.5-5L12 7z" fill="#ff7a14" stroke="#ff7a14" />
      </svg>
    </div>
  );
}

function Tab({ label, active, onClick, testid, badge, title, compact = false }: {
  label:   string;
  active:  boolean;
  onClick: () => void;
  testid:  string;
  badge?:  number;
  title?:  string;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      title={title}
      aria-current={active ? 'page' : undefined}
      className={[
        'group relative inline-flex items-center gap-1.5 px-3.5 py-2 rounded-chunk-sm whitespace-nowrap',
        compact ? 'w-full justify-between' : '',
        'font-display font-bold text-[12.5px] tracking-[0.1em] uppercase',
        'transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80',
        active
          ? 'text-white shadow-brand-glow'
          : 'text-silver hover:text-white hover:bg-bg3/70',
      ].join(' ')}
      style={active ? {
        background: 'linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0) 20%), linear-gradient(180deg, rgba(255,122,20,0.3) 0%, rgba(255,122,20,0.12) 100%)',
        border: '1px solid rgba(255,122,20,0.55)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 10px 24px -18px rgba(255,122,20,0.75)',
      } : {
        border: '1px solid rgba(148,163,184,0.08)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.02)',
      }}
    >
      <span>{label}</span>
      {badge !== undefined && badge > 0 && (
        <span
          className="ml-1 min-w-[18px] h-[18px] px-1.5 grid place-items-center rounded-full font-mono text-[10px] font-bold"
          style={{
            background: 'linear-gradient(180deg, #ff8a30, #cc5400)',
            color: '#fff',
            boxShadow: '0 0 0 1px rgba(255,122,20,0.5), 0 0 8px rgba(255,122,20,0.5)',
          }}
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
      {active && (
        <span
          className="absolute -bottom-[7px] left-1/2 -translate-x-1/2 h-[3px] w-8 rounded-full"
          style={{ background: 'linear-gradient(90deg, transparent, #ff7a14, transparent)' }}
        />
      )}
    </button>
  );
}

function MenuSection({
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
          <Tab
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

function OperatorModePanel({
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
            <Tab
              label="Admin"
              active={current === 'admin'}
              onClick={() => onNavigate('admin')}
              testid={mobile ? 'nav-admin-mobile-operator-mode' : 'nav-admin-operator-mode'}
            />
            <Tab
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

function OperatorModeMenu({
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
        <Tab
          label="Return to player workspace"
          active={false}
          onClick={() => onNavigate('finder')}
          testid="nav-return-to-player-menu"
          compact
        />
        <Tab
          label="Admin"
          active={current === 'admin'}
          onClick={() => onNavigate('admin')}
          testid="nav-admin-operator-menu"
          compact
        />
        <Tab
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

function primaryWorkspaceForRoute(route: Route): PrimaryWorkspace | null {
  if (route === 'finder' || route === 'map' || route === 'search-tuning') return 'explore';
  if (route === 'my-work' || route === 'watchlist' || route === 'pinned' || route === 'colony' || route === 'colony-planner') return 'plan';
  if (route === 'compare' || route === 'fc') return 'review';
  return null;
}

function isRouteActive(current: Route, target: Route): boolean {
  if (current === target) return true;
  if (target === 'my-work' && (current === 'watchlist' || current === 'pinned')) return true;
  if (target === 'colony-planner' && current === 'colony') return true;
  return false;
}

function workspaceMetaForRoute(route: Route): WorkspaceMeta {
  switch (route) {
    case 'finder':
      return {
        title: 'Finder',
        primaryLabel: 'Explore',
        supportingText: 'Find promising systems. Save them for later or inspect them before starting a plan.',
        nextAction: 'Save systems for later or inspect them before starting a plan.',
        statusLabel: 'Finder',
        statusTone: 'available',
      };
    case 'map':
      return {
        title: 'Galactic Map',
        primaryLabel: 'Explore',
        supportingText: 'Use the map as a secondary Explore aid for current Finder results. It stays discoverability-focused and does not become a planning cockpit in this slice.',
        nextAction: 'Inspect a mapped system or return to Finder for the main discovery flow.',
        statusLabel: 'Secondary Explore surface',
        statusTone: 'available',
      };
    case 'search-tuning':
      return {
        title: 'Development Tuning',
        primaryLabel: 'Explore',
        supportingText: 'Refine discovery weighting and candidate filters without changing the core Finder or planning logic.',
        nextAction: 'Run a search, inspect a candidate, then enter Plan from a real system.',
        statusLabel: 'Explore support tool',
        statusTone: 'available',
      };
    case 'colony-planner':
      return {
        title: 'Colony Planner',
        primaryLabel: 'Plan',
        supportingText: 'Use the canonical live planning workspace for serious colony planning. Simulation preview remains reusable inventory only and is not wired here.',
        nextAction: 'Plan from a selected system or return to Explore to choose one safely.',
        statusLabel: 'Canonical live planner',
        statusTone: 'canonical',
      };
    case 'my-work':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Return to saved systems, local plans, and established colony work without splitting that context between Watchlist, Pins, and the planner.',
        nextAction: 'Resume a saved system, continue a plan, or review established colony work.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'watchlist':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Watchlist now feeds the Saved Systems view in My Work so synced saved candidates sit beside local planning context.',
        nextAction: 'Inspect a saved system or start planning from a deliberate hand-off.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'pinned':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Pins now feed the Saved Systems view in My Work so local shortlist context stays beside saved systems and plans.',
        nextAction: 'Inspect a saved system or continue from active planning work.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'compare':
      return {
        title: 'Compare',
        primaryLabel: 'Review',
        supportingText: 'Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace.',
        nextAction: 'Inspect a compared system or return to Explore to find a better candidate.',
        statusLabel: 'Decision review',
        statusTone: 'available',
      };
    case 'fc':
      return {
        title: 'FC Route Planner',
        primaryLabel: 'Review',
        supportingText: 'Use fleet-carrier routing as a supporting tool for player logistics without turning it into a primary Explore or Plan workspace.',
        nextAction: 'Review route support needs, then return to Explore or Plan for system work.',
        statusLabel: 'Supporting tool',
        statusTone: 'available',
      };
    case 'colony':
      return {
        title: 'Colony Tracker',
        primaryLabel: 'Plan',
        supportingText: 'Colony tracking remains available by route while My Work becomes the calm player-facing home for saved systems, plans, and colonies.',
        nextAction: 'Use My Work for the current player flow, or inspect tracked systems directly.',
        statusLabel: 'Supporting tracker',
        statusTone: 'available',
      };
    case 'admin':
      return {
        title: 'Admin',
        primaryLabel: 'Operator',
        supportingText: 'Admin tools remain separate from normal player navigation and are not promoted into the Explore, Plan, or Review hierarchy.',
        nextAction: 'Use only when operator/admin access is intentionally required.',
        statusLabel: 'Operator-only tools',
        statusTone: 'caution',
      };
    case 'operator':
      return {
        title: 'Operator Cockpit',
        primaryLabel: 'Operator',
        supportingText: 'Read-only operator surfaces remain outside the normal player shell and are not part of the player-facing primary hierarchy.',
        nextAction: 'Use only for guarded operator review tasks.',
        statusLabel: 'Operator-only tools',
        statusTone: 'caution',
      };
    case 'planner-preview':
      return {
        title: 'Planner Preview',
        primaryLabel: 'Preview',
        supportingText: 'The isolated planner preview stays separate from the live planner so visual experiments never blur into real player workflows.',
        nextAction: 'Return to the live planner for real player workflows.',
        statusLabel: 'Preview-only route',
        statusTone: 'caution',
      };
    case 'chip-preview':
      return {
        title: 'Chip Preview',
        primaryLabel: 'Preview',
        supportingText: 'This isolated route renders the paired economy chip on its own so shape and chrome tweaks stay separate from live Finder workflows.',
        nextAction: 'Judge the chip shape here, then return to Finder once it feels right.',
        statusLabel: 'Preview-only route',
        statusTone: 'caution',
      };
  }
}
