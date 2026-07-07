import { useCallback, useEffect, useState } from 'react';

/**
 * FC Planner = Fleet Carrier route planning.
 *
 * Stored locally so the cmdr can pick up where they left off across
 * reloads. Storage key `ed_fc_v2`. Pure client computation: no backend
 * call, just Euclidean math on the waypoint coords.
 */
export interface FcWaypoint {
  /** Stable id for React keys + reorder. We can't trust id64 since the
   *  legacy app accepted free-text waypoints with no coords. */
  id:    string;
  name:  string;
  /** Coords are nullable: the user can add a name-only waypoint and we'll
   *  refuse to include it in the calculation rather than hand-waving. */
  x:     number | null;
  y:     number | null;
  z:     number | null;
  id64?: number | null;
}

export interface FcConfig {
  jump_range_ly:    number;
  cargo_t:          number;
  tritium_per_jump: number;
  tritium_price_cr: number;
}

export const DEFAULT_FC_CONFIG: FcConfig = {
  jump_range_ly:    500,
  cargo_t:          25_000,
  tritium_per_jump: 50,
  tritium_price_cr: 50_000,
};

export interface FcLeg {
  from:        FcWaypoint;
  to:          FcWaypoint;
  /** null = at least one endpoint has unknown coords. */
  distance_ly: number | null;
  hops:        number | null;
  tritium_t:   number | null;
}

export interface FcRoute {
  legs:                FcLeg[];
  total_distance_ly:   number;
  total_hops:          number;
  total_tritium_t:     number;
  total_cost_cr:       number;
  cargo_trips:         number;
  /** Names of waypoints we couldn't compute a leg for (no coords). */
  missing_coord_names: string[];
}

const STORAGE_KEY = 'ed_fc_v2';

interface PersistedShape { waypoints: FcWaypoint[]; config: FcConfig }

function readStorage(): PersistedShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { waypoints: [], config: DEFAULT_FC_CONFIG };
    const parsed = JSON.parse(raw) as Partial<PersistedShape>;
    return {
      waypoints: Array.isArray(parsed.waypoints) ? parsed.waypoints : [],
      config:    { ...DEFAULT_FC_CONFIG, ...(parsed.config ?? {}) },
    };
  } catch {
    return { waypoints: [], config: DEFAULT_FC_CONFIG };
  }
}

function writeStorage(state: PersistedShape): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
  catch { /* quota / private mode */ }
}

function uid(): string {
  return `wp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

export interface UseFcPlanner {
  waypoints:  FcWaypoint[];
  config:     FcConfig;
  add:        (input: Omit<FcWaypoint, 'id'>) => void;
  remove:     (id: string) => void;
  move:       (id: string, dir: -1 | 1) => void;
  clear:      () => void;
  setConfig:  (patch: Partial<FcConfig>) => void;
  /** Pure fn from `waypoints` + `config` → {legs, totals}. */
  route:      FcRoute;
  exportCsv:  () => void;
}

export function useFcPlanner(): UseFcPlanner {
  const [state, setState] = useState<PersistedShape>(readStorage);
  const { waypoints, config } = state;

  // Persist on every mutation (cheap; no debounce needed at this volume).
  useEffect(() => { writeStorage(state); }, [state]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setState(readStorage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const add = useCallback<UseFcPlanner['add']>((input) => {
    setState((s) => ({
      ...s,
      waypoints: [...s.waypoints, { ...input, id: uid() }],
    }));
  }, []);

  const remove = useCallback((id: string) => {
    setState((s) => ({ ...s, waypoints: s.waypoints.filter((w) => w.id !== id) }));
  }, []);

  const move = useCallback((id: string, dir: -1 | 1) => {
    setState((s) => {
      const i = s.waypoints.findIndex((w) => w.id === id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= s.waypoints.length) return s;
      const next = s.waypoints.slice();
      [next[i], next[j]] = [next[j], next[i]];
      return { ...s, waypoints: next };
    });
  }, []);

  const clear = useCallback(() => {
    setState((s) => ({ ...s, waypoints: [] }));
  }, []);

  const setConfig = useCallback<UseFcPlanner['setConfig']>((patch) => {
    setState((s) => ({ ...s, config: { ...s.config, ...patch } }));
  }, []);

  const route = computeRoute(waypoints, config);

  const exportCsv = useCallback(() => {
    if (waypoints.length === 0) return;
    const q = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['Order', 'System', 'X', 'Y', 'Z',
                    'Distance from prev (LY)', 'Hops from prev', 'Tritium from prev (t)'];
    const rows = waypoints.map((wp, i) => {
      const leg = i > 0 ? route.legs[i - 1] : null;
      return [
        i + 1, wp.name,
        wp.x ?? '', wp.y ?? '', wp.z ?? '',
        leg?.distance_ly?.toFixed(2) ?? '',
        leg?.hops ?? '',
        leg?.tritium_t ?? '',
      ];
    });
    const csv = [header.map(q).join(','), ...rows.map((r) => r.map(q).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ed-fc-route-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [waypoints, route]);

  return { waypoints, config, add, remove, move, clear, setConfig, route, exportCsv };
}

// ─── Pure computation ──────────────────────────────────────────────────────

function computeRoute(waypoints: FcWaypoint[], config: FcConfig): FcRoute {
  const legs: FcLeg[] = [];
  const missing = new Set<string>();
  let total_distance_ly = 0;
  let total_hops        = 0;
  let total_tritium_t   = 0;

  const jr = Math.max(1, config.jump_range_ly);  // guard against /0

  for (let i = 1; i < waypoints.length; i++) {
    const a = waypoints[i - 1];
    const b = waypoints[i];

    const haveCoords = a.x != null && a.y != null && a.z != null
                    && b.x != null && b.y != null && b.z != null;

    if (!haveCoords) {
      if (a.x == null) missing.add(a.name);
      if (b.x == null) missing.add(b.name);
      legs.push({ from: a, to: b, distance_ly: null, hops: null, tritium_t: null });
      continue;
    }

    const dx = b.x! - a.x!;
    const dy = b.y! - a.y!;
    const dz = b.z! - a.z!;
    const d  = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const hops = Math.ceil(d / jr);
    const trit = hops * config.tritium_per_jump;

    legs.push({ from: a, to: b, distance_ly: d, hops, tritium_t: trit });
    total_distance_ly += d;
    total_hops        += hops;
    total_tritium_t   += trit;
  }

  const total_cost_cr = total_tritium_t * config.tritium_price_cr;
  const cargo_trips   = config.cargo_t > 0
    ? Math.ceil(total_tritium_t / config.cargo_t)
    : 0;

  return {
    legs,
    total_distance_ly,
    total_hops,
    total_tritium_t,
    total_cost_cr,
    cargo_trips,
    missing_coord_names: [...missing],
  };
}
