import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PlannerWarehouseEvidence } from '@/types/api';
import { WarehouseEvidenceCard } from './WarehouseEvidenceCard';

/**
 * Stage 18H — Warehouse-to-Planner Evidence Bridge (read-only).
 *
 * These tests pin the safe boundaries: the planner always presents warehouse
 * evidence as report-only, defaults to an unavailable/unknown state, renders
 * conservative source-labelled findings, and exposes NO controls that could
 * mutate planner state.
 */
describe('WarehouseEvidenceCard', () => {
  it('renders the safe unavailable/unknown state when no evidence is supplied', () => {
    render(<WarehouseEvidenceCard />);

    const card = screen.getByTestId('planner-warehouse-evidence');
    expect(card).toBeTruthy();
    const unavailable = within(card).getByTestId('warehouse-evidence-unavailable');
    expect(unavailable.textContent).toContain('No warehouse evidence artifact is available.');
    // Unknown source label, not a "no evidence" / false claim.
    expect(within(unavailable).getByTestId('warehouse-evidence-source-unknown')).toBeTruthy();
    expect(within(card).queryByTestId('warehouse-evidence-items')).toBeNull();
  });

  it('treats an explicitly unavailable summary the same as missing (stays unknown)', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'unavailable',
      reportOnly: true,
      items: [],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByTestId('warehouse-evidence-unavailable')).toBeTruthy();
    expect(screen.queryByTestId('warehouse-evidence-item')).toBeNull();
  });

  it('always states that the planner uses canonical data and warehouse evidence is report-only', () => {
    render(<WarehouseEvidenceCard />);

    expect(screen.getByTestId('warehouse-evidence-source-boundary').textContent).toBe(
      'Planner is using canonical data; warehouse evidence is report-only.',
    );
    expect(screen.getByTestId('warehouse-evidence-report-only-tag').textContent).toMatch(/report-only/i);
  });

  it('renders conservative, source-labelled report-only findings when supplied', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      items: [
        {
          label: 'report_only',
          source: 'warehouse_report_only',
          summary: 'Warehouse has newer report-only evidence for this system.',
        },
        {
          label: 'verify',
          source: 'warehouse_report_only',
          summary: 'Station/body association available as verify evidence.',
        },
      ],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    const items = screen.getAllByTestId('warehouse-evidence-item');
    expect(items).toHaveLength(2);
    expect(screen.getByText('Warehouse has newer report-only evidence for this system.')).toBeTruthy();
    expect(screen.getAllByTestId('warehouse-evidence-source-warehouse_report_only').length).toBe(2);
    expect(screen.getByTestId('warehouse-evidence-label-verify')).toBeTruthy();
    expect(screen.queryByTestId('warehouse-evidence-unavailable')).toBeNull();
  });

  it('renders stale, risky/needs-review, unresolved, and blocked findings conservatively', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      items: [
        { label: 'stale', source: 'warehouse_report_only', summary: 'Warehouse coverage says this system has stale/undated source evidence.' },
        { label: 'needs_review', source: 'warehouse_report_only', summary: 'Warehouse report has risky conflicts.' },
        { label: 'unresolved', source: 'warehouse_report_only', summary: 'Station/body association unresolved in warehouse report.' },
        { label: 'blocked', source: 'warehouse_report_only', summary: 'Warehouse report has blocked conflicts.' },
      ],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByTestId('warehouse-evidence-label-stale').textContent).toMatch(/stale/i);
    expect(screen.getByTestId('warehouse-evidence-label-needs_review').textContent).toMatch(/needs review/i);
    expect(screen.getByTestId('warehouse-evidence-label-unresolved').textContent).toMatch(/unresolved/i);
    expect(screen.getByTestId('warehouse-evidence-label-blocked').textContent).toMatch(/blocked/i);
    // No promotion / canonical / apply wording anywhere in the card.
    expect(screen.getByTestId('planner-warehouse-evidence').textContent).not.toMatch(
      /promote|apply|canonical write|make canonical|overwrite/i,
    );
  });

  it('keeps canonical, observed, warehouse report-only, and unknown sources visually separated', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      items: [
        { label: 'report_only', source: 'canonical', summary: 'Planner is using canonical data.' },
        { label: 'report_only', source: 'observed', summary: 'Observed evidence exists separately.' },
        { label: 'report_only', source: 'warehouse_report_only', summary: 'Warehouse report-only evidence.' },
        { label: 'unknown', source: 'unknown', summary: 'Source not established.' },
      ],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByTestId('warehouse-evidence-source-canonical').textContent).toBe('Canonical');
    expect(screen.getByTestId('warehouse-evidence-source-observed').textContent).toBe('Observed');
    expect(screen.getByTestId('warehouse-evidence-source-warehouse_report_only').textContent).toBe('Warehouse report-only');
    expect(screen.getByTestId('warehouse-evidence-source-unknown').textContent).toBe('Unknown');
  });

  it('exposes NO interactive controls (read-only, no mutation surface)', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      items: [
        { label: 'report_only', source: 'warehouse_report_only', summary: 'Warehouse report-only evidence.' },
      ],
    };
    const { container } = render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(container.querySelectorAll('button').length).toBe(0);
    expect(container.querySelectorAll('a').length).toBe(0);
    expect(container.querySelectorAll('input, select, textarea').length).toBe(0);
    expect(container.querySelectorAll('[role="button"]').length).toBe(0);
  });
});
