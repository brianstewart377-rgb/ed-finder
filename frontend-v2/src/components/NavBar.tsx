import type { Route } from '@/hooks/useHashRoute';

/** Top-bar nav for the v2 app. Sticky so it stays accessible while scrolling
 *  long result lists or the watchlist. */
export interface NavBarProps {
  current:    Route;
  onNavigate: (r: Route) => void;
  /** Watchlist count badge — null = not loaded yet, undefined = hide. */
  watchlistCount?: number | null;
  /** Pinned count badge — local-storage backed so null isn't meaningful. */
  pinnedCount?:   number;
  /** Compare count badge — also local-storage backed. */
  compareCount?:  number;
  health?:    string;
}

export function NavBar({ current, onNavigate, watchlistCount, pinnedCount, compareCount, health }: NavBarProps) {
  return (
    <nav className="sticky top-0 z-20 -mx-4 sm:-mx-8 mb-6 px-4 sm:px-8 py-3 bg-bg1/85 backdrop-blur border-b border-border">
      <div className="max-w-7xl mx-auto flex items-center gap-3 sm:gap-6">
        <span className="font-mono text-orange tracking-wider text-lg shrink-0">
          ED:FINDER <span className="text-text-dim text-[10px]">v2</span>
        </span>
        <div className="flex gap-1 flex-1 flex-wrap">
          <Tab active={current === 'finder'}    onClick={() => onNavigate('finder')}    label="🔍 Finder"    testid="nav-finder" />
          <Tab active={current === 'watchlist'} onClick={() => onNavigate('watchlist')} label="👁️ Watchlist" testid="nav-watchlist"
               badge={watchlistCount ?? undefined} />
          <Tab active={current === 'pinned'}    onClick={() => onNavigate('pinned')}    label="📌 Pinned"    testid="nav-pinned"
               badge={pinnedCount} />
          <Tab active={current === 'compare'}   onClick={() => onNavigate('compare')}   label="⚖️ Compare"   testid="nav-compare"
               badge={compareCount} />
          <Tab active={current === 'optimizer'} onClick={() => onNavigate('optimizer')} label="🎚️ Optimizer" testid="nav-optimizer" />
          <Tab active={current === 'map'}       onClick={() => onNavigate('map')}       label="🗺️ Map"       testid="nav-map" />
          <Tab active={current === 'admin'}     onClick={() => onNavigate('admin')}     label="⚙️ Admin"      testid="nav-admin" />
        </div>
        <span className="hidden sm:inline font-mono text-[10px] text-text-dim">
          {health ?? '…'}
        </span>
      </div>
    </nav>
  );
}

function Tab({ active, onClick, label, testid, badge }: {
  active:  boolean;
  onClick: () => void;
  label:   string;
  testid:  string;
  badge?:  number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={[
        'px-3 py-1.5 rounded font-mono text-xs transition-colors',
        active
          ? 'bg-orange/20 text-orange border border-orange/40'
          : 'text-text-dim border border-transparent hover:text-text hover:bg-bg3',
      ].join(' ')}
    >
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="ml-2 px-1.5 py-0.5 rounded bg-orange text-bg1 text-[10px] font-bold">
          {badge}
        </span>
      )}
    </button>
  );
}
