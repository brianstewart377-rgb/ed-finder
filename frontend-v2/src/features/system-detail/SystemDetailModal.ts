import { createElement, Fragment } from 'react';
import type { SystemDetail } from '@/types/api';
import { ColonisationAccessCard } from './ColonisationAccessCard';
import {
  SystemDetailModal as SystemDetailModalBase,
  type SystemDetailModalProps,
} from './SystemDetailModal.tsx';

export type { SystemDetailModalProps } from './SystemDetailModal.tsx';

type RenderActionSystem = Parameters<NonNullable<SystemDetailModalProps['renderActions']>>[0];

/**
 * Adds the destination-first corridor entry to the established System Detail
 * modal without changing its existing inspection or normal-plan behaviour.
 *
 * This `.ts` module intentionally shadows the extension-less app import while
 * explicitly composing the established `.tsx` implementation.
 */
export function SystemDetailModal(props: SystemDetailModalProps) {
  const { onStartPlan, renderActions } = props;
  const renderColonisationActions = (system: RenderActionSystem) => createElement(
    Fragment,
    null,
    system
      ? createElement(
        'div',
        { className: 'basis-full' },
        createElement(ColonisationAccessCard, {
          system: system as SystemDetail,
          onStartCorridorPlan: (destination: SystemDetail) => {
            onStartPlan?.(destination, {
              objective: 'destination_first_corridor',
              startApproach: 'destination_first_corridor',
            });
          },
        }),
      )
      : null,
    renderActions?.(system),
  );

  return createElement(SystemDetailModalBase, {
    ...props,
    renderActions: renderColonisationActions,
  });
}
