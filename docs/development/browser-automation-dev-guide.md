# Browser Automation Development Guide

Cypress is ED-Finder's browser automation authority. The runnable harness covers
Chromium-family browsers and Firefox. WebKit is explicitly retired; retained
Stage 26 documents and receipts describe historical runs only.

## Interactive development

Start the disposable local services and frontend, then open Cypress:

```bash
make dev
make dev-test
```

Select a spec in the Cypress UI to inspect DOM state, network traffic, command
history, screenshots, and failures. To run the protected-style Chrome suite
headlessly with failure video and screenshots:

```bash
cd frontend
yarn e2e
```

Run the Firefox browser class separately:

```bash
cd frontend
yarn e2e:firefox
```

The browser binary can be checked after dependency installation with
`yarn exec cypress verify`.

## Writing tests

Browser specs live in `frontend/cypress/e2e/`; shared commands live in
`frontend/cypress/support/e2e.js`. Prefer stable accessible selectors or
`data-testid` through `cy.getByTestId()`. Stub only the bounded API calls the
scenario owns, and assert user-visible state rather than implementation timing.

Accessibility checks use `cypress-axe`:

```javascript
cy.injectAxe();
cy.checkA11y(null, {
  runOnly: {
    type: 'tag',
    values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'],
  },
});
```

Deterministic visual evidence uses a fixed viewport and the shared command,
which disables animation, transitions, and carets before capture:

```javascript
cy.viewport(1280, 720);
cy.captureDeterministicBaseline('feature-1280x720', {
  blackout: ['canvas'],
});
```

Blackout only content that is inherently non-deterministic and is covered by a
separate assertion. Cypress writes screenshots and videos below
`frontend/cypress/artifacts/`; CI uploads those paths on failure.

## Troubleshooting

- If the page cannot load, verify the disposable API health endpoint and the
  Vite preview URL configured in `frontend/cypress.config.cjs`.
- If a canvas assertion fails, use `cy.assertCanvasSynced()` and inspect the
  captured video for resize or context-loss evidence.
- If axe reports a violation, keep the rule and DOM target in the failure
  output; do not suppress it without a reviewed accessibility disposition.
- If screenshots vary, remove clock/random data through scenario fixtures and
  wait for an observable stable state before capture.
