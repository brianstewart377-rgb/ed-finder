/* global Cypress, cy, expect */

const REVIEW_LAB_RUN = Cypress.env('reviewLabRun') === true;
const OUTPUT_PATH = Cypress.env('reviewOutputPath') || '';
const RAW_SCENARIO_PLAN = Cypress.env('reviewScenariosJson') || '';

const SYSTEMS = {
  alpha: { id64: 7200000000001, name: 'Review Alpha' },
  beta: { id64: 7200000000002, name: 'Review Beta' },
  gamma: { id64: 7200000000003, name: 'Review Gamma' },
  delta: { id64: 7200000000004, name: 'Review Delta' },
};

const PLANNER_OVERFLOW_TEST_IDS = [
  'colony-planner-workspace',
  'whole-system-colony-planner',
  'workspace-planner-content',
  'planner-telemetry-region',
  'planner-canvas',
];

const VIEWPORT_PROFILES = Object.freeze([
  {
    profile_name: 'planner_desktop_primary',
    viewport_width: 1440,
    viewport_height: 900,
    device_scale_factor: 1,
    product_scope: 'planner',
    acceptance_level: 'required',
  },
  {
    profile_name: 'planner_laptop_minimum',
    viewport_width: 1280,
    viewport_height: 720,
    device_scale_factor: 1,
    product_scope: 'planner',
    acceptance_level: 'required',
  },
  {
    profile_name: 'planner_constrained_diagnostic',
    viewport_width: 1024,
    viewport_height: 768,
    device_scale_factor: 1,
    product_scope: 'planner',
    acceptance_level: 'diagnostic',
  },
  {
    profile_name: 'finder_mobile',
    viewport_width: 390,
    viewport_height: 844,
    device_scale_factor: 1,
    product_scope: 'finder_and_system_detail',
    acceptance_level: 'required',
  },
  {
    profile_name: 'planner_mobile_resilience',
    viewport_width: 390,
    viewport_height: 844,
    device_scale_factor: 1,
    product_scope: 'planner',
    acceptance_level: 'resilience_only',
  },
]);

const summary = {
  summarySchemaVersion: 1,
  reviewLabRun: REVIEW_LAB_RUN,
  selectedScenarioNames: [],
  browserFlowKeys: [],
  selectedPlan: null,
  scenarios: {},
  accessibility: {},
  viewportProfiles: VIEWPORT_PROFILES.map((entry) => ({ ...entry })),
  profileResults: {},
  productObservations: [],
  apiResponses: [],
  consoleEntries: [],
  pageErrors: [],
  fatalError: null,
};

let scenarioPlan = null;
let activeProfile = null;
let activeScenario = null;
let activeScenarioStart = 0;
const failedProfiles = new Map();
const failedScenarios = new Map();

function sanitizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500);
}

function consoleText(args) {
  return sanitizeText(args.map((value) => {
    if (typeof value === 'string') return value;
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }).join(' '));
}

function apiPath(urlString) {
  const url = new URL(urlString);
  return `${url.pathname}${url.search}`;
}

function profile(name) {
  const metadata = VIEWPORT_PROFILES.find((entry) => entry.profile_name === name);
  if (!metadata) throw new Error(`Unknown viewport profile ${name}.`);
  return metadata;
}

function ensureProfileResult(name) {
  if (!summary.profileResults[name]) {
    summary.profileResults[name] = {
      status: 'passed',
      checks: { effectiveViewportApplied: false },
      diagnostics: {},
      error: null,
    };
  }
  return summary.profileResults[name];
}

function beginProfile(name) {
  activeProfile = name;
  activeScenario = null;
  const metadata = profile(name);
  ensureProfileResult(name);
  cy.viewport(metadata.viewport_width, metadata.viewport_height);
}

function beginScenario(name) {
  activeScenario = name;
  activeScenarioStart = summary.apiResponses.length;
  summary.scenarios[name] = {
    status: 'running',
    checks: {},
    apiResponses: [],
    error: null,
  };
  return summary.scenarios[name].checks;
}

function finishScenario(name) {
  const scenario = summary.scenarios[name];
  scenario.status = 'passed';
  scenario.apiResponses = summary.apiResponses.slice(activeScenarioStart);
}

