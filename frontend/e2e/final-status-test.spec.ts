import { test, expect } from '@playwright/test';

// Manual status/diagnostic probe. It deliberately emits broad console/API
// diagnostics and a screenshot; the canonical required flows live in smoke.spec.ts.
test.skip(
  process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true',
  'manual status diagnostic; run explicitly when investigating E2E state',
);

test('comprehensive E2E status check', async ({ page }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║        COMPREHENSIVE E2E STATUS CHECK                       ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture page errors (for robustness)
  const pageErrors: string[] = [];
  const errorHandler = (error: Error) => {
    pageErrors.push(error.message);
    console.log(`[PAGE ERROR] ${error.message}`);
  };
  page.on('pageerror', errorHandler);

  try {
    // API health
    const apiHealth = await fetch('http://localhost:8000/api/health').then(r => r.json()).catch(e => ({ error: e.message }));
    console.log('✓ API Status:', JSON.stringify(apiHealth));

    // Navigate to app using hash-based routing
    console.log('\n✓ Navigating to /#map (hash-based routing)...');
    await page.goto('/#map');
    await page.waitForTimeout(5000);

    // Capture all info
    const title = await page.title();
    console.log(`✓ Page Title: ${title}`);

    const url = page.url();
    console.log(`✓ Current URL: ${url}`);

    // Check for canvas
    const canvasCount = await page.locator('canvas').count();
    console.log(`✓ Canvas Elements: ${canvasCount}`);
    expect(canvasCount).toBeGreaterThan(0);

    // Check for map viewport
    const viewportCount = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
    console.log(`✓ Map Viewport Elements: ${viewportCount}`);

    // Check for Three.js scene
    const sceneElements = await page.locator('[class*="scene"],[data-testid*="scene"]').count();
    console.log(`✓ Scene Elements: ${sceneElements}`);

    // Capture console logs
    const consoleLogs: string[] = [];
    const consoleHandler = (msg: any) => {
      const text = msg.text();
      if (text.includes('[viewport-systems]') || text.includes('Real') || text.includes('Stars')) {
        consoleLogs.push(text);
        console.log(`  [CONSOLE] ${text}`);
      }
    };
    page.on('console', consoleHandler);

    // Check API calls
    const apiCalls: { method: string; url: string }[] = [];
    const responseHandler = (response: any) => {
      if (response.url().includes('/api/map')) {
        apiCalls.push({
          method: 'GET',
          url: response.url().split('?')[0]
        });
        console.log(`  [API] ${response.status()} ${response.url().split('?')[0]}`);
      }
    };
    page.on('response', responseHandler);

    // Wait for any potential API calls
    await page.waitForTimeout(3000);

    console.log('\n╔════════════════════════════════════════════════════════════╗');
    console.log('║  SUMMARY                                                     ║');
    console.log('╚════════════════════════════════════════════════════════════╝');
    console.log(`✓ API Connected: ${apiHealth.status === 'ok' ? 'YES' : 'NO'}`);
    console.log(`✓ Frontend Loaded: YES`);
    console.log(`✓ Canvas Detected: ${canvasCount > 0 ? 'YES' : 'PENDING/NO'}`);
    console.log(`✓ Map Viewport Detected: ${viewportCount > 0 ? 'YES' : 'PENDING/NO'}`);
    console.log(`✓ Real-Star Viewport Hook: ${consoleLogs.length > 0 ? 'ACTIVE' : 'INACTIVE'}`);
    console.log(`✓ Map Systems API Calls: ${apiCalls.length}`);

    await page.screenshot({ path: 'test-results/final-status.png', fullPage: true });
    console.log('\n✓ Diagnostic screenshot written');

    // Assert no page errors occurred
    expect(
      pageErrors,
      `Page errors should not occur. Errors: ${pageErrors.join(', ')}`
    ).toEqual([]);

    // Clean up handlers
    page.off('console', consoleHandler);
    page.off('response', responseHandler);

  } finally {
    page.off('pageerror', errorHandler);
  }
});
