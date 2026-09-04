import { error } from '@sveltejs/kit';
import { parseId64 } from '$lib/domain/id64';
import { plannerModes } from '$lib/routing/legacy-hash';
export function load({ params }) {
  const parts = (params.state ?? '').split('/').filter(Boolean);
  if (!parts.length) return { system: null, project: null, mode: null };
  if (parts[0] !== 'system' || !parts[1]) error(404, 'Invalid planner route');
  let system;
  try {
    system = parseId64(parts[1]);
  } catch {
    error(404, 'Invalid system identifier');
  }
  let cursor = 2;
  let project: string | null = null;
  let mode: string | null = null;
  if (parts[cursor] === 'project' && parts[cursor + 1]) {
    project = decodeURIComponent(parts[cursor + 1]);
    cursor += 2;
  }
  if (parts[cursor] === 'mode' && plannerModes.has(parts[cursor + 1] ?? '')) {
    mode = parts[cursor + 1];
    cursor += 2;
  }
  if (cursor !== parts.length) error(404, 'Invalid planner route');
  return { system, project, mode };
}
