export const routes = [
  'finder',
  'my-work',
  'compare',
  'map',
  'search-tuning',
  'fc',
  'colony-planner',
  'admin',
  'operator',
] as const;
export type AppRoute = (typeof routes)[number];
const aliases: Record<string, AppRoute> = {
  watchlist: 'my-work',
  pinned: 'my-work',
  colony: 'my-work',
};
const id = (value?: string) =>
  value && /^\d+$/.test(value) && BigInt(value) > 0n ? value : null;
export function legacyHashPath(hash: string): string | null {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (!parts.length) return null;
  if (parts[0] === 'system')
    return id(parts[1]) ? `/finder/system/${parts[1]}` : '/finder';
  const route =
    aliases[parts[0]] ??
    (routes.includes(parts[0] as AppRoute) ? parts[0] : 'finder');
  const suffix = parts.slice(1).join('/');
  return `/${route}${suffix ? `/${suffix}` : ''}`;
}
export function routeFromPath(pathname: string) {
  const parts = pathname.split('/').filter(Boolean);
  const first = aliases[parts[0]] ?? parts[0] ?? 'finder';
  return {
    route: (routes.includes(first as AppRoute) ? first : 'finder') as AppRoute,
    parts,
    alias: aliases[parts[0]] ? parts[0] : null,
  };
}
