import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ADMIN_TOKEN_SESSION_KEY } from '$lib/api/client';
import { adminToken } from '$lib/persistence/stores';
import SessionAdminTokenControl from './SessionAdminTokenControl.svelte';

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  adminToken.clear();
  adminToken.hydrate();
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  adminToken.clear();
});

describe('SessionAdminTokenControl', () => {
  it('stores an explicitly entered token only for the browser session', async () => {
    render(SessionAdminTokenControl);

    await fireEvent.input(screen.getByTestId('session-admin-token-input'), {
      target: { value: '  bounded-token  ' },
    });
    await fireEvent.click(screen.getByTestId('session-admin-token-save'));

    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBe(
      'bounded-token',
    );
    expect(localStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
    await waitFor(() =>
      expect(
        screen.getByTestId('session-admin-token-status'),
      ).toHaveTextContent('A session token is configured.'),
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Session admin token saved.',
    );
  });

  it('clears the compatibility credential without touching owner-claim state', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'existing-token');
    adminToken.hydrate();
    render(SessionAdminTokenControl);

    await waitFor(() =>
      expect(screen.getByTestId('session-admin-token-clear')).toBeEnabled(),
    );
    await fireEvent.click(screen.getByTestId('session-admin-token-clear'));

    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
    expect(screen.getByTestId('session-admin-token-status')).toHaveTextContent(
      'No session token is configured.',
    );
    expect(screen.queryByTestId('owner-claim-token')).not.toBeInTheDocument();
  });
});
