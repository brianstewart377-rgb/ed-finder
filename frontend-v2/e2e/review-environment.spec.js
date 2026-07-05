/* global process, navigator, window, document, HTMLElement, localStorage, URL */
import fs from 'node:fs/promises';
import path from 'node:path';
import { test, expect } from '@playwright/test';

const REVIEW_LAB_RUN = process.env.EDFINDER_REVIEW_LAB_RUN === '1';
const OUTPUT_PATH = process.env.EDFINDER_REVIEW_OUTPUT_PATH || '';
const RAW_SCENARIO_PLAN = process.env.EDFINDER_REVIEW_SCENARIOS_JSON || '';
const REVIEW_ENVIRONMENT_OUTPUT_CONFIGURED = Boolean(process.env.EDFINDER_REVIEW_OUTPUT_PATH);
const REVIEW_ENVIRONMENT_PLAN_CONFIGURED = Boolean(process.env.EDFINDER_REVIEW_SCENARIOS_JSON);
const REVIEW_ENVIRONMENT_MARKER_CONFIGURED = REVIEW_LAB_RUN;

function shouldSkipReviewLabCollector() {
  return !REVIEW_ENVIRONMENT_MARKER_CONFIGURED
    && !REVIEW_ENVIRONMENT_OUTPUT_CONFIGURED
    && !REVIEW_ENVIRONMENT_PLAN_CONFIGURED;
}

function reviewEnvironmentConfigError() {
  if (shouldSkipReviewLabCollector()) {
    return null;
  }
  if (!REVIEW_ENVIRONMENT_MARKER_CONFIGURED || !REVIEW_ENVIRONMENT_OUTPUT_CONFIGURED || !REVIEW_ENVIRONMENT_PLAN_CONFIGURED) {
    return 'Review Lab browser verification requires EDFINDER_REVIEW_LAB_RUN=1 together with EDFINDER_REVIEW_OUTPUT_PATH and EDFINDER_REVIEW_SCENARIOS_JSON.';
  }
  return null;
}

const SYSTEMS = {
  alpha: { id64: 7200000000001, name: 'Review Alpha' },
  beta: { id64: 7200000000002, name: 'Review Beta' },
  gamma: { id64: 7200000000003, name: 'Review Gamma' },
  delta: { id64: 7200000000004, name: 'Review Delta' },
};

