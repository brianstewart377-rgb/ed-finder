import { describe, expect, it } from 'vitest';
import { isStage26EProductionMapEnabled } from './production-route-flag';

describe('Stage 26E production route flag', () => {
  it('requires the exact enabled value and rejects rollback or malformed values', () => {
    expect(isStage26EProductionMapEnabled(undefined)).toBe(false);
    expect(isStage26EProductionMapEnabled(false)).toBe(false);
    expect(isStage26EProductionMapEnabled(true)).toBe(false);
    expect(isStage26EProductionMapEnabled('true')).toBe(false);
    expect(isStage26EProductionMapEnabled('ENABLED')).toBe(false);
    expect(isStage26EProductionMapEnabled('enabled')).toBe(true);
  });
});
