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
    expect(unavailable.textContent).toContain('Unknown. Selected-system evidence has not been established.');
    expect(screen.getByTestId('warehouse-evidence-freshness-unknown').textContent).toMatch(/unknown freshness/i);
    expect(screen.getByTestId('warehouse-evidence-envelope-status-unknown').textContent).toMatch(/unknown/i);
    expect(screen.getByTestId('warehouse-evidence-source-posture-unknown').textContent).toMatch(/unknown source path/i);
    expect(screen.getByTestId('warehouse-evidence-review-status').textContent).toContain('Passive review only');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-not_evaluated').textContent).toMatch(/not evaluated/i);
    expect(screen.getByTestId('warehouse-evidence-status-detail').textContent).toContain('Unknown. Selected-system evidence has not been established.');
    expect(screen.getByTestId('warehouse-evidence-source-classes').textContent).toContain('Unavailable');
    expect(screen.getByTestId('warehouse-evidence-semantics').textContent).toContain('Report-only review context');
    // Unknown source label, not a "no evidence" / false claim.
    expect(within(unavailable).getByTestId('warehouse-evidence-source-unknown')).toBeTruthy();
    expect(within(card).queryByTestId('warehouse-evidence-items')).toBeNull();
  });

  it('renders unavailable as a distinct state instead of collapsing it into unknown', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'unavailable',
      reportOnly: true,
      items: [],
      evidenceEnvelope: {
        status: 'unavailable',
        sourceClasses: ['unavailable'],
        semantics: ['report_only_review_context', 'not_full_coverage'],
        reportOnly: true,
        selectedSystemOnly: true,
        plannerTruthSourceClass: 'unavailable',
        claimsCanonicalTruth: false,
        claimsFullCoverage: false,
        summary: 'Selected-system evidence is unavailable in this read-only planner envelope. Source classes: no linked selected-system evidence.',
      },
      boundedStaging: {
        status: 'unavailable',
        reportOnly: true,
        boundedStagingOnly: true,
      },
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByTestId('warehouse-evidence-unavailable')).toBeTruthy();
    expect(screen.getByTestId('warehouse-evidence-envelope-status-unavailable').textContent).toMatch(/unavailable/i);
    expect(screen.getByTestId('warehouse-evidence-status-detail').textContent).toContain('No approved bounded staging evidence is linked to this selected system.');
    expect(screen.queryByTestId('warehouse-evidence-item')).toBeNull();
  });

  it('always states that the planner uses canonical data and the evidence panel is report-only', () => {
    render(<WarehouseEvidenceCard />);

    expect(screen.getByTestId('warehouse-evidence-source-boundary').textContent).toBe(
      'Planner is using canonical data; this evidence panel is report-only.',
    );
    expect(screen.getByTestId('warehouse-evidence-report-only-tag').textContent).toMatch(/report-only/i);
  });

  it('renders conservative, source-labelled report-only findings when supplied', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      freshnessStatus: 'fresh',
      evaluatedAt: '2026-06-17T14:00:00Z',
      manualReviewRequired: false,
      sourceName: 'warehouse_reconciliation',
      runKey: 'warehouse/run-20260617.json',
      sourcePosture: 'dedicated_contract',
      evidenceEnvelope: {
        status: 'available',
        sourceClasses: ['bounded_staging', 'derived_report'],
        semantics: ['bounded_staging_evidence', 'report_only_review_context', 'not_full_coverage'],
        reportOnly: true,
        selectedSystemOnly: true,
        plannerTruthSourceClass: 'unavailable',
        claimsCanonicalTruth: false,
        claimsFullCoverage: false,
        summary: 'Selected-system evidence is available in this read-only planner envelope. Source classes: bounded staging evidence, derived report evidence.',
      },
      boundedStaging: {
        status: 'available',
        reportOnly: true,
        boundedStagingOnly: true,
        sourceName: 'edsm',
        sourceBatchLabel: 'edsm-stations-20260619T190906Z',
        sourceSha256: 'b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984',
        sourceRunKey: 'stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z',
        bridgeKey: 'source_runs:stage19bb-edsm-10000-row-bounded-staging-20260619T200018Z',
        rowLimit: 10000,
        availableRowLimits: [1000, 10000],
        matchedRowCount: 2,
        latestSourceUpdatedAt: '2026-06-19T20:00:18Z',
        summary: 'Stage 19BB bounded staging evidence includes 2 staging rows for this system in the approved 10000-row context; it remains bounded staging-only review context, not canonical truth and not full EDSM coverage.',
      },
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
    expect(screen.getByTestId('warehouse-evidence-freshness-fresh').textContent).toMatch(/fresh/i);
    expect(screen.getByTestId('warehouse-evidence-source-posture-dedicated_contract').textContent).toMatch(/dedicated contract/i);
    expect(screen.getByTestId('warehouse-evidence-source-run').textContent).toContain('warehouse_reconciliation');
    expect(screen.getByTestId('warehouse-evidence-envelope-status-available').textContent).toMatch(/available/i);
    expect(screen.getByTestId('warehouse-evidence-status-detail').textContent).toContain('Available. Selected-system evidence is present as read-only review context only.');
    expect(screen.getByTestId('warehouse-evidence-source-classes').textContent).toContain('Bounded staging');
    expect(screen.getByTestId('warehouse-evidence-semantics').textContent).toContain('Not full EDSM coverage');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-available').textContent).toContain('Bounded staging evidence');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-summary').textContent).toContain('edsm-stations-20260619T190906Z');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-summary').textContent).toContain('limit 10000');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-guidance').textContent).toContain('Bounded staging evidence');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-guidance').textContent).toContain('Report-only review context');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-guidance').textContent).toContain('Not canonical truth');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-guidance').textContent).toContain('Not full EDSM coverage');
    expect(screen.getByTestId('warehouse-evidence-bounded-staging-guidance').textContent).toContain('Limited to approved Stage 19BB row-cap evidence');
    expect(screen.queryByTestId('warehouse-evidence-unavailable')).toBeNull();
  });

  it('renders live canonical and observed findings without claiming warehouse-only scope', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      freshnessStatus: 'not_evaluated',
      evaluatedAt: '2026-06-18T09:30:00Z',
      manualReviewRequired: true,
      sourceName: 'warehouse_reconciliation',
      runKey: 'warehouse/run-20260618.json',
      sourcePosture: 'dedicated_contract',
      evidenceEnvelope: {
        status: 'available',
        sourceClasses: ['canonical', 'observed_facts'],
        semantics: ['canonical_truth', 'observed_report', 'report_only_review_context', 'not_full_coverage'],
        reportOnly: true,
        selectedSystemOnly: true,
        plannerTruthSourceClass: 'canonical',
        claimsCanonicalTruth: false,
        claimsFullCoverage: false,
        summary: 'Selected-system evidence is available in this read-only planner envelope. Source classes: canonical evidence, observed-facts evidence.',
      },
      items: [
        {
          label: 'report_only',
          source: 'canonical',
          summary: 'Canonical app data for Lave includes 4 bodies and 2 stations; 1 local station-body links are matched.',
        },
        {
          label: 'needs_review',
          source: 'observed',
          summary: 'Observed evidence includes 3 persisted facts across service_presence:2, economy:1; latest observed at 2026-06-18T09:30:00Z.',
        },
      ],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByText('Planner evidence')).toBeTruthy();
    expect(screen.getByTestId('warehouse-evidence-source-canonical')).toBeTruthy();
    expect(screen.getByTestId('warehouse-evidence-source-observed')).toBeTruthy();
    expect(screen.getByTestId('warehouse-evidence-source-classes').textContent).toContain('Canonical evidence');
    expect(screen.getByTestId('warehouse-evidence-source-classes').textContent).toContain('Observed facts');
    expect(screen.getByTestId('warehouse-evidence-semantics').textContent).toContain('Canonical truth remains separate');
    expect(screen.getByTestId('warehouse-evidence-semantics').textContent).toContain('Observed report');
    expect(screen.getByTestId('warehouse-evidence-source-boundary').textContent).not.toMatch(/warehouse evidence is report-only/i);
  });

  it('renders not-evaluated freshness without implying fresh evidence', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      freshnessStatus: 'not_evaluated',
      evaluatedAt: null,
      manualReviewRequired: true,
      sourcePosture: 'provenance_bridge',
      evidenceEnvelope: {
        status: 'not_evaluated',
        sourceClasses: ['derived_report'],
        semantics: ['report_only_review_context', 'not_full_coverage'],
        reportOnly: true,
        selectedSystemOnly: true,
        plannerTruthSourceClass: 'canonical',
        claimsCanonicalTruth: false,
        claimsFullCoverage: false,
        summary: 'Selected-system evidence was not evaluated in this runtime. Source classes: derived report evidence.',
      },
      boundedStaging: {
        status: 'not_evaluated',
        reportOnly: true,
        boundedStagingOnly: true,
      },
      items: [
        {
          label: 'report_only',
          source: 'warehouse_report_only',
          summary: 'Selected-system warehouse evidence is only available as provenance fallback review context.',
        },
      ],
    };
    render(<WarehouseEvidenceCard evidence={evidence} />);

    expect(screen.getByTestId('warehouse-evidence-freshness-not_evaluated').textContent).toMatch(/not evaluated/i);
    expect(screen.getByTestId('warehouse-evidence-envelope-status-not_evaluated').textContent).toMatch(/not evaluated/i);
    expect(screen.getByTestId('warehouse-evidence-status-detail').textContent).toContain('The staging boundary was not safely queryable for this request.');
    expect(screen.getByTestId('warehouse-evidence-freshness-not_evaluated').textContent).not.toMatch(/fresh/i);
  });

  it('renders stale, risky/needs-review, unresolved, and blocked findings conservatively', () => {
    const evidence: PlannerWarehouseEvidence = {
      availability: 'report_only',
      reportOnly: true,
      freshnessStatus: 'stale',
      manualReviewRequired: true,
      sourcePosture: 'provenance_bridge',
      warnings: ['Warehouse freshness is stale; treat this per-system evidence as review-only context.'],
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
    expect(screen.getByTestId('warehouse-evidence-review-status').textContent).toContain('Manual review required');
    expect(screen.getByTestId('warehouse-evidence-source-posture-provenance_bridge').textContent).toMatch(/provenance fallback/i);
    expect(screen.getByTestId('warehouse-evidence-warnings').textContent).toContain('Warehouse freshness is stale');
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
