import { useQuery } from '@tanstack/react-query';
import { getEvidenceSystemSummary } from '@/lib/api';
import type { EvidenceSystemSummaryResponse } from '@/types/api';

export interface UseSystemEvidenceSummary {
  data: EvidenceSystemSummaryResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSystemEvidenceSummary(id64: number | null): UseSystemEvidenceSummary {
  const q = useQuery<EvidenceSystemSummaryResponse, Error>({
    queryKey: ['system-evidence-summary', id64],
    enabled: id64 != null,
    queryFn: () => getEvidenceSystemSummary(id64 as number),
  });

  return {
    data: q.data ?? null,
    loading: q.isLoading,
    error: q.error ? q.error.message : null,
    refetch: () => { void q.refetch(); },
  };
}