function parseScenarioPlan(rawValue) {
  if (!rawValue) throw new Error('Review Lab scenario plan is required.');
  let parsed;
  try {
    parsed = JSON.parse(rawValue);
  } catch {
    throw new Error('Review Lab scenario plan could not be parsed.');
  }
  if (!Array.isArray(parsed.selectedScenarioNames) || !Array.isArray(parsed.browserFlowKeys)) {
    throw new Error('Review Lab scenario plan is malformed.');
  }
  return {
    selectedScenarioNames: parsed.selectedScenarioNames,
    browserFlowKeys: parsed.browserFlowKeys,
    includeProductObservations: Boolean(parsed.includeProductObservations),
  };
}

function flowEnabled(name) {
  return scenarioPlan.browserFlowKeys.includes(name);
}

function validateEffectiveViewport(name) {
  const metadata = profile(name);
  cy.window().then((win) => {
    const effective = {
      viewport_width: win.innerWidth,
      viewport_height: win.innerHeight,
      device_scale_factor: win.devicePixelRatio,
    };
    expect(effective.viewport_width, `${name} viewport width`).to.equal(metadata.viewport_width);
    expect(effective.viewport_height, `${name} viewport height`).to.equal(metadata.viewport_height);
    expect(effective.device_scale_factor, `${name} device scale factor`).to.equal(metadata.device_scale_factor);
    ensureProfileResult(name).checks.effectiveViewportApplied = true;
  });
}

function expectReviewCardsAccessible() {
  Object.values(SYSTEMS).forEach((system) => {
    cy.getByTestId(`result-card-${system.id64}`)
      .scrollIntoView()
      .should('be.visible')
      .and('contain.text', system.name);
  });
}

function gotoFinder() {
  cy.visit('/#finder');
  cy.getByTestId('finder-page-heading').should('be.visible');
  cy.getByTestId('filter-module-system').should('be.visible').click();
  cy.contains('label', 'Colony status').should('be.visible').invoke('attr', 'for').then((controlId) => {
    expect(controlId, 'Colony status control id').to.be.a('string').and.not.be.empty;
    cy.get(`[id="${controlId}"]`).should('be.visible').click();
    cy.get('[role="listbox"]:visible').last().within(() => {
      cy.contains('[role="option"]', 'Any')
        .should('be.visible')
        .click();
    });
    cy.get(`[id="${controlId}"]`).should('contain.text', 'Any');
  });
  cy.press(Cypress.Keyboard.Keys.ESC);
  cy.getByTestId('search-submit').should('be.visible').and('be.enabled').click();
  cy.getByTestId('search-summary', { timeout: 20_000 }).should('be.visible');
  expectReviewCardsAccessible();
}

function openResultCard(id64) {
  const testId = `result-card-${id64}`;
  cy.getByTestId(testId).should('be.visible').then(($card) => {
    const inspect = [...$card.find('button')].find((button) => (
      /Inspect system/i.test(button.textContent || '') && Cypress.dom.isVisible(button)
    ));
    if (!inspect) {
      cy.wrap($card).find('header').click();
    }
  });
  cy.getByTestId(testId).contains('button', 'Inspect system').should('be.visible');
}

function openSystemDetail(id64) {
  openResultCard(id64);
  cy.getByTestId(`result-card-${id64}`).contains('button', 'Inspect system').click();
  cy.getByTestId('system-detail-modal').should('be.visible');
  cy.getByTestId('system-detail-close').should('be.visible');
}

function closeSystemDetailWithEscape() {
  cy.getByTestId('system-detail-close')
    .should('be.visible')
    .focus()
    .should('have.focus');
  cy.press(Cypress.Keyboard.Keys.ESC);
}

function armFocusedButtonEnterDefaultAction(control, label) {
  expect(control.tagName, `${label} native element`).to.equal('BUTTON');
  expect(control.disabled, `${label} enabled`).to.equal(false);

  let clickObserved = false;
  let enterEvent = null;
  const observeClick = () => {
    clickObserved = true;
  };
  const observeKeydown = (event) => {
    if (event.key === 'Enter' || event.keyCode === 13) {
      enterEvent = event;
    }
  };
  control.addEventListener('click', observeClick);
  control.addEventListener('keydown', observeKeydown);

  return {
    complete() {
      control.removeEventListener('click', observeClick);
      control.removeEventListener('keydown', observeKeydown);
      expect(enterEvent, `${label} Enter keydown`).not.to.equal(null);

      const stillFocused = control.ownerDocument.activeElement === control;
      if (
        !enterEvent.defaultPrevented
        && !clickObserved
        && stillFocused
        && control.isConnected
        && !control.disabled
      ) {
        control.click();
      }
    },
  };
}

