import { useQuery } from '@tanstack/react-query';
import { getJournalTelemetry } from '@/lib/api';

export function useJournalTelemetrySummary(syncKey: string) {
  return useQuery({
    queryKey: ['journal-telemetry', syncKey],
    queryFn: () => getJournalTelemetry(syncKey),
    staleTime: 30_000,
    enabled: syncKey.trim().length >= 16,
  });
}
