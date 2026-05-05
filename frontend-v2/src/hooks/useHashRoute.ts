import { useEffect, useState } from 'react';

/**
 * Tiny hash-based router. Hash routes (e.g. `/v2/#watchlist`) avoid needing
 * to teach nginx about every v2 sub-route — the SPA fallback we already
 * have for `/v2/index.html` is enough.
 *
 * For 4 tabs this is all we need; if v2 ever grows path params or nested
 * routes we'll switch to `react-router`. Premature DI = needless deps.
 */
export type Route = 'finder' | 'watchlist' | 'pinned' | 'compare' | 'map';
const VALID: Route[] = ['finder', 'watchlist', 'pinned', 'compare', 'map'];

function parseHash(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '').toLowerCase();
  return (VALID as string[]).includes(raw) ? (raw as Route) : 'finder';
}

export function useHashRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = (r: Route) => {
    window.location.hash = `#${r}`;
  };

  return [route, navigate];
}
