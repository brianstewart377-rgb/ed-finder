import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef, type MutableRefObject } from 'react';

export const REAL_STAR_FADE_DURATION_S = 0.5;

export interface RealStarFadeTargets {
  densitySwirlOpacity: number;
  starsOpacity: number;
}

export function realStarLayerTargets(
  realStarCount: number,
  truncated: boolean,
): RealStarFadeTargets {
  const showRealStars = realStarCount > 0 && !truncated;
  const targets = {
    densitySwirlOpacity: showRealStars ? 0 : 1, // Fade swirl as real stars appear
    starsOpacity: showRealStars ? 1 : 0,
  };
  if (showRealStars) {
    console.log(`[RealStarFade] Showing ${realStarCount} stars (truncated=${truncated})`);
  }
  return targets;
}

export interface RealStarFadeState extends RealStarFadeTargets {
  startDensitySwirlOpacity: number;
  startStarsOpacity: number;
  elapsedSeconds: number;
}

export function beginRealStarFade(current: RealStarFadeTargets): RealStarFadeState {
  return {
    ...current,
    startDensitySwirlOpacity: current.densitySwirlOpacity,
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
    densitySwirlOpacity: state.startDensitySwirlOpacity
      + (targets.densitySwirlOpacity - state.startDensitySwirlOpacity) * progress,
    starsOpacity: state.startStarsOpacity
      + (targets.starsOpacity - state.startStarsOpacity) * progress,
    startDensitySwirlOpacity: state.startDensitySwirlOpacity,
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
  densitySwirlOpacityRef: MutableRefObject<number>;
  starsOpacityRef: MutableRefObject<number>;
} {
  const { invalidate } = useThree();
  const densitySwirlOpacityRef = useRef(targets.densitySwirlOpacity);
  const starsOpacityRef = useRef(targets.starsOpacity);
  const fadeStateRef = useRef(beginRealStarFade(targets));

  useEffect(() => {
    if (
      densitySwirlOpacityRef.current === targets.densitySwirlOpacity
      && starsOpacityRef.current === targets.starsOpacity
    ) return;

    fadeStateRef.current = beginRealStarFade({
      densitySwirlOpacity: densitySwirlOpacityRef.current,
      starsOpacity: starsOpacityRef.current,
    });
    invalidate();
  }, [invalidate, targets.densitySwirlOpacity, targets.starsOpacity]);

  useFrame((_state, delta) => {
    const advanced = advanceRealStarFade(fadeStateRef.current, targets, delta);
    fadeStateRef.current = advanced.state;
    densitySwirlOpacityRef.current = advanced.state.densitySwirlOpacity;
    starsOpacityRef.current = advanced.state.starsOpacity;
    applyOpacities(advanced.state);

    if (advanced.complete) {
      console.log(`[RealStarFade] Complete: swirl=${advanced.state.densitySwirlOpacity.toFixed(2)}, stars=${advanced.state.starsOpacity.toFixed(2)}`);
    }

    if (!advanced.complete) invalidate();
  });

  return { densitySwirlOpacityRef, starsOpacityRef };
}
