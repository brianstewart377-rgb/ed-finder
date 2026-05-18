import { Telescope } from 'lucide-react';
import type { ArchitectObservationInput } from './architectObservationUtils';
import {
  architectObservationGuidance,
  architectPrimaryPortFlagLabel,
  architectSlotCountLabel,
  architectSurveyLabel,
  normalizeArchitectObservation,
} from './architectObservationUtils';
import { Chip } from './components';

export function ArchitectObservationPanel({
  observation,
  compact = false,
  showPrimaryPortPlacementReminder = false,
}: {
  observation?: ArchitectObservationInput | null;
  compact?: boolean;
  showPrimaryPortPlacementReminder?: boolean;
}) {
  const status = normalizeArchitectObservation(observation);
  const guidance = architectObservationGuidance(status, { showPrimaryPortPlacementReminder });

  return (
    <section
      aria-label="Architect observation status"
      data-testid="architect-observation-panel"
      className={[
        'rounded border border-cyan/25 bg-cyan/5 text-[11px] leading-snug text-silver-dk',
        compact ? 'px-2 py-1.5' : 'px-3 py-2',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        <Telescope size={13} />
        Architect observation
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <Chip tone={status.surveyState === 'observed' ? 'good' : 'default'}>{architectSurveyLabel(status)}</Chip>
        <Chip tone={status.primaryPortFlag.state === 'observed' ? 'good' : 'warn'}>
          {architectPrimaryPortFlagLabel(status)}
        </Chip>
        <Chip>{architectSlotCountLabel('Orbital slots', status.orbitalSlotCount)}</Chip>
        <Chip>{architectSlotCountLabel('Ground slots', status.groundSlotCount)}</Chip>
        <Chip>Read-only</Chip>
      </div>
      <ul className="mt-2 space-y-1">
        {guidance.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