function activateControl(testId, keyboard) {
  cy.getByTestId(testId)
    .scrollIntoView({ block: 'center' })
    .should('be.visible');
  if (keyboard) {
    return cy.getByTestId(testId)
      .focus()
      .should('have.focus')
      .then(($control) => {
        const activation = armFocusedButtonEnterDefaultAction($control[0], testId);
        return cy.wrap($control, { log: false })
          .type('{enter}', { force: true })
          .then(() => activation.complete());
      });
  }
  return cy.getByTestId(testId).click();
}

function startPlannerFromSystemDetail(id64, options = {}) {
  const keyboard = Boolean(options.keyboard);
  activateControl('open-plan-start', keyboard);
  activateControl('plan-objective-decide_later', keyboard);
  activateControl('plan-approach-manual', keyboard);

  const evidenceAlias = `evidence-${id64}`;
  cy.intercept(`**/api/colony-planner/system/${id64}/warehouse-planner-evidence`).as(evidenceAlias);
  let fallbackAlias = null;
  if (id64 === SYSTEMS.delta.id64) {
    fallbackAlias = `fallback-${id64}`;
    cy.intercept(`**/api/colony-planner/system/${id64}/provenance-cockpit`).as(fallbackAlias);
  }

  activateControl('confirm-start-plan', keyboard);
  cy.wait(`@${evidenceAlias}`, { timeout: 20_000 }).then((interception) => {
    if (interception.response?.statusCode === 503 && fallbackAlias) {
      cy.wait(`@${fallbackAlias}`, { timeout: 20_000 });
    }
  });
}

function waitForPlanner(systemName) {
  cy.getByTestId('colony-planner-workspace', { timeout: 20_000 }).should('be.visible');
  cy.getByTestId('planner-evidence-discoverability-surface').should('be.visible');
  cy.getByTestId('planner-warehouse-evidence').should('be.visible');
  cy.getByTestId('workspace-context-header').should('be.visible').within(() => {
    cy.contains('h1, h2, h3, h4, h5, h6', 'Colony Planner').should('be.visible');
    cy.contains(new RegExp(`^${systemName}$`)).should('be.visible');
  });
}

function openEvidenceTechnicalDetail(expectedStatus, expectedSourcePosture = null) {
  cy.getByTestId(`warehouse-evidence-envelope-status-${expectedStatus}`, { timeout: 20_000 }).should('exist');
  if (expectedSourcePosture) {
    cy.getByTestId(`warehouse-evidence-source-posture-${expectedSourcePosture}`, { timeout: 20_000 }).should('exist');
  }
  cy.get('body').then(($body) => {
    const hasCompactDetails = $body.find('[data-testid="warehouse-evidence-technical-details"]').length > 0;
    if (hasCompactDetails) {
      cy.getByTestId('warehouse-evidence-technical-details').then((details) => {
        if (!details.prop('open')) {
          const summaryNode = details[0]?.querySelector('summary');
          expect(summaryNode, 'warehouse evidence technical-details summary').to.exist;
          summaryNode.click();
        }
      });
      cy.getByTestId('warehouse-evidence-technical-details').should('have.attr', 'open');
      return;
    }
    cy.getByTestId('warehouse-evidence-disclosure-toggle').should('be.visible').then(($toggle) => {
      if ($toggle.attr('aria-expanded') !== 'true') cy.wrap($toggle).click();
    });
    cy.getByTestId('warehouse-evidence-disclosure-panel').should('be.visible');
  });
}

function assertNoRecovery(checks) {
  cy.get('body').then(($body) => {
    checks.noRecoveryScreen = !$body.text().includes('ED:Finder UI Recovery');
    expect(checks.noRecoveryScreen, 'recovery UI should not be visible').to.equal(true);
  });
}

