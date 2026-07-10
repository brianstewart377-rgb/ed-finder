import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SearchForm } from './SearchForm';
import { DEFAULT_FILTERS } from './useSearch';
import { useAutocomplete } from './useAutocomplete';

vi.mock('./useAutocomplete', () => ({
  useAutocomplete: vi.fn(),
}));

describe('SearchForm reference autocomplete data trust', () => {
  it('defaults colony status to non-colonised only on each fresh load', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [],
      loading: false,
      err: null,
    });

    render(
      <SearchForm
        filters={DEFAULT_FILTERS}
        onChange={() => undefined}
        onSubmit={() => undefined}
        onReset={() => undefined}
      />,
    );

    const colonyStatus = screen.getByLabelText('Colony status') as HTMLSelectElement;
    expect(colonyStatus.value).toBe('uninhabited');
    expect(screen.getByRole('option', { name: 'Non-colonised only' })).toBeTruthy();
  });

  it('does not accept unknown-coordinate reference systems', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [{ id64: 2008132031194, name: 'Exioce', x: 0, y: 0, z: 0, population: 0 }],
      loading: false,
      err: null,
    });
    const onChange = vi.fn();

    render(
      <SearchForm
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onSubmit={() => undefined}
        onReset={() => undefined}
      />,
    );

    fireEvent.focus(screen.getByTestId('ref-system-input'));
    fireEvent.click(screen.getByTestId('ref-system-option-2008132031194'));

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText('Unknown')).toBeTruthy();
  });

  it('accepts known reference coordinates', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [{ id64: 42, name: 'Known', x: 1, y: 2, z: 3, population: 0 }],
      loading: false,
      err: null,
    });
    const onChange = vi.fn();

    render(
      <SearchForm
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onSubmit={() => undefined}
        onReset={() => undefined}
      />,
    );

    fireEvent.focus(screen.getByTestId('ref-system-input'));
    fireEvent.click(screen.getByTestId('ref-system-option-42'));

    expect(onChange).toHaveBeenCalledWith({
      refName: 'Known',
      refCoords: { x: 1, y: 2, z: 3 },
    });
  });
});
