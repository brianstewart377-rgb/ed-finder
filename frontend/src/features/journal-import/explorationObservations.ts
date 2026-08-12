import type {
  ExplorationObservationInput,
  JournalImportObservationInput,
} from '@/types/api';

const EXPLORATION_EVENTS = new Set<ExplorationObservationInput['event_type']>([
  'CarrierJump', 'FSDJump', 'Location', 'Scan', 'FSSDiscoveryScan',
  'FSSAllBodiesFound', 'SAASignalsFound', 'FSSBodySignals', 'CodexEntry',
  'SAAScanComplete', 'ScanOrganic', 'SellOrganicData', 'SellExplorationData',
  'MultiSellExplorationData',
]);

export function toExplorationObservations(
  observations: JournalImportObservationInput[],
): ExplorationObservationInput[] {
  return observations.flatMap((observation) => {
    if (
      !EXPLORATION_EVENTS.has(observation.event_type as ExplorationObservationInput['event_type'])
      || observation.system_id64 == null
      || !observation.observed_at
    ) return [];
    const payloadBodyName = typeof observation.payload.BodyName === 'string'
      ? observation.payload.BodyName
      : null;
    const numericSubjectId = observation.subject_type === 'body'
      && observation.subject_id != null
      && /^\d+$/.test(observation.subject_id)
      ? observation.subject_id
      : null;
    return [{
      observation_key: observation.observation_key,
      event_type: observation.event_type as ExplorationObservationInput['event_type'],
      observed_at: observation.observed_at,
      system_id64: observation.system_id64,
      system_name: observation.system_name,
      body_id: numericSubjectId,
      body_name: payloadBodyName ?? (
        observation.subject_type === 'body' && numericSubjectId == null
          ? observation.subject_id
          : null
      ),
      payload: observation.payload,
    }];
  });
}
