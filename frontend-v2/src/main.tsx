import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { registerSW } from 'virtual:pwa-register';
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

// Service worker registration. autoUpdate mode means new builds replace
// the cached bundle on next reload. We pass an `onNeedRefresh` handler so
// users can opt to refresh immediately when an update is detected — but
// keep it lightweight (a console hint) to avoid surprising prompts.
registerSW({
  immediate: true,
  onNeedRefresh: () => {
    console.info('[ED:Finder] Update available — reload to apply.');
  },
  onOfflineReady: () => {
    console.info('[ED:Finder] Ready to work offline.');
  },
});
