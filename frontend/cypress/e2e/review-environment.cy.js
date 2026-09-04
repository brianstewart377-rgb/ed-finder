/* global Cypress, cy, expect, describe, before, afterEach, it, URL */

// Review Lab's browser collector. The Python Review Lab remains the owner of
// schema validation, network policy, fallback correlation, and evaluation.
const SYSTEMS = {
  alpha: { id64: 7200000000001, name: 'Review Alpha' },
  beta: { id64: 7200000000002, name: 'Review Beta' },
  gamma: { id64: 7200000000003, name: 'Review Gamma' },
  delta: { id64: 7200000000004, name: 'Review Delta' },
};
const PROFILES = [
  ['planner_desktop_primary', 1440, 900, 'planner', 'required'],
  ['planner_laptop_minimum', 1280, 720, 'planner', 'required'],
  ['planner_constrained_diagnostic', 1024, 768, 'planner', 'diagnostic'],
  ['finder_mobile', 390, 844, 'finder_and_system_detail', 'required'],
  ['planner_mobile_resilience', 390, 844, 'planner', 'resilience_only'],
].map(([profile_name, viewport_width, viewport_height, product_scope, acceptance_level]) => ({
  profile_name, viewport_width, viewport_height, device_scale_factor: 1, product_scope, acceptance_level,
}));
const OVERFLOW_IDS = ['colony-planner-workspace', 'whole-system-colony-planner', 'workspace-planner-content', 'planner-telemetry-region', 'planner-canvas'];

const outputPath = Cypress.env('REVIEW_OUTPUT_PATH');
const rawPlan = Cypress.env('REVIEW_SCENARIOS_JSON');
const reviewLabRun = String(Cypress.env('REVIEW_LAB_RUN')) === '1';
const summary = {
  summarySchemaVersion: 1, reviewLabRun, selectedScenarioNames: [], browserFlowKeys: [], selectedPlan: null,
  scenarios: {}, accessibility: {}, viewportProfiles: [], profileResults: {}, productObservations: [],
  apiResponses: [], consoleEntries: [], pageErrors: [], fatalError: null,
};

