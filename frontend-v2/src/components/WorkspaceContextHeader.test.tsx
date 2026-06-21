import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SemanticStatusBadge } from './SemanticStatusBadge';
import { WorkspaceContextHeader } from './WorkspaceContextHeader';

describe('WorkspaceContextHeader', () => {
  it('renders journey context, selected system identity, facts, and actions together', () => {
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

    expect(screen.getByText('Journey stage: Plan')).toBeTruthy();
    expect(screen.getByText('Colony Planner')).toBeTruthy();
    expect(screen.getByText('Selected system')).toBeTruthy();
    expect(screen.getByText('Lave')).toBeTruthy();
    expect(screen.getByText('ID64 123')).toBeTruthy();
    expect(screen.getByText('Coords')).toBeTruthy();
    expect(screen.getByText('Refinery')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open system detail' })).toBeTruthy();
  });
});
