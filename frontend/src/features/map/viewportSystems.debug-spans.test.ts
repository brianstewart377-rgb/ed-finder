import { describe, it } from 'vitest';
import { realStarViewportSpan, shouldEnableRealStarDetail, REAL_STAR_ENTER_MAX_LY, REAL_STAR_EXIT_MAX_LY } from './viewportSystems';

describe('viewport span calculation debug', () => {
  const viewport = { width: 1280, height: 720 };

  it('should show actual spans at various zoom levels', () => {
    const scenarios = [
      { zoom: 0.5, label: 'very zoomed in' },
      { zoom: 1, label: 'normal' },
      { zoom: 5, label: 'zoomed in' },
      { zoom: 100, label: 'zoomed out' },
      { zoom: 130, label: 'boundary' },
      { zoom: 140, label: 'boundary' },
      { zoom: 1000, label: 'very zoomed out' },
    ];

    const camera = { center: { x: 0, z: 0 }, pitchDeg: 0.5 };

    console.log('\n=== Viewport Span Debug ===');
    console.log(`ENTER_MAX_LY: ${REAL_STAR_ENTER_MAX_LY}`);
    console.log(`EXIT_MAX_LY: ${REAL_STAR_EXIT_MAX_LY}`);
    console.log('');

    scenarios.forEach(({ zoom, label }) => {
      const span = realStarViewportSpan({ ...camera, zoom }, viewport);
      const shouldEnableFromOff = shouldEnableRealStarDetail({ ...camera, zoom }, viewport, false);
      const shouldEnableFromOn = shouldEnableRealStarDetail({ ...camera, zoom }, viewport, true);

      console.log(`zoom=${zoom.toString().padEnd(6)} (${label}):`);
      console.log(`  maxSpan: ${span.maxSpan.toFixed(0)} LY`);
      console.log(`  enter threshold (${REAL_STAR_ENTER_MAX_LY}): ${shouldEnableFromOff ? 'YES' : 'NO'}`);
      console.log(`  exit threshold (${REAL_STAR_EXIT_MAX_LY}): ${shouldEnableFromOn ? 'YES' : 'NO'}`);
      console.log('');
    });
  });
});
