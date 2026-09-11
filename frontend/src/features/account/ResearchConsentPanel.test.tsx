import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getV3ResearchConsent, putV3ResearchConsent } from '@/lib/api';
import { useAuth } from '@/features/auth/useAuth';
import type { V3ResearchConsentState } from '@/lib/api';
import { ResearchConsentPanel, RESEARCH_CONSENT_COPY } from './ResearchConsentPanel';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    getV3ResearchConsent: vi.fn(),
    putV3ResearchConsent: vi.fn(),
  };
});

vi.mock('@/features/auth/useAuth', () => ({
  useAuth: vi.fn(),
}));

const mockedGetV3ResearchConsent = vi.mocked(getV3ResearchConsent);
const mockedPutV3ResearchConsent = vi.mocked(putV3ResearchConsent);
const mockedUseAuth = vi.mocked(useAuth);

function consentState(overrides: Partial<V3ResearchConsentState>): V3ResearchConsentState {
  return {
    decision: 'NONE',
    consent_version: null,
    sanitized_contract_version: null,
    purpose: null,
    audience_code: null,
    decided_at: null,
    withdrawable: false,
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ResearchConsentPanel />
    </QueryClientProvider>,
  );
}

describe('ResearchConsentPanel', () => {
  afterEach(() => {
    mockedGetV3ResearchConsent.mockReset();
    mockedPutV3ResearchConsent.mockReset();
    mockedUseAuth.mockReset();
  });

  it('shows the honest pseudonymous copy and the opt-in button when consent is NONE', async () => {
    mockedUseAuth.mockReturnValue({
      loading: false,
      authenticated: true,
      user: { commander_name: 'Test' } as never,
      ownerClaimAvailable: false,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      claimOwner: vi.fn(),
      refresh: vi.fn(),
    });
    mockedGetV3ResearchConsent.mockResolvedValue(consentState({ decision: 'NONE' }));

    renderPanel();

    expect(await screen.findByTestId('research-consent-share')).toBeTruthy();
    expect(screen.getByTestId('research-consent-card').textContent).toContain(RESEARCH_CONSENT_COPY);
    expect(screen.getByTestId('research-consent-card').textContent).toContain('Sanitized and pseudonymous — not anonymous.');
    expect(screen.getByTestId('research-consent-state').textContent).toContain('No contribution');
    // Journal upload is never conditioned on consent — no upload control here.
    expect(screen.queryByTestId('journal-upload-panel')).toBeNull();
  });

  it('grants on the explicit opt-in and then shows the granted state with version and date', async () => {
    mockedUseAuth.mockReturnValue({
      loading: false,
      authenticated: true,
      user: { commander_name: 'Test' } as never,
      ownerClaimAvailable: false,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      claimOwner: vi.fn(),
      refresh: vi.fn(),
    });
    mockedGetV3ResearchConsent
      .mockResolvedValueOnce(consentState({ decision: 'NONE' }))
      .mockResolvedValue(consentState({
        decision: 'GRANT',
        consent_version: '1.0',
        sanitized_contract_version: '1.0.0',
        purpose: 'CRE_RESEARCH_EVIDENCE',
        audience_code: 'CRE',
        decided_at: '2026-08-28T10:00:00Z',
        withdrawable: true,
      }));
    mockedPutV3ResearchConsent.mockResolvedValue(consentState({
      decision: 'GRANT',
      consent_version: '1.0',
      decided_at: '2026-08-28T10:00:00Z',
      withdrawable: true,
    }));

    renderPanel();
    fireEvent.click(await screen.findByTestId('research-consent-share'));

    await waitFor(() => expect(mockedPutV3ResearchConsent).toHaveBeenCalledWith({ decision: 'GRANT' }));
    expect(await screen.findByTestId('research-consent-granted')).toBeTruthy();
    expect(screen.getByTestId('research-consent-granted').textContent).toContain('consent 1.0 since');
    expect(screen.getByTestId('research-consent-state').textContent).toContain('Contributing');
    expect(screen.getByTestId('research-consent-withdraw')).toBeTruthy();
  });

  it('withdraws an active contribution and shows the withdrawn state', async () => {
    mockedUseAuth.mockReturnValue({
      loading: false,
      authenticated: true,
      user: { commander_name: 'Test' } as never,
      ownerClaimAvailable: false,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      claimOwner: vi.fn(),
      refresh: vi.fn(),
    });
    mockedGetV3ResearchConsent
      .mockResolvedValueOnce(consentState({
        decision: 'GRANT',
        consent_version: '1.0',
        decided_at: '2026-08-28T10:00:00Z',
        withdrawable: true,
      }))
      .mockResolvedValue(consentState({ decision: 'WITHDRAW', consent_version: '1.0', decided_at: '2026-08-28T11:00:00Z' }));
    mockedPutV3ResearchConsent.mockResolvedValue(consentState({ decision: 'WITHDRAW', consent_version: '1.0' }));

    renderPanel();
    fireEvent.click(await screen.findByTestId('research-consent-withdraw'));

    await waitFor(() => expect(mockedPutV3ResearchConsent).toHaveBeenCalledWith({ decision: 'WITHDRAW' }));
    await waitFor(() => expect(screen.getByTestId('research-consent-state').textContent).toContain('Withdrawn'));
    // Withdrawn still offers the explicit opt-in again (server decides re-grant).
    expect(screen.getByTestId('research-consent-share')).toBeTruthy();
  });

  it('never queries consent for anonymous visitors (enabled: !!user)', async () => {
    mockedUseAuth.mockReturnValue({
      loading: false,
      authenticated: false,
      user: null,
      ownerClaimAvailable: false,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      claimOwner: vi.fn(),
      refresh: vi.fn(),
    });

    renderPanel();
    await waitFor(() => expect(mockedGetV3ResearchConsent).not.toHaveBeenCalled());
  });
});
