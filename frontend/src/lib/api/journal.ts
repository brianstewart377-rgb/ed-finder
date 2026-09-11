import { jsonFetch } from './core';

// NOTE(types-gen): regenerate api.gen.ts and switch to components['schemas']
// when the API with /api/v1/journal is running. Until then these interfaces
// are hand-declared to match the V3 journal wire DTOs EXACTLY (snake_case
// field names, same names/types) — see docs/superpowers/plans/2026-08-28-v3-
// journal-intelligence-foundation.md Task 3. Do NOT hand-edit api.gen.ts.

// ── Personal journal lane (POST /api/v1/journal/imports) ────────────────

export interface V3JournalFileRef {
  name: string;
  content_sha256: string;
  size_bytes: number;
  line_count: number;
  event_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
}

export interface V3JournalEventInput {
  event_type: string;
  event_timestamp: string;
  source_record_hash: string;
  source_file: string;
  source_offset: number;
  payload: Record<string, unknown>;
}

export interface V3JournalImportRequest {
  parser_version: string;
  files: V3JournalFileRef[];
  events: V3JournalEventInput[];
}

export interface V3JournalImportReceipt {
  import_id: string;
  status: string;
  files_received: number;
  files_skipped: number;
  files_admitted: number;
  events_received: number;
  events_inserted: number;
  duplicates_skipped: number;
  privacy_stripped_fields: number;
  event_counts: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
}

export interface V3JournalSummaryResponse {
  events_stored: number;
  unique_bodies: number;
  unique_bio_observations: number;
  systems_observed: number;
  last_imported_at: string | null;
  event_counts: Record<string, number>;
  imported_files: number;
}

export interface V3JournalSystemRow {
  system_id64: string;
  system_name: string | null;
  first_observed_at: string | null;
  last_observed_at: string | null;
  visit_count: number;
}

export interface V3JournalBodyRow {
  system_id64: string;
  body_id: string;
  body_name: string | null;
  first_observed_at: string | null;
  last_observed_at: string | null;
  scan_count: number;
}

export interface V3CodexEntryRow {
  entry_id: string;
  name: string | null;
  category: string | null;
  subcategory: string | null;
  region: string | null;
  system_id64: string | null;
  body_id: string | null;
  first_observed_at: string | null;
  last_observed_at: string | null;
}

export interface V3OrganicProgressRow {
  genus: string;
  species: string;
  variant: string | null;
  stages: string[];
  first_observed_at: string | null;
  last_observed_at: string | null;
}

export interface V3SaleRow {
  bio_data: Array<Record<string, unknown>>;
  market_id: string | null;
  observed_at: string;
}

// ── Research lane (consent + export) ────────────────────────────────────

export type V3ConsentDecision = 'GRANT' | 'WITHDRAW';

export interface V3ResearchConsentState {
  decision: V3ConsentDecision | 'NONE';
  consent_version: string | null;
  sanitized_contract_version: string | null;
  purpose: string | null;
  audience_code: string | null;
  decided_at: string | null;
  withdrawable: boolean;
}

export interface V3ResearchConsentRequest {
  decision: V3ConsentDecision;
}

export interface V3ResearchExportRequest {
  limit: number;
}

export interface V3ResearchExportReceipt {
  export_batch_id: string;
  sanitized_contract_version: string;
  consent_version: string;
  lineage_token: string;
  observation_count: number;
  payload_sha256: string;
  batch_state: string;
  created_at: string;
}

/** Receipt + the deterministically rebuilt export payload. */
export interface V3ResearchExportDetail extends V3ResearchExportReceipt {
  payload: Record<string, unknown>;
}

// ── Functions ───────────────────────────────────────────────────────────

export function createV3JournalImport(request: V3JournalImportRequest): Promise<V3JournalImportReceipt> {
  return jsonFetch('/v1/journal/imports', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function getV3JournalImport(importId: string): Promise<V3JournalImportReceipt> {
  return jsonFetch(`/v1/journal/imports/${encodeURIComponent(importId)}`);
}

export function getV3JournalSummary(): Promise<V3JournalSummaryResponse> {
  return jsonFetch('/v1/journal/summary');
}

export function listV3JournalSystems(offset = 0, limit = 50): Promise<V3JournalSystemRow[]> {
  return jsonFetch(`/v1/journal/systems?offset=${offset}&limit=${limit}`);
}

export function listV3JournalBodies(offset = 0, limit = 50): Promise<V3JournalBodyRow[]> {
  return jsonFetch(`/v1/journal/bodies?offset=${offset}&limit=${limit}`);
}

export function listV3JournalCodex(): Promise<V3CodexEntryRow[]> {
  return jsonFetch('/v1/journal/codex');
}

export function listV3JournalOrganics(): Promise<V3OrganicProgressRow[]> {
  return jsonFetch('/v1/journal/organics');
}

export function listV3JournalSales(offset = 0, limit = 50): Promise<V3SaleRow[]> {
  return jsonFetch(`/v1/journal/sales?offset=${offset}&limit=${limit}`);
}

export function getV3ResearchConsent(): Promise<V3ResearchConsentState> {
  return jsonFetch('/v1/journal/research-consent');
}

export function putV3ResearchConsent(request: V3ResearchConsentRequest): Promise<V3ResearchConsentState> {
  return jsonFetch('/v1/journal/research-consent', {
    method: 'PUT',
    body: JSON.stringify(request),
  });
}

export function createV3ResearchExport(request: V3ResearchExportRequest): Promise<V3ResearchExportReceipt> {
  return jsonFetch('/v1/journal/research-exports', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function listV3ResearchExports(): Promise<V3ResearchExportReceipt[]> {
  return jsonFetch('/v1/journal/research-exports');
}

export function getV3ResearchExport(exportBatchId: string): Promise<V3ResearchExportDetail> {
  return jsonFetch(`/v1/journal/research-exports/${encodeURIComponent(exportBatchId)}`);
}
