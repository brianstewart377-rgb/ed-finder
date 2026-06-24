import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SemanticStatusBadge } from './SemanticStatusBadge';
import { WorkspaceContextHeader } from './WorkspaceContextHeader';

describe('WorkspaceContextHeader', () => {
  it('lets supporting text use the full width when there is no right rail', () => {
    render(
      <WorkspaceContextHeader
        journeyLabel="Review"
        title="Compare"
        supportingText="Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace."
        status={<SemanticStatusBadge label="Ready" tone="available" />}
      />,
    );

    const supportingText = screen.getByText('Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace.');
    expect(supportingText.className).toContain('max-w-none');
    expect(supportingText.className).not.toContain('max-w-3xl');
  });

  it('renders journey context, selected system identity, facts, actions, and constrained supporting text together', () => {
    render(
      <WorkspaceContextHeader
        journeyLabel="Journey stage: Plan"
        title="Colony Planner"
        supportingText="Build the selected system with canonical planner data."
        selectedSystemName="Lave"
        selectedSystemMeta="ID64 123"
        status={<SemanticStatusBadge label="Available" tone="available" />}
        facts={[
          { label: 'Coords', value: '1, 2, 3', tone: 'cyan' },
          { label: 'Economy', value: 'Refinery', tone: 'orange' },
        ]}
        actions={<button type="button">Open system detail</button>}
      />,
    );

    const supportingText = screen.getByText('Build the selected system with canonical planner data.');
    expect(screen.getByText('Journey stage: Plan')).toBeTruthy();
    expect(screen.getByText('Colony Planner')).toBeTruthy();
    expect(screen.getByText('Selected system')).toBeTruthy();
    expect(screen.getByText('Lave')).toBeTruthy();
    expect(screen.getByText('ID64 123')).toBeTruthy();
    expect(screen.getByText('Coords')).toBeTruthy();
    expect(screen.getByText('Refinery')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open system detail' })).toBeTruthy();
    expect(supportingText.className).toContain('max-w-3xl');
    expect(supportingText.className).not.toContain('max-w-none');
  });
});