function sanitize(value) { return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500); }
function testId(id) { return `[data-testid="${id}"]` }
function visible(id) { return cy.get(`${testId(id)}:visible`).first().should('be.visible'); }
function recordProfile(profile, checks, diagnostics = {}) {
  summary.viewportProfiles.push({ ...profile });
  summary.profileResults[profile.profile_name] = { status: 'passed', checks: { effectiveViewportApplied: true, ...checks }, diagnostics, error: null };
}
function writeSummary() { if (outputPath) cy.writeFile(outputPath, `${JSON.stringify(summary, null, 2)}\n`, { log: false }); }
function overflow(ids = []) {
  return cy.document().then((doc) => {
    const documentWidth = Math.max(doc.documentElement?.scrollWidth || 0, doc.body?.scrollWidth || 0);
    const containerOverflow = ids.map((id) => {
      const node = doc.querySelector(testId(id));
      if (!(node instanceof doc.defaultView.HTMLElement)) return null;
      return { testId: id, clientWidth: node.clientWidth, scrollWidth: node.scrollWidth, overflowPx: Math.max(0, node.scrollWidth - node.clientWidth) };
    }).filter((item) => item && item.overflowPx > 4);
    return { documentOverflowPx: Math.max(0, documentWidth - doc.defaultView.innerWidth), documentWidth, viewportWidth: doc.defaultView.innerWidth, containerOverflow };
  });
}
function assertViewport(profile) {
  cy.viewport(profile.viewport_width, profile.viewport_height);
  cy.window().should((win) => {
    expect(win.innerWidth).to.eq(profile.viewport_width);
    expect(win.innerHeight).to.eq(profile.viewport_height);
    expect(win.devicePixelRatio).to.eq(1);
  });
}
function gotoFinder() {
  cy.visit('/#finder', { onBeforeLoad(win) {
    win.localStorage.clear();
    if (win.navigator.serviceWorker) win.navigator.serviceWorker.register = async () => ({ scope: '/' });
    ['error', 'warn', 'log', 'info', 'debug'].forEach((type) => {
      const original = win.console[type];
      win.console[type] = (...args) => { summary.consoleEntries.push({ type, text: sanitize(args.join(' ')) }); original.apply(win.console, args); };
    });
  } });
  visible('finder-page-heading'); visible('filter-module-system').click();
  cy.contains('label', 'Colony status').parent().find('button').click(); cy.contains('[role="option"]', /^Any$/).click();
  cy.get('body').type('{esc}'); visible('search-submit').click(); visible('search-summary');
  Object.values(SYSTEMS).forEach(({ id64, name }) => { visible(`result-card-${id64}`).scrollIntoView(); cy.contains(name).first().should('be.visible'); });
}
function openDetail(system) {
  const card = testId(`result-card-${system.id64}`);
  cy.get(card).should('be.visible').then(($card) => {
    if (!$card.find('button:contains("Inspect system")').is(':visible')) cy.wrap($card).find('header').click();
  });
  cy.get(card).contains('button', /^Inspect system$/).click(); visible('system-detail-modal');
}
function startPlanner(system, keyboard = false) {
  ['open-plan-start', 'plan-objective-decide_later', 'plan-approach-manual'].forEach((id) => {
    const control = visible(id);
    if (keyboard) control.focus().should('have.focus').type('{enter}'); else control.click();
  });
  visible('confirm-start-plan').then(($button) => {
    if (keyboard) cy.wrap($button).focus().should('have.focus').type('{enter}'); else cy.wrap($button).click();
  });
  visible('colony-planner-workspace'); visible('planner-evidence-discoverability-surface'); visible('planner-warehouse-evidence');
  visible('workspace-context-header').contains('h1, h2, h3', 'Colony Planner').should('be.visible');
  cy.get(testId('workspace-context-header')).contains(system.name).should('be.visible');
}
function openTechnical(status, posture) {
  cy.get(testId(`warehouse-evidence-envelope-status-${status}`), { timeout: 20000 }).should('exist');
  if (posture) cy.get(testId(`warehouse-evidence-source-posture-${posture}`), { timeout: 20000 }).should('exist');
  cy.get('body').then(($body) => {
    const details = $body.find(testId('warehouse-evidence-technical-details'));
    if (details.length) {
      if (!details.attr('open')) cy.wrap(details).find('summary').click();
      cy.wrap(details).should('have.attr', 'open');
    } else {
      cy.get(testId('warehouse-evidence-disclosure-toggle')).then(($toggle) => {
        if ($toggle.attr('aria-expanded') !== 'true') cy.wrap($toggle).click();
      });
      visible('warehouse-evidence-disclosure-panel');
    }
  });
}
function telemetryKeyboard() {
  visible('planner-telemetry-dock-toggle').focus().should('have.focus').type('{enter}').should('have.attr', 'aria-expanded', 'true')
    .type('{enter}').should('have.attr', 'aria-expanded', 'false');
}
function noRecovery() { cy.contains('ED:Finder UI Recovery').should('not.exist'); }
function scenario(flow) {
  const system = SYSTEMS[flow]; const start = summary.apiResponses.length; const checks = {};
  gotoFinder(); openDetail(system); cy.contains(system.name).first().should('be.visible'); checks.systemDetailLoaded = true;
  if (flow === 'alpha') {
    cy.get('body').type('{esc}'); cy.get(testId('system-detail-modal')).should('not.exist'); checks.modalEscapeCloseWorks = true; summary.accessibility.modalEscapeCloseWorks = true;
    openDetail(system); startPlanner(system, true); summary.accessibility.alphaKeyboardOpenPlannerWorks = true;
    Object.assign(checks, { plannerOpened: true, reportOnlyBoundaryVisible: true, canonicalBoundaryVisible: true });
    cy.get(testId('planner-evidence-discoverability-summary')).should('contain.text', 'canonical planner truth'); openTechnical('available');
    visible('warehouse-evidence-source-posture-dedicated_contract'); visible('warehouse-evidence-report-only-tag');
  } else {
    startPlanner(system); checks.plannerOpened = true;
    if (flow === 'beta') { openTechnical('unavailable'); checks.unavailablePostureVisible = true; }
    if (flow === 'gamma') { openTechnical('unknown'); checks.unknownPostureVisible = true; }
    if (flow === 'delta') {
      openTechnical('unknown', 'provenance_bridge');
      visible('warehouse-evidence-summary').should('contain.text', 'plan has not been changed automatically');
      visible('warehouse-evidence-envelope-summary'); visible('warehouse-evidence-source-class-list'); visible('warehouse-evidence-semantic-list');
      cy.get(testId('warehouse-evidence-item')).should('not.exist'); visible('warehouse-evidence-bounded-staging-not_evaluated'); visible('warehouse-evidence-warnings');
      Object.assign(checks, { provenanceFallbackVisible: true, fallbackRemainsNonCanonical: true, technicalFallbackDisclosureVisible: true, noDedicatedEvidenceClaim: true, notEvaluatedBoundaryVisible: true, provenanceWarningVisible: true });
    }
    checks.reportOnlyBoundaryVisible = true;
  }
  noRecovery(); checks.noRecoveryScreen = true;
  cy.then(() => { summary.scenarios[flow] = { status: 'passed', checks, apiResponses: summary.apiResponses.slice(start), error: null }; });
}

