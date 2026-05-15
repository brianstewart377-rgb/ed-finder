import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';

describe('NavBar', () => {
  it('renders Advanced Search Tuning while keeping the optimizer nav test id', () => {
    render(<NavBar current="optimizer" onNavigate={vi.fn()} />);

    expect(screen.getByTestId('nav-optimizer').textContent).toContain('Advanced Search Tuning');
  });
});
