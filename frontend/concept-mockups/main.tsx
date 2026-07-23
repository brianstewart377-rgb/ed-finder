import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Reuse the canonical design-system tokens + cockpit utility classes so the
// mockups share one identity with the product. This import is read-only; the
// gallery never imports canonical routes, hooks, stores, or API modules.
import '../src/index.css';
import { ConceptGalleryApp } from '../src/concept-mockups/ConceptGalleryApp';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('#root not found in concept-mockups/index.html');

createRoot(rootEl).render(
  <StrictMode>
    <ConceptGalleryApp />
  </StrictMode>,
);
