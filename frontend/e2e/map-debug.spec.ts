import { test, expect } from '@playwright/test';

test('Map rendering - debug console and network', async ({ page }) => {
  test.setTimeout(45_000);

  // Capture console messages and errors
  const consoleLogs: Array<{ type: string; text: string }> = [];
  const networkErrors: string[] = [];

  page.on('console', (msg) => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
    if (msg.type() === 'error' || msg.type() === 'warning') {
      console.log(`[CONSOLE ${msg.type().toUpperCase()}] ${msg.text()}`);
    }
  });

  page.on('requestfailed', (request) => {
    networkErrors.push(`${request.method()} ${request.url()} - ${request.failure()?.errorText}`);
    console.log(`[NETWORK ERROR] ${request.method()} ${request.url().split('?')[0]}`);
  });

  // Navigate to map
  console.log('\n=== NAVIGATING TO MAP ===');
  await page.goto('/');

  // Click map tab
  console.log('=== CLICKING MAP TAB ===');
  await page.getByTestId('nav-map').click();
  await page.waitForTimeout(2000);

  // Check canvas exists
  const canvas = page.locator('canvas');
  const canvasCount = await canvas.count();
  console.log(`=== CANVAS COUNT: ${canvasCount} ===`);
  expect(canvasCount).toBeGreaterThan(0);

  // Zoom in a few times
  console.log('=== ZOOMING IN ===');
  const renderer = page.locator('.map-foundation-renderer');
  for (let i = 0; i < 3; i++) {
    await renderer.evaluate((el) => {
      (el as any).dispatchEvent(new WheelEvent('wheel', { deltaY: -500, bubbles: true }));
    });
    await page.waitForTimeout(500);
    const zoom = await renderer.getAttribute('data-camera-zoom');
    console.log(`Zoom step ${i + 1}: ${zoom} LY/px`);
  }

  // Wait for API calls
  await page.waitForTimeout(1000);

  // Report findings
  console.log('\n=== CONSOLE OUTPUT SUMMARY ===');
  const errors = consoleLogs.filter(l => l.type === 'error');
  const warnings = consoleLogs.filter(l => l.type === 'warning');
  console.log(`Errors: ${errors.length}`);
  console.log(`Warnings: ${warnings.length}`);

  if (errors.length > 0) {
    console.log('\nERRORS:');
    errors.forEach(e => console.log(`  - ${e.text}`));
  }

  if (networkErrors.length > 0) {
    console.log('\nNETWORK ERRORS:');
    networkErrors.forEach(e => console.log(`  - ${e}`));
  }

  console.log('\n=== END DEBUG ===\n');

  // Assertions
  expect(errors.length, 'Should have no console errors').toBe(0);
  expect(networkErrors.length, 'Should have no network errors').toBe(0);
});
