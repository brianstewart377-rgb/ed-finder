import type { ReactNode } from 'react';
import type { SystemBody, SystemDetail, SystemStation } from '@/types/api';
import { distanceFromSol, formatCoords, formatPopulationForSystem, systemStatusLabel } from '@/lib/format';
import { compareBodiesByHierarchy } from '@/lib/bodyHierarchySort';
import { transientStationPlanningReason } from '@/features/colony-planner/existingInfrastructure';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';

export function ModalHeader({
  system,
  id64,
  loading,
  hasError,
}: {
  system?: SystemDetail | null;
  id64: number;
  loading: boolean;
  hasError: boolean;
}) {
  const statusLabel = loading
    ? 'Loading'
    : hasError
      ? 'Unavailable'
      : system
        ? systemStatusLabel(system)
        : 'Unknown';
  const statusTone = loading
    ? 'loading'
    : hasError
      ? 'unavailable'
      : statusLabel === 'Colonised'
        ? 'canonical'
        : statusLabel === 'Colonising'
          ? 'caution'
          : 'available';

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg2/90 px-5 py-4 pr-16 backdrop-blur-md rounded-t-chunk-lg sm:px-7 sm:pr-20">
      <WorkspaceContextHeader
        journeyLabel="Journey stage: Inspect"
        title="System Detail"
        headingLevel={2}
        supportingText="Review the selected system, understand its current context, and move into planning when you are ready."
        selectedSystemName={loading ? 'Loading system...' : system?.name || 'Unknown system'}
        selectedSystemMeta={<span className="tabular-nums">ID64 {id64}</span>}
        status={<SemanticStatusBadge label={statusLabel} tone={statusTone} />}
        testId="system-detail-context-header"
      />
      <h2 id="system-detail-title" className="sr-only">
        {loading ? 'Loading system detail' : system?.name || 'Unknown system'}
      </h2>
    </header>
  );
}

