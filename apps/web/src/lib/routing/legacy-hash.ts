import { parseId64, type Id64 } from '$lib/domain/id64';

export const plannerModes = new Set([
  'build-plan',
  'suggested-builds',
  'preview',
  'sequence',
  'map',
  'evidence',
  'validation',
  'export',
]);

const hosts: Record<string, string> = {
  finder: '/',
  map: '/explore',
  'my-work': '/my-work',
  watchlist: '/my-work/watchlist',
  pinned: '/my-work/pinned',
  colony: '/my-work/colony',
  compare: '/compare',
  'search-tuning': '/search-tuning',
  fc: '/fc',
  admin: '/admin',
  operator: '/operator',
};

export interface LegacyDestination {
  pathname: string;
  search: string;
}

function id(value: string | undefined): Id64 | null {
  if (!value) return null;
  try {
    return parseId64(value);
  } catch {
    return null;
  }
}

/** Convert the former React hash router URL without using lossy numeric coercion. */
export function legacyHashDestination(
  hash: string,
  currentSearch = '',
): LegacyDestination | null {
  if (!hash) return null;
  const raw = hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean);
  if (parts.length === 0 || parts[0] === 'finder') {
    if (parts[1] === 'system') {
      const system = id(parts[2]);
      return system
        ? { pathname: '/', search: mergeQuery(currentSearch, 'system', system) }
        : { pathname: '/', search: currentSearch };
    }
    return { pathname: '/', search: currentSearch };
  }
  if (parts[0] === 'system') {
    const system = id(parts[1]);
    return system
      ? { pathname: '/', search: mergeQuery(currentSearch, 'system', system) }
      : { pathname: '/', search: currentSearch };
  }
  if (parts[0] === 'colony-planner')
    return plannerDestination(parts, currentSearch);

  const pathname = hosts[parts[0]];
  if (!pathname) return { pathname: '/', search: currentSearch };
  if (parts[1] === 'system') {
    const system = id(parts[2]);
    return system
      ? { pathname, search: mergeQuery(currentSearch, 'system', system) }
      : { pathname, search: currentSearch };
  }
  return { pathname, search: currentSearch };
}

function plannerDestination(
  parts: string[],
  currentSearch: string,
): LegacyDestination {
  const system = parts[1] === 'system' ? id(parts[2]) : null;
  if (!system) return { pathname: '/colony-planner', search: currentSearch };
  let pathname = `/colony-planner/system/${system}`;
  let cursor = 3;
  if (parts[cursor] === 'project' && parts[cursor + 1]) {
    pathname += `/project/${encodeURIComponent(decodeURIComponent(parts[cursor + 1]))}`;
    cursor += 2;
  }
  if (parts[cursor] === 'mode' && plannerModes.has(parts[cursor + 1] ?? '')) {
    pathname += `/mode/${parts[cursor + 1]}`;
    cursor += 2;
  }
  if (parts[cursor] === 'detail') {
    const detail = id(parts[cursor + 1]);
    if (detail)
      return { pathname, search: mergeQuery(currentSearch, 'system', detail) };
  }
  return { pathname, search: currentSearch };
}

function mergeQuery(currentSearch: string, key: string, value: string): string {
  const query = new URLSearchParams(currentSearch);
  query.set(key, value);
  const result = query.toString();
  return result ? `?${result}` : '';
}

export function applyLegacyHash(
  location: Location,
  replace: (url: string) => void,
): boolean {
  const destination = legacyHashDestination(location.hash, location.search);
  if (!destination) return false;
  replace(`${destination.pathname}${destination.search}`);
  return true;
}
