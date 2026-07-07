import { useState } from 'react';
import type { SystemResult } from '@/types/api';
import {
  formatPopulationForSystem,
  formatDistance,
  formatCoords,
  isInhabited,
  systemStatusLabel,
} from '@/lib/format';
import { getFinderArchetypeSummary } from '@/lib/archetypes';
import {
  economyColor,
  economyLabel,
  economySoftColor,
  normaliseEconomyName,
} from '@/features/colony-planner/economyVisuals';
import {
  Pin, Scale, Eye, Map, Copy, ChevronDown, Search,
} from 'lucide-react';

/**
 * One row in the search-results list — chunky brushed-metal card with
 * collapsible body.
 *
 * Stateless: parents pass action callbacks (onPin / onToggleSavedForLater /
 * onCompare / onOpenDetail / onShowOnMap). The card only owns the
 * open/closed toggle.
 */
export interface ResultCardProps {
  system: SystemResult;
  index:  number;
  isPinned?: boolean;
  isCompared?: boolean;
  isSavedForLater?: boolean;
  savedActionState?: 'idle' | 'saving' | 'removing';
  onPin?:     (id64: number) => void;
  onCompare?: (id64: number) => void;
  onToggleSavedForLater?: (id64: number) => void;
  onShowOnMap?:  (id64: number) => void;
  onOpenDetail?: (id64: number) => void;
}

export function ResultCard({
  system, index, isPinned = false, isCompared = false,
  isSavedForLater = false, savedActionState = 'idle',
  onPin, onCompare, onToggleSavedForLater, onShowOnMap, onOpenDetail,
}: ResultCardProps) {
  const [open, setOpen] = useState(false);

  const inhabited  = isInhabited(system);
  const dist       = formatDistance(system.distance) ?? '—';
  const popLabel   = formatPopulationForSystem(system);
  const status     = systemStatusLabel(system);
  const archetypeScore = system.archetype_score ?? system.overall_development_potential ?? null;
  const archetypeLabel = getFinderArchetypeSummary(system);
  const systemId64 = Number(system.id64);
  const hasValidSystemId = Number.isFinite(systemId64) && systemId64 > 0;
  const saveActionBusy = savedActionState === 'saving' || savedActionState === 'removing';
  const saveActionLabel = savedActionState === 'saving'
    ? 'Saving…'
    : savedActionState === 'removing'
      ? 'Removing…'
      : isSavedForLater
        ? 'Saved'
        : 'Save for later';

  return (
    <article
      data-testid={`result-card-${system.id64}`}
      className="panel-thin overflow-hidden transition-all duration-200 hover:border-orange/40 hover:-translate-y-[1px]"
      style={{
        borderColor: inhabited ? 'rgba(248,113,113,0.35)' : undefined,
        boxShadow: open
          ? 'inset 0 1px 0 rgba(255,255,255,0.06), 0 18px 38px -24px rgba(0,0,0,0.92), 0 0 28px -26px rgba(255,122,20,0.45)'
          : undefined,
      }}
    >
      {/* ── Header (always visible, click toggles body) ────────────── */}
      <header
        onClick={() => setOpen((v) => !v)}
        className="flex flex-wrap items-center gap-2.5 px-4 py-3.5 cursor-pointer select-none"
        style={{
          background: open
            ? 'linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0))'
            : undefined,
        }}
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

        {archetypeLabel && (
          <ArchetypeChip
            archetypeKey={archetypeLabel.key}
            label={archetypeLabel.label}
            source={archetypeLabel.source}
            primaryEconomy={system.primaryEconomy ?? null}
            secondaryEconomy={system.secondaryEconomy ?? null}
          />
        )}

        <span
          data-testid="result-card-archetype-score"
          className="font-mono text-[11px] font-bold tracking-wider px-2.5 py-1 rounded-chunk border"
          style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0) 18%), linear-gradient(180deg, rgba(34,211,238,0.16), rgba(34,211,238,0.05))',
            borderColor: 'rgba(34,211,238,0.45)',
            color: '#67e8f9',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 12px 24px -20px rgba(34,211,238,0.55)',
          }}
          title={`Development score: ${archetypeScore ?? '—'}/100`}
        >
          Score {archetypeScore ?? '—'}
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
             style={{ background: 'linear-gradient(180deg, rgba(255,255,255,0.03), rgba(20,22,26,0.62))' }}>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs font-mono">
            {archetypeLabel && (
              <Row
                label={archetypeLabel.source === 'archetype' ? 'Primary archetype' : 'Suggested archetype'}
                value={archetypeLabel.label}
                highlight
              />
            )}
            {archetypeScore != null && <Row label="Development score" value={`${archetypeScore}/100`} highlight />}
            {system.buildability_score != null && <Row label="Buildability" value={`${system.buildability_score}/100`} />}
            {system.purity_score != null && <Row label="Purity" value={`${system.purity_score}/100`} />}
            {system.est_total_slots != null && <Row label="Est. slots" value={`${system.est_total_slots}`} />}
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
            <ActionButton
              onClick={() => onToggleSavedForLater?.(system.id64)}
              active={isSavedForLater}
              disabled={saveActionBusy}
              ariaLabel={isSavedForLater ? 'Remove from saved' : 'Save for later'}
              ariaBusy={saveActionBusy}
            >
              <Eye size={13} className="mr-1.5" />
              {saveActionLabel}
            </ActionButton>
            {onOpenDetail && (
              <ActionButton onClick={() => onOpenDetail(system.id64)} primary disabled={!hasValidSystemId}>
                <Search size={13} className="mr-1.5" /> Inspect system
              </ActionButton>
            )}
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

