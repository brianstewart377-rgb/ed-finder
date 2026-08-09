import type {
  ExplorationFactsResponse,
  ExplorationImportReceipt,
  ExplorationImportRequest,
} from '@/types/api';
import { jsonFetch } from './core';

export function importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt> {
  return jsonFetch('/exploration/import', {
    method: 'POST',
    body:   JSON.stringify(request),
  });
}

export function getExplorationFacts(syncKey: string): Promise<ExplorationFactsResponse> {
  return jsonFetch(`/exploration/facts/${encodeURIComponent(syncKey)}`);
}
