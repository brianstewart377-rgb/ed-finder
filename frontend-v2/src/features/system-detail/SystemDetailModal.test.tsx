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

describe('SystemDetailModal inspection checkpoint', () => {
  afterEach(() => {
    mockedUseSystemDetail.mockReset();
    vi.restoreAllMocks();
  });

  it('renders a compact planning context without a start-plan control', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByTestId('system-detail-planning-context')).toBeTruthy();
    expect(screen.getByText('Inspection checkpoint')).toBeTruthy();
    expect(screen.getByText('Review this system before planning')).toBeTruthy();
    expect(screen.getByText('Inspection only')).toBeTruthy();
    expect(screen.getByText('opportunities, risks, uncertainty')).toBeTruthy();
    expect(screen.getByText('begins from a reviewed system')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Save for later/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Start a plan/i })).toBeNull();
    expect(screen.queryByText(/Draft/i)).toBeNull();
    expect(screen.queryByText(/Create draft/i)).toBeNull();
    expect(screen.getAllByText('Test System').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ID64 123').length).toBeGreaterThan(0);
  });

  it('shows reversible saved-state copy in System Detail', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        savedForLater
      />,
    );

    const button = screen.getByRole('button', { name: /Remove from saved/i });
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-pressed')).toBe('true');
  });

  it('keeps the planning context passive', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
      />,
    );

    expect(screen.queryByTestId('open-plan-start')).toBeNull();
    expect(screen.queryByTestId('plan-start-panel')).toBeNull();
    expect(screen.queryByTestId('confirm-start-plan')).toBeNull();
  });

  it('keeps the normal System Detail overview visible', () => {
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
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

  it('saving a system does not create a plan', () => {
    const onToggleSaveForLater = vi.fn();
    mockLoadedSystem();

    render(
      <SystemDetailModal
        id64={123}
        onClose={() => undefined}
        onToggleSaveForLater={onToggleSaveForLater}
      />,
    );

    fireEvent.click(screen.getByTestId('system-detail-save-for-later'));

    expect(onToggleSaveForLater).toHaveBeenCalledTimes(1);
    expect(onToggleSaveForLater).toHaveBeenCalledWith(expect.objectContaining({ id64: 123 }));
    expect(screen.queryByText(/Create draft/i)).toBeNull();
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
