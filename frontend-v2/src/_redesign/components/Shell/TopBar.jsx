import React from 'react';
import {
  Compass, Eye, Pin, Scale, Sliders, Route, Building2, Map, Settings,
  Activity, Database,
} from 'lucide-react';
import { Readout } from '../UI/Hud';

const TABS = [
  { key: 'finder',    label: 'Finder',    icon: Compass    },
  { key: 'watchlist', label: 'Watchlist', icon: Eye,        badge: 7 },
  { key: 'pinned',    label: 'Pinned',    icon: Pin,        badge: 3 },
  { key: 'compare',   label: 'Compare',   icon: Scale,      badge: 2 },
  { key: 'optimizer', label: 'Advanced Search Tuning', icon: Sliders },
  { key: 'fc',        label: 'FC Route',  icon: Route,      badge: 4 },
  { key: 'colony',    label: 'Colony',    icon: Building2,  badge: 4 },
  { key: 'map',       label: 'Map',       icon: Map         },
  { key: 'admin',     label: 'Admin',     icon: Settings    },
];

export function TopBar({ tab, onTab }) {
  return (
    <header
      className="relative flex items-stretch h-14 border-b border-[hsla(232,22%,60%,0.22)] bg-[hsla(232,18%,12%,0.78)] backdrop-blur-xl"
      data-testid="top-bar"
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-4 border-r border-[hsla(232,22%,60%,0.22)] min-w-[230px]">
        <div className="relative w-8 h-8 flex items-center justify-center">
          <div className="absolute inset-0 border border-[var(--ed-orange-dk)] rounded-full" />
          <div className="absolute inset-1 border border-[var(--ed-orange)]/40 rounded-full sweep" />
          <div className="w-1.5 h-1.5 bg-[var(--ed-orange)] rounded-full text-glow-orange" />
        </div>
        <div className="leading-tight">
          <div className="font-display text-[13px] tracking-[0.22em] text-[var(--steel-100)]">ED:FINDER</div>
          <div className="font-mono text-[9px] text-[var(--steel-400)] tracking-wider">SELF-HOSTED · v3.2</div>
        </div>
      </div>

      {/* Tabs */}
      <nav
        className="flex items-stretch flex-1 overflow-x-auto"
        data-testid="tabs"
        style={{ scrollbarWidth: 'none' }}
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              onClick={() => onTab(t.key)}
              data-testid={`tab-${t.key}`}
              className={[
                'group relative flex items-center gap-2 px-4 border-r border-[var(--steel-700)] transition-all whitespace-nowrap',
                active
                  ? 'bg-gradient-to-b from-[var(--steel-800)] to-[var(--steel-850)] text-[var(--ed-orange-lt)]'
                  : 'text-[var(--steel-400)] hover:text-[var(--steel-200)] hover:bg-[var(--steel-850)]/60',
              ].join(' ')}
            >
              {active && (
                <span className="absolute top-0 left-0 right-0 h-[2px] bg-[var(--ed-orange)] text-glow-orange" />
              )}
              <Icon size={14} strokeWidth={1.6} />
              <span className="font-display text-[10px] tracking-[0.16em]">{t.label}</span>
              {t.badge && t.badge > 0 && (
                <span
                  className={[
                    'ml-1 px-1.5 py-px rounded-[2px] font-mono text-[9px] tabular-nums',
                    active
                      ? 'bg-[var(--ed-orange)] text-[var(--steel-980)]'
                      : 'bg-[var(--steel-700)] text-[var(--steel-200)]',
                  ].join(' ')}
                >
                  {t.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Live status */}
      <div className="flex items-center gap-2 px-4 border-l border-[hsla(232,22%,60%,0.22)]">
        <Readout size="sm" className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] hud-pulse" />
          EDDN
        </Readout>
        <Readout size="sm" className="hidden md:flex items-center gap-1.5">
          <Database size={9} strokeWidth={2} />
          186.2M
        </Readout>
        <Readout size="sm" className="hidden lg:flex items-center gap-1.5">
          <Activity size={9} strokeWidth={2} />
          12ms
        </Readout>
      </div>
    </header>
  );
}
