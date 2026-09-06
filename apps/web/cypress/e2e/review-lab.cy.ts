type ReviewLabConfig = Readonly<{
  reviewLabRun: boolean;
  reviewOutputPath: string;
  reviewScenariosJson: string;
}>;

type ReviewSummary = {
  summarySchemaVersion: number;
  reviewLabRun: true;
  selectedScenarioNames: string[];
  browserFlowKeys: string[];
  scenarios: Record<
    string,
    {
      status: 'passed' | 'failed';
      checks: Record<string, boolean>;
      diagnostics?: Record<string, string>;
    }
  >;
  apiResponses: Array<{
    method: string;
    path: string;
    status: number;
    expectedFailure?: boolean;
  }>;
  externalOrigins: string[];
  consoleEntries: Array<{ type: string; text: string }>;
  pageErrors: string[];
  fatalError: string | null;
};

const REVIEW_ALPHA = { id64: '7200000000001', name: 'Review Alpha' };
const readySelector = '[role="status"][data-renderer-state="ready"]';
const selectedStorageKey = 'ed-finder:selected-system-context';
let currentFlow = '';

const clean = (value: unknown) =>
  String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 500);

const parseTrustedConfig = (raw: ReviewLabConfig) => {
  if (
    raw?.reviewLabRun !== true ||
    typeof raw.reviewOutputPath !== 'string' ||
    !raw.reviewOutputPath ||
    typeof raw.reviewScenariosJson !== 'string' ||
    !raw.reviewScenariosJson
  ) {
    throw new Error(
      'Review Lab browser verification requires the trusted Node-task handshake.',
    );
  }
  const plan = JSON.parse(raw.reviewScenariosJson) as {
    selectedScenarioNames?: unknown;
    browserFlowKeys?: unknown;
  };
  if (
    !Array.isArray(plan.selectedScenarioNames) ||
    !Array.isArray(plan.browserFlowKeys)
  ) {
    throw new Error('Review Lab scenario plan is malformed.');
  }
  return {
    outputPath: raw.reviewOutputPath,
    selectedScenarioNames: plan.selectedScenarioNames as string[],
    browserFlowKeys: plan.browserFlowKeys as string[],
  };
};

