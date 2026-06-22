import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';

describe('NavBar', () => {
  it('exposes Explore / Plan / Review as primary player workspaces and keeps operator tools separate', () => {
    render(<NavBar current="watchlist" onNavigate={vi.fn()} health="Online" watchlistCount={2} />);

    expect(screen.getByTestId('nav-primary-explore').textContent).toContain('Explore');
    expect(screen.getByTestId('nav-primary-plan').textContent).toContain('Plan');
    expect(screen.getByTestId('nav-primary-review').textContent).toContain('Review');
    expect(screen.getByTestId('nav-primary-review').getAttribute('aria-current')).toBe('page');
    expect(screen.getByTestId('nav-operator-tools').textContent).toContain('Admin');
    expect(screen.getByTestId('nav-operator-tools').textContent).toContain('Operator');
  });

  it('renders route-specific secondary navigation within the active primary workspace', () => {
    const { rerender } = render(<NavBar current="search-tuning" onNavigate={vi.fn()} health="Online" />);

    expect(screen.getByTestId('nav-search-tuning').textContent).toContain('Advanced Search Tuning');
    expect(screen.queryByTestId('nav-fc')).toBeNull();

    rerender(<NavBar current="compare" onNavigate={vi.fn()} health="Online" compareCount={2} colonyCount={1} fcCount={1} />);
    expect(screen.getByTestId('nav-fc').textContent).toContain('FC Planner');
    expect(screen.getByTestId('nav-colony').textContent).toContain('Colony Tracker');
  });

  it('shows selected-system context only when provided and keeps primary navigation keyboard focusable', () => {
    render(
      <NavBar
        current="colony-planner"
        onNavigate={vi.fn()}
        health="Online"
        selectedSystem={{ id64: 123, name: 'Shinrarta Dezhra', loading: false }}
      />,
    );

    expect(screen.getByTestId('product-shell-context').textContent).toContain('Shinrarta Dezhra');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('ID64 123');

    const planButton = screen.getByTestId('nav-primary-plan');
    planButton.focus();
    expect(document.activeElement).toBe(planButton);
    expect(planButton.className).toContain('focus-visible:ring-2');
  });

  it('keeps menu closed by default and toggles open/close explicitly', () => {
    render(<NavBar current="colony-planner" onNavigate={vi.fn()} health="Online" />);

    expect(screen.queryByTestId('nav-menu-panel')).toBeNull();

    fireEvent.click(screen.getByTestId('nav-menu-toggle'));
    expect(screen.getByTestId('nav-menu-panel')).toBeTruthy();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('nav-menu-panel')).toBeNull();
  });

  it('closes the menu on route click and outside click', () => {
    const onNavigate = vi.fn();
    render(<NavBar current="colony-planner" onNavigate={onNavigate} health="Online" />);

    fireEvent.click(screen.getByTestId('nav-menu-toggle'));
    expect(screen.getByTestId('nav-menu-panel')).toBeTruthy();

    fireEvent.click(screen.getByTestId('nav-finder-menu'));
    expect(onNavigate).toHaveBeenCalledWith('finder');
    expect(screen.queryByTestId('nav-menu-panel')).toBeNull();

    fireEvent.click(screen.getByTestId('nav-menu-toggle'));
    expect(screen.getByTestId('nav-menu-panel')).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('nav-menu-panel')).toBeNull();
  });
});
