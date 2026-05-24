import { useState } from 'react';
import type { SystemResult } from '@/types/api';
import {
  ratingTier,
  formatPopulationForSystem,
  formatConfidence,
  formatDistance,
  formatCoords,
  isInhabited,
  systemStatusLabel,
} from '@/lib/format';
import { displayRationale } from '@/lib/rationale';
import {
  Pin, Scale, Eye, Map, Copy, ChevronDown, Search,
  Rocket,
} from 'lucide-react';

/**
 * One row in the search-results list — chunky brushed-metal card with
 * collapsible body.
 *
 * Stateless: parents pass action callbacks (onPin / onWatch / onCompare /
 * onOpenDetail / onOpenColonyPlanner / onShowOnMap). The card only owns the
 * open/closed toggle.
 */
export interface ResultCardProps {
  system: SystemResult;
  index:  number;
  isPinned?: boolean;
  isCompared?: boolean;
  onPin?:     (id64: number) => void;
  onCompare?: (id64: number) => void;
  onWatch?:   (id64: number) => void;
  onShowOnMap?:  (id64: number) => void;
  onOpenDetail?: (id64: number, options?: { focus?: 'colony-planner' }) => void;
  onOpenColonyPlanner?: (id64: number) => void;
}

export function ResultCard({
  system, index, isPinned = false, isCompared = false,
  onPin, onCompare, onWatch, onShowOnMap, onOpenDetail, onOpenColonyPlanner,
}: ResultCardProps) {
  const [open, setOpen] = useState(false);

  const rating     = system._rating;
  const score      = rating?.score ?? null;
  const tier       = ratingTier(score);
  const scoreLabel = `Rating score: ${score ?? '—'}/100`;
  const conf       = formatConfidence(rating?.confidence);
  const inhabited  = isInhabited(system);
  const dist       = formatDistance(system.distance) ?? '—';
  const popLabel   = formatPopulationForSystem(system);
  const status     = systemStatusLabel(system);
  const systemId64 = Number(system.id64);
  const hasValidSystemId = Number.isFinite(systemId64) && systemId64 > 0;
  const openColonyPlanner = () => {
    if (!hasValidSystemId) return;
    if (onOpenColonyPlanner) {
      onOpenColonyPlanner(systemId64);
    } else {
      onOpenDetail?.(systemId64, { focus: 'colony-planner' });
    }
  };

  return (
    <article
      data-testid={`result-card-${system.id64}`}
      className="panel-thin overflow-hidden transition-all duration-200 hover:border-orange/40"
      style={{
        borderColor: inhabited ? 'rgba(248,113,113,0.35)' : undefined,
      }}
    >
      {/* ── Header (always visible, click toggles body) ────────────── */}
      <header
        onClick={() => setOpen((v) => !v)}
        className="flex flex-wrap items-center gap-2.5 px-4 py-3 cursor-pointer select-none"
      >
        {/* Index plate */}
        <span
          className="font-mono text-[11px] font-bold tracking-wider min-w-[32px] text-center px-1.5 py-0.5 rounded-md"
          style={{
            background: 'linear-gradient(180deg, hsl(214 8% 22%), hsl(216 10% 14%))',
            color: '#c8ccd1',
            border: '1px solid hsl(216 10% 30%)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
          }}
        >
          #{index + 1}
        </span>

        {/* Pin & Compare quick-toggles */}
        <IconToggle
          active={isPinned}
          onClick={(e) => { e.stopPropagation(); onPin?.(system.id64); }}
          aria-label={isPinned ? 'Unpin system' : 'Pin system'}
          testid={`result-card-pin-${system.id64}`}
        >
          <Pin size={14} className={isPinned ? 'text-orange-lt fill-orange/40' : ''} />
        </IconToggle>
        <IconToggle
          active={isCompared}
          onClick={(e) => { e.stopPropagation(); onCompare?.(system.id64); }}
          aria-label={isCompared ? 'Remove from comparison' : 'Add to comparison'}
          testid={`result-card-compare-${system.id64}`}
        >
          <Scale size={14} className={isCompared ? 'text-orange-lt' : ''} />
        </IconToggle>

        {/* Name */}
        <h3 className="font-mono text-[15px] font-bold tracking-wider text-orange flex-1 min-w-0 truncate">
          {system.name || 'Unknown System'}
        </h3>

        {/* Distance */}
        <span className="font-mono text-xs tabular-nums text-silver px-2 py-0.5 rounded-md bg-bg3/60 border border-border">
          {dist === '—' ? <span className="text-silver-dk">— LY</span> : <>{dist.replace(/ LY$/, '')} <span className="text-silver-dk">LY</span></>}
        </span>

        {/* Colonised pill */}
        <span
          className={[
            'chip',
            inhabited ? 'border-red/45 text-red bg-red/10' : 'border-green/45 text-green bg-green/10',
          ].join(' ')}
          style={inhabited ? {
            background: 'linear-gradient(180deg, rgba(248,113,113,0.18), rgba(248,113,113,0.08))',
          } : {
            background: 'linear-gradient(180deg, rgba(74,222,128,0.18), rgba(74,222,128,0.08))',
          }}
        >
          {status === 'Colonised' ? 'COL' : status === 'Colonising' ? 'BUILD' : 'FREE'}
        </span>

        {/* Population */}
        <span className="chip chip-silver">{popLabel}</span>

        {/* Rating badge — bigger, chunkier */}
        <span
          className="font-mono text-[11px] font-bold tracking-wider px-2.5 py-1 rounded-chunk border"
          style={{
            background: `linear-gradient(180deg, ${tier.fillColor}33, ${tier.fillColor}11)`,
            borderColor: `${tier.fillColor}88`,
            color: tier.fillColor,
            boxShadow: `inset 0 1px 0 rgba(255,255,255,0.08), 0 0 12px -4px ${tier.fillColor}66`,
          }}
          title={`Score: ${score ?? '—'}/100`}
        >
          {tier.label} {score ?? '—'}
        </span>

        {/* Confidence */}
        {conf && (
          <span
            className="font-mono text-[10px] text-silver-dk hidden sm:inline-flex items-center gap-0.5"
            title={`Rating confidence: ${conf.tier} (${conf.pct}%)`}
          >
            <span
              className={[
                conf.tier === 'High'   && 'text-green',
                conf.tier === 'Medium' && 'text-gold',
                conf.tier === 'Low'    && 'text-red',
              ].filter(Boolean).join(' ')}
            >
              {conf.symbol}
            </span>
            {conf.pct}%
          </span>
        )}

        {/* Score fill bar */}
        <span
          className="block w-20 h-2 rounded-full overflow-hidden"
          role="img"
          aria-label={scoreLabel}
          title={scoreLabel}
          style={{
            background: 'linear-gradient(180deg, hsl(216 10% 12%), hsl(218 11% 8%))',
            border: '1px solid hsl(216 10% 26%)',
            boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.6)',
          }}
        >
          <span
            className="block h-full transition-all duration-500"
            aria-hidden="true"
            style={{
              width: `${Math.max(0, Math.min(100, score ?? 0))}%`,
              background: `linear-gradient(90deg, ${tier.fillColor}, ${tier.fillColor}cc)`,
              boxShadow: `0 0 8px ${tier.fillColor}88`,
            }}
          />
        </span>

        {/* Caret */}
        <ChevronDown
          size={16}
          className={['text-silver-dk transition-transform duration-200', open && 'rotate-180'].filter(Boolean).join(' ')}
        />
      </header>

      {/* ── Body (toggled) ────────────────────────────────────────── */}
      {open && (
        <div className="border-t border-border/70 px-4 py-4 space-y-3 animate-fade-up"
             style={{ background: 'linear-gradient(180deg, rgba(20,22,26,0.3), rgba(20,22,26,0.6))' }}>
          {displayRationale(rating?.rationale) && (
            <p className="text-silver-dk italic leading-snug text-sm">
              {displayRationale(rating?.rationale)}
            </p>
          )}
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs font-mono">
            {system.primaryEconomy && <Row label="Economy"    value={system.primaryEconomy} highlight />}
            {system.allegiance     && <Row label="Allegiance" value={system.allegiance} />}
            {system.security       && <Row label="Security"   value={system.security} />}
            <Row
              label="Coords"
              value={formatCoords(system.coords, system.id64)}
            />
          </dl>

          {(system.elw_count || system.ww_count || system.ammonia_count ||
            system.terraformable_count || system.bio_signal_total) ? (
            <div className="flex flex-wrap gap-1.5 text-[10px] font-mono pt-1">
              {bodyChip('ELW',   system.elw_count)}
              {bodyChip('WW',    system.ww_count)}
              {bodyChip('AW',    system.ammonia_count)}
              {bodyChip('Terra', system.terraformable_count)}
              {bodyChip('Bio',   system.bio_signal_total)}
              {bodyChip('Geo',   system.geo_signal_total)}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2 pt-1">
            {onOpenDetail && (
              <ActionButton onClick={() => onOpenDetail(system.id64)} primary>
                <Search size={13} className="mr-1.5" /> Details
              </ActionButton>
            )}
            {(onOpenColonyPlanner || onOpenDetail) && (
              <ActionButton
                onClick={() => {
                  openColonyPlanner();
                }}
                disabled={!hasValidSystemId}
              >
                <Rocket size={13} className="mr-1.5" /> Evaluate in Colony Planner
              </ActionButton>
            )}
            <ActionButton onClick={() => onWatch?.(system.id64)}>
              <Eye size={13} className="mr-1.5" /> Watch
            </ActionButton>
            <ActionButton onClick={() => onShowOnMap?.(system.id64)}>
              <Map size={13} className="mr-1.5" /> Map
            </ActionButton>
            <ActionButton onClick={() => { void navigator.clipboard?.writeText?.(system.name || 'Unknown System'); }}>
              <Copy size={13} className="mr-1.5" /> Copy name
            </ActionButton>
          </div>
        </div>
      )}
    </article>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function Row({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: boolean }) {
  return (
    <>
      <dt className="text-silver-dk uppercase tracking-wider text-[10px]">{label}</dt>
      <dd className={highlight ? 'text-orange-lt' : 'text-silver'}>{value}</dd>
    </>
  );
}

function bodyChip(label: string, count: number | null | undefined) {
  if (!count || count <= 0) return null;
  return (
    <span className="chip">
      {label} <span className="text-orange font-bold tabular-nums">{count}</span>
    </span>
  );
}

function IconToggle({
  active, onClick, children, testid, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean; testid: string }) {
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      aria-pressed={active}
      className={[
        'grid place-items-center w-7 h-7 rounded-md transition-all duration-150',
        active
          ? 'text-orange-lt bg-orange/10 border border-orange/45'
          : 'text-silver-dk hover:text-silver border border-transparent hover:border-border',
      ].join(' ')}
      {...rest}
    >
      {children}
    </button>
  );
}

function ActionButton({
  onClick, children, primary, disabled = false,
}: {
  onClick: () => void;
  children: React.ReactNode;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={[
        primary ? 'btn-primary' : 'btn-metal',
        'inline-flex items-center text-[11px] py-1.5 px-3',
        disabled ? 'cursor-not-allowed opacity-45' : '',
      ].join(' ')}
    >
      {children}
    </button>
  );
}
