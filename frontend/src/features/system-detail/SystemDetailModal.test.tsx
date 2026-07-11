import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { EvidenceSystemSummaryResponse, SystemArchetypeResponse, SystemDetail } from '@/types/api';
import { useSystemDetail } from './useSystemDetail';
import { useSystemArchetype } from './useSystemArchetype';
import { useSystemEvidenceSummary } from './useSystemEvidenceSummary';
import { SystemDetailModal } from './SystemDetailModal';

vi.mock('./RegionalPositionPanel', () => ({
  RegionalPositionPanel: ({ id64 }: { id64: number }) => (
    <div data-testid="regional-position-panel">Regional position {id64}</div>
  ),
}));

vi.mock('./useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('./useSystemArchetype', () => ({
  useSystemArchetype: vi.fn(),
}));

vi.mock('./useSystemEvidenceSummary', () => ({
  useSystemEvidenceSummary: vi.fn(),
}));

const mockedUseSystemDetail = vi.mocked(useSystemDetail);
const mockedUseSystemArchetype = vi.mocked(useSystemArchetype);
const mockedUseSystemEvidenceSummary = vi.mocked(useSystemEvidenceSummary);

const system = {
  id64: 123,
  name: 'Test System',
  x: 1,
  y: 2,
  z: 3,
  bodies: [],
  stations: [],
} as unknown as SystemDetail;

