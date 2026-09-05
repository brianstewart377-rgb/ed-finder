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
  accessibility: Record<string, boolean>;
  apiResponses: Array<{
    method: string;
    path: string;
    status: number;
    expectedFailure?: boolean;
  }>;
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

  before(() => {
    cy.task('getReviewLabConfig').then((raw) => {
      const config = parseTrustedConfig(raw as ReviewLabConfig);
      outputPath = config.outputPath;
      summary = {
        summarySchemaVersion: 1,
        reviewLabRun: true,
        selectedScenarioNames: config.selectedScenarioNames,
        browserFlowKeys: config.browserFlowKeys,
        scenarios: {},
        accessibility: {},
        apiResponses: [],
        consoleEntries: [],
        pageErrors: [],
        fatalError: null,
      };
    });
    cy.intercept({ url: '**/api/**', middleware: true }, (request) => {
      request.on('response', (response) => {
        const url = new URL(request.url);
        summary.apiResponses.push({
          method: request.method,
          path: `${url.pathname}${url.search}`,
          status: response.statusCode,
          expectedFailure:
            currentFlow === 'apiFailure' && response.statusCode === 503,
        });
      });
    });
  });

  after(() => {
    cy.task('writeReviewLabSummary', { outputPath, summary });
  });

  it('executes only the selected synthetic V3 scenarios', () => {
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
        const browserConsole = (window as Window & { console: Console })
          .console;
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
    if (flows.includes('exploreInspect')) {
      currentFlow = 'exploreInspect';
      cy.intercept('POST', '/api/local/search').as('reviewSearch');
      cy.intercept('GET', '/api/local/autocomplete*').as('reviewAutocomplete');
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.wait('@reviewSearch').its('response.statusCode').should('eq', 200);
      cy.get('h1').should('contain.text', 'Chart a promising system');
      cy.get(`[data-system-result="${REVIEW_ALPHA.id64}"]`).should(
        'contain.text',
        REVIEW_ALPHA.name,
      );
      cy.get(readySelector, { timeout: 20_000 }).should('be.visible');
      cy.get('#system-search').clear().type('Review Al');
      cy.wait('@reviewAutocomplete')
        .its('response.statusCode')
        .should('eq', 200);
      cy.get('#system-search').type('{downArrow}{enter}');
      summary.accessibility.keyboardTypeaheadWorks = true;
      cy.get(`[data-system-result="${REVIEW_ALPHA.id64}"] [data-result-select]`)
        .should('be.focused')
        .and('have.attr', 'aria-pressed', 'true');
      cy.get(
        `[data-system-result="${REVIEW_ALPHA.id64}"] .inspect-link`,
      ).click();
      cy.location('pathname').should('eq', '/inspect');
      cy.location('search').should('eq', `?system=${REVIEW_ALPHA.id64}`);
      cy.get(`[data-system-id64="${REVIEW_ALPHA.id64}"]`)
        .should('contain.text', REVIEW_ALPHA.name)
        .and('contain.text', REVIEW_ALPHA.id64)
        .then(() =>
          markPassed('exploreInspect', {
            exploreLoaded: true,
            syntheticSystemVisible: true,
            babylonReady: true,
            inspectLoaded: true,
            exactId64Preserved: true,
          }),
        );
    }

    if (flows.includes('apiFailure')) {
      currentFlow = 'apiFailure';
      cy.intercept(
        { method: 'POST', url: '/api/local/search', times: 2 },
        {
          statusCode: 503,
          headers: { 'content-type': 'application/problem+json' },
          body: {
            type: 'https://ed-finder.invalid/problem/review-lab-search-failure',
            title: 'Synthetic Review Lab search failure',
            status: 503,
          },
        },
      ).as('failedSearch');
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
            failureInjected: true,
            errorRendered: true,
            selectionContextPreserved: true,
          }),
        );
    }

    if (flows.includes('emptyResults')) {
      currentFlow = 'emptyResults';
      cy.intercept(
        { method: 'POST', url: '/api/local/search', times: 1 },
        {
          statusCode: 200,
          body: {
            results: [],
            total: 0,
            count: 0,
            source: 'review_lab_synthetic_empty',
          },
        },
      ).as('emptySearch');
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.wait('@emptySearch').its('response.statusCode').should('eq', 200);
      cy.contains('No systems match this discovery area.').should('be.visible');
      cy.get(readySelector, { timeout: 20_000 }).should('be.visible');
      cy.get('.spatial-canvas')
        .should('have.attr', 'data-scene-target-count', '0')
        .then(() =>
          markPassed('emptyResults', {
            emptyInjected: true,
            emptyRendered: true,
            zeroTargetScene: true,
            babylonReady: true,
          }),
        );
    }

    if (flows.includes('rendererRecovery')) {
      currentFlow = 'rendererRecovery';
      cy.visit('/explore', { onBeforeLoad: instrumentWindow });
      cy.get(readySelector, { timeout: 20_000 })
        .should('be.visible')
        .invoke('attr', 'data-renderer-backend')
        .then((backend) => {
          cy.get<HTMLCanvasElement>('canvas[data-spatial-canvas]').then(
            ($canvas) => {
              const canvas = $canvas[0];
              const context =
                backend === 'WEBGL2' ? canvas.getContext('webgl2') : null;
              const extension = context?.getExtension('WEBGL_lose_context');
              if (extension) {
                const activeContext = context as WebGL2RenderingContext;
                extension.loseContext();
                cy.wrap(null)
                  .should(() =>
                    expect(activeContext.isContextLost()).to.equal(true),
                  )
                  .then(() => {
                    extension.restoreContext();
                    cy.wrap(null).should(() =>
                      expect(activeContext.isContextLost()).to.equal(false),
                    );
                  });
              } else {
                cy.viewport(960, 680);
                cy.get('canvas[data-spatial-canvas]')
                  .invoke('attr', 'data-resize-revision')
                  .then((revision) =>
                    expect(Number(revision)).to.be.greaterThan(0),
                  );
              }
              cy.get(readySelector).should('be.visible');
              cy.then(() =>
                markPassed(
                  'rendererRecovery',
                  {
                    babylonReady: true,
                    rendererLifecycleExercised: true,
                    rendererRemainedUsable: true,
                    noUncaughtError: summary.pageErrors.length === 0,
                  },
                  {
                    recoveryMode: extension
                      ? 'webgl-context-loss-and-restore'
                      : 'neutral-resize-lifecycle-fallback',
                  },
                ),
              );
            },
          );
        });
    }

    if (flows.includes('navigationContainment')) {
      currentFlow = 'navigationContainment';
      cy.visit(`/inspect?system=${REVIEW_ALPHA.id64}`, {
        onBeforeLoad: instrumentWindow,
      });
      cy.get(`[data-system-id64="${REVIEW_ALPHA.id64}"] h1`)
        .should('contain.text', REVIEW_ALPHA.name)
        .and('be.focused');
      summary.accessibility.inspectHeadingFocused = true;
      cy.contains('a', 'Back to Explore').click();
      cy.location('pathname').should('eq', '/explore');
      cy.window().then((window) => {
        const external = window.performance
          .getEntriesByType('resource')
          .map((entry) => new URL(entry.name))
          .filter((url) => url.origin !== window.location.origin);
        expect(external, 'external resource requests').to.deep.equal([]);
        markPassed('navigationContainment', {
          directInspectLoaded: true,
          headingFocused: true,
          returnedToExplore: true,
          sameOriginOnly: true,
        });
      });
    }
  });
});