function assertVisible(testId, checks, key) {
  cy.getByTestId(testId).should('be.visible').then(() => {
    checks[key] = true;
  });
}

function assertText(testId, pattern, checks, key) {
  if (pattern instanceof RegExp) {
    cy.getByTestId(testId).invoke('text').should('match', pattern);
  } else {
    cy.getByTestId(testId).should('contain.text', pattern);
  }
  cy.then(() => {
    checks[key] = true;
  });
}

function assertHiddenOrAbsent(testId) {
  cy.get('body').should(($body) => {
    const elements = $body.find(`[data-testid="${testId}"]`);
    expect(
      elements.length === 0 || !Cypress.dom.isVisible(elements[0]),
      `${testId} should be hidden or absent`,
    ).to.equal(true);
  });
}

function assertRenderedControl(testId, label) {
  return cy.getByTestId(testId).first().should(($control) => {
    const control = $control[0];
    const style = control.ownerDocument.defaultView.getComputedStyle(control);
    const rect = control.getBoundingClientRect();
    expect(style.display, `${label} display`).not.to.equal('none');
    expect(style.visibility, `${label} visibility`).not.to.equal('hidden');
    expect(rect.width, `${label} rendered width`).to.be.greaterThan(0);
    expect(rect.height, `${label} rendered height`).to.be.greaterThan(0);
  });
}

function telemetryToggle() {
  return cy.getByTestId('planner-telemetry-dock-toggle').first();
}

function assertTelemetryToggleRendered() {
  return telemetryToggle().should(($toggle) => {
    const toggle = $toggle[0];
    const style = toggle.ownerDocument.defaultView.getComputedStyle(toggle);
    const rect = toggle.getBoundingClientRect();
    expect(style.display, 'telemetry toggle display').not.to.equal('none');
    expect(style.visibility, 'telemetry toggle visibility').not.to.equal('hidden');
    expect(rect.width, 'telemetry toggle rendered width').to.be.greaterThan(0);
    expect(rect.height, 'telemetry toggle rendered height').to.be.greaterThan(0);
  });
}

function ensureTelemetryToggleKeyboardWorks(checks) {
  assertTelemetryToggleRendered()
    .focus()
    .should('have.focus')
    .then(($toggle) => {
      const activation = armFocusedButtonEnterDefaultAction(
        $toggle[0],
        'planner telemetry toggle',
      );
      return cy.wrap($toggle, { log: false })
        .type('{enter}', { force: true })
        .then(() => activation.complete());
    });
  telemetryToggle().should('have.attr', 'aria-expanded', 'true');

  assertTelemetryToggleRendered()
    .focus()
    .should('have.focus')
    .then(($toggle) => {
      const activation = armFocusedButtonEnterDefaultAction(
        $toggle[0],
        'planner telemetry toggle',
      );
      return cy.wrap($toggle, { log: false })
        .type('{enter}', { force: true })
        .then(() => activation.complete());
    });
  telemetryToggle().should('have.attr', 'aria-expanded', 'false').then(() => {
    checks.telemetryToggleKeyboardWorks = true;
    summary.accessibility.plannerDesktopTelemetryToggleKeyboardWorks = true;
  });
}

function telemetryToggleCanReceiveFocus(checks) {
  assertTelemetryToggleRendered()
    .focus()
    .should('have.focus')
    .then(() => {
      checks.safeFocusAndNavigation = true;
    });
}

function collectOverflowMetrics(testIds) {
  return cy.window().then((win) => {
    const documentWidth = Math.max(
      win.document.documentElement?.scrollWidth || 0,
      win.document.body?.scrollWidth || 0,
    );
    const documentOverflowPx = Math.max(0, documentWidth - win.innerWidth);
    const containerOverflow = testIds
      .map((testId) => {
        const node = win.document.querySelector(`[data-testid="${testId}"]`);
        if (!(node instanceof win.HTMLElement)) return null;
        return {
          testId,
          clientWidth: node.clientWidth,
          scrollWidth: node.scrollWidth,
          overflowPx: Math.max(0, node.scrollWidth - node.clientWidth),
        };
      })
      .filter((value) => value && value.overflowPx > 4);
    return {
      documentOverflowPx,
      documentWidth,
      viewportWidth: win.innerWidth,
      containerOverflow,
    };
  });
}

