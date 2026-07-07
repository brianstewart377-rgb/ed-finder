import { formatPopulationForSystem, formatDistance, formatCoords } from '@/lib/format';
import { archetypeTierFromScore, getDevelopmentScore, getFinderArchetypeSummary } from '@/lib/archetypes';
import type { SystemResult } from '@/types/api';

export const VIEW_MODES = [
  { id: 'results', label: 'Results', description: 'Fits the current Finder result dots.' },
  { id: 'galaxy', label: 'Galaxy', description: 'Frames the full galactic disc and axes.' },
  { id: 'reference', label: 'Reference', description: 'Centers the chosen reference system.' },
] as const;

export function MapLegend({
  activeLayerSummary,
  currentViewLabel,
  currentViewDescription,
}: {
  activeLayerSummary: string;
  currentViewLabel: string;
  currentViewDescription: string;
}) {
  return (
    <details
      data-testid="map-legend"
      className="panel-thin px-4 py-2 text-[11px] text-silver-dk"
    >
      <summary className="cursor-pointer select-none font-mono text-orange-lt tracking-wider">
        Map legend · {currentViewLabel}: {currentViewDescription} · Active: {activeLayerSummary}
      </summary>
      <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        <LegendItem label="Results" value="Fits the current Finder result dots." />
        <LegendItem label="Galaxy" value="Frames the full galactic disc and axes." />
        <LegendItem label="Reference" value="Centers the chosen reference system." />
        <LegendItem label="Finder dots" value="Current Finder systems with archetype-led development scores." />
        <LegendItem label="Regions" value="Canonical galaxy region labels." />
        <LegendItem label="Heatmap" value="Voxel cells summarising legacy rating density from map aggregate views." />
        <LegendItem label="Clusters" value="Approximate hulls around high-rating grouped systems." />
        <LegendItem label="Timeline" value="Discovery-count buckets for the map scrubber foundation." />
      </div>
    </details>
  );
}

export function TimelineSummary({
  dataTestId = 'map-timeline-summary',
  bucket,
  total,
  pointCount,
  latestDate,
}: {
  dataTestId?: string;
  bucket: 'month' | 'quarter' | 'year';
  total: number;
  pointCount: number;
  latestDate: string | null;
}) {
  return (
    <section
      data-testid={dataTestId}
      className="panel-thin flex flex-wrap items-center gap-3 px-3 py-2 font-mono text-[11px] text-silver-dk"
    >
      <span className="text-orange-lt uppercase tracking-[0.14em]">Timeline foundation</span>
      <span>{pointCount} buckets</span>
      <span>{total} discoveries tracked</span>
      <span>Bucket: {bucket}</span>
      <span>Latest: {latestDate ?? 'Unknown'}</span>
    </section>
  );
}

export function SelectionPanel({ system }: { system: SystemResult | null }) {
  if (!system) {
    return (
      <aside
        data-testid="map-selection-panel"
        className="panel-thin border-dashed p-4 font-mono text-xs text-silver-dk space-y-2"
      >
        <div className="text-orange-lt text-sm font-display tracking-wider">Select a star</div>
        <p>Click any system on the map to see its details here.</p>
      </aside>
    );
  }
  const archetypeScore = getDevelopmentScore(system);
  const tier = system.archetype_tier ?? archetypeTierFromScore(archetypeScore);
  const archetype = getFinderArchetypeSummary(system);
  return (
    <aside
      data-testid="map-selection-panel"
      className="panel-thin p-4 font-mono text-xs space-y-3"
    >
      <div>
        <div className="text-orange-lt font-bold text-sm">{system.name}</div>
        <div className="text-text-dim text-[10px]">
          {formatCoords(system.coords, system.id64)}
        </div>
      </div>
      <div className="flex gap-2 items-center">
        <span
          className={[
            'px-2 py-0.5 rounded border font-bold',
            tier === 'S' && 'bg-cyan/20 text-cyan border-cyan/50',
            tier === 'A' && 'bg-green/20 text-green border-green/50',
            tier === 'B' && 'bg-gold/20 text-gold border-gold/50',
            tier === 'C' && 'bg-orange/20 text-orange border-orange/50',
            tier === 'D' && 'bg-red/20 text-red border-red/50',
            tier == null && 'bg-bg4 text-text-dim border-border',
          ].filter(Boolean).join(' ')}
        >
          {tier ?? '—'} {archetypeScore ?? '—'}
        </span>
        <span className="text-text-dim">
          {formatPopulationForSystem(system)}
        </span>
      </div>
      <dl className="space-y-1 text-[11px]">
        {archetype && (
          <Row
            label={archetype.source === 'archetype' ? 'Primary archetype' : 'Suggested archetype'}
            value={archetype.label}
          />
        )}
        {system.buildability_score != null && <Row label="Buildability" value={`${system.buildability_score}/100`} />}
        {system.purity_score != null && <Row label="Purity" value={`${system.purity_score}/100`} />}
        {system.primaryEconomy && (
          <Row label="Economy" value={system.primaryEconomy} />
        )}
        {system.allegiance && <Row label="Allegiance" value={system.allegiance} />}
        {system.security && <Row label="Security" value={system.security} />}
        {formatDistance(system.distance) && (
          <Row label="Distance" value={formatDistance(system.distance)!} />
        )}
      </dl>
    </aside>
  );
}

