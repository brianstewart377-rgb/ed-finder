import { useEffect, useRef, useState } from 'react';
import { Rocket, X } from 'lucide-react';
import type { RecommendedBuildPlan, SystemDetail, SystemBody, SystemStation } from '@/types/api';
import { formatPopulation } from '@/lib/format';
import { displayRationale } from '@/lib/rationale';
import { useSystemDetail } from './useSystemDetail';
import { RatingRadar } from './RatingRadar';
import { BuildabilityPanel } from './BuildabilityPanel';
import { SlotPredictionPanel } from './SlotPredictionPanel';
import { RecommendedBuildsPanel } from './RecommendedBuildsPanel';
import { SimulationPreviewPanel } from './SimulationPreviewPanel';
import { RegionalPositionPanel } from './RegionalPositionPanel';

export interface SystemDetailModalProps {
  id64:    number;
  onClose: () => void;
  focusIntent?: 'colony-planner' | null;
  /** Renders alongside Spansh / Inara / EDSM so callers can wire up
   *  Watchlist / Pin / Compare / Show-on-map without this component knowing
   *  about those features. Receives the loaded SystemDetail or null while
   *  the fetch is in flight. */
  renderActions?: (sys: SystemDetail | null) => React.ReactNode;
}

/**
 * Full system-detail modal. Renders on top of the current tab via a
 * fixed-position overlay; closes on:
 *   • Escape key
 *   • click on the dim backdrop (not the content)
 *   • the X button in the header
 *
 * Body scroll is locked while the modal is open so the page underneath
 * doesn't scroll when you wheel the modal content.
 */
export function SystemDetailModal({ id64, onClose, focusIntent = null, renderActions }: SystemDetailModalProps) {
  const { data, loading, error, refetch } = useSystemDetail(id64);
  const [selectedBuild, setSelectedBuild] = useState<RecommendedBuildPlan | null>(null);
  const colonyPlannerRef = useRef<HTMLDivElement | null>(null);
  const highlightTimeoutRef = useRef<number | null>(null);
  const [highlightPlanner, setHighlightPlanner] = useState(false);

  // Esc closes the modal. Body scroll lock only fires if we're actually
  // mounted (id64 changes between mounts so this is per-open).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (highlightTimeoutRef.current !== null) {
        window.clearTimeout(highlightTimeoutRef.current);
        highlightTimeoutRef.current = null;
      }
    };
  }, [onClose]);

  useEffect(() => {
    setSelectedBuild(null);
  }, [id64]);

  const focusColonyPlanner = () => {
    const node = colonyPlannerRef.current;
    if (!node) return;
    node.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    node.focus({ preventScroll: true });
    setHighlightPlanner(true);
    if (highlightTimeoutRef.current !== null) {
      window.clearTimeout(highlightTimeoutRef.current);
    }
    highlightTimeoutRef.current = window.setTimeout(() => {
      setHighlightPlanner(false);
      highlightTimeoutRef.current = null;
    }, 1800);
  };

  useEffect(() => {
    if (!data || focusIntent !== 'colony-planner') return;
    const handle = window.setTimeout(focusColonyPlanner, 0);
    return () => window.clearTimeout(handle);
  }, [data, focusIntent]);

  return (
    <div
      data-testid="system-detail-modal"
      className="fixed inset-0 z-40 flex items-start justify-center bg-bg1/85 backdrop-blur-md overflow-y-auto px-4 py-8 sm:py-12"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="system-detail-title"
    >
      <article
        className="panel relative w-full max-w-6xl animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <ModalHeader
          name={data?.name}
          id64={id64}
          loading={loading}
          onClose={onClose}
        />

        <div className="px-5 sm:px-6 py-5 space-y-5 text-sm">
          {loading && (
            <div className="text-text-dim font-mono text-sm py-12 text-center">
              Loading system data…
            </div>
          )}

          {error && (
            <div className="rounded border border-red/50 bg-red/10 p-3 font-mono text-xs text-red flex flex-wrap items-center gap-3">
              <span className="font-bold">Failed to load:</span>
              <span>{error}</span>
              <button
                type="button"
                onClick={refetch}
                className="ml-auto px-2 py-1 rounded bg-bg4 border border-border text-text-dim hover:text-orange"
              >
                ↺ Retry
              </button>
            </div>
          )}

          {data && (
            <>
              <ColonyPlannerEntryPoint onOpen={focusColonyPlanner} />
              <Section title="Rating profile">
                <RatingRadar sys={data} />
              </Section>
              <SystemInfoGrid sys={data} />
              <BodiesSection bodies={data.bodies} />
              <StationsSection stations={data.stations} />
              <ExplorationValue value={data.exploration_value} />

              {/* Colony Build Analysis — simulation engine panels */}
              <Section title="Colony Planning">
                <BuildabilityPanel id64={id64} />
                <div className="mt-4">
                  <RegionalPositionPanel id64={id64} />
                </div>
                <div className="mt-4">
                  <RecommendedBuildsPanel system={data} onPreviewBuild={setSelectedBuild} />
                </div>
                <div className="mt-4">
                  <div
                    ref={colonyPlannerRef}
                    tabIndex={-1}
                    data-testid="colony-planner-focus-target"
                    className={[
                      'rounded-chunk-lg outline-none transition-[box-shadow,border-color] duration-300',
                      highlightPlanner ? 'ring-2 ring-orange/70 shadow-brand-glow' : '',
                    ].join(' ')}
                  >
                    <SimulationPreviewPanel system={data} selectedPlan={selectedBuild} />
                  </div>
                </div>
                <div className="mt-4">
                  <SlotPredictionPanel id64={id64} />
                </div>
              </Section>

              <ExternalLinks sys={data} />
            </>
          )}

          <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
            {renderActions?.(data)}
          </div>
        </div>
      </article>
    </div>
  );
}

