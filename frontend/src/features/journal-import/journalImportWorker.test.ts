import { describe, expect, it } from 'vitest';
import { parseFiles } from './journalImportWorker';

function journalFile(name: string, events: Record<string, unknown>[]): File {
  const text = events.map((event) => JSON.stringify(event)).join('\n');
  return new File([text], name, { type: 'text/plain' });
}

describe('journal import worker: Colonisation event system-context tracking', () => {
  it('attributes ColonisationSystemClaim/Release to their own SystemAddress', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'ColonisationSystemClaim',
        StarSystem: 'Claim System',
        SystemAddress: 111,
      },
      {
        timestamp: '2026-08-08T10:05:00Z',
        event: 'ColonisationSystemClaimRelease',
        StarSystem: 'Claim System',
        SystemAddress: 111,
      },
    ]);

    const result = await parseFiles([file]);

    expect(result.observations).toHaveLength(2);
    expect(result.observations.map((o) => o.event_type)).toEqual([
      'ColonisationSystemClaim',
      'ColonisationSystemClaimRelease',
    ]);
    expect(result.observations.every((o) => o.system_id64 === 111 && o.system_name === 'Claim System')).toBe(true);
  });

  it('attributes context-less Colonisation events to the most recently seen system', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Colony Prime',
        SystemAddress: 222,
      },
      {
        timestamp: '2026-08-08T10:10:00Z',
        event: 'ColonisationBeaconDeployed',
      },
      {
        timestamp: '2026-08-08T10:15:00Z',
        event: 'ColonisationConstructionDepot',
        MarketID: 999,
        ConstructionProgress: 0.5,
        ConstructionComplete: false,
        ConstructionFailed: false,
        ResourcesRequired: [
          { Name: 'steel', Name_Localised: 'Steel', RequiredAmount: 100, ProvidedAmount: 50, Payment: 0 },
        ],
      },
      {
        timestamp: '2026-08-08T10:20:00Z',
        event: 'ColonisationContribution',
        MarketID: 999,
        Contributions: [{ Name: 'steel', Name_Localised: 'Steel', Amount: 25 }],
      },
      {
        timestamp: '2026-08-08T10:30:00Z',
        event: 'CompleteConstruction',
      },
    ]);

    const result = await parseFiles([file]);

    expect(result.observations).toHaveLength(5);
    for (const observation of result.observations) {
      expect(observation.system_id64).toBe(222);
      expect(observation.system_name).toBe('Colony Prime');
    }

    const depot = result.observations.find((o) => o.event_type === 'ColonisationConstructionDepot');
    expect(depot?.payload).toEqual({
      MarketID: 999,
      ConstructionProgress: 0.5,
      ConstructionComplete: false,
      ConstructionFailed: false,
      ResourcesRequired: [
        { Name: 'steel', Name_Localised: 'Steel', RequiredAmount: 100, ProvidedAmount: 50, Payment: 0 },
      ],
    });

    const contribution = result.observations.find((o) => o.event_type === 'ColonisationContribution');
    expect(contribution?.payload).toEqual({
      MarketID: 999,
      Contributions: [{ Name: 'steel', Name_Localised: 'Steel', Amount: 25 }],
    });
  });

  it('carries system context across rotated journal files within the same session', async () => {
    const firstFile = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Colony Prime',
        SystemAddress: 222,
      },
    ]);
    // 5 minutes later, well inside SESSION_GAP_RESET_MS -- a real file
    // rotation, not a new session.
    const secondFile = journalFile('Journal.02.log', [
      {
        timestamp: '2026-08-08T10:05:00Z',
        event: 'CompleteConstruction',
      },
    ]);

    const result = await parseFiles([firstFile, secondFile]);

    const completion = result.observations.find((o) => o.event_type === 'CompleteConstruction');
    expect(completion?.system_id64).toBe(222);
    expect(completion?.system_name).toBe('Colony Prime');
  });

  it('drops a context-less Colonisation event that appears before any system context is known', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'ColonisationBeaconDeployed',
      },
    ]);

    const result = await parseFiles([file]);

    expect(result.observations).toHaveLength(0);
    expect(result.preview.skipped_lines).toBe(1);
  });

  it('resets tracked context across a large timestamp gap instead of misattributing to a stale system', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Old Session System',
        SystemAddress: 111,
      },
      // 90 minutes later -- past SESSION_GAP_RESET_MS (30 min), a different
      // play session's worth of files selected together.
      {
        timestamp: '2026-08-08T11:30:00Z',
        event: 'CompleteConstruction',
      },
    ]);

    const result = await parseFiles([file]);

    expect(result.observations.map((o) => o.event_type)).toEqual(['FSDJump']);
    expect(result.preview.skipped_lines).toBe(1);
  });

  it('does not fall back to stale context for an ordinarily self-contained event with a missing address', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Colony Prime',
        SystemAddress: 222,
      },
      // Docked normally carries its own SystemAddress; this one is missing
      // it (malformed/older record) and must be dropped, not silently
      // attributed to the previous FSDJump's system.
      {
        timestamp: '2026-08-08T10:05:00Z',
        event: 'Docked',
        StationName: 'Some Station',
      },
    ]);

    const result = await parseFiles([file]);

    expect(result.observations.map((o) => o.event_type)).toEqual(['FSDJump']);
    expect(result.preview.skipped_lines).toBe(1);
  });

  it('tracks context from a non-allowlisted event type that still carries a system address', async () => {
    const file = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Colony Prime',
        SystemAddress: 222,
      },
      // Not in ALLOWED_EVENT_TYPES, never staged as its own observation --
      // but it carries a newer system address that should still update the
      // tracked context for the context-less event after it.
      {
        timestamp: '2026-08-08T10:05:00Z',
        event: 'SupercruiseExit',
        StarSystem: 'Second System',
        SystemAddress: 333,
      },
      {
        timestamp: '2026-08-08T10:10:00Z',
        event: 'CompleteConstruction',
      },
    ]);

    const result = await parseFiles([file]);

    const completion = result.observations.find((o) => o.event_type === 'CompleteConstruction');
    expect(completion?.system_id64).toBe(333);
    expect(completion?.system_name).toBe('Second System');
  });

  it('sorts files chronologically by name before processing, regardless of selection order', async () => {
    const earlierFile = journalFile('Journal.01.log', [
      {
        timestamp: '2026-08-08T10:00:00Z',
        event: 'FSDJump',
        StarSystem: 'Colony Prime',
        SystemAddress: 222,
      },
    ]);
    const laterFile = journalFile('Journal.02.log', [
      {
        timestamp: '2026-08-08T10:05:00Z',
        event: 'CompleteConstruction',
      },
    ]);

    // Passed out of order (later file first) -- the worker must still sort
    // by filename before tracking context sequentially.
    const result = await parseFiles([laterFile, earlierFile]);

    const completion = result.observations.find((o) => o.event_type === 'CompleteConstruction');
    expect(completion?.system_id64).toBe(222);
  });
});