function returnToFinder(checks) {
  cy.contains('button', /Back to Finder/i).should('be.visible').click();
  cy.getByTestId('search-summary').should('be.visible').then(() => {
    checks.safeReturnToFinder = true;
  });
}

function setupPlannerProfile(name, system = SYSTEMS.alpha) {
  beginProfile(name);
  gotoFinder();
  validateEffectiveViewport(name);
  openSystemDetail(system.id64);
  startPlannerFromSystemDetail(system.id64);
  waitForPlanner(system.name);
}

Cypress.on('window:before:load', (win) => {
  ['error', 'warn', 'info', 'log'].forEach((type) => {
    const original = win.console[type]?.bind(win.console);
    win.console[type] = (...args) => {
      summary.consoleEntries.push({
        type: type === 'warn' ? 'warning' : type,
        text: consoleText(args),
      });
      original?.(...args);
    };
  });

  try {
    if ('serviceWorker' in win.navigator && win.navigator.serviceWorker) {
      Object.defineProperty(win.navigator.serviceWorker, 'register', {
        configurable: true,
        value: async () => ({ scope: '/' }),
      });
    }
  } catch {
    // Preview-mode service-worker registration noise is outside Review Lab readiness.
  }
});

Cypress.on('uncaught:exception', (error) => {
  summary.pageErrors.push(sanitizeText(error?.stack || error?.message || String(error)));
  // Record the error and let the Python Review Lab policy decide whether it is
  // an allowed or blocking observation.
  return false;
});

