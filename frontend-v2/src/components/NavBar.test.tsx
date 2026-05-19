import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';

describe('NavBar', () => {
  it('renders Advanced Search Tuning with the search-tuning nav test id', () => {
    render(<NavBar current="search-tuning" onNavigate={vi.fn()} health="Online" />);

    expect(screen.getByTestId('nav-search-tuning').textContent).toContain('Advanced Search Tuning');
    expect(screen.getByTestId('nav-fc').textContent).toContain('FC Planner');
    expect(screen.getByTestId('nav-colony').textContent).toContain('Colony Tracker');
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
