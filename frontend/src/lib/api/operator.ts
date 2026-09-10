import type {
  AdminCronStatus,
  AdminDataStatus,
  AdminOperationHistoryResponse,
  AdminOperationRunResponse,
  AppStatus,
  CacheStats,
  EnrichmentStationStatus,
  EnrichmentWarehouseStatus,
  OperatorArtifactSummary,
  OperatorBridgeSummary,
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
  OperatorStagingImpactSummary,
} from '@/types/api';
import { jsonFetch } from './core';

function adminHeaders(token = ''): HeadersInit | undefined {
  const value = token.trim();
  return value ? { 'X-Admin-Token': value } : undefined;
}

// ── Admin / ops ──────────────────────────────────────────────────────
export function status(token = ''): Promise<AppStatus> {
  return jsonFetch('/status', { headers: adminHeaders(token) });
}

export function cacheStats(token = ''): Promise<CacheStats> {
  return jsonFetch('/cache/stats', { headers: adminHeaders(token) });
}

export function cacheClear(token: string): Promise<{
  ok: boolean;
  partial: boolean;
  redis_cleared: boolean;
  message: string;
}> {
  return jsonFetch('/cache/clear', {
    method:  'POST',
    headers: adminHeaders(token),
  });
}

export function rebuildClusters(token: string): Promise<{ message: string; job_id: string }> {
  return jsonFetch('/admin/rebuild-clusters', {
    method:  'POST',
    headers: adminHeaders(token),
  });
}

export function rebuildRatings(token: string): Promise<{
  ok: boolean;
  message: string;
  dirty_before: number;
  cleared: number;
}> {
  return jsonFetch('/admin/rebuild-ratings', {
    method:  'POST',
    headers: adminHeaders(token),
  });
}

export function enrichmentStationStatus(token: string): Promise<EnrichmentStationStatus> {
  return jsonFetch('/admin/enrichment/station-status', {
    headers: adminHeaders(token),
  });
}

export function enrichmentWarehouseStatus(token: string): Promise<EnrichmentWarehouseStatus> {
  return jsonFetch('/admin/enrichment/warehouse-status', {
    headers: adminHeaders(token),
  });
}

export function adminDataStatus(token: string): Promise<AdminDataStatus> {
  return jsonFetch('/admin/data-status', {
    headers: adminHeaders(token),
  });
}

export function adminCronStatus(token: string): Promise<AdminCronStatus> {
  return jsonFetch('/admin/cron-status', {
    headers: adminHeaders(token),
  });
}

export function adminRunOperation(token: string, operationKey: string): Promise<AdminOperationRunResponse> {
  return jsonFetch(`/admin/operations/${encodeURIComponent(operationKey)}`, {
    method: 'POST',
    headers: adminHeaders(token),
  });
}

export function adminOperationHistory(token: string, limit = 6): Promise<AdminOperationHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return jsonFetch(`/admin/operations/history?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorSafetyGates(token: string): Promise<OperatorSafetyGateSummary> {
  return jsonFetch('/api/operator/safety-gates', {
    headers: adminHeaders(token),
  });
}

export function operatorSourceRuns(token: string, limit = 25): Promise<OperatorSourceRunSummary[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return jsonFetch(`/api/operator/source-runs?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorSourceRunDetail(token: string, sourceRunKey: string): Promise<OperatorSourceRunDetail> {
  const params = new URLSearchParams({ source_run_key: sourceRunKey });
  return jsonFetch(`/api/operator/source-run-detail?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorSourceRunArtifacts(token: string, sourceRunKey: string): Promise<OperatorArtifactSummary> {
  const params = new URLSearchParams({ source_run_key: sourceRunKey });
  return jsonFetch(`/api/operator/source-run-artifacts?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorSourceRunBridge(token: string, sourceRunKey: string): Promise<OperatorBridgeSummary> {
  const params = new URLSearchParams({ source_run_key: sourceRunKey });
  return jsonFetch(`/api/operator/source-run-bridge?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorSourceRunStagingImpact(
  token: string,
  sourceRunKey: string,
  limit = 100,
): Promise<{
  source_run_key: string;
  bridge_present: boolean;
  staging_impact: OperatorStagingImpactSummary | null;
}> {
  const params = new URLSearchParams({ source_run_key: sourceRunKey, limit: String(limit) });
  return jsonFetch(`/api/operator/source-run-staging-impact?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}

export function operatorDiagnosticRows(
  token: string,
  options: { sourceRunKey?: string | null; limit?: number } = {},
): Promise<OperatorDiagnosticRowSummary[]> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 25) });
  if (options.sourceRunKey) params.set('source_run_key', options.sourceRunKey);
  return jsonFetch(`/api/operator/diagnostic-staging-rows?${params.toString()}`, {
    headers: adminHeaders(token),
  });
}
