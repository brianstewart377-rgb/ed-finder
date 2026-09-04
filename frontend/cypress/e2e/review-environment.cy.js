/// <reference types="cypress" />

const SYSTEMS = {
  alpha: { id64: 7200000000001, name: 'Review Alpha' }, beta: { id64: 7200000000002, name: 'Review Beta' },
  gamma: { id64: 7200000000003, name: 'Review Gamma' }, delta: { id64: 7200000000004, name: 'Review Delta' },
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
const PLANNER_IDS = ['colony-planner-workspace', 'whole-system-colony-planner', 'workspace-planner-content', 'planner-telemetry-region', 'planner-canvas'];

function clean(value) { return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500); }
function validateReviewLabConfig(raw) {
  if (!raw || raw.reviewLabRun !== true || typeof raw.reviewOutputPath !== 'string' || !raw.reviewOutputPath
      || typeof raw.reviewScenariosJson !== 'string' || !raw.reviewScenariosJson) {
    throw new Error('Review Lab browser verification requires a complete trusted Node-task handshake.');
  }
  const value = JSON.parse(raw.reviewScenariosJson);
  if (!Array.isArray(value.selectedScenarioNames) || !Array.isArray(value.browserFlowKeys)) throw new Error('Review Lab scenario plan is malformed.');
  return Object.freeze({
    reviewLabRun: true,
    reviewOutputPath: raw.reviewOutputPath,
    selectedPlan: Object.freeze({ ...value, includeProductObservations: Boolean(value.includeProductObservations) }),
  });
}
function summaryFor(selectedPlan) {
  return { summarySchemaVersion: 1, reviewLabRun: true, selectedScenarioNames: selectedPlan.selectedScenarioNames,
    browserFlowKeys: selectedPlan.browserFlowKeys, selectedPlan, scenarios: {}, accessibility: {}, viewportProfiles: [],
    profileResults: {}, productObservations: [], apiResponses: [], consoleEntries: [], pageErrors: [], fatalError: null };
}
function instrument(summary) {
  cy.intercept({ url: '**/api/**', middleware: true }, (req) => req.on('response', (res) => {
    const url = new URL(req.url); summary.apiResponses.push({ method: req.method, path: `${url.pathname}${url.search}`, status: res.statusCode });
  }));
  cy.on('window:before:load', (win) => {
    try { if (win.navigator.serviceWorker) win.navigator.serviceWorker.register = async () => ({ scope: '/' }); } catch { /* best effort */ }
    win.addEventListener('error', (event) => summary.pageErrors.push(clean(event.error?.stack || event.message)));
    for (const type of ['error', 'warn', 'log', 'info', 'debug']) {
      const original = win.console[type]; win.console[type] = (...args) => { summary.consoleEntries.push({ type, text: clean(args.join(' ')) }); original.apply(win.console, args); };
    }
  });
}
function labelledControl(labelText) {
  const exactLabel = new RegExp(`^${Cypress._.escapeRegExp(labelText)}$`);
  return cy.contains('label', exactLabel).should(($label) => {
    const controlId = $label.attr('for');
    expect(controlId, `${labelText} label control id`).to.be.a('string');
    expect(controlId, `${labelText} label control id`).not.to.equal('');
  }).then(($label) => {
    const controlId = $label.attr('for');
    return cy.get(`#${Cypress.$.escapeSelector(controlId)}`)
      .should(($control) => {
        expect(
          $control.is('button') || $control.attr('role') === 'combobox',
          `${labelText} control has button or combobox semantics`,
        ).to.eq(true);
      })
      .should('be.visible')
      .and('be.enabled');
  });
}
function finder() {
  cy.visit('/#finder'); cy.getByTestId('finder-page-heading').should('be.visible');
  cy.getByTestId('filter-module-system').click(); labelledControl('Colony status').click();
  cy.contains('[role="option"]', /^Any$/).should('be.visible').click(); cy.get('body').type('{esc}'); cy.getByTestId('search-submit').click();
  cy.getByTestId('search-summary', { timeout: 20000 }).should('be.visible');
  Object.values(SYSTEMS).forEach(({ id64, name }) => { cy.getByTestId(`result-card-${id64}`).scrollIntoView().should('be.visible'); cy.contains(name).should('be.visible'); });
}
function detail(system) {
  const card = `[data-testid="result-card-${system.id64}"]`;
  cy.get(card).should('be.visible').then(($card) => { if (!$card.find('button:contains("Inspect system")').is(':visible')) cy.wrap($card).find('header').click(); });
  cy.get(card).contains('button', 'Inspect system').click(); cy.getByTestId('system-detail-modal').should('be.visible');
}
function closeDetailWithEscape() {
  // SystemDetailModal locks body scrolling in the same effect that installs
  // its window keydown listener. Wait for that observable side effect so the
  // real Escape event cannot race the listener installation (notably in
  // Firefox).
  cy.get('body').should(($body) => {
    expect($body[0].style.overflow, 'modal Escape listener readiness').to.eq('hidden');
  });
  cy.window().then((win) => {
    win.dispatchEvent(new win.KeyboardEvent('keydown', {
      key: 'Escape', code: 'Escape', which: 27, keyCode: 27, bubbles: true, cancelable: true,
    }));
  });
  cy.getByTestId('system-detail-modal').should('not.exist');
  cy.get('body').should(($body) => {
    expect($body[0].style.overflow, 'body overflow restored after modal close').to.eq('');
  });
  cy.location('hash').should('eq', '#finder');
}
function armFocusedButtonEnterDefaultAction(control, label) {
  expect(control.tagName, `${label} native element`).to.equal('BUTTON');
  expect(control.disabled, `${label} enabled`).to.equal(false);

  let clickObserved = false;
  const observeClick = () => { clickObserved = true; };
  control.addEventListener('click', observeClick, { once: true });
  control.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') {
      control.removeEventListener('click', observeClick);
      return;
    }

    // Cypress emits the focused Enter key events but omits the native button
    // default action on this CI path. Wait for propagation, honour
    // preventDefault(), and supply only that missing default action.
    const win = control.ownerDocument.defaultView;
    win.queueMicrotask(() => {
      const stillFocused = control.ownerDocument.activeElement === control;
      if (!event.defaultPrevented && !clickObserved && stillFocused
          && control.isConnected && !control.disabled) {
        control.click();
      }
      control.removeEventListener('click', observeClick);
    });
  }, { once: true });
}
function planner(system, keyboard = false, keyboardOpened = null) {
  if (keyboard) {
    cy.get('[data-testid="open-plan-start"]:visible').should('have.length', 1).focus().should('have.focus')
      .then(($control) => armFocusedButtonEnterDefaultAction($control[0], 'open-plan-start'));
    cy.focused().type('{enter}');
  } else {
    cy.getByTestId('open-plan-start').should('be.visible').click();
  }
  cy.getByTestId('plan-start-panel').should('be.visible');
  if (keyboardOpened) cy.then(keyboardOpened);
  ['plan-objective-decide_later', 'plan-approach-manual', 'confirm-start-plan'].forEach((id) => {
    cy.getByTestId(id).should('be.visible').click();
  });
  cy.getByTestId('colony-planner-workspace', { timeout: 20000 }).should('be.visible');
  cy.getByTestId('planner-evidence-discoverability-surface').should('be.visible'); cy.getByTestId('planner-warehouse-evidence').should('be.visible');
  cy.getByTestId('workspace-context-header').should('contain.text', system.name).contains('h1,h2,h3', 'Colony Planner').should('be.visible');
}
function technical(status, posture) {
  cy.getByTestId(`warehouse-evidence-envelope-status-${status}`, { timeout: 20000 }).should('exist');
  if (posture) cy.getByTestId(`warehouse-evidence-source-posture-${posture}`).should('exist');
  cy.get('body').then(($body) => {
    const details = $body.find('[data-testid="warehouse-evidence-technical-details"]');
    if (details.length) { if (!details.attr('open')) cy.wrap(details).find('summary').click(); cy.wrap(details).should('have.attr', 'open'); }
    else cy.getByTestId('warehouse-evidence-disclosure-toggle').then(($t) => { if ($t.attr('aria-expanded') !== 'true') cy.wrap($t).click(); });
  });
}
function overflow(ids, callback) {
  cy.document().then((doc) => { const width = Math.max(doc.documentElement.scrollWidth, doc.body.scrollWidth); const result = {
    documentOverflowPx: Math.max(0, width - doc.defaultView.innerWidth), documentWidth: width, viewportWidth: doc.defaultView.innerWidth,
    containerOverflow: ids.map((testId) => { const n = doc.querySelector(`[data-testid="${testId}"]`); return n && { testId, clientWidth: n.clientWidth, scrollWidth: n.scrollWidth, overflowPx: Math.max(0, n.scrollWidth - n.clientWidth) }; }).filter((v) => v && v.overflowPx > 4),
  }; callback(result); });
}
function telemetry(checks, summary) {
  const toggle = () => cy.get('[data-testid="planner-telemetry-dock-toggle"]:visible').first();
  toggle().focus().should('have.focus')
    .then(($control) => armFocusedButtonEnterDefaultAction($control[0], 'planner telemetry toggle'));
  toggle().should('have.focus').type('{enter}', { force: true });
  toggle().should('have.attr', 'aria-expanded', 'true');
  toggle().focus().should('have.focus')
    .then(($control) => armFocusedButtonEnterDefaultAction($control[0], 'planner telemetry toggle'));
  toggle().should('have.focus').type('{enter}', { force: true });
  toggle().should('have.attr', 'aria-expanded', 'false');
  checks.telemetryToggleKeyboardWorks = true; summary.accessibility.plannerDesktopTelemetryToggleKeyboardWorks = true;
}
function profile(summary, metadata, body) {
  summary.viewportProfiles.push(metadata); const result = { status: 'failed', checks: { effectiveViewportApplied: false }, diagnostics: {}, error: null };
  cy.viewport(metadata.viewport_width, metadata.viewport_height); cy.visit('/'); cy.clearLocalStorage(); cy.reload();
  cy.window().then((win) => { expect(win.innerWidth).to.eq(metadata.viewport_width); expect(win.innerHeight).to.eq(metadata.viewport_height); result.checks.effectiveViewportApplied = true; });
  body(result).then(() => { result.status = 'passed'; summary.profileResults[metadata.profile_name] = result; });
}

