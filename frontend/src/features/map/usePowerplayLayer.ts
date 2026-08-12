import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { CommanderPowerplayResponse, PowerplaySystemsResponse } from '@/lib/api';

export function usePowerplayLayer(commanderKey: string, enabled: boolean) {
  const systems = useQuery<PowerplaySystemsResponse, Error>({
    queryKey: ['powerplay', commanderKey, 'systems'],
    queryFn: () => api.powerplaySystems(commanderKey),
    enabled: enabled && Boolean(commanderKey),
    staleTime: 60_000,
  });
  const commander = useQuery<CommanderPowerplayResponse, Error>({
    queryKey: ['powerplay', commanderKey, 'commander'],
    queryFn: () => api.powerplayCommander(commanderKey),
    enabled: enabled && Boolean(commanderKey),
    staleTime: 60_000,
  });
  return { systems, commander };
}