function ColonyPlannerEntryPoint({ onOpen }: { onOpen: () => void }) {
  return (
    <section className="rounded-chunk-lg border border-orange/35 bg-orange/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-3xl">
          <h3 className="font-mono text-[12px] uppercase tracking-[0.18em] text-orange">
            Colony Planner
          </h3>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            Build a plan for this system, start from Suggested Builds if you are unsure, then run Preview when you are ready to evaluate it.
          </p>
        </div>
        <button
          type="button"
          onClick={onOpen}
          data-testid="open-colony-planner"
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25"
        >
          <Rocket size={14} />
          Open Colony Planner
        </button>
      </div>
    </section>
  );
}

// ─── Header ────────────────────────────────────────────────────────────────

function ModalHeader({
  name, id64, loading, onClose,
}: { name?: string; id64: number; loading: boolean; onClose: () => void }) {
  return (
    <header className="sticky top-0 z-10 flex items-start gap-3 px-5 sm:px-7 py-4 border-b border-border bg-bg2/85 backdrop-blur-md rounded-t-chunk-lg">
      <div className="min-w-0 flex-1">
        <h2
          id="system-detail-title"
          className="font-mono text-orange tracking-[0.14em] text-xl font-bold truncate"
        >
          {loading ? 'Loading…' : name || 'Unknown system'}
        </h2>
        <div className="font-mono text-[10px] tracking-[0.2em] text-silver-dk mt-1 uppercase">
          ID64 · <span className="tabular-nums text-silver">{id64}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onClose}
        data-testid="system-detail-close"
        aria-label="Close"
        className="shrink-0 grid place-items-center w-9 h-9 rounded-full text-silver-dk hover:text-orange-lt hover:bg-orange/10 border border-border hover:border-orange/45 transition-colors"
      >
        <X size={16} />
      </button>
    </header>
  );
}

// ─── Sections ──────────────────────────────────────────────────────────────

