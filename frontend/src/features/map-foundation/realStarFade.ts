import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef, type MutableRefObject } from 'react';

export const REAL_STAR_FADE_DURATION_S = 0.5;

export interface RealStarFadeTargets {
  heatmapOpacity: number;
  starsOpacity: number;
}

export function realStarLayerTargets(
  realStarCount: number,
  truncated: boolean,
): RealStarFadeTargets {
  const showRealStars = realStarCount > 0 && !truncated;
  const targets = {
    heatmapOpacity: showRealStars ? 0 : 1,
    starsOpacity: showRealStars ? 1 : 0,
  };
  if (showRealStars) {
    console.log(`[RealStarFade] Showing ${realStarCount} stars (truncated=${truncated})`);
  }
  return targets;
}

export interface RealStarFadeState extends RealStarFadeTargets {
  startHeatmapOpacity: number;
  startStarsOpacity: number;
  elapsedSeconds: number;
}

export function beginRealStarFade(current: RealStarFadeTargets): RealStarFadeState {
  return {
    ...current,
    startHeatmapOpacity: current.heatmapOpacity,
    startStarsOpacity: current.starsOpacity,
    elapsedSeconds: 0,
  };
}

function easeInOutCubic(progress: number): number {
  return progress < 0.5
    ? 4 * progress * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 3) / 2;
}

export function advanceRealStarFade(
  state: RealStarFadeState,
  targets: RealStarFadeTargets,
  deltaSeconds: number,
): { state: RealStarFadeState; complete: boolean } {
  const elapsedSeconds = Math.min(
    state.elapsedSeconds + Math.max(0, Math.min(deltaSeconds, 0.1)),
    REAL_STAR_FADE_DURATION_S,
  );
  const progress = easeInOutCubic(elapsedSeconds / REAL_STAR_FADE_DURATION_S);
  const nextState = {
    heatmapOpacity: state.startHeatmapOpacity
      + (targets.heatmapOpacity - state.startHeatmapOpacity) * progress,
    starsOpacity: state.startStarsOpacity
      + (targets.starsOpacity - state.startStarsOpacity) * progress,
    startHeatmapOpacity: state.startHeatmapOpacity,
    startStarsOpacity: state.startStarsOpacity,
    elapsedSeconds,
  };
  return {
    state: nextState,
    complete: elapsedSeconds >= REAL_STAR_FADE_DURATION_S,
  };
}

export function useRealStarFade(
  targets: RealStarFadeTargets,
  applyOpacities: (opacities: RealStarFadeTargets) => void,
): {
  heatmapOpacityRef: MutableRefObject<number>;
  starsOpacityRef: MutableRefObject<number>;
} {
  const { invalidate } = useThree();
  const heatmapOpacityRef = useRef(targets.heatmapOpacity);
  const starsOpacityRef = useRef(targets.starsOpacity);
  const fadeStateRef = useRef(beginRealStarFade(targets));

  useEffect(() => {
    if (
      heatmapOpacityRef.current === targets.heatmapOpacity
      && starsOpacityRef.current === targets.starsOpacity
    ) return;

    fadeStateRef.current = beginRealStarFade({
      heatmapOpacity: heatmapOpacityRef.current,
      starsOpacity: starsOpacityRef.current,
    });
    // The canvas uses frameloop="demand". A query result changing the fade
    // target does not otherwise schedule a render frame.
    invalidate();
  }, [invalidate, targets.heatmapOpacity, targets.starsOpacity]);

  useFrame((_state, delta) => {
    const advanced = advanceRealStarFade(fadeStateRef.current, targets, delta);
    fadeStateRef.current = advanced.state;
    heatmapOpacityRef.current = advanced.state.heatmapOpacity;
    starsOpacityRef.current = advanced.state.starsOpacity;
    applyOpacities(advanced.state);

    if (advanced.complete && targets.heatmapOpacity !== 1) {
      console.log(`[RealStarFade] Complete: heatmap=${advanced.state.heatmapOpacity.toFixed(2)}, stars=${advanced.state.starsOpacity.toFixed(2)}`);
    }

    // Keep demand rendering alive until the complete cross-fade has actually
    // reached its targets. R3F already supplied this frame's delta; consuming
    // clock.getDelta() again would yield an almost-zero step.
    if (!advanced.complete) invalidate();
  });

  return { heatmapOpacityRef, starsOpacityRef };
}
