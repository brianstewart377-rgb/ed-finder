import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { SelectedSystemRouteBar } from './SelectedSystemRouteBar';

vi.mock('@/lib/api', () => ({ api: { system: vi.fn() } }));

const mockedSystem = vi.mocked(api.system);

afterEach(() => {
  window.location.hash = '';
  mockedSystem.mockReset();
});

describe('SelectedSystemRouteBar', () => {
  it('shows name, evidence posture, then supporting ID64 for a non-modal Finder context route', async () => {
    window.location.hash = '#finder/context/123456';
    mockedSystem.mockResolvedValue({ id64: 123456, name: 'Lave' } as never);

    render(<SelectedSystemRouteBar />);

    await waitFor(() => expect(screen.getByTestId('selected-system-context-name').textContent).toContain('Lave'));
    const bar = screen.getByTestId('selected-system-context-bar');
    const text = bar.textContent ?? '';
    expect(text.indexOf('Lave')).toBeLessThan(text.indexOf('System detail available'));
    expect(text.indexOf('System detail available')).toBeLessThan(text.indexOf('ID64 123456'));
    expect(screen.queryByTestId('selected-system-context-inspect')).not.toBeNull();
  });

  it('shows an honest recovery state for an invalid selected-system link without fetching a prior system', () => {
    window.location.hash = '#finder/context/not-a-number';

    render(<SelectedSystemRouteBar />);

    expect(screen.getByTestId('selected-system-context-error').textContent).toContain('invalid');
    expect(mockedSystem).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('selected-system-context-recover'));
    expect(window.location.hash).toBe('#finder');
  });
});
