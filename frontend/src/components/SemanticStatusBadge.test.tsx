import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SemanticStatusBadge } from './SemanticStatusBadge';

describe('SemanticStatusBadge', () => {
  it('renders visible text for semantic states instead of relying on color alone', () => {
    render(
      <div>
        <SemanticStatusBadge label="Available" tone="available" />
        <SemanticStatusBadge label="Report-only review context" tone="report_only" />
        <SemanticStatusBadge label="Not evaluated" tone="not_evaluated" />
      </div>,
    );

    expect(screen.getByText('Available')).toBeTruthy();
    expect(screen.getByText('Report-only review context')).toBeTruthy();
    expect(screen.getByText('Not evaluated')).toBeTruthy();
  });
});
