import { test, expect } from '@playwright/test';

test('real-star layer zoom detection', async ({ page }) => {
  test.setTimeout(60000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║         REAL-STAR LAYER ZOOM DETECTION TEST               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture console logs including viewport-systems messages
  const viewportMessages: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (text.includes('[viewport-systems]')) {
      viewportMessages.push(text);
      console.log(`[VIEWPORT] ${text}`);
    }
  });

  // Navigate to map
  console.log('Navigating to map...');
  await page.goto('http://localhost:3000/#map');
  await page.waitForTimeout(3000);

  // Check initial state
  let canvas = await page.locator('canvas').count();
  console.log(`✓ Initial canvas found: ${canvas}`);

  // Initial zoom level check
  const initialZoom = await page.evaluate(() => {
    const output = document.querySelector('output[aria-label="Map zoom"]');
    return output ? output.textContent : 'unknown';
  });
  console.log(`✓ Initial zoom level: ${initialZoom} LY`);

  // Now try to zoom in by finding and clicking zoom buttons
  console.log('\nZooming in...');
  const zoomInBtn = page.locator('[data-testid="map-zoom-in"], button[aria-label*="Zoom in"], button:has-text("+")')
    .first();

  // Click zoom in multiple times
  for (let i = 0; i < 10; i++) {
    const isVisible = await zoomInBtn.isVisible().catch(() => false);
    if (isVisible) {
      await zoomInBtn.click();
      await page.waitForTimeout(300);

      const currentZoom = await page.evaluate(() => {
        const output = document.querySelector('output[aria-label="Map zoom"]');
        return output ? output.textContent : 'unknown';
      });
      console.log(`  Step ${i + 1}: Zoom = ${currentZoom} LY`);

      // Check for viewport-systems messages
      if (viewportMessages.length > 0) {
        console.log(`  ✓ Viewport hook detected! Messages: ${viewportMessages.length}`);
      }
    } else {
      console.log(`  Zoom button not found at step ${i + 1}`);
      break;
    }
  }

  // Final check
  canvas = await page.locator('canvas').count();
  const finalZoom = await page.evaluate(() => {
    const output = document.querySelector('output[aria-label="Map zoom"]');
    return output ? output.textContent : 'unknown';
  });

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║  FINAL SUMMARY                                             ║');
  console.log('╚════════════════════════════════════════════════════════════╝');
  console.log(`✓ Canvas still rendering: ${canvas > 0 ? 'YES' : 'NO'}`);
  console.log(`✓ Final zoom level: ${finalZoom} LY`);
  console.log(`✓ Viewport-systems messages detected: ${viewportMessages.length > 0 ? 'YES' : 'NO'}`);
  if (viewportMessages.length > 0) {
    console.log(`  Messages:`);
    viewportMessages.forEach(msg => console.log(`    ${msg}`));
  }
});
