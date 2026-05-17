import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ColonyPlannerSectionNav } from './ColonyPlannerSectionNav';

describe('ColonyPlannerSectionNav', () => {
  it('shows planner workflow order with primary steps and later steps', () => {
    render(<ColonyPlannerSectionNav />);

    expect(screen.getByRole('navigation', { name: /Colony planner workflow/i })).toBeTruthy();
    expect(screen.getByText('Suggested Builds')).toBeTruthy();
    expect(screen.getByText('Build Plan')).toBeTruthy();
    expect(screen.getByText('Preview Result')).toBeTruthy();
    expect(screen.getByText('Observed Evidence')).toBeTruthy();
    expect(screen.getByText('Validation')).toBeTruthy();
  });

  it('identifies later steps and workflow direction', () => {
    render(<ColonyPlannerSectionNav />);

    expect(screen.getAllByText('Later step', { selector: 'span' })).toHaveLength(2);
    expect(screen.getByText(/Suggested Builds\s*[→]\s*Build Plan\s*[→]\s*Preview Result/i)).toBeTruthy();
  });
});
