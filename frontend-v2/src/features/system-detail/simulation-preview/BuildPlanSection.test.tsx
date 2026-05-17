import { vi, describe, expect, it, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BuildPlanSection } from './BuildPlanSection';
import { importSystemLayout } from '@/lib/api';
import type { FacilityTemplate, SystemBody, SimulateBuildResponse, LayoutImportResponse } from '@/types/api';
import type { StartMode } from './types';

vi.mock('@/lib/api', () => ({
  importSystemLayout: vi.fn(),
}));

const mockedImportSystemLayout = vi.mocked(importSystemLayout);

const templateMinimal: FacilityTemplate = {
  category: 'port',
  confidence: 'inferred',
  id: 'generic_port_alpha',
  name: 'Generic Port Alpha',
  tier: 1,
  economy: null,
  is_port: true,
  is_support_facility: false,
  allowed_location: 'surface_or_orbit',
  pad_size: 'large',
  notes: null,
  yellow_cp_generated: 0,
  green_cp_generated: 0,
  yellow_cp_cost: 0,
  green_cp_cost: 0,
};

const bodies: SystemBody[] = [{ id: 1, name: 'Body 1', body_type: 'Planet', is_landable: true }];
const previewResult: SimulateBuildResponse = {
  system_id64: 123,
  mechanics_version: 'colonisation-engine-v2.1',
  target_archetype: 'refinery_industrial',
  final_score: 70,
  composition_score: 70,
  buildability_score: 70,
  build_complexity: 'moderate',
  confidence: 0.82,
  cp: {
    yellow_cp_final: 0,
    green_cp_final: 0,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_spent: 0,
    green_cp_spent: 0,
    t2_ports: 0,
    t3_ports: 0,
    warnings: [],
  },
  cp_timeline: [],
  cp_repair_suggestions: [],
  observation_summary: {
    status: 'predicted_only',
    observed_facts_count: 0,
    confirmed_count: 0,
    mismatch_count: 0,
    observed_only_count: 0,
    predicted_only_count: 0,
    unknown_count: 0,
    confidence_impact: 'none',
    summary: 'No observations yet.',
  },
  prediction_observation_diffs: [],
  economy_composition: {},
  economy_order: [],
  economy_stack: {},
  port_economy_states: [],
  influence_ledger: [],
  inherited_economies: [],
  topology: {},
  services: {},
  port_service_states: [],
  service_unlock_ledger: [],
  data_quality: {
    slots: 'estimated',
    facility_catalogue: 'community_observed',
    topology: 'inferred',
  },
  confidence_signals: [],
  mechanics_trace: {},
  top_two_alignment: 'none',
  contamination_risk: 'low',
  warnings: [],
  strengths: [],
  recommendations: [],
  mechanics_notes: [],
  links: { strong_links: [], weak_links: [] },
};

function renderPlan(systemId64: number) {
  return render(
    <BuildPlanSection
      systemId64={systemId64}
      systemName="Test System"
      startMode={'blank_advanced' as StartMode}
      hasRecommendedBuild={false}
      loadingRecommended={false}
      targetArchetype="refinery_industrial"
      onTargetArchetypeChange={vi.fn()}
      placements={[]}
      templates={[templateMinimal]}
      bodies={bodies}
      templatesLoading={false}
      templatesErrorMessage={null}
      optimiserCandidateOriginLabel={null}
      optimiserCandidateWasEdited={false}
      initialAssumptions={[]}
      previewResult={previewResult}
      isPreviewResultStale={false}
      runningPreview={false}
      onUseRecommended={vi.fn()}
      onBlank={vi.fn()}
      onShowSuggestedBuilds={vi.fn()}
      onAddPlacement={vi.fn()}
      onUpdatePlacement={vi.fn()}
      onRemovePlacement={vi.fn()}
      onMovePlacement={vi.fn()}
    />,
  );
}

describe('BuildPlanSection layout import state', () => {
  beforeEach(() => {
    mockedImportSystemLayout.mockReset();
  });

  afterEach(() => {
    mockedImportSystemLayout.mockReset();
  });

  it('clears layout import status when system changes', async () => {
    mockedImportSystemLayout.mockRejectedValue(new Error('network unavailable'));

    const { rerender } = renderPlan(123);

    fireEvent.click(screen.getByRole('button', { name: /Import \/ refresh system layout/i }));
    expect(mockedImportSystemLayout).toHaveBeenCalledWith(123, { source: 'spansh' });
    expect(await screen.findByText(/Layout import failed: network unavailable/)).toBeTruthy();

    rerender(
      <BuildPlanSection
        systemId64={456}
        systemName="Next System"
        startMode={'blank_advanced' as StartMode}
        hasRecommendedBuild={false}
        loadingRecommended={false}
        targetArchetype="refinery_industrial"
        onTargetArchetypeChange={vi.fn()}
        placements={[]}
        templates={[templateMinimal]}
        bodies={bodies}
        templatesLoading={false}
        templatesErrorMessage={null}
        optimiserCandidateOriginLabel={null}
        optimiserCandidateWasEdited={false}
        initialAssumptions={[]}
        previewResult={previewResult}
        isPreviewResultStale={false}
        runningPreview={false}
        onUseRecommended={vi.fn()}
        onBlank={vi.fn()}
        onShowSuggestedBuilds={vi.fn()}
        onAddPlacement={vi.fn()}
        onUpdatePlacement={vi.fn()}
        onRemovePlacement={vi.fn()}
        onMovePlacement={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText(/Layout import failed: network unavailable/)).toBeNull();
    });
  });

  it('renders layout import success status after successful import', async () => {
    const importResult: LayoutImportResponse = {
      system_id64: 123,
      source: 'spansh',
      status: 'success',
      fetched_at: '2026-05-16T00:00:00Z',
      summary: {
        bodies_found: 4,
        stations_found: 2,
        bodies_upserted: 4,
        stations_upserted: 2,
        warnings_count: 0,
      },
      warnings: [],
      errors: [],
    };
    mockedImportSystemLayout.mockResolvedValue(importResult);

    renderPlan(123);

    fireEvent.click(screen.getByRole('button', { name: /Import \/ refresh system layout/i }));
    expect(await screen.findByText(/Status/)).toBeTruthy();
    expect(await screen.findByText('success')).toBeTruthy();
  });
});
