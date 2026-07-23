import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';

describe('NavBar', () => {
  it('shows one direct route strip without duplicated workspace headings', () => {
    render(<NavBar current="my-work" onNavigate={vi.fn()} health="Online" watchlistCount={2} />);

    expect(screen.queryByTestId('nav-group-explore')).toBeNull();
    expect(screen.queryByTestId('nav-group-plan')).toBeNull();
    expect(screen.queryByTestId('nav-group-review')).toBeNull();
    expect(screen.getByTestId('nav-player-routes')).toBeTruthy();
    expect(screen.getByTestId('nav-my-work').getAttribute('aria-current')).toBe('page');
    expect(screen.queryByTestId('nav-operator-tools')).toBeNull();
    expect(screen.queryByTestId('nav-admin')).toBeNull();
    expect(screen.queryByTestId('nav-operator')).toBeNull();
  });

  it('keeps all player routes visible instead of requiring a duplicate primary click layer', () => {
    const { rerender } = render(<NavBar current="my-work" onNavigate={vi.fn()} health="Online" />);

    expect(screen.getByTestId('nav-my-work').textContent).toContain('My Work');
    expect(screen.getByTestId('nav-finder').textContent).toContain('Finder');
    expect(screen.getByTestId('nav-compare').textContent).toContain('Compare');
    expect(screen.getByTestId('nav-my-work')).toBeTruthy();

    rerender(<NavBar current="compare" onNavigate={vi.fn()} health="Online" compareCount={2} fcCount={1} />);
    expect(screen.getByTestId('nav-fc').textContent).toContain('FC Route Planner');
    expect(screen.queryByTestId('nav-colony')).toBeNull();
  });

  it('shows selected-system context with evidence posture when a shared shell context exists', () => {
    const onOpenSelectedSystemInPlan = vi.fn();
    render(
      <NavBar
        current="map"
        onNavigate={vi.fn()}
        health="Online"
        onOpenSelectedSystemInPlan={onOpenSelectedSystemInPlan}
        selectedSystem={{
          id64: 123,
          name: 'Shinrarta Dezhra',
          loading: false,
          evidenceLabel: 'Available candidate',
          evidenceTone: 'available',
          evidenceSummary: 'Candidate remains in focus across Explore, Inspect, Plan, and Review.',
        }}
      />,
    );

    expect(screen.getByTestId('product-shell-context').textContent).toContain('Shinrarta Dezhra');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('ID64 123');
    expect(screen.getByTestId('selected-system-evidence-badge').textContent).toContain('Available candidate');
    expect(screen.getByTestId('product-shell-context').textContent).toContain('Candidate remains in focus across Explore, Inspect, Plan, and Review.');
    fireEvent.click(screen.getByTestId('nav-open-selected-system-plan'));
    expect(onOpenSelectedSystemInPlan).toHaveBeenCalledTimes(1);

    const plannerButton = screen.getByTestId('nav-colony-planner');
    plannerButton.focus();
    expect(document.activeElement).toBe(plannerButton);
    expect(plannerButton.className).toContain('focus-visible:ring-2');
  });

  it('uses full-width supporting text for Compare and removes its redundant Review eyebrow', () => {
    const { rerender } = render(<NavBar current="compare" onNavigate={vi.fn()} health="Online" />);

    const context = screen.getByTestId('product-shell-context');
    const supportingText = within(context).getByText('Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace.');
    expect(context.textContent).toContain('Decision review');
    expect(context.textContent).toContain('Compare');
    expect(within(context).queryByText(/^Review$/i)).toBeNull();
    expect(supportingText.className).toContain('max-w-none');
    expect(supportingText.className).not.toContain('max-w-3xl');

    // Map is now an immersive route: with no selected system it does not
    // render the large workspace-context header (keeps the map from being
    // pushed down by an extra stacked bar). It still appears once a system
    // is selected.
    rerender(<NavBar current="map" onNavigate={vi.fn()} health="Online" />);
    expect(screen.queryByTestId('product-shell-context')).toBeNull();

    rerender(
      <NavBar
        current="map"
        onNavigate={vi.fn()}
        health="Online"
        selectedSystem={{
          id64: 123,
          name: 'Shinrarta Dezhra',
          loading: false,
          evidenceLabel: 'Available candidate',
          evidenceTone: 'available',
          evidenceSummary: 'Candidate remains in focus for inspect hand-off from the map.',
        }}
      />,
    );
    expect(within(screen.getByTestId('product-shell-context')).getByText(/^Explore$/i)).toBeTruthy();
  });
  it('keeps Finder compact when no system is selected, but shows shell context once Plan owns a selected system', () => {
    const { rerender } = render(<NavBar current="finder" onNavigate={vi.fn()} health="Online" />);

    expect(screen.queryByTestId('product-shell-context')).toBeNull();
    expect(screen.queryByTestId('product-shell-context-mobile')).toBeNull();
    expect(screen.queryByText('Primary workspace')).toBeNull();
    expect(screen.queryByText('Discovery workspace')).toBeNull();
    expect(screen.queryByText('Next action')).toBeNull();

    rerender(
      <NavBar
        current="colony-planner"
        onNavigate={vi.fn()}
        health="Online"
        selectedSystem={{
          id64: 123,
          name: 'Shinrarta Dezhra',
          loading: false,
          evidenceLabel: 'Available candidate',
          evidenceTone: 'available',
          evidenceSummary: 'Planner keeps the selected system visible while player context moves between routes.',
        }}
      />,
    );

    expect(screen.getByTestId('product-shell-context').textContent).toContain('Shinrarta Dezhra');
    expect(screen.getByTestId('selected-system-evidence-badge').textContent).toContain('Available candidate');
    expect(screen.queryByTestId('nav-open-selected-system-plan')).toBeNull();

    for (const route of ['my-work', 'watchlist', 'pinned'] as const) {
      rerender(
        <NavBar
          current={route}
          onNavigate={vi.fn()}
          health="Online"
          onOpenSelectedSystemInPlan={vi.fn()}
          selectedSystem={{
            id64: 123,
            name: 'Shinrarta Dezhra',
            loading: false,
            evidenceLabel: 'Available candidate',
            evidenceTone: 'available',
            evidenceSummary: 'Planner keeps the selected system visible while player context moves between routes.',
          }}
        />,
      );

      expect(screen.getByTestId('product-shell-context').textContent).toContain('Shinrarta Dezhra');
      expect(screen.getByTestId('nav-my-work').getAttribute('aria-current')).toBe('page');
      expect(screen.getByTestId('nav-open-selected-system-plan')).toBeTruthy();
    }
  });

  it('renders one flat desktop navigation strip with direct destination tabs', () => {
    render(<NavBar current="colony-planner" onNavigate={vi.fn()} health="Online" />);

    const routeStrip = screen.getByTestId('nav-desktop-route-strip');
    expect(screen.queryByTestId('nav-group-explore')).toBeNull();
    expect(screen.queryByTestId('nav-group-plan')).toBeNull();
    expect(screen.queryByTestId('nav-group-review')).toBeNull();
    expect(routeStrip.contains(screen.getByTestId('nav-player-routes'))).toBe(true);
    expect(routeStrip.contains(screen.getByTestId('nav-my-work'))).toBe(true);
    expect(routeStrip.contains(screen.getByTestId('nav-colony-planner'))).toBe(true);
    expect(screen.getByTestId('nav-colony-planner').getAttribute('aria-current')).toBe('page');
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

  it('keeps admin and operator out of the standard mobile player menu', () => {
    render(<NavBar current="finder" onNavigate={vi.fn()} health="Online" />);

    fireEvent.click(screen.getByTestId('nav-menu-toggle'));

    expect(screen.getByTestId('nav-menu-panel')).toBeTruthy();
    expect(screen.queryByTestId('nav-admin-menu')).toBeNull();
    expect(screen.queryByTestId('nav-operator-menu')).toBeNull();
    expect(screen.queryByTestId('operator-mode-menu')).toBeNull();
  });

  it('renders a separate operator-mode panel with a return action on admin routes', () => {
    const onNavigate = vi.fn();
    render(<NavBar current="admin" onNavigate={onNavigate} health="Online" />);

    expect(screen.getByTestId('operator-mode-context-desktop').textContent).toContain('Separate mode: Operator');
    expect(screen.getByTestId('operator-mode-context-desktop').textContent).toContain('outside the normal Explore, Plan, and Review player journey');
    expect(screen.queryByTestId('nav-secondary-routes')).toBeNull();

    fireEvent.click(screen.getByTestId('nav-return-to-player-desktop'));
    expect(onNavigate).toHaveBeenCalledWith('finder');
  });
});