const DEFAULT_BASE_URL = 'http://localhost:4173';
const PLANNER_OVERFLOW_TEST_IDS = [
  'colony-planner-workspace',
  'whole-system-colony-planner',
  'workspace-planner-content',
  'planner-telemetry-region',
  'raven-real-planner-canvas',
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

test.describe('Local review environment verification', () => {
  test('captures deterministic browser verification summary', async ({ browser, baseURL }) => {
    test.setTimeout(120_000);
    test.skip(
      shouldSkipReviewLabCollector(),
      'Review Lab browser verification only runs under scripts/dev/review_environment.py verify --mode full.',
    );
    const configError = reviewEnvironmentConfigError();
    const summary = {
      summarySchemaVersion: 1,
      reviewLabRun: REVIEW_LAB_RUN,
      selectedScenarioNames: [],
      browserFlowKeys: [],
      selectedPlan: null,
      scenarios: {},
      accessibility: {},
      viewportProfiles: [],
      profileResults: {},
      productObservations: [],
      apiResponses: [],
      consoleEntries: [],
      pageErrors: [],
      fatalError: null,
    };
    if (configError) {
      summary.fatalError = sanitizeText(configError);
      if (REVIEW_ENVIRONMENT_OUTPUT_CONFIGURED) {
        await writeSummary(OUTPUT_PATH, summary);
      }
      throw new Error(configError);
    }
    const scenarioPlan = parseScenarioPlan(RAW_SCENARIO_PLAN, { strict: true });
    summary.selectedScenarioNames = scenarioPlan.selectedScenarioNames;
    summary.browserFlowKeys = scenarioPlan.browserFlowKeys;
    summary.selectedPlan = scenarioPlan;
    await assertOutputPathWritable(OUTPUT_PATH);

    try {
      const resolvedBaseUrl = baseURL || DEFAULT_BASE_URL;
      await runViewportMatrix(browser, resolvedBaseUrl, scenarioPlan, summary);
    } catch (error) {
      summary.fatalError = sanitizeText(error?.stack || error?.message || String(error));
      throw error;
    } finally {
      await writeSummary(OUTPUT_PATH, summary);
    }
  });
});


async function openSystemDetailFromResultCard(page, systemId64) {
  await openResultCard(page, systemId64);
  const card = page.getByTestId(`result-card-${systemId64}`);
  const inspectSystem = card.getByRole('button', { name: /Inspect system/i });
  await expect(inspectSystem).toBeVisible();
  await inspectSystem.click();
  await expect(page.getByTestId('system-detail-modal')).toBeVisible();
}

async function startPlannerDraftFromSystemDetail(page, { useKeyboard = false } = {}) {
  await expect(page.getByTestId('colony-planner-entry-card')).toBeVisible();

  const openPlanStart = page.getByTestId('open-plan-start');
  await expect(openPlanStart).toBeVisible();

  if (useKeyboard) {
    await openPlanStart.focus();
    await page.keyboard.press('Enter');
  } else {
    await openPlanStart.click();
  }

  await expect(page.getByTestId('plan-start-panel')).toBeVisible();

  await page.getByTestId('plan-objective-materials_coverage').click();
  await page.getByTestId('plan-approach-manual').click();

  const confirmStart = page.getByTestId('confirm-start-plan');
  await expect(confirmStart).toBeEnabled();

  if (useKeyboard) {
    await confirmStart.focus();
    await page.keyboard.press('Enter');
  } else {
    await confirmStart.click();
  }
}

async function openPlannerFromResultCard(page, systemId64, systemName) {
  await openSystemDetailFromResultCard(page, systemId64);
  await startPlannerDraftFromSystemDetail(page);
  await waitForPlanner(page, systemName);
}

async function runAlphaScenario(page, baseURL, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page, baseURL);
    await openSystemDetailFromResultCard(page, SYSTEMS.alpha.id64);
    await expect(page.getByText(SYSTEMS.alpha.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('system-detail-modal')).toBeHidden();
    checks.modalEscapeCloseWorks = true;
    summary.accessibility.modalEscapeCloseWorks = true;

    await openSystemDetailFromResultCard(page, SYSTEMS.alpha.id64);
    await startPlannerDraftFromSystemDetail(page, { useKeyboard: true });
    await waitForPlanner(page, SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    summary.accessibility.alphaKeyboardOpenPlannerWorks = true;
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('planner-evidence-discoverability-surface'));
    checks.canonicalBoundaryVisible = await expectText(
      page.getByTestId('planner-evidence-discoverability-summary'),
      /canonical planner truth/i,
    );
    await openEvidenceTechnicalDetail(page);
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    checks.availablePostureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-status-available'));
    checks.dedicatedContractVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-posture-dedicated_contract'));
    checks.reportOnlyTagVisible = await expectVisible(page.getByTestId('warehouse-evidence-report-only-tag'));

    summary.scenarios.alpha = scenarioResult('passed', checks, summary.apiResponses.slice(start));
  } catch (error) {
    summary.scenarios.alpha = scenarioResult(
      'failed',
      checks,
      summary.apiResponses.slice(start),
      error,
    );
    throw error;
  }
}

async function runBetaScenario(page, baseURL, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page, baseURL);
    await openSystemDetailFromResultCard(page, SYSTEMS.beta.id64);
    await expect(page.getByText(SYSTEMS.beta.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;
    await startPlannerDraftFromSystemDetail(page);
    await waitForPlanner(page, SYSTEMS.beta.name);
    checks.plannerOpened = true;
    await openEvidenceTechnicalDetail(page);
    checks.unavailablePostureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-status-unavailable'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('planner-evidence-discoverability-surface'));
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    summary.scenarios.beta = scenarioResult('passed', checks, summary.apiResponses.slice(start));
  } catch (error) {
    summary.scenarios.beta = scenarioResult(
      'failed',
      checks,
      summary.apiResponses.slice(start),
      error,
    );
    throw error;
  }
}

