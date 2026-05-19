import type { Route } from '@/hooks/useHashRoute';
import { useDensity } from '@/hooks/useDensity';
import { useEffect, useMemo, useRef, useState } from 'react';

/** Top-bar nav for the v2 app — sticky chrome panel with brushed-metal sheen
 *  and an ED-orange "active-tab" indicator. Height tuned to match the EDDN
 *  bottom ticker for visual symmetry. */
export interface NavBarProps {
  current:    Route;
  onNavigate: (r: Route) => void;
  watchlistCount?: number | null;
  pinnedCount?:    number;
  compareCount?:   number;
  colonyCount?:    number;
  fcCount?:        number;
  health?:         string;
}

export function NavBar({
  current, onNavigate,
  watchlistCount, pinnedCount, compareCount, colonyCount, fcCount,
  health,
}: NavBarProps) {
  const ok = (health ?? '').toLowerCase() === 'online';
  const { density, cycle } = useDensity();
  const densityIcon  = density === 'compact' ? '▬' : density === 'spacious' ? '☰' : '≡';
  const densityLabel = density.charAt(0).toUpperCase() + density.slice(1);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const tabs = useMemo(() => ([
    { route: 'finder' as const, label: '🔍 Finder', testid: 'nav-finder' },
    { route: 'watchlist' as const, label: '☁️ Watchlist', testid: 'nav-watchlist', badge: watchlistCount ?? undefined, title: 'Watchlist — synced to your account, alerts on changes' },
    { route: 'pinned' as const, label: '📌 Pins', testid: 'nav-pinned', badge: pinnedCount, title: 'Pins — quick local shortlist on this device only' },
    { route: 'compare' as const, label: '⚖️ Compare', testid: 'nav-compare', badge: compareCount },
    { route: 'search-tuning' as const, label: '🎚️ Advanced Search Tuning', testid: 'nav-search-tuning' },
    { route: 'fc' as const, label: '🚀 FC Planner', testid: 'nav-fc', badge: fcCount },
    { route: 'colony' as const, label: '🏗️ Colony Tracker', testid: 'nav-colony', badge: colonyCount },
    { route: 'map' as const, label: '🗺️ Map', testid: 'nav-map' },
    { route: 'admin' as const, label: '⚙️ Admin', testid: 'nav-admin' },
  ]), [watchlistCount, pinnedCount, compareCount, fcCount, colonyCount]);

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

  const currentTab = tabs.find((tab) => tab.route === current);
  return (
    <nav
      className="sticky top-3 z-30 mx-auto mb-8 max-w-[1840px] px-3"
      data-testid="navbar"
    >
      {/* py-1.5 here matches the EDDN ticker bar height so top + bottom chrome align */}
      <div className="panel relative flex items-center gap-3 sm:gap-5 px-4 sm:px-6 py-1.5">
        {/* ── Logo lockup ─────────────────────────────── */}
        <div className="flex items-center gap-3 shrink-0">
          <Logo />
          <div className="flex flex-col leading-tight hidden sm:flex">
            <span className="font-mono text-[15px] font-bold tracking-[0.18em] text-orange">
              ED:FINDER
            </span>
            <span className="font-mono text-[9px] tracking-[0.32em] text-silver-dk -mt-0.5">
              v2
            </span>
          </div>
        </div>

        {/* divider */}
        <span className="h-9 w-px bg-gradient-to-b from-transparent via-border-bright to-transparent shrink-0 hidden sm:block" />

        <div className="hidden lg:flex flex-1 items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <Tab
              key={tab.route}
              label={tab.label}
              active={current === tab.route}
              onClick={() => handleNavigate(tab.route)}
              testid={tab.testid}
              badge={tab.badge}
              title={tab.title}
            />
          ))}
        </div>

        <div className="lg:hidden min-w-0 flex-1">
          <span className="truncate rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
            {currentTab?.label ?? 'Route'}
          </span>
        </div>

        {/* ── Density toggle ─────────────────────────── */}
        <button
          type="button"
          onClick={cycle}
          data-testid="nav-density-toggle"
          title={`Density: ${densityLabel} (click to cycle)`}
          aria-label={`Density: ${densityLabel}, click to cycle`}
          className="flex items-center justify-center shrink-0 w-8 h-8 rounded-full bg-bg3/60 border border-border text-silver hover:text-orange-lt hover:border-orange-dk transition-colors font-mono text-[14px] leading-none"
        >
          <span aria-hidden>{densityIcon}</span>
        </button>

        <button
          ref={toggleRef}
          type="button"
          data-testid="nav-menu-toggle"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((value) => !value)}
          className="lg:hidden inline-flex items-center justify-center rounded-chunk-sm border border-border bg-bg3/55 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-silver hover:border-orange/50 hover:text-orange"
        >
          Menu
        </button>

        {/* ── Status pill — always visible across breakpoints.
         * Collapses to a dot-only chip on narrow screens, expands with
         * the text label at md+. Used to be 'hidden md:flex' which led
         * users on smaller viewports to think the backend was offline. */}
        <div
          className="flex items-center gap-2 shrink-0 px-2 md:px-3 py-1.5 rounded-full bg-bg3/60 border border-border"
          title={ok ? `Backend online — ${health}` : (health ?? 'Checking…')}
          data-testid="nav-status-pill"
        >
          <span className={[
            'h-2 w-2 rounded-full',
            ok ? 'bg-green shadow-[0_0_8px_2px_rgba(74,222,128,0.55)]'
               : 'bg-red shadow-[0_0_8px_2px_rgba(248,113,113,0.55)]',
          ].join(' ')} />
          <span className="hidden md:inline font-mono text-[10px] tracking-wider text-silver-dk uppercase">
            {ok ? 'Online' : (health ?? 'API')}
          </span>
        </div>
      </div>

      {menuOpen && (
        <div
          ref={menuRef}
          data-testid="nav-menu-panel"
          className="panel mt-2 p-2 lg:hidden"
        >
          <div className="grid gap-1">
            {tabs.map((tab) => (
              <Tab
                key={`menu-${tab.route}`}
                label={tab.label}
                active={current === tab.route}
                onClick={() => handleNavigate(tab.route)}
                testid={`${tab.testid}-menu`}
                badge={tab.badge}
                title={tab.title}
                compact
              />
            ))}
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
        background: 'linear-gradient(135deg, #1c1f24 0%, #0a0c10 100%)',
        boxShadow:
          'inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(255,122,20,0.4), 0 0 12px -2px rgba(255,122,20,0.5)',
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
      className={[
        'group relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-chunk-sm whitespace-nowrap',
        compact ? 'w-full justify-between' : '',
        'font-display font-bold text-[12.5px] tracking-[0.1em] uppercase',
        'transition-all duration-200',
        active
          ? 'text-white shadow-brand-glow'
          : 'text-silver hover:text-white hover:bg-bg3/70',
      ].join(' ')}
      style={active ? {
        background: 'linear-gradient(180deg, rgba(255,122,20,0.32) 0%, rgba(255,122,20,0.12) 100%)',
        border: '1px solid rgba(255,122,20,0.55)',
      } : { border: '1px solid transparent' }}
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
