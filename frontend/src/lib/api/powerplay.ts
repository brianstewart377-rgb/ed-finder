import { jsonFetch } from './core';

export interface PowerplayJournalEventInput {
  observation_key: string;
  event_type: string;
  observed_at: string;
  game_build?: string | null;
  source_payload: Record<string, unknown>;
}

export interface PowerplayImportRequest {
  commander_key: string;
  source: 'journal';
  source_version: string;
  events: PowerplayJournalEventInput[];
}

export interface PowerplayImportReceipt {
  commander_key: string;
  events_received: number;
  system_observations_staged: number;
  commander_events_staged: number;
  duplicates_skipped: number;
  cycles_versioned: number;
}

export interface PowerplayValueEvidence {
  source: string;
  version: string;
  confidence: number;
  observed_at: string;
}

export interface PowerplaySystemState {
  system_address: number;
  system_name: string | null;
  x: number | null;
  y: number | null;
  z: number | null;
  controlling_power: unknown;
  control_state: unknown;
  control_progress: unknown;
  reinforcement_points: unknown;
  undermining_points: unknown;
  powers: unknown[];
  observed_at: string;
  cycle_start: string;
  game_build: string | null;
  source_payload: Record<string, unknown>;
  observation_age_seconds: number;
  uncertainty: 'low' | 'medium' | 'high';
  uncertainty_reasons: string[];
  value_provenance: Record<string, PowerplayValueEvidence>;
}

export interface PowerplaySystemsResponse {
  commander_key: string;
  systems: PowerplaySystemState[];
  count: number;
  truncated: boolean;
  snapshot_version: string;
}

export interface CommanderPowerplayResponse {
  commander_key: string;
  pledge: unknown;
  rank: unknown;
  merits: unknown;
  last_updated: string | null;
  cycle_start: string;
  cycle_merits_earned: unknown;
  value_provenance: Record<string, PowerplayValueEvidence>;
  recent_contributions: Array<{
    observed_at: string;
    power: unknown;
    merits_gained: unknown;
    total_merits: unknown;
    source: string;
    version: string;
    confidence: number;
  }>;
  snapshot_version: string;
}

export interface PowerplayHistoryResponse {
  commander_key: string;
  cycles: Array<{
    week: string;
    cycle_start: string;
    captured_at: string;
    control_snapshot: Record<string, unknown>;
    snapshot_hash: string;
    source: string;
    version: string;
    confidence: number;
  }>;
  change_events: Array<{
    system_address: number;
    system_name: string | null;
    observed_at: string;
    cycle_start: string;
    changes: Record<string, { from: unknown; to: unknown }>;
    source: string;
    version: string;
    confidence: number;
  }>;
  snapshot_version: string;
}

export function importPowerplay(request: PowerplayImportRequest): Promise<PowerplayImportReceipt> {
  return jsonFetch('/powerplay/import', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function powerplaySystems(commanderKey: string): Promise<PowerplaySystemsResponse> {
  return jsonFetch(`/powerplay/systems?commander_key=${encodeURIComponent(commanderKey)}`);
}

export function powerplayCommander(commanderKey: string): Promise<CommanderPowerplayResponse> {
  return jsonFetch(`/powerplay/commander?commander_key=${encodeURIComponent(commanderKey)}`);
}

export function powerplayHistory(commanderKey: string): Promise<PowerplayHistoryResponse> {
  return jsonFetch(`/powerplay/history?commander_key=${encodeURIComponent(commanderKey)}`);
}
