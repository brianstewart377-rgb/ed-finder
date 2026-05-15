import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';

describe('NavBar', () => {
  it('renders Advanced Search Tuning with the search-tuning nav test id', () => {
    render(<NavBar current="search-tuning" onNavigate={vi.fn()} />);

    expect(screen.getByTestId('nav-search-tuning').textContent).toContain('Advanced Search Tuning');
  });
});
