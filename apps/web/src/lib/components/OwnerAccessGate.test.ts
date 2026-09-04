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
    await fireEvent.input(screen.getByTestId('owner-claim-token'), {
      target: { value: 'token' },
    });
    await fireEvent.click(screen.getByTestId('owner-claim-submit'));
    await waitFor(() => expect(claimOwner).toHaveBeenCalledWith('token'));
  });
});
