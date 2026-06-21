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

test.describe('Local review environment verification', () => {
  test('captures deterministic browser verification summary', async ({ page }) => {
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

    await page.addInitScript(() => {
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

    try {
      await clearState(page);
      for (const flowKey of scenarioPlan.browserFlowKeys) {
        if (flowKey === 'alpha') {
          await runAlphaScenario(page, summary);
        } else if (flowKey === 'beta') {
          await runBetaScenario(page, summary);
        } else if (flowKey === 'gamma') {
          await runGammaScenario(page, summary);
        } else if (flowKey === 'delta') {
          await runDeltaScenario(page, summary);
        }
      }
      if (scenarioPlan.includeProductObservations) {
        await runMobileObservation(page, summary);
      }
    } catch (error) {
      summary.fatalError = sanitizeText(error?.stack || error?.message || String(error));
      throw error;
    } finally {
      await writeSummary(OUTPUT_PATH, summary);
    }
  });
});

async function runAlphaScenario(page, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page);
    await openResultCard(page, SYSTEMS.alpha.id64);
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByTestId('system-detail-modal')).toBeVisible();
    await expect(page.getByText(SYSTEMS.alpha.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('system-detail-modal')).toBeHidden();
    checks.modalEscapeCloseWorks = true;
    summary.accessibility.modalEscapeCloseWorks = true;

    await openResultCard(page, SYSTEMS.alpha.id64);
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByTestId('system-detail-modal')).toBeVisible();
    const openPlanner = page.getByTestId('open-colony-planner');
    await openPlanner.focus();
    await page.keyboard.press('Enter');
    await waitForPlanner(page, SYSTEMS.alpha.name);
    checks.plannerOpened = true;
    summary.accessibility.alphaKeyboardOpenPlannerWorks = true;
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-boundary'));
    checks.canonicalBoundaryVisible = await expectText(
      page.getByTestId('planner-evidence-discoverability-highlights'),
      /Planner truth stays canonical/i,
    );
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

async function runBetaScenario(page, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page);
    await openResultCard(page, SYSTEMS.beta.id64);
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByTestId('system-detail-modal')).toBeVisible();
    await expect(page.getByText(SYSTEMS.beta.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;
    await page.getByTestId('open-colony-planner').click();
    await waitForPlanner(page, SYSTEMS.beta.name);
    checks.plannerOpened = true;
    checks.unavailablePostureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-status-unavailable'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-boundary'));
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

async function runGammaScenario(page, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page);
    await openResultCard(page, SYSTEMS.gamma.id64);
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByTestId('system-detail-modal')).toBeVisible();
    await expect(page.getByText(SYSTEMS.gamma.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;
    await page.getByTestId('open-colony-planner').click();
    await waitForPlanner(page, SYSTEMS.gamma.name);
    checks.plannerOpened = true;
    checks.unknownPostureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-status-unknown'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-boundary'));
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

async function runDeltaScenario(page, summary) {
  const start = summary.apiResponses.length;
  const checks = {};
  try {
    await gotoFinder(page);
    await openResultCard(page, SYSTEMS.delta.id64);
    await page.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByTestId('system-detail-modal')).toBeVisible();
    await expect(page.getByText(SYSTEMS.delta.name).first()).toBeVisible();
    checks.systemDetailLoaded = true;

    await page.getByTestId('open-colony-planner').click();
    await waitForPlanner(page, SYSTEMS.delta.name);
    checks.plannerOpened = true;
    checks.provenanceFallbackVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-posture-provenance_bridge'));
    checks.reportOnlyBoundaryVisible = await expectVisible(page.getByTestId('warehouse-evidence-source-boundary'));
    checks.fallbackRemainsNonCanonical = await expectText(
      page.getByTestId('warehouse-evidence-discoverability-highlights'),
      /Not canonical truth/i,
    );
    checks.technicalFallbackDisclosureVisible = await expectVisible(page.getByTestId('warehouse-evidence-envelope-summary'))
      && await expectVisible(page.getByTestId('warehouse-evidence-source-class-list'))
      && await expectVisible(page.getByTestId('warehouse-evidence-semantic-list'));
    checks.noDedicatedEvidenceClaim = await page.getByTestId('warehouse-evidence-item').count() === 0;
    checks.noRecoveryScreen = !(await recoveryVisible(page));
    checks.unavailableFallbackVisible = await expectVisible(page.getByTestId('warehouse-evidence-unavailable'));
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

async function runMobileObservation(page, summary) {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoFinder(page);
  await openResultCard(page, SYSTEMS.delta.id64);
  await page.getByRole('button', { name: /Evaluate in Colony Planner/i }).click();
  await waitForPlanner(page, SYSTEMS.delta.name);

  const dockToggle = page.getByTestId('planner-telemetry-dock-toggle');
  await expect(dockToggle).toBeVisible();
  await dockToggle.focus();
  await page.keyboard.press('Enter');
  await expect(dockToggle).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Enter');
  await expect(dockToggle).toHaveAttribute('aria-expanded', 'false');
  summary.accessibility.mobileTelemetryToggleKeyboardWorks = true;

  const overflow = await page.evaluate(() => {
    const testIds = [
      'colony-planner-workspace',
      'whole-system-colony-planner',
      'workspace-planner-content',
      'planner-telemetry-region',
      'raven-real-planner-canvas',
    ];
    return testIds
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
  });

  if (overflow.length > 0) {
    summary.productObservations.push({
      key: 'known-pr259-narrow-viewport-planner-overflow',
      classification: 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
      owner: 'PR #259',
      environmentReady: true,
      productAcceptanceReady: false,
      description: 'Narrow viewport planner overflow remains visible in the mobile review journey.',
      metrics: overflow,
    });
  }
}

async function gotoFinder(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="search-summary"]', { timeout: 20_000 });
  await expect(page.getByText(SYSTEMS.alpha.name).first()).toBeVisible();
  await expect(page.getByText(SYSTEMS.beta.name).first()).toBeVisible();
  await expect(page.getByText(SYSTEMS.gamma.name).first()).toBeVisible();
  await expect(page.getByText(SYSTEMS.delta.name).first()).toBeVisible();
}

async function clearState(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'domcontentloaded' });
}

async function openResultCard(page, id64) {
  const card = page.getByTestId(`result-card-${id64}`);
  const header = card.locator('header');
  const actionButton = card.getByRole('button', { name: /Details|Evaluate in Colony Planner/i }).first();
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
  await expect(page.getByText(systemName).first()).toBeVisible();
}

async function expectVisible(locator) {
  await expect(locator).toBeVisible();
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
