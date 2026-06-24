import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from './useSystemDetail';
import { SystemDetailModal } from './SystemDetailModal';

vi.mock('./useSystemDetail', () => ({
  useSystemDetail: vi.fn(),
}));

vi.mock('./RatingRadar', () => ({ RatingRadar: () => <div>Rating radar</div> }));

const mockedUseSystemDetail = vi.mocked(useSystemDetail);

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
}

describe('SystemDetailModal Colony Planner entry point', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    vi.restoreAllMocks();
  });

  it('renders the new save-or-start planning entry point on System Detail', () => {
    mockLoadedSystem();

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
    expect(screen.getByRole('button', { name: /Start a plan/i })).toBeTruthy();
  });

  it('creates a draft only after explicit objective and manual start confirmation', () => {
    const onStartPlan = vi.fn();
    mockLoadedSystem();

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

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onStartPlan={() => undefined}
      />,
    );

    expect(screen.getByText('Journey stage: Inspect')).toBeTruthy();
    expect(screen.getByText('System Detail')).toBeTruthy();
    expect(screen.getByText('Rating radar')).toBeTruthy();
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

  it('shows a friendly disabled planner state when no workspace handler is available', () => {
    mockLoadedSystem();

    render(<SystemDetailModal id64={123} onClose={() => undefined} />);

    expect(screen.getByText('Planner unavailable')).toBeTruthy();
    expect(screen.getByText(/Planner routing is unavailable for this system record/i)).toBeTruthy();
    expect((screen.getByTestId('open-plan-start') as HTMLButtonElement).disabled).toBe(true);
  });

  it('saving a system does not create a plan', () => {
    const onStartPlan = vi.fn();
    const onToggleSaveForLater = vi.fn();
    mockLoadedSystem();

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
    expect(onToggleSaveForLater).toHaveBeenCalledWith(expect.objectContaining({ id64: 123 }));
    expect(onStartPlan).not.toHaveBeenCalled();
  });

  it('does not expose raw backend errors in the compact System Detail error state', () => {
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

  it('keeps normal modal close behaviours working without an embedded planner target', () => {
    const onClose = vi.fn();
    mockLoadedSystem();

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
