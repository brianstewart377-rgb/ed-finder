import type { EnrichmentStationStatus } from '@/types/api';

export function formatUnknown(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return value.toLocaleString();
  return value;
}

export function formatBool(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value ? 'yes' : 'no';
}

export function formatDistribution(value: Record<string, number> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return '—';
  return Object.entries(value)
    .map(([key, count]) => `${key}:${count}`)
    .join(', ');
}

export function formatProgress(status: EnrichmentStationStatus): string {
  const current = status.latest_progress?.current;
  const total = status.latest_progress?.total;
  const percent = status.latest_progress?.batch_progress_percent;
  if (current == null || total == null) return '—';
  const percentText = percent == null ? '' : ` (${percent}%)`;
  return `${current.toLocaleString()} / ${total.toLocaleString()}${percentText}`;
}

export function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}
