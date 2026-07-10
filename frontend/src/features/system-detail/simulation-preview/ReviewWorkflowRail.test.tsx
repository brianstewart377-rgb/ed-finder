import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReviewWorkflowRail } from './ReviewWorkflowRail';

describe('ReviewWorkflowRail', () => {
  it('shows the review journey and next move for evidence before any preview exists', () => {
    render(
      <ReviewWorkflowRail
        activeMode="evidence"
        previewStatus="not_run"
        observedFactsCount={0}
      />,
    );

    expect(screen.getByTestId('review-workflow-rail').textContent).toMatch(/Evidence in focus/);
    expect(screen.getByText('Preview')).toBeTruthy();
    expect(screen.getByText('Not run')).toBeTruthy();
    expect(screen.getByText('No facts yet')).toBeTruthy();
    expect(screen.getByText('Needs preview')).toBeTruthy();
    expect(screen.getByText('Later step')).toBeTruthy();
    expect(screen.getByTestId('review-workflow-next-move').textContent).toMatch(/Run Preview first/i);
  });

  it('shows export readiness once review inputs are in place', () => {
    render(
      <ReviewWorkflowRail
        activeMode="export"
        previewStatus="current"
        observedFactsCount={4}
        exportReady
      />,
    );

    expect(screen.getByText('Current')).toBeTruthy();
    expect(screen.getByText('4 facts')).toBeTruthy();
    expect(screen.getByText('Ready to compare')).toBeTruthy();
    expect(screen.getAllByText('Ready').length).toBeGreaterThan(0);
    expect(screen.getByTestId('review-workflow-next-move').textContent).toMatch(/generated packs/i);
  });
});
