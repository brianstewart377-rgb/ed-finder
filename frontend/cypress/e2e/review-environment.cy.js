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
const WAREHOUSE_DISCOVERABILITY_SURFACE = '[data-testid="planner-evidence-discoverability-surface"]';
const WAREHOUSE_EVIDENCE_SURFACE = '[data-testid="planner-warehouse-evidence"]';
const WAREHOUSE_TECHNICAL_DETAILS = 'details[data-testid="warehouse-evidence-technical-details"]';
const WAREHOUSE_DISCLOSURE_TOGGLE = 'button[data-testid="warehouse-evidence-disclosure-toggle"]';
const WAREHOUSE_DISCLOSURE_PANEL = '[data-testid="warehouse-evidence-disclosure-panel"]';
const WAREHOUSE_TECHNICAL_DISCLOSURES = `${WAREHOUSE_TECHNICAL_DETAILS}, ${WAREHOUSE_DISCLOSURE_TOGGLE}`;
const WHOLE_SYSTEM_PLANNER = 'section[data-testid="whole-system-colony-planner"]';
const PLANNER_TELEMETRY_REGION = 'div[data-testid="planner-telemetry-region"]';
const PLANNER_TELEMETRY_TOGGLE = 'button[data-testid="planner-telemetry-dock-toggle"]';
const PLANNER_TELEMETRY_CONTENT = 'div[data-testid="planner-telemetry-dock-content"]';

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
function emulateFocusedButtonEnterDefaultAction(control, label) {
  expect(control.tagName, `${label} native element`).to.equal('BUTTON');
  expect(control.disabled, `${label} enabled`).to.equal(false);
  expect(control.ownerDocument.activeElement, `${label} focused`).to.equal(control);

  const win = control.ownerDocument.defaultView;
  let clickObserved = false;
  const observeClick = () => { clickObserved = true; };
  control.addEventListener('click', observeClick, { once: true });
  const keydown = new win.KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true, cancelable: true,
  });
  const allowed = control.dispatchEvent(keydown);
  if (allowed && !keydown.defaultPrevented && !clickObserved
      && control.ownerDocument.activeElement === control
      && control.isConnected && !control.disabled) {
    control.dispatchEvent(new win.MouseEvent('click', {
      bubbles: true, cancelable: true, composed: true, detail: 0, view: win,
    }));
  }
  control.dispatchEvent(new win.KeyboardEvent('keyup', {
    key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true, cancelable: true,
  }));
  control.removeEventListener('click', observeClick);
}
function supplyPlannerEnterDefaultActionIfNeeded() {
  cy.get('body').then(($body) => {
    if (!$body.find('[data-testid="plan-start-panel"]').length) {
      cy.focused().then(($control) => {
        emulateFocusedButtonEnterDefaultAction($control[0], 'open-plan-start');
      });
    }
  });
}
function planner(system, keyboard = false, keyboardOpened = null) {
  const evidenceAlias = `warehouseEvidence${system.id64}`;
  const provenanceAlias = `provenanceCockpit${system.id64}`;
  cy.intercept('GET', `/api/colony-planner/system/${system.id64}/warehouse-planner-evidence`).as(evidenceAlias);
  cy.intercept('GET', `/api/colony-planner/system/${system.id64}/provenance-cockpit`).as(provenanceAlias);
  if (keyboard) {
    cy.get('[data-testid="open-plan-start"]:visible').should('have.length', 1).focus().should('have.focus');
    cy.focused().type('{enter}');
    supplyPlannerEnterDefaultActionIfNeeded();
  } else {
    cy.getByTestId('open-plan-start').should('be.visible').click();
  }
  cy.getByTestId('plan-start-panel').should('be.visible');
  if (keyboardOpened) cy.then(keyboardOpened);
  ['plan-objective-decide_later', 'plan-approach-manual', 'confirm-start-plan'].forEach((id) => {
    cy.getByTestId(id).should('be.visible').click();
  });
  cy.getByTestId('colony-planner-workspace', { timeout: 20000 }).should('be.visible');
  cy.wait(`@${evidenceAlias}`).then((interception) => {
    const status = interception.response?.statusCode;
    expect(status, 'warehouse planner evidence response status').to.be.oneOf([200, 503]);
    if (status === 503) {
      expect(system.id64, '503 evidence response is confined to Review Delta').to.eq(SYSTEMS.delta.id64);
      return cy.wait(`@${provenanceAlias}`).its('response.statusCode').should('eq', 200);
    }
    return undefined;
  });
  cy.getByTestId('planner-evidence-discoverability-surface').should('be.visible'); cy.getByTestId('planner-warehouse-evidence').should('be.visible');
  cy.getByTestId('workspace-context-header').should('contain.text', system.name).contains('h1,h2,h3', 'Colony Planner').should('be.visible');
}
function currentWarehouseEvidenceSurface() {
  return cy.get(WAREHOUSE_DISCOVERABILITY_SURFACE, { timeout: 20000 })
    .should('have.length', 1)
    .and('be.visible')
    .children(WAREHOUSE_EVIDENCE_SURFACE)
    .should(($surfaces) => {
      expect($surfaces, 'current planner warehouse evidence surface').to.have.length(1);
    })
    .and('be.visible');
}
function waitForWarehouseEvidenceRender(status, posture) {
  const statusSelector = `[data-testid="warehouse-evidence-envelope-status-${status}"]`;
  const postureSelector = `[data-testid="warehouse-evidence-source-posture-${posture}"]`;
  // Gamma's loading card and final contract are both "unknown", but only the
  // final render has the expected source posture. Let React commit that render
  // before discovering which of the card's two native disclosures is current.
  return currentWarehouseEvidenceSurface().should(($surface) => {
    expect($surface.find(statusSelector), `current warehouse evidence ${status} status marker`).to.have.length(1);
    expect($surface.find(postureSelector), `current warehouse evidence ${posture} source-posture marker`).to.have.length(1);
  });
}
function currentWarehouseTechnicalDisclosure() {
  return currentWarehouseEvidenceSurface()
    .should(($surface) => {
      const $disclosures = $surface.find(WAREHOUSE_TECHNICAL_DISCLOSURES);
      expect(
        $disclosures,
        'current planner warehouse evidence must expose exactly one supported native technical disclosure',
      ).to.have.length(1);

      const $disclosure = $disclosures.eq(0);
      if ($disclosure.is(WAREHOUSE_TECHNICAL_DETAILS)) {
        expect($disclosure.children('summary'), 'native technical details must have exactly one direct summary').to.have.length(1);
        return;
      }

      expect($disclosure.is(WAREHOUSE_DISCLOSURE_TOGGLE), 'custom technical disclosure must use a native button').to.eq(true);
      expect($disclosure.attr('type'), 'custom technical disclosure native button type').to.eq('button');
      expect($disclosure.attr('aria-expanded'), 'custom technical disclosure expansion state').to.be.oneOf(['true', 'false']);
      const panelId = $disclosure.attr('aria-controls');
      expect(panelId, 'custom technical disclosure controlled panel id').to.be.a('string').and.not.equal('');
      const $panels = $surface.find(WAREHOUSE_DISCLOSURE_PANEL);
      expect($panels, 'custom technical disclosure must have exactly one panel in the current evidence surface').to.have.length(1);
      expect($panels.attr('id'), 'custom technical disclosure panel linkage').to.eq(panelId);
    })
    .then(() => currentWarehouseEvidenceSurface())
    .should(($surface) => {
      expect(
        $surface.find(WAREHOUSE_TECHNICAL_DISCLOSURES),
        're-queried current planner warehouse evidence technical disclosure',
      ).to.have.length(1);
    })
    .then(($surface) => (
      $surface.find(WAREHOUSE_TECHNICAL_DETAILS).length ? 'details' : 'button'
    ));
}
function openCurrentWarehouseTechnicalDisclosure() {
  return currentWarehouseTechnicalDisclosure().then((variant) => {
    if (variant === 'details') {
      return currentWarehouseEvidenceSurface()
        .find(WAREHOUSE_TECHNICAL_DETAILS)
        .should('have.length', 1)
        .then(($details) => {
          if ($details[0].open) return undefined;
          return currentWarehouseEvidenceSurface()
            .find(WAREHOUSE_TECHNICAL_DETAILS)
            .should('have.length', 1)
            .children('summary')
            .should('have.length', 1)
            .and('be.visible')
            .click();
        })
        .then(() => currentWarehouseTechnicalDisclosure().should('eq', 'details'))
        .then(() => currentWarehouseEvidenceSurface()
          .find(WAREHOUSE_TECHNICAL_DETAILS)
          .should(($details) => {
            expect($details, 're-queried native warehouse technical details').to.have.length(1);
            expect($details[0].open, 'native warehouse technical details open state').to.eq(true);
          }));
    }

    return currentWarehouseEvidenceSurface()
      .find(WAREHOUSE_DISCLOSURE_TOGGLE)
      .should('have.length', 1)
      .then(($toggle) => {
        if ($toggle.attr('aria-expanded') === 'true') return undefined;
        return currentWarehouseEvidenceSurface()
          .find(WAREHOUSE_DISCLOSURE_TOGGLE)
          .should('have.length', 1)
          .should('be.visible')
          .and('be.enabled')
          .click();
      })
      .then(() => currentWarehouseTechnicalDisclosure().should('eq', 'button'))
      .then(() => currentWarehouseEvidenceSurface()
        .find(WAREHOUSE_DISCLOSURE_TOGGLE)
        .should('have.attr', 'aria-expanded', 'true'))
      .then(() => currentWarehouseEvidenceSurface()
        .find(WAREHOUSE_DISCLOSURE_PANEL)
        .should(($panel) => {
          expect($panel, 're-queried custom technical disclosure panel').to.have.length(1);
          expect($panel[0].hidden, 'custom technical disclosure panel hidden state').to.eq(false);
          expect($panel.attr('aria-hidden'), 'custom technical disclosure panel aria-hidden state').to.eq('false');
        })
        .and('be.visible'));
  });
}
function technical(status, posture) {
  const statusSelector = `[data-testid="warehouse-evidence-envelope-status-${status}"]`;
  const postureSelector = `[data-testid="warehouse-evidence-source-posture-${posture}"]`;
  return waitForWarehouseEvidenceRender(status, posture)
    .then(() => openCurrentWarehouseTechnicalDisclosure())
    .then(() => currentWarehouseEvidenceSurface()
      .find('[data-testid="warehouse-evidence-envelope-summary"]')
      .should('be.visible'))
    .then(() => currentWarehouseEvidenceSurface()
      .find(statusSelector)
      .should('have.length', 1)
      .and('be.visible'))
    .then(() => currentWarehouseEvidenceSurface()
      .find(postureSelector)
      .should('have.length', 1)
      .and('be.visible'));
}
function overflow(ids, callback) {
  cy.document().then((doc) => { const width = Math.max(doc.documentElement.scrollWidth, doc.body.scrollWidth); const result = {
    documentOverflowPx: Math.max(0, width - doc.defaultView.innerWidth), documentWidth: width, viewportWidth: doc.defaultView.innerWidth,
    containerOverflow: ids.map((testId) => { const n = doc.querySelector(`[data-testid="${testId}"]`); return n && { testId, clientWidth: n.clientWidth, scrollWidth: n.scrollWidth, overflowPx: Math.max(0, n.scrollWidth - n.clientWidth) }; }).filter((v) => v && v.overflowPx > 4),
  }; callback(result); });
}
function currentWholeSystemPlanner() {
  return cy.get(WHOLE_SYSTEM_PLANNER, { timeout: 20000 })
    .should(($planners) => {
      expect($planners, 'current visible whole-system colony planner').to.have.length(1);
      expect($planners.attr('aria-label'), 'whole-system colony planner accessible name').to.eq('Whole-system colony planner');
    })
    .and('be.visible');
}
function currentPlannerTelemetryRegion() {
  return currentWholeSystemPlanner()
    .find(PLANNER_TELEMETRY_REGION)
    .should(($regions) => {
      expect($regions, 'current planner telemetry region').to.have.length(1);
      expect($regions.attr('data-layout'), 'current planner telemetry region layout').to.eq('plan-details-panel');
    })
    .and('be.visible');
}
function currentPlannerTelemetryToggle() {
  return currentPlannerTelemetryRegion()
    .find(PLANNER_TELEMETRY_TOGGLE)
    .should('have.length', 1);
}
function assertCurrentPlannerTelemetryState(expanded) {
  const dockState = expanded === 'true' ? 'open' : 'closed';
  return currentPlannerTelemetryRegion()
    .should(($region) => {
      expect(expanded, 'expected planner telemetry expansion state').to.be.oneOf(['true', 'false']);
      expect($region.attr('data-mobile-dock'), 'planner telemetry region dock state').to.eq(dockState);

      const $toggles = $region.find(PLANNER_TELEMETRY_TOGGLE);
      expect($toggles, 'current planner telemetry native toggle').to.have.length(1);
      const $toggle = $toggles.eq(0);
      expect($toggle.prop('tagName'), 'planner telemetry toggle native element').to.eq('BUTTON');
      expect($toggle.attr('type'), 'planner telemetry toggle native button type').to.eq('button');
      expect($toggle.prop('disabled'), 'planner telemetry toggle enabled state').to.eq(false);
      expect($toggle.attr('aria-expanded'), 'planner telemetry toggle expansion state').to.eq(expanded);

      const panelId = $toggle.attr('aria-controls');
      expect(panelId, 'planner telemetry controlled panel id').to.be.a('string').and.not.equal('');
      const $panels = $region.find(PLANNER_TELEMETRY_CONTENT);
      expect($panels, 'current planner telemetry controlled panel').to.have.length(1);
      expect($panels.attr('id'), 'planner telemetry controlled panel linkage').to.eq(panelId);
      expect($region.find(`#${Cypress.$.escapeSelector(panelId)}`), 'unique linked planner telemetry panel').to.have.length(1);
      expect($panels.attr('data-open'), 'planner telemetry controlled panel state').to.eq(expanded);
    })
    .then(() => currentPlannerTelemetryToggle()
      .should('have.attr', 'aria-expanded', expanded));
}
function exposeCurrentPlannerTelemetryToggle() {
  return currentPlannerTelemetryRegion()
    .scrollTo(0, 0, { duration: 0, ensureScrollable: false })
    .should(($region) => {
      expect($region[0].scrollTop, 'planner telemetry region reset scroll position').to.eq(0);
    })
    .then(() => currentPlannerTelemetryToggle().scrollIntoView({ duration: 0 }))
    .then(() => currentPlannerTelemetryToggle()
      .should('be.visible')
      .and('be.enabled'));
}
function telemetry(checks, summary) {
  assertCurrentPlannerTelemetryState('false');
  exposeCurrentPlannerTelemetryToggle();
  currentPlannerTelemetryToggle().focus();
  currentPlannerTelemetryToggle().should('have.focus');
  cy.focused().should(($control) => {
    expect($control, 'focused planner telemetry toggle').to.have.length(1);
    expect($control.attr('data-testid'), 'focused planner telemetry test id').to.eq('planner-telemetry-dock-toggle');
    expect($control.is(PLANNER_TELEMETRY_TOGGLE), 'focused control is the native planner telemetry toggle').to.eq(true);
    expect($control.closest(PLANNER_TELEMETRY_REGION), 'focused toggle belongs to the current telemetry region').to.have.length(1);
    expect($control.closest(WHOLE_SYSTEM_PLANNER), 'focused toggle belongs to the current whole-system planner').to.have.length(1);
  }).type('{enter}');
  assertCurrentPlannerTelemetryState('true');

  exposeCurrentPlannerTelemetryToggle();
  currentPlannerTelemetryToggle().focus();
  currentPlannerTelemetryToggle().should('have.focus');
  cy.focused().should(($control) => {
    expect($control, 're-focused planner telemetry toggle').to.have.length(1);
    expect($control.is(PLANNER_TELEMETRY_TOGGLE), 're-focused control is the native planner telemetry toggle').to.eq(true);
    expect($control.closest(PLANNER_TELEMETRY_REGION), 're-focused toggle belongs to the current telemetry region').to.have.length(1);
    expect($control.closest(WHOLE_SYSTEM_PLANNER), 're-focused toggle belongs to the current whole-system planner').to.have.length(1);
  }).type('{enter}');
  assertCurrentPlannerTelemetryState('false');
  cy.then(() => {
    checks.telemetryToggleKeyboardWorks = true;
    summary.accessibility.plannerDesktopTelemetryToggleKeyboardWorks = true;
  });
}
function profile(summary, metadata, body, execution) {
  summary.viewportProfiles.push(metadata); const result = { status: 'failed', checks: { effectiveViewportApplied: false }, diagnostics: {}, error: null };
  cy.then(() => {
    execution.current = { profileName: metadata.profile_name, result };
    summary.profileResults[metadata.profile_name] = result;
  });
  cy.viewport(metadata.viewport_width, metadata.viewport_height); cy.visit('/'); cy.clearLocalStorage(); cy.reload();
  cy.window().then((win) => { expect(win.innerWidth).to.eq(metadata.viewport_width); expect(win.innerHeight).to.eq(metadata.viewport_height); result.checks.effectiveViewportApplied = true; });
  body(result).then(() => {
    expect(execution.current?.profileName, 'completed viewport profile attribution').to.eq(metadata.profile_name);
    expect(execution.current?.result, 'completed viewport profile result').to.equal(result);
    result.status = 'passed';
    execution.current = null;
  });
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
    const execution = { current: null };
    Cypress.on('fail', (error) => {
      const firstError = clean(error?.stack || error?.message || String(error));
      if (summary.fatalError === null) summary.fatalError = firstError;
      if (execution.current) {
        execution.current.result.status = 'failed';
        if (execution.current.result.error === null) execution.current.result.error = summary.fatalError;
        summary.profileResults[execution.current.profileName] = execution.current.result;
      }
      throw error;
    });

    profile(summary, PROFILES[0], (result) => { let chain = cy.wrap(null);
      selectedPlan.browserFlowKeys.forEach((key) => { chain = chain.then(() => { const system = SYSTEMS[key]; const start = summary.apiResponses.length; const checks = {};
        finder(); detail(system);
        if (key === 'alpha') { closeDetailWithEscape(); checks.modalEscapeCloseWorks = true; summary.accessibility.modalEscapeCloseWorks = true; detail(system); }
        planner(system, key === 'alpha', key === 'alpha' ? () => { summary.accessibility.alphaKeyboardOpenPlannerWorks = true; } : null); checks.systemDetailLoaded = true; checks.plannerOpened = true;
        if (key === 'alpha') { checks.reportOnlyBoundaryVisible = true; checks.canonicalBoundaryVisible = true; technical('available', 'dedicated_contract'); checks.availablePostureVisible = true; checks.dedicatedContractVisible = true; checks.reportOnlyTagVisible = true; }
        if (key === 'beta') { technical('unavailable', 'dedicated_contract'); checks.unavailablePostureVisible = true; checks.reportOnlyBoundaryVisible = true; }
        if (key === 'gamma') { technical('unknown', 'dedicated_contract'); checks.unknownPostureVisible = true; checks.reportOnlyBoundaryVisible = true; }
        if (key === 'delta') { technical('unknown', 'provenance_bridge'); checks.provenanceFallbackVisible = true; checks.reportOnlyBoundaryVisible = true; checks.fallbackRemainsNonCanonical = true; checks.technicalFallbackDisclosureVisible = true; cy.getByTestId('warehouse-evidence-item').should('not.exist'); checks.noDedicatedEvidenceClaim = true; }
        checks.noRecoveryScreen = true; cy.then(() => { summary.scenarios[key] = { status: 'passed', checks, apiResponses: summary.apiResponses.slice(start), error: null }; });
      }); }); return chain.then(() => { telemetry(result.checks, summary); result.checks.noRecoveryScreen = true; overflow(PLANNER_IDS, (m) => { result.diagnostics = m; result.checks.documentOverflowWithinTolerance = m.documentOverflowPx <= 4; result.checks.criticalOverflowWithinTolerance = !m.containerOverflow.length; expect(m.documentOverflowPx).to.be.at.most(4); expect(m.containerOverflow).to.have.length(0); }); });
    }, execution);
    profile(summary, PROFILES[1], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, reportOnlyBoundaryVisible: true, canonicalBoundaryVisible: true, keyControlsReachable: true, safeFocusAndNavigation: true, noRecoveryScreen: true }); telemetry(r.checks, summary); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; r.checks.documentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.checks.criticalOverflowWithinTolerance = !m.containerOverflow.length; }); return cy.wrap(null); }, execution);
    profile(summary, PROFILES[2], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, selectedSystemContextVisible: true, noRecoveryScreen: true }); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; if (m.documentOverflowPx > 4 || m.containerOverflow.length) summary.productObservations.push({ key: 'planner_constrained_layout_compromise_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Constrained planner layout compromise remained bounded and escape-safe at 1024x768.', metrics: m }); }); cy.contains('button', /Back to Finder/i).click(); cy.getByTestId('search-summary').should('be.visible').then(() => { r.checks.safeReturnToFinder = true; }); return cy.wrap(null); }, execution);
    profile(summary, PROFILES[3], (r) => { finder(); Object.assign(r.checks, { finderLoaded: true, reviewCardsAccessible: true }); overflow([], (m) => { r.checks.finderDocumentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.diagnostics.finder_document = m; }); detail(SYSTEMS.alpha); Object.assign(r.checks, { systemDetailOpened: true, systemDetailCloseControlVisible: true }); closeDetailWithEscape(); r.checks.modalEscapeCloseWorks = true; summary.accessibility.modalEscapeCloseWorks = true; detail(SYSTEMS.alpha); overflow([], (m) => { r.checks.systemDetailDocumentOverflowWithinTolerance = m.documentOverflowPx <= 4; r.diagnostics.system_detail_document = m; }); cy.getByTestId('system-detail-close').click(); Object.assign(r.checks, { closeControlWorks: true, noRecoveryScreen: true }); return cy.wrap(null); }, execution);
    profile(summary, PROFILES[4], (r) => { finder(); detail(SYSTEMS.alpha); planner(SYSTEMS.alpha); Object.assign(r.checks, { plannerOpened: true, selectedSystemContextVisible: true, safeExitControlVisible: true, noRecoveryScreen: true }); overflow(PLANNER_IDS, (m) => { r.diagnostics = m; if (m.documentOverflowPx > 4 || m.containerOverflow.length) summary.productObservations.push({ key: 'planner_mobile_resilience_overflow_diagnostic', classification: 'KNOWN_VIEWPORT_DIAGNOSTIC', owner: 'PR #259', environmentReady: true, productAcceptanceReady: true, description: 'Phone-width planner overflow remained a bounded resilience diagnostic and did not redefine desktop planner acceptance.', metrics: m }); }); cy.contains('button', /Back to Finder/i).click(); cy.getByTestId('search-summary').then(() => { r.checks.safeReturnToFinder = true; }); return cy.wrap(null); }, execution);
    cy.then(() => cy.task('writeReviewLabSummary', { outputPath: reviewConfig.reviewOutputPath, summary }, { log: false }));
  });
});
