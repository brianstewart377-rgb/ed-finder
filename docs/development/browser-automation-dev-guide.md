# Browser Automation Development Guide

Cypress is the repository's only active browser automation framework. The
Python Review Lab remains the acceptance/evaluation owner; Cypress is its
browser driver. Historical Stage 26 browser receipts remain evidence, but the
old executable harnesses are not current commands.

## Local use

Start the disposable local API and frontend preview described by the root
README, then run:

```bash
cd frontend
yarn e2e             # strict Chrome release gate
yarn e2e:firefox     # strict Firefox release gate
yarn e2e:open        # interactive Cypress runner
```

CI runs the strict suite with zero retries in both Chrome and Firefox. The
release journey, owner/auth boundary, renderer synchronization telemetry and
WCAG axe scan live under `frontend/cypress/e2e/`.

## Screenshots and visual baselines

The release-gate suite fixes its viewport and clock, disables animation and
transition noise, and captures `release-gate/home-1280x720`. Cypress writes
screenshots, videos, and downloads under `frontend/cypress/artifacts/`; CI
uploads that directory on every run. New visual checks should likewise fix the
viewport and time, wait for observable readiness, suppress animation, and use a
stable screenshot name so an accepted artifact can be compared across runs.

## Adding browser coverage

Add `*.cy.js` specs under `frontend/cypress/e2e/` and shared commands under
`frontend/cypress/support/e2e.js`. Use `cy.intercept()` with bounded responses
for failure paths. Do not introduce unbounded promises or retries that can turn
a failed release journey green. Use `cy.injectAxe()` and `cy.checkA11y()` for
new accessibility surfaces.

Never point local browser automation at production or load production
credentials. Browser tests use disposable local/CI services only.
