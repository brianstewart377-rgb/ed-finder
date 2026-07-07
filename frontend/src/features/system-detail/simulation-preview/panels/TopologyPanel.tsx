import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';

type TopologySummary = {
  local_body_groups?: Array<{
    local_body_id: string;
    body_name?: string | null;
    main_surface_port?: { facility_name: string; tier: number } | null;
    main_orbital_port?: { facility_name: string; tier: number } | null;
    facility_count: number;
  }>;
  strong_links?: unknown[];
  weak_links?: unknown[];
  pass_through_links?: unknown[];
  converted_ports?: Array<{ facility_name: string; reason: string }>;
};

export function TopologyPanel({ topology }: { topology: SimulateBuildResponse['topology'] }) {
  const summary = topology as TopologySummary | undefined;
  const groups = summary?.local_body_groups ?? [];
  if (groups.length === 0) return null;
  const strong = summary?.strong_links?.length ?? 0;
  const weak = summary?.weak_links?.length ?? 0;
  const passThrough = summary?.pass_through_links?.length ?? 0;
  const converted = summary?.converted_ports ?? [];
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3 font-mono text-[11px] text-silver">
      <div className="mb-2 text-[10px] uppercase tracking-[0.18em] text-silver-dk">Topology graph</div>
      <div className="flex flex-wrap gap-1.5">
        <Chip tone={strong > 0 ? 'good' : 'default'}>{strong} strong links</Chip>
        <Chip>{weak} weak links</Chip>
        {passThrough > 0 && <Chip tone="good">{passThrough} pass-through</Chip>}
        {converted.length > 0 && <Chip tone="warn">{converted.length} converted ports</Chip>}
      </div>
      <div className="mt-2 space-y-1.5">
        {groups.slice(0, 3).map((group) => (
          <div key={group.local_body_id} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
            <div className="text-silver">{group.body_name || `Body ${group.local_body_id}`}</div>
            <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-silver-dk">
              {group.main_orbital_port && <span>Orbital Main: {group.main_orbital_port.facility_name}</span>}
              {group.main_surface_port && <span>Surface Main: {group.main_surface_port.facility_name}</span>}
              <span>{group.facility_count} assets</span>
            </div>
          </div>
        ))}
      </div>
      {converted.slice(0, 2).map((port) => (
        <div key={port.facility_name} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 text-[10px] leading-snug text-gold">
          {port.facility_name}: {port.reason}
        </div>
      ))}
    </div>
  );
}
