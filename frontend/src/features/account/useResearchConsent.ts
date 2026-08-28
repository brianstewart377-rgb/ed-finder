import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getV3ResearchConsent, putV3ResearchConsent } from '@/lib/api';

export const RESEARCH_CONSENT_QUERY_KEY = ['v3-journal', 'consent'];

/**
 * Research-contribution consent state machine (NONE / GRANTED / WITHDRAWN).
 * The consent query only runs for authenticated users; grant/withdraw are
 * explicit user actions and invalidate the consent state on success.
 */
export function useResearchConsent(enabled: boolean) {
  const queryClient = useQueryClient();

  const consentQuery = useQuery({
    queryKey: RESEARCH_CONSENT_QUERY_KEY,
    queryFn: () => getV3ResearchConsent(),
    enabled,
  });

  const grantMutation = useMutation({
    mutationFn: () => putV3ResearchConsent({ decision: 'GRANT' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: RESEARCH_CONSENT_QUERY_KEY });
    },
  });

  const withdrawMutation = useMutation({
    mutationFn: () => putV3ResearchConsent({ decision: 'WITHDRAW' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: RESEARCH_CONSENT_QUERY_KEY });
    },
  });

  return {
    state: consentQuery.data ?? null,
    loading: consentQuery.isLoading,
    error: consentQuery.error,
    grant: () => grantMutation.mutateAsync(),
    withdraw: () => withdrawMutation.mutateAsync(),
    busy: grantMutation.isPending || withdrawMutation.isPending,
  };
}