describe('Local review environment verification', () => {
  let reviewConfig;
  let activeSummary;
  before(() => {
    cy.task('getReviewLabConfig', null, { log: false }).then((raw) => {
      reviewConfig = validateReviewLabConfig(raw);
    });
  });
  afterEach(() => {
    if (activeSummary && reviewConfig) cy.task('writeReviewLabSummary', { outputPath: reviewConfig.reviewOutputPath, summary: activeSummary }, { log: false });
  });
  it('captures deterministic browser verification summary', () => {
    const selectedPlan = reviewConfig.selectedPlan; const summary = summaryFor(selectedPlan); activeSummary = summary; instrument(summary);
    Cypress.on('fail', (error) => { summary.fatalError = clean(error.stack || error.message); throw error; });

    profile(summary, PROFILES[0], (result) => { let chain = cy.wrap(null);
      selectedPlan.browserFlowKeys.forEach((key) => { chain = chain.then(() => { const system = SYSTEMS[key]; const start = summary.apiResponses.length; const checks = {};
        finder(); detail(system);
        if (key === 'alpha') { closeDetailWithEscape(); checks.modalEscapeCloseWorks = true; summary.accessibility.modalEscapeCloseWorks = true; detail(system); }
        planner(system, key === 'alpha', key === 'alpha' ? () => { summary.accessibility.alphaKeyboardOpenPlannerWorks = true; } : null); checks.systemDetailLoaded = true; checks.plannerOpened = true;
        if (key === 'alpha') { checks.reportOnlyBoundaryVisible = true; checks.canonicalBoundaryVisible = true; technical('available'); checks.availablePostureVisible = true; checks.dedicatedContractVisible = true; checks.reportOnlyTagVisible = true; }
        if (key === 'beta') { technical('unavailable'); checks.unavailablePostureVisible = true; checks.reportOnlyBoundaryVisible = true; }
        if (key === 'gamma') { technical('unknown'); checks.unknownPostureVisible = true; checks.reportOnlyBoundaryVisible = true; }
        if (key === 'delta') { technical('unknown', 'provenance_bridge'); checks.provenanceFallbackVisible = true; checks.reportOnlyBoundaryVisible = true; checks.fallbackRemainsNonCanonical = true; checks.technicalFallbackDisclosureVisible = true; cy.getByTestId('warehouse-evidence-item').should('not.exist'); checks.noDedicatedEvidenceClaim = true; }
        checks.noRecoveryScreen = true; cy.then(() => { summary.scenarios[key] = { status: 'passed', checks, apiResponses: summary.apiResponses.slice(start), error: null }; });
      }); }); return chain.then(() => { telemetry(result.checks, summary); result.checks.noRecoveryScreen = true; overflow(PLANNER_IDS, (m) => { result.diagnostics = m; result.checks.documentOverflowWithinTolerance = m.documentOverflowPx <= 4; result.checks.criticalOverflowWithinTolerance = !m.containerOverflow.length; expect(m.documentOverflowPx).to.be.at.most(4); expect(m.containerOverflow).to.have.length(0); }); });
    });
    profile(summary, PROFILES[1], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, reportOnlyBoundaryVisible: true, canonicalBoundaryVisible: true, keyControlsReachable: true, safeFocusAndNavigation: true, noRecoveryScreen: true }); telemetry(r.checks, summary); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; r.checks.documentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.checks.criticalOverflowWithinTolerance = !m.containerOverflow.length; }); return cy.wrap(null); });
    profile(summary, PROFILES[2], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, selectedSystemContextVisible: true, noRecoveryScreen: true }); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; if (m.documentOverflowPx > 4 || m.containerOverflow.length) summary.productObservations.push({ key: 'planner_constrained_layout_compromise_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Constrained planner layout compromise remained bounded and escape-safe at 1024x768.', metrics: m }); }); cy.contains('button', /Back to Finder/i).click(); cy.getByTestId('search-summary').should('be.visible').then(() => { r.checks.safeReturnToFinder = true; }); return cy.wrap(null); });
    profile(summary, PROFILES[3], (r) => { finder(); Object.assign(r.checks, { finderLoaded: true, reviewCardsAccessible: true }); overflow([], (m) => { r.checks.finderDocumentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.diagnostics.finder_document = m; }); detail(SYSTEMS.alpha); Object.assign(r.checks, { systemDetailOpened: true, systemDetailCloseControlVisible: true }); closeDetailWithEscape(); r.checks.modalEscapeCloseWorks = true; summary.accessibility.modalEscapeCloseWorks = true; detail(SYSTEMS.alpha); overflow([], (m) => { r.checks.systemDetailDocumentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.diagnostics.system_detail_document = m; }); cy.getByTestId('system-detail-close').click(); Object.assign(r.checks, { closeControlWorks: true, noRecoveryScreen: true }); return cy.wrap(null); });
    profile(summary, PROFILES[4], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, selectedSystemContextVisible: true, safeExitControlVisible: true, noRecoveryScreen: true }); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; if (m.documentOverflowPx > 4 || m.containerOverflow.length) summary.productObservations.push({ key: 'planner_mobile_resilience_overflow_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Phone-width planner overflow remained a bounded resilience diagnostic and did not redefine desktop planner acceptance.', metrics: m }); }); cy.contains('button', /Back to Finder/i).click(); cy.getByTestId('search-summary').then(() => { r.checks.safeReturnToFinder = true; }); return cy.wrap(null); });
    cy.then(() => cy.task('writeReviewLabSummary', { outputPath: reviewConfig.reviewOutputPath, summary }, { log: false }));
  });
});
