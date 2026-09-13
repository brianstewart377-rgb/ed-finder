import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '$lib/api/client';
import { parseJournals } from '$lib/journal/parse';
import JournalAccountPanel from './JournalAccountPanel.svelte';

vi.mock('$lib/api/client', () => ({
  getVerifiedCommanders: vi.fn(),
  importVerifiedJournals: vi.fn(),
  offerGalaxyFacts: vi.fn(),
  getGalaxyContributions: vi.fn(),
  withdrawGalaxyContribution: vi.fn(),
}));
vi.mock('$lib/journal/parse', () => ({ parseJournals: vi.fn() }));
vi.mock('$lib/auth/auth', () => ({ auth: { signIn: vi.fn() } }));

const hash = 'a'.repeat(64);
const saved: api.V3VerifiedImportReceipt = {
  import_ids: ['original-import'],
  files_admitted: 1,
  files_skipped: 0,
  events_inserted: 2,
  duplicates_skipped: 0,
  held_files: [{ name: 'another.log', reason: 'commander_not_linked' }],
};

async function selectFile() {
  await screen.findByText(/F123/);
  await fireEvent.change(screen.getByLabelText('Select journal logs'), {
    target: { files: [new File(['journal'], 'mine.log')] },
  });
}

describe('private journal import and explicit sharing', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getVerifiedCommanders).mockResolvedValue([
      {
        commander_id: 'commander',
        commander_name: 'Test Commander',
        journal_fid: 'F123',
        verified_at: '2026-01-01T00:00:00Z',
      },
    ]);
    vi.mocked(api.getGalaxyContributions).mockResolvedValue([]);
    vi.mocked(api.importVerifiedJournals).mockResolvedValue(saved);
    vi.mocked(api.offerGalaxyFacts).mockResolvedValue({
      new_offers: 1,
      already_offered: 0,
      skipped: {},
    });
    vi.mocked(parseJournals).mockResolvedValue({
      body: {
        parser_version: 'test',
        files: [
          {
            name: 'mine.log',
            content_sha256: hash,
            size_bytes: 7,
            line_count: 2,
            event_count: 2,
          },
        ],
        events: [],
      },
      held: [],
    });
  });
  afterEach(cleanup);

  it('keeps sharing off by default and reports held files alongside successful imports', async () => {
    render(JournalAccountPanel);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    await selectFile();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Import journals' }),
    );
    await screen.findByText(/2 events saved/);
    expect(
      screen.getByText(/another.log: commander not linked/),
    ).toBeInTheDocument();
    expect(api.offerGalaxyFacts).not.toHaveBeenCalled();
  });

  it('retries a failed explicit sharing request with only the selected file hashes', async () => {
    vi.mocked(api.offerGalaxyFacts).mockRejectedValueOnce(new Error('offline'));
    render(JournalAccountPanel);
    await selectFile();
    await fireEvent.click(screen.getByRole('checkbox'));
    await fireEvent.click(
      screen.getByRole('button', { name: 'Import journals' }),
    );
    await screen.findByText(/Your Journal is saved. Sharing needs a retry/);
    await fireEvent.click(
      screen.getByRole('button', { name: 'Retry sharing saved import' }),
    );
    await waitFor(() => expect(api.offerGalaxyFacts).toHaveBeenCalledTimes(2));
    expect(api.offerGalaxyFacts).toHaveBeenLastCalledWith(
      'original-import',
      [hash],
      expect.any(AbortSignal),
    );
    expect(api.importVerifiedJournals).toHaveBeenCalledOnce();
  });

  it('aborts work on account-panel removal and ignores a late response', async () => {
    let complete!: (value: api.V3VerifiedImportReceipt) => void;
    vi.mocked(api.importVerifiedJournals).mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    const panel = render(JournalAccountPanel);
    await selectFile();
    await fireEvent.click(screen.getByRole('checkbox'));
    await fireEvent.click(
      screen.getByRole('button', { name: 'Import journals' }),
    );
    await waitFor(() =>
      expect(api.importVerifiedJournals).toHaveBeenCalledOnce(),
    );
    const signal = vi.mocked(api.importVerifiedJournals).mock.calls[0][1]!;
    panel.unmount();
    expect(signal.aborted).toBe(true);
    complete(saved);
    await Promise.resolve();
    expect(api.offerGalaxyFacts).not.toHaveBeenCalled();
  });

  it('keeps verified commanders usable if loading contribution history fails', async () => {
    vi.mocked(api.getGalaxyContributions).mockRejectedValue(
      new Error('offline'),
    );
    render(JournalAccountPanel);
    await selectFile();
    expect(
      screen.getByRole('button', { name: 'Import journals' }),
    ).toBeEnabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Some account data');
  });
});
