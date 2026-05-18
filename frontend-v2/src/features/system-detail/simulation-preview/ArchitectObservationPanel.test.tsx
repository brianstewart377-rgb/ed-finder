import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ArchitectObservationPanel } from './ArchitectObservationPanel';

describe('ArchitectObservationPanel', () => {
  it('renders unknown Architect survey state as read-only guidance', () => {
    render(<ArchitectObservationPanel />);

    expect(screen.getByRole('region', { name: 'Architect observation status' })).toBeTruthy();
    expect(screen.getByText('Architect survey: not observed')).toBeTruthy();
    expect(screen.getByText('Primary-port flag: unknown')).toBeTruthy();
    expect(screen.getByText('Orbital slots: unknown')).toBeTruthy();
    expect(screen.getByText('Ground slots: unknown')).toBeTruthy();
    expect(screen.getByText('Primary-port flag is unknown until observed in Architect Mode.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /primary/i })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /primary/i })).toBeNull();
  });

  it('renders provided observed Architect context without edit controls', () => {
    render(
      <ArchitectObservationPanel
        observation={{
          surveyState: 'observed',
          orbitalSlotCount: 3,
          groundSlotCount: 2,
          primaryPortFlag: { state: 'observed', bodyName: 'A 1', slotLabel: 'Orbital slot 2' },
        }}
      />,
    );

    expect(screen.getByText('Architect survey: observed')).toBeTruthy();
    expect(screen.getByText('Primary-port flag: observed on A 1 / Orbital slot 2')).toBeTruthy();
    expect(screen.getByText('Orbital slots: 3')).toBeTruthy();
    expect(screen.getByText('Ground slots: 2')).toBeTruthy();
    expect(screen.getByText('If the flagged primary-port slot is inconvenient, consider an outpost there and place the main station elsewhere.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /make primary/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /remove primary/i })).toBeNull();
  });
});