export function MapLayerStatusRow({
  sourceLabel,
  showRegions,
  showHeatmap,
  showClusters,
  showTimeline,
  timelineBucket,
  regionsLoading,
  regionsError,
  heatmapLoading,
  heatmapError,
  clustersLoading,
  clustersError,
  timelineLoading,
  timelineError,
}: {
  sourceLabel: string;
  showRegions: boolean;
  showHeatmap: boolean;
  showClusters: boolean;
  showTimeline: boolean;
  timelineBucket: 'month' | 'quarter' | 'year';
  regionsLoading: boolean;
  regionsError: boolean;
  heatmapLoading: boolean;
  heatmapError: boolean;
  clustersLoading: boolean;
  clustersError: boolean;
  timelineLoading: boolean;
  timelineError: boolean;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div
        data-testid="map-source-badge"
        className="inline-flex items-center gap-2 px-3 py-1 rounded-chunk-sm text-[11px] font-mono text-silver-dk"
        style={{
          background: 'linear-gradient(180deg, rgba(28, 31, 36, 0.6), rgba(18, 20, 24, 0.6))',
          border: '1px solid hsl(216 10% 24%)',
        }}
      >
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: '#3ddc84' }}
        />
        <span>{sourceLabel}</span>
      </div>
      {showRegions && regionsLoading && <StatusText tone="loading">Loading regions…</StatusText>}
      {showRegions && regionsError && <StatusText tone="error">Regions failed</StatusText>}
      {showHeatmap && heatmapLoading && <StatusText tone="loading">Loading heatmap…</StatusText>}
      {showHeatmap && heatmapError && <StatusText tone="error">Heatmap failed</StatusText>}
      {showClusters && clustersLoading && <StatusText tone="loading">Loading clusters…</StatusText>}
      {showClusters && clustersError && <StatusText tone="error">Clusters failed</StatusText>}
      {showTimeline && timelineLoading && <StatusText tone="loading">Loading timeline…</StatusText>}
      {showTimeline && timelineError && <StatusText tone="error">Timeline failed</StatusText>}
      {showTimeline && !timelineLoading && !timelineError && (
        <span className="font-mono text-[10px] text-silver-dk">Timeline bucket: {timelineBucket}</span>
      )}
    </div>
  );
}

function LegendItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] uppercase tracking-wider text-silver">{label}</div>
      <div className="leading-snug">{value}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-text-dim">{label}</dt>
      <dd className="text-text">{value}</dd>
    </div>
  );
}

function StatusText({
  tone,
  children,
}: {
  tone: 'loading' | 'error';
  children: string;
}) {
  return (
    <span className={tone === 'loading'
      ? 'font-mono text-[10px] text-silver-dk animate-pulse'
      : 'font-mono text-[10px] text-red'}
    >
      {children}
    </span>
  );
}
