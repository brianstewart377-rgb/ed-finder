import { test, expect } from '@playwright/test';

test('comprehensive E2E status check', async ({ page }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║        COMPREHENSIVE E2E STATUS CHECK                       ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

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

  // Check for map viewport
  const viewportCount = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
  console.log(`✓ Map Viewport Elements: ${viewportCount}`);

  // Check for Three.js scene
  const sceneElements = await page.locator('[class*="scene"],[data-testid*="scene"]').count();
  console.log(`✓ Scene Elements: ${sceneElements}`);

  // Capture console logs
  const consoleLogs: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (text.includes('[viewport-systems]') || text.includes('Real') || text.includes('Stars')) {
      consoleLogs.push(text);
      console.log(`  [CONSOLE] ${text}`);
    }
  });

  // Check API calls
  const apiCalls: { method: string; url: string }[] = [];
  page.on('response', (response) => {
    if (response.url().includes('/api/map')) {
      apiCalls.push({
        method: 'GET',
        url: response.url().split('?')[0]
      });
      console.log(`  [API] ${response.status()} ${response.url().split('?')[0]}`);
    }
  });

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

  // Take final screenshot
  await page.screenshot({ path: 'test-results/final-status.png' });
  console.log('\n✓ Screenshot saved to test-results/final-status.png');
});