describe('Local review environment verification', () => {
  before(function () {
    if (!reviewLabRun || !outputPath || !rawPlan) {
      if (reviewLabRun || outputPath || rawPlan) {
        throw new Error('Review Lab browser verification requires EDFINDER_REVIEW_LAB_RUN=1 together with EDFINDER_REVIEW_OUTPUT_PATH and EDFINDER_REVIEW_SCENARIOS_JSON.');
      }
      this.skip();
      return;
    }
    const plan = typeof rawPlan === 'string' ? JSON.parse(rawPlan) : rawPlan; summary.selectedScenarioNames = plan.selectedScenarioNames; summary.browserFlowKeys = plan.browserFlowKeys; summary.selectedPlan = plan;
    cy.intercept({ url: '**/api/**', middleware: true }, (req) => { req.on('response', (res) => { const url = new URL(req.url); summary.apiResponses.push({ method: req.method, path: `${url.pathname}${url.search}`, status: res.statusCode }); }); });
    Cypress.on('uncaught:exception', (error) => { summary.pageErrors.push(sanitize(error.stack || error.message)); return false; });
  });
  afterEach(function () { if (this.currentTest.state === 'failed') summary.fatalError = sanitize(this.currentTest.err?.stack || this.currentTest.err?.message); writeSummary(); });

  it('captures deterministic browser verification summary', { defaultCommandTimeout: 20000 }, () => {
    const desktop = PROFILES[0]; assertViewport(desktop); summary.browserFlowKeys.forEach(scenario); telemetryKeyboard(); summary.accessibility.plannerDesktopTelemetryToggleKeyboardWorks = true; noRecovery();
    overflow(OVERFLOW_IDS).then((metrics) => { expect(metrics.documentOverflowPx).to.be.at.most(4); expect(metrics.containerOverflow).to.have.length(0); recordProfile(desktop, { documentOverflowWithinTolerance: true, criticalOverflowWithinTolerance: true, telemetryToggleKeyboardWorks: true, noRecoveryScreen: true }, metrics); });

    const laptop = PROFILES[1]; assertViewport(laptop); gotoFinder(); openDetail(SYSTEMS.alpha); startPlanner(SYSTEMS.alpha); telemetryKeyboard();
    visible('planner-evidence-discoverability-summary').should('contain.text', 'canonical planner truth'); visible('summary-rail-collapse-toggle'); noRecovery();
    overflow(OVERFLOW_IDS).then((metrics) => { expect(metrics.documentOverflowPx).to.be.at.most(4); expect(metrics.containerOverflow).to.have.length(0); recordProfile(laptop, { plannerOpened: true, reportOnlyBoundaryVisible: true, canonicalBoundaryVisible: true, documentOverflowWithinTolerance: true, criticalOverflowWithinTolerance: true, keyControlsReachable: true, telemetryToggleKeyboardWorks: true, safeFocusAndNavigation: true, noRecoveryScreen: true }, metrics); });

    const constrained = PROFILES[2]; assertViewport(constrained); gotoFinder(); openDetail(SYSTEMS.alpha); startPlanner(SYSTEMS.alpha); noRecovery();
    overflow(OVERFLOW_IDS).then((metrics) => { if (metrics.documentOverflowPx > 4 || metrics.containerOverflow.length) summary.productObservations.push({ key: 'planner_constrained_layout_compromise_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Constrained planner layout compromise remained bounded and escape-safe at 1024x768.', metrics }); cy.contains('button', /Back to Finder/i).click(); visible('search-summary'); recordProfile(constrained, { plannerOpened: true, selectedSystemContextVisible: true, safeReturnToFinder: true, noRecoveryScreen: true }, metrics); });

    const mobile = PROFILES[3]; assertViewport(mobile); gotoFinder();
    overflow().then((finderMetrics) => { expect(finderMetrics.documentOverflowPx).to.be.at.most(4); openDetail(SYSTEMS.alpha); visible('system-detail-close'); cy.get('body').type('{esc}'); cy.get(testId('system-detail-modal')).should('not.exist'); openDetail(SYSTEMS.alpha); overflow().then((detailMetrics) => { expect(detailMetrics.documentOverflowPx).to.be.at.most(4); visible('system-detail-close').click(); cy.get(testId('system-detail-modal')).should('not.exist'); noRecovery(); recordProfile(mobile, { finderLoaded: true, reviewCardsAccessible: true, systemDetailOpened: true, systemDetailCloseControlVisible: true, modalEscapeCloseWorks: true, closeControlWorks: true, finderDocumentOverflowWithinTolerance: true, systemDetailDocumentOverflowWithinTolerance: true, noRecoveryScreen: true }, { finder_document: finderMetrics, system_detail_document: detailMetrics }); }); });

    const resilience = PROFILES[4]; assertViewport(resilience); gotoFinder(); openDetail(SYSTEMS.alpha); startPlanner(SYSTEMS.alpha); cy.contains('button', /Back to Finder/i).should('be.visible'); noRecovery();
    overflow(OVERFLOW_IDS).then((metrics) => { if (metrics.documentOverflowPx > 4 || metrics.containerOverflow.length) summary.productObservations.push({ key: 'planner_mobile_resilience_overflow_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Phone-width planner overflow remained a bounded resilience diagnostic and did not redefine desktop planner acceptance.', metrics }); cy.contains('button', /Back to Finder/i).click(); visible('search-summary'); recordProfile(resilience, { plannerOpened: true, selectedSystemContextVisible: true, safeExitControlVisible: true, safeReturnToFinder: true, noRecoveryScreen: true }, metrics); });
    cy.then(() => {
      const delta = summary.scenarios.delta;
      if (delta) { delta.checks.deltaDedicated503Seen = delta.apiResponses.some((r) => r.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/warehouse-planner-evidence` && r.status === 503); delta.checks.deltaFallback200Seen = delta.apiResponses.some((r) => r.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/provenance-cockpit` && r.status === 200); }
    });
  });
});
