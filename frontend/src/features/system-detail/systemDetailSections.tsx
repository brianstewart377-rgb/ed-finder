import type { ReactNode } from 'react';
import type {
  EvidenceRecord,
  EvidenceSystemFocusArea,
  EvidenceSystemSummaryResponse,
  SystemBody,
  SystemDetail,
  SystemStation,
} from '@/types/api';
import {
  distanceFromSol,
  formatCoords,
  formatEvidenceSourceList,
  formatPopulationForSystem,
  formatTimestamp,
  systemStatusLabel,
} from '@/lib/format';
import { compareBodiesByHierarchy } from '@/lib/bodyHierarchySort';
import { transientStationPlanningReason } from '@/features/colony-planner/existingInfrastructure';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { ExpansionPlanBadge } from '@/features/expansion-plans/ExpansionPlanBadge';

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
      {!loading && system ? (
        <div className="mt-2">
          <ExpansionPlanBadge id64={id64} />
        </div>
      ) : null}
      <h2 id="system-detail-title" className="sr-only">
        {loading ? 'Loading system detail' : system?.name || 'Unknown system'}
      </h2>
    </header>
  );
}

export function SystemInfoGrid({ sys }: { sys: SystemDetail }) {
  const dSol = distanceFromSol(sys, sys.id64);
  const bodyDataUpdatedAt = formatTimestamp(sys.body_data_updated_at);
  const bodyDataSources = formatEvidenceSourceList(sys.body_data_sources);
  const statusUpdatedAt = formatTimestamp(sys.status_updated_at);
  const statusSource = formatEvidenceSourceList(
    sys.status_source ? [sys.status_source] : [],
  );
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
    bodyDataUpdatedAt
      ? {
          label: 'Body data freshness',
          value: (
            <span className="text-silver">
              Updated {bodyDataUpdatedAt}
              {bodyDataSources ? <span className="text-text-dim text-[10px] ml-2">({bodyDataSources})</span> : null}
            </span>
          ),
        }
      : null,
    statusUpdatedAt
      ? {
          label: 'Colonisation state',
          value: (
            <span className="text-silver">
              Updated {statusUpdatedAt}
              {statusSource ? <span className="text-text-dim text-[10px] ml-2">({statusSource})</span> : null}
            </span>
          ),
        }
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

export function SystemEvidenceSection({
  summary,
  loading,
  error,
  onRetry,
}: {
  summary: EvidenceSystemSummaryResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <Section title="Evidence">
        <div className="premium-subpanel px-4 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <SemanticStatusBadge label="Loading" tone="loading" />
            <span className="text-sm text-silver">Loading evidence posture for this system.</span>
          </div>
        </div>
      </Section>
    );
  }

  if (error) {
    return (
      <Section title="Evidence">
        <div className="rounded-chunk-lg border border-red/50 bg-[linear-gradient(180deg,rgba(248,113,113,0.12),rgba(127,29,29,0.16))] p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <SemanticStatusBadge label="Unavailable" tone="unavailable" />
            <span className="font-semibold text-red">Evidence detail is unavailable right now.</span>
          </div>
          <p className="mt-2 text-silver">
            Canonical system detail is still available, but the trust-layer explanation could not be loaded.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="btn-metal mt-3 text-xs font-mono font-bold"
          >
            Retry
          </button>
        </div>
      </Section>
    );
  }

  if (!summary) return null;

  const activeRecords = summary.records ?? [];
  const focusAreas = summary.focus_areas ?? [];
  const posture = evidenceSurfacePosture(summary);

  return (
    <Section title="Evidence">
      <div data-testid="system-detail-evidence-section" className="space-y-3">
        <div className="rounded-chunk-lg border border-border bg-bg3/45 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              <SemanticStatusBadge label={posture.label} tone={posture.tone} />
              <p className="max-w-3xl text-sm leading-relaxed text-silver">
                {posture.summary}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px] font-mono">
              <CountChip label="Observed facts" value={summary.observed_fact_count} />
              <CountChip label="Active records" value={summary.imported_record_count} />
              <CountChip label="Derived features" value={summary.derived_feature_count} />
              <CountChip label="Open proposals" value={summary.open_rule_proposal_count} />
            </div>
          </div>
        </div>

        {focusAreas.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {focusAreas.map((focusArea) => (
              <FocusAreaCard key={focusArea.key} focusArea={focusArea} />
            ))}
          </div>
        ) : null}

        {activeRecords.length > 0 ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {activeRecords.map((record) => {
              const observedAt = formatTimestamp(record.observed_at ?? record.collected_at ?? null);
              const expiresAt = formatTimestamp(record.expires_at);
              const sourceLabel = formatEvidenceSourceList([record.source_name]) ?? record.source_name;
              return (
                <article
                  key={record.evidence_key}
                  data-testid={`system-evidence-record-${record.evidence_key}`}
                  className="rounded-chunk-lg border border-border bg-bg3/40 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                        {humanizeEvidenceLabel(record.evidence_type)}
                      </p>
                      <p className="mt-1 text-sm font-semibold text-text">
                        {record.summary?.trim() || 'Active evidence record linked for this system.'}
                      </p>
                    </div>
                    <SemanticStatusBadge
                      label={recordLifecycleLabel(record)}
                      tone={recordLifecycleTone(record)}
                    />
                  </div>
                  <dl className="mt-3 grid gap-x-4 gap-y-2 text-[11px] sm:grid-cols-2">
                    <EvidenceMetaRow label="Source" value={sourceLabel} />
                    <EvidenceMetaRow label="Subject" value={recordSubjectLabel(record)} />
                    <EvidenceMetaRow label="Observed" value={observedAt ?? 'Unknown'} />
                    <EvidenceMetaRow label="Confidence" value={humanizeEvidenceLabel(record.confidence)} />
                    <EvidenceMetaRow label="Origin" value={humanizeEvidenceLabel(record.origin)} />
                    {expiresAt ? <EvidenceMetaRow label="Expires" value={expiresAt} /> : null}
                  </dl>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4 text-sm text-silver">
            No active evidence records are linked yet. Canonical system detail remains the answer surface while evidence promotion catches up.
          </div>
        )}

        {summary.derived_features.length > 0 ? (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Derived features
            </p>
            <ul className="mt-3 space-y-2 text-sm text-silver">
              {summary.derived_features.map((feature) => (
                <li key={feature.feature_key}>
                  <span className="font-semibold text-text">{humanizeEvidenceLabel(feature.feature_name)}:</span>{' '}
                  {feature.summary?.trim() || 'Derived evidence feature available for review.'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {summary.open_rule_proposals.length > 0 ? (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Open evidence proposals
            </p>
            <ul className="mt-3 space-y-2 text-sm text-silver">
              {summary.open_rule_proposals.map((proposal) => (
                <li key={proposal.proposal_key}>
                  <span className="font-semibold text-text">{humanizeEvidenceLabel(proposal.proposal_type)}:</span>{' '}
                  {proposal.summary}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
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

function CountChip({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded-full border border-border bg-bg4 px-2.5 py-1 text-silver">
      {label}: <span className="text-text">{value}</span>
    </span>
  );
}

function FocusAreaCard({ focusArea }: { focusArea: EvidenceSystemFocusArea }) {
  const badge = focusAreaBadge(focusArea.posture);
  return (
    <article
      data-testid={`system-evidence-focus-${focusArea.key}`}
      className="rounded-chunk-lg border border-border bg-bg3/40 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
            {focusArea.label}
          </p>
          {focusArea.evidence_type ? (
            <p className="mt-1 text-[11px] text-text-dim">
              {humanizeEvidenceLabel(focusArea.evidence_type)}
            </p>
          ) : null}
        </div>
        <SemanticStatusBadge label={badge.label} tone={badge.tone} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-silver">
        {focusArea.summary}
      </p>
    </article>
  );
}

function EvidenceMetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/40 pb-1">
      <dt className="font-mono uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className="text-right font-mono text-text">{value}</dd>
    </div>
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

function evidenceSurfacePosture(
  summary: EvidenceSystemSummaryResponse,
): { label: string; tone: SemanticStatusTone; summary: string } {
  if (summary.imported_record_count > 0) {
    return {
      label: 'Active evidence linked',
      tone: 'available',
      summary: 'These active evidence records explain the current trust posture for this system without changing canonical detail directly.',
    };
  }
  if ((summary.focus_areas ?? []).some((focusArea) => focusArea.posture === 'canonical_present')) {
    return {
      label: 'Canonical data linked',
      tone: 'canonical',
      summary: 'Important system facts are already present in canonical app data here, even where lifecycle-managed evidence promotion has not caught up yet.',
    };
  }
  if (summary.observed_fact_count > 0) {
    return {
      label: 'Observation log only',
      tone: 'observed',
      summary: 'Raw observations exist for this system, but no active lifecycle-managed evidence record is linked yet.',
    };
  }
  return {
    label: 'No evidence linked',
    tone: 'unknown',
    summary: 'No observed, promoted, or canonical fallback evidence is currently linked for this system.',
  };
}

function focusAreaBadge(posture: string): { label: string; tone: SemanticStatusTone } {
  if (posture === 'evidence_linked') {
    return { label: 'Evidence linked', tone: 'available' };
  }
  if (posture === 'canonical_present') {
    return { label: 'Canonical present', tone: 'canonical' };
  }
  if (posture === 'observed_only') {
    return { label: 'Observed only', tone: 'observed' };
  }
  return { label: 'Missing', tone: 'unknown' };
}

function recordLifecycleTone(record: EvidenceRecord): SemanticStatusTone {
  if (record.record_status === 'quarantined') return 'needs_review';
  if (record.record_status === 'rejected') return 'blocked';
  if (record.record_status !== 'active') return 'caution';
  if (record.freshness_status === 'stale' || record.freshness_status === 'expired') return 'stale';
  if (record.freshness_status === 'unknown') return 'unknown';
  return 'available';
}

function recordLifecycleLabel(record: EvidenceRecord): string {
  return `${humanizeEvidenceLabel(record.record_status)} / ${humanizeEvidenceLabel(record.freshness_status)}`;
}

function recordSubjectLabel(record: EvidenceRecord): string {
  const subjectType = humanizeEvidenceLabel(record.subject_type);
  if (!record.subject_id) return subjectType;
  return `${subjectType} ${record.subject_id}`;
}

function humanizeEvidenceLabel(value?: string | null): string {
  const source = value?.trim();
  if (!source) return 'Unknown';
  return source
    .split('_')
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}

const tableWrapperStyle = {
  background: 'linear-gradient(180deg, rgba(20,22,26,0.85), rgba(14,16,20,0.85))',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px -16px rgba(0,0,0,0.6)',
} as const;

const tableHeadStyle = {
  background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
  borderBottom: '1px solid hsl(216 10% 24%)',
} as const;
