import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RoleReviewCard } from './RoleReviewCard';
import type { RoleReviewResult } from './colonyRoleReview';


function review(overrides: Partial<RoleReviewResult> = {}): RoleReviewResult {
  return {
    consistency: 'partial',
    consistencyLabel: 'Partially aligned',
    declaredRoles: [
      {
        id: 'declared:1:industrial_core',
        body_id: '1',
        role_id: 'industrial_core',
        source: 'declared',
        label: 'Industrial Core',
      },
    ],
    observedRoles: [
      {
        id: 'observed:1:tourism_agriculture_body',
        body_id: '1',
        role_id: 'tourism_agriculture_body',
        source: 'observed',
        confidence: 'likely',
        label: 'Observed Tourism Focus',
        evidenceLabel: 'Observed Tourism economy',
      },
    ],
    summaries: ['Declared Industrial Core but observed Observed Tourism Focus.'],
    conflicts: ['Role conflict: Tourism + Heavy Industrial'],
    coverage: {
      declaredCount: 1,
      observedCount: 1,
      matchedCount: 0,
      mismatchCount: 1,
    },
    ...overrides,
  };
}

describe('RoleReviewCard', () => {
  it('separates declared strategy and observed evidence while surfacing review highlights', () => {
    render(<RoleReviewCard result={review()} />);

    expect(screen.getByText('Declared strategy')).toBeTruthy();
    expect(screen.getByText('Observed evidence')).toBeTruthy();
    expect(screen.getByText('Declared/observed mismatch')).toBeTruthy();
    expect(screen.getByText('Declared conflict')).toBeTruthy();
    expect(screen.getByText('Observed but not declared')).toBeTruthy();
    expect(screen.getByText('Declared without support')).toBeTruthy();
    expect(screen.getByText('Industrial')).toBeTruthy();
    expect(screen.getByText('Observed Tourism Focus / Observed Tourism economy')).toBeTruthy();
  });

  it('falls back to aligned guidance when no role-review issues are present', () => {
    render(
      <RoleReviewCard
        result={review({
          consistency: 'aligned',
          consistencyLabel: 'Strategy aligned',
          observedRoles: [
            {
              id: 'observed:1:industrial_core',
              body_id: '1',
              role_id: 'industrial_core',
              source: 'observed',
              confidence: 'strong',
              label: 'Observed Industrial Core',
              evidenceLabel: 'Observed Industrial economy',
            },
          ],
          summaries: ['Declared Industrial Core matches observed Observed Industrial Core.'],
          conflicts: [],
          coverage: {
            declaredCount: 1,
            observedCount: 1,
            matchedCount: 1,
            mismatchCount: 0,
          },
        })}
      />,
    );

    expect(screen.getByText('Signals aligned')).toBeTruthy();
  });
});
