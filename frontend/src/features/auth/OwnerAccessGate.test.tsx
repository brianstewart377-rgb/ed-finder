import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OwnerAccessGate } from './OwnerAccessGate';
import type { UseAuth } from './useAuth';

function auth(overrides: Partial<UseAuth> = {}): UseAuth {
  return {
    loading: false,
    authenticated: false,
    user: null,
    ownerClaimAvailable: false,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn().mockResolvedValue(undefined),
    claimOwner: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

const ACCOUNT_ID = '4ff3ff94-5815-42f0-a89d-66cd87b79155';

describe('OwnerAccessGate', () => {
  it('requires Frontier sign-in before rendering operational content', () => {
    const session = auth();
    render(
      <OwnerAccessGate auth={session}>
        <div data-testid="private-dashboard">Private dashboard</div>
      </OwnerAccessGate>,
    );

    expect(screen.queryByTestId('private-dashboard')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /sign in with frontier/i }));
    expect(session.signIn).toHaveBeenCalledTimes(1);
  });

  it('does not render operational content for a signed-in non-owner', () => {
    render(
      <OwnerAccessGate auth={auth({
        authenticated: true,
        user: { account_id: ACCOUNT_ID, commander_name: null, is_owner: false },
      })}>
        <div data-testid="private-dashboard">Private dashboard</div>
      </OwnerAccessGate>,
    );

    expect(screen.getByTestId('owner-access-denied')).toBeTruthy();
    expect(screen.queryByTestId('private-dashboard')).toBeNull();
  });

  it('allows the existing admin secret to assign the first owner once', async () => {
    const claimOwner = vi.fn().mockResolvedValue(undefined);
    render(
      <OwnerAccessGate auth={auth({
        authenticated: true,
        user: { account_id: ACCOUNT_ID, commander_name: null, is_owner: false },
        ownerClaimAvailable: true,
        claimOwner,
      })}>
        <div>Private dashboard</div>
      </OwnerAccessGate>,
    );

    fireEvent.change(screen.getByTestId('owner-claim-token'), {
      target: { value: 'existing-secret' },
    });
    fireEvent.click(screen.getByTestId('owner-claim-submit'));
    await waitFor(() => expect(claimOwner).toHaveBeenCalledWith('existing-secret'));
  });

  it('renders operational content for the owner role assignment only', () => {
    render(
      <OwnerAccessGate auth={auth({
        authenticated: true,
        user: { account_id: ACCOUNT_ID, commander_name: null, is_owner: true },
      })}>
        <div data-testid="private-dashboard">Private dashboard</div>
      </OwnerAccessGate>,
    );

    expect(screen.getByTestId('private-dashboard')).toBeTruthy();
  });
});

