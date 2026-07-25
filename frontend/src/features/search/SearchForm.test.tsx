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

    fireEvent.click(screen.getByTestId('filter-module-system'));
    const colonyStatus = screen.getByLabelText('Colony status');
    expect(colonyStatus.textContent).toBe('Non-colonised only');
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

    fireEvent.click(screen.getByTestId('filter-module-reference'));
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

    fireEvent.click(screen.getByTestId('filter-module-reference'));
    fireEvent.focus(screen.getByTestId('ref-system-input'));
    fireEvent.click(screen.getByTestId('ref-system-option-42'));

    expect(onChange).toHaveBeenCalledWith({
      refName: 'Known',
      refCoords: { x: 1, y: 2, z: 3 },
    });
  });

  it('blocks search submission while the typed reference is unresolved', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [{ id64: 42, name: 'Known', x: 1, y: 2, z: 3, population: 0 }],
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

    fireEvent.click(screen.getByTestId('filter-module-reference'));
    fireEvent.change(screen.getByTestId('ref-system-input'), { target: { value: 'Know' } });

    expect(screen.getByTestId('search-submit').getAttribute('disabled')).not.toBeNull();
    expect(screen.getByTestId('reference-system-status').textContent).toMatch(/Pick a system from autocomplete/i);
  });

  it('uses enter to resolve the first valid autocomplete hit instead of submitting stale coordinates', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [{ id64: 42, name: 'Known', x: 1, y: 2, z: 3, population: 0 }],
      loading: false,
      err: null,
    });
    const onChange = vi.fn();
    const onSubmit = vi.fn();

    render(
      <SearchForm
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onSubmit={onSubmit}
        onReset={() => undefined}
      />,
    );

    fireEvent.click(screen.getByTestId('filter-module-reference'));
    const input = screen.getByTestId('ref-system-input');
    fireEvent.change(input, { target: { value: 'Know' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', charCode: 13 });

    expect(onChange).toHaveBeenCalledWith({
      refName: 'Known',
      refCoords: { x: 1, y: 2, z: 3 },
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('opens one adjacent filter workspace and returns focus when Done closes it', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [],
      loading: false,
      err: null,
    });
    const onWorkspaceChange = vi.fn();

    render(
      <SearchForm
        filters={DEFAULT_FILTERS}
        onChange={() => undefined}
        onSubmit={() => undefined}
        onReset={() => undefined}
        onWorkspaceChange={onWorkspaceChange}
      />,
    );

    const radiusModule = screen.getByTestId('filter-module-distance');
    fireEvent.click(radiusModule);

    expect(screen.getByTestId('filter-workspace')).toBeTruthy();
    expect(screen.getByText('Define the search area')).toBeTruthy();
    expect(onWorkspaceChange).toHaveBeenLastCalledWith(true);

    fireEvent.click(screen.getByTestId('filter-workspace-done'));

    expect(screen.queryByTestId('filter-workspace')).toBeNull();
    expect(onWorkspaceChange).toHaveBeenLastCalledWith(false);
    expect(document.activeElement).toBe(radiusModule);
  });

  it('gives every filter module a distinct icon and explanatory collapsed summary', () => {
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

    expect(screen.getByText('Search filters')).toBeTruthy();
    expect(screen.queryByText('categories')).toBeNull();
    expect(screen.getByRole('navigation', { name: 'Search filter categories' })).toBeTruthy();

    const expectedModules = [
      ['reference', 'Origin system', 'Distances measured from Sol', 'origin'],
      ['presets', 'Search profiles', 'Ready-made searches for common goals', 'profiles'],
      ['distance', 'Range & results', 'Within 200 LY · show up to 50', 'range'],
      ['system', 'Settlement & economy', 'Non-colonised · any economy', 'system'],
      ['high-value', 'Valuable worlds', 'Earth-like, water and ammonia worlds', 'high-value'],
      ['stars', 'Stellar objects', 'Black holes, neutron stars and more', 'stars'],
      ['landable', 'Accessible surfaces', 'Landable and walkable bodies', 'landable'],
      ['planetary', 'Planet classes', 'Rocky, icy, metal-rich and gas worlds', 'planetary'],
      ['signals', 'Rings & signals', 'Rings, geological and biological signals', 'signals'],
      ['sort', 'Sort results', 'Best development potential first', 'sort'],
    ] as const;

    const iconNames = new Set<string>();
    for (const [id, label, summary, iconName] of expectedModules) {
      const module = screen.getByTestId(`filter-module-${id}`);
      expect(module.textContent).toContain(label);
      expect(module.textContent).toContain(summary);
      const icon = module.querySelector('[data-icon]');
      expect(icon?.getAttribute('data-icon')).toBe(iconName);
      iconNames.add(iconName);
    }

    expect(iconNames.size).toBe(expectedModules.length);
  });

  it('names active body constraints instead of replacing them with a count', () => {
    vi.mocked(useAutocomplete).mockReturnValue({
      hits: [],
      loading: false,
      err: null,
    });

    render(
      <SearchForm
        filters={{
          ...DEFAULT_FILTERS,
          bodyRanges: {
            ...DEFAULT_FILTERS.bodyRanges,
            elw: { min: 1, max: 6 },
            ww: { min: 2, max: 4 },
            ammonia: { min: 1, max: 5 },
          },
        }}
        onChange={() => undefined}
        onSubmit={() => undefined}
        onReset={() => undefined}
      />,
    );

    expect(screen.getByTestId('filter-module-high-value').textContent)
      .toContain('Earth-like ≥ 1 · Water Worlds 2–4 · +1 more');
  });

  it('closes the active filter workspace with Escape', () => {
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

    fireEvent.click(screen.getByTestId('filter-module-sort'));
    expect(screen.getByTestId('filter-workspace')).toBeTruthy();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('filter-workspace')).toBeNull();
  });
});
