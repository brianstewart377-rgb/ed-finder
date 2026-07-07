import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PlannerStatusStrip } from './PlannerStatusStrip';
import type { PlanningEconomyLedger } from './planningEconomy';

const emptyLedger: PlanningEconomyLedger = {
  entries: [],
  plannedCount: 0,
  projectedCount: 0,
  unknownCount: 0,
  total: 0,
};

describe('PlannerStatusStrip', () => {
  it('renders concise readable core counts without zero unresolved-review clutter', () => {
    render(
      <PlannerStatusStrip
        selection={{ type: 'system' }}
        planningFocusLabel={null}
        placementCount={0}
        projectedCount={0}
        existingCount={1}
        inferredExistingCount={0}
        emptySlotCount={5}
        unresolvedExistingCount={0}
        unsavedChanges={false}
        economyLedger={emptyLedger}
      />,
    );

    const strip = screen.getByTestId('planner-status-strip');
    expect(strip.getAttribute('data-readability')).toBe('solid-graphite');
    expect(strip.textContent).toContain('Existing');
    expect(strip.textContent).toContain('Planned');
    expect(strip.textContent).toContain('Preview');
    expect(strip.textContent).toContain('Open slots');
    expect(strip.textContent).toContain('Saved locally');
    expect(screen.queryByTestId('existing-location-review')).toBeNull();
    expect(strip.textContent).not.toContain('Unresolved existing');
  });

  it('uses player-facing review wording only when existing locations need review', () => {
    render(
      <PlannerStatusStrip
        selection={{ type: 'system' }}
        planningFocusLabel="Workspace System A 1"
        placementCount={2}
        projectedCount={1}
        existingCount={1}
        inferredExistingCount={0}
        emptySlotCount={3}
        unresolvedExistingCount={2}
        prerequisiteIssueCount={1}
        unsavedChanges
        economyLedger={emptyLedger}
      />,
    );

    expect(screen.getByTestId('existing-location-review').textContent).toContain('Existing locations need review');
    expect(screen.getByTestId('existing-location-review').textContent).toContain('Confirmed 1');
    expect(screen.getByTestId('existing-location-review').textContent).toContain('Inferred 0');
    expect(screen.getByTestId('existing-location-review').textContent).toContain('Need review 2');
    expect(screen.getByTestId('planner-prerequisite-summary').textContent).toContain('1 prerequisite warning');
    expect(screen.getByTestId('planner-status-strip').textContent).not.toContain('warehouse');
  });
});
