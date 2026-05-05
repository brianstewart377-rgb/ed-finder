import { useState } from 'react';
import type { SystemResult } from '@/types/api';
import {
  ratingTier,
  formatPopulation,
  formatConfidence,
  isInhabited,
} from '@/lib/format';

/**
 * One row in the search-results list.
 *
 * Composition root: `<ResultCard system={…} index={…} />`. All formatting
 * lives in `lib/format.ts`; this component only handles layout + the
 * collapsed/expanded toggle, which is the simplest piece of stateful
 * behaviour in the original vanilla version (~10 lines of JS).
 *
 * No global state, no context. The `onPin` / `onWatch` etc. action callbacks
 * are wired in by the parent so this card is trivial to unit-test in
 * isolation.
 */
export interface ResultCardProps {
  system: SystemResult;
  index:  number;
  onPin?:    (id64: number) => void;
  onWatch?:  (id64: number) => void;
  onShowOnMap?: (id64: number) => void;
}

export function ResultCard({ system, index, onPin, onWatch, onShowOnMap }: ResultCardProps) {
  const [open, setOpen] = useState(false);

  const rating     = system._rating;
  const score      = rating?.score ?? null;
  const tier       = ratingTier(score);
  const conf       = formatConfidence(rating?.confidence);
  const inhabited  = isInhabited(system);
  const dist       = system.distance != null ? system.distance.toFixed(2) : '?';
  const popLabel   = formatPopulation(system.population);

  // Background tint based on tier — subtle, doesn't fight the dark UI.
  const tintClass = inhabited
    ? 'border-red/40 bg-red/[0.04]'
    : 'border-border hover:border-orange-dk';

  return (
    <article
      data-testid={`result-card-${system.id64}`}
      className={[
        'rounded-md border bg-bg3/60 transition-colors duration-150',
        tintClass,
      ].join(' ')}
    >
      {/* ── Header (always visible, click toggles body) ────────────── */}
      <header
        onClick={() => setOpen((v) => !v)}
        className="flex flex-wrap items-center gap-2 px-3 py-2 cursor-pointer select-none"
      >
        <button
          type="button"
          aria-label="Pin system"
          onClick={(e) => { e.stopPropagation(); onPin?.(system.id64); }}
          className="text-base hover:scale-110 transition-transform"
        >
          📍
        </button>
        <span className="font-mono text-text-dim text-[11px] min-w-[28px]">
          #{index + 1}
        </span>
        <h3 className="font-mono text-orange text-sm font-semibold flex-1 min-w-0 truncate">
          {system.name || 'Unknown System'}
        </h3>
        <span className="font-mono text-text-dim text-xs whitespace-nowrap">
          {dist} LY
        </span>
        {/* Colonised pill */}
        <span
          className={[
            'text-[10px] px-1.5 py-0.5 rounded border font-mono',
            inhabited
              ? 'bg-red/20 text-red border-red/40'
              : 'bg-green/20 text-green border-green/40',
          ].join(' ')}
        >
          {inhabited ? 'COL' : 'FREE'}
        </span>
        {/* Population pill */}
        <span className="text-[10px] px-1.5 py-0.5 rounded border border-border text-text-dim font-mono">
          {popLabel}
        </span>
        {/* Rating badge */}
        <span
          className={[
            'text-[11px] px-2 py-0.5 rounded border font-mono font-bold',
            tier.label === 'EXCELLENT' && 'bg-green/20 text-green border-green/50',
            tier.label === 'GOOD'      && 'bg-gold/20 text-gold border-gold/50',
            tier.label === 'OK'        && 'bg-orange/20 text-orange border-orange/50',
            tier.label === 'POOR'      && 'bg-red/20 text-red border-red/50',
            tier.label === 'N/A'       && 'bg-bg4 text-text-dim border-border',
          ].filter(Boolean).join(' ')}
          title={`Score: ${score ?? '—'}/100`}
        >
          {tier.label} {score ?? '—'}
        </span>
        {/* Confidence */}
        {conf && (
          <span
            className="text-[10px] font-mono text-text-dim"
            title={`Rating confidence: ${conf.tier} (${conf.pct}%)`}
          >
            <span
              className={[
                'mr-0.5',
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
        {/* Score fill bar — micro-viz, instantly tells you 50 vs 90. */}
        <span className="block w-16 h-1.5 bg-bg4 rounded overflow-hidden">
          <span
            className="block h-full"
            style={{
              width: `${Math.max(0, Math.min(100, score ?? 0))}%`,
              backgroundColor: tier.fillColor,
            }}
          />
        </span>
        <span
          className={[
            'text-text-dim text-[10px] transition-transform duration-150',
            open && 'rotate-180',
          ].filter(Boolean).join(' ')}
        >
          ▼
        </span>
      </header>

      {/* ── Body (toggled) ────────────────────────────────────────── */}
      {open && (
        <div className="border-t border-border px-3 py-3 text-sm space-y-3">
          {/* Rationale, if present */}
          {rating?.rationale && (
            <p className="text-text-dim italic leading-snug">
              {rating.rationale}
            </p>
          )}
          {/* Key facts */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">
            {system.primaryEconomy && (
              <>
                <dt className="text-text-dim">Economy</dt>
                <dd className="text-text">{system.primaryEconomy}</dd>
              </>
            )}
            {system.allegiance && (
              <>
                <dt className="text-text-dim">Allegiance</dt>
                <dd className="text-text">{system.allegiance}</dd>
              </>
            )}
            {system.security && (
              <>
                <dt className="text-text-dim">Security</dt>
                <dd className="text-text">{system.security}</dd>
              </>
            )}
            {system.coords && (
              <>
                <dt className="text-text-dim">Coords</dt>
                <dd className="text-text">
                  {system.coords.x.toFixed(2)},
                  {' '}{system.coords.y.toFixed(2)},
                  {' '}{system.coords.z.toFixed(2)}
                </dd>
              </>
            )}
          </dl>
          {/* Body-count chips */}
          {(system.elw_count || system.ww_count || system.ammonia_count ||
            system.terraformable_count || system.bio_signal_total) && (
            <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
              {bodyChip('ELW',  system.elw_count)}
              {bodyChip('WW',   system.ww_count)}
              {bodyChip('AW',   system.ammonia_count)}
              {bodyChip('Terra', system.terraformable_count)}
              {bodyChip('Bio',   system.bio_signal_total)}
              {bodyChip('Geo',   system.geo_signal_total)}
            </div>
          )}
          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-1">
            <ActionButton onClick={() => onWatch?.(system.id64)}    icon="👁️" label="Watch" />
            <ActionButton onClick={() => onShowOnMap?.(system.id64)} icon="🗺️" label="Map" />
            <ActionButton
              onClick={() => navigator.clipboard.writeText(system.name)}
              icon="📋"
              label="Copy name"
            />
          </div>
        </div>
      )}
    </article>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Tiny helper components — kept inline to keep the slice self-contained.
// Promote to their own files only if a third site reuses them.
// ───────────────────────────────────────────────────────────────────────────
function bodyChip(label: string, count: number | null | undefined) {
  if (!count || count <= 0) return null;
  return (
    <span className="px-1.5 py-0.5 rounded bg-bg4 text-text border border-border">
      {label} <span className="text-orange font-bold">{count}</span>
    </span>
  );
}

function ActionButton({ onClick, icon, label }: {
  onClick: () => void;
  icon:    string;
  label:   string;
}) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="px-2 py-1 rounded bg-bg4 border border-border text-text-dim hover:text-orange hover:border-orange-dk transition-colors text-xs"
    >
      <span className="mr-1">{icon}</span>{label}
    </button>
  );
}
