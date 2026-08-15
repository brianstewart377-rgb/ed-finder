/**
 * Debugging script for real-star layer visibility.
 *
 * Run with: npx playwright test debug-real-stars.spec.ts --headed --debug
 *
 * This script will:
 * 1. Navigate to the map
 * 2. Log camera position and zoom at each step
 * 3. Check console for [viewport-systems] messages
 * 4. Verify API requests are being made
 * 5. Take screenshots at key points
 */

import { test, expect } from '@playwright/test';
import {
  navigateToMap,
  getCurrentZoom,
  zoomIn,
  takeScreenshot,
  isRealStarLayerVisible,
  isHeatmapVisible,
} from './dev-helpers';

test('debug real-star layer visibility', async ({ page, context }, testInfo) => {
  testInfo.setTimeout(120000);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║           REAL-STAR LAYER DEBUGGING SESSION                ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Capture all console messages
  const consoleLogs: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    consoleLogs.push(text);
    if (text.includes('[viewport-systems]') || text.includes('Error') || text.includes('✓')) {
      console.log(`  CONSOLE: ${text}`);
    }
  });

  // Capture network requests
  const networkLog: string[] = [];
  page.on('response', (response) => {
    if (response.url().includes('/api/map')) {
      const status = response.status();
      const msg = `${status} ${response.url().split('?')[0]}`;
      networkLog.push(msg);
      console.log(`  NETWORK: ${msg}`);
    }
  });

  console.log('Step 1: Navigating to map...');
  await navigateToMap(page);
  await page.waitForTimeout(1000);

  let currentZoom = await getCurrentZoom(page);
  console.log(`  Zoom: ${currentZoom}`);
  await takeScreenshot(page, 'debug-01-initial');

  console.log('\nStep 2: Checking initial state...');
  const heatmapVisible = await isHeatmapVisible(page);
  const starsVisible = await isRealStarLayerVisible(page);
  console.log(`  Heatmap visible: ${heatmapVisible}`);
  console.log(`  Real-stars visible: ${starsVisible}`);

  console.log('\nStep 3: Gradual zoom-in with detailed logging...');
  for (let i = 0; i < 12; i++) {
    console.log(`\n  Zoom step ${i + 1}:`);

    await zoomIn(page, 1);
    await page.waitForTimeout(800);

    currentZoom = await getCurrentZoom(page);
    console.log(`    Zoom level: ${currentZoom}`);

    // Check camera position
    const camera = await page.evaluate(() => {
      // Try to access the Three.js camera if available
      return (window as any).__THREE_CAMERA_INFO || 'N/A';
    });
    if (camera !== 'N/A') {
      console.log(`    Camera: ${JSON.stringify(camera)}`);
    }

    // Check viewport size
    const viewport = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return null;
      return {
        width: canvas.clientWidth,
        height: canvas.clientHeight,
      };
    });
    console.log(`    Viewport: ${viewport?.width}x${viewport?.height}`);

    // Check layer visibility
    const hasHeatmap = await isHeatmapVisible(page);
    const hasStars = await isRealStarLayerVisible(page);
    console.log(`    Heatmap: ${hasHeatmap ? '✓' : '✗'}`);
    console.log(`    Real-stars: ${hasStars ? '✓' : '✗'}`);

    // Take screenshot every 3 steps
    if ((i + 1) % 3 === 0) {
      await takeScreenshot(page, `debug-${String(i + 2).padStart(2, '0')}-zoom-${currentZoom}`);
    }

    // If we found real-stars, log success
    if (hasStars && !previouslyHadStars) {
      console.log(`\n  🎉 REAL-STARS APPEARED AT STEP ${i + 1}!`);
      await takeScreenshot(page, 'debug-REAL-STARS-FOUND');
      break;
    }

    const previouslyHadStars = hasStars;
  }

  console.log('\nStep 4: Summary of console messages:');
  const viewportMessages = consoleLogs.filter((m) => m.includes('[viewport-systems]'));
  if (viewportMessages.length > 0) {
    console.log('  ✓ Found viewport-systems messages:');
    viewportMessages.slice(-5).forEach((m) => console.log(`    ${m}`));
  } else {
    console.log('  ✗ NO viewport-systems messages found!');
    console.log('  This means the hook may not be detecting zoom correctly.');
  }

  console.log('\nStep 5: Network requests summary:');
  const uniqueUrls = new Set(networkLog);
  if (uniqueUrls.has('200 http://localhost:8001/api/map/systems')) {
    console.log('  ✓ Real-stars endpoint was called');
  } else {
    console.log('  ✗ Real-stars endpoint was NOT called');
  }

  if (uniqueUrls.has('200 http://localhost:8001/api/map/heatmap')) {
    console.log('  ✓ Heatmap endpoint was called');
  } else {
    console.log('  ✗ Heatmap endpoint was NOT called');
  }

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                  DEBUGGING COMPLETE                        ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Final screenshot
  await takeScreenshot(page, 'debug-final-state');
});
