import { describe, expect, it } from 'vitest';
import {
  CpRepairPanel,
  DataConfidencePanel,
  MechanicsTracePanel,
  ObservedVsPredictedPanel,
  SimulationPreview,
} from './SimulationPreview';


describe('SimulationPreview legacy exports', () => {
  it('keeps the public import path compatible after decomposition', () => {
    expect(SimulationPreview).toBeDefined();
    expect(ObservedVsPredictedPanel).toBeDefined();
    expect(DataConfidencePanel).toBeDefined();
    expect(MechanicsTracePanel).toBeDefined();
    expect(CpRepairPanel).toBeDefined();
  });
});