function mockLoadedSystem(overrides: Partial<SystemDetail> = {}) {
  mockedUseSystemDetail.mockReturnValue({
    data: { ...system, ...overrides } as SystemDetail,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
  mockLoadedEvidenceSummary();
}

function mockLoadedArchetype(overrides: Partial<SystemArchetypeResponse> = {}) {
  mockedUseSystemArchetype.mockReturnValue({
    data: {
      id64: 123,
      name: 'Test System',
      archetypes: {
        refinery_industrial: {
          score: 92,
          tier: 'A',
          label: 'Refinery / Industrial Megacomplex',
          rationale: {
            headline: 'Strong refinery-industrial fit with scalable slot capacity.',
            positives: ['Dense industrial body mix', 'Good buildability'],
            risks: ['Surface-port evidence remains partial'],
            tags: ['industrial', 'slots'],
          },
        },
      },
      primary_archetype: 'refinery_industrial',
      secondary_archetype: 'trade_logistics',
      overall_development_potential: 88,
      buildability_score: 81,
      purity_score: 74,
      confidence: 0.82,
      tags: ['industrial'],
      ...overrides,
    } as SystemArchetypeResponse,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
}

function mockLoadedEvidenceSummary(overrides: Partial<EvidenceSystemSummaryResponse> = {}) {
  mockedUseSystemEvidenceSummary.mockReturnValue({
    data: {
      schema_version: 'evidence_store/v1',
      system_id64: 123,
      observed_fact_count: 0,
      imported_record_count: 0,
      derived_feature_count: 0,
      open_rule_proposal_count: 0,
      focus_areas: [],
      records: [],
      derived_features: [],
      open_rule_proposals: [],
      ...overrides,
    } as EvidenceSystemSummaryResponse,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
}

describe('SystemDetailModal Colony Planner entry point', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    mockedUseSystemArchetype.mockReset();
    mockedUseSystemEvidenceSummary.mockReset();
    vi.restoreAllMocks();
  });

  it('renders the new save-or-start planning entry point on System Detail', () => {
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByTestId('colony-planner-entry-card')).toBeTruthy();
    expect(screen.getByText('Planning available')).toBeTruthy();
    expect(screen.queryByText('Inspection checkpoint')).toBeNull();
    expect(screen.queryByText('Inspection only')).toBeNull();
    expect(
      screen.getByText(
        /Assess this system, save it for later if needed, then create an intentional draft/i,
      ),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /Save for later/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Start a plan/i })).toBeTruthy();
    expect(screen.getAllByText('Test System').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ID64 123').length).toBeGreaterThan(0);
  });

  it('shows reversible saved-state copy in System Detail without hiding plan start', () => {
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        savedForLater
        onStartPlan={() => undefined}
      />,
    );

    const button = screen.getByRole('button', { name: /Remove from saved/i });
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('Saved')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Start a plan/i })).toBeTruthy();
  });

  it('shows in-progress save feedback and disables duplicate System Detail saves', () => {
    const onToggleSaveForLater = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        saveForLaterState="saving"
        onToggleSaveForLater={onToggleSaveForLater}
        onStartPlan={() => undefined}
      />,
    );

    const button = screen.getByRole('button', { name: /Save for later/i }) as HTMLButtonElement;
    expect(screen.getByText('Saving…')).toBeTruthy();
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onToggleSaveForLater).not.toHaveBeenCalled();
  });

  it('creates a draft only after explicit objective and manual start confirmation', () => {
    const onStartPlan = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={onStartPlan}
      />,
    );

    fireEvent.click(screen.getByTestId('open-plan-start'));
    expect(screen.getByTestId('plan-start-panel')).toBeTruthy();
    expect(onStartPlan).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('plan-objective-materials_coverage'));
    fireEvent.click(screen.getByTestId('plan-approach-manual'));
    expect(screen.getByText('Test System - Materials coverage')).toBeTruthy();

    fireEvent.click(screen.getByTestId('confirm-start-plan'));

    expect(onStartPlan).toHaveBeenCalledTimes(1);
    expect(onStartPlan).toHaveBeenCalledWith(
      expect.objectContaining({ id64: 123, name: 'Test System' }),
      {
        objective: 'materials_coverage',
        startApproach: 'manual',
      },
    );
  });

  it('accepts decide-later plus recommendation-assisted as a valid plan start', () => {
    const onStartPlan = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={onStartPlan}
      />,
    );

    fireEvent.click(screen.getByTestId('open-plan-start'));
    fireEvent.click(screen.getByTestId('plan-objective-decide_later'));
    fireEvent.click(screen.getByTestId('plan-approach-recommendation'));
    fireEvent.click(screen.getByTestId('confirm-start-plan'));

    expect(onStartPlan).toHaveBeenCalledTimes(1);
    expect(onStartPlan).toHaveBeenCalledWith(
      expect.objectContaining({ id64: 123 }),
      {
        objective: 'decide_later',
        startApproach: 'recommendation_assisted',
      },
    );
  });

  it('keeps the normal System Detail overview visible', () => {
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByText('Journey stage: Inspect')).toBeTruthy();
    expect(screen.getByText('System Detail')).toBeTruthy();
    expect(screen.getByText('Archetype assessment')).toBeTruthy();
    expect(screen.getByTestId('archetype-primary').textContent).toContain('Refinery / Industrial Megacomplex');
    expect(screen.getByTestId('regional-position-panel').textContent).toContain('123');
    expect(screen.getByText('System info')).toBeTruthy();
    expect(screen.getByText('Coordinates')).toBeTruthy();
    expect(screen.getByText('External')).toBeTruthy();
  });

  it('shows station body, lane, and association provenance in the stations panel', () => {
    mockLoadedSystem({
      name: 'Exioce',
      stations: [
        {
          id: 2001,
          market_id: 2001,
          name: 'Macmillan Depot',
          station_type: 'Orbis',
          body_id: 31,
          body_name: 'Exioce 3 d',
          lane: 'orbital',
          association_status: 'confirmed',
          association_confidence: 'exact',
          association_source: 'edsm_body_name',
          landing_pad_size: 'L',
        },
        {
          id: 2002,
          market_id: 2002,
          name: 'Fort Lawrence',
          station_type: 'Orbis',
          body_id: 4,
          body_name: 'Exioce 4',
          lane: 'orbital',
          association_status: 'confirmed',
          association_confidence: 'exact',
          association_source: 'edsm_body_name',
          landing_pad_size: 'L',
        },
        {
          id: 2003,
          market_id: 2003,
          name: 'Miller Terminal',
          station_type: 'Coriolis',
          body_id: 52,
          body_name: 'Exioce 5 b',
          lane: 'orbital',
          association_status: 'confirmed',
          association_confidence: 'exact',
          association_source: 'edsm_body_name',
          landing_pad_size: 'L',
        },
        {
          id: 2004,
          market_id: 2004,
          name: 'T9J-99T',
          station_type: 'Unknown',
          association_status: 'unresolved',
          association_confidence: 'unresolved',
          association_source: 'unknown',
        },
      ],
    } as unknown as Partial<SystemDetail>);
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    const table = screen.getByTestId('system-detail-stations-table');
    const macmillanRow = within(table).getByText('Macmillan Depot').closest('tr') as HTMLElement;
    const fortRow = within(table).getByText('Fort Lawrence').closest('tr') as HTMLElement;
    const millerRow = within(table).getByText('Miller Terminal').closest('tr') as HTMLElement;
    const carrierRow = within(table).getByText('T9J-99T').closest('tr') as HTMLElement;

    expect(within(macmillanRow).getByText('Exioce 3 d')).toBeTruthy();
    expect(within(macmillanRow).getByText('Confirmed / exact / EDSM')).toBeTruthy();
    expect(within(macmillanRow).getByText('Orbital')).toBeTruthy();
    expect(within(fortRow).getByText('Exioce 4')).toBeTruthy();
    expect(within(fortRow).getByText('Confirmed / exact / EDSM')).toBeTruthy();
    expect(within(millerRow).getByText('Exioce 5 b')).toBeTruthy();
    expect(within(millerRow).getByText('Confirmed / exact / EDSM')).toBeTruthy();
    expect(within(carrierRow).getByText('Transient / non-slot')).toBeTruthy();
    expect(within(carrierRow).getByText('Fleet Carrier / transient / ignored for colony planning')).toBeTruthy();
  });

  it('surfaces body-data and colonisation freshness cues in system info', () => {
    mockLoadedSystem({
      body_data_updated_at: '2026-07-11T09:00:00Z',
      body_data_sources: ['eddn_scan', 'frontier_journal_scan'],
      status_updated_at: '2026-07-11T10:15:00Z',
      status_source: 'eddn',
    } as Partial<SystemDetail>);
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByText('Body data freshness')).toBeTruthy();
    expect(screen.getByText(/Frontier Journal/i)).toBeTruthy();
    expect(screen.getByText('Colonisation state')).toBeTruthy();
    expect(screen.getAllByText(/EDDN/i).length).toBeGreaterThan(0);
  });

  it('renders the new evidence panel with active lifecycle-managed records', () => {
    mockLoadedSystem();
    mockLoadedArchetype();
    mockLoadedEvidenceSummary({
      observed_fact_count: 6,
      imported_record_count: 2,
      derived_feature_count: 1,
      open_rule_proposal_count: 1,
      focus_areas: [
        {
          key: 'colonisation_status',
          label: 'Colonisation status',
          posture: 'evidence_linked',
          summary: 'Colonisation state observed from the live relay.',
          evidence_type: 'colonisation_status',
          evidence_key: 'evd_col_status',
        },
        {
          key: 'station_set',
          label: 'Station set',
          posture: 'canonical_present',
          summary: 'Canonical station data currently includes 4 stations for this system.',
          evidence_type: null,
          evidence_key: null,
        },
      ],
      records: [
        {
          evidence_key: 'evd_col_status',
          system_id64: 123,
          source_name: 'eddn',
          origin: 'imported',
          subject_type: 'system',
          subject_id: '123',
          evidence_type: 'colonisation_status',
          record_status: 'active',
          freshness_status: 'current',
          confidence: 'high',
          summary: 'Colonisation state observed from the live relay.',
          source_record_id: null,
          source_run_key: 'run_eddn_1',
          observed_at: '2026-07-11T10:15:00Z',
          collected_at: '2026-07-11T10:15:30Z',
          expires_at: null,
          value: { is_colonised: true },
          provenance: {},
          tags: [],
          metadata: {},
          created_at: '2026-07-11T10:15:30Z',
          updated_at: '2026-07-11T10:15:30Z',
        },
      ],
      derived_features: [
        {
          feature_key: 'feat_station_set',
          system_id64: 123,
          feature_name: 'station_set_completeness',
          feature_version: 'v1',
          feature_status: 'active',
          confidence: 'medium',
          summary: 'Station-set evidence looks complete for the current relay horizon.',
          derived_from_run_key: 'run_eddn_1',
          derived_at: '2026-07-11T10:16:00Z',
          expires_at: null,
          value: {},
          evidence_refs: ['evd_col_status'],
          metadata: {},
          created_at: '2026-07-11T10:16:00Z',
          updated_at: '2026-07-11T10:16:00Z',
        },
      ],
      open_rule_proposals: [
        {
          proposal_key: 'prop_station_review',
          proposal_type: 'station_set_review',
          domain: 'system_detail',
          scope_type: 'system',
          scope_key: '123',
          status: 'pending_review',
          priority: 'medium',
          risk_level: 'low',
          auto_approval_eligible: false,
          summary: 'Review the current station-set evidence against operator notes.',
          proposed_by: 'evidence-pipeline',
          decided_by: null,
          decision_notes: null,
          proposed_change: {},
          evidence_refs: ['evd_col_status'],
          impact_summary: {},
          metadata: {},
          created_at: '2026-07-11T10:17:00Z',
          updated_at: '2026-07-11T10:17:00Z',
          decided_at: null,
        },
      ],
    });

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    const evidenceSection = screen.getByTestId('system-detail-evidence-section');
    expect(screen.getByText('Evidence')).toBeTruthy();
    expect(evidenceSection).toBeTruthy();
    expect(screen.getByText('Active evidence linked')).toBeTruthy();
    expect(screen.getAllByText(/Colonisation state observed from the live relay/i).length).toBeGreaterThan(0);
    expect(evidenceSection.textContent).toContain('Observed facts: 6');
    expect(evidenceSection.textContent).toContain('Derived features: 1');
    expect(evidenceSection.textContent).toContain('Open proposals: 1');
    expect(screen.getByTestId('system-evidence-focus-colonisation_status').textContent).toContain('Evidence linked');
    expect(screen.getByTestId('system-evidence-focus-station_set').textContent).toContain('Canonical present');
    expect(screen.getByText(/Station set completeness/i)).toBeTruthy();
    expect(screen.getByText(/Review the current station-set evidence against operator notes/i)).toBeTruthy();
  });

  it('uses canonical fallback focus areas so known system facts do not read as unknown', () => {
    mockLoadedSystem();
    mockLoadedArchetype();
    mockLoadedEvidenceSummary({
      observed_fact_count: 0,
      imported_record_count: 0,
      derived_feature_count: 0,
      open_rule_proposal_count: 0,
      focus_areas: [
        {
          key: 'body_completeness',
          label: 'Body coverage',
          posture: 'canonical_present',
          summary: 'Canonical body data currently covers 12/15 scanned bodies for this system.',
          evidence_type: null,
          evidence_key: null,
        },
        {
          key: 'station_set',
          label: 'Station set',
          posture: 'canonical_present',
          summary: 'Canonical station data currently includes 3 stations for this system.',
          evidence_type: null,
          evidence_key: null,
        },
      ],
    });

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByText('Canonical data linked')).toBeTruthy();
    expect(screen.getByTestId('system-evidence-focus-body_completeness').textContent).toContain('Canonical present');
    expect(screen.getByText(/covers 12\/15 scanned bodies/i)).toBeTruthy();
    expect(screen.queryByText('No evidence linked')).toBeNull();
  });

  it('shows the compact evidence-unavailable state without hiding canonical system detail', () => {
    const retryEvidence = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();
    mockedUseSystemEvidenceSummary.mockReturnValue({
      data: null,
      loading: false,
      error: 'evidence fetch failed',
      refetch: retryEvidence,
    });

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByText(/Evidence detail is unavailable right now/i)).toBeTruthy();
    expect(screen.getByText('System info')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));
    expect(retryEvidence).toHaveBeenCalledTimes(1);
  });

  it('shows a friendly disabled planner state when no workspace handler is available', () => {
    mockLoadedSystem();
    mockLoadedArchetype();

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByText('Planner unavailable')).toBeTruthy();
    expect(screen.getByText(/Planner routing is unavailable for this system record/i)).toBeTruthy();
    expect((screen.getByTestId('open-plan-start') as HTMLButtonElement).disabled).toBe(true);
  });

  it('saving a system does not create a plan', () => {
    const onStartPlan = vi.fn();
    const onToggleSaveForLater = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onToggleSaveForLater={onToggleSaveForLater}
        onStartPlan={onStartPlan}
      />,
    );

    fireEvent.click(screen.getByTestId('system-detail-save-for-later'));

    expect(onToggleSaveForLater).toHaveBeenCalledTimes(1);
    expect(onToggleSaveForLater).toHaveBeenCalledWith(expect.objectContaining({
      system: expect.objectContaining({ id64: 123 }),
    }));
    expect(onStartPlan).not.toHaveBeenCalled();
  });

  it('does not expose raw backend errors in the compact System Detail error state', () => {
    mockLoadedArchetype();
    mockLoadedEvidenceSummary();
    mockedUseSystemDetail.mockReturnValue({
      data: null,
      loading: false,
      error: '{"trace":"backend exploded"}',
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByText(/System detail is unavailable right now/i)).toBeTruthy();
    expect(screen.queryByText(/backend exploded/i)).toBeNull();
  });

  it('falls back to the development snapshot already present on system detail when the archetype refresh fails', () => {
    mockLoadedSystem({
      primary_archetype: 'refinery_industrial',
      overall_development_potential: 86,
      buildability_score: 79,
      purity_score: 72,
      archetype_confidence: 0.77,
    } as Partial<SystemDetail>);
    mockedUseSystemArchetype.mockReturnValue({
      data: null,
      loading: false,
      error: 'boom',
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} onStartPlan={() => undefined} />);

    expect(screen.getByTestId('archetype-assessment')).toBeTruthy();
    expect(screen.getByTestId('archetype-assessment-warning').textContent).toContain('Using the development snapshot already loaded with system detail');
    expect(screen.getByTestId('archetype-primary').textContent).toContain('Refinery / Industrial Megacomplex');
    expect(screen.getByText('Development score snapshot 86. Buildability 79. Purity 72.')).toBeTruthy();
  });

  it('falls back to the legacy system-detail score when archetype rows are missing', () => {
    mockLoadedSystem({
      primary_economy: 'Industrial',
      score: 68,
      overall_development_potential: null,
      buildability_score: null,
      purity_score: null,
    } as Partial<SystemDetail>);
    mockedUseSystemArchetype.mockReturnValue({
      data: null,
      loading: false,
      error: 'boom',
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} onStartPlan={() => undefined} />);

    expect(screen.getByTestId('archetype-assessment')).toBeTruthy();
    expect(screen.getByTestId('archetype-assessment-warning').textContent).toContain('Using the development snapshot already loaded with system detail');
    expect(screen.getByTestId('archetype-primary').textContent).toContain('Industrial');
    expect(screen.getByText('Development score snapshot 68. Using the score already present on system detail until archetype rows refresh.')).toBeTruthy();
  });

  it('shows the compact unavailable state when neither live nor fallback archetype data exists', () => {
    mockLoadedSystem();
    mockedUseSystemArchetype.mockReturnValue({
      data: null,
      loading: false,
      error: 'boom',
      refetch: vi.fn(),
    });

    render(<SystemDetailModal id64={123} onClose={() => undefined} onStartPlan={() => undefined} />);

    expect(screen.getByTestId('archetype-assessment-error')).toBeTruthy();
    expect(screen.getByText(/retry to refresh the development assessment/i)).toBeTruthy();
  });

  it('keeps normal modal close behaviours working without an embedded planner target', () => {
    const onClose = vi.fn();
    mockLoadedSystem();
    mockLoadedArchetype();

    render(
      <SystemDetailModal
        id64={123}
        onClose={onClose}
        onStartPlan={() => undefined}
      />,
    );

    fireEvent.click(screen.getByTestId('system-detail-close'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByTestId('system-detail-modal'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
