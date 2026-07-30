'use strict';

// ED:Finder deliberately keeps its service worker cache-neutral. Production
// data and hashed application assets already have explicit HTTP cache policy,
// while a service-worker cache can make a deliberately manual deploy appear
// stale. This worker exists to provide a valid, cross-browser lifecycle and a
// stable upgrade path without intercepting requests.
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
