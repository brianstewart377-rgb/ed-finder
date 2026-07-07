import type { SystemDetail, SystemResult } from '@/types/api';
import { MapTab } from '@/features/map/MapTab';


export function MapFoundationWorkspaceView({ system }: { system: SystemDetail }) {
  const coords = toCoords(system.coords);
  const plottedSystems = [toMapSystem(system)];
  const reference = {
    name: system.name ?? `ID64 ${system.id64}`,
    x: coords.x,
    z: coords.z,
  };

  return (
    <div className="space-y-3" data-testid="map-foundation-workspace-view">
      <section className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk">
        <span className="font-bold text-cyan">Map mode</span>
        <span className="ml-2">
          Stage 20C establishes the planner map foundation as a read-only spatial context surface. Layer toggles, timeline,
          and selection are informational only and do not mutate Build Plan, Evidence, Validation, or any Stage 19 deferred lane.
        </span>
      </section>
      <MapTab systems={plottedSystems} reference={reference} />
    </div>
  );
}


function toMapSystem(system: SystemDetail): SystemResult {
  const coords = toCoords(system.coords);
  return {
    id64: system.id64,
    name: system.name ?? `ID64 ${system.id64}`,
    coords,
    population: system.population ?? null,
    primaryEconomy: system.primaryEconomy ?? null,
    allegiance: system.allegiance ?? null,
    security: system.security ?? null,
    distance: 0,
  } as SystemResult;
}

function toCoords(value: unknown): { x: number; y: number; z: number } {
  const coords = (value ?? {}) as { x?: number | null; y?: number | null; z?: number | null };
  return {
    x: typeof coords.x === 'number' ? coords.x : 0,
    y: typeof coords.y === 'number' ? coords.y : 0,
    z: typeof coords.z === 'number' ? coords.z : 0,
  };
}
