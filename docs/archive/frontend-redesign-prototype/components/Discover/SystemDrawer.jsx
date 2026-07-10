import React from 'react';
import { ratingTier, fmtPop, ECONOMIES, ECON_COLORS } from '../../lib/mockData';
import { Panel, PanelHeader, SectionLabel, RatingBar, TierPill, HudButton } from '../UI/Hud';
import { RatingRadar } from './RatingRadar';
import { Bookmark, Scale, Route, MessageSquare, X, ExternalLink, MapPin, Star } from 'lucide-react';

export function SystemDrawer({ system, watched, onClose, onWatch }) {
  if (!system) {
    return (
      <Panel className="h-full overflow-hidden flex items-center justify-center text-center p-6" chamfer={false}>
        <div>
          <Star className="mx-auto mb-3 text-[var(--steel-500)]" size={28} strokeWidth={1.2} />
          <div className="font-display text-[12px] tracking-[0.16em] text-[var(--steel-300)] mb-1">SELECT A SYSTEM</div>
          <p className="font-mono text-[10px] text-[var(--steel-500)] leading-relaxed max-w-[200px] mx-auto">
            Click any row in the result list — or any star on the map — to see its full rating breakdown here.
          </p>
        </div>
      </Panel>
    );
  }

  const tier = ratingTier(system.score);

  return (
    <Panel className="h-full overflow-hidden flex flex-col" chamfer={false} active>
      <PanelHeader
        icon={<MapPin size={13} strokeWidth={1.6} />}
        title="SYSTEM BRIEFING"
        sub={`${system.x}, ${system.y}, ${system.z}`}
        right={
          <button onClick={onClose} className="p-1 text-[var(--steel-400)] hover:text-[var(--steel-100)]">
            <X size={14} strokeWidth={1.5} />
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Headline */}
        <div className="space-y-1.5">
          <h2 className="font-display text-[16px] tracking-[0.06em] text-[var(--steel-100)] text-glow-orange">
            {system.name}
          </h2>
          <p className="text-[12px] text-[var(--steel-300)] italic leading-snug">
            {system.rationale}
          </p>
          <div className="flex items-center gap-2 pt-1">
            <TierPill score={system.score} tier={tier} />
            <span className="font-mono text-[10px] text-[var(--steel-400)]">
              confidence{' '}
              <span className="text-[var(--steel-200)] tabular-nums">
                {(system.confidence * 100).toFixed(0)}%
              </span>
            </span>
            <span className="text-[var(--steel-700)]">·</span>
            <span className="font-mono text-[10px] text-[var(--steel-400)]">
              {system.distance.toFixed(1)} LY
            </span>
          </div>
        </div>

        {/* THE HEADLINE GRAPHIC: rating radar */}
        <div className="flex items-center justify-center py-1">
          <RatingRadar breakdown={system.breakdown} suggested={system.economySuggestion} size={220} />
        </div>

        {/* Per-economy bars in detail */}
        <div className="space-y-1.5">
          <SectionLabel>ECONOMY BREAKDOWN</SectionLabel>
          {Object.entries(system.breakdown).map(([k, v]) => (
            <RatingBar
              key={k}
              label={k}
              score={v}
              color={ECON_COLORS[k] || 'var(--ed-orange)'}
              size="sm"
            />
          ))}
        </div>

        {/* Vital stats */}
        <div className="space-y-1.5">
          <SectionLabel>SYSTEM VITALS</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Population"  value={fmtPop(system.population)} />
            <Stat label="Allegiance"  value={system.allegiance} />
            <Stat label="Security"    value={system.security} />
            <Stat label="Status"      value={system.is_colonised ? 'Colonised' : 'Free'} />
            <Stat label="ELW / WW"    value={`${system.bodies.elw} / ${system.bodies.ww}`} />
            <Stat label="Terraform"   value={system.bodies.terra} />
            <Stat label="Bio / Geo"   value={`${system.signals.bio} / ${system.signals.geo}`} />
            <Stat label="Landables"   value={system.bodies.landable} />
          </div>
        </div>

        {/* Notes (placeholder) */}
        <div className="space-y-1.5">
          <SectionLabel>NOTES</SectionLabel>
          <button className="w-full text-left px-3 py-2 rounded-sm border border-dashed border-[var(--steel-700)] text-[var(--steel-500)] font-mono text-[10px] hover:text-[var(--steel-300)] hover:border-[var(--steel-500)]">
            <MessageSquare size={11} strokeWidth={1.5} className="inline mr-1.5" />
            Add a private note about this system…
          </button>
        </div>
      </div>

      {/* Action footer */}
      <footer className="border-t border-[var(--steel-700)] p-3 grid grid-cols-3 gap-1.5">
        <HudButton
          icon={Bookmark}
          onClick={() => onWatch(system.id64)}
          active={watched}
          size="sm"
        >
          {watched ? 'WATCHED' : 'WATCH'}
        </HudButton>
        <HudButton icon={Scale}  size="sm">COMPARE</HudButton>
        <HudButton icon={Route}  size="sm">ROUTE</HudButton>
      </footer>
    </Panel>
  );
}

function Stat({ label, value }) {
  return (
    <div className="readout rounded-sm px-2 py-1.5">
      <div className="font-mono text-[8px] text-[var(--steel-500)] uppercase tracking-wider">{label}</div>
      <div className="font-display text-[12px] tracking-[0.06em] text-[var(--ed-orange-lt)]">{value}</div>
    </div>
  );
}
