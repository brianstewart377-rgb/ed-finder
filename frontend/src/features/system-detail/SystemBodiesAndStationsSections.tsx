import type { ReactNode } from 'react';
import type { SystemBody, SystemStation } from '@/types/api';
import { compareBodiesByHierarchy } from '@/lib/bodyHierarchySort';
import { transientStationPlanningReason } from '@/features/colony-planner/existingInfrastructure';
import { Section } from './SystemDetailSectionShell';
import { BodyThumbnail } from './body-thumbnail/BodyThumbnail';

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
              <th className="px-3 py-2.5 w-9" aria-hidden></th>
              <th className="px-3 py-2.5 text-left">Name</th>
              <th className="px-3 py-2.5 text-left">Type</th>
              <th className="px-3 py-2.5 text-left">Tags</th>
              <th className="px-3 py-2.5 text-right">Dist (ls)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((body) => (
              <tr key={body.id} className="border-t border-border/50 hover:bg-orange/5 transition-colors">
                <td className="px-3 py-1.5 align-middle"><BodyThumbnail body={body} /></td>
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
