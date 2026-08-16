import { test, expect } from '@playwright/test';

test('check map page loads', async ({ page }) => {
  test.setTimeout(60000);

  // Capture console and errors BEFORE navigation
  page.on('console', (msg) => {
    console.log(`[CONSOLE] ${msg.type()}: ${msg.text()}`);
  });

  page.on('pageerror', (error) => {
    console.log(`[PAGE ERROR] ${error.message}`);
  });

  page.on('request', (request) => {
    if (request.url().includes('/api/')) {
      console.log(`[REQUEST] ${request.method()} ${request.url().split('?')[0]}`);
    }
  });

  page.on('response', (response) => {
    if (response.url().includes('/api/')) {
      console.log(`[RESPONSE] ${response.status()} ${response.url().split('?')[0]}`);
    }
  });

  console.log('\n✓ Navigating to map...');
  await page.goto('http://localhost:3000/map');

  // Wait for page to fully load
  await page.waitForTimeout(5000);

  // Check if Map tab exists and click it if needed
  const mapTab = page.locator('button:has-text("Map")').first();
  const mapTabVisible = await mapTab.isVisible().catch(() => false);
  console.log(`✓ Map tab visible: ${mapTabVisible}`);
  if (mapTabVisible) {
    console.log('✓ Clicking Map tab...');
    await mapTab.click();
    await page.waitForTimeout(2000);
  }

  // Check what's on the page
  const title = await page.title();
  console.log(`✓ Page title: ${title}`);

  // Check if root element exists
  const root = await page.locator('#root');
  const rootVisible = await root.isVisible().catch(() => false);
  console.log(`✓ Root element visible: ${rootVisible}`);

  // Check for any error messages
  const errorElements = await page.locator('[role="alert"], .error, [class*="error"]').allTextContents();
  if (errorElements.length > 0) {
    console.log(`✗ Errors found: ${errorElements.join(', ')}`);
  } else {
    console.log(`✓ No error elements visible`);
  }

  // Try to find the map canvas with alternate selectors
  const canvas = await page.locator('canvas').count();
  console.log(`✓ Canvas elements found: ${canvas}`);

  // Look for map viewport
  const mapViewport = await page.locator('[data-testid="stage26e-production-map-viewport"]').count();
  console.log(`✓ Map viewport elements found: ${mapViewport}`);

  // Check body content
  const bodyText = await page.locator('body').textContent();
  if (bodyText) {
    console.log(`✓ Body text (first 200 chars): ${bodyText.substring(0, 200)}`);
  }

  // Take a screenshot for visual inspection
  await page.screenshot({ path: 'test-results/simple-map-test.png' });
  console.log(`✓ Screenshot saved`);
});
