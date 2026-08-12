import type {
  ExpeditionImportRequest,
  RouteDetail,
  RouteListResponse,
  RouteType,
  SpanshRouteImportRequest,
} from '@/types/api';
import { jsonFetch } from './core';

export function listRoutes(commanderId: string, type?: RouteType): Promise<RouteListResponse> {
  const query = new URLSearchParams({ commander_id: commanderId });
  if (type) query.set('type', type);
  return jsonFetch(`/routes/list?${query.toString()}`);
}

export function getRoute(routeId: string, commanderId: string): Promise<RouteDetail> {
  const query = new URLSearchParams({ commander_id: commanderId });
  return jsonFetch(`/routes/${encodeURIComponent(routeId)}?${query.toString()}`);
}

export function getPersonalTrail(commanderId: string, fromDate?: string, toDate?: string): Promise<RouteDetail> {
  const query = new URLSearchParams({ commander_id: commanderId });
  if (fromDate) query.set('from_date', fromDate);
  if (toDate) query.set('to_date', toDate);
  return jsonFetch(`/routes/trail?${query.toString()}`);
}

export function listExpeditions(commanderId: string): Promise<RouteListResponse> {
  const query = new URLSearchParams({ commander_id: commanderId });
  return jsonFetch(`/routes/expeditions?${query.toString()}`);
}

export function importSpanshRoute(request: SpanshRouteImportRequest): Promise<RouteDetail> {
  return jsonFetch('/routes/import/spansh', { method: 'POST', body: JSON.stringify(request) });
}

export function saveExpedition(request: ExpeditionImportRequest): Promise<RouteDetail> {
  return jsonFetch('/routes/expeditions', { method: 'POST', body: JSON.stringify(request) });
}
