import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('#root not found in index.html');
}
const root = createRoot(rootEl);

// ────────────────────────────────────────────────────────────────────────────
// Feature flag: ?ui=v3  or  localStorage.uiV3 = "1"  →  load the redesign.
//
// The redesign is a parallel shell living in src/_redesign/. It is dynamically
// imported so its bundle (and its global CSS reset in redesign.css) never
// reaches users who haven't opted in. Default users keep getting the existing
// v2 experience exactly as before — zero behaviour change for them.
//
// To opt in:
//   • visit any page with `?ui=v3` (one-shot URL preview), or
//   • run `localStorage.setItem('uiV3', '1')` in devtools (sticky preview),
//     reload to apply.
//
// To turn it off: `?ui=v2` (one-shot) or
//   `localStorage.removeItem('uiV3')` and reload.
// ────────────────────────────────────────────────────────────────────────────
function shouldUseRedesign(): boolean {
  const params = new URLSearchParams(window.location.search);
  const q = params.get('ui');
  if (q === 'v3') {
    localStorage.setItem('uiV3', '1');
    return true;
  }
  if (q === 'v2') {
    localStorage.removeItem('uiV3');
    return false;
  }
  return localStorage.getItem('uiV3') === '1';
}

async function bootstrap() {
  if (shouldUseRedesign()) {
    const { default: RedesignApp } = await import('./_redesign/RedesignApp.jsx');
    root.render(
      <StrictMode>
        <RedesignApp />
      </StrictMode>,
    );
  } else {
    await import('./index.css');
    const { default: App } = await import('./App');
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  }
}

void bootstrap();

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