function SystemInfoGrid({ sys }: { sys: SystemDetail }) {
  const dSol = Math.hypot(sys.x ?? 0, sys.y ?? 0, sys.z ?? 0);
  const fields: Array<{ label: string; value: React.ReactNode } | null> = [
    {
      label: 'Coordinates',
      value: (
        <span className="tabular-nums text-cyan">
          {sys.x?.toFixed(2)}, {sys.y?.toFixed(2)}, {sys.z?.toFixed(2)}
          <span className="text-text-dim text-[10px] ml-2">
            ({dSol.toFixed(1)} LY from Sol)
          </span>
        </span>
      ),
    },
    sys.primary_economy
      ? { label: 'Primary economy', value: <span className="text-gold">{sys.primary_economy}</span> }
      : null,
    sys.secondary_economy
      ? { label: 'Secondary economy', value: sys.secondary_economy }
      : null,
    sys.economy_suggestion
      ? { label: 'Suggested economy', value: <span className="text-orange">{sys.economy_suggestion}</span> }
      : null,
    {
      label: 'Population',
      value: sys.population && sys.population > 0
        ? formatPopulation(sys.population)
        : <span className="text-green">Uncolonised</span>,
    },
    sys.security    ? { label: 'Security',    value: sys.security } : null,
    sys.allegiance  ? { label: 'Allegiance',  value: sys.allegiance } : null,
    sys.government  ? { label: 'Government',  value: sys.government } : null,
    sys.main_star_subtype || sys.main_star_type
      ? { label: 'Main star', value: <span className="text-cyan">{sys.main_star_subtype || sys.main_star_type}</span> }
      : null,
    displayRationale(sys.rationale) ? { label: 'Rating rationale', value: <span className="italic text-text-dim">{displayRationale(sys.rationale)}</span> } : null,
  ];

  const visible = fields.filter(
    (f): f is { label: string; value: React.ReactNode } => f !== null,
  );

  return (
    <Section title="System info">
      <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
        {visible.map((f) => (
          <div key={f.label} className="flex justify-between gap-3 border-b border-border/50 pb-1">
            <dt className="text-text-dim font-mono uppercase tracking-wider text-[10px]">{f.label}</dt>
            <dd className="text-right text-text font-mono">{f.value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

function BodiesSection({ bodies }: { bodies?: SystemBody[] }) {
  if (!bodies || bodies.length === 0) return null;

  // Stars first, then planets/moons by distance from main star.
  const sorted = [...bodies].sort((a, b) => {
    const rank = (v: SystemBody) =>
      v.body_type === 'Star' ? 0 :
      v.body_type === 'Planet' ? 1 : 2;
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    return (a.distance_from_star ?? Infinity) - (b.distance_from_star ?? Infinity);
  });

  return (
    <Section title={`Bodies (${bodies.length})`}>
      <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}>
        <table className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
            borderBottom: '1px solid hsl(216 10% 24%)',
          }}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Tags</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((b) => (
              <tr key={b.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{b.name}</td>
                <td className="px-3 py-2 text-silver">{b.subtype || b.body_type || '—'}</td>
                <td className="px-3 py-2 text-silver-dk text-[10px]">
                  <BodyTags body={b} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {b.distance_from_star != null ? b.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function BodyTags({ body }: { body: SystemBody }) {
  const tags: string[] = [];
  if (body.is_earth_like)         tags.push('🌍 ELW');
  if (body.is_water_world)        tags.push('🌊 WW');
  if (body.is_ammonia_world)      tags.push('🟣 AW');
  if (body.is_landable)           tags.push('⬇ Land');
  if (body.is_terraformable)      tags.push('♻ Terr');
  if ((body.bio_signal_count ?? 0) > 0) tags.push(`🧬 ×${body.bio_signal_count}`);
  if ((body.geo_signal_count ?? 0) > 0) tags.push(`🌋 ×${body.geo_signal_count}`);
  if (body.spectral_class)        tags.push(`${body.spectral_class}${body.is_scoopable ? ' ⛽' : ''}`);
  if (tags.length === 0) return <span className="text-text-dim">—</span>;
  return <>{tags.join(' · ')}</>;
}

function StationsSection({ stations }: { stations?: SystemStation[] }) {
  if (!stations || stations.length === 0) return null;
  return (
    <Section title={`Stations (${stations.length})`}>
      <div className="overflow-x-auto rounded-chunk-lg border border-border" style={{
        background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}>
        <table className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
            borderBottom: '1px solid hsl(216 10% 24%)',
          }}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Pad</th>
              <th className="px-3 py-2.5 text-left">Services</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {stations.map((s) => (
              <tr key={s.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{s.name}</td>
                <td className="px-3 py-2 text-silver">{s.station_type || '—'}</td>
                <td className="px-3 py-2">
                  <span className={[
                    'inline-grid place-items-center min-w-[26px] h-6 rounded-md text-[10px] font-bold border',
                    s.landing_pad_size === 'L' ? 'border-green/50 text-green bg-green/10'
                      : s.landing_pad_size === 'M' ? 'border-gold/50 text-gold bg-gold/10'
                      : s.landing_pad_size === 'S' ? 'border-silver-dk/50 text-silver bg-bg4'
                      : 'border-border text-silver-dk',
                  ].join(' ')}>
                    {s.landing_pad_size || '?'}
                  </span>
                </td>
                <td className="px-3 py-2 text-silver-dk text-[10px] space-x-1">
                  {s.has_market     && <span className="chip">Market</span>}
                  {s.has_shipyard   && <span className="chip">Shipyard</span>}
                  {s.has_outfitting && <span className="chip">Outfitting</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {s.distance_from_star != null ? s.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function ExplorationValue({ value }: { value?: SystemDetail['exploration_value'] }) {
  if (!value || value.combined_value <= 0) return null;
  return (
    <Section title="Estimated exploration value">
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <ValueCell label="Scan"     value={value.total_scan_value} />
        <ValueCell label="Mapping"  value={value.total_mapping_value} />
        <ValueCell label="Combined" value={value.combined_value} highlight />
      </div>
    </Section>
  );
}

function ValueCell({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={[
      'rounded border p-2',
      highlight ? 'border-orange/50 bg-orange/10' : 'border-border bg-bg3/40',
    ].join(' ')}>
      <div className="text-text-dim uppercase tracking-wider text-[10px]">{label}</div>
      <div className={['tabular-nums font-bold', highlight ? 'text-orange' : 'text-text'].join(' ')}>
        {value.toLocaleString()} cr
      </div>
    </div>
  );
}

function ExternalLinks({ sys }: { sys: SystemDetail }) {
  const links: Array<[string, string]> = [
    ['Spansh', `https://spansh.co.uk/system/${sys.id64}`],
    ['Inara',  `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(sys.name || '')}`],
    ['EDSM',   `https://www.edsm.net/en/system/id/${sys.id64}/name/${encodeURIComponent(sys.name || '')}`],
  ];
  return (
    <Section title="External">
      <div className="flex flex-wrap gap-2 text-xs font-mono">
        {links.map(([label, href]) => (
          <a
            key={label}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 rounded bg-bg4 border border-border text-text-dim hover:text-orange hover:border-orange-dk"
          >
            {label} ↗
          </a>
        ))}
      </div>
    </Section>
  );
}

// ─── Layout helpers ────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="font-mono text-silver-dk uppercase tracking-[0.22em] text-[10px] flex items-center gap-3">
        <span className="block h-px flex-1 bg-gradient-to-r from-transparent via-border-bright to-transparent" />
        <span className="text-orange">{title}</span>
        <span className="block h-px flex-1 bg-gradient-to-r from-border-bright via-border-bright to-transparent" />
      </h3>
      {children}
    </section>
  );
}
