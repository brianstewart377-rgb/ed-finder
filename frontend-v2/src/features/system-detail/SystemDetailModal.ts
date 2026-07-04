import { ColonisationAccessCard } from './ColonisationAccessCard';
import {
  SystemDetailModal as SystemDetailModalBase,
  type SystemDetailModalProps,
} from './SystemDetailModal.tsx';

export type { SystemDetailModalProps } from './SystemDetailModal.tsx';

/**
 * Adds the destination-first corridor entry to the established System Detail
 * modal without changing its existing inspection or normal-plan behaviour.
 *
 * This `.ts` module intentionally shadows the extension-less app import while
 * explicitly composing the established `.tsx` implementation.
 */
export function SystemDetailModal(props: SystemDetailModalProps) {
  const { onStartPlan, renderActions } = props;

  return (
    <SystemDetailModalBase
      {...props}
      renderActions={(system) => (
        <>
          {system ? (
            <div className="basis-full">
              <ColonisationAccessCard
                system={system}
                onStartCorridorPlan={(destination) => {
                  onStartPlan?.(destination, {
                    objective: 'destination_first_corridor',
                    startApproach: 'destination_first_corridor',
                  });
                }}
              />
            </div>
          ) : null}
          {renderActions?.(system)}
        </>
      )}
    />
  );
}