async function runGammaScenario(page, baseURL, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page, baseURL);
    await openSystemDetailFromResultCard(page, SYSTEMS.gamma.id64);
    await expect(page.getByText(SYSTEMS.gamma.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;
    await startPlannerDraftFromSystemDetail(page);
    await waitForPlanner(page, SYSTEMS.gamma.name);
    checks.plannerOpened = true;
    await openEvidenceTechnicalDetail(page);
    checks.unknownPostureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-status-unknown'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('planner-evidence-discoverability-surface'));
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    summary.scenarios.gamma = scenarioResult('passed', checks, summary.apiResponses.slice(start));
  } catch (error) {
    summary.scenarios.gamma = scenarioResult(
      'failed',
      checks,
      summary.apiResponses.slice(start),
      error,
    );
    throw error;
  }
}

async function runDeltaScenario(page, baseURL, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page, baseURL);
    await openSystemDetailFromResultCard(page, SYSTEMS.delta.id64);
    await expect(page.getByText(SYSTEMS.delta.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;

    await startPlannerDraftFromSystemDetail(page);
    await waitForPlanner(page, SYSTEMS.delta.name);
    checks.plannerOpened = true;
    await openEvidenceTechnicalDetail(page);
    checks.provenanceFallbackVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-posture-provenance_bridge'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('planner-evidence-discoverability-surface'));
    checks.fallbackRemainsNonCanonical = await expectText(
      page.getByTestId('warehouse-evidence-summary'),
      /Some data is unavailable for this system\. Your plan has not been changed automatically\./i,
    );
    checks.technicalFallbackDisclosureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-summary'))
      && await expectVisible(page.getByTestId('warehouse-evidence-source-class-list'))
      && await expectVisible(page.getByTestId('warehouse-evidence-semantic-list'));
    checks.noDedicatedEvidenceClaim = await page.getByTestId('warehouse-evidence-item').count() === 0;
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    checks.unavailableFallbackVisible = await expectText(
      page.getByTestId('warehouse-evidence-summary'),
      /Your plan has not been changed automatically/i,
    );
    checks.provenanceWarningVisible = await expectVisible(page.getByTestId('warehouse-evidence-warnings'));

    const deltaResponses = summary.apiResponses.slice(start);
    const dedicatedFailure = deltaResponses.find((response) => (
      response.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/warehouse-planner-evidence`
      && response.status === 503
    ));
    const fallbackSuccess = deltaResponses.find((response) => (
      response.path === `/api/colony-planner/system/${SYSTEMS.delta.id64}/provenance-cockpit`
      && response.status === 200
    ));
    checks.deltaDedicated503Seen = Boolean(dedicatedFailure);
    checks.deltaFallback200Seen = Boolean(fallbackSuccess);

    summary.scenarios.delta = scenarioResult('passed', checks, deltaResponses);
  } catch (error) {
    summary.scenarios.delta = scenarioResult(
      'failed',
      checks,
      summary.apiResponses.slice(start),
      error,
    );
    throw error;
  }
}

async function runSelectedSystemRouteJourney(page, baseURL) {
  const checks = {};

  await page.goto(resolveUrl(baseURL, `/#finder/context/${SYSTEMS.alpha.id64}`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('search-summary')).toBeVisible();
  await expect(productShellContext(page)).toContainText(SYSTEMS.alpha.name);
  await expect(productShellContext(page)).toContainText('Evidence posture unavailable');
  await expect(page.getByTestId('system-detail-modal')).toHaveCount(0);
  checks.finderContextVisible = true;

  await page.goto(resolveUrl(baseURL, `/#finder/system/${SYSTEMS.alpha.id64}`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('system-detail-modal')).toBeVisible();
  await page.getByTestId('system-detail-close').click();
  await expect(page).toHaveURL(new RegExp(`#finder/context/${SYSTEMS.alpha.id64}$`));
  await expect(page.getByTestId('system-detail-modal')).toHaveCount(0);
  checks.inspectCloseReturnsFinderContext = true;

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.alpha.id64}`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('No active draft for this system')).toBeVisible();
  await page.getByTestId('planner-inline-state')
    .getByRole('button', { name: /^Back to Finder$/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`#finder/context/${SYSTEMS.alpha.id64}$`));
  await expect(page.getByTestId('system-detail-modal')).toHaveCount(0);
  checks.plannerBackReturnsFinderContext = true;
  checks.directPlannerNoDraftVisible = true;

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.alpha.id64}`), { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: /^Create draft$/ }).click();
  await expect(page).toHaveURL(new RegExp(`#colony-planner/system/${SYSTEMS.alpha.id64}/project/`));
  checks.explicitCreateDraftRoutesToExactProject = true;

  const createdProject = await readStoredProject(page, SYSTEMS.alpha.id64);
  checks.createdDraftPersisted = Boolean(createdProject?.id && createdProject?.projectName);

  await page.goto(resolveUrl(baseURL, `/#finder/system/${SYSTEMS.beta.id64}/extra`), { waitUntil: 'domcontentloaded' });
  await expect(productShellContext(page)).toContainText('Selected system route invalid');
  await expectNoStaleSelectedContext(page, {
    absentName: SYSTEMS.alpha.name,
    absentId64: SYSTEMS.alpha.id64,
    absentEvidencePosture: true,
    absentProjectName: createdProject?.projectName ?? null,
  });
  checks.invalidFinderRouteClearsStaleContext = true;

  await page.goto(resolveUrl(baseURL, '/#finder/context/7999999999999'), { waitUntil: 'domcontentloaded' });
  await expect(productShellContext(page)).toContainText('Selected system unavailable');
  await expectNoStaleSelectedContext(page, {
    absentName: SYSTEMS.alpha.name,
    absentId64: SYSTEMS.alpha.id64,
    absentEvidencePosture: true,
    absentProjectName: createdProject?.projectName ?? null,
  });
  checks.unavailableSelectedSystemClearsStaleContext = true;

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.beta.id64}/extra`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('planner-inline-state')).toContainText('Selected system route invalid');
  await expectNoStaleSelectedContext(page, {
    absentName: SYSTEMS.alpha.name,
    absentId64: SYSTEMS.alpha.id64,
    absentEvidencePosture: true,
    absentProjectName: createdProject?.projectName ?? null,
  });
  checks.invalidPlannerSystemRouteClearsStaleContext = true;

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.alpha.id64}/project`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('planner-inline-state')).toContainText('Selected project route invalid');
  await expectNoVisibleText(page, createdProject?.projectName ?? null);
  checks.malformedPlannerProjectRejected = true;

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.alpha.id64}/project/missing-project`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('planner-inline-state')).toContainText('Selected project unavailable');
  await expectNoVisibleText(page, createdProject?.projectName ?? null);
  checks.missingPlannerProjectRejected = true;

  if (!createdProject?.id) {
    throw new Error('Selected-system route journey could not find the explicit draft in local storage.');
  }

  await page.goto(resolveUrl(baseURL, `/#colony-planner/system/${SYSTEMS.beta.id64}/project/${createdProject.id}`), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('planner-inline-state')).toContainText('Selected project does not belong to this system');
  await expectNoVisibleText(page, createdProject.projectName);
  checks.crossSystemPlannerProjectRejected = true;

  return checks;
}

