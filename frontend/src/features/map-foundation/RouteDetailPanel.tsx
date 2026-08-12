import type { RouteDetail, RouteSummary } from '@/types/api';

function metadataText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function RouteDetailPanel({
  routes,
  selectedRouteId,
  detail,
  loading,
  error,
  onSelect,
}: {
  routes: RouteSummary[];
  selectedRouteId: string | null;
  detail: RouteDetail | null;
  loading: boolean;
  error: string | null;
  onSelect: (routeId: string | null) => void;
}) {
  const organizer = metadataText(detail?.metadata.organizer);
  const description = metadataText(detail?.metadata.description);
  const routeMode = metadataText(detail?.metadata.route_mode);
  return (
    <aside className="route-detail-panel" aria-label="Route detail" data-testid="route-detail-panel">
      <div className="route-detail-panel__header">
        <div>
          <span>Route layer</span>
          <strong>{detail?.name ?? 'Select a route'}</strong>
        </div>
        <select
          aria-label="Selected route"
          data-testid="route-selector"
          value={selectedRouteId ?? ''}
          onChange={(event) => onSelect(event.target.value || null)}
        >
          <option value="">Route layer off</option>
          {routes.map((route) => (
            <option key={route.route_id} value={route.route_id}>
              {route.name} · {route.type}
            </option>
          ))}
        </select>
      </div>
      {loading && <p className="route-detail-panel__state">Loading route…</p>}
      {error && <p role="alert" className="route-detail-panel__error">{error}</p>}
      {!loading && !error && detail && (
        <>
          <div className="route-detail-panel__metrics">
            <div><span>Complete</span><strong>{detail.completion_percent.toFixed(1)}%</strong></div>
            <div><span>Remaining</span><strong>{detail.remaining_distance.toLocaleString()} LY</strong></div>
            <div><span>Actual / planned</span><strong>{detail.visited_count} / {detail.waypoint_count}</strong></div>
          </div>
          <div className="route-detail-panel__progress" aria-label={`${detail.completion_percent}% complete`}>
            <span style={{ width: `${Math.min(100, Math.max(0, detail.completion_percent))}%` }} />
          </div>
          <p className="route-detail-panel__meta">
            {detail.source}{routeMode ? ` · ${routeMode}` : ''}{organizer ? ` · ${organizer}` : ''}
          </p>
          {description && <p className="route-detail-panel__description">{description}</p>}
          <ol className="route-detail-panel__waypoints" data-testid="route-alignment-list">
            {detail.planned_actual_alignment.map((alignment) => (
              <li
                key={`${detail.route_id}-${alignment.planned_order}`}
                className={alignment.planned_order === detail.current_waypoint_index ? 'is-current' : ''}
              >
                <span aria-label={alignment.visited ? 'Visited' : 'Not visited'}>{alignment.visited ? '✓' : '○'}</span>
                <div>
                  <strong>{alignment.waypoint.system_name}</strong>
                  <small>
                    {alignment.visited_at ? new Date(alignment.visited_at).toLocaleString() : 'Planned'}
                    {alignment.distance_from_planned != null ? ` · ${alignment.distance_from_planned.toFixed(1)} LY off route` : ''}
                  </small>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      {!loading && !error && !detail && (
        <p className="route-detail-panel__state">
          {routes.length ? 'Choose a personal, journal, Spansh, or expedition route.' : 'No saved routes yet. Import journals or a Spansh route to begin.'}
        </p>
      )}
    </aside>
  );
}
