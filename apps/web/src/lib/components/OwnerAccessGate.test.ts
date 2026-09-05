import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OwnerAccessGate from './OwnerAccessGate.svelte';

afterEach(cleanup);
const base = {
  loading: false,
  authenticated: false,
  user: null,
  ownerClaimAvailable: false,
  error: null,
};

describe('OwnerAccessGate', () => {
  it('keeps signed-out users away from operational content', () => {
    render(OwnerAccessGate, {
      props: {
        authState: base,
        signIn: vi.fn(),
        signOut: vi.fn(),
        claimOwner: vi.fn(),
        children: (() => {}) as never,
      },
    });
    expect(screen.getByTestId('owner-sign-in-required')).toBeInTheDocument();
  });
  it('offers the bounded owner claim only when available', async () => {
    const claimOwner = vi.fn().mockResolvedValue(undefined);
    render(OwnerAccessGate, {
      props: {
        authState: {
          ...base,
          authenticated: true,
          user: { commander_name: 'Cmdr', is_owner: false },
          ownerClaimAvailable: true,
        },
        signIn: vi.fn(),
        signOut: vi.fn(),
        claimOwner,
        children: (() => {}) as never,
      },
    });
    const input = screen.getByTestId('owner-claim-token');
    await fireEvent.input(input, {
      target: { value: 'token' },
    });
    await fireEvent.click(screen.getByTestId('owner-claim-submit'));
    await waitFor(() => expect(claimOwner).toHaveBeenCalledWith('token'));
    await waitFor(() => expect(input).toHaveValue(''));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps the password input and reports a failed owner claim', async () => {
    const claimOwner = vi
      .fn()
      .mockRejectedValue(new Error('Invalid admin token'));
    render(OwnerAccessGate, {
      props: {
        authState: {
          ...base,
          authenticated: true,
          user: { commander_name: 'Cmdr', is_owner: false },
          ownerClaimAvailable: true,
        },
        signIn: vi.fn(),
        signOut: vi.fn(),
        claimOwner,
        children: (() => {}) as never,
      },
    });
    const input = screen.getByTestId('owner-claim-token');
    await fireEvent.input(input, {
      target: { value: 'rejected-token' },
    });
    await fireEvent.click(screen.getByTestId('owner-claim-submit'));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Invalid admin token',
      ),
    );
    expect(input).toHaveValue('rejected-token');
    expect(screen.getByTestId('owner-access-denied')).toBeInTheDocument();
  });
});
