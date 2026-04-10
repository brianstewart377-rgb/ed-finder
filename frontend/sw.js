// ED:Finder Service Worker — v3.23
// Caches the app shell (HTML + key static assets) for offline access.
// API calls are always network-first so fresh data is always preferred.

const CACHE_NAME = 'ed-finder-shell-v3.23';
const SHELL_ASSETS = [
  '/',
  '/index.html',
];

// Install: pre-cache shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

// Activate: delete old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
//   - API calls (/api/*) → network only (always fresh)
//   - External CDN resources → stale-while-revalidate
//   - App shell (/, /index.html) → cache first, then network
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and cross-origin requests (except CDNs we cache)
  if (event.request.method !== 'GET') return;

  // Network-only for API
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request).catch(() => new Response('{"error":"offline"}', { headers: { 'Content-Type': 'application/json' } })));
    return;
  }

  // Cache-first for app shell
  if (SHELL_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        const networkFetch = fetch(event.request).then(response => {
          if (response.ok) {
            caches.open(CACHE_NAME).then(c => c.put(event.request, response.clone()));
          }
          return response;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
    return;
  }

  // Stale-while-revalidate for CDN assets
  if (url.hostname.includes('cdn.') || url.hostname.includes('jsdelivr') || url.hostname.includes('tailwindcss') || url.hostname.includes('fontawesome')) {
    event.respondWith(
      caches.open(CACHE_NAME).then(cache =>
        cache.match(event.request).then(cached => {
          const networkFetch = fetch(event.request).then(response => {
            if (response.ok) cache.put(event.request, response.clone());
            return response;
          }).catch(() => cached);
          return cached || networkFetch;
        })
      )
    );
  }
});
