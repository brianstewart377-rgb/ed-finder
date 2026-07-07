import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from './components/ErrorBoundary';

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('#root not found in index.html');
}
const root = createRoot(rootEl);

const REDESIGN_PREVIEW_KEY = 'uiPreview';

// The redesign remains an opt-in preview shell with a single current flag
// contract so old rollout naming no longer leaks into active code paths.
function shouldUseRedesign(): boolean {
  const params = new URLSearchParams(window.location.search);
  const q = params.get('ui');
  if (q === 'preview') {
    localStorage.setItem(REDESIGN_PREVIEW_KEY, '1');
    return true;
  }
  if (q === 'live') {
    localStorage.removeItem(REDESIGN_PREVIEW_KEY);
    return false;
  }
  return localStorage.getItem(REDESIGN_PREVIEW_KEY) === '1';
}

async function bootstrap() {
  if (shouldUseRedesign()) {
    const { default: RedesignApp } = await import('./_redesign/RedesignApp.jsx');
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <RedesignApp />
        </ErrorBoundary>
      </StrictMode>,
    );
  } else {
    await import('./index.css');
    const { default: App } = await import('./App');
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </StrictMode>,
    );
  }
}

void bootstrap();

function normaliseBase(base: string): string {
  if (!base || base === '/') return '/';
  return base.endsWith('/') ? base : `${base}/`;
}

// Service worker registration. The build emits `sw.js` under the app base; we
// register it manually here (avoids the virtual:pwa-register module which has
// a known resolution issue in some yarn-classic + vite 6 setups).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    const scope = normaliseBase(import.meta.env.BASE_URL || '/');
    const swUrl = new URL(`.${scope}sw.js`, window.location.origin).pathname;
    navigator.serviceWorker
      .register(swUrl, { scope })
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
        console.info(`[ED:Finder] Service worker registered for ${scope}.`);
      })
      .catch(err => console.warn('[ED:Finder] SW registration failed:', err));
  });
}