function ArchetypeChip({
  archetypeKey,
  label,
  source,
  primaryEconomy,
  secondaryEconomy,
}: {
  archetypeKey: string;
  label: string;
  source: 'archetype' | 'economy';
  primaryEconomy: string | null;
  secondaryEconomy: string | null;
}) {
  const parts = getSplitEconomyChipParts(archetypeKey, label, primaryEconomy, secondaryEconomy);

  if (!parts) {
    return (
      <span
        data-testid="result-card-suggested-archetype"
        className="font-mono text-[10px] font-bold tracking-[0.12em] px-2.5 py-1 rounded-chunk border uppercase"
        style={{
          background: 'linear-gradient(180deg, rgba(34,211,238,0.16), rgba(34,211,238,0.06))',
          borderColor: 'rgba(34,211,238,0.45)',
          color: '#67e8f9',
        }}
        title={`${source === 'archetype' ? 'Primary' : 'Suggested'} archetype: ${label}`}
      >
        {label}
      </span>
    );
  }

  return (
    <span
      data-testid="result-card-suggested-archetype"
      aria-label={label}
      className="relative inline-flex overflow-hidden rounded-chunk border uppercase"
      style={{
        borderColor: 'rgba(148,163,184,0.3)',
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.05), 0 0 10px -6px ${parts.primaryColor}, 0 0 10px -6px ${parts.secondaryColor}`,
      }}
      title={`${source === 'archetype' ? 'Primary' : 'Suggested'} archetype: ${label}`}
    >
      <span
        data-testid="result-card-suggested-archetype-primary-piece"
        className="relative z-[1] inline-flex items-center px-2.5 py-1 pr-4 font-mono text-[10px] font-bold tracking-[0.12em]"
        style={{
          background: `linear-gradient(180deg, ${parts.primarySoft}, rgba(15,23,42,0.08))`,
          color: '#d7f7fb',
        }}
      >
        <span data-testid="result-card-suggested-archetype-primary" style={{ color: parts.primaryColor }}>
          {parts.primaryEconomy}
        </span>
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-1/2 z-[2] w-8 -translate-x-1/2"
      >
        <svg viewBox="0 0 32 32" preserveAspectRatio="none" className="h-full w-full">
          <path
            d="M16 0 L14 10 C14 12.5 15.5 14 18 14 C21.2 14 23 16.1 23 19 C23 21.9 21.2 24 18 24 C15.5 24 14 25.5 14 28 L16 32"
            fill="none"
            stroke="rgba(11,18,24,0.92)"
            strokeWidth="5"
            strokeLinecap="round"
          />
          <path
            d="M16 0 L14.5 10 C14.5 12.3 15.8 13.6 18 13.6 C20.7 13.6 22.2 15.5 22.2 19 C22.2 22.5 20.7 24.4 18 24.4 C15.8 24.4 14.5 25.7 14.5 28 L16 32"
            fill="none"
            stroke="rgba(226,232,240,0.18)"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span
        data-testid="result-card-suggested-archetype-secondary-piece"
        className="relative z-[1] inline-flex items-center px-2.5 py-1 pl-4 font-mono text-[10px] font-bold tracking-[0.12em]"
        style={{
          background: `linear-gradient(180deg, ${parts.secondarySoft}, rgba(15,23,42,0.08))`,
          color: '#d7f7fb',
        }}
      >
        <span data-testid="result-card-suggested-archetype-secondary" style={{ color: parts.secondaryColor }}>
          {parts.secondaryEconomy}
        </span>
        {parts.suffix ? <span className="text-silver"> {parts.suffix}</span> : null}
      </span>
    </span>
  );
}

function getSplitEconomyChipParts(
  archetypeKey: string,
  label: string,
  primaryEconomy: string | null,
  secondaryEconomy: string | null,
): {
  primaryEconomy: string;
  secondaryEconomy: string;
  suffix: string;
  primaryColor: string;
  secondaryColor: string;
  primarySoft: string;
  secondarySoft: string;
} | null {
  const mappedPair = getSplitEconomyPairFromArchetypeKey(archetypeKey);
  if (mappedPair) {
    return {
      primaryEconomy: mappedPair.primaryEconomy,
      secondaryEconomy: mappedPair.secondaryEconomy,
      suffix: mappedPair.suffix,
      primaryColor: economyColor(mappedPair.primaryEconomy),
      secondaryColor: economyColor(mappedPair.secondaryEconomy),
      primarySoft: economySoftColor(mappedPair.primaryEconomy),
      secondarySoft: economySoftColor(mappedPair.secondaryEconomy),
    };
  }

  const labelPair = getSplitEconomyPairFromLabel(label);
  if (labelPair) {
    return {
      primaryEconomy: labelPair.primaryEconomy,
      secondaryEconomy: labelPair.secondaryEconomy,
      suffix: labelPair.suffix,
      primaryColor: economyColor(labelPair.primaryEconomy),
      secondaryColor: economyColor(labelPair.secondaryEconomy),
      primarySoft: economySoftColor(labelPair.primaryEconomy),
      secondarySoft: economySoftColor(labelPair.secondaryEconomy),
    };
  }

  if (!primaryEconomy || !secondaryEconomy) return null;

  const canonicalPrimary = economyLabel(primaryEconomy);
  const canonicalSecondary = economyLabel(secondaryEconomy);
  const prefix = `${canonicalPrimary} / ${canonicalSecondary}`;
  if (!label.startsWith(prefix)) return null;

  return {
    primaryEconomy: canonicalPrimary,
    secondaryEconomy: canonicalSecondary,
    suffix: label.slice(prefix.length).trim(),
    primaryColor: economyColor(canonicalPrimary),
    secondaryColor: economyColor(canonicalSecondary),
    primarySoft: economySoftColor(canonicalPrimary),
    secondarySoft: economySoftColor(canonicalSecondary),
  };
}

function getSplitEconomyPairFromLabel(label: string): {
  primaryEconomy: string;
  secondaryEconomy: string;
  suffix: string;
} | null {
  const slashIndex = label.indexOf('/');
  if (slashIndex === -1) return null;

  const primaryCandidate = label.slice(0, slashIndex).trim();
  const primaryEconomy = normaliseEconomyName(primaryCandidate);
  if (!primaryEconomy) return null;

  const rightSide = label.slice(slashIndex + 1).trim();
  const words = rightSide.split(/\s+/).filter(Boolean);
  for (let prefixLength = Math.min(words.length, 3); prefixLength >= 1; prefixLength -= 1) {
    const secondaryCandidate = words.slice(0, prefixLength).join(' ');
    const secondaryEconomy = normaliseEconomyName(secondaryCandidate);
    if (!secondaryEconomy) continue;
    return {
      primaryEconomy: economyLabel(primaryEconomy),
      secondaryEconomy: economyLabel(secondaryEconomy),
      suffix: words.slice(prefixLength).join(' ').trim(),
    };
  }

  return null;
}

function getSplitEconomyPairFromArchetypeKey(archetypeKey: string): {
  primaryEconomy: string;
  secondaryEconomy: string;
  suffix: string;
} | null {
  switch (archetypeKey) {
    case 'refinery_industrial':
      return { primaryEconomy: 'Refinery', secondaryEconomy: 'Industrial', suffix: 'Megacomplex' };
    case 'extraction_refinery':
      return { primaryEconomy: 'Extraction', secondaryEconomy: 'Refinery', suffix: 'Mining Hub' };
    case 'agriculture_terraforming':
      return { primaryEconomy: 'Agriculture', secondaryEconomy: 'Terraforming', suffix: 'Colony' };
    case 'hitech_tourism':
      return { primaryEconomy: 'HighTech', secondaryEconomy: 'Tourism', suffix: 'Prestige Colony' };
    case 'military_industrial':
      return { primaryEconomy: 'Military', secondaryEconomy: 'Industrial', suffix: 'Complex' };
    default:
      return null;
  }
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
  onClick, children, primary, disabled = false, active = false, ariaLabel, ariaBusy = false,
}: {
  onClick: () => void;
  children: React.ReactNode;
  primary?: boolean;
  disabled?: boolean;
  active?: boolean;
  ariaLabel?: string;
  ariaBusy?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={ariaLabel}
      aria-busy={ariaBusy || undefined}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={[
        primary ? 'btn-primary' : active ? 'btn-primary' : 'btn-metal',
        'inline-flex items-center text-[11px] py-1.5 px-3',
        disabled ? 'cursor-not-allowed opacity-45' : '',
      ].join(' ')}
    >
      {children}
    </button>
  );
}
