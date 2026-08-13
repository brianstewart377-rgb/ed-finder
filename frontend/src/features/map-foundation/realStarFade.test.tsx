import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  advanceRealStarFade,
  beginRealStarFade,
  realStarLayerTargets,
  useRealStarFade,
  type RealStarFadeTargets,
} from './realStarFade';

const fiber = vi.hoisted(() => ({
  frame: null as null | ((state: unknown, delta: number) => void),
  invalidate: vi.fn(),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (callback: (state: unknown, delta: number) => void) => {
    fiber.frame = callback;
  },
  useThree: () => ({ invalidate: fiber.invalidate }),
}));

describe('real-star cross-fade', () => {
  it('keeps the heatmap visible for empty or truncated detail results', () => {
    expect(realStarLayerTargets(0, false)).toEqual({
      heatmapOpacity: 1,
      starsOpacity: 0,
    });
    expect(realStarLayerTargets(40_000, true)).toEqual({
      heatmapOpacity: 1,
      starsOpacity: 0,
    });
    expect(realStarLayerTargets(10, false)).toEqual({
      heatmapOpacity: 0,
      starsOpacity: 1,
    });
  });

  it('advances from the supplied frame delta and reaches both targets', () => {
    let state = beginRealStarFade({ heatmapOpacity: 1, starsOpacity: 0 });
    const targets = { heatmapOpacity: 0, starsOpacity: 1 };

    for (let frame = 0; frame < 5; frame += 1) {
      state = advanceRealStarFade(state, targets, 0.1).state;
    }

    expect(state.heatmapOpacity).toBe(0);
    expect(state.starsOpacity).toBe(1);
    expect(state.elapsedSeconds).toBe(0.5);
  });

  it('invalidates a demand canvas until a target change finishes', () => {
    fiber.invalidate.mockClear();
    const applyOpacities = vi.fn();
    const initial = { heatmapOpacity: 1, starsOpacity: 0 };
    const detail = { heatmapOpacity: 0, starsOpacity: 1 };
    const hook = renderHook(
      ({ targets }: { targets: RealStarFadeTargets }) => useRealStarFade(targets, applyOpacities),
      { initialProps: { targets: initial } },
    );

    hook.rerender({ targets: detail });
    expect(fiber.invalidate).toHaveBeenCalledTimes(1);

    const stateWithPoisonedClock = {
      clock: { getDelta: () => { throw new Error('clock delta must not be consumed twice'); } },
    };
    for (let frame = 0; frame < 5; frame += 1) {
      act(() => fiber.frame?.(stateWithPoisonedClock, 0.1));
    }

    expect(applyOpacities).toHaveBeenLastCalledWith(expect.objectContaining({
      heatmapOpacity: 0,
      starsOpacity: 1,
    }));
    expect(hook.result.current.heatmapOpacityRef.current).toBe(0);
    expect(hook.result.current.starsOpacityRef.current).toBe(1);
    expect(fiber.invalidate).toHaveBeenCalledTimes(5);
  });
});
