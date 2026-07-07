import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SequenceCockpitWorkspaceView } from './SequenceCockpitWorkspaceView';


describe('SequenceCockpitWorkspaceView', () => {
  it('renders explicit build order and manual preview guidance before a preview run', () => {
    const onRunPreview = vi.fn();

    render(
      <SequenceCockpitWorkspaceView
        placements={[
          {
            facility_template_id: 'orbital_port_small',
            local_body_id: '12',
            is_primary_port: true,
            build_order: 1,
          },
          {
            facility_template_id: 'agri_hub',
            local_body_id: '13',
            is_primary_port: false,
            build_order: 2,
          },
        ] as never}
        templates={[
          { id: 'orbital_port_small', name: 'Orbital Port', is_port: true },
          { id: 'agri_hub', name: 'Agriculture Hub', is_port: false },
        ] as never}
        bodies={[
          { id: 12, name: 'Body A' },
          { id: 13, name: 'Body B' },
        ] as never}
        result={null}
        isResultStale={false}
        canRun={true}
        running={false}
        onRunPreview={onRunPreview}
      />,
    );

    expect(screen.getByTestId('sequence-cockpit-workspace-view')).toBeTruthy();
    expect(screen.getByText(/Build order and CP tradeoffs are explicit here/)).toBeTruthy();
    expect(screen.getByText('1. Orbital Port')).toBeTruthy();
    expect(screen.getByText('2. Agriculture Hub')).toBeTruthy();
    expect(screen.getByText('Primary port')).toBeTruthy();
    expect(screen.getByText(/CP curve, timeline, and repair suggestions appear after an explicit Preview run/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Run Preview' }));
    expect(onRunPreview).toHaveBeenCalledTimes(1);
  });

  it('renders CP summary, timeline, and stale warning when preview data exists', () => {
    render(
      <SequenceCockpitWorkspaceView
        placements={[] as never}
        templates={[] as never}
        bodies={[] as never}
        result={{
          cp: {
            yellow_cp_final: 12,
            green_cp_final: -3,
            t2_ports: 1,
            t3_ports: 0,
            warnings: ['Port upgrade bottleneck'],
          },
          cp_timeline: [
            {
              step: 1,
              facility_template_id: 'orbital_port_small',
              facility_name: 'Orbital Port',
              yellow_delta: 5,
              green_delta: -1,
              yellow_before: 0,
              yellow_after: 5,
              green_before: 0,
              green_after: -1,
              warnings: ['Use a repair step later'],
            },
          ],
          cp_repair_suggestions: [
            {
              type: 'resequence',
              severity: 'high',
              summary: 'Move the port later',
              reason: 'Reduces early CP pressure',
              expected_effect: 'Improves yellow CP curve',
              action: 'Resequence',
              affected_steps: [1],
              confidence: 'high',
              caveats: ['May slow early exports'],
              suggested_action: null,
            },
          ],
        } as never}
        isResultStale={true}
        canRun={true}
        running={false}
        onRunPreview={() => {}}
      />,
    );

    expect(screen.getByText(/Preview-derived CP metrics are stale/)).toBeTruthy();
    expect(screen.getByText('Construction points')).toBeTruthy();
    expect(screen.getByText('CP build-order timeline')).toBeTruthy();
    expect(screen.getByText('CP Repair Suggestions')).toBeTruthy();
  });
});
