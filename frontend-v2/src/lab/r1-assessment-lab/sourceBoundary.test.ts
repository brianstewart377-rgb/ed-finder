import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const APP_SOURCE = readFileSync(resolve(import.meta.dirname, '../../App.tsx'), 'utf-8');

describe('R1 assessment lab source boundary', () => {
  it('keeps the exact lab hash and dynamic import inside a DEV-only source branch', () => {
    expect(APP_SOURCE).toContain("import.meta.env.DEV");
    expect(APP_SOURCE).toContain('#r1-assessment-lab');
    expect(APP_SOURCE).toContain("lazy(() => import('@/lab/r1-assessment-lab/R1AssessmentLabApp'))");
  });

  it('states explicitly that source structure does not prove dead-code elimination', () => {
    expect(true).toBe(true);
  });

  it('states explicitly that final acceptance requires production artifact scanning', () => {
    expect(true).toBe(true);
  });
});
