import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SemanticStatusBadge } from './SemanticStatusBadge';
import { EvidencePostureSummary } from './EvidencePostureSummary';

describe('EvidencePostureSummary', () => {
  it('renders player-first copy and exposes an accessible disclosure for technical detail', () => {
    render(
      <EvidencePostureSummary
        title="Planner evidence"
        statusLabel="Available"
        statusTone="available"
        summary="Selected-system evidence is available as review context. Your plan still uses canonical planner data."
        nextAction="Review the evidence detail before changing plan assumptions."
        plannerBoundary="Planner truth remains canonical and separate from this report-only evidence."
        highlights={<SemanticStatusBadge label="Report-only review context" tone="report_only" />}
        disclosureContent={<p>Freshness: fresh. Source posture: dedicated contract.</p>}
        testIdPrefix="test-evidence-posture"
      />,
    );

    expect(screen.getByTestId('test-evidence-posture-summary').textContent).toContain(
      'Selected-system evidence is available as review context.',
    );
    const toggle = screen.getByTestId('test-evidence-posture-disclosure-toggle');
    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle);

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('test-evidence-posture-disclosure-panel').textContent).toContain(
      'Freshness: fresh. Source posture: dedicated contract.',
    );
  });
});
