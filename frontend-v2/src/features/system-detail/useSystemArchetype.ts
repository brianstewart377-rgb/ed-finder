import { useQuery } from '@tanstack/react-query';
import { getSystemArchetype } from '@/lib/api';
import type { SystemArchetypeResponse } from '@/types/api';

export interface UseSystemArchetype {
  data: SystemArchetypeResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSystemArchetype(id64: number | null): UseSystemArchetype {
  const q = useQuery<SystemArchetypeResponse, Error>({
    queryKey: ['system-archetype', id64],
    enabled: id64 != null,
    queryFn: () => getSystemArchetype(id64 as number),
  });

  return {
    data: q.data ?? null,
    loading: q.isLoading,
    error: q.error ? q.error.message : null,
    refetch: () => { void q.refetch(); },
  };
}