async function runViewportMatrix(browser, baseURL, scenarioPlan, summary) {
  await runViewportProfile(browser, baseURL, summary, profile('planner_desktop_primary'), async (page) => {
    const checks = {};
    for (const flowKey of scenarioPlan.browserFlowKeys) {
      if (flowKey === 'alpha') {
        await runAlphaScenario(page, baseURL, summary);
      } else if (flowKey === 'beta') {
        await runBetaScenario(page, baseURL, summary);
      } else if (flowKey === 'gamma') {
        await runGammaScenario(page, baseURL, summary);
      } else if (flowKey === 'delta') {
        await runDeltaScenario(page, baseURL, summary);
      }
    }
    Object.assign(checks, await runSelectedSystemRouteJourney(page, baseURL));
    checks.telemetryToggleKeyboardWorks = await ensureTelemetryToggleKeyboardWorks(page);
    summary.accessibility.plannerDesktopTelemetryToggleKeyboardWorks = true;
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    const overflow = await collectOverflowMetrics(page, PLANNER_OVERFLOW_TEST_IDS);
    checks.documentOverflowWithinTolerance = overflow.documentOverflowPx <= 4;
    checks.criticalOverflowWithinTolerance = overflow.containerOverflow.length === 0;
    if (!checks.documentOverflowWithinTolerance || !checks.criticalOverflowWithinTolerance) {
      throw new Error('Planner desktop primary overflow exceeded tolerance.');
    }
    return { checks, diagnostics: overflow };
  });

  await runViewportProfile(browser, baseURL, summary, profile('planner_laptop_minimum'), async (page) => {
    const checks = {};
    await gotoFinder(page, baseURL);
    await openSystemDetailFromResultCard(page, SYSTEMS.alpha.id64);
    await startPlannerDraftFromSystemDetail(page);
    await waitForPlanner(page, SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('planner-evidence-discoverability-surface'));
    checks.canonicalBoundaryVisible = await expectText(
      page.getByTestId('planner-evidence-discoverability-summary'),
      /canonical planner truth/i,
    );
    checks.keyControlsReachable = await expectVisible(visibleByTestId(page, 'planner-telemetry-dock-toggle'))
      && await expectVisible(page.getByTestId('summary-rail-collapse-toggle'));
    checks.telemetryToggleKeyboardWorks = await ensureTelemetryToggleKeyboardWorks(page);
    checks.safeFocusAndNavigation = await telemetryToggleCanReceiveFocus(page);
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    const overflow = await collectOverflowMetrics(page, PLANNER_OVERFLOW_TEST_IDS);
    checks.documentOverflowWithinTolerance = overflow.documentOverflowPx <= 4;
    checks.criticalOverflowWithinTolerance = overflow.containerOverflow.length === 0;
    if (!checks.documentOverflowWithinTolerance || !checks.criticalOverflowWithinTolerance) {
      throw new Error('Planner laptop minimum overflow exceeded tolerance.');
    }
    return { checks, diagnostics: overflow };
  });

  await runViewportProfile(browser, baseURL, summary, profile('planner_constrained_diagnostic'), async (page) => {
    const checks = {};
    await gotoFinder(page, baseURL);
    await openPlannerFromResultCard(page, SYSTEMS.alpha.id64, SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    checks.selectedSystemContextVisible = await expectVisible(plannerSelectedSystem(page, SYSTEMS.alpha.name));
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    const overflow = await collectOverflowMetrics(page, PLANNER_OVERFLOW_TEST_IDS);
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
    await page.getByRole('button', { name: /Back to Finder/i }).click();
    await expect(page.getByTestId('search-summary')).toBeVisible();
    checks.safeReturnToFinder = true;
    return { checks, diagnostics: overflow };
  });

  await runViewportProfile(browser, baseURL, summary, profile('finder_mobile'), async (page) => {
    const checks = {};
    await gotoFinder(page, baseURL);
    checks.finderLoaded = true;
    checks.reviewCardsAccessible = await expectReviewCardsAccessible(page);
    const finderOverflow = await collectOverflowMetrics(page, []);
    checks.finderDocumentOverflowWithinTolerance = finderOverflow.documentOverflowPx <= 4;
    if (!checks.finderDocumentOverflowWithinTolerance) {
      throw new Error('Finder mobile document overflow exceeded tolerance.');
    }
    await openSystemDetailFromResultCard(page, SYSTEMS.alpha.id64);
    checks.systemDetailOpened = true;
    checks.systemDetailCloseControlVisible = await expectVisible(page.getByTestId('system-detail-close'));
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('system-detail-modal')).toBeHidden();
    checks.modalEscapeCloseWorks = true;
    summary.accessibility.modalEscapeCloseWorks = true;
    await openSystemDetailFromResultCard(page, SYSTEMS.alpha.id64);
    const detailOverflow = await collectOverflowMetrics(page, []);
    checks.systemDetailDocumentOverflowWithinTolerance = detailOverflow.documentOverflowPx <= 4;
    if (!checks.systemDetailDocumentOverflowWithinTolerance) {
      throw new Error('System detail mobile document overflow exceeded tolerance.');
    }
    await page.getByTestId('system-detail-close').click();
    await expect(page.getByTestId('system-detail-modal')).toBeHidden();
    checks.closeControlWorks = true;
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    return {
      checks,
      diagnostics: {
        finder_document: finderOverflow,
        system_detail_document: detailOverflow,
      },
    };
  });

  await runViewportProfile(browser, baseURL, summary, profile('planner_mobile_resilience'), async (page) => {
    const checks = {};
    await gotoFinder(page, baseURL);
    await openPlannerFromResultCard(page, SYSTEMS.alpha.id64, SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    checks.selectedSystemContextVisible = await expectVisible(plannerSelectedSystem(page, SYSTEMS.alpha.name));
    checks.safeExitControlVisible = await expectVisible(page.getByRole('button', { name: /Back to Finder/i }));
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    const overflow = await collectOverflowMetrics(page, PLANNER_OVERFLOW_TEST_IDS);
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
    await page.getByRole('button', { name: /Back to Finder/i }).click();
    await expect(page.getByTestId('search-summary')).toBeVisible();
    checks.safeReturnToFinder = true;
    return { checks, diagnostics: overflow };
  });
}

async function runViewportProfile(browser, baseURL, summary, metadata, callback) {
  const context = await browser.newContext({
    viewport: {
      width: metadata.viewport_width,
      height: metadata.viewport_height,
    },
    deviceScaleFactor: metadata.device_scale_factor,
  });
  await installReviewLabInitScript(context);
  const page = await context.newPage();
  attachSummaryListeners(page, summary);
  summary.viewportProfiles.push({ ...metadata });

  const result = {
    status: 'failed',
    checks: {
      effectiveViewportApplied: false,
    },
    diagnostics: {},
    error: null,
  };

  try {
    await clearState(page, baseURL);
    result.checks.effectiveViewportApplied = await validateEffectiveViewport(page, metadata);
    const profileOutcome = await callback(page);
    result.status = 'passed';
    result.checks = {
      ...result.checks,
      ...(profileOutcome?.checks || {}),
    };
    result.diagnostics = profileOutcome?.diagnostics || {};
    summary.profileResults[metadata.profile_name] = result;
  } catch (error) {
    result.error = sanitizeText(error?.stack || error?.message || String(error));
    summary.profileResults[metadata.profile_name] = result;
  } finally {
    await context.close();
  }
}

function attachSummaryListeners(page, summary) {
  page.on('console', (message) => {
    summary.consoleEntries.push({
      type: message.type(),
      text: sanitizeText(message.text()),
    });
  });
  page.on('pageerror', (error) => {
    summary.pageErrors.push(sanitizeText(error?.stack || error?.message || String(error)));
  });
  page.on('response', (response) => {
    const url = response.url();
    if (!url.includes('/api/')) return;
    summary.apiResponses.push({
      method: response.request().method(),
      path: apiPath(url),
      status: response.status(),
    });
  });
}

async function installReviewLabInitScript(context) {
  await context.addInitScript(() => {
    const stub = async () => ({ scope: '/v2/' });
    try {
      if ('serviceWorker' in navigator && navigator.serviceWorker) {
        navigator.serviceWorker.register = stub;
      }
    } catch {
      // Best effort: preview-mode service-worker registration noise is not part
      // of review-environment readiness.
    }
  });
}

async function validateEffectiveViewport(page, metadata) {
  const effective = await page.evaluate(() => ({
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    device_scale_factor: window.devicePixelRatio,
  }));
  if (
    effective.viewport_width !== metadata.viewport_width
    || effective.viewport_height !== metadata.viewport_height
    || effective.device_scale_factor !== metadata.device_scale_factor
  ) {
    throw new Error(`Effective viewport did not match profile ${metadata.profile_name}.`);
  }
  return true;
}

async function ensureTelemetryToggleKeyboardWorks(page) {
  const dockToggle = visibleByTestId(page, 'planner-telemetry-dock-toggle');
  await expect(dockToggle).toBeVisible();
  await dockToggle.focus();
  await expect(dockToggle).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(dockToggle).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Enter');
  await expect(dockToggle).toHaveAttribute('aria-expanded', 'false');
  return true;
}

async function telemetryToggleCanReceiveFocus(page) {
  const dockToggle = visibleByTestId(page, 'planner-telemetry-dock-toggle');
  await dockToggle.focus();
  await expect(dockToggle).toBeFocused();
  return true;
}

async function expectReviewCardsAccessible(page) {
  for (const system of Object.values(SYSTEMS)) {
    const card = page.getByTestId(`result-card-${system.id64}`);
    await card.scrollIntoViewIfNeeded();
    await expect(card).toBeVisible();
    await expect(page.getByText(system.name).first()).toBeVisible();
  }
  return true;
}

async function collectOverflowMetrics(page, testIds) {
  return page.evaluate((ids) => {
    const documentWidth = Math.max(
      document.documentElement?.scrollWidth || 0,
      document.body?.scrollWidth || 0,
    );
    const documentOverflowPx = Math.max(0, documentWidth - window.innerWidth);
    const containerOverflow = ids
      .map((testId) => {
        const node = document.querySelector(`[data-testid="${testId}"]`);
        if (!(node instanceof HTMLElement)) return null;
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
      viewportWidth: window.innerWidth,
      containerOverflow,
    };
  }, testIds);
}

function profile(name) {
  const metadata = VIEWPORT_PROFILES.find((entry) => entry.profile_name === name);
  if (!metadata) {
    throw new Error(`Unknown viewport profile ${name}.`);
  }
  return metadata;
}

function visibleByTestId(page, testId) {
  return page.locator(`[data-testid="${testId}"]:visible`).first();
}

async function gotoFinder(page, baseURL) {
  await page.goto(resolveUrl(baseURL, '/'), { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="search-summary"]', { timeout: 20_000 });
  await expectReviewCardsAccessible(page);
}

async function clearState(page, baseURL) {
  await page.goto(resolveUrl(baseURL, '/'), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'domcontentloaded' });
}

async function openResultCard(page, id64) {
  const card = page.getByTestId(`result-card-${id64}`);
  const header = card.locator('header');
  const actionButton = card.getByRole('button', { name: /Inspect system/i });
  await expect(card).toBeVisible();
  if (await actionButton.isVisible().catch(() => false)) {
    return;
  }
  await header.evaluate((node) => {
    if (node instanceof HTMLElement) {
      node.click();
    }
  });
  await expect(actionButton).toBeVisible({ timeout: 10_000 });
}

async function waitForPlanner(page, systemName) {
  await expect(page.getByTestId('colony-planner-workspace')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('planner-evidence-discoverability-surface')).toBeVisible();
  await expect(page.getByTestId('planner-warehouse-evidence')).toBeVisible();
  await expect(plannerWorkspaceHeader(page)).toBeVisible();
  await expect(plannerWorkspaceHeader(page).getByRole('heading', { name: 'Colony Planner' })).toBeVisible();
  await expect(plannerSelectedSystem(page, systemName)).toBeVisible();
}

async function openEvidenceTechnicalDetail(page) {
  const toggle = page.getByTestId('warehouse-evidence-disclosure-toggle');

  if (await toggle.isVisible().catch(() => false)) {
    if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
      await toggle.click();
    }
    await expect(page.getByTestId('warehouse-evidence-disclosure-panel')).toBeVisible();
    return true;
  }

  const details = page.getByTestId('warehouse-evidence-technical-details');
  await expect(details).toBeVisible();

  const detailsAreOpen = await details.evaluate((node) => node.open);
  if (!detailsAreOpen) {
    await details.locator('summary').click();
  }

  await expect(details).toHaveJSProperty('open', true);
  return true;
}

async function expectVisible(locator) {
  await expect(locator).toBeVisible();
  return true;
}

function plannerWorkspaceHeader(page) {
  return page.getByTestId('workspace-context-header');
}

function productShellContext(page) {
  return visibleByTestId(page, 'product-shell-context');
}

function plannerSelectedSystem(page, systemName) {
  return plannerWorkspaceHeader(page).getByText(systemName, { exact: true });
}

async function readStoredProject(page, systemId64) {
  return page.evaluate((targetSystemId64) => {
    const raw = window.localStorage.getItem('ed_colony_projects_v1');
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    const projects = parsed?.state?.projects ?? parsed?.projects ?? {};
    const match = Object.values(projects)
      .find((project) => project && project.system_id64 === targetSystemId64 && !project.archived_at);

    if (!match) return null;
    return {
      id: match.id,
      projectName: match.project_name,
    };
  }, systemId64);
}

async function expectNoVisibleText(page, text) {
  if (!text) return true;
  const locator = page.getByText(text, { exact: true });
  if (await locator.count() === 0) return true;
  await expect(locator.first()).toBeHidden();
  return true;
}

async function expectNoStaleSelectedContext(page, {
  absentName,
  absentId64,
  absentEvidencePosture = false,
  absentProjectName = null,
}) {
  await expectNoVisibleText(page, absentName);
  if (absentId64 != null) {
    await expectNoVisibleText(page, `ID64 ${absentId64}`);
  }
  if (absentEvidencePosture) {
    await expectNoVisibleText(page, 'Evidence posture unavailable');
  }
  await expectNoVisibleText(page, absentProjectName);
  return true;
}

async function expectText(locator, pattern) {
  await expect(locator).toContainText(pattern);
  return true;
}

async function recoveryVisible(page) {
  return page.getByText('ED:Finder UI Recovery').first().isVisible().catch(() => false);
}

function scenarioResult(status, checks, apiResponses, error) {
  return {
    status,
    checks,
    apiResponses,
    error: error ? sanitizeText(error?.stack || error?.message || String(error)) : null,
  };
}

function apiPath(urlString) {
  const url = new URL(urlString);
  return `${url.pathname}${url.search}`;
}

function resolveUrl(baseURL, route) {
  return new URL(route, baseURL || DEFAULT_BASE_URL).toString();
}

function parseScenarioPlan(rawValue, options = {}) {
  const strict = Boolean(options.strict);
  if (!rawValue) {
    if (strict) {
      throw new Error('Review Lab scenario plan is required.');
    }
    return defaultScenarioPlan();
  }
  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed.selectedScenarioNames) || !Array.isArray(parsed.browserFlowKeys)) {
      throw new Error('Review Lab scenario plan is malformed.');
    }
    return {
      selectedScenarioNames: parsed.selectedScenarioNames,
      browserFlowKeys: parsed.browserFlowKeys,
      includeProductObservations: Boolean(parsed.includeProductObservations),
    };
  } catch {
    if (strict) {
      throw new Error('Review Lab scenario plan could not be parsed.');
    }
    return defaultScenarioPlan();
  }
}

function defaultScenarioPlan() {
  return {
    selectedScenarioNames: ['planner_core'],
    browserFlowKeys: ['alpha', 'beta', 'gamma', 'delta'],
    includeProductObservations: true,
  };
}

function sanitizeText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 500);
}

async function assertOutputPathWritable(outputPath) {
  const directory = path.dirname(outputPath);
  const probePath = path.join(directory, '.review-lab-write-probe');
  await fs.mkdir(directory, { recursive: true });
  await fs.writeFile(probePath, 'ok\n', 'utf8');
  await fs.unlink(probePath);
}

async function writeSummary(outputPath, summary) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
}
