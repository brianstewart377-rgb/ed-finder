import type { CompareEntry } from '$lib/persistence/storage';

export const COMPARE_MAX = 6;
const UNAVAILABLE = 'Unavailable';

export interface CompareCell {
  display: string;
  csvValue: string | number;
  best: boolean;
}

export interface CompareMetricRow {
  label: string;
  cells: CompareCell[];
}

const archetypeLabels: Readonly<Record<string, string>> = {
  refinery_industrial: 'Refinery / Industrial Megacomplex',
  extraction_refinery: 'Extraction / Refinery Mining Hub',
  agriculture_terraforming: 'Agriculture / Terraforming Colony',
  hitech_tourism: 'High Tech / Tourism Prestige Colony',
  expansion_capital: 'Expansion Capital',
  trade_logistics: 'Trade / Logistics Hub',
  population_capital: 'Population Capital',
  ax_forward_base: 'AX Forward Operating Base',
  military_industrial: 'Military / Industrial Complex',
  flexible_multirole: 'Flexible Multi-Role Colony',
};

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function archetype(value: unknown): string {
  const key = text(value);
  return key
    ? (archetypeLabels[key] ??
        key
          .split(/[_-]+/)
          .filter(Boolean)
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' '))
    : UNAVAILABLE;
}

function development(value: number | null): string {
  if (value === null) return UNAVAILABLE;
  const tier =
    value >= 88
      ? 'S'
      : value >= 76
        ? 'A'
        : value >= 60
          ? 'B'
          : value >= 45
            ? 'C'
            : 'D';
  return `${tier} ${value}`;
}

function population(entry: CompareEntry): string {
  const value = finite(entry.population);
  if (value === null || value < 0) return 'Unknown';
  if (value === 0) {
    return entry.is_colonised === true || entry.is_being_colonised === true
      ? 'Population unknown'
      : 'Uninhabited';
  }
  if (value >= 1_000_000_000) return `${(value / 1e9).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1e3).toFixed(1)}K`;
  return String(value);
}

function status(entry: CompareEntry): string {
  const inhabitants = finite(entry.population);
  if (entry.is_colonised === true || (inhabitants !== null && inhabitants > 0))
    return 'Colonised';
  if (entry.is_being_colonised === true) return 'Colonising';
  if (entry.is_colonised === false || inhabitants === 0) return 'Available';
  return 'Unknown';
}

/** Normalize legacy snapshots at the display boundary without changing stored data. */
export function buildCompareRows(
  entries: readonly CompareEntry[],
): CompareMetricRow[] {
  const plain = (
    label: string,
    render: (entry: CompareEntry) => string,
  ): CompareMetricRow => ({
    label,
    cells: entries.map((entry) => {
      const display = render(entry);
      return { display, csvValue: display, best: false };
    }),
  });
  const numeric = (
    label: string,
    extract: (entry: CompareEntry) => unknown,
    render: (value: number | null) => string = (value) =>
      value === null ? UNAVAILABLE : String(value),
    higherIsBetter = true,
  ): CompareMetricRow => {
    const values = entries.map((entry) => finite(extract(entry)));
    const known = values.filter((value): value is number => value !== null);
    // One measured value cannot establish a winner against unknowns. All-equal
    // values need no annotation; tied best values otherwise receive equal credit.
    const hasComparison = known.length >= 2 && new Set(known).size > 1;
    const best = hasComparison
      ? higherIsBetter
        ? Math.max(...known)
        : Math.min(...known)
      : null;
    return {
      label,
      cells: values.map((value) => ({
        display: render(value),
        csvValue: value ?? UNAVAILABLE,
        best: value !== null && best !== null && value === best,
      })),
    };
  };
  const count = (label: string, key: string) =>
    numeric(label, (entry) => {
      const value = finite(entry[key]);
      return value !== null && value >= 0 ? value : null;
    });

  return [
    numeric(
      'Development score',
      (entry) =>
        finite(entry.archetype_score) ??
        finite(entry.overall_development_potential),
      development,
    ),
    plain('Primary archetype', (entry) => archetype(entry.primary_archetype)),
    plain('Secondary archetype', (entry) =>
      archetype(entry.secondary_archetype),
    ),
    plain('Archetype confidence', (entry) => {
      const confidence = finite(entry.archetype_confidence);
      return confidence !== null && confidence >= 0 && confidence <= 1
        ? `${Math.round(confidence * 100)}%`
        : UNAVAILABLE;
    }),
    numeric('Buildability', (entry) => entry.buildability_score),
    numeric('Purity', (entry) => entry.purity_score),
    count('Estimated slots', 'est_total_slots'),
    plain(
      'Primary economy',
      (entry) =>
        text(entry.primaryEconomy) ??
        text(entry.primary_economy) ??
        UNAVAILABLE,
    ),
    numeric(
      'Distance from ref',
      (entry) => {
        const distance = finite(entry.distance);
        // Legacy searches can use zero when no reference was chosen.
        return distance !== null && distance > 0 ? distance : null;
      },
      (value) => (value === null ? UNAVAILABLE : `${value.toFixed(2)} LY`),
      false,
    ),
    plain('Population', population),
    plain('Status', status),
    plain(
      'Main star',
      (entry) =>
        text(entry.main_star_subtype) ??
        text(entry.main_star_type) ??
        UNAVAILABLE,
    ),
    plain('Security', (entry) => text(entry.security) ?? UNAVAILABLE),
    plain('Allegiance', (entry) => text(entry.allegiance) ?? UNAVAILABLE),
    count('ELW', 'elw_count'),
    count('Water worlds', 'ww_count'),
    count('Ammonia', 'ammonia_count'),
    count('Terraformable', 'terraformable_count'),
    count('Landable', 'landable_count'),
    count('Bio signals', 'bio_signal_total'),
    count('Geo signals', 'geo_signal_total'),
  ];
}

export function compareCsv(entries: readonly CompareEntry[]): string {
  const quote = (value: string | number) => {
    const safe =
      typeof value === 'string' && /^[=+\-@\t\r]/.test(value)
        ? `'${value}`
        : String(value);
    return `"${safe.replace(/"/g, '""')}"`;
  };
  return [
    ['Metric', ...entries.map((entry) => entry.name)],
    ...buildCompareRows(entries).map((row) => [
      row.label === 'Distance from ref' ? 'Distance from ref LY' : row.label,
      ...row.cells.map((cell) => cell.csvValue),
    ]),
  ]
    .map((row) => row.map(quote).join(','))
    .join('\r\n');
}
