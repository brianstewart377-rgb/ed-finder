import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const APP_SOURCE = readFileSync(resolve(import.meta.dirname, '../../App.tsx'), 'utf-8');
const TEST_SOURCE = readFileSync(import.meta.filename, 'utf-8');

describe('R1 assessment lab source boundary', () => {
  it('keeps the exact lab hash declaration and lazy import inside the DEV-only source branch', () => {
    const devBranchIndex = APP_SOURCE.indexOf('if (import.meta.env.DEV) {');
    const hashIndex = APP_SOURCE.indexOf("const DEV_R1_ASSESSMENT_LAB_HASH = '#r1-assessment-lab';");
    const lazyImportIndex = APP_SOURCE.indexOf("const DevR1AssessmentLabApp = lazy(() => import('@/lab/r1-assessment-lab/R1AssessmentLabApp'));");

    expect(devBranchIndex).toBeGreaterThanOrEqual(0);
    expect(hashIndex).toBeGreaterThan(devBranchIndex);
    expect(lazyImportIndex).toBeGreaterThan(devBranchIndex);
  });

  it('keeps ProductionNormalRoot as the production fallback in App source', () => {
    const productionReturnIndex = APP_SOURCE.indexOf('return <ProductionNormalRoot />;');
    const devBranchIndex = APP_SOURCE.indexOf('if (import.meta.env.DEV) {');

    expect(productionReturnIndex).toBeGreaterThan(devBranchIndex);
  });

  it('contains the required limitation and final-gate text in this source test', () => {
    expect(TEST_SOURCE).toContain('Source structure does not prove dead-code elimination.');
    expect(TEST_SOURCE).toContain('Final acceptance requires production artifact scanning.');
  });
});