export function SystemInfoGrid({ sys }: { sys: SystemDetail }) {
  const dSol = distanceFromSol(sys, sys.id64);
  const fields: Array<{ label: string; value: ReactNode } | null> = [
    {
      label: 'Coordinates',
      value: (
        <span className="tabular-nums text-cyan">
          {formatCoords(sys, sys.id64)}
          {dSol != null && (
            <span className="text-text-dim text-[10px] ml-2">
              ({dSol.toFixed(1)} LY from Sol)
            </span>
          )}
        </span>
      ),
    },
    sys.primary_economy
      ? { label: 'Primary economy', value: <span className="text-gold">{sys.primary_economy}</span> }
      : null,
    sys.secondary_economy
      ? { label: 'Secondary economy', value: sys.secondary_economy }
      : null,
    {
      label: 'Population',
      value: formatPopulationForSystem(sys),
    },
    sys.security ? { label: 'Security', value: sys.security } : null,
    sys.allegiance ? { label: 'Allegiance', value: sys.allegiance } : null,
    sys.government ? { label: 'Government', value: sys.government } : null,
    sys.main_star_subtype || sys.main_star_type
      ? { label: 'Main star', value: <span className="text-cyan">{sys.main_star_subtype || sys.main_star_type}</span> }
      : null,
  ];

  const visible = fields.filter(
    (field): field is { label: string; value: ReactNode } => field !== null,
  );

  return (
    <Section title="System info">
      <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
        {visible.map((field) => (
          <div key={field.label} className="flex justify-between gap-3 border-b border-border/50 pb-1">
            <dt className="text-text-dim font-mono uppercase tracking-wider text-[10px]">{field.label}</dt>
            <dd className="text-right text-text font-mono">{field.value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

export function BodiesSection({ bodies, systemName }: { bodies?: SystemBody[]; systemName?: string | null }) {
  if (!bodies || bodies.length === 0) return null;

  const sorted = [...bodies].sort((a, b) => {
    const rank = (value: SystemBody) => (
      value.body_type === 'Star' ? 0
        : value.body_type === 'Planet' ? 1
          : 2
    );
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    return compareBodiesByHierarchy(a, b, systemName);
  });

  return (
    <Section title={`Bodies (${bodies.length})`}>
      <DataTable>
        <table className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={tableHeadStyle}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Tags</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((body) => (
              <tr key={body.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{body.name}</td>
                <td className="px-3 py-2 text-silver">{body.subtype || body.body_type || '—'}</td>
                <td className="px-3 py-2 text-silver-dk text-[10px]">
                  <BodyTags body={body} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {body.distance_from_star != null ? body.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  );
}

export function StationsSection({ stations }: { stations?: SystemStation[] }) {
  if (!stations || stations.length === 0) return null;

  return (
    <Section title={`Stations (${stations.length})`}>
      <DataTable>
        <table data-testid="system-detail-stations-table" className="w-full text-xs font-mono">
          <thead className="text-silver-dk uppercase tracking-[0.16em] text-[10px]" style={tableHeadStyle}>
            <tr>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Body</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Lane</th>
              <th className="px-3 py-2.5 text-left">Status</th>
              <th className="px-3 py-2.5 text-left">Pad</th>
              <th className="px-3 py-2.5 text-left">Services</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {stations.map((station) => (
              <tr key={station.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-2 text-orange-lt font-semibold">{station.name}</td>
                <td className="px-3 py-2 text-silver">{stationBodyLabel(station)}</td>
                <td className="px-3 py-2 text-silver">{station.station_type || '—'}</td>
                <td className="px-3 py-2">
                  <StationLaneBadge station={station} />
                </td>
                <td className="px-3 py-2">
                  <StationAssociationBadge station={station} />
                </td>
                <td className="px-3 py-2">
                  <span className={[
                    'inline-grid place-items-center min-w-[26px] h-6 rounded-md text-[10px] font-bold border',
                    station.landing_pad_size === 'L' ? 'border-green/50 text-green bg-green/10'
                      : station.landing_pad_size === 'M' ? 'border-gold/50 text-gold bg-gold/10'
                        : station.landing_pad_size === 'S' ? 'border-silver-dk/50 text-silver bg-bg4'
                          : 'border-border text-silver-dk',
                  ].join(' ')}>
                    {station.landing_pad_size || '?'}
                  </span>
                </td>
                <td className="px-3 py-2 text-silver-dk text-[10px] space-x-1">
                  {station.has_market && <span className="chip">Market</span>}
                  {station.has_shipyard && <span className="chip">Shipyard</span>}
                  {station.has_outfitting && <span className="chip">Outfitting</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-silver">
                  {station.distance_from_star != null ? station.distance_from_star.toFixed(0) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  );
}

export function ExplorationValue({ value }: { value?: SystemDetail['exploration_value'] }) {
  if (!value || value.combined_value <= 0) return null;

  return (
    <Section title="Estimated exploration value">
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <ValueCell label="Scan" value={value.total_scan_value} />
        <ValueCell label="Mapping" value={value.total_mapping_value} />
        <ValueCell label="Combined" value={value.combined_value} highlight />
      </div>
    </Section>
  );
}

export function ExternalLinks({ sys }: { sys: SystemDetail }) {
  const links: Array<[string, string]> = [
    ['Spansh', `https://spansh.co.uk/system/${sys.id64}`],
    ['Inara', `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(sys.name || '')}`],
    ['EDSM', `https://www.edsm.net/en/system/id/${sys.id64}/name/${encodeURIComponent(sys.name || '')}`],
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

export function Section({ title, children }: { title: string; children: ReactNode }) {
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

function BodyTags({ body }: { body: SystemBody }) {
  const tags: string[] = [];
  if (body.is_earth_like) tags.push('🌍 ELW');
  if (body.is_water_world) tags.push('🌊 WW');
  if (body.is_ammonia_world) tags.push('🟣 AW');
  if (body.is_landable) tags.push('⬇ Land');
  if (body.is_terraformable) tags.push('♻ Terr');
  if ((body.bio_signal_count ?? 0) > 0) tags.push(`🧬 ×${body.bio_signal_count}`);
  if ((body.geo_signal_count ?? 0) > 0) tags.push(`🌋 ×${body.geo_signal_count}`);
  if (body.spectral_class) tags.push(`${body.spectral_class}${body.is_scoopable ? ' ⛽' : ''}`);
  if (tags.length === 0) return <span className="text-text-dim">—</span>;
  return <>{tags.join(' · ')}</>;
}

function StationLaneBadge({ station }: { station: SystemStation }) {
  const transientReason = transientStationPlanningReason(station as SystemStation & Record<string, unknown>);
  const label = transientReason
    ? 'Transient / non-slot'
    : station.lane === 'orbital'
      ? 'Orbital'
      : station.lane === 'surface'
        ? 'Surface'
        : 'Unknown';
  const tone = transientReason
    ? 'border-cyan/35 bg-cyan/10 text-cyan'
    : station.lane === 'orbital' || station.lane === 'surface'
      ? 'border-green/35 bg-green/10 text-green'
      : 'border-gold/35 bg-gold/10 text-gold';

  return (
    <span
      title={transientReason ?? `Lane: ${label}`}
      className={['inline-flex rounded border px-2 py-1 text-[10px]', tone].join(' ')}
    >
      {label}
    </span>
  );
}

function StationAssociationBadge({ station }: { station: SystemStation }) {
  const transientReason = transientStationPlanningReason(station as SystemStation & Record<string, unknown>);
  if (transientReason) {
    return (
      <span
        title={transientReason}
        className="inline-flex rounded border border-cyan/35 bg-cyan/10 px-2 py-1 text-[10px] text-cyan"
      >
        Fleet Carrier / transient / ignored for colony planning
      </span>
    );
  }

  const status = formatAssociationStatus(station.association_status);
  const confidence = formatAssociationConfidence(station.association_confidence);
  const source = formatAssociationSource(station.association_source);
  const label = [status, confidence, source].filter(Boolean).join(' / ') || 'Unknown';
  const tone = station.association_status === 'confirmed'
    ? 'border-green/35 bg-green/10 text-green'
    : station.association_status === 'inferred'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border text-silver-dk bg-bg4';

  return (
    <span
      title={station.resolver_notes ?? label}
      className={['inline-flex rounded border px-2 py-1 text-[10px]', tone].join(' ')}
    >
      {label}
    </span>
  );
}

function DataTable({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-chunk-lg border border-border" style={tableWrapperStyle}>
      {children}
    </div>
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

function stationBodyLabel(station: SystemStation): string {
  return station.body_name || station.station_body_name || (station.body_id != null ? `Body ${station.body_id}` : '—');
}

function formatAssociationStatus(value?: string | null): string | null {
  if (value === 'confirmed') return 'Confirmed';
  if (value === 'inferred') return 'Inferred';
  if (value === 'unresolved') return 'Unresolved';
  return null;
}

function formatAssociationConfidence(value?: string | null): string | null {
  if (value === 'exact') return 'exact';
  if (value === 'strong_inference') return 'strong inference';
  if (value === 'weak_inference') return 'weak inference';
  if (value === 'unresolved') return 'unresolved';
  return null;
}

function formatAssociationSource(value?: string | null): string | null {
  const source = value?.trim();
  if (!source) return null;
  if (source.toLowerCase().startsWith('edsm')) return 'EDSM';
  if (source === 'transient_non_slot') return 'transient';
  return source.replace(/_/g, ' ');
}

const tableWrapperStyle = {
  background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
} as const;

const tableHeadStyle = {
  background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
  borderBottom: '1px solid hsl(216 10% 24%)',
} as const;
