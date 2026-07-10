import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReviewReadinessStrip } from './ReviewReadinessStrip';

describe('ReviewReadinessStrip', () => {
  it('shows blocked review posture before any preview exists', () => {
    render(
      <ReviewReadinessStrip
        activeMode="validation"
        previewStatus="not_run"
        observedFactsCount={0}
      />,
    );

    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/Validation blocked/);
    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/Later export step/);
    expect(screen.getByTestId('review-readiness-summary').textContent).toMatch(/Run Preview first/i);
  });

  it('shows aligned review posture once preview and evidence are current', () => {
    render(
      <ReviewReadinessStrip
        activeMode="export"
        previewStatus="current"
        observedFactsCount={3}
        exportReady
        exportBlockerCount={0}
      />,
    );

    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/Current preview/);
    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/3 observed facts/);
    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/Validation ready/);
    expect(screen.getByTestId('review-readiness-strip').textContent).toMatch(/Export ready/);
    expect(screen.getByTestId('review-readiness-summary').textContent).toMatch(/aligned enough for a clean review hand-off/i);
  });
});
