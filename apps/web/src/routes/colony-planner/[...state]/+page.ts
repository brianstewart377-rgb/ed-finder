import { error, redirect } from '@sveltejs/kit';
import { parseId64 } from '$lib/domain/id64';
import { plannerModes } from '$lib/routing/legacy-hash';

export function load({ params, url }) {
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
  let canonicalPath = `/colony-planner/system/${system}`;

  if (parts[cursor] === 'project' && parts[cursor + 1]) {
    try {
      project = decodeURIComponent(parts[cursor + 1]);
    } catch {
      error(404, 'Invalid project identifier');
    }
    canonicalPath += `/project/${encodeURIComponent(project)}`;
    cursor += 2;
  }

  if (parts[cursor] === 'mode') {
    const requestedMode = parts[cursor + 1] ?? '';
    if (!plannerModes.has(requestedMode)) error(404, 'Invalid planner mode');
    mode = requestedMode;
    canonicalPath += `/mode/${mode}`;
    cursor += 2;
  }

  if (parts[cursor] === 'detail' && parts[cursor + 1]) {
    let detail;
    try {
      detail = parseId64(parts[cursor + 1]);
    } catch {
      error(404, 'Invalid detail system identifier');
    }
    cursor += 2;
    if (cursor !== parts.length) error(404, 'Invalid planner route');

    const query = new URLSearchParams(url.search);
    query.set('system', detail);
    const search = query.toString();
    redirect(307, `${canonicalPath}${search ? `?${search}` : ''}`);
  }

  if (cursor !== parts.length) error(404, 'Invalid planner route');
  return { system, project, mode };
}
