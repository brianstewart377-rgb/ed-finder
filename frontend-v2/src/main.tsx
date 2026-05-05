import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('#root not found in index.html');
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Service worker registration. vite-plugin-pwa emits /v2/sw.js at build time;
// we register it manually here (avoids the virtual:pwa-register module which
// has a known resolution issue in some yarn-classic + vite 6 setups).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/v2/sw.js', { scope: '/v2/' })
      .then(reg => {
        // Auto-detect updates roughly every hour.
        setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
        reg.addEventListener('updatefound', () => {
          const sw = reg.installing;
          if (!sw) return;
          sw.addEventListener('statechange', () => {
            if (sw.state === 'installed' && navigator.serviceWorker.controller) {
              console.info('[ED:Finder] Update available — reload to apply.');
            }
          });
        });
        console.info('[ED:Finder] Service worker registered for /v2/.');
      })
      .catch(err => console.warn('[ED:Finder] SW registration failed:', err));
  });
}