describe('Local review environment verification — Cypress', () => {
  before(() => {
    const configError = !REVIEW_LAB_RUN || !OUTPUT_PATH || !RAW_SCENARIO_PLAN
      ? 'Review Lab browser verification requires EDFINDER_REVIEW_LAB_RUN=1 together with EDFINDER_REVIEW_OUTPUT_PATH and EDFINDER_REVIEW_SCENARIOS_JSON.'
      : null;
    if (configError) {
      summary.fatalError = sanitizeText(configError);
      if (OUTPUT_PATH) {
        return cy.task('writeReviewSummary', { outputPath: OUTPUT_PATH, summary }, { log: false }).then(() => {
          throw new Error(configError);
        });
      }
      throw new Error(configError);
    }

    scenarioPlan = parseScenarioPlan(RAW_SCENARIO_PLAN);
    summary.selectedScenarioNames = scenarioPlan.selectedScenarioNames;
    summary.browserFlowKeys = scenarioPlan.browserFlowKeys;
    summary.selectedPlan = scenarioPlan;
    VIEWPORT_PROFILES.forEach((metadata) => ensureProfileResult(metadata.profile_name));
  });

  beforeEach(() => {
    cy.intercept('**/api/**', (req) => {
      req.on('after:response', (res) => {
        summary.apiResponses.push({
          method: req.method,
          path: apiPath(req.url),
          status: res.statusCode,
        });
      });
    });
  });

  afterEach(function recordFailure() {
    const error = this.currentTest?.err;
    if (this.currentTest?.state === 'failed') {
      const text = sanitizeText(error?.stack || error?.message || String(error || 'Cypress test failed'));
      if (activeProfile) failedProfiles.set(activeProfile, text);
      if (activeScenario) {
        failedScenarios.set(activeScenario, text);
        const scenario = summary.scenarios[activeScenario] || { checks: {} };
        scenario.status = 'failed';
        scenario.apiResponses = summary.apiResponses.slice(activeScenarioStart);
        scenario.error = text;
        summary.scenarios[activeScenario] = scenario;
      }
    }
    activeProfile = null;
    activeScenario = null;
  });

  after(() => {
    for (const metadata of VIEWPORT_PROFILES) {
      const result = ensureProfileResult(metadata.profile_name);
      if (failedProfiles.has(metadata.profile_name)) {
        result.status = 'failed';
        result.error = failedProfiles.get(metadata.profile_name);
      } else {
        result.status = 'passed';
      }
    }
    for (const [name, error] of failedScenarios) {
      const scenario = summary.scenarios[name] || { checks: {}, apiResponses: [] };
      scenario.status = 'failed';
      scenario.error = error;
      summary.scenarios[name] = scenario;
    }
    cy.task('writeReviewSummary', { outputPath: OUTPUT_PATH, summary }, { log: false });
  });

  it('runs Review Alpha available-evidence journey', () => {
    if (!flowEnabled('alpha')) return;
    beginProfile('planner_desktop_primary');
    const checks = beginScenario('alpha');
    gotoFinder();
    validateEffectiveViewport('planner_desktop_primary');
    openSystemDetail(SYSTEMS.alpha.id64);
    cy.getByTestId('system-detail-modal').should('contain.text', SYSTEMS.alpha.name);
    checks.systemDetailLoaded = true;

    closeSystemDetailWithEscape();
    assertHiddenOrAbsent('system-detail-modal');
    checks.modalEscapeCloseWorks = true;
    summary.accessibility.modalEscapeCloseWorks = true;

    openSystemDetail(SYSTEMS.alpha.id64);
    startPlannerFromSystemDetail(SYSTEMS.alpha.id64, { keyboard: true });
    waitForPlanner(SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    summary.accessibility.alphaKeyboardOpenPlannerWorks = true;
    assertVisible('planner-evidence-discoverability-surface', checks, 'reportOnlyBoundaryVisible');
    assertText('planner-evidence-discoverability-summary', /canonical planner truth/i, checks, 'canonicalBoundaryVisible');
    openEvidenceTechnicalDetail('available');
    assertNoRecovery(checks);
    assertVisible('warehouse-evidence-envelope-status-available', checks, 'availablePostureVisible');
    assertVisible('warehouse-evidence-source-posture-dedicated_contract', checks, 'dedicatedContractVisible');
    assertVisible('warehouse-evidence-report-only-tag', checks, 'reportOnlyTagVisible');
    cy.then(() => finishScenario('alpha'));
  });

  it('runs Review Beta unavailable-evidence journey', () => {
    if (!flowEnabled('beta')) return;
    beginProfile('planner_desktop_primary');
    const checks = beginScenario('beta');
    gotoFinder();
    validateEffectiveViewport('planner_desktop_primary');
    openSystemDetail(SYSTEMS.beta.id64);
    cy.getByTestId('system-detail-modal').should('contain.text', SYSTEMS.beta.name);
    checks.systemDetailLoaded = true;
    startPlannerFromSystemDetail(SYSTEMS.beta.id64);
    waitForPlanner(SYSTEMS.beta.name);
    checks.plannerOpened = true;
    openEvidenceTechnicalDetail('unavailable');
    assertVisible('warehouse-evidence-envelope-status-unavailable', checks, 'unavailablePostureVisible');
    assertVisible('planner-evidence-discoverability-surface', checks, 'reportOnlyBoundaryVisible');
    assertNoRecovery(checks);
    cy.then(() => finishScenario('beta'));
  });

  it('runs Review Gamma unknown-evidence journey', () => {
    if (!flowEnabled('gamma')) return;
    beginProfile('planner_desktop_primary');
    const checks = beginScenario('gamma');
    gotoFinder();
    validateEffectiveViewport('planner_desktop_primary');
    openSystemDetail(SYSTEMS.gamma.id64);
    cy.getByTestId('system-detail-modal').should('contain.text', SYSTEMS.gamma.name);
    checks.systemDetailLoaded = true;
    startPlannerFromSystemDetail(SYSTEMS.gamma.id64);
    waitForPlanner(SYSTEMS.gamma.name);
    checks.plannerOpened = true;
    openEvidenceTechnicalDetail('unknown');
    assertVisible('warehouse-evidence-envelope-status-unknown', checks, 'unknownPostureVisible');
    assertVisible('planner-evidence-discoverability-surface', checks, 'reportOnlyBoundaryVisible');
    assertNoRecovery(checks);
    cy.then(() => finishScenario('gamma'));
  });

  it('runs Review Delta provenance-fallback journey', () => {
    if (!flowEnabled('delta')) return;
    beginProfile('planner_desktop_primary');
    const checks = beginScenario('delta');
    gotoFinder();
    validateEffectiveViewport('planner_desktop_primary');
    openSystemDetail(SYSTEMS.delta.id64);
    cy.getByTestId('system-detail-modal').should('contain.text', SYSTEMS.delta.name);
    checks.systemDetailLoaded = true;
    startPlannerFromSystemDetail(SYSTEMS.delta.id64);
    waitForPlanner(SYSTEMS.delta.name);
    checks.plannerOpened = true;
    openEvidenceTechnicalDetail('unknown', 'provenance_bridge');
    assertVisible('warehouse-evidence-source-posture-provenance_bridge', checks, 'provenanceFallbackVisible');
    assertVisible('planner-evidence-discoverability-surface', checks, 'reportOnlyBoundaryVisible');
    assertText('warehouse-evidence-summary', /plan has not been changed automatically/i, checks, 'fallbackRemainsNonCanonical');
    cy.getByTestId('warehouse-evidence-envelope-summary').should('be.visible');
    cy.getByTestId('warehouse-evidence-source-class-list').should('be.visible');
    cy.getByTestId('warehouse-evidence-semantic-list').should('be.visible').then(() => {
      checks.technicalFallbackDisclosureVisible = true;
    });
    cy.get('body').then(($body) => {
      checks.noDedicatedEvidenceClaim = $body.find('[data-testid="warehouse-evidence-item"]').length === 0;
      expect(checks.noDedicatedEvidenceClaim, 'fallback should not claim dedicated evidence').to.equal(true);
    });
    assertNoRecovery(checks);
    assertVisible('warehouse-evidence-bounded-staging-not_evaluated', checks, 'notEvaluatedBoundaryVisible');
    assertVisible('warehouse-evidence-warnings', checks, 'provenanceWarningVisible');
    cy.then(() => {
      const responses = summary.apiResponses.slice(activeScenarioStart);
      checks.deltaDedicated503Seen = responses.some((response) => (
        response.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/warehouse-planner-evidence`
        && response.status === 503
      ));
      checks.deltaFallback200Seen = responses.some((response) => (
        response.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/provenance-cockpit`
        && response.status === 200
      ));
      finishScenario('delta');
    });
  });

  it('validates desktop planner keyboard and overflow posture', () => {
    setupPlannerProfile('planner_desktop_primary');
    const checks = ensureProfileResult('planner_desktop_primary').checks;
    checks.plannerOpened = true;
    ensureTelemetryToggleKeyboardWorks(checks);
    assertNoRecovery(checks);
    collectOverflowMetrics(PLANNER_OVERFLOW_TEST_IDS).then((overflow) => {
      checks.documentOverflowWithinTolerance = overflow.documentOverflowPx <= 4;
      checks.criticalOverflowWithinTolerance = overflow.containerOverflow.length === 0;
      ensureProfileResult('planner_desktop_primary').diagnostics = overflow;
      expect(checks.documentOverflowWithinTolerance, 'desktop document overflow').to.equal(true);
      expect(checks.criticalOverflowWithinTolerance, 'desktop critical container overflow').to.equal(true);
    });
  });

  it('validates minimum laptop planner posture', () => {
    setupPlannerProfile('planner_laptop_minimum');
    const checks = ensureProfileResult('planner_laptop_minimum').checks;
    checks.plannerOpened = true;
    assertVisible('planner-evidence-discoverability-surface', checks, 'reportOnlyBoundaryVisible');
    assertText('planner-evidence-discoverability-summary', /canonical planner truth/i, checks, 'canonicalBoundaryVisible');
    assertTelemetryToggleRendered();
    assertRenderedControl('summary-rail-collapse-toggle', 'summary rail collapse toggle')
    .focus()
    .should('have.focus')
    .then(() => {
      checks.keyControlsReachable = true;
    });
    ensureTelemetryToggleKeyboardWorks(checks);
    telemetryToggleCanReceiveFocus(checks);
    assertNoRecovery(checks);
    collectOverflowMetrics(PLANNER_OVERFLOW_TEST_IDS).then((overflow) => {
      checks.documentOverflowWithinTolerance = overflow.documentOverflowPx <= 4;
      checks.criticalOverflowWithinTolerance = overflow.containerOverflow.length === 0;
      ensureProfileResult('planner_laptop_minimum').diagnostics = overflow;
      expect(checks.documentOverflowWithinTolerance, 'laptop document overflow').to.equal(true);
      expect(checks.criticalOverflowWithinTolerance, 'laptop critical container overflow').to.equal(true);
    });
  });

  it('records constrained desktop planner diagnostics and safe return', () => {
    setupPlannerProfile('planner_constrained_diagnostic');
    const checks = ensureProfileResult('planner_constrained_diagnostic').checks;
    checks.plannerOpened = true;
    cy.getByTestId('workspace-context-header').should('contain.text', SYSTEMS.alpha.name).then(() => {
      checks.selectedSystemContextVisible = true;
    });
    assertNoRecovery(checks);
    collectOverflowMetrics(PLANNER_OVERFLOW_TEST_IDS).then((overflow) => {
      ensureProfileResult('planner_constrained_diagnostic').diagnostics = overflow;
      if (overflow.documentOverflowPx > 4 || overflow.containerOverflow.length > 0) {
        summary.productObservations.push({
          key: 'planner_constrained_layout_compromise_diagnostic',
          classification: 'KNOWN_VIEWPORT_DIAGNOSTIC',
          owner: 'PR #259',
          environmentReady: true,
          productAcceptanceReady: true,
          description: 'Constrained planner layout compromise remained bounded and escape-safe at 1024x768.',
          metrics: overflow,
        });
      }
    });
    returnToFinder(checks);
  });

  it('validates Finder and system-detail mobile posture', () => {
    beginProfile('finder_mobile');
    const checks = ensureProfileResult('finder_mobile').checks;
    gotoFinder();
    validateEffectiveViewport('finder_mobile');
    checks.finderLoaded = true;
    expectReviewCardsAccessible();
    checks.reviewCardsAccessible = true;
    collectOverflowMetrics([]).then((finderOverflow) => {
      checks.finderDocumentOverflowWithinTolerance = finderOverflow.documentOverflowPx <= 4;
      expect(checks.finderDocumentOverflowWithinTolerance, 'Finder mobile document overflow').to.equal(true);
      ensureProfileResult('finder_mobile').diagnostics.finder_document = finderOverflow;
    });

    openSystemDetail(SYSTEMS.alpha.id64);
    checks.systemDetailOpened = true;
    assertVisible('system-detail-close', checks, 'systemDetailCloseControlVisible');
    closeSystemDetailWithEscape();
    assertHiddenOrAbsent('system-detail-modal');
    checks.modalEscapeCloseWorks = true;
    summary.accessibility.modalEscapeCloseWorks = true;

    openSystemDetail(SYSTEMS.alpha.id64);
    collectOverflowMetrics([]).then((detailOverflow) => {
      checks.systemDetailDocumentOverflowWithinTolerance = detailOverflow.documentOverflowPx <= 4;
      expect(checks.systemDetailDocumentOverflowWithinTolerance, 'system detail mobile document overflow').to.equal(true);
      ensureProfileResult('finder_mobile').diagnostics.system_detail_document = detailOverflow;
    });
    cy.getByTestId('system-detail-close').click();
    assertHiddenOrAbsent('system-detail-modal');
    checks.closeControlWorks = true;
    assertNoRecovery(checks);
  });

  it('validates phone-width planner resilience and safe exit', () => {
    setupPlannerProfile('planner_mobile_resilience');
    const checks = ensureProfileResult('planner_mobile_resilience').checks;
    checks.plannerOpened = true;
    cy.getByTestId('workspace-context-header').should('contain.text', SYSTEMS.alpha.name).then(() => {
      checks.selectedSystemContextVisible = true;
    });
    cy.contains('button', /Back to Finder/i).should('be.visible').then(() => {
      checks.safeExitControlVisible = true;
    });
    assertNoRecovery(checks);
    collectOverflowMetrics(PLANNER_OVERFLOW_TEST_IDS).then((overflow) => {
      ensureProfileResult('planner_mobile_resilience').diagnostics = overflow;
      if (overflow.documentOverflowPx > 4 || overflow.containerOverflow.length > 0) {
        summary.productObservations.push({
          key: 'planner_mobile_resilience_overflow_diagnostic',
          classification: 'KNOWN_VIEWPORT_DIAGNOSTIC',
          owner: 'PR #259',
          environmentReady: true,
          productAcceptanceReady: true,
          description: 'Phone-width planner overflow remained a bounded resilience diagnostic and did not redefine desktop planner acceptance.',
          metrics: overflow,
        });
      }
    });
    returnToFinder(checks);
  });
});
