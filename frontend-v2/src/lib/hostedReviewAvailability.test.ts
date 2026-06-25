import { describe, expect, it } from 'vitest';
import manifest from './hostedReviewAvailability.manifest.json';
import {
  HOSTED_REVIEW_FEATURE_AVAILABILITY,
  detectHostedReviewSurface,
  hostedReviewAvailabilityForRoute,
  validateHostedReviewAvailabilityManifest,
} from './hostedReviewAvailability';

describe('hostedReviewAvailability', () => {
  it('derives frontend feature availability from the shared manifest', () => {
    expect(validateHostedReviewAvailabilityManifest(manifest).features).toEqual(manifest.features);
    expect(HOSTED_REVIEW_FEATURE_AVAILABILITY).toEqual(manifest.features);
  });

  it('classifies supported, intentionally unavailable, and excluded hosted-review features', () => {
    const byKey = new Map(HOSTED_REVIEW_FEATURE_AVAILABILITY.map((feature) => [feature.key, feature]));

    expect(byKey.get('finder')?.state).toBe('supported');
    expect(byKey.get('colony-planner')?.state).toBe('supported');
    expect(byKey.get('map')?.state).toBe('supported');
    expect(byKey.get('admin')?.state).toBe('intentionally_unavailable');
    expect(byKey.get('operator')?.state).toBe('intentionally_unavailable');
    expect(byKey.get('search-tuning')?.state).toBe('intentionally_unavailable');
    expect(byKey.get('profile-sync')?.state).toBe('excluded');
  });

  it('maps visible routes to hosted-review policy states', () => {
    expect(hostedReviewAvailabilityForRoute('map')?.state).toBe('supported');
    expect(hostedReviewAvailabilityForRoute('admin')?.state).toBe('intentionally_unavailable');
    expect(hostedReviewAvailabilityForRoute('operator')?.state).toBe('intentionally_unavailable');
    expect(hostedReviewAvailabilityForRoute('search-tuning')?.state).toBe('intentionally_unavailable');
  });

  it('detects hosted-review mode from explicit build marker or hosted hostname', () => {
    expect(detectHostedReviewSurface('localhost', 'hosted')).toBe(true);
    expect(detectHostedReviewSurface('review.ed-finder.app')).toBe(true);
    expect(detectHostedReviewSurface('localhost')).toBe(false);
  });
});
