import { useEffect } from 'react';
import type { SystemDetail, SystemBody, SystemStation } from '@/types/api';
import { ratingTier, formatPopulation } from '@/lib/format';
import { useSystemDetail } from './useSystemDetail';

export interface SystemDetailModalProps {
  id64:    number;
  onClose: () => void;
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
export function SystemDetailModal({ id64, onClose, renderActions }: SystemDetailModalProps) {
  const { data, loading, error, refetch } = useSystemDetail(id64);

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
    };
  }, [onClose]);

  return (
    <div
      data-testid="system-detail-modal"
      className="fixed inset-0 z-30 flex items-start justify-center bg-bg1/80 backdrop-blur-sm overflow-y-auto px-4 py-8 sm:py-12"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="system-detail-title"
    >
      <article
        className="relative w-full max-w-4xl rounded-md border border-border bg-bg2 shadow-2xl"
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
              <SystemInfoGrid sys={data} />
              <ScoreBars sys={data} />
              <BodiesSection bodies={data.bodies} />
              <StationsSection stations={data.stations} />
              <ExplorationValue value={data.exploration_value} />
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

// ─── Header ────────────────────────────────────────────────────────────────

function ModalHeader({
  name, id64, loading, onClose,
}: { name?: string; id64: number; loading: boolean; onClose: () => void }) {
  return (
    <header className="sticky top-0 z-10 flex items-start gap-3 px-5 sm:px-6 py-4 border-b border-border bg-bg2/95 backdrop-blur rounded-t-md">
      <div className="min-w-0 flex-1">
        <h2
          id="system-detail-title"
          className="font-mono text-orange tracking-wider text-lg truncate"
        >
          {loading ? 'Loading…' : name || 'Unknown system'}
        </h2>
        <div className="font-mono text-[11px] text-text-dim mt-0.5">
          ID64: <span className="tabular-nums">{id64}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onClose}
        data-testid="system-detail-close"
        aria-label="Close"
        className="shrink-0 px-2 py-1 rounded text-text-dim hover:text-orange hover:bg-bg3 text-lg"
      >
        ✕
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
    sys.rationale ? { label: 'Rating rationale', value: <span className="italic text-text-dim">{sys.rationale}</span> } : null,
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

function ScoreBars({ sys }: { sys: SystemDetail }) {
  const items: Array<[string, number | null | undefined]> = [
    ['Overall',     sys.score],
    ['Agriculture', sys.score_agriculture],
    ['Refinery',    sys.score_refinery],
    ['Industrial',  sys.score_industrial],
    ['High Tech',   sys.score_hightech],
    ['Military',    sys.score_military],
    ['Tourism',     sys.score_tourism],
    ['Extraction',  sys.score_extraction],
  ];
  const visible = items.filter(([, v]) => v != null);

  if (visible.length === 0) return null;

  return (
    <Section title="Suitability scores">
      <div className="space-y-1.5">
        {visible.map(([label, score]) => {
          const pct  = Math.max(0, Math.min(100, score ?? 0));
          const tier = ratingTier(score ?? null);
          return (
            <div key={label} className="grid grid-cols-[110px_1fr_40px] items-center gap-3 text-xs font-mono">
              <span className="text-text-dim">{label}</span>
              <span className="block h-2 bg-bg4 rounded overflow-hidden">
                <span
                  className="block h-full transition-[width]"
                  style={{ width: `${pct}%`, backgroundColor: tier.fillColor }}
                />
              </span>
              <span className="text-right tabular-nums" style={{ color: tier.fillColor }}>{pct}</span>
            </div>
          );
        })}
      </div>
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
      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs font-mono">
          <thead className="bg-bg3/60 text-text-dim uppercase tracking-wider text-[10px]">
            <tr>
              <th className="px-2 py-1 text-left">Name</th>
              <th className="px-2 py-1 text-left">Type</th>
              <th className="px-2 py-1 text-left">Tags</th>
              <th className="px-2 py-1 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((b) => (
              <tr key={b.id} className="border-t border-border/60 hover:bg-bg3/30">
                <td className="px-2 py-1 text-orange">{b.name}</td>
                <td className="px-2 py-1 text-text-dim">{b.subtype || b.body_type || '—'}</td>
                <td className="px-2 py-1 text-text-dim text-[10px]">
                  <BodyTags body={b} />
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-text-dim">
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
      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-xs font-mono">
          <thead className="bg-bg3/60 text-text-dim uppercase tracking-wider text-[10px]">
            <tr>
              <th className="px-2 py-1 text-left">Name</th>
              <th className="px-2 py-1 text-left">Type</th>
              <th className="px-2 py-1 text-left">Pad</th>
              <th className="px-2 py-1 text-left">Services</th>
              <th className="px-2 py-1 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {stations.map((s) => (
              <tr key={s.id} className="border-t border-border/60 hover:bg-bg3/30">
                <td className="px-2 py-1 text-orange">{s.name}</td>
                <td className="px-2 py-1 text-text-dim">{s.station_type || '—'}</td>
                <td className="px-2 py-1">
                  <span className={[
                    'px-1.5 py-0.5 rounded text-[10px] border',
                    s.landing_pad_size === 'L' ? 'border-green/50 text-green'
                      : s.landing_pad_size === 'M' ? 'border-gold/50 text-gold'
                      : s.landing_pad_size === 'S' ? 'border-text-dim text-text-dim'
                      : 'border-border text-text-dim',
                  ].join(' ')}>
                    {s.landing_pad_size || '?'}
                  </span>
                </td>
                <td className="px-2 py-1 text-text-dim text-[10px] space-x-1">
                  {s.has_market     && <span className="px-1 rounded bg-bg4 border border-border">Market</span>}
                  {s.has_shipyard   && <span className="px-1 rounded bg-bg4 border border-border">Shipyard</span>}
                  {s.has_outfitting && <span className="px-1 rounded bg-bg4 border border-border">Outfitting</span>}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-text-dim">
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
    <section>
      <h3 className="font-mono text-orange uppercase tracking-wider text-[11px] mb-2 border-b border-border/50 pb-1">
        {title}
      </h3>
      {children}
    </section>
  );
}
