// Minimal no-op service worker for ED Finder
// Prevents browser console errors when index.html tries to register it
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