describe('isolated V3 Review Lab', () => {
  let outputPath = '';
  let summary: ReviewSummary;

  const setReviewMode = (mode: 'normal' | 'api_failure' | 'empty_results') =>
    cy
      .request('POST', `/api/review/scenario/${mode}`)
      .its('status')
      .should('eq', 200);

  before(() => {
    cy.task('getReviewLabConfig').then((raw) => {
      const config = parseTrustedConfig(raw as ReviewLabConfig);
      outputPath = config.outputPath;
      summary = {
        summarySchemaVersion: 2,
        reviewLabRun: true,
        selectedScenarioNames: config.selectedScenarioNames,
        browserFlowKeys: config.browserFlowKeys,
        scenarios: {},
        apiResponses: [],
        externalOrigins: [],
        consoleEntries: [],
        pageErrors: [],
        fatalError: null,
      };
    });
    cy.intercept({ url: '**', middleware: true }, (request) => {
      const url = new URL(request.url);
      const baseUrl = Cypress.config('baseUrl');
      if (typeof baseUrl === 'string' && url.origin !== new URL(baseUrl).origin) {
        summary.externalOrigins.push(url.origin);
      }
      if (!url.pathname.startsWith('/api/')) return;
      request.on('response', (response) => {
        summary.apiResponses.push({
          method: request.method,
          path: `${url.pathname}${url.search}`,
          status: response.statusCode,
          expectedFailure:
            response.statusCode === 503 &&
            String(response.headers['x-edfinder-review-failure'] ?? '') ===
              'api-failure',
        });
      });
    });
  });

  after(() => {
    cy.task('writeReviewLabSummary', { outputPath, summary });
  });

  it('executes only selected Review Lab synthetic edge and failure scenarios', () => {
    Cypress.once('fail', (error) => {
      summary.fatalError = clean(error.message);
      if (currentFlow) {
        summary.scenarios[currentFlow] = {
          status: 'failed',
          checks: summary.scenarios[currentFlow]?.checks ?? {},
        };
      }
      throw error;
    });

    const instrumentWindow = (window: Window) => {
      window.addEventListener('error', (event) =>
        summary.pageErrors.push(clean(event.error?.stack || event.message)),
      );
      window.addEventListener('unhandledrejection', (event) =>
        summary.pageErrors.push(clean(event.reason)),
      );
      for (const type of ['error', 'warn'] as const) {
        const browserConsole = (window as Window & { console: Console }).console;
        const original = browserConsole[type];
        browserConsole[type] = (...args: unknown[]) => {
          summary.consoleEntries.push({ type, text: clean(args.join(' ')) });
          original.apply(browserConsole, args);
        };
      }
    };

    const markPassed = (
      flow: string,
      checks: Record<string, boolean>,
      diagnostics?: Record<string, string>,
    ) => {
      summary.scenarios[flow] = { status: 'passed', checks, diagnostics };
    };

    const flows = summary.browserFlowKeys;

    if (flows.includes('syntheticWiring')) {
      currentFlow = 'syntheticWiring';
      setReviewMode('normal');
      cy.intercept('POST', '/api/local/search').as('wiringSearch');
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.wait('@wiringSearch').its('response.statusCode').should('eq', 200);
      cy.get(`[data-system-result="${REVIEW_ALPHA.id64}"]`).should(
        'contain.text',
        REVIEW_ALPHA.name,
      );
      cy.get(readySelector, { timeout: 20_000 })
        .should('be.visible')
        .then(() =>
          markPassed('syntheticWiring', {
            syntheticSystemVisible: true,
            babylonReady: true,
          }),
        );
    }

    if (flows.includes('apiFailure')) {
      currentFlow = 'apiFailure';
      setReviewMode('api_failure');
      cy.intercept('POST', '/api/local/search').as('failedSearch');
      cy.visit('/explore', {
        onBeforeLoad(window) {
          instrumentWindow(window);
          window.localStorage.setItem(selectedStorageKey, REVIEW_ALPHA.id64);
        },
      });
      cy.wait('@failedSearch').its('response.statusCode').should('eq', 503);
      cy.wait('@failedSearch').its('response.statusCode').should('eq', 503);
      cy.contains(
        '[role="alert"]',
        'Discovery results could not be loaded.',
      ).should('be.visible');
      cy.window()
        .its('localStorage')
        .invoke('getItem', selectedStorageKey)
        .should('eq', REVIEW_ALPHA.id64)
        .then(() =>
          markPassed('apiFailure', {
            failureModeActivated: true,
            errorRendered: true,
            selectionContextPreserved: true,
          }),
        );
      setReviewMode('normal');
    }

    if (flows.includes('emptyResults')) {
      currentFlow = 'emptyResults';
      setReviewMode('empty_results');
      cy.intercept('POST', '/api/local/search').as('emptySearch');
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.wait('@emptySearch').its('response.statusCode').should('eq', 200);
      cy.contains('No systems match this discovery area.').should('be.visible');
      cy.get(readySelector, { timeout: 20_000 }).should('be.visible');
      cy.get('.spatial-canvas')
        .should('have.attr', 'data-scene-target-count', '0')
        .then(() =>
          markPassed('emptyResults', {
            emptyModeActivated: true,
            emptyRendered: true,
            zeroTargetScene: true,
            babylonReady: true,
          }),
        );
      setReviewMode('normal');
    }

    if (flows.includes('rendererRecovery')) {
      currentFlow = 'rendererRecovery';
      setReviewMode('normal');
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.get(readySelector, { timeout: 20_000 })
        .should('be.visible')
        .invoke('attr', 'data-renderer-backend')
        .then((backend) => {
          cy.get<HTMLCanvasElement>('canvas[data-spatial-canvas]').then(
            ($canvas) => {
              const canvas = $canvas[0];
              let recoveryMode = 'neutral-lifecycle-fallback';
              const context =
                backend === 'WEBGL2' ? canvas.getContext('webgl2') : null;
              const extension = context?.getExtension('WEBGL_lose_context');
              if (extension) {
                const activeContext = context as WebGL2RenderingContext;
                const contextLost = new Cypress.Promise<void>((resolve) => {
                  canvas.addEventListener('webglcontextlost', () => resolve(), {
                    once: true,
                  });
                });
                const contextRestored = new Cypress.Promise<boolean>(
                  (resolve) => {
                    canvas.addEventListener(
                      'webglcontextrestored',
                      () => resolve(true),
                      { once: true },
                    );
                    window.setTimeout(() => resolve(false), 2_000);
                  },
                );
                extension.loseContext();
                cy.wrap(contextLost)
                  .then(() => {
                    expect(activeContext.isContextLost()).to.equal(true);
                  })
                  .then(() => {
                    extension.restoreContext();
                    return cy.wrap(contextRestored);
                  })
                  .then((restored) => {
                    if (!restored) {
                      recoveryMode = 'webgl-context-loss-remount-fallback';
                      cy.reload();
                      return;
                    }
                    recoveryMode = 'webgl-context-loss-and-restore';
                    expect(activeContext.isContextLost()).to.equal(false);
                  });
              } else {
                cy.reload();
              }
              cy.get(readySelector, { timeout: 20_000 }).should('be.visible');
              cy.then(() =>
                markPassed(
                  'rendererRecovery',
                  {
                    babylonReady: true,
                    rendererLifecycleExercised: true,
                    rendererRemainedUsable: true,
                    noUncaughtError: summary.pageErrors.length === 0,
                  },
                  { recoveryMode },
                ),
              );
            },
          );
        });
    }

    cy.then(() => {
      expect(
        [...new Set(summary.externalOrigins)],
        'Review Lab external resource origins',
      ).to.deep.equal([]);
    });
  });
});
