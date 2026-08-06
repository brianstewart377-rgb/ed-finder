import type { ReactNode } from 'react';
import type { SystemDetail } from '@/types/api';
import {
  distanceFromSol,
  formatCoords,
  formatEvidenceSourceList,
  formatPopulationForSystem,
  formatTimestamp,
  systemStatusLabel,
} from '@/lib/format';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import { ExpansionPlanBadge } from '@/features/expansion-plans/ExpansionPlanBadge';
import { Section } from './SystemDetailSectionShell';

export { Section };
export { SystemEvidenceSection } from './SystemEvidenceSection';
export { BodiesSection, StationsSection } from './SystemBodiesAndStationsSections';

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
