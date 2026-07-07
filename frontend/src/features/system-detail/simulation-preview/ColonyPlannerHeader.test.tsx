import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ColonyPlannerHeader } from './ColonyPlannerHeader';

describe('ColonyPlannerHeader', () => {
  it('keeps planner workflow labels aligned with later-step styling', () => {
    render(
      <ColonyPlannerHeader
        initialPlanLabel={null}
        startMode="blank_advanced"
        hasRecommendedBuild={false}
        canRun={false}
        running={false}
        onRunPreview={vi.fn()}
      />,
    );

    expect(screen.getByText('Colony Planner')).toBeTruthy();
    expect(screen.getByText('Suggested Builds')).toBeTruthy();
    expect(screen.getByText('Build Plan')).toBeTruthy();
    expect(screen.getByText('Preview Result')).toBeTruthy();
    expect(screen.getByText('Observed Evidence')).toBeTruthy();
    expect(screen.getByText('Validation')).toBeTruthy();
    expect(screen.queryByText('Observed Evidence - Later step')).toBeNull();
    expect(screen.queryByText('Validation - Later step')).toBeNull();
  });

  it('invokes run preview only when enabled', () => {
    const onRunPreview = vi.fn();
    const { rerender } = render(
      <ColonyPlannerHeader
        initialPlanLabel={null}
        startMode="recommended"
        hasRecommendedBuild
        canRun={false}
        running={false}
        onRunPreview={onRunPreview}
      />,
    );

    const runButton = screen.getByRole('button', { name: /run preview/i });
    runButton.click();
    expect(onRunPreview).not.toHaveBeenCalled();

    rerender(
      <ColonyPlannerHeader
        initialPlanLabel={null}
        startMode="recommended"
        hasRecommendedBuild
        canRun={true}
        running={false}
        onRunPreview={onRunPreview}
      />,
    );
    screen.getByRole('button', { name: /run preview/i }).click();
    expect(onRunPreview).toHaveBeenCalledTimes(1);
  });
});
